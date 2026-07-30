"""CLI composition adapter for supervised implementation-plan execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import parse_plan_state_from_markdown
from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk import (
    ClineSdkSessionRunner,
)
from cline_sdlc.features.lifecycle_orchestration.adapters.outbound.validation_runner import (
    SubprocessValidationCommandRunner,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_implementation import (
    PlanImplementationBlocker,
    PlanImplementationRequest,
    PlanImplementationResult,
    PlanImplementationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionRequest,
    SlicePlanActMediation,
    SlicePlanActStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    SliceReconciliationRequest,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PartialSliceProgress,
    PlanSliceDefinition,
    PlanTaskDefinition,
    SelectedSlice,
    SliceCompletionEvidence,
    SliceSelectionRequest,
    SliceSelectionResult,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationDiscoveryRequest,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.discover_validation import (
    DiscoverValidationCommands,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.execute_slice import ExecuteSlice
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.implement_plan import ImplementPlan
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.reconcile_slice import ReconcileSlice
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_session_attempts import RunSessionAttempts
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_validation import RunValidationCommands
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_slice import SelectSlice
from cline_sdlc.features.operation_policy.application.use_cases.classify_operation import ClassifyOperation
from cline_sdlc.features.repository_coordination.adapters.outbound.audit_approval import (
    RunAuditInvocationApprovalRecorder,
)
from cline_sdlc.features.repository_coordination.adapters.outbound.git_cli import GitCliRepositoryInspector
from cline_sdlc.features.repository_coordination.adapters.outbound.git_history import GitCliPlanHistoryReader
from cline_sdlc.features.repository_coordination.adapters.outbound.git_slice_commit import GitCliSliceCommitter
from cline_sdlc.features.repository_coordination.adapters.outbound.plan_artifact import StrictPlanArtifactInspector
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import (
    InvocationApproval,
    PlanReconciliationRequest,
    PlanReconciliationResult,
    PlanReconciliationStatus,
)
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import SliceCommitRequest
from cline_sdlc.features.repository_coordination.application.use_cases.commit_slice import CommitSlice
from cline_sdlc.features.repository_coordination.application.use_cases.reconcile_plan import ReconcilePlan
from cline_sdlc.features.run_audit.adapters.outbound.filesystem_store import FilesystemRunAuditStore
from cline_sdlc.features.run_audit.application.use_cases.record_invocation_approval import RecordInvocationApproval

if TYPE_CHECKING:
    from pathlib import Path

    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import SliceExecutionResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import SliceCommitCandidate

DEFAULT_FOCUSED_VALIDATION = ValidationCommandCandidate(
    scope=ValidationScope.FOCUSED,
    command=ValidationCommand(executable="uv", arguments=("run", "pytest")),
    source=ValidationCommandSource.DEFAULT,
    reason="default focused validation when selected task paths do not map to a narrower pytest target",
)


@dataclass(frozen=True)
class PlanImplementationRuntimeRequest:
    """Inputs required to compose and run the implementation-plan runtime."""

    invocation: InvocationRequest
    repository_root: Path
    plan_path: Path
    plan_content: str
    plan_state: PlanState
    tasks: tuple[PlanTaskDefinition, ...]


def run_plan_implementation_runtime(request: PlanImplementationRuntimeRequest) -> PlanImplementationResult:
    """Authorize and execute the selected implementation slice through production adapters."""
    relative_plan_path = _repository_relative_path(request.plan_path, repository_root=request.repository_root)
    selection_request = _selection_request(request.plan_state, request.tasks)
    specification_path = (request.repository_root / request.plan_state.specification).resolve(strict=True)

    artifact_inspector = StrictPlanArtifactInspector()
    repository_inspector = GitCliRepositoryInspector()
    reconciliation = ReconcilePlan(
        artifact_inspector=artifact_inspector,
        history_reader=GitCliPlanHistoryReader(),
        approval_recorder=RunAuditInvocationApprovalRecorder(
            RecordInvocationApproval(FilesystemRunAuditStore()),
        ),
    ).execute(
        PlanReconciliationRequest(
            repository_root=request.repository_root,
            run_id=_run_id(request.plan_state.work_id),
            approved_at=datetime.now(UTC),
            plan_path=relative_plan_path,
            plan_content=request.plan_content.encode(),
            specification_path=request.plan_state.specification,
            specification_content=specification_path.read_bytes(),
            selection_request=selection_request,
        )
    )
    if reconciliation.status is PlanReconciliationStatus.COMPLETE and reconciliation.approval is not None:
        return PlanImplementationResult(status=PlanImplementationStatus.COMPLETED, approval=reconciliation.approval)
    if reconciliation.status is not PlanReconciliationStatus.AUTHORIZED:
        return _blocked_from_reconciliation(request, reconciliation)
    if reconciliation.approval is None or reconciliation.selection is None:
        return _blocked_without_approval(
            request,
            "plan_reconciliation_incomplete",
            "plan reconciliation omitted approval",
        )

    progress = _FilesystemPlanProgress(
        repository_root=request.repository_root,
        plan_path=relative_plan_path,
        specification_path=request.plan_state.specification,
        tasks=request.tasks,
        cline_command=request.invocation.cline_command,
        timeout_seconds=request.invocation.timeout_seconds,
    )
    implementation = ImplementPlan(
        progress=progress,
        slice_execution=ExecuteSlice(
            session_attempts=RunSessionAttempts(
                runner=ClineSdkSessionRunner(),
                repository_inspector=repository_inspector,
            ),
            operation_classifier=ClassifyOperation(),
            validation_execution=RunValidationCommands(
                classifier=ClassifyOperation(),
                runner=SubprocessValidationCommandRunner(),
            ),
        ),
        slice_reconciliation=ReconcileSlice(repository_inspector),
        slice_commit=CommitSlice(artifact_inspector, GitCliSliceCommitter()),
    )
    return implementation.execute(
        PlanImplementationRequest(approval=reconciliation.approval, initial_selection=reconciliation.selection)
    )


@dataclass
class _FilesystemPlanProgress:
    """Refresh plan, specification, and Git observations around each slice transaction."""

    repository_root: Path
    plan_path: str
    specification_path: str
    tasks: tuple[PlanTaskDefinition, ...]
    cline_command: str
    timeout_seconds: float
    _pre_execution_plan_content: dict[str, bytes] | None = None

    def __post_init__(self) -> None:
        self._pre_execution_plan_content = {}

    def prepare_execution(self, approval: InvocationApproval, selection: SelectedSlice) -> SliceExecutionRequest:
        plan_content = self._read_plan_bytes()
        if self._pre_execution_plan_content is None:
            self._pre_execution_plan_content = {}
        self._pre_execution_plan_content[selection.slice_id] = plan_content
        expected_paths = self._expected_paths(selection)
        validation = DiscoverValidationCommands().execute(
            ValidationDiscoveryRequest(
                changed_paths=expected_paths,
                include_broad_commands=False,
                include_build_command=False,
            )
        )
        return SliceExecutionRequest(
            approval=approval,
            selection=selection,
            specification_path=self.specification_path,
            specification_content=self._read_specification_text(),
            specification_digest=approval.specification_digest,
            plan_path=self.plan_path,
            plan_content=plan_content.decode("utf-8", errors="strict"),
            material_digest=approval.material_digest,
            repository_request=RepositoryInspectionRequest(working_directory=self.repository_root),
            cline_command=self.cline_command,
            timeout_seconds=self.timeout_seconds,
            focused_validation_commands=tuple(
                candidate for candidate in validation.commands if candidate.scope is ValidationScope.FOCUSED
            )
            or (DEFAULT_FOCUSED_VALIDATION,),
            expected_paths=expected_paths,
            plan_act_mediation=SlicePlanActMediation(
                status=SlicePlanActStatus.READY_TO_ACT,
                summary=(
                    "same-session Plan-to-Act mode switching is proven for the SDK-first reset MVP; "
                    "the orchestrator authorizes this bounded Act turn."
                ),
                run_id=approval.run_id,
                task_id=selection.task_id,
                slice_id=selection.slice_id,
                specification_digest=approval.specification_digest,
                material_digest=approval.material_digest,
                operation_policy=approval.profile,
                diagnostic_reference="docs/sdk-capability-matrix.md#gate-conclusion",
            ),
        )

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        return SliceReconciliationRequest(
            work_id=self._read_plan_state().work_id,
            approval=approval,
            selection=selection,
            slice_start_commit=approval.starting_head,
            specification_digest=approval.specification_digest,
            material_digest=approval.material_digest,
            plan_path=self.plan_path,
            expected_paths=self._expected_paths(selection),
            execution=execution,
            repository_request=RepositoryInspectionRequest(working_directory=self.repository_root),
        )

    def prepare_commit(self, approval: InvocationApproval, candidate: SliceCommitCandidate) -> SliceCommitRequest:
        _ = approval
        if self._pre_execution_plan_content is None or candidate.slice_id not in self._pre_execution_plan_content:
            message = "pre-execution plan content is unavailable for selected slice"
            raise ValueError(message)
        return SliceCommitRequest(
            repository_root=self.repository_root,
            plan_path=self.plan_path,
            current_plan_content=self._pre_execution_plan_content[candidate.slice_id],
            updated_plan_content=self._read_plan_bytes(),
            candidate=candidate,
            short_description=candidate.slice_id,
        )

    def select_after_commit(self, approval: InvocationApproval, commit: str) -> SliceSelectionResult:
        _ = approval, commit
        state = self._read_plan_state()
        return SelectSlice().execute(_selection_request(state, self.tasks))

    def _expected_paths(self, selection: SelectedSlice) -> tuple[str, ...]:
        if selection.resuming_partial:
            state = self._read_plan_state()
            if state.partial_slice_paths:
                return tuple(dict.fromkeys((self.plan_path, *state.partial_slice_paths)))
        selected_definition = _slice_definition(self.tasks, selection)
        if selected_definition.expected_paths:
            return tuple(dict.fromkeys((self.plan_path, *selected_definition.expected_paths)))
        return (self.plan_path,)

    def _read_plan_bytes(self) -> bytes:
        return (self.repository_root / self.plan_path).read_bytes()

    def _read_specification_text(self) -> str:
        return (self.repository_root / self.specification_path).read_text(encoding="utf-8", errors="strict")

    def _read_plan_state(self) -> PlanState:
        return parse_plan_state_from_markdown(self._read_plan_bytes().decode("utf-8", errors="strict"))


def _selection_request(plan_state: PlanState, tasks: tuple[PlanTaskDefinition, ...]) -> SliceSelectionRequest:
    return SliceSelectionRequest(
        tasks=tasks,
        completed_slice_ids=plan_state.completed_slices,
        completion_evidence=tuple(
            SliceCompletionEvidence(slice_id=slice_id, completed=True) for slice_id in plan_state.completed_slices
        ),
        partial_slice=PartialSliceProgress(
            task_id=plan_state.current_task,
            slice_id=plan_state.current_slice,
            paths=plan_state.partial_slice_paths,
        )
        if plan_state.current_task is not None and plan_state.current_slice is not None
        else None,
    )


def _slice_definition(tasks: tuple[PlanTaskDefinition, ...], selection: SelectedSlice) -> PlanSliceDefinition:
    for task in tasks:
        if task.task_id != selection.task_id:
            continue
        for slice_definition in task.slices:
            if slice_definition.slice_id == selection.slice_id:
                return slice_definition
    message = "selected slice is not present in parsed plan task definitions"
    raise ValueError(message)


def _blocked_from_reconciliation(
    request: PlanImplementationRuntimeRequest,
    result: PlanReconciliationResult,
) -> PlanImplementationResult:
    approval = result.approval or _fallback_approval(request)
    blocker = result.blocker
    return PlanImplementationResult(
        status=PlanImplementationStatus.BLOCKED,
        approval=approval,
        blocker=PlanImplementationBlocker(
            code=blocker.code if blocker is not None else "plan_reconciliation_blocked",
            summary=blocker.summary if blocker is not None else "plan reconciliation did not authorize implementation",
            evidence=blocker.evidence if blocker is not None else None,
        ),
    )


def _blocked_without_approval(
    request: PlanImplementationRuntimeRequest,
    code: str,
    summary: str,
) -> PlanImplementationResult:
    return PlanImplementationResult(
        status=PlanImplementationStatus.BLOCKED,
        approval=_fallback_approval(request),
        blocker=PlanImplementationBlocker(code=code, summary=summary),
    )


def _fallback_approval(request: PlanImplementationRuntimeRequest) -> InvocationApproval:
    return InvocationApproval(
        run_id=_run_id(request.plan_state.work_id),
        profile="balanced",
        starting_head="0" * 40,
        approved_at=datetime.now(UTC),
        specification_digest=request.plan_state.specification_digest,
        material_digest=request.plan_state.material_digest,
        remediation_envelope_applicable=True,
    )


def _run_id(work_id: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{work_id}-{timestamp}"


def _repository_relative_path(path: Path, *, repository_root: Path) -> str:
    return path.resolve(strict=True).relative_to(repository_root.resolve(strict=True)).as_posix()
