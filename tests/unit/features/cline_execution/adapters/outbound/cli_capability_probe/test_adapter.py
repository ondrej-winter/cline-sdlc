"""Tests for the subprocess-backed Cline capability probe."""

import sys
from pathlib import Path

from cline_sdlc.features.cline_execution.adapters.outbound.cli_capability_probe import SubprocessClineCapabilityProbe
from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
from cline_sdlc.features.cline_execution.domain.capability import CapabilityStatus

UNPROVEN_CRITICAL_CAPABILITY_COUNT = 0


def test_probe_records_advertised_supporting_capabilities_and_unproven_sidecar_contracts() -> None:
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
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.UNPROVEN
    assert statuses["cline_authored_interruption_recovery_metadata"] is CapabilityStatus.UNPROVEN
    assert report.critical_capabilities_proven
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


def test_probe_records_repository_local_required_skill(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")
    skill_file = tmp_path / ".agents" / "skills" / "checkpoint-blocking-skill" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("---\nname: checkpoint-blocking-skill\n---\n", encoding="utf-8")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline)),
            required_skills=("checkpoint-blocking-skill",),
            repository_root=tmp_path,
        )
    )

    observations = {observation.name: observation for observation in report.observations}
    assert observations["required_skill:checkpoint-blocking-skill"].status is CapabilityStatus.PROVEN
    assert "Repository-local skill file" in observations["required_skill:checkpoint-blocking-skill"].evidence


def test_probe_does_not_escape_repository_local_skill_directory(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")
    escaped_skill_file = tmp_path / "escaped-skill" / "SKILL.md"
    escaped_skill_file.parent.mkdir()
    escaped_skill_file.write_text("---\nname: escaped-skill\n---\n", encoding="utf-8")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline)),
            required_skills=("../escaped-skill",),
            repository_root=tmp_path,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["required_skill:../escaped-skill"] is CapabilityStatus.MISSING


def test_probe_fails_closed_for_missing_executable() -> None:
    report = SubprocessClineCapabilityProbe().probe(CapabilityProbeRequest(command=("/definitely/missing/cline",)))

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["json_output"] is CapabilityStatus.MISSING
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.UNPROVEN
    assert report.critical_capabilities_proven


def test_supervised_session_probe_can_prove_status_sidecar_contract(tmp_path: Path) -> None:
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
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.PROVEN
    assert statuses["cline_authored_interruption_recovery_metadata"] is CapabilityStatus.PROVEN
    assert report.critical_capabilities_proven


def test_supervised_session_probe_fails_closed_for_missing_sidecar(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline), "--fake-session-scenario", "missing-sidecar"),
            supervised_session_probe=True,
            repository_root=tmp_path,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.UNPROVEN
    assert statuses["cline_authored_interruption_recovery_metadata"] is CapabilityStatus.UNPROVEN


def test_supervised_session_probe_fails_closed_for_malformed_sidecar(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline), "--fake-session-scenario", "malformed-sidecar"),
            supervised_session_probe=True,
            repository_root=tmp_path,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.UNPROVEN
    assert statuses["cline_authored_interruption_recovery_metadata"] is CapabilityStatus.UNPROVEN


def test_supervised_session_probe_reports_missing_recovery_metadata(tmp_path: Path) -> None:
    fake_cline = Path(__file__).with_name("fake_helping_cline.py")

    report = SubprocessClineCapabilityProbe().probe(
        CapabilityProbeRequest(
            command=(sys.executable, str(fake_cline), "--fake-session-scenario", "missing-interruption-recovery"),
            supervised_session_probe=True,
            repository_root=tmp_path,
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.PROVEN
    assert statuses["cline_authored_interruption_recovery_metadata"] is CapabilityStatus.UNPROVEN
    assert report.critical_capabilities_proven


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
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.UNPROVEN
    assert statuses["cline_authored_interruption_recovery_metadata"] is CapabilityStatus.PROVEN
    assert report.critical_capabilities_proven
