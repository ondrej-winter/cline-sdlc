"""End-to-end application proof for cross-process partial-slice resumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_implementation import (
    PlanImplementationRequest,
    PlanImplementationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
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
    PartialSliceProgress,
    PlanSliceDefinition,
    PlanTaskDefinition,
    SelectedSlice,
    SliceCompletionEvidence,
    SliceSelectionRequest,
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
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_slice import SelectSlice
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
    SliceCommitRequest,
    SliceCommitResult,
    SliceCommitStatus,
)

SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
STARTING_HEAD = "a" * 40
RESUME_COMMIT = "b" * 40
PLAN_PATH = "docs/plans/work.md"


@dataclass
class RecordingExecution:
    selections: list[SelectedSlice] = field(default_factory=list)

    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        self.selections.append(request.selection)
        return SliceExecutionResult(status=SliceExecutionStatus.COMPLETED)


class PassingReconciliation:
    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
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


class PassingCommit:
    def execute(self, _request: SliceCommitRequest) -> SliceCommitResult:
        return SliceCommitResult(status=SliceCommitStatus.COMMITTED, commit=RESUME_COMMIT)


@dataclass
class ResumeProgress:
    def prepare_execution(self, approval: InvocationApproval, selection: SelectedSlice) -> SliceExecutionRequest:
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
            expected_paths=(PLAN_PATH, "src/partial.py"),
        )

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        return SliceReconciliationRequest(
            work_id="resume-work",
            approval=approval,
            selection=selection,
            slice_start_commit=STARTING_HEAD,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
            plan_path=PLAN_PATH,
            expected_paths=(PLAN_PATH, "src/partial.py"),
            execution=execution,
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
        )

    def prepare_commit(
        self,
        _approval: InvocationApproval,
        candidate: SliceCommitCandidate,
    ) -> SliceCommitRequest:
        return SliceCommitRequest(
            repository_root=Path("/repo"),
            plan_path=PLAN_PATH,
            current_plan_content=b"partial",
            updated_plan_content=b"complete",
            candidate=candidate,
            short_description="resume partial slice",
        )

    def select_after_commit(self, _approval: InvocationApproval, _commit: str) -> SliceSelectionResult:
        return SliceSelectionResult(status=SliceSelectionStatus.COMPLETE, completed_slice_ids=("slice-1", "slice-2"))


def test_new_process_resumes_recorded_partial_slice_before_later_work() -> None:
    selection = SelectSlice().execute(
        SliceSelectionRequest(
            tasks=(
                PlanTaskDefinition(
                    task_id="task-1",
                    slices=(
                        PlanSliceDefinition(slice_id="slice-1"),
                        PlanSliceDefinition(slice_id="slice-2", dependencies=("slice-1",)),
                    ),
                ),
            ),
            completed_slice_ids=("slice-1",),
            completion_evidence=(SliceCompletionEvidence(slice_id="slice-1", completed=True),),
            partial_slice=PartialSliceProgress(
                task_id="task-1",
                slice_id="slice-2",
                paths=(PLAN_PATH, "src/partial.py"),
            ),
        )
    )
    assert selection.selection is not None
    execution = RecordingExecution()

    result = ImplementPlan(
        progress=ResumeProgress(),
        slice_execution=execution,
        slice_reconciliation=PassingReconciliation(),
        slice_commit=PassingCommit(),
    ).execute(PlanImplementationRequest(approval=_approval(), initial_selection=selection.selection))

    assert result.status is PlanImplementationStatus.COMPLETED
    assert result.completed_slice_ids == ("slice-2",)
    assert result.commits == (RESUME_COMMIT,)
    assert [item.slice_id for item in execution.selections] == ["slice-2"]
    assert execution.selections[0].resuming_partial is True


def _approval() -> InvocationApproval:
    return InvocationApproval(
        run_id="run-resume",
        profile="balanced",
        starting_head=STARTING_HEAD,
        approved_at=datetime(2026, 7, 26, 17, 0, tzinfo=UTC),
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )


def _focused_validation() -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand(executable="uv", arguments=("run", "pytest", "tests/focused.py")),
        source=ValidationCommandSource.EXPLICIT,
        reason="accepted resume verification",
    )
