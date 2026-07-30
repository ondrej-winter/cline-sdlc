"""Use case for Cline capability and skill preflight."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
from cline_sdlc.features.cline_execution.application.dtos.preflight import (
    ClinePreflightBlocker,
    ClinePreflightResult,
    ClinePreflightStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
    from cline_sdlc.features.cline_execution.application.ports.capability_probe import ClineCapabilityProbePort
    from cline_sdlc.features.cline_execution.domain.capability import CapabilityObservation, ClineCapabilityReport


class PreflightClineCapabilities:
    """Verify Cline executable capabilities before any lifecycle stage starts."""

    def __init__(self, probe: ClineCapabilityProbePort) -> None:
        self._probe = probe

    def execute(self, request: ClinePreflightRequest) -> ClinePreflightResult:
        """Return legacy CLI compatibility blockers for the requested command."""
        report = self._probe.probe(
            CapabilityProbeRequest(command=request.command, required_skills=request.required_skills)
        )
        blockers = _blockers_from_report(report)
        return ClinePreflightResult(
            status=ClinePreflightStatus.READY if not blockers else ClinePreflightStatus.FAILED,
            executable=report.executable,
            version=report.version,
            blockers=blockers,
        )


def _blockers_from_report(report: ClineCapabilityReport) -> tuple[ClinePreflightBlocker, ...]:
    return tuple(
        _blocker_from_observation(observation)
        for observation in report.blocking_observations
        if observation.name.startswith("required_skill:")
    )


def _blocker_from_observation(observation: CapabilityObservation) -> ClinePreflightBlocker:
    return ClinePreflightBlocker(
        code=f"cline_capability_{observation.name}",
        summary=f"Cline capability {observation.name!r} is {observation.status.value}.",
        evidence=observation.evidence,
    )
