"""Tests for the legacy Cline CLI discovery probe script."""

from __future__ import annotations

import json

from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    CapabilityObservation,
    CapabilityStatus,
    ClineCapabilityReport,
)
from scripts import probe_cline_capabilities


def test_parser_description_quarantines_cli_probe_from_sdk_readiness() -> None:
    parser = probe_cline_capabilities.build_parser()

    assert parser.description is not None
    assert "legacy Cline CLI discovery probe" in parser.description
    assert "not SDK readiness evidence" in parser.description
    assert "ADR 0002" in parser.description


def test_report_json_marks_cli_probe_as_not_sdk_readiness_evidence() -> None:
    report = ClineCapabilityReport(
        executable="cline",
        version="3.0.47",
        observations=(
            CapabilityObservation(
                name="terminal_outcome",
                status=CapabilityStatus.PROVEN,
                criticality=CapabilityCriticality.CRITICAL,
                evidence="legacy CLI discovery passed",
            ),
        ),
        limitations=(),
    )

    payload = json.loads(probe_cline_capabilities.report_to_json(report))

    assert payload["critical_capabilities_proven"] is True
    assert payload["sdk_readiness_evidence"] is False
