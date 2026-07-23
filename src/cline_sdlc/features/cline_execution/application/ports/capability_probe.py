"""Outbound port for Cline CLI capability probing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
    from cline_sdlc.features.cline_execution.domain.capability import ClineCapabilityReport


class ClineCapabilityProbePort(Protocol):
    """Probe a Cline CLI executable without starting lifecycle work."""

    def probe(self, request: CapabilityProbeRequest) -> ClineCapabilityReport:
        """Return capability evidence for the requested Cline command."""
