"""Outbound port for legacy Cline CLI discovery probing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
    from cline_sdlc.features.cline_execution.domain.capability import ClineCapabilityReport


class ClineCapabilityProbePort(Protocol):
    """Probe a Cline CLI executable for compatibility, not SDK readiness."""

    def probe(self, request: CapabilityProbeRequest) -> ClineCapabilityReport:
        """Return legacy CLI discovery evidence for the requested command."""
