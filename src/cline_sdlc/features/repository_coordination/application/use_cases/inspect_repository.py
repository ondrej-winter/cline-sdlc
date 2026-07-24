"""Use case for repository inspection preflight."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.repository import (
        RepositoryInspectionRequest,
        RepositoryInspectionResult,
    )
    from cline_sdlc.features.repository_coordination.application.ports.git import GitRepositoryInspectorPort


class InspectRepository:
    """Inspect Git repository state before lifecycle stage execution."""

    def __init__(self, inspector: GitRepositoryInspectorPort) -> None:
        self._inspector = inspector

    def execute(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        """Return repository observations from the configured inspector port."""
        return self._inspector.inspect(request)
