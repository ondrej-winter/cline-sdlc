"""Execute accepted final-review remediation once and confirm the result."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.domain.findings import FindingSeverity
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
    FinalReviewStatus,
    RemediationStatus,
    finding_is_open,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import FinalValidationStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.remediation import (
    RemediationBlocker,
    RemediationExecutionStatus,
    RemediationRequest,
    RemediationResult,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import SliceExecutionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    SliceKind,
    SliceReconciliationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SelectedSlice
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import SliceCommitStatus

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
        FinalReviewRequest,
        FinalReviewResult,
        RemediationRecord,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import (
        FinalValidationRequest,
        FinalValidationResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
        SliceExecutionRequest,
        SliceExecutionResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
        SliceCommitCandidate,
        SliceReconciliationRequest,
        SliceReconciliationResult,
    )
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
    from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
        SliceCommitRequest,
        SliceCommitResult,
    )


class SliceExecutionPort(Protocol):
    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        """Execute one fresh remediation session and focused validation."""


class SliceReconciliationPort(Protocol):
    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
        """Independently reconcile one remediation attempt."""


class SliceCommitPort(Protocol):
    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        """Create one explicit remediation commit."""


class FinalValidationPort(Protocol):
    def execute(self, request: FinalValidationRequest) -> FinalValidationResult:
        """Rerun affected authoritative broad checks."""


class FinalReviewPort(Protocol):
    def execute(self, request: FinalReviewRequest) -> FinalReviewResult:
        """Run exactly one fresh read-only confirmation review."""


class RemediationProgressPort(Protocol):
    """Refresh plan and Git inputs around remediation transactions."""

    def prepare_execution(
        self, approval: InvocationApproval, record: RemediationRecord, selection: SelectedSlice
    ) -> SliceExecutionRequest:
        """Build a remediation-role execution request."""

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        record: RemediationRecord,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        """Build a remediation-kind reconciliation request."""

    def prepare_commit(
        self, approval: InvocationApproval, record: RemediationRecord, candidate: SliceCommitCandidate
    ) -> SliceCommitRequest:
        """Build the one-attempt progress transition for a remediation commit."""

    def prepare_validation(self, approval: InvocationApproval, end_commit: str) -> FinalValidationRequest:
        """Build affected broad validation against the latest remediation commit."""

    def prepare_confirmation(
        self, approval: InvocationApproval, end_commit: str, validation: FinalValidationResult
    ) -> FinalReviewRequest:
        """Build the one fresh confirmation-review request."""


class RemediateFinalReview:
    """Compose existing slice boundaries for one-attempt final remediation."""

    def __init__(  # noqa: PLR0913 - Explicit ports keep orchestration dependencies visible.
        self,
        *,
        progress: RemediationProgressPort,
        slice_execution: SliceExecutionPort,
        slice_reconciliation: SliceReconciliationPort,
        slice_commit: SliceCommitPort,
        final_validation: FinalValidationPort,
        final_review: FinalReviewPort,
    ) -> None:
        self._progress = progress
        self._slice_execution = slice_execution
        self._slice_reconciliation = slice_reconciliation
        self._slice_commit = slice_commit
        self._final_validation = final_validation
        self._final_review = final_review

    def execute(self, request: RemediationRequest) -> RemediationResult:
        """Commit each accepted correction once, rerun broad checks, and confirm."""
        records: list[RemediationRecord] = []
        commits: list[str] = []
        for record in request.initial_review.remediation_records:
            stopped = self._execute_record(request.approval, record, records, commits)
            if stopped is not None:
                return stopped

        latest_commit = commits[-1]
        validation = self._final_validation.execute(self._progress.prepare_validation(request.approval, latest_commit))
        if validation.status is not FinalValidationStatus.COMPLETED:
            blocker = validation.blocker
            return _stopped(
                RemediationExecutionStatus.FAILED,
                records,
                commits,
                RemediationBlocker(
                    blocker.code if blocker else "affected_broad_validation_incomplete",
                    blocker.summary if blocker else "affected broad validation did not pass",
                    blocker.evidence if blocker else None,
                ),
                validation=validation,
            )
        confirmation = self._final_review.execute(
            self._progress.prepare_confirmation(request.approval, latest_commit, validation)
        )
        confirmation_failure = _confirmation_failure(request, confirmation)
        if confirmation_failure is not None:
            return _stopped(
                RemediationExecutionStatus.BLOCKED,
                records,
                commits,
                confirmation_failure,
                validation=validation,
                confirmation=confirmation,
            )
        return RemediationResult(
            status=RemediationExecutionStatus.COMPLETED,
            remediation_records=tuple(records),
            commits=tuple(commits),
            final_validation=validation,
            confirmation_review=confirmation,
        )

    def _execute_record(  # noqa: PLR0911 - Each transaction boundary fails closed with distinct evidence.
        self,
        approval: InvocationApproval,
        record: RemediationRecord,
        records: list[RemediationRecord],
        commits: list[str],
    ) -> RemediationResult | None:
        selection = SelectedSlice(task_id="final-remediation", slice_id=record.finding_id, resuming_partial=False)
        execution_request = self._progress.prepare_execution(approval, record, selection)
        if execution_request.session_role is not SessionRole.REMEDIATION:
            return _stopped(
                RemediationExecutionStatus.BLOCKED,
                records,
                commits,
                RemediationBlocker("remediation_role_required", "remediation must use a fresh remediation session"),
            )
        execution = self._slice_execution.execute(execution_request)
        if execution.status is not SliceExecutionStatus.COMPLETED:
            blocker = execution.blocker
            status = (
                RemediationExecutionStatus.INTERRUPTED
                if execution.status is SliceExecutionStatus.INTERRUPTED
                else RemediationExecutionStatus.FAILED
            )
            return _stopped(
                status,
                records,
                commits,
                RemediationBlocker(
                    blocker.code if blocker else "remediation_execution_incomplete",
                    blocker.summary if blocker else "remediation execution did not complete",
                    blocker.evidence if blocker else None,
                ),
            )
        reconciliation_request = self._progress.prepare_reconciliation(approval, record, selection, execution)
        if reconciliation_request.kind is not SliceKind.REMEDIATION:
            return _stopped(
                RemediationExecutionStatus.BLOCKED,
                records,
                commits,
                RemediationBlocker("remediation_kind_required", "reconciliation must preserve remediation ownership"),
            )
        reconciliation = self._slice_reconciliation.execute(reconciliation_request)
        if (
            reconciliation.status is not SliceReconciliationStatus.COMMIT_CANDIDATE
            or reconciliation.commit_candidate is None
        ):
            return _from_reconciliation(records, commits, reconciliation)
        candidate = reconciliation.commit_candidate
        if candidate.kind is not SliceKind.REMEDIATION or candidate.slice_id != record.finding_id:
            return _stopped(
                RemediationExecutionStatus.BLOCKED,
                records,
                commits,
                RemediationBlocker("remediation_identity_diverged", "commit candidate changed remediation identity"),
            )
        commit = self._slice_commit.execute(self._progress.prepare_commit(approval, record, candidate))
        if commit.status is not SliceCommitStatus.COMMITTED or commit.commit is None:
            return _from_commit(records, commits, commit)
        records.append(replace(record, status=RemediationStatus.COMPLETED, attempt_count=1))
        commits.append(commit.commit)
        return None


def _confirmation_failure(request: RemediationRequest, result: FinalReviewResult) -> RemediationBlocker | None:
    initial_ids = {record.finding_id for record in request.initial_review.remediation_records}
    open_findings = tuple(finding for finding in result.findings if finding_is_open(finding))
    repeated = next((finding for finding in open_findings if finding.id in initial_ids), None)
    if repeated is not None:
        return RemediationBlocker("repeated_final_finding", "confirmation repeated a remediated finding", repeated.id)
    unresolved = next(
        (finding for finding in open_findings if finding.severity in {FindingSeverity.BLOCKING, FindingSeverity.MAJOR}),
        None,
    )
    if unresolved is not None:
        return RemediationBlocker(
            "new_unresolved_final_finding",
            "confirmation found a new unresolved finding",
            unresolved.id,
        )
    if result.status is not FinalReviewStatus.CLEAN:
        blocker = result.blocker
        return RemediationBlocker(
            blocker.code if blocker else "confirmation_review_not_clean",
            blocker.summary if blocker else "confirmation review did not establish a clean result",
            blocker.evidence if blocker else None,
        )
    return None


def _from_reconciliation(
    records: list[RemediationRecord], commits: list[str], result: SliceReconciliationResult
) -> RemediationResult:
    blocker = result.blocker
    status = (
        RemediationExecutionStatus.RECOVERY_REQUIRED
        if result.status is SliceReconciliationStatus.RECOVERY_REQUIRED
        else RemediationExecutionStatus.BLOCKED
    )
    return _stopped(
        status,
        records,
        commits,
        RemediationBlocker(
            blocker.code if blocker else "remediation_reconciliation_incomplete",
            blocker.summary if blocker else "remediation reconciliation did not produce a commit candidate",
            blocker.evidence if blocker else None,
        ),
    )


def _from_commit(records: list[RemediationRecord], commits: list[str], result: SliceCommitResult) -> RemediationResult:
    blocker = result.blocker
    status = (
        RemediationExecutionStatus.RECOVERY_REQUIRED
        if result.status is SliceCommitStatus.RECOVERY_REQUIRED
        else RemediationExecutionStatus.BLOCKED
    )
    return _stopped(
        status,
        records,
        commits,
        RemediationBlocker(
            blocker.code if blocker else "remediation_commit_incomplete",
            blocker.summary if blocker else "remediation commit did not complete",
            blocker.evidence if blocker else None,
        ),
    )


def _stopped(  # noqa: PLR0913 - Terminal evidence is assembled explicitly at one boundary.
    status: RemediationExecutionStatus,
    records: list[RemediationRecord],
    commits: list[str],
    blocker: RemediationBlocker,
    *,
    validation: FinalValidationResult | None = None,
    confirmation: FinalReviewResult | None = None,
) -> RemediationResult:
    return RemediationResult(
        status=status,
        remediation_records=tuple(records),
        commits=tuple(commits),
        final_validation=validation,
        confirmation_review=confirmation,
        blocker=blocker,
    )
