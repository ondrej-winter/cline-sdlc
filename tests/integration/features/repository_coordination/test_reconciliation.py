"""Integration tests for plan ownership reconciliation and invocation approval."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PlanSliceDefinition,
    PlanTaskDefinition,
    SliceCompletionEvidence,
    SliceSelectionRequest,
)
from cline_sdlc.features.repository_coordination.adapters.outbound.audit_approval import (
    RunAuditInvocationApprovalRecorder,
)
from cline_sdlc.features.repository_coordination.adapters.outbound.git_history import GitCliPlanHistoryReader
from cline_sdlc.features.repository_coordination.adapters.outbound.plan_artifact import StrictPlanArtifactInspector
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import (
    PlanReconciliationRequest,
    PlanReconciliationResult,
    PlanReconciliationStatus,
)
from cline_sdlc.features.repository_coordination.application.use_cases.reconcile_plan import ReconcilePlan
from cline_sdlc.features.run_audit.adapters.outbound.filesystem_store import FilesystemRunAuditStore
from cline_sdlc.features.run_audit.application.use_cases.record_invocation_approval import RecordInvocationApproval

if TYPE_CHECKING:
    from pathlib import Path

SPECIFICATION_PATH = "docs/spec.md"
PLAN_PATH = "docs/plan.md"
APPROVED_AT = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def test_authorizes_next_slice_after_verifying_unique_owning_commit(tmp_path: Path) -> None:
    repository, specification = _repository_with_completed_slice(tmp_path)
    plan = (repository / PLAN_PATH).read_bytes()

    result = _reconciler().execute(_request(repository, specification, plan))

    assert result.status is PlanReconciliationStatus.AUTHORIZED
    assert result.selection is not None
    assert result.selection.slice_id == "slice-2"
    assert result.approval is not None
    assert result.approval.starting_head == _git_stdout(repository, "rev-parse", "HEAD")
    assert result.owning_commits[0][0] == "slice-1"
    payload = json.loads((repository / ".cline-sdlc/runs/run-1/approval.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-1"
    assert payload["profile"] == "balanced"
    assert payload["remediation_envelope_applicable"] is True


def test_records_approval_before_blocking_missing_slice_owner(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    specification = b"# Specification\n"
    plan = _plan(specification, completed=("slice-1",))
    _write(repository, SPECIFICATION_PATH, specification)
    _write(repository, PLAN_PATH, plan)
    _git(repository, "add", SPECIFICATION_PATH, PLAN_PATH)
    _git(repository, "commit", "-m", "Add inconsistent plan progress")

    result = _reconciler().execute(_request(repository, specification, plan))

    assert _blocker_code(result) == "slice_owner_missing"
    assert (repository / ".cline-sdlc/runs/run-1/approval.json").is_file()


def test_blocks_duplicate_reachable_owner_claims(tmp_path: Path) -> None:
    repository, specification = _repository_with_completed_slice(tmp_path)
    plan = (repository / PLAN_PATH).read_bytes()
    _write(repository, "notes.txt", b"duplicate\n")
    _git(repository, "add", "notes.txt")
    _git(repository, "commit", "-m", _owner_message(_material_digest(plan)))

    result = _reconciler().execute(_request(repository, specification, plan))

    assert _blocker_code(result) == "slice_owner_ambiguous"


def test_blocks_material_or_specification_drift_before_recording_approval(tmp_path: Path) -> None:
    repository, specification = _repository_with_completed_slice(tmp_path)
    plan = (repository / PLAN_PATH).read_bytes()

    material_result = _reconciler().execute(
        _request(repository, specification, plan.replace(b"## Scope", b"## Changed Scope"))
    )
    specification_result = _reconciler().execute(_request(repository, b"changed specification", plan, run_id="run-2"))

    assert _blocker_code(material_result) == "artifact_reconciliation_failed"
    assert _blocker_code(specification_result) == "artifact_reconciliation_failed"
    assert not (repository / ".cline-sdlc/runs/run-1/approval.json").exists()


def test_rejects_conflicting_second_approval_for_same_run(tmp_path: Path) -> None:
    repository, specification = _repository_with_completed_slice(tmp_path)
    plan = (repository / PLAN_PATH).read_bytes()
    reconciler = _reconciler()
    first = reconciler.execute(_request(repository, specification, plan))
    _write(repository, "later.txt", b"human commit\n")
    _git(repository, "add", "later.txt", ".gitignore")
    _git(repository, "commit", "-m", "Add later human commit")

    second = reconciler.execute(_request(repository, specification, plan))

    assert first.status is PlanReconciliationStatus.AUTHORIZED
    assert _blocker_code(second) == "invocation_approval_not_recorded"


def test_blocks_unrecorded_dirty_paths(tmp_path: Path) -> None:
    repository, specification = _repository_with_completed_slice(tmp_path)
    plan = (repository / PLAN_PATH).read_bytes()
    _write(repository, "unexpected.txt", b"dirty\n")

    result = _reconciler().execute(_request(repository, specification, plan))

    assert _blocker_code(result) == "unexpected_dirty_paths"


def _repository_with_completed_slice(tmp_path: Path) -> tuple[Path, bytes]:
    repository = _initialized_repository(tmp_path)
    specification = b"# Specification\n"
    incomplete_plan = _plan(specification)
    completed_plan = _plan(specification, completed=("slice-1",))
    _write(repository, SPECIFICATION_PATH, specification)
    _write(repository, PLAN_PATH, incomplete_plan)
    _git(repository, "add", SPECIFICATION_PATH, PLAN_PATH)
    _git(repository, "commit", "-m", "Add ready plan")
    _write(repository, PLAN_PATH, completed_plan)
    _git(repository, "add", PLAN_PATH)
    _git(repository, "commit", "-m", _owner_message(_material_digest(completed_plan)))
    return repository, specification


def _request(
    repository: Path,
    specification: bytes,
    plan: bytes,
    *,
    run_id: str = "run-1",
) -> PlanReconciliationRequest:
    return PlanReconciliationRequest(
        repository_root=repository,
        run_id=run_id,
        approved_at=APPROVED_AT,
        plan_path=PLAN_PATH,
        plan_content=plan,
        specification_path=SPECIFICATION_PATH,
        specification_content=specification,
        selection_request=SliceSelectionRequest(
            tasks=(
                PlanTaskDefinition(task_id="task-1", slices=(PlanSliceDefinition(slice_id="slice-1"),)),
                PlanTaskDefinition(
                    task_id="task-2",
                    slices=(PlanSliceDefinition(slice_id="slice-2", dependencies=("slice-1",)),),
                ),
            ),
            completed_slice_ids=("slice-1",),
            completion_evidence=(SliceCompletionEvidence(slice_id="slice-1", completed=True),),
        ),
    )


def _reconciler() -> ReconcilePlan:
    store = FilesystemRunAuditStore()
    return ReconcilePlan(
        StrictPlanArtifactInspector(),
        GitCliPlanHistoryReader(),
        RunAuditInvocationApprovalRecorder(RecordInvocationApproval(store)),
    )


def _plan(specification: bytes, *, completed: tuple[str, ...] = ()) -> bytes:
    specification_digest = compute_specification_digest(specification)
    completed_yaml = "[]" if not completed else "\n" + "\n".join(f"  - {item}" for item in completed)
    template = f"""# Plan

<!-- cline-sdlc-material:start -->
## Objective
Deliver the test plan.

## Scope
Test reconciliation.
<!-- cline-sdlc-material:end -->

<!-- cline-sdlc-progress:start -->
```cline-sdlc-state
schema_version: 1
work_id: test-work
profile: balanced
phase: ready
specification: {SPECIFICATION_PATH}
specification_digest: {specification_digest}
plan_revision: 1
review_iteration: 1
review_readiness: ready
digest_schema_version: 1
material_digest: sha256:{"0" * 64}
current_task: null
current_slice: null
slice_start_commit: null
partial_slice_paths: []
completed_slices: {completed_yaml}
remediation_records: []
validation_evidence: []
blocker: null
created_at: 2026-07-25T10:00:00Z
updated_at: 2026-07-25T10:00:00Z
completed_at: null
```
<!-- cline-sdlc-progress:end -->
""".encode()
    return template.replace(f"sha256:{'0' * 64}".encode(), _material_digest(template).encode())


def _material_digest(plan: bytes) -> str:
    return compute_plan_material_digest(
        PlanMaterialDigestInput(
            plan_markdown=plan,
            plan_revision=1,
            specification=SPECIFICATION_PATH,
            specification_digest=compute_specification_digest(b"# Specification\n"),
        )
    )


def _owner_message(material_digest: str) -> str:
    return f"""feat(sdlc): complete slice-1 test slice

Cline-SDLC-Work-ID: test-work
Cline-SDLC-Slice-ID: slice-1
Cline-SDLC-Slice-Kind: implementation
Cline-SDLC-Material-Digest: {material_digest}
"""


def _initialized_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--initial-branch", "feature/test")
    _git(repository, "config", "user.email", "cline-sdlc@example.test")
    _git(repository, "config", "user.name", "Cline SDLC Tests")
    return repository


def _write(repository: Path, relative_path: str, content: bytes) -> None:
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _blocker_code(result: PlanReconciliationResult) -> str:
    assert result.status is PlanReconciliationStatus.BLOCKED
    assert result.blocker is not None
    return result.blocker.code


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
