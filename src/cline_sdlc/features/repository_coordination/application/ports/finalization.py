"""Outbound ports for plan finalization and complete-history verification."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
        FinalizationHistoryObservation,
        FinalizationHistoryRequest,
        GitFinalizationObservation,
        GitFinalizationRequest,
    )


class GitFinalizerPort(Protocol):
    """Create one explicit hook-enabled progress-only finalization commit."""

    def finalize(self, request: GitFinalizationRequest) -> GitFinalizationObservation:
        """Return commit evidence or leave explicit recovery state."""


class FinalizationHistoryReaderPort(Protocol):
    """Read reachable finalization claims without changing repository state."""

    def observe(self, request: FinalizationHistoryRequest) -> FinalizationHistoryObservation:
        """Return current state and all reachable finalization candidates."""
