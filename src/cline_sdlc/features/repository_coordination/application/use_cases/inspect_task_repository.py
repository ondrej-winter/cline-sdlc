"""Use case for staged repository task inspection."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from cline_sdlc.features.repository_coordination.application.dtos.task_repository import (
    TaskRepositoryInspectionBlocker,
    TaskRepositoryInspectionResult,
    TaskRepositoryInspectionStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.task_repository import (
        StagedChangeSet,
        TaskRepositoryInspectionRequest,
    )
    from cline_sdlc.features.repository_coordination.application.ports.git import GitTaskRepositoryInspectorPort


class InspectTaskRepository:
    """Inspect already staged repository changes before repository task execution."""

    def __init__(self, inspector: GitTaskRepositoryInspectorPort) -> None:
        self._inspector = inspector

    def execute(self, request: TaskRepositoryInspectionRequest) -> TaskRepositoryInspectionResult:
        """Return staged repository observations from the configured inspector port."""
        result = self._inspector.inspect_task_repository(request)
        if not result.ready:
            return result
        return _validated_ready_result(request, result)


def _validated_ready_result(
    request: TaskRepositoryInspectionRequest,
    result: TaskRepositoryInspectionResult,
) -> TaskRepositoryInspectionResult:
    change_set = result.change_set
    if change_set is None:
        return _failed("staged_change_set_unavailable", "ready staged inspection must include a change set")
    blocker = _change_set_blocker(change_set)
    if blocker is not None:
        return blocker

    authorized_paths = {_normalized_path(path) for path in request.authorized_paths}
    return _authorized_scope_result(authorized_paths, change_set, result)


def _change_set_blocker(change_set: StagedChangeSet) -> TaskRepositoryInspectionResult | None:
    required_blocker = _required_change_set_blocker(change_set)
    if required_blocker is not None:
        return required_blocker
    if change_set.operation_states:
        return _failed(
            "git_operation_in_progress",
            "repository has an unresolved Git operation in progress",
            evidence=", ".join(change_set.operation_states),
        )
    if not change_set.has_staged_changes:
        return _failed("no_staged_changes", "repository task requires at least one staged path")
    for staged_path in change_set.staged_paths:
        if _unsafe_repository_path(staged_path):
            return _failed(
                "unsafe_staged_path",
                "staged paths must be safe repository-relative paths",
                path=staged_path,
            )
    return None


def _required_change_set_blocker(change_set: StagedChangeSet) -> TaskRepositoryInspectionResult | None:
    if not change_set.repository_root:
        return _failed("git_repository_unavailable", "ready staged inspection must identify a Git repository root")
    if not change_set.head_commit:
        return _failed("git_head_unavailable", "ready staged inspection must identify the current HEAD commit")
    if not change_set.read_only:
        return _failed(
            "staged_inspection_mutated_repository",
            "staged repository inspection must be read-only and must not mutate Git state",
        )
    return None


def _authorized_scope_result(
    authorized_paths: set[str],
    change_set: StagedChangeSet,
    result: TaskRepositoryInspectionResult,
) -> TaskRepositoryInspectionResult:
    if authorized_paths:
        for staged_path in change_set.staged_paths:
            if staged_path not in authorized_paths:
                return _failed(
                    "staged_paths_outside_authorized_scope",
                    "staged changes include paths outside the authorized scope",
                    path=staged_path,
                )
    return result


def _failed(
    code: str,
    summary: str,
    *,
    path: str | None = None,
    evidence: str | None = None,
) -> TaskRepositoryInspectionResult:
    return TaskRepositoryInspectionResult(
        status=TaskRepositoryInspectionStatus.FAILED,
        blockers=(TaskRepositoryInspectionBlocker(code=code, summary=summary, path=path, evidence=evidence),),
    )


def _normalized_path(path: object) -> str:
    return str(path).replace("\\", "/")


def _unsafe_repository_path(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path:
        return True
    parts = PurePosixPath(path).parts
    return ".." in parts
