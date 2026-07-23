"""Use case for the Phase 0 Cline CLI capability spike."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
    from cline_sdlc.features.cline_execution.application.ports.capability_probe import ClineCapabilityProbePort
    from cline_sdlc.features.cline_execution.domain.capability import ClineCapabilityReport


class ProveClineCliContracts:
    """Collect supervised evidence for the CLI-wrapper viability gate."""

    def __init__(self, probe: ClineCapabilityProbePort) -> None:
        self._probe = probe

    def execute(self, request: CapabilityProbeRequest) -> ClineCapabilityReport:
        """Probe the requested Cline CLI command and return typed evidence."""
        return self._probe.probe(request)
