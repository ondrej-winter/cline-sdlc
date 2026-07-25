"""Integration tests for explicit atomic implementation-slice commits."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import parse_plan_state_from_markdown
from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import SliceCommitCandidate
from cline_sdlc.features.repository_coordination.adapters.outbound.git_slice_commit import GitCliSliceCommitter
from cline_sdlc.features.repository_coordination.adapters.outbound.plan_artifact import StrictPlanArtifactInspector
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
    SliceCommitRequest,
    SliceCommitStatus,
)
from cline_sdlc.features.repository_coordination.application.use_cases.commit_slice import CommitSlice

if TYPE_CHECKING:
    from pathlib import Path

PLAN_PATH = "docs/plan.md"
SOURCE_PATH = "src/feature.py"
SPECIFICATION_PATH = "docs/spec.md"
SLICE_ID = "task-4.4"
WORK_ID = "test-work"
SPECIFICATION = b"# Specification\n"
SPECIFICATION_DIGEST = compute_specification_digest(SPECIFICATION)


def test_creates_one_explicit_hook_enabled_slice_commit(tmp_path: Path) -> None:
    repository, request = _prepared_request(tmp_path)
    hook_marker = repository / ".git/hook-ran"
    _hook(repository, f"#!/bin/sh\ntouch {hook_marker}\n")

    result = _use_case().execute(request)

    assert result.status is SliceCommitStatus.COMMITTED
    assert result.commit == _git_stdout(repository, "rev-parse", "HEAD")
    assert hook_marker.is_file()
    assert _git_stdout(repository, "status", "--porcelain=v1") == ""
    assert set(_git_stdout(repository, "show", "--format=", "--name-only", "HEAD").splitlines()) == {
        PLAN_PATH,
        SOURCE_PATH,
    }
    message = _git_stdout(repository, "show", "-s", "--format=%B", "HEAD")
    assert message.count("Cline-SDLC-Work-ID:") == 1
    assert message.count("Cline-SDLC-Slice-ID:") == 1
    assert message.count("Cline-SDLC-Slice-Kind:") == 1
    assert message.count("Cline-SDLC-Material-Digest:") == 1
    assert "Cline-SDLC-Slice-Kind: implementation" in message
    state = parse_plan_state_from_markdown((repository / PLAN_PATH).read_text(encoding="utf-8"))
    assert state.completed_slices == (SLICE_ID,)
    assert not state.has_active_slice
    assert result.commit not in (repository / PLAN_PATH).read_text(encoding="utf-8")


def test_hook_failure_leaves_verified_changes_uncommitted_and_unstaged(tmp_path: Path) -> None:
    repository, request = _prepared_request(tmp_path)
    starting_head = request.candidate.starting_head
    _hook(repository, "#!/bin/sh\necho hook rejected >&2\nexit 1\n")

    result = _use_case().execute(request)

    assert result.status is SliceCommitStatus.RECOVERY_REQUIRED
    assert result.recovery is not None
    assert result.recovery.paths == request.candidate.paths
    assert result.blocker is not None
    assert "hook rejected" in (result.blocker.evidence or "")
    assert _git_stdout(repository, "rev-parse", "HEAD") == starting_head
    assert _git_stdout(repository, "diff", "--cached", "--name-only") == ""
    assert set(_status_paths(repository)) == set(request.candidate.paths)
    state = parse_plan_state_from_markdown((repository / PLAN_PATH).read_text(encoding="utf-8"))
    assert state.completed_slices == (SLICE_ID,)


def test_unrelated_dirty_path_prevents_staging_or_plan_write(tmp_path: Path) -> None:
    repository, request = _prepared_request(tmp_path)
    (repository / "unrelated.txt").write_text("human work\n", encoding="utf-8")

    result = _use_case().execute(request)

    assert result.status is SliceCommitStatus.RECOVERY_REQUIRED
    assert _git_stdout(repository, "rev-parse", "HEAD") == request.candidate.starting_head
    assert _git_stdout(repository, "diff", "--cached", "--name-only") == ""
    assert (repository / PLAN_PATH).read_bytes() == request.current_plan_content


def test_moved_head_prevents_staging_or_plan_write(tmp_path: Path) -> None:
    repository, request = _prepared_request(tmp_path)
    (repository / "later.txt").write_text("later commit\n", encoding="utf-8")
    _git(repository, "add", "later.txt")
    _git(repository, "commit", "-m", "Add later human commit")

    result = _use_case().execute(request)

    assert result.status is SliceCommitStatus.RECOVERY_REQUIRED
    assert _git_stdout(repository, "diff", "--cached", "--name-only") == ""
    assert (repository / PLAN_PATH).read_bytes() == request.current_plan_content


def test_invalid_completion_transition_blocks_before_git_effects(tmp_path: Path) -> None:
    repository, request = _prepared_request(tmp_path)
    invalid_update = _plan(phase="implementing", completed=(), active=False)
    request = SliceCommitRequest(
        repository_root=request.repository_root,
        plan_path=request.plan_path,
        current_plan_content=request.current_plan_content,
        updated_plan_content=invalid_update,
        candidate=request.candidate,
        short_description=request.short_description,
    )

    result = _use_case().execute(request)

    assert result.status is SliceCommitStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "slice_completion_transition_invalid"
    assert _git_stdout(repository, "rev-parse", "HEAD") == request.candidate.starting_head
    assert (repository / PLAN_PATH).read_bytes() == request.current_plan_content


def _prepared_request(tmp_path: Path) -> tuple[Path, SliceCommitRequest]:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--initial-branch", "feature/task-4.4")
    _git(repository, "config", "user.email", "cline-sdlc@example.test")
    _git(repository, "config", "user.name", "Cline SDLC Tests")
    _write(repository, SPECIFICATION_PATH, SPECIFICATION)
    _write(repository, PLAN_PATH, _plan(phase="ready", completed=(), active=False))
    _write(repository, SOURCE_PATH, b"VALUE = 1\n")
    _git(repository, "add", SPECIFICATION_PATH, PLAN_PATH, SOURCE_PATH)
    _git(repository, "commit", "-m", "Add ready implementation fixture")
    starting_head = _git_stdout(repository, "rev-parse", "HEAD")

    current_plan = _plan(phase="implementing", completed=(), active=True, start_commit=starting_head)
    updated_plan = _plan(phase="implementing", completed=(SLICE_ID,), active=False)
    _write(repository, PLAN_PATH, current_plan)
    _write(repository, SOURCE_PATH, b"VALUE = 2\n")
    material_digest = parse_plan_state_from_markdown(current_plan.decode()).material_digest
    candidate = SliceCommitCandidate(
        work_id=WORK_ID,
        task_id="task-4",
        slice_id=SLICE_ID,
        starting_head=starting_head,
        material_digest=material_digest,
        paths=(PLAN_PATH, SOURCE_PATH),
        validation_evidence=(),
    )
    return repository, SliceCommitRequest(
        repository_root=repository,
        plan_path=PLAN_PATH,
        current_plan_content=current_plan,
        updated_plan_content=updated_plan,
        candidate=candidate,
        short_description="add atomic commit support",
    )


def _plan(
    *,
    phase: str,
    completed: tuple[str, ...],
    active: bool,
    start_commit: str | None = None,
) -> bytes:
    completed_yaml = "[]" if not completed else "\n" + "\n".join(f"  - {item}" for item in completed)
    current_task = "task-4" if active else "null"
    current_slice = SLICE_ID if active else "null"
    slice_start_commit = start_commit if active else "null"
    partial_paths = f"\n  - {PLAN_PATH}\n  - {SOURCE_PATH}" if active else "[]"
    template = f"""# Plan

<!-- cline-sdlc-material:start -->
## Objective
Deliver atomic commits.
<!-- cline-sdlc-material:end -->

<!-- cline-sdlc-progress:start -->
```cline-sdlc-state
schema_version: 1
work_id: {WORK_ID}
profile: balanced
phase: {phase}
specification: {SPECIFICATION_PATH}
specification_digest: {SPECIFICATION_DIGEST}
plan_revision: 1
review_iteration: 1
review_readiness: ready
digest_schema_version: 1
material_digest: sha256:{"0" * 64}
current_task: {current_task}
current_slice: {current_slice}
slice_start_commit: {slice_start_commit}
partial_slice_paths: {partial_paths}
completed_slices: {completed_yaml}
remediation_records: []
validation_evidence:
  - slice_id: {SLICE_ID}
    command: uv run pytest tests/integration/features/repository_coordination/test_slice_commit.py
    result: passed
    exit_code: 0
    recorded_at: 2026-07-25T20:00:00Z
blocker: null
created_at: 2026-07-25T19:00:00Z
updated_at: 2026-07-25T20:00:00Z
completed_at: null
```
<!-- cline-sdlc-progress:end -->
""".encode()
    digest = compute_plan_material_digest(
        PlanMaterialDigestInput(
            plan_markdown=template,
            plan_revision=1,
            specification=SPECIFICATION_PATH,
            specification_digest=SPECIFICATION_DIGEST,
        )
    )
    return template.replace(f"sha256:{'0' * 64}".encode(), digest.encode())


def _use_case() -> CommitSlice:
    return CommitSlice(StrictPlanArtifactInspector(), GitCliSliceCommitter())


def _hook(repository: Path, content: str) -> None:
    hook = repository / ".git/hooks/pre-commit"
    hook.write_text(content, encoding="utf-8")
    hook.chmod(0o755)


def _write(repository: Path, relative_path: str, content: bytes) -> None:
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _status_paths(repository: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ("git", "--no-pager", "status", "--porcelain=v1", "--untracked-files=all"),  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout
    return tuple(line[3:] for line in output.splitlines())


def _git(cwd: Path, *arguments: str) -> None:
    subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()
