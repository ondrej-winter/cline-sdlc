"""Shared deterministic fixtures for plan-finalization tests."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)
from cline_sdlc.features.repository_coordination.application.dtos.finalization import RepositoryFinalizationRequest
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval

if TYPE_CHECKING:
    from pathlib import Path

PLAN_PATH = "docs/plan.md"
SPECIFICATION_PATH = "docs/spec.md"
WORK_ID = "finalization-work"
SPECIFICATION = b"# Specification\n"
SPECIFICATION_DIGEST = compute_specification_digest(SPECIFICATION)
APPROVED_AT = datetime(2026, 7, 26, 18, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 7, 26, 19, 0, tzinfo=UTC)


def initialized_repository(tmp_path: Path) -> Path:
    """Create a clean feature-branch repository with an implementing plan."""
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init", "--initial-branch", "feature/task-5.4")
    git(repository, "config", "user.email", "cline-sdlc@example.test")
    git(repository, "config", "user.name", "Cline SDLC Tests")
    write(repository, SPECIFICATION_PATH, SPECIFICATION)
    write(repository, PLAN_PATH, plan("implementing"))
    git(repository, "add", SPECIFICATION_PATH, PLAN_PATH)
    git(repository, "commit", "-m", "Add implementation awaiting finalization")
    return repository


def finalization_request(repository: Path) -> RepositoryFinalizationRequest:
    """Build strict complete and recovery transitions for the current HEAD."""
    head = git_stdout(repository, "rev-parse", "HEAD")
    current = (repository / PLAN_PATH).read_bytes()
    approval = InvocationApproval(
        run_id="run-finalization",
        profile="balanced",
        starting_head=head,
        approved_at=APPROVED_AT,
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=material_digest(current),
        remediation_envelope_applicable=True,
    )
    return RepositoryFinalizationRequest(
        repository_root=repository,
        plan_path=PLAN_PATH,
        current_plan_content=current,
        approval=approval,
        completed_plan_content=plan("complete", completed_at=COMPLETED_AT),
        recovery_plan_content=plan("blocked", start_commit=head),
        completed_at=COMPLETED_AT,
    )


def complete_noop_request(repository: Path) -> RepositoryFinalizationRequest:
    """Build a read-only request for the currently committed complete plan."""
    current = (repository / PLAN_PATH).read_bytes()
    return RepositoryFinalizationRequest(
        repository_root=repository,
        plan_path=PLAN_PATH,
        current_plan_content=current,
        approval=InvocationApproval(
            run_id="run-noop",
            profile="balanced",
            starting_head=git_stdout(repository, "rev-parse", "HEAD"),
            approved_at=APPROVED_AT,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=material_digest(current),
            remediation_envelope_applicable=True,
        ),
    )


def plan(phase: str, *, completed_at: datetime | None = None, start_commit: str | None = None) -> bytes:
    """Render one strict plan with stable material and configurable progress state."""
    active = phase == "blocked"
    blocker = (
        "\n  code: finalization_commit_failed\n  summary: Finalization commit failed and requires recovery."
        if active
        else " null"
    )
    completed_value = "null" if completed_at is None else timestamp(completed_at)
    updated = completed_at or COMPLETED_AT
    template = f"""# Plan

<!-- cline-sdlc-material:start -->
## Objective
Deliver verified finalization.
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
current_task: {"finalization" if active else "null"}
current_slice: {"finalization" if active else "null"}
slice_start_commit: {start_commit if active else "null"}
partial_slice_paths:{f"\n  - {PLAN_PATH}" if active else " []"}
completed_slices:
  - task-1
remediation_records:
  - finding_id: FINAL-001
    requirement: Preserve approved behavior.
    path_scope:
      - src/example.py
    correction: Restore approved behavior.
    verification: uv run pytest tests/example.py
    status: completed
    attempt_count: 1
validation_evidence:
  - slice_id: task-1
    command: uv run pytest
    result: passed
    exit_code: 0
    recorded_at: 2026-07-26T18:30:00Z
blocker:{blocker}
created_at: 2026-07-26T17:00:00Z
updated_at: {timestamp(updated)}
completed_at: {completed_value}
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


def material_digest(content: bytes) -> str:
    """Return the stored digest from a fixture plan."""
    marker = b"material_digest: "
    return content.split(marker, maxsplit=1)[1].splitlines()[0].decode()


def timestamp(value: datetime) -> str:
    """Render an explicit UTC timestamp."""
    return value.isoformat().replace("+00:00", "Z")


def write(repository: Path, relative_path: str, content: bytes) -> None:
    """Write fixture bytes under the repository."""
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def git(cwd: Path, *arguments: str) -> None:
    """Run a non-interactive Git fixture command."""
    subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def git_stdout(cwd: Path, *arguments: str) -> str:
    """Return stripped stdout from a non-interactive Git fixture command."""
    completed = subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()
