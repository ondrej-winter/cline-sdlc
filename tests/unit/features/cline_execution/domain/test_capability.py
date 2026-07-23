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
