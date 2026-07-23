"""Tests for the Cline CLI capability proof use case."""

from dataclasses import dataclass

from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
from cline_sdlc.features.cline_execution.application.use_cases.prove_cli_contracts import ProveClineCliContracts
from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    CapabilityObservation,
    CapabilityStatus,
    ClineCapabilityReport,
)


@dataclass
class RecordingProbe:
    """Fake probe that records the request it received."""

    request: CapabilityProbeRequest | None = None

    def probe(self, request: CapabilityProbeRequest) -> ClineCapabilityReport:
        self.request = request
        return ClineCapabilityReport(
            executable="cline",
            version="3.0.46",
            observations=(
                CapabilityObservation(
                    name="terminal_outcome",
                    status=CapabilityStatus.UNPROVEN,
                    criticality=CapabilityCriticality.CRITICAL,
                    evidence="not exercised",
                ),
            ),
            limitations=("not exercised",),
        )


def test_delegates_capability_probe_request() -> None:
    probe = RecordingProbe()
    request = CapabilityProbeRequest(command=("/bin/cline",), required_skills=("idea-refine",))

    report = ProveClineCliContracts(probe).execute(request)

    assert probe.request == request
    assert report.version == "3.0.46"
    assert not report.critical_capabilities_proven
