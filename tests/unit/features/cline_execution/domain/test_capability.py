"""Tests for Cline capability evidence values."""

from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    CapabilityObservation,
    CapabilityStatus,
    ClineCapabilityReport,
)


def test_report_blocks_when_critical_capability_is_only_advertised() -> None:
    report = ClineCapabilityReport(
        executable="cline",
        version="3.0.46",
        observations=(
            CapabilityObservation(
                name="json_output",
                status=CapabilityStatus.ADVERTISED,
                criticality=CapabilityCriticality.SUPPORTING,
                evidence="help contains --json",
            ),
            CapabilityObservation(
                name="terminal_outcome",
                status=CapabilityStatus.UNPROVEN,
                criticality=CapabilityCriticality.CRITICAL,
                evidence="no proof yet",
            ),
        ),
        limitations=("no proof yet",),
    )

    assert not report.critical_capabilities_proven
    assert [observation.name for observation in report.blocking_observations] == ["terminal_outcome"]
    assert report.first_unproven_observation is report.observations[1]


def test_report_is_ready_when_all_critical_capabilities_are_proven() -> None:
    report = ClineCapabilityReport(
        executable="cline",
        version="3.0.46",
        observations=(
            CapabilityObservation(
                name="terminal_outcome",
                status=CapabilityStatus.PROVEN,
                criticality=CapabilityCriticality.CRITICAL,
                evidence="supervised proof passed",
            ),
        ),
        limitations=(),
    )

    assert report.critical_capabilities_proven
    assert report.blocking_observations == ()
    assert report.first_unproven_observation is None


def test_report_exposes_first_unproven_supporting_observation_after_critical_readiness() -> None:
    report = ClineCapabilityReport(
        executable="cline",
        version="3.0.47",
        observations=(
            CapabilityObservation(
                name="required_skill:idea-refine",
                status=CapabilityStatus.PROVEN,
                criticality=CapabilityCriticality.CRITICAL,
                evidence="skill exists",
            ),
            CapabilityObservation(
                name="json_output",
                status=CapabilityStatus.ADVERTISED,
                criticality=CapabilityCriticality.SUPPORTING,
                evidence="help contains --json",
            ),
            CapabilityObservation(
                name="supervised_session_writes_status_sidecar",
                status=CapabilityStatus.UNPROVEN,
                criticality=CapabilityCriticality.SUPPORTING,
                evidence="no live proof yet",
            ),
        ),
        limitations=(),
    )

    assert report.critical_capabilities_proven
    assert report.blocking_observations == ()
    assert report.first_unproven_observation is report.observations[2]
