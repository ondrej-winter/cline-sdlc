"""Tests for the Cline SDK adapter runtime probe."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk.runtime_probe import (
    ClineSdkRuntimeProbe,
    CommandResult,
)
from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import (
    SdkRuntimeCapability,
    SdkRuntimeCapabilitySource,
    SdkRuntimeCapabilityStatus,
    SdkRuntimePreflightRequest,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pytest


@dataclass
class RecordingCommandRunner:
    """Fake command runner that records SDK runtime probe commands."""

    results: Iterator[CommandResult]
    commands: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)

    def run(self, command: tuple[str, ...], *, cwd: str | None = None) -> CommandResult:
        self.commands.append((command, cwd))
        return next(self.results)


def test_probe_reports_ready_when_node_version_and_sdk_resolution_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/local/bin/{command}")
    runner = RecordingCommandRunner(
        iter(
            (
                CommandResult(exit_code=0, stdout="v22.11.0\n"),
                CommandResult(exit_code=0, stdout="file:///runner/node_modules/@cline/sdk/index.js\n"),
            )
        )
    )

    observation = ClineSdkRuntimeProbe(runner).inspect(SdkRuntimePreflightRequest())

    assert observation.node_executable == "/usr/local/bin/node"
    assert observation.node_version == "v22.11.0"
    assert observation.sdk_resolved
    assert observation.blockers == ()
    capabilities = {evidence.capability: evidence for evidence in observation.capabilities}
    assert capabilities[SdkRuntimeCapability.NODE_RUNTIME].status is SdkRuntimeCapabilityStatus.PROVEN
    assert capabilities[SdkRuntimeCapability.SDK_PACKAGE].status is SdkRuntimeCapabilityStatus.PROVEN
    assert capabilities[SdkRuntimeCapability.AGENT_RUN].source is SdkRuntimeCapabilitySource.AGENT_SMOKE
    assert capabilities[SdkRuntimeCapability.CLINECORE_SESSION].source is SdkRuntimeCapabilitySource.CLINECORE_SMOKE
    assert capabilities[SdkRuntimeCapability.TOOL_POLICY_COVERAGE].status is SdkRuntimeCapabilityStatus.PROVEN
    assert capabilities[SdkRuntimeCapability.PERMISSION_APPROVAL].status is SdkRuntimeCapabilityStatus.UNPROVEN
    assert capabilities[SdkRuntimeCapability.PLAN_ACT_OBSERVATION].status is SdkRuntimeCapabilityStatus.UNPROVEN
    assert capabilities[SdkRuntimeCapability.ACT_AUTHORIZATION].status is SdkRuntimeCapabilityStatus.UNPROVEN
    assert capabilities[SdkRuntimeCapability.CLI_PROBE_EXCLUDED].status is SdkRuntimeCapabilityStatus.PROVEN
    assert runner.commands[0] == (("node", "--version"), None)
    assert runner.commands[1][0] == (
        "node",
        "--input-type=module",
        "--eval",
        "import.meta.resolve('@cline/sdk')",
    )
    package_resolution_cwd = runner.commands[1][1]
    assert package_resolution_cwd is not None
    assert package_resolution_cwd.endswith("cline_sdk/node_runner")


def test_probe_reports_missing_node_without_running_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    runner = RecordingCommandRunner(iter(()))

    observation = ClineSdkRuntimeProbe(runner).inspect(SdkRuntimePreflightRequest())

    assert observation.node_executable is None
    assert observation.blockers[0].code == "node_missing"
    assert runner.commands == []


def test_probe_reports_unsupported_node_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/local/bin/{command}")
    runner = RecordingCommandRunner(iter((CommandResult(exit_code=0, stdout="v20.19.0\n"),)))

    observation = ClineSdkRuntimeProbe(runner).inspect(SdkRuntimePreflightRequest())

    assert observation.node_version == "v20.19.0"
    assert observation.blockers[0].code == "node_version_unsupported"
    assert len(runner.commands) == 1


def test_probe_reports_missing_sdk_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/local/bin/{command}")
    runner = RecordingCommandRunner(
        iter((CommandResult(exit_code=0, stdout="v22.11.0\n"), CommandResult(exit_code=1, stderr="not found")))
    )

    observation = ClineSdkRuntimeProbe(runner).inspect(SdkRuntimePreflightRequest())

    assert not observation.sdk_resolved
    assert observation.blockers[0].code == "cline_sdk_missing"
