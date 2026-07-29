"""Use case for staged repository task inspection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.repository_coordination.application.dtos.task_repository import (
    TaskRepositoryInspectionBlocker,
    TaskRepositoryInspectionResult,
    TaskRepositoryInspectionStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.task_repository import (
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
    if not change_set.has_staged_changes:
        return _failed("no_staged_changes", "repository task requires at least one staged path")

    authorized_paths = {_normalized_path(path) for path in request.authorized_paths}
    if authorized_paths:
        for staged_path in change_set.staged_paths:
            if staged_path not in authorized_paths:
                return _failed(
                    "staged_paths_outside_authorized_scope",
                    "staged changes include paths outside the authorized scope",
                    path=staged_path,
                )
    return result


def _failed(code: str, summary: str, *, path: str | None = None) -> TaskRepositoryInspectionResult:
    return TaskRepositoryInspectionResult(
        status=TaskRepositoryInspectionStatus.FAILED,
        blockers=(TaskRepositoryInspectionBlocker(code=code, summary=summary, path=path),),
    )


def _normalized_path(path: object) -> str:
    return str(path).replace("\\", "/")
