"""Contract tests for one bounded implementation-slice session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptBlocker,
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionRequest,
    SliceExecutionStatus,
    SlicePlanActMediation,
    SlicePlanActStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SelectedSlice
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationDiscoveryBlocker,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationExecutionRequest,
    ValidationExecutionResult,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.execute_slice import ExecuteSlice
from cline_sdlc.features.operation_policy.application.dtos.operation import (
    ClassifyOperationRequest,
    PlannedOperationAuthorization,
    PlannedOperationKind,
)
from cline_sdlc.features.operation_policy.application.use_cases.classify_operation import ClassifyOperation
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest

SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
HEAD = "a" * 40
EXPECTED_SESSION_AND_VALIDATION_RUNS = 2
DEFAULT_PLAN_ACT = object()


@dataclass
class RecordingSessions:
    results: list[SessionAttemptResult]
    requests: list[SessionAttemptRequest]

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        return self.results.pop(0)


@dataclass
class RecordingValidation:
    results: list[ValidationExecutionResult]
    requests: list[ValidationExecutionRequest]

    def execute(self, request: ValidationExecutionRequest) -> ValidationExecutionResult:
        self.requests.append(request)
        return self.results.pop(0)


def test_executes_only_approved_slice_and_independent_focused_validation() -> None:
    sessions = RecordingSessions([_completed_session(("src/feature.py", "tests/test_feature.py"))], [])
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(_request())

    assert result.completed
    assert result.changed_paths == ("src/feature.py", "tests/test_feature.py")
    assert result.repair_attempts == 0
    assert len(sessions.requests) == 1
    prompt = sessions.requests[0].session_request.command[-1]
    assert "Current slice: task-4.2" in prompt
    assert "Do not work on later slices" in prompt
    assert "create commits" in prompt
    assert SPECIFICATION_DIGEST in prompt
    assert MATERIAL_DIGEST in prompt
    assert len(validation.requests) == 1
    assert all(candidate.scope is ValidationScope.FOCUSED for candidate in validation.requests[0].commands)


def test_exact_planned_dependency_operation_is_recorded_as_allowed() -> None:
    operation = ClassifyOperationRequest(
        executable="uv",
        arguments=("lock",),
        authorization=PlannedOperationAuthorization(
            kind=PlannedOperationKind.DEPENDENCY,
            material_requirement="Task 4.2 requires the accepted dependency lock update.",
            executable="uv",
            arguments=("lock",),
            owned_paths=("pyproject.toml", "uv.lock"),
        ),
    )

    result = _execute().execute(_request(operations=(operation,)))

    assert result.completed
    assert result.operation_decisions[0].is_allowed
    assert result.operation_decisions[0].accepted_material_requirement is not None


def test_unclassifiable_operation_blocks_before_session() -> None:
    sessions = RecordingSessions([_completed_session()], [])
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(
        _request(operations=(ClassifyOperationRequest(executable="unknown-tool"),))
    )

    assert result.status is SliceExecutionStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "slice_operation_not_authorized"
    assert sessions.requests == []
    assert validation.requests == []


def test_missing_same_session_plan_to_act_evidence_blocks_implementation_before_session() -> None:
    sessions = RecordingSessions([_completed_session()], [])
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(_request(plan_act_mediation=None))

    assert result.status is SliceExecutionStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "slice_plan_act_support_unproven"
    assert sessions.requests == []
    assert validation.requests == []


def test_plan_act_needs_user_input_stops_without_acting_or_validation() -> None:
    sessions = RecordingSessions([_completed_session()], [])
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(
        _request(
            plan_act_mediation=_plan_act_mediation(
                SlicePlanActStatus.NEEDS_USER_INPUT,
                summary="Cline needs the user to choose between two accepted alternatives.",
                diagnostic_reference="session:plan-question-1",
            )
        )
    )

    assert result.status is SliceExecutionStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "slice_plan_act_needs_user_input"
    assert result.blocker.evidence == "session:plan-question-1"
    assert sessions.requests == []
    assert validation.requests == []


def test_unproven_plan_act_support_records_blocker_instead_of_emulating_readiness() -> None:
    sessions = RecordingSessions([_completed_session()], [])
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(
        _request(
            plan_act_mediation=_plan_act_mediation(
                SlicePlanActStatus.UNPROVEN,
                summary="same-session Plan-to-Act sequencing is not proven for this slice envelope.",
            )
        )
    )

    assert result.status is SliceExecutionStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "slice_plan_act_support_unproven"
    assert "not proven" in result.blocker.summary
    assert sessions.requests == []
    assert validation.requests == []


def test_ready_to_act_must_match_same_session_slice_digests_and_policy() -> None:
    sessions = RecordingSessions([_completed_session()], [])
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(
        _request(plan_act_mediation=_plan_act_mediation(SlicePlanActStatus.READY_TO_ACT, slice_id="other-slice"))
    )

    assert result.status is SliceExecutionStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "slice_plan_act_scope_mismatch"
    assert result.blocker.evidence == "slice_id"
    assert sessions.requests == []
    assert validation.requests == []


def test_focused_validation_failure_permits_one_fresh_repair() -> None:
    sessions = RecordingSessions([_completed_session(("src/feature.py",)), _completed_session(("src/feature.py",))], [])
    validation = RecordingValidation([_failed_validation(), _passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(_request())

    assert result.completed
    assert result.repair_attempts == 1
    assert len(sessions.requests) == EXPECTED_SESSION_AND_VALIDATION_RUNS
    assert "Repair only the current slice" in sessions.requests[1].session_request.command[-1]
    assert len(validation.requests) == EXPECTED_SESSION_AND_VALIDATION_RUNS


def test_second_focused_validation_failure_exhausts_repair() -> None:
    sessions = RecordingSessions([_completed_session(), _completed_session()], [])
    validation = RecordingValidation([_failed_validation(), _failed_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(_request())

    assert result.status is SliceExecutionStatus.FAILED
    assert result.blocker is not None
    assert result.blocker.code == "focused_validation_repair_exhausted"
    assert result.repair_attempts == 1
    assert len(sessions.requests) == EXPECTED_SESSION_AND_VALIDATION_RUNS


def test_failed_session_preserves_attributable_changed_paths_without_validation() -> None:
    sessions = RecordingSessions(
        [
            SessionAttemptResult(
                status=SessionAttemptStatus.BLOCKED,
                attempts=(),
                changed_paths=("src/partial.py",),
                blocker=SessionAttemptBlocker(code="session_retry_not_safe", summary="ambiguous writes prevent retry"),
            )
        ],
        [],
    )
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(_request())

    assert result.status is SliceExecutionStatus.BLOCKED
    assert result.changed_paths == ("src/partial.py",)
    assert validation.requests == []


def test_approval_digest_divergence_starts_no_session() -> None:
    sessions = RecordingSessions([_completed_session()], [])
    validation = RecordingValidation([_passing_validation()], [])

    result = _execute(sessions=sessions, validation=validation).execute(_request(material_digest=f"sha256:{'3' * 64}"))

    assert result.status is SliceExecutionStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "material_digest_diverged"
    assert sessions.requests == []
    assert validation.requests == []


def test_request_rejects_broad_validation_and_unsafe_expected_paths() -> None:
    broad = ValidationCommandCandidate(
        scope=ValidationScope.BROAD,
        command=ValidationCommand(executable="uv", arguments=("run", "pytest")),
        source=ValidationCommandSource.EXPLICIT,
        reason="broad command is outside the slice contract",
    )

    with pytest.raises(ValueError, match="focused validation commands only"):
        _request(focused_validation_commands=(broad,))
    with pytest.raises(ValueError, match="normalized repository-relative paths"):
        _request(expected_paths=("../outside.py",))


def _execute(
    *,
    sessions: RecordingSessions | None = None,
    validation: RecordingValidation | None = None,
) -> ExecuteSlice:
    return ExecuteSlice(
        session_attempts=sessions or RecordingSessions([_completed_session()], []),
        operation_classifier=ClassifyOperation(),
        validation_execution=validation or RecordingValidation([_passing_validation()], []),
    )


def _plan_act_mediation(
    status: SlicePlanActStatus,
    *,
    summary: str = "Cline is ready to act within the accepted slice boundary.",
    slice_id: str = "task-4.2",
    diagnostic_reference: str | None = None,
) -> SlicePlanActMediation:
    return SlicePlanActMediation(
        status=status,
        summary=summary,
        run_id="run-task-4.2",
        task_id="task-4",
        slice_id=slice_id,
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        operation_policy="balanced",
        diagnostic_reference=diagnostic_reference,
    )


def _request(
    *,
    operations: tuple[ClassifyOperationRequest, ...] = (),
    material_digest: str = MATERIAL_DIGEST,
    focused_validation_commands: tuple[ValidationCommandCandidate, ...] | None = None,
    expected_paths: tuple[str, ...] = ("src/feature.py", "tests/test_feature.py", "docs/plans/work.md"),
    plan_act_mediation: SlicePlanActMediation | None | object = DEFAULT_PLAN_ACT,
) -> SliceExecutionRequest:
    if plan_act_mediation is DEFAULT_PLAN_ACT:
        plan_act_mediation = _plan_act_mediation(SlicePlanActStatus.READY_TO_ACT)
    typed_plan_act_mediation = cast("SlicePlanActMediation | None", plan_act_mediation)
    return SliceExecutionRequest(
        approval=InvocationApproval(
            run_id="run-task-4.2",
            profile="balanced",
            starting_head=HEAD,
            approved_at=datetime(2026, 7, 25, 18, 0, tzinfo=UTC),
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
            remediation_envelope_applicable=True,
        ),
        selection=SelectedSlice(task_id="task-4", slice_id="task-4.2", resuming_partial=False),
        specification_path="docs/specs/work.md",
        specification_content="# Accepted specification\nOnly accepted behavior.",
        specification_digest=SPECIFICATION_DIGEST,
        plan_path="docs/plans/work.md",
        plan_content="# Ready plan\nTask 4.2 is the current slice; Task 4.3 is later.",
        material_digest=material_digest,
        repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
        cline_command="cline",
        timeout_seconds=1800,
        focused_validation_commands=focused_validation_commands or (_focused_candidate(),),
        expected_paths=expected_paths,
        operations=operations,
        plan_act_mediation=typed_plan_act_mediation,
    )


def _completed_session(changed_paths: tuple[str, ...] = ()) -> SessionAttemptResult:
    terminal = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(
            SessionOutcome(
                session_role=SessionRole.IMPLEMENTATION,
                status=SessionStatus.COMPLETED,
                reason="slice_verified",
                changed_paths=changed_paths,
            ),
        ),
    )
    return SessionAttemptResult(
        status=SessionAttemptStatus.COMPLETED,
        attempts=(),
        terminal_session_result=terminal,
        changed_paths=changed_paths,
    )


def _focused_candidate() -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand(executable="uv", arguments=("run", "pytest", "tests/test_feature.py")),
        source=ValidationCommandSource.EXPLICIT,
        reason="accepted slice focused verification",
    )


def _passing_validation() -> ValidationExecutionResult:
    return ValidationExecutionResult(
        evidence=(
            ValidationEvidence(
                scope=ValidationScope.FOCUSED,
                command=_focused_candidate().command,
                status=ValidationEvidenceStatus.PASSED,
                summary="focused validation passed",
                exit_code=0,
                recorded_at=datetime(2026, 7, 25, 18, 5, tzinfo=UTC),
            ),
        )
    )


def _failed_validation() -> ValidationExecutionResult:
    return ValidationExecutionResult(
        evidence=(
            ValidationEvidence(
                scope=ValidationScope.FOCUSED,
                command=_focused_candidate().command,
                status=ValidationEvidenceStatus.FAILED,
                summary="focused validation failed",
                exit_code=1,
                recorded_at=datetime(2026, 7, 25, 18, 5, tzinfo=UTC),
            ),
        ),
        blockers=(
            ValidationDiscoveryBlocker(
                code="validation_command_failed",
                summary="focused validation failed",
                evidence=_focused_candidate().command.display,
            ),
        ),
    )
