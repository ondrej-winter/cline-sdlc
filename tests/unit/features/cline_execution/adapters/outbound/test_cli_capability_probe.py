"""Tests for the subprocess-backed Cline capability probe."""

import sys
from pathlib import Path

from cline_sdlc.features.cline_execution.adapters.outbound.cli_capability_probe import SubprocessClineCapabilityProbe
from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
from cline_sdlc.features.cline_execution.domain.capability import CapabilityStatus

UNPROVEN_CRITICAL_CAPABILITY_COUNT = 3


def test_probe_records_advertised_supporting_capabilities_and_unproven_critical_contracts() -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(CapabilityProbeRequest(command=(sys.executable, str(fake_cline))))

    statuses = {observation.name: observation.status for observation in report.observations}
    assert report.version == "3.0.46"
    assert statuses["json_output"] is CapabilityStatus.ADVERTISED
    assert statuses["finite_timeout_option"] is CapabilityStatus.ADVERTISED
    assert statuses["isolated_data_directory"] is CapabilityStatus.ADVERTISED
    assert statuses["hook_injection_directory"] is CapabilityStatus.ADVERTISED
    assert statuses["explicit_working_directory"] is CapabilityStatus.ADVERTISED
    assert statuses["skill_management_command"] is CapabilityStatus.ADVERTISED
    assert statuses["exactly_one_machine_detectable_terminal_outcome"] is CapabilityStatus.UNPROVEN
    assert statuses["pre_execution_permission_mediation"] is CapabilityStatus.UNPROVEN
    assert statuses["interruption_recovery_observability"] is CapabilityStatus.UNPROVEN
    assert not report.critical_capabilities_proven
    assert len(report.limitations) == UNPROVEN_CRITICAL_CAPABILITY_COUNT


def test_probe_records_required_skill_availability() -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(command=(sys.executable, str(fake_cline)), required_skills=("idea-refine",))
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["required_skill:idea-refine"] is CapabilityStatus.PROVEN


def test_probe_records_missing_required_skill() -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(command=(sys.executable, str(fake_cline)), required_skills=("missing-skill",))
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["required_skill:missing-skill"] is CapabilityStatus.MISSING
    assert not report.critical_capabilities_proven


def test_supervised_session_probe_can_prove_critical_contracts(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline)),
            supervised_session_probe=True,
            repository_root=tmp_path,
            data_directory=tmp_path / "data",
            hooks_directory=tmp_path / "hooks",
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["exactly_one_machine_detectable_terminal_outcome"] is CapabilityStatus.PROVEN
    assert statuses["pre_execution_permission_mediation"] is CapabilityStatus.PROVEN
    assert statuses["interruption_recovery_observability"] is CapabilityStatus.PROVEN
    assert report.critical_capabilities_proven


def test_supervised_session_probe_extracts_wrapped_message_outcome(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline), "--fake-session-scenario", "wrapped-message-outcome"),
            supervised_session_probe=True,
            repository_root=tmp_path,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["exactly_one_machine_detectable_terminal_outcome"] is CapabilityStatus.PROVEN
    assert statuses["pre_execution_permission_mediation"] is CapabilityStatus.PROVEN
    assert statuses["interruption_recovery_observability"] is CapabilityStatus.PROVEN


def test_supervised_session_probe_extracts_wrapped_content_text_outcome(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline), "--fake-session-scenario", "wrapped-content-text-outcome"),
            supervised_session_probe=True,
            repository_root=tmp_path,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["exactly_one_machine_detectable_terminal_outcome"] is CapabilityStatus.PROVEN
    assert statuses["pre_execution_permission_mediation"] is CapabilityStatus.PROVEN
    assert statuses["interruption_recovery_observability"] is CapabilityStatus.PROVEN


def test_supervised_session_probe_fails_closed_for_duplicate_outcomes(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline), "--fake-session-scenario", "duplicate-outcome"),
            supervised_session_probe=True,
            repository_root=tmp_path,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["exactly_one_machine_detectable_terminal_outcome"] is CapabilityStatus.UNPROVEN
    assert not report.critical_capabilities_proven


def test_supervised_session_probe_records_bounded_timeout(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline), "--fake-session-scenario", "timeout"),
            supervised_session_probe=True,
            repository_root=tmp_path,
            session_timeout_seconds=0.1,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["exactly_one_machine_detectable_terminal_outcome"] is CapabilityStatus.UNPROVEN
    assert statuses["interruption_recovery_observability"] is CapabilityStatus.PROVEN
    assert not report.critical_capabilities_proven
