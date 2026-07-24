"""Outbound port for repository inspection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.repository import (
        RepositoryInspectionRequest,
        RepositoryInspectionResult,
    )


class GitRepositoryInspectorPort(Protocol):
    """Inspect repository state without making repository changes."""

    def inspect(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        """Return a typed repository snapshot or actionable blockers."""
