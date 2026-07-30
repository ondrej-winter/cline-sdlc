"""Integration tests for the adapter-owned Cline SDK Node runner proof."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk.adapter import ClineSdkSessionRunner
from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk.protocol import parse_runner_output
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest, ClineSessionTerminalStatus
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole

RUNNER_DIRECTORY = Path("src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner")


def test_node_runner_reports_missing_sdk_configuration_as_structured_failure() -> None:
    node_executable = shutil.which("node")
    if node_executable is None:
        message = "Node.js is required for the Cline SDK runner integration test."
        raise AssertionError(message)
    request = {
        "schemaVersion": 1,
        "role": "implementation",
        "instructions": "Implement a safe test slice.",
        "outcomeContract": "Return one terminal result.",
        "timeoutSeconds": 5,
        "workingDirectory": "/repo",
        "requiredSkills": [],
        "artifactContext": [],
        "executionMode": "read_only",
        "safeContext": ["slice=task-4a"],
    }

    completed = subprocess.run(  # noqa: S603 - test executes the trusted adapter-local Node runner.
        [node_executable, "runner.mjs"],
        cwd=RUNNER_DIRECTORY,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
        env={},
    )

    result = parse_runner_output(completed.stdout, exit_code=completed.returncode, stderr=completed.stderr)

    assert completed.returncode == 1
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.FAILED
    assert result.blockers[0].code == "missing_sdk_configuration"
    assert "CLINE_SDK_API_KEY" not in completed.stdout


def test_python_adapter_invokes_real_node_runner_as_structured_boundary() -> None:
    node_executable = shutil.which("node")
    if node_executable is None:
        message = "Node.js is required for the Cline SDK adapter integration test."
        raise AssertionError(message)
    request = ClineSessionRequest(
        command=("node", "runner.mjs"),
        working_directory=Path("/repo"),
        timeout_seconds=5,
        session_role=SessionRole.IMPLEMENTATION,
        instructions="Implement a safe test slice.",
        outcome_contract="Return one terminal result.",
        safe_context=("slice=task-5",),
    )

    result = ClineSdkSessionRunner(
        node_command=(node_executable,),
        runner_directory=RUNNER_DIRECTORY,
        environment={},
    ).run(request)

    assert result.process_status.value == "exited"
    assert result.exit_code == 1
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.FAILED
    assert result.blockers[0].code == "missing_sdk_configuration"
    assert "CLINE_SDK_API_KEY" not in result.stdout
