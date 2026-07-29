"""Tests for the Python Cline SDK session runner adapter."""

from __future__ import annotations

import sys
from threading import Event
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk.adapter import ClineSdkSessionRunner
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionRequest,
    ClineSessionTerminalStatus,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole

if TYPE_CHECKING:
    from pathlib import Path

NONZERO_EXIT_CODE = 7


def _request(tmp_path: Path, *, timeout_seconds: float = 2.0) -> ClineSessionRequest:
    return ClineSessionRequest(
        command=("node", "runner.mjs"),
        working_directory=tmp_path,
        timeout_seconds=timeout_seconds,
        session_role=SessionRole.IMPLEMENTATION,
        instructions="Implement the accepted slice.",
        outcome_contract="Return exactly one typed terminal result.",
    )


def _write_fake_runner(tmp_path: Path, source: str) -> Path:
    runner = tmp_path / "fake_runner.py"
    runner.write_text(source, encoding="utf-8")
    return runner


def test_adapter_invokes_runner_with_protocol_stdin_and_parses_success(tmp_path: Path) -> None:
    runner = _write_fake_runner(
        tmp_path,
        """
import json
import sys

request = json.loads(sys.stdin.read())
assert request["instructions"] == "Implement the accepted slice."
print(json.dumps({"type": "event", "evidenceType": "assistant_output", "summary": "safe output"}))
print(json.dumps({"type": "terminal_result", "status": "completed"}))
""".lstrip(),
    )

    result = ClineSdkSessionRunner(
        node_command=(sys.executable,),
        runner_directory=tmp_path,
        runner_script=runner.name,
    ).run(_request(tmp_path))

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == 0
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.COMPLETED
    assert result.events[0].summary == "safe output"


def test_adapter_preserves_nonzero_runner_exit_with_structured_blocker(tmp_path: Path) -> None:
    runner = _write_fake_runner(
        tmp_path,
        """
import json
import sys

print(json.dumps({"type": "blocker", "code": "missing_sdk_configuration", "summary": "missing config"}))
print(json.dumps({"type": "terminal_result", "status": "failed"}))
sys.exit({NONZERO_EXIT_CODE})
""".replace("{NONZERO_EXIT_CODE}", str(NONZERO_EXIT_CODE)).lstrip(),
    )

    result = ClineSdkSessionRunner(
        node_command=(sys.executable,),
        runner_directory=tmp_path,
        runner_script=runner.name,
    ).run(_request(tmp_path))

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == NONZERO_EXIT_CODE
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.FAILED
    assert result.blockers[0].code == "missing_sdk_configuration"


def test_adapter_fails_closed_for_malformed_runner_output(tmp_path: Path) -> None:
    runner = _write_fake_runner(tmp_path, "print('{not-json}')\n")

    result = ClineSdkSessionRunner(
        node_command=(sys.executable,),
        runner_directory=tmp_path,
        runner_script=runner.name,
    ).run(_request(tmp_path))

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.INVALID_OUTPUT
    assert result.blockers[-1].code == "malformed_protocol_json"


def test_adapter_timeout_terminates_runner_and_returns_structured_blocker(tmp_path: Path) -> None:
    runner = _write_fake_runner(
        tmp_path,
        """
import time

time.sleep(10)
""".lstrip(),
    )

    result = ClineSdkSessionRunner(
        node_command=(sys.executable,),
        runner_directory=tmp_path,
        runner_script=runner.name,
    ).run(_request(tmp_path, timeout_seconds=0.1))

    assert result.process_status is ClineSessionProcessStatus.TIMED_OUT
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.TIMED_OUT
    assert result.blockers[0].code == "sdk_runner_timeout"


def test_adapter_interruption_terminates_runner_and_returns_structured_blocker(tmp_path: Path) -> None:
    interruption = Event()
    interruption.set()
    runner = _write_fake_runner(
        tmp_path,
        """
import time

time.sleep(10)
""".lstrip(),
    )

    result = ClineSdkSessionRunner(
        node_command=(sys.executable,),
        runner_directory=tmp_path,
        runner_script=runner.name,
        interruption=interruption,
    ).run(_request(tmp_path))

    assert result.process_status is ClineSessionProcessStatus.INTERRUPTED
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.INTERRUPTED
    assert result.blockers[0].code == "sdk_runner_interrupted"


def test_adapter_start_failure_returns_structured_blocker(tmp_path: Path) -> None:
    result = ClineSdkSessionRunner(
        node_command=("/definitely/not/a/node",),
        runner_directory=tmp_path,
    ).run(_request(tmp_path))

    assert result.process_status is ClineSessionProcessStatus.START_FAILED
    assert result.sdk_terminal_status is ClineSessionTerminalStatus.FAILED
    assert result.blockers[0].code == "sdk_runner_start_failed"
