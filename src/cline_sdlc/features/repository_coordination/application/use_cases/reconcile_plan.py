"""Reconcile accepted plan artifacts, Git ownership, and invocation approval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SliceSelectionStatus
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_slice import SelectSlice
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import (
    InvocationApproval,
    OwningCommitCandidate,
    PlanArtifactEvidence,
    PlanHistoryRequest,
    PlanReconciliationBlocker,
    PlanReconciliationRequest,
    PlanReconciliationResult,
    PlanReconciliationStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.ports.reconciliation import (
        InvocationApprovalRecorderPort,
        PlanArtifactInspectorPort,
        PlanHistoryReaderPort,
    )


class ReconcilePlan:
    """Fail closed unless artifacts, progress, history, and approval agree."""

    def __init__(
        self,
        artifact_inspector: PlanArtifactInspectorPort,
        history_reader: PlanHistoryReaderPort,
        approval_recorder: InvocationApprovalRecorderPort,
    ) -> None:
        self._artifact_inspector = artifact_inspector
        self._history_reader = history_reader
        self._approval_recorder = approval_recorder

    def execute(self, request: PlanReconciliationRequest) -> PlanReconciliationResult:  # noqa: PLR0911
        """Authorize selected work only after immutable approval is safely recorded."""
        artifact = self._artifact_inspector.inspect(request.plan_content, request.specification_content)
        if artifact.evidence is None:
            return _blocked(
                "artifact_reconciliation_failed",
                "plan or specification evidence is invalid",
                artifact.error,
            )
        current = artifact.evidence
        if current.specification_path != request.specification_path:
            return _blocked("specification_path_mismatch", "plan state references a different specification")
        if current.completed_slice_ids != request.selection_request.completed_slice_ids:
            return _blocked("completed_progress_conflict", "plan state and slice-selection progress must agree exactly")

        history = self._history_reader.observe(
            PlanHistoryRequest(
                repository_root=request.repository_root,
                plan_path=request.plan_path,
                completed_slice_ids=current.completed_slice_ids,
            )
        )
        approval = InvocationApproval(
            run_id=request.run_id,
            profile="balanced",
            starting_head=history.head_commit,
            approved_at=request.approved_at,
            specification_digest=current.specification_digest,
            material_digest=current.material_digest,
            remediation_envelope_applicable=request.remediation_envelope_applicable,
        )
        try:
            self._approval_recorder.record_approval(request.repository_root.resolve().as_posix(), approval)
        except (OSError, ValueError) as err:
            return _blocked(
                "invocation_approval_not_recorded",
                "invocation approval could not be recorded safely",
                str(err),
            )

        owners_result = self._verify_owners(current, history.owning_candidates)
        if isinstance(owners_result, PlanReconciliationResult):
            return owners_result

        partial_blocker = _partial_state_blocker(current, history.head_commit, history.dirty_paths)
        if partial_blocker is not None:
            return partial_blocker

        selection = SelectSlice().execute(request.selection_request)
        if selection.status is SliceSelectionStatus.BLOCKED:
            if selection.blocker is None:
                return _blocked("slice_selection_invalid", "blocked slice selection omitted its blocker")
            return _blocked(selection.blocker.code, selection.blocker.summary, selection.blocker.evidence)

        status = (
            PlanReconciliationStatus.COMPLETE
            if selection.status is SliceSelectionStatus.COMPLETE
            else PlanReconciliationStatus.AUTHORIZED
        )
        return PlanReconciliationResult(
            status=status,
            approval=approval,
            selection=selection.selection,
            owning_commits=tuple((slice_id, commit) for slice_id, commit in owners_result.items()),
        )

    def _verify_owners(
        self,
        current: PlanArtifactEvidence,
        candidates: tuple[OwningCommitCandidate, ...],
    ) -> dict[str, str] | PlanReconciliationResult:
        owners: dict[str, str] = {}
        for slice_id in current.completed_slice_ids:
            matching = tuple(
                candidate
                for candidate in candidates
                if candidate.slice_id == slice_id
                and candidate.work_id == current.work_id
                and candidate.slice_kind in {"implementation", "remediation"}
                and candidate.material_digest == current.material_digest
            )
            if len(matching) != 1:
                return _blocked(
                    "slice_owner_ambiguous" if matching else "slice_owner_missing",
                    "completed slice requires exactly one reachable owning commit",
                    slice_id,
                )
            candidate = matching[0]
            committed = self._artifact_inspector.inspect(candidate.plan_content, b"")
            parent = (
                self._artifact_inspector.inspect(candidate.parent_plan_content, b"")
                if candidate.parent_plan_content is not None
                else None
            )
            if committed.evidence is None or slice_id not in committed.evidence.completed_slice_ids:
                return _blocked(
                    "slice_transition_missing",
                    "owning commit must contain the completed slice transition",
                    slice_id,
                )
            if parent is not None and parent.evidence is not None and slice_id in parent.evidence.completed_slice_ids:
                return _blocked(
                    "slice_transition_not_introduced",
                    "owning commit must introduce the completion transition",
                    slice_id,
                )
            owners[slice_id] = candidate.commit
        return owners


def _partial_state_blocker(
    current: PlanArtifactEvidence,
    head_commit: str,
    dirty_paths: tuple[str, ...],
) -> PlanReconciliationResult | None:
    has_partial = current.current_slice is not None
    if not has_partial and dirty_paths:
        return _blocked(
            "unexpected_dirty_paths",
            "dirty paths require a recorded partial slice",
            ", ".join(dirty_paths),
        )
    if not has_partial:
        return None
    if current.slice_start_commit != head_commit:
        return _blocked("partial_slice_head_mismatch", "partial slice must resume from its recorded starting HEAD")
    observed = set(dirty_paths)
    recorded = set(current.partial_slice_paths)
    if not observed or not observed.issubset(recorded):
        return _blocked(
            "partial_slice_paths_mismatch",
            "observed dirty paths must be a non-empty subset of recorded partial slice paths",
        )
    return None


def _blocked(code: str, summary: str, evidence: str | None = None) -> PlanReconciliationResult:
    return PlanReconciliationResult(
        status=PlanReconciliationStatus.BLOCKED,
        blocker=PlanReconciliationBlocker(code=code, summary=summary, evidence=evidence),
    )
