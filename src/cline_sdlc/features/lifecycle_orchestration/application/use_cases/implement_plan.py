"""Run approved implementation slices serially until completion or first failure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_implementation import (
    PlanImplementationBlocker,
    PlanImplementationRequest,
    PlanImplementationResult,
    PlanImplementationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import SliceExecutionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import SliceReconciliationStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SliceSelectionStatus
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import SliceCommitStatus

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
        SliceExecutionRequest,
        SliceExecutionResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
        SliceCommitCandidate,
        SliceReconciliationRequest,
        SliceReconciliationResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
        SelectedSlice,
        SliceSelectionResult,
    )
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
    from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
        SliceCommitRequest,
        SliceCommitResult,
    )


class SliceExecutionPort(Protocol):
    """Execute one fresh bounded slice session."""

    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        """Return session, operation, and focused-validation evidence."""


class SliceReconciliationPort(Protocol):
    """Independently reconcile one executed slice."""

    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
        """Return a commit candidate or attributable failure state."""


class SliceCommitPort(Protocol):
    """Create one explicit atomic slice commit."""

    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        """Return the verified local commit or recovery state."""


class PlanProgressPort(Protocol):
    """Refresh plan-owned inputs around each serial transaction."""

    def prepare_execution(self, approval: InvocationApproval, selection: SelectedSlice) -> SliceExecutionRequest:
        """Build current execution input without changing invocation approval."""

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        """Build reconciliation input from current Git and artifact state."""

    def prepare_commit(
        self,
        approval: InvocationApproval,
        candidate: SliceCommitCandidate,
    ) -> SliceCommitRequest:
        """Build the progress-only plan transition for a verified candidate."""

    def select_after_commit(self, approval: InvocationApproval, commit: str) -> SliceSelectionResult:
        """Refresh progress and select the next dependency-ready slice."""


class ImplementPlan:
    """Compose existing single-slice boundaries into one fail-closed serial loop."""

    def __init__(
        self,
        *,
        progress: PlanProgressPort,
        slice_execution: SliceExecutionPort,
        slice_reconciliation: SliceReconciliationPort,
        slice_commit: SliceCommitPort,
    ) -> None:
        self._progress = progress
        self._slice_execution = slice_execution
        self._slice_reconciliation = slice_reconciliation
        self._slice_commit = slice_commit

    def execute(self, request: PlanImplementationRequest) -> PlanImplementationResult:
        """Commit serial slices while the original approval remains valid."""
        approval = request.approval
        selection = request.initial_selection
        completed: list[str] = []
        commits: list[str] = []

        while True:
            execution = self._slice_execution.execute(self._progress.prepare_execution(approval, selection))
            if execution.status is not SliceExecutionStatus.COMPLETED:
                blocker = execution.blocker
                status = (
                    PlanImplementationStatus.BLOCKED
                    if execution.status is SliceExecutionStatus.BLOCKED
                    else PlanImplementationStatus.FAILED
                )
                return _stopped(
                    status,
                    approval,
                    completed,
                    commits,
                    PlanImplementationBlocker(
                        blocker.code if blocker else "slice_execution_incomplete",
                        blocker.summary if blocker else "slice execution did not complete",
                        blocker.evidence if blocker else None,
                    ),
                )

            reconciliation = self._slice_reconciliation.execute(
                self._progress.prepare_reconciliation(approval, selection, execution)
            )
            if (
                reconciliation.status is not SliceReconciliationStatus.COMMIT_CANDIDATE
                or reconciliation.commit_candidate is None
            ):
                return _reconciliation_stopped(approval, completed, commits, reconciliation)

            commit = self._slice_commit.execute(
                self._progress.prepare_commit(approval, reconciliation.commit_candidate)
            )
            if commit.status is not SliceCommitStatus.COMMITTED or commit.commit is None:
                return _commit_stopped(approval, completed, commits, commit)

            completed.append(selection.slice_id)
            commits.append(commit.commit)
            next_selection = self._progress.select_after_commit(approval, commit.commit)
            if next_selection.status is SliceSelectionStatus.COMPLETE:
                return PlanImplementationResult(
                    status=PlanImplementationStatus.COMPLETED,
                    approval=approval,
                    completed_slice_ids=tuple(completed),
                    commits=tuple(commits),
                )
            if next_selection.status is not SliceSelectionStatus.SELECTED or next_selection.selection is None:
                selection_blocker = next_selection.blocker
                return _stopped(
                    PlanImplementationStatus.BLOCKED,
                    approval,
                    completed,
                    commits,
                    PlanImplementationBlocker(
                        selection_blocker.code if selection_blocker else "next_slice_not_selected",
                        (
                            selection_blocker.summary
                            if selection_blocker
                            else "plan progress did not select later work safely"
                        ),
                        selection_blocker.evidence if selection_blocker else None,
                    ),
                )
            selection = next_selection.selection


def _reconciliation_stopped(
    approval: InvocationApproval,
    completed: list[str],
    commits: list[str],
    result: SliceReconciliationResult,
) -> PlanImplementationResult:
    blocker = result.blocker
    status = (
        PlanImplementationStatus.RECOVERY_REQUIRED
        if result.status is SliceReconciliationStatus.RECOVERY_REQUIRED
        else PlanImplementationStatus.BLOCKED
    )
    return _stopped(
        status,
        approval,
        completed,
        commits,
        PlanImplementationBlocker(
            blocker.code if blocker else "slice_reconciliation_incomplete",
            blocker.summary if blocker else "slice reconciliation did not produce a commit candidate",
            blocker.evidence if blocker else None,
        ),
    )


def _commit_stopped(
    approval: InvocationApproval,
    completed: list[str],
    commits: list[str],
    result: SliceCommitResult,
) -> PlanImplementationResult:
    blocker = result.blocker
    status = (
        PlanImplementationStatus.RECOVERY_REQUIRED
        if result.status is SliceCommitStatus.RECOVERY_REQUIRED
        else PlanImplementationStatus.BLOCKED
    )
    return _stopped(
        status,
        approval,
        completed,
        commits,
        PlanImplementationBlocker(
            blocker.code if blocker else "slice_commit_incomplete",
            blocker.summary if blocker else "slice commit did not complete",
            blocker.evidence if blocker else None,
        ),
    )


def _stopped(
    status: PlanImplementationStatus,
    approval: InvocationApproval,
    completed: list[str],
    commits: list[str],
    blocker: PlanImplementationBlocker,
) -> PlanImplementationResult:
    return PlanImplementationResult(
        status=status,
        approval=approval,
        completed_slice_ids=tuple(completed),
        commits=tuple(commits),
        blocker=blocker,
    )
