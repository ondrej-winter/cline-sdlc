"""Tests for Cline capability and skill preflight."""

from dataclasses import dataclass

import pytest

from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
from cline_sdlc.features.cline_execution.application.dtos.preflight import (
    ClinePreflightRequest,
    ClinePreflightStatus,
)
from cline_sdlc.features.cline_execution.application.use_cases.preflight import PreflightClineCapabilities
from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    CapabilityObservation,
    CapabilityStatus,
    ClineCapabilityReport,
)


@dataclass
class RecordingCapabilityProbe:
    """Fake capability probe that records the preflight probe request."""

    report: ClineCapabilityReport
    request: CapabilityProbeRequest | None = None

    def probe(self, request: CapabilityProbeRequest) -> ClineCapabilityReport:
        self.request = request
        return self.report


def test_preflight_is_ready_when_critical_capabilities_are_proven() -> None:
    probe = RecordingCapabilityProbe(_report(_critical("required_skill:idea-refine", CapabilityStatus.PROVEN)))

    result = PreflightClineCapabilities(probe).execute(
        ClinePreflightRequest(command=("/opt/bin/cline",), required_skills=("idea-refine",))
    )

    assert result.status is ClinePreflightStatus.READY
    assert result.ready
    assert result.blockers == ()
    assert probe.request == CapabilityProbeRequest(command=("/opt/bin/cline",), required_skills=("idea-refine",))


@pytest.mark.parametrize(
    ("status", "expected_summary_fragment"),
    [
        (CapabilityStatus.MISSING, "missing"),
        (CapabilityStatus.UNPROVEN, "unproven"),
    ],
)
def test_preflight_fails_closed_for_missing_or_unproven_required_skill(
    status: CapabilityStatus,
    expected_summary_fragment: str,
) -> None:
    probe = RecordingCapabilityProbe(_report(_critical("required_skill:idea-refine", status)))

    result = PreflightClineCapabilities(probe).execute(ClinePreflightRequest(required_skills=("idea-refine",)))

    assert result.status is ClinePreflightStatus.FAILED
    assert not result.ready
    assert len(result.blockers) == 1
    assert result.blockers[0].code == "cline_capability_required_skill:idea-refine"
    assert expected_summary_fragment in result.blockers[0].summary
    assert result.blockers[0].evidence == "observed evidence"


def test_preflight_ignores_supporting_advertisements_for_readiness() -> None:
    probe = RecordingCapabilityProbe(_report(_supporting("json_output", CapabilityStatus.ADVERTISED)))

    result = PreflightClineCapabilities(probe).execute(ClinePreflightRequest())

    assert result.status is ClinePreflightStatus.READY
    assert result.ready


def test_preflight_request_rejects_empty_command_and_skills() -> None:
    with pytest.raises(ValueError, match="command"):
        ClinePreflightRequest(command=())

    with pytest.raises(ValueError, match="arguments"):
        ClinePreflightRequest(command=("cline", ""))

    with pytest.raises(ValueError, match="skills"):
        ClinePreflightRequest(required_skills=(" ",))


def _report(*observations: CapabilityObservation) -> ClineCapabilityReport:
    return ClineCapabilityReport(
        executable="cline",
        version="3.0.46",
        observations=observations,
        limitations=tuple(observation.evidence for observation in observations if not observation.is_satisfied),
    )


def _critical(name: str, status: CapabilityStatus) -> CapabilityObservation:
    return CapabilityObservation(
        name=name,
        status=status,
        criticality=CapabilityCriticality.CRITICAL,
        evidence="observed evidence",
    )


def _supporting(name: str, status: CapabilityStatus) -> CapabilityObservation:
    return CapabilityObservation(
        name=name,
        status=status,
        criticality=CapabilityCriticality.SUPPORTING,
        evidence="advertised evidence",
    )
