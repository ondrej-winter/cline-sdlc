"""Create one explicit atomic commit from a reconciled slice candidate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import SliceKind
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
    GitSliceCommitRequest,
    SliceCommitBlocker,
    SliceCommitRecovery,
    SliceCommitResult,
    SliceCommitStatus,
    require_commit_hash,
)

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import PlanArtifactEvidence
    from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import SliceCommitRequest
    from cline_sdlc.features.repository_coordination.application.ports.reconciliation import PlanArtifactInspectorPort
    from cline_sdlc.features.repository_coordination.application.ports.slice_commit import GitSliceCommitterPort


class CommitSlice:
    """Validate progress-only completion before authorizing exact Git effects."""

    def __init__(self, artifact_inspector: PlanArtifactInspectorPort, committer: GitSliceCommitterPort) -> None:
        self._artifact_inspector = artifact_inspector
        self._committer = committer

    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        """Create and independently verify one local implementation-slice commit."""
        current = self._artifact_inspector.inspect(request.current_plan_content, b"")
        updated = self._artifact_inspector.inspect(request.updated_plan_content, b"")
        blocker = _progress_blocker(request, current.evidence, updated.evidence, current.error, updated.error)
        if blocker is not None:
            return SliceCommitResult(status=SliceCommitStatus.BLOCKED, blocker=blocker)

        message = _commit_message(request)
        observation = self._committer.commit(
            GitSliceCommitRequest(
                repository_root=request.repository_root,
                starting_head=request.candidate.starting_head,
                paths=request.candidate.paths,
                plan_path=request.plan_path,
                expected_plan_content=request.current_plan_content,
                updated_plan_content=request.updated_plan_content,
                message=message,
            )
        )
        if not observation.committed:
            blocker = SliceCommitBlocker(
                code="slice_commit_failed",
                summary="Git did not create the authorized slice commit",
                evidence=observation.error,
            )
            return SliceCommitResult(
                status=SliceCommitStatus.RECOVERY_REQUIRED,
                recovery=SliceCommitRecovery(
                    task_id=request.candidate.task_id,
                    slice_id=request.candidate.slice_id,
                    slice_start_commit=request.candidate.starting_head,
                    paths=request.candidate.paths,
                    blocker=blocker,
                ),
                blocker=blocker,
            )
        verification = _verification_blocker(
            request,
            observation.commit,
            observation.committed_paths,
            observation.commit_message,
        )
        if verification is not None:
            return SliceCommitResult(status=SliceCommitStatus.BLOCKED, commit=observation.commit, blocker=verification)
        return SliceCommitResult(status=SliceCommitStatus.COMMITTED, commit=observation.commit)


def _progress_blocker(  # noqa: PLR0911 - Each fail-closed progress invariant has distinct evidence.
    request: SliceCommitRequest,
    current: PlanArtifactEvidence | None,
    updated: PlanArtifactEvidence | None,
    current_error: str | None,
    updated_error: str | None,
) -> SliceCommitBlocker | None:
    if current is None or updated is None:
        return SliceCommitBlocker(
            "slice_progress_invalid",
            "current and updated plan progress must both pass strict artifact validation",
            current_error or updated_error,
        )
    candidate = request.candidate
    stable_identity = (candidate.work_id, candidate.material_digest)
    if (current.work_id, current.material_digest) != stable_identity or (
        updated.work_id,
        updated.material_digest,
    ) != stable_identity:
        return SliceCommitBlocker(
            "slice_progress_diverged",
            "progress update changed approved work or material identity",
        )
    if (
        updated.specification_path != current.specification_path
        or updated.specification_digest != current.specification_digest
    ):
        return SliceCommitBlocker("slice_progress_diverged", "progress update changed specification identity")
    if candidate.kind is SliceKind.REMEDIATION:
        transition_error = _remediation_transition_error(candidate.slice_id, current, updated)
        if transition_error is not None:
            return transition_error
    elif updated.completed_slice_ids != (*current.completed_slice_ids, candidate.slice_id):
        return SliceCommitBlocker(
            "slice_completion_transition_invalid",
            "progress update must append exactly the committed slice once",
        )
    if updated.current_task is not None or updated.current_slice is not None or updated.slice_start_commit is not None:
        return SliceCommitBlocker(
            "slice_completion_still_active",
            "completed slice progress must clear active slice fields",
        )
    if updated.partial_slice_paths:
        return SliceCommitBlocker("slice_completion_still_partial", "completed slice progress must clear partial paths")
    return None


def _remediation_transition_error(
    finding_id: str,
    current: PlanArtifactEvidence,
    updated: PlanArtifactEvidence,
) -> SliceCommitBlocker | None:
    if updated.completed_slice_ids != current.completed_slice_ids:
        return SliceCommitBlocker("remediation_progress_diverged", "remediation must not change completed plan slices")
    current_records = {record.finding_id: record for record in current.remediation_records}
    updated_records = {record.finding_id: record for record in updated.remediation_records}
    if set(current_records) != set(updated_records) or finding_id not in current_records:
        return SliceCommitBlocker(
            "remediation_transition_invalid",
            "remediation must update exactly one existing finding",
        )
    before = current_records[finding_id]
    after = updated_records[finding_id]
    if (
        before.status != "pending"
        or before.attempt_count != 0
        or after.status != "completed"
        or after.attempt_count != 1
    ):
        return SliceCommitBlocker(
            "remediation_transition_invalid",
            "remediation must consume its single permitted attempt",
        )
    if (before.finding_id, before.requirement, before.path_scope, before.correction, before.verification) != (
        after.finding_id,
        after.requirement,
        after.path_scope,
        after.correction,
        after.verification,
    ):
        return SliceCommitBlocker(
            "remediation_progress_diverged",
            "remediation changed its approved correction boundary",
        )
    unchanged = tuple(record for record in current.remediation_records if record.finding_id != finding_id)
    updated_unchanged = tuple(record for record in updated.remediation_records if record.finding_id != finding_id)
    if unchanged != updated_unchanged:
        return SliceCommitBlocker("remediation_progress_diverged", "remediation changed another finding record")
    return None


def _commit_message(request: SliceCommitRequest) -> str:
    candidate = request.candidate
    action = "remediate" if candidate.kind.value == "remediation" else "complete"
    commit_type = "fix" if candidate.kind.value == "remediation" else request.commit_type
    subject = f"{commit_type}(sdlc): {action} {candidate.slice_id} {request.short_description.strip()}"
    return "\n".join(
        (
            subject,
            "",
            f"Cline-SDLC-Work-ID: {candidate.work_id}",
            f"Cline-SDLC-Slice-ID: {candidate.slice_id}",
            f"Cline-SDLC-Slice-Kind: {candidate.kind.value}",
            f"Cline-SDLC-Material-Digest: {candidate.material_digest}",
        )
    )


def _verification_blocker(
    request: SliceCommitRequest,
    commit: str | None,
    committed_paths: tuple[str, ...],
    message: str | None,
) -> SliceCommitBlocker | None:
    try:
        require_commit_hash(commit or "")
    except ValueError as err:
        return SliceCommitBlocker("slice_commit_not_verified", "created commit hash is invalid", str(err))
    if tuple(sorted(committed_paths)) != tuple(sorted(request.candidate.paths)):
        return SliceCommitBlocker(
            "slice_commit_paths_mismatch",
            "created commit does not contain exactly the candidate paths",
        )
    expected = _commit_message(request)
    if message is None or message.strip() != expected:
        return SliceCommitBlocker(
            "slice_commit_trailers_mismatch",
            "created commit message or trailers do not match authorization",
        )
    return None
