"""Outbound port for already-discovered artifact location conventions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import ArtifactLocationConvention


class ArtifactConventionProvider(Protocol):
    """Provide safe repository artifact conventions without executing repository code."""

    def discover_conventions(self) -> tuple[ArtifactLocationConvention, ...]:
        """Return discovered convention candidates for managed lifecycle artifacts."""
