"""Outbound port for repository inspection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.repository import (
        RepositoryInspectionRequest,
        RepositoryInspectionResult,
    )
    from cline_sdlc.features.repository_coordination.application.dtos.task_repository import (
        TaskRepositoryInspectionRequest,
        TaskRepositoryInspectionResult,
    )


class GitRepositoryInspectorPort(Protocol):
    """Inspect repository state without making repository changes."""

    def inspect(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        """Return a typed repository snapshot or actionable blockers."""

    def inspect_task_repository(self, request: TaskRepositoryInspectionRequest) -> TaskRepositoryInspectionResult:
        """Return staged task repository evidence or actionable blockers."""
