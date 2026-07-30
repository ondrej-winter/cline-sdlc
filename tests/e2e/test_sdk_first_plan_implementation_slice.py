"""End-to-end application proof for one SDK-first implementation slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionDiagnosticReference,
    ClineSessionEvidence,
    ClineSessionEvidenceType,
    ClineSessionProcessStatus,
    ClineSessionResult,
    ClineSessionTerminalStatus,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_implementation import (
    PlanImplementationRequest,
    PlanImplementationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionRequest,
    SliceExecutionResult,
    SlicePlanActMediation,
    SlicePlanActStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    SliceCommitCandidate,
    SliceReconciliationRequest,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    SelectedSlice,
    SliceSelectionResult,
    SliceSelectionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationExecutionRequest,
    ValidationExecutionResult,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.execute_slice import ExecuteSlice
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.implement_plan import ImplementPlan
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.reconcile_slice import ReconcileSlice
from cline_sdlc.features.operation_policy.application.use_cases.classify_operation import ClassifyOperation
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
    RepositoryInspectionStatus,
    RepositorySnapshot,
)
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
    SliceCommitRequest,
    SliceCommitResult,
    SliceCommitStatus,
)

SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
STARTING_HEAD = "a" * 40
SLICE_COMMIT = "b" * 40
PLAN_PATH = "docs/plans/sdk-first.md"
SOURCE_PATH = "src/cline_sdlc/features/example/application/use_cases/do_work.py"
TEST_PATH = "tests/unit/features/example/application/test_do_work.py"
PATHS = (PLAN_PATH, SOURCE_PATH, TEST_PATH)


@dataclass
class RecordingSdkSessionAttempts:
    requests: list[SessionAttemptRequest] = field(default_factory=list)

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        result = ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=0,
            terminal_outcomes=(
                SessionOutcome(
                    session_role=SessionRole.IMPLEMENTATION,
                    status=SessionStatus.COMPLETED,
                    reason="slice_verified",
                    changed_paths=PATHS,
                ),
            ),
            events=(
                ClineSessionEvidence(
                    evidence_type=ClineSessionEvidenceType.DIAGNOSTIC,
                    summary="SDK event stream normalized by the adapter",
                    sdk_event_type="assistant-text-delta",
                ),
            ),
            sdk_terminal_status=ClineSessionTerminalStatus.COMPLETED,
            diagnostic_references=(
                ClineSessionDiagnosticReference(
                    kind="run_id",
                    value="sdk-run-task-13",
                    summary="safe SDK run reference",
                ),
            ),
        )
        return SessionAttemptResult(
            status=SessionAttemptStatus.COMPLETED,
            attempts=(),
            terminal_session_result=result,
            changed_paths=PATHS,
        )


@dataclass
class PassingFocusedValidation:
    requests: list[ValidationExecutionRequest] = field(default_factory=list)

    def execute(self, request: ValidationExecutionRequest) -> ValidationExecutionResult:
        self.requests.append(request)
        return ValidationExecutionResult(evidence=(_passing_validation(),))


@dataclass
class RecordingRepositoryInspector:
    requests: list[RepositoryInspectionRequest] = field(default_factory=list)

    def inspect(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        self.requests.append(request)
        return RepositoryInspectionResult(
            status=RepositoryInspectionStatus.READY,
            snapshot=RepositorySnapshot(
                repository_root=str(request.working_directory),
                head_commit=STARTING_HEAD,
                branch="feature/task-13",
                dirty_paths=PATHS,
            ),
        )


@dataclass
class RecordingCommit:
    requests: list[SliceCommitRequest] = field(default_factory=list)

    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        self.requests.append(request)
        return SliceCommitResult(status=SliceCommitStatus.COMMITTED, commit=SLICE_COMMIT)


@dataclass
class OneSliceProgress:
    plan_act_status: SlicePlanActStatus
    execution_requests: list[SliceExecutionRequest] = field(default_factory=list)
    reconciliation_requests: list[SliceReconciliationRequest] = field(default_factory=list)

    def prepare_execution(self, approval: InvocationApproval, selection: SelectedSlice) -> SliceExecutionRequest:
        request = SliceExecutionRequest(
            approval=approval,
            selection=selection,
            specification_path="docs/specs/sdk-first.md",
            specification_content="# Accepted specification\nImplement one safe SDK-first proof slice.",
            specification_digest=SPECIFICATION_DIGEST,
            plan_path=PLAN_PATH,
            plan_content="# Ready implementation plan\nTask 13 is the current slice.",
            material_digest=MATERIAL_DIGEST,
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
            cline_command="cline",
            timeout_seconds=1800,
            focused_validation_commands=(_focused_validation(),),
            expected_paths=PATHS,
            plan_act_mediation=_plan_act(self.plan_act_status),
        )
        self.execution_requests.append(request)
        return request

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        request = SliceReconciliationRequest(
            work_id="sdk-first-task-13",
            approval=approval,
            selection=selection,
            slice_start_commit=STARTING_HEAD,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
            plan_path=PLAN_PATH,
            expected_paths=PATHS,
            execution=execution,
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
        )
        self.reconciliation_requests.append(request)
        return request

    def prepare_commit(self, _approval: InvocationApproval, candidate: SliceCommitCandidate) -> SliceCommitRequest:
        return SliceCommitRequest(
            repository_root=Path("/repo"),
            plan_path=PLAN_PATH,
            current_plan_content=b"current task 13 progress",
            updated_plan_content=b"completed task 13 progress",
            candidate=candidate,
            short_description="prove sdk first slice path",
        )

    def select_after_commit(self, _approval: InvocationApproval, _commit: str) -> SliceSelectionResult:
        return SliceSelectionResult(status=SliceSelectionStatus.COMPLETE, completed_slice_ids=("task-13.1",))


def test_one_accepted_slice_completes_only_after_sdk_execution_reconciliation_validation_and_commit() -> None:
    sessions = RecordingSdkSessionAttempts()
    validation = PassingFocusedValidation()
    inspector = RecordingRepositoryInspector()
    commit = RecordingCommit()
    progress = OneSliceProgress(SlicePlanActStatus.READY_TO_ACT)

    result = _use_case(progress, sessions, validation, inspector, commit).execute(
        PlanImplementationRequest(approval=_approval(), initial_selection=_selection())
    )

    assert result.status is PlanImplementationStatus.COMPLETED
    assert result.completed_slice_ids == ("task-13.1",)
    assert result.commits == (SLICE_COMMIT,)
    assert len(sessions.requests) == 1
    assert len(validation.requests) == 1
    assert len(inspector.requests) == 1
    assert len(commit.requests) == 1
    assert progress.reconciliation_requests[0].execution.validation_evidence == (_passing_validation(),)
    assert commit.requests[0].candidate.paths == PATHS
    assert commit.requests[0].candidate.validation_evidence == (_passing_validation(),)


def test_unproven_same_session_plan_to_act_evidence_blocks_before_session_reconciliation_or_commit() -> None:
    sessions = RecordingSdkSessionAttempts()
    validation = PassingFocusedValidation()
    inspector = RecordingRepositoryInspector()
    commit = RecordingCommit()
    progress = OneSliceProgress(SlicePlanActStatus.UNPROVEN)

    result = _use_case(progress, sessions, validation, inspector, commit).execute(
        PlanImplementationRequest(approval=_approval(), initial_selection=_selection())
    )

    assert result.status is PlanImplementationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "slice_plan_act_support_unproven"
    assert sessions.requests == []
    assert validation.requests == []
    assert inspector.requests == []
    assert commit.requests == []


def _use_case(
    progress: OneSliceProgress,
    sessions: RecordingSdkSessionAttempts,
    validation: PassingFocusedValidation,
    inspector: RecordingRepositoryInspector,
    commit: RecordingCommit,
) -> ImplementPlan:
    return ImplementPlan(
        progress=progress,
        slice_execution=ExecuteSlice(
            session_attempts=sessions,
            operation_classifier=ClassifyOperation(),
            validation_execution=validation,
        ),
        slice_reconciliation=ReconcileSlice(inspector),
        slice_commit=commit,
    )


def _approval() -> InvocationApproval:
    return InvocationApproval(
        run_id="run-task-13",
        profile="balanced",
        starting_head=STARTING_HEAD,
        approved_at=datetime(2026, 7, 30, 7, 30, tzinfo=UTC),
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )


def _selection() -> SelectedSlice:
    return SelectedSlice(task_id="task-13", slice_id="task-13.1", resuming_partial=False)


def _plan_act(status: SlicePlanActStatus) -> SlicePlanActMediation:
    return SlicePlanActMediation(
        status=status,
        summary="same-session Plan-to-Act sequencing evidence is ready."
        if status is SlicePlanActStatus.READY_TO_ACT
        else "same-session Plan-to-Act sequencing is unproven.",
        run_id="run-task-13",
        task_id="task-13",
        slice_id="task-13.1",
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        operation_policy="balanced",
        diagnostic_reference="sdk-capability-matrix:plan-act",
    )


def _focused_validation() -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand(executable="uv", arguments=("run", "pytest", "tests/unit/features/example")),
        source=ValidationCommandSource.EXPLICIT,
        reason="accepted SDK-first slice focused verification",
    )


def _passing_validation() -> ValidationEvidence:
    return ValidationEvidence(
        scope=ValidationScope.FOCUSED,
        command=_focused_validation().command,
        status=ValidationEvidenceStatus.PASSED,
        summary="focused validation passed",
        exit_code=0,
        recorded_at=datetime(2026, 7, 30, 7, 35, tzinfo=UTC),
    )
