"""End-to-end application tests for serial plan implementation transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_implementation import (
    PlanImplementationRequest,
    PlanImplementationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionBlocker,
    SliceExecutionRequest,
    SliceExecutionResult,
    SliceExecutionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    SliceCommitCandidate,
    SliceReconciliationRequest,
    SliceReconciliationResult,
    SliceReconciliationStatus,
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
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.implement_plan import ImplementPlan
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
    SliceCommitRequest,
    SliceCommitResult,
    SliceCommitStatus,
)

SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
PLAN_PATH = "docs/plans/work.md"
SLICE_IDS = ("slice-1", "slice-2", "slice-3")
STARTING_HEAD = "a" * 40
HUMAN_COMMIT = "e" * 40
SLICE_COMMITS = ("b" * 40, "c" * 40, "d" * 40)


@dataclass
class RecordingExecution:
    results: list[SliceExecutionResult]
    requests: list[SliceExecutionRequest] = field(default_factory=list)

    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        self.requests.append(request)
        return self.results.pop(0)


@dataclass
class RecordingReconciliation:
    requests: list[SliceReconciliationRequest] = field(default_factory=list)

    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
        self.requests.append(request)
        return SliceReconciliationResult(
            status=SliceReconciliationStatus.COMMIT_CANDIDATE,
            commit_candidate=SliceCommitCandidate(
                work_id=request.work_id,
                task_id=request.selection.task_id,
                slice_id=request.selection.slice_id,
                starting_head=request.slice_start_commit,
                material_digest=request.material_digest,
                paths=request.expected_paths,
                validation_evidence=(),
            ),
        )


@dataclass
class RecordingCommit:
    commits: list[str]
    requests: list[SliceCommitRequest] = field(default_factory=list)

    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        self.requests.append(request)
        return SliceCommitResult(status=SliceCommitStatus.COMMITTED, commit=self.commits.pop(0))


@dataclass
class RecordingProgress:
    next_selections: list[SliceSelectionResult]
    current_head: str = STARTING_HEAD
    approval_ids: list[int] = field(default_factory=list)

    def prepare_execution(self, approval: InvocationApproval, selection: SelectedSlice) -> SliceExecutionRequest:
        self.approval_ids.append(id(approval))
        return SliceExecutionRequest(
            approval=approval,
            selection=selection,
            specification_path="docs/specs/work.md",
            specification_content="# Accepted specification",
            specification_digest=SPECIFICATION_DIGEST,
            plan_path=PLAN_PATH,
            plan_content="# Ready plan",
            material_digest=MATERIAL_DIGEST,
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
            cline_command="cline",
            timeout_seconds=1800,
            focused_validation_commands=(_focused_validation(),),
            expected_paths=(PLAN_PATH, f"src/{selection.slice_id}.py"),
        )

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        self.approval_ids.append(id(approval))
        return SliceReconciliationRequest(
            work_id="serial-work",
            approval=approval,
            selection=selection,
            slice_start_commit=self.current_head,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
            plan_path=PLAN_PATH,
            expected_paths=(PLAN_PATH, f"src/{selection.slice_id}.py"),
            execution=execution,
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
        )

    def prepare_commit(
        self,
        approval: InvocationApproval,
        candidate: SliceCommitCandidate,
    ) -> SliceCommitRequest:
        self.approval_ids.append(id(approval))
        return SliceCommitRequest(
            repository_root=Path("/repo"),
            plan_path=PLAN_PATH,
            current_plan_content=f"current {candidate.slice_id}".encode(),
            updated_plan_content=f"completed {candidate.slice_id}".encode(),
            candidate=candidate,
            short_description=f"complete {candidate.slice_id}",
        )

    def select_after_commit(self, approval: InvocationApproval, commit: str) -> SliceSelectionResult:
        self.approval_ids.append(id(approval))
        self.current_head = HUMAN_COMMIT if commit == SLICE_COMMITS[0] else commit
        return self.next_selections.pop(0)


def test_runs_three_fresh_serial_transactions_with_one_immutable_approval() -> None:
    approval = _approval()
    execution = RecordingExecution([_completed_execution() for _ in SLICE_IDS])
    reconciliation = RecordingReconciliation()
    commit = RecordingCommit(list(SLICE_COMMITS))
    progress = RecordingProgress(
        [
            _selected(SLICE_IDS[1]),
            _selected(SLICE_IDS[2]),
            SliceSelectionResult(status=SliceSelectionStatus.COMPLETE, completed_slice_ids=SLICE_IDS),
        ]
    )

    result = _use_case(progress, execution, reconciliation, commit).execute(
        PlanImplementationRequest(approval=approval, initial_selection=_selection(SLICE_IDS[0]))
    )

    assert result.status is PlanImplementationStatus.COMPLETED
    assert result.completed_slice_ids == SLICE_IDS
    assert result.commits == SLICE_COMMITS
    assert [request.selection.slice_id for request in execution.requests] == list(SLICE_IDS)
    assert len({id(request) for request in execution.requests}) == len(SLICE_IDS)
    assert set(progress.approval_ids) == {id(approval)}
    assert reconciliation.requests[1].slice_start_commit == HUMAN_COMMIT
    assert [request.candidate.slice_id for request in commit.requests] == list(SLICE_IDS)


def test_non_completed_transaction_starts_no_later_slice() -> None:
    execution = RecordingExecution(
        [
            _completed_execution(),
            SliceExecutionResult(
                status=SliceExecutionStatus.BLOCKED,
                blocker=SliceExecutionBlocker("approval_required", "manual approval is required"),
            ),
        ]
    )
    reconciliation = RecordingReconciliation()
    commit = RecordingCommit(list(SLICE_COMMITS))
    progress = RecordingProgress([_selected(SLICE_IDS[1])])

    result = _use_case(progress, execution, reconciliation, commit).execute(
        PlanImplementationRequest(approval=_approval(), initial_selection=_selection(SLICE_IDS[0]))
    )

    assert result.status is PlanImplementationStatus.BLOCKED
    assert result.completed_slice_ids == (SLICE_IDS[0],)
    assert result.commits == (SLICE_COMMITS[0],)
    assert [request.selection.slice_id for request in execution.requests] == list(SLICE_IDS[:2])
    assert len(reconciliation.requests) == 1
    assert len(commit.requests) == 1
    assert result.blocker is not None
    assert result.blocker.code == "approval_required"


def _use_case(
    progress: RecordingProgress,
    execution: RecordingExecution,
    reconciliation: RecordingReconciliation,
    commit: RecordingCommit,
) -> ImplementPlan:
    return ImplementPlan(
        progress=progress,
        slice_execution=execution,
        slice_reconciliation=reconciliation,
        slice_commit=commit,
    )


def _approval() -> InvocationApproval:
    return InvocationApproval(
        run_id="run-serial",
        profile="balanced",
        starting_head=STARTING_HEAD,
        approved_at=datetime(2026, 7, 26, 1, 0, tzinfo=UTC),
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )


def _selection(slice_id: str) -> SelectedSlice:
    return SelectedSlice(task_id="task-serial", slice_id=slice_id, resuming_partial=False)


def _selected(slice_id: str) -> SliceSelectionResult:
    return SliceSelectionResult(status=SliceSelectionStatus.SELECTED, selection=_selection(slice_id))


def _completed_execution() -> SliceExecutionResult:
    return SliceExecutionResult(status=SliceExecutionStatus.COMPLETED)


def _focused_validation() -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand(executable="uv", arguments=("run", "pytest", "tests/focused.py")),
        source=ValidationCommandSource.EXPLICIT,
        reason="accepted slice verification",
    )
