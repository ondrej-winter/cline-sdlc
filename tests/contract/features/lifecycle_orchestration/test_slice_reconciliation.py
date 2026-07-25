"""Contract tests for independent implementation-slice reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionBlocker,
    SliceExecutionResult,
    SliceExecutionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    SliceReconciliationRequest,
    SliceReconciliationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SelectedSlice
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.reconcile_slice import ReconcileSlice
from cline_sdlc.features.operation_policy.domain.policy import (
    OperationDecision,
    OperationDecisionStatus,
)
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionBlocker,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
    RepositoryInspectionStatus,
    RepositorySnapshot,
)

HEAD = "a" * 40
SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
PATHS = ("docs/plans/work.md", "src/feature.py", "tests/test_feature.py")


@dataclass
class RecordingInspector:
    result: RepositoryInspectionResult
    requests: list[RepositoryInspectionRequest]

    def inspect(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        self.requests.append(request)
        return self.result


def test_produces_exact_commit_candidate_when_all_evidence_agrees() -> None:
    inspector = RecordingInspector(_inspection(PATHS), [])

    result = ReconcileSlice(inspector).execute(_request())

    assert result.status is SliceReconciliationStatus.COMMIT_CANDIDATE
    assert result.commit_candidate is not None
    assert result.commit_candidate.slice_id == "task-4.3"
    assert result.commit_candidate.paths == PATHS
    assert result.commit_candidate.starting_head == HEAD
    assert result.commit_candidate.material_digest == MATERIAL_DIGEST
    assert len(result.commit_candidate.validation_evidence) == 1
    assert len(inspector.requests) == 1


def test_later_slice_start_may_follow_the_immutable_invocation_starting_head() -> None:
    later_head = "b" * 40
    request = replace(_request(), slice_start_commit=later_head)
    inspector = RecordingInspector(_inspection(PATHS, head=later_head), [])

    result = ReconcileSlice(inspector).execute(request)

    assert result.status is SliceReconciliationStatus.COMMIT_CANDIDATE
    assert result.commit_candidate is not None
    assert result.commit_candidate.starting_head == later_head
    assert request.approval.starting_head == HEAD


def test_out_of_scope_path_is_rejected_even_when_reported_and_observed() -> None:
    paths = (*PATHS, "unrelated.txt")
    result = ReconcileSlice(RecordingInspector(_inspection(paths), [])).execute(_request(execution=_execution(paths)))

    assert result.status is SliceReconciliationStatus.RECOVERY_REQUIRED
    assert result.blocker is not None
    assert result.blocker.code == "slice_path_out_of_scope"


def test_failed_execution_preserves_observed_paths_for_recovery() -> None:
    execution = SliceExecutionResult(
        status=SliceExecutionStatus.BLOCKED,
        changed_paths=("src/feature.py",),
        blocker=SliceExecutionBlocker("session_retry_not_safe", "ambiguous writes prevent retry"),
    )

    result = ReconcileSlice(RecordingInspector(_inspection(("src/feature.py",)), [])).execute(
        _request(execution=execution)
    )

    assert result.status is SliceReconciliationStatus.RECOVERY_REQUIRED
    assert result.recovery is not None
    assert result.recovery.blocker.code == "session_retry_not_safe"


def test_repository_observation_failure_blocks_without_recovery_claim() -> None:
    inspection = RepositoryInspectionResult(
        status=RepositoryInspectionStatus.FAILED,
        blockers=(RepositoryInspectionBlocker("git_status_unavailable", "status failed"),),
    )

    result = ReconcileSlice(RecordingInspector(inspection, [])).execute(_request())

    assert result.status is SliceReconciliationStatus.BLOCKED
    assert result.recovery is None
    assert result.blocker is not None
    assert result.blocker.code == "repository_observation_failed"


def test_unsafe_observed_path_blocks_without_claiming_recoverable_ownership() -> None:
    result = ReconcileSlice(RecordingInspector(_inspection(("../outside.py",)), [])).execute(_request())

    assert result.status is SliceReconciliationStatus.BLOCKED
    assert result.recovery is None
    assert result.blocker is not None
    assert result.blocker.code == "slice_changed_path_invalid"


def test_request_rejects_unsafe_or_incomplete_path_scope() -> None:
    with pytest.raises(ValueError, match="normalized repository-relative"):
        _request(expected_paths=("../outside.py", "docs/plans/work.md"))
    with pytest.raises(ValueError, match="include the progress plan"):
        _request(expected_paths=("src/feature.py",))


def _request(
    *,
    execution: SliceExecutionResult | None = None,
    material_digest: str = MATERIAL_DIGEST,
    expected_paths: tuple[str, ...] = PATHS,
) -> SliceReconciliationRequest:
    approval = InvocationApproval(
        run_id="run-task-4.3",
        profile="balanced",
        starting_head=HEAD,
        approved_at=datetime(2026, 7, 25, 19, 0, tzinfo=UTC),
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )
    return SliceReconciliationRequest(
        work_id="cline-sdlc-orchestrator",
        approval=approval,
        selection=SelectedSlice(task_id="task-4", slice_id="task-4.3", resuming_partial=False),
        slice_start_commit=HEAD,
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=material_digest,
        plan_path="docs/plans/work.md",
        expected_paths=expected_paths,
        execution=execution or _execution(PATHS),
        repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
    )


def _execution(
    paths: tuple[str, ...],
    *,
    validation: tuple[ValidationEvidence, ...] | None = None,
    decisions: tuple[OperationDecision, ...] = (),
) -> SliceExecutionResult:
    terminal = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(
            SessionOutcome(
                session_role=SessionRole.IMPLEMENTATION,
                status=SessionStatus.COMPLETED,
                reason="slice_verified",
                changed_paths=paths,
            ),
        ),
    )
    attempt = SessionAttemptResult(
        status=SessionAttemptStatus.COMPLETED,
        attempts=(),
        terminal_session_result=terminal,
        changed_paths=paths,
    )
    return SliceExecutionResult(
        status=SliceExecutionStatus.COMPLETED,
        session_attempts=(attempt,),
        operation_decisions=decisions,
        validation_evidence=(_passing_validation(),) if validation is None else validation,
        changed_paths=paths,
    )


def _inspection(paths: tuple[str, ...], *, head: str = HEAD) -> RepositoryInspectionResult:
    return RepositoryInspectionResult(
        status=RepositoryInspectionStatus.READY,
        snapshot=RepositorySnapshot(
            repository_root="/repo",
            head_commit=head,
            branch="feature/task-4.3",
            dirty_paths=paths,
        ),
    )


def _passing_validation() -> ValidationEvidence:
    return ValidationEvidence(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand("uv", ("run", "pytest", "tests/test_feature.py")),
        status=ValidationEvidenceStatus.PASSED,
        summary="focused validation passed",
        exit_code=0,
        recorded_at=datetime(2026, 7, 25, 19, 5, tzinfo=UTC),
    )


def _failed_validation() -> ValidationEvidence:
    return replace(
        _passing_validation(),
        status=ValidationEvidenceStatus.FAILED,
        summary="focused validation failed",
        exit_code=1,
    )


def _denied_operation() -> OperationDecision:
    return OperationDecision(
        status=OperationDecisionStatus.APPROVAL_REQUIRED,
        rule_id="deny_unclassifiable",
        summary="operation is not classifiable",
        proposed_operation="unknown-tool",
    )


@pytest.mark.parametrize(
    ("reconciliation_request", "inspection", "code"),
    [
        (_request(execution=_execution(("src/feature.py",))), _inspection(PATHS), "slice_changed_paths_mismatch"),
        (_request(), _inspection((*PATHS, "unrelated.txt")), "slice_changed_paths_mismatch"),
        (_request(), _inspection(PATHS, head="b" * 40), "slice_head_moved"),
        (
            _request(execution=_execution(PATHS, validation=())),
            _inspection(PATHS),
            "focused_validation_not_verified",
        ),
        (
            _request(execution=_execution(PATHS, validation=(_failed_validation(),))),
            _inspection(PATHS),
            "focused_validation_not_verified",
        ),
        (
            _request(execution=_execution(PATHS, decisions=(_denied_operation(),))),
            _inspection(PATHS),
            "prohibited_slice_operation",
        ),
        (
            _request(material_digest=f"sha256:{'3' * 64}"),
            _inspection(PATHS),
            "material_digest_diverged",
        ),
    ],
)
def test_failures_with_observed_writes_return_attributable_recovery(
    reconciliation_request: SliceReconciliationRequest,
    inspection: RepositoryInspectionResult,
    code: str,
) -> None:
    result = ReconcileSlice(RecordingInspector(inspection, [])).execute(reconciliation_request)

    assert result.status is SliceReconciliationStatus.RECOVERY_REQUIRED
    assert result.commit_candidate is None
    assert result.recovery is not None
    assert inspection.snapshot is not None
    assert result.recovery.paths == tuple(sorted(inspection.snapshot.dirty_paths))
    assert result.recovery.blocker.code == code
