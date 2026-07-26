"""Independently reconcile one executed slice without staging or committing."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import SliceExecutionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    PartialSliceRecovery,
    SliceCommitCandidate,
    SliceReconciliationBlocker,
    SliceReconciliationRequest,
    SliceReconciliationResult,
    SliceReconciliationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationEvidenceStatus,
    ValidationScope,
)

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositorySnapshot
    from cline_sdlc.features.repository_coordination.application.ports.git import GitRepositoryInspectorPort


class ReconcileSlice:
    """Require execution, policy, validation, approval, and Git evidence to agree."""

    def __init__(self, repository_inspector: GitRepositoryInspectorPort) -> None:
        self._repository_inspector = repository_inspector

    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
        """Return exact commit eligibility or attributable uncommitted recovery state."""
        inspection = self._repository_inspector.inspect(request.repository_request)
        if not inspection.ready or inspection.snapshot is None:
            evidence = "; ".join(blocker.code for blocker in inspection.blockers) or None
            return _blocked(
                "repository_observation_failed",
                "repository state could not be observed unambiguously after slice execution",
                evidence,
            )
        return self._reconcile_snapshot(request, inspection.snapshot)

    def _reconcile_snapshot(  # noqa: PLR0911 - Each fail-closed boundary returns its own evidence.
        self,
        request: SliceReconciliationRequest,
        snapshot: RepositorySnapshot,
    ) -> SliceReconciliationResult:
        """Reconcile one unambiguous post-session repository snapshot."""
        failure = _approval_failure(request)
        if failure is not None:
            return _failed(request, snapshot, failure)
        if snapshot.head_commit != request.slice_start_commit:
            return _failed(
                request,
                snapshot,
                SliceReconciliationBlocker(
                    "slice_head_moved",
                    "repository HEAD moved after the slice started",
                    snapshot.head_commit,
                ),
            )
        if request.execution.status is not SliceExecutionStatus.COMPLETED:
            execution_blocker = request.execution.blocker
            return _failed(
                request,
                snapshot,
                SliceReconciliationBlocker(
                    execution_blocker.code if execution_blocker is not None else "slice_execution_incomplete",
                    execution_blocker.summary if execution_blocker is not None else "slice execution did not complete",
                ),
            )

        path_evidence = _reconcile_paths(request, snapshot)
        if isinstance(path_evidence, SliceReconciliationBlocker):
            return _failed(request, snapshot, path_evidence)
        if not path_evidence:
            return _blocked("slice_has_no_changes", "completed slice execution produced no commit-eligible changes")

        denied = next((decision for decision in request.execution.operation_decisions if not decision.is_allowed), None)
        if denied is not None:
            return _failed(
                request,
                snapshot,
                SliceReconciliationBlocker(
                    "prohibited_slice_operation",
                    "slice execution includes an operation that was not authorized",
                    denied.proposed_operation,
                ),
            )
        if not request.execution.validation_evidence or any(
            evidence.scope is not ValidationScope.FOCUSED
            or evidence.status is not ValidationEvidenceStatus.PASSED
            or evidence.exit_code != 0
            for evidence in request.execution.validation_evidence
        ):
            return _failed(
                request,
                snapshot,
                SliceReconciliationBlocker(
                    "focused_validation_not_verified",
                    "slice commit eligibility requires independently passing focused validation evidence",
                ),
            )

        return SliceReconciliationResult(
            status=SliceReconciliationStatus.COMMIT_CANDIDATE,
            commit_candidate=SliceCommitCandidate(
                work_id=request.work_id,
                task_id=request.selection.task_id,
                slice_id=request.selection.slice_id,
                starting_head=request.slice_start_commit,
                material_digest=request.material_digest,
                paths=path_evidence,
                validation_evidence=request.execution.validation_evidence,
                operation_decisions=request.execution.operation_decisions,
                kind=request.kind,
            ),
        )


def _approval_failure(request: SliceReconciliationRequest) -> SliceReconciliationBlocker | None:
    if request.specification_digest != request.approval.specification_digest:
        return SliceReconciliationBlocker(
            "specification_digest_diverged",
            "specification digest no longer matches invocation approval",
        )
    if request.material_digest != request.approval.material_digest:
        return SliceReconciliationBlocker(
            "material_digest_diverged",
            "plan material digest no longer matches invocation approval",
        )
    return None


def _reported_paths(request: SliceReconciliationRequest) -> tuple[str, ...]:
    paths: list[str] = []
    for session in request.execution.session_attempts:
        if session.terminal_session_result is None:
            continue
        for outcome in session.terminal_session_result.terminal_outcomes:
            paths.extend(outcome.changed_paths)
    return _normalized_paths(tuple(dict.fromkeys(paths)))


def _reconcile_paths(
    request: SliceReconciliationRequest,
    snapshot: RepositorySnapshot,
) -> tuple[str, ...] | SliceReconciliationBlocker:
    try:
        observed_paths = _normalized_paths(snapshot.dirty_paths)
        reported_paths = _reported_paths(request)
        execution_paths = _normalized_paths(request.execution.changed_paths)
    except ValueError as err:
        return SliceReconciliationBlocker(
            "slice_changed_path_invalid",
            "slice reconciliation observed an unsafe repository-relative path",
            str(err),
        )
    if reported_paths != observed_paths or execution_paths != observed_paths:
        return SliceReconciliationBlocker(
            "slice_changed_paths_mismatch",
            "reported and independently observed changed paths must agree exactly",
            _path_comparison(reported_paths, observed_paths),
        )
    unexpected_paths = tuple(path for path in observed_paths if path not in request.expected_paths)
    if unexpected_paths:
        return SliceReconciliationBlocker(
            "slice_path_out_of_scope",
            "observed changes exceed the accepted slice path scope",
            ", ".join(unexpected_paths),
        )
    return observed_paths


def _normalized_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        if (
            not raw_path.strip()
            or raw_path.startswith(("/", "../"))
            or "\\" in raw_path
            or ".." in path.parts
            or path.as_posix() != raw_path
        ):
            message = "changed paths must be normalized repository-relative POSIX paths"
            raise ValueError(message)
        normalized.append(raw_path)
    return tuple(sorted(set(normalized)))


def _path_comparison(reported: tuple[str, ...], observed: tuple[str, ...]) -> str:
    return f"reported={','.join(reported) or '<none>'}; observed={','.join(observed) or '<none>'}"


def _failed(
    request: SliceReconciliationRequest,
    snapshot: RepositorySnapshot,
    blocker: SliceReconciliationBlocker,
) -> SliceReconciliationResult:
    try:
        paths = _normalized_paths(snapshot.dirty_paths)
    except ValueError:
        paths = ()
    if not paths:
        return SliceReconciliationResult(status=SliceReconciliationStatus.BLOCKED, blocker=blocker)
    return SliceReconciliationResult(
        status=SliceReconciliationStatus.RECOVERY_REQUIRED,
        recovery=PartialSliceRecovery(
            task_id=request.selection.task_id,
            slice_id=request.selection.slice_id,
            slice_start_commit=request.slice_start_commit,
            paths=paths,
            blocker=blocker,
        ),
        blocker=blocker,
    )


def _blocked(code: str, summary: str, evidence: str | None = None) -> SliceReconciliationResult:
    return SliceReconciliationResult(
        status=SliceReconciliationStatus.BLOCKED,
        blocker=SliceReconciliationBlocker(code=code, summary=summary, evidence=evidence),
    )
