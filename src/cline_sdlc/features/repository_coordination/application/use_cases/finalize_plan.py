"""Create or verify the unique progress-only plan finalization commit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase
from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
    FinalizationBlocker,
    FinalizationHistoryRequest,
    FinalizationResult,
    FinalizationStatus,
    GitFinalizationRequest,
    require_commit_hash,
)

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
        FinalizationCommitCandidate,
        RepositoryFinalizationRequest,
    )
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import PlanArtifactEvidence
    from cline_sdlc.features.repository_coordination.application.ports.finalization import (
        FinalizationHistoryReaderPort,
        GitFinalizerPort,
    )
    from cline_sdlc.features.repository_coordination.application.ports.reconciliation import PlanArtifactInspectorPort


class FinalizePlan:
    """Fail closed unless progress, approval, Git effects, and history agree."""

    def __init__(
        self,
        artifact_inspector: PlanArtifactInspectorPort,
        finalizer: GitFinalizerPort,
        history_reader: FinalizationHistoryReaderPort,
    ) -> None:
        self._artifact_inspector = artifact_inspector
        self._finalizer = finalizer
        self._history_reader = history_reader

    def execute(self, request: RepositoryFinalizationRequest) -> FinalizationResult:
        """Create one finalization commit or verify an existing completed plan."""
        current_inspection = self._artifact_inspector.inspect(request.current_plan_content, b"")
        if current_inspection.evidence is None:
            return _blocked(
                "finalization_plan_invalid",
                "current plan failed strict validation",
                current_inspection.error,
            )
        current = current_inspection.evidence
        identity_failure = _identity_failure(request, current)
        if identity_failure is not None:
            return identity_failure
        if current.phase is PlanPhase.COMPLETE:
            return self._verify_complete(request, current)
        return self._create_finalization(request, current)

    def _create_finalization(  # noqa: PLR0911 - Each fail-closed invariant has distinct evidence.
        self,
        request: RepositoryFinalizationRequest,
        current: PlanArtifactEvidence,
    ) -> FinalizationResult:
        if (
            request.completed_plan_content is None
            or request.recovery_plan_content is None
            or request.completed_at is None
        ):
            return _blocked(
                "finalization_transition_missing",
                "incomplete plan requires explicit finalization transition bytes",
            )
        transition_failure = _current_state_failure(request, current)
        if transition_failure is not None:
            return transition_failure
        completed_inspection = self._artifact_inspector.inspect(request.completed_plan_content, b"")
        recovery_inspection = self._artifact_inspector.inspect(request.recovery_plan_content, b"")
        if completed_inspection.evidence is None or recovery_inspection.evidence is None:
            return _blocked(
                "finalization_transition_invalid",
                "completed and recovery plans must both pass strict validation",
                completed_inspection.error or recovery_inspection.error,
            )
        transition_failure = _transition_failure(
            request,
            current,
            completed_inspection.evidence,
            recovery_inspection.evidence,
        )
        if transition_failure is not None:
            return transition_failure

        message = _message(current.work_id, current.material_digest)
        observation = self._finalizer.finalize(
            GitFinalizationRequest(
                repository_root=request.repository_root,
                starting_head=request.approval.starting_head,
                plan_path=request.plan_path,
                expected_plan_content=request.current_plan_content,
                completed_plan_content=request.completed_plan_content,
                recovery_plan_content=request.recovery_plan_content,
                message=message,
            )
        )
        if not observation.committed:
            return FinalizationResult(
                status=FinalizationStatus.RECOVERY_REQUIRED,
                blocker=FinalizationBlocker(
                    "finalization_commit_failed",
                    "Git did not create the authorized finalization commit",
                    observation.error,
                ),
            )
        verification_failure = _commit_observation_failure(
            request,
            observation.commit,
            observation.committed_paths,
            observation.commit_message,
            message,
        )
        if verification_failure is not None:
            return verification_failure
        verified = self._verify_complete(request, completed_inspection.evidence)
        if verified.status is not FinalizationStatus.ALREADY_COMPLETE:
            return verified
        return FinalizationResult(status=FinalizationStatus.FINALIZED, commit=observation.commit)

    def _verify_complete(
        self,
        request: RepositoryFinalizationRequest,
        current: PlanArtifactEvidence,
    ) -> FinalizationResult:
        if current.phase is not PlanPhase.COMPLETE or current.completed_at is None:
            return _blocked("plan_not_complete", "complete-plan verification requires complete state")
        history = self._history_reader.observe(
            FinalizationHistoryRequest(repository_root=request.repository_root, plan_path=request.plan_path)
        )
        if history.dirty_paths:
            return _blocked(
                "complete_plan_dirty",
                "a verified complete plan requires a clean working tree",
                ", ".join(history.dirty_paths),
            )
        matching = tuple(
            candidate
            for candidate in history.candidates
            if candidate.work_id == current.work_id and candidate.material_digest == current.material_digest
        )
        if len(matching) != 1:
            return _blocked(
                "finalization_commit_ambiguous" if matching else "finalization_commit_missing",
                "complete plan requires exactly one reachable finalization commit",
            )
        candidate_failure = self._candidate_failure(current, matching[0])
        if candidate_failure is not None:
            return candidate_failure
        return FinalizationResult(status=FinalizationStatus.ALREADY_COMPLETE, commit=matching[0].commit)

    def _candidate_failure(
        self,
        current: PlanArtifactEvidence,
        candidate: FinalizationCommitCandidate,
    ) -> FinalizationResult | None:
        committed = self._artifact_inspector.inspect(candidate.plan_content, b"")
        parent = (
            self._artifact_inspector.inspect(candidate.parent_plan_content, b"")
            if candidate.parent_plan_content is not None
            else None
        )
        if committed.evidence is None or committed.evidence.phase is not PlanPhase.COMPLETE:
            return _blocked("finalization_transition_missing", "finalization commit must contain complete plan state")
        if parent is None or parent.evidence is None or parent.evidence.phase is PlanPhase.COMPLETE:
            return _blocked("finalization_transition_not_introduced", "finalization commit must introduce completion")
        committed_state = committed.evidence
        if (
            _stable_identity(committed_state) != _stable_identity(current)
            or committed_state.completed_at != current.completed_at
        ):
            return _blocked("completed_plan_diverged", "current complete plan diverges from its finalization commit")
        return None


def _identity_failure(
    request: RepositoryFinalizationRequest,
    current: PlanArtifactEvidence,
) -> FinalizationResult | None:
    if current.specification_digest != request.approval.specification_digest:
        return _blocked("specification_digest_diverged", "specification digest diverged from invocation approval")
    if current.material_digest != request.approval.material_digest:
        return _blocked("material_digest_diverged", "plan material digest diverged from invocation approval")
    return None


def _current_state_failure(  # noqa: PLR0911 - Each fail-closed invariant has distinct evidence.
    request: RepositoryFinalizationRequest,
    current: PlanArtifactEvidence,
) -> FinalizationResult | None:
    if current.phase is not PlanPhase.IMPLEMENTING:
        return _blocked("finalization_phase_invalid", "only an implementing plan may transition to complete")
    if current.current_task is not None or current.current_slice is not None or current.slice_start_commit is not None:
        return _blocked("finalization_work_active", "finalization requires no active slice")
    if current.partial_slice_paths:
        return _blocked("finalization_work_partial", "finalization requires no partial paths")
    if current.blocker is not None:
        return _blocked("finalization_blocked", "finalization requires no plan blocker")
    if any(record.status != "completed" or record.attempt_count != 1 for record in current.remediation_records):
        return _blocked("remediation_incomplete", "all remediation records must be completed before finalization")
    if request.completed_at is None or request.completed_at < request.approval.approved_at:
        return _blocked("completion_time_invalid", "completion time must be UTC and not precede invocation approval")
    return None


def _transition_failure(  # noqa: PLR0911 - Each fail-closed invariant has distinct evidence.
    request: RepositoryFinalizationRequest,
    current: PlanArtifactEvidence,
    completed: PlanArtifactEvidence,
    recovery: PlanArtifactEvidence,
) -> FinalizationResult | None:
    if _stable_identity(completed) != _stable_identity(current) or _stable_identity(recovery) != _stable_identity(
        current
    ):
        return _blocked("finalization_progress_diverged", "finalization changed approved plan identity or progress")
    if completed.phase is not PlanPhase.COMPLETE or completed.completed_at != request.completed_at:
        return _blocked("completion_transition_invalid", "completed plan must record the exact completion time")
    if completed.updated_at != request.completed_at or completed.blocker is not None:
        return _blocked(
            "completion_transition_invalid",
            "completed plan must clear blockers and update timestamps atomically",
        )
    if (
        recovery.phase is not PlanPhase.BLOCKED
        or recovery.current_task != "finalization"
        or recovery.current_slice != "finalization"
    ):
        return _blocked("finalization_recovery_invalid", "recovery plan must reserve the finalization transaction")
    if recovery.slice_start_commit != request.approval.starting_head or recovery.partial_slice_paths != (
        request.plan_path,
    ):
        return _blocked(
            "finalization_recovery_invalid",
            "recovery plan must identify starting HEAD and only the plan path",
        )
    if recovery.blocker is None or recovery.completed_at is not None:
        return _blocked("finalization_recovery_invalid", "recovery plan must remain blocked and incomplete")
    return None


def _stable_identity(evidence: PlanArtifactEvidence) -> tuple[object, ...]:
    return (
        evidence.work_id,
        evidence.specification_path,
        evidence.specification_digest,
        evidence.material_digest,
        evidence.completed_slice_ids,
        evidence.remediation_records,
        evidence.validation_evidence,
    )


def _message(work_id: str, material_digest: str) -> str:
    return "\n".join(
        (
            "chore(sdlc): finalize completed plan",
            "",
            f"Cline-SDLC-Work-ID: {work_id}",
            "Cline-SDLC-Plan-Finalization: true",
            f"Cline-SDLC-Material-Digest: {material_digest}",
        )
    )


def _commit_observation_failure(
    request: RepositoryFinalizationRequest,
    commit: str | None,
    committed_paths: tuple[str, ...],
    message: str | None,
    expected_message: str,
) -> FinalizationResult | None:
    try:
        require_commit_hash(commit or "")
    except ValueError as err:
        return _blocked("finalization_commit_not_verified", "created finalization hash is invalid", str(err))
    if committed_paths != (request.plan_path,):
        return _blocked("finalization_paths_mismatch", "finalization commit must contain only the plan")
    if message is None or message.strip() != expected_message:
        return _blocked("finalization_trailers_mismatch", "finalization commit trailers do not match authorization")
    return None


def _blocked(code: str, summary: str, evidence: str | None = None) -> FinalizationResult:
    return FinalizationResult(
        status=FinalizationStatus.BLOCKED,
        blocker=FinalizationBlocker(code=code, summary=summary, evidence=evidence),
    )
