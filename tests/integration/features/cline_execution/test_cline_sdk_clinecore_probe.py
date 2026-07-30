"""Integration tests for the adapter-owned ClineCore capability probe."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk.protocol import parse_runner_output
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionTerminalStatus

RUNNER_DIRECTORY = Path("src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner")


def test_clinecore_probe_reports_missing_sdk_configuration_as_structured_failure() -> None:
    node_executable = shutil.which("node")
    if node_executable is None:
        message = "Node.js is required for the ClineCore probe integration test."
        raise AssertionError(message)
    request = {
        "schemaVersion": 1,
        "role": "implementation",
        "instructions": "Probe ClineCore safely.",
        "outcomeContract": "Return one terminal result.",
        "timeoutSeconds": 5,
        "workingDirectory": "/repo",
        "requiredSkills": [],
        "artifactContext": [],
        "executionMode": "read_only",
        "safeContext": ["slice=task-4b"],
    }

    completed = subprocess.run(  # noqa: S603 - test executes the trusted adapter-local Node probe.
        [node_executable, "clinecore-probe.mjs"],
        cwd=RUNNER_DIRECTORY,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
        env={},
    )

    result = parse_runner_output(completed.stdout, exit_code=completed.returncode, stderr=completed.stderr)

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.FAILED
    assert result.blockers[0].code == "missing_sdk_configuration"
    assert "CLINE_SDK_API_KEY" not in completed.stdout
