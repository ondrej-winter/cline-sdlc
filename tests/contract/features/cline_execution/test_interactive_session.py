"""Contract tests for attached interactive Cline session execution."""

from __future__ import annotations

import signal
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from cline_sdlc.features.cline_execution.adapters.outbound.interactive_process import (
    AttachedInteractiveClineSessionRunner,
)
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionRequest,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionStatus
from tests.contract.features.cline_execution.conftest import FakeClineFactory, FakeClineRequest

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class RecordingTerminal:
    """Test terminal that records human-visible attached-session output."""

    stdout: str = ""
    stderr: str = ""

    def write_stdout(self, text: str) -> None:
        """Record stdout text forwarded through the terminal boundary."""
        self.stdout += text

    def write_stderr(self, text: str) -> None:
        """Record stderr text forwarded through the terminal boundary."""
        self.stderr += text


def _request(command: list[str], working_directory: Path, *, timeout_seconds: float = 2.0) -> ClineSessionRequest:
    return ClineSessionRequest(
        command=tuple(command),
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
    )


def test_interactive_session_preserves_human_output_and_terminal_outcome(
    fake_cline: FakeClineFactory,
    tmp_path: Path,
) -> None:
    terminal = RecordingTerminal()

    result = AttachedInteractiveClineSessionRunner(terminal).run(
        _request(fake_cline(FakeClineRequest("interactive-valid")), tmp_path)
    )

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == 0
    assert result.has_exactly_one_terminal_outcome
    assert result.terminal_outcomes[0].status is SessionStatus.COMPLETED
    assert "human-visible question" in terminal.stdout
    assert terminal.stderr == "interactive warning\n"


def test_interactive_session_keeps_malformed_outcome_separate_from_human_output(
    fake_cline: FakeClineFactory,
    tmp_path: Path,
) -> None:
    terminal = RecordingTerminal()

    result = AttachedInteractiveClineSessionRunner(terminal).run(
        _request(fake_cline(FakeClineRequest("interactive-malformed")), tmp_path)
    )

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.terminal_outcomes == ()
    assert result.malformed_output_lines == ("{not-json}",)
    assert "human-visible question" in terminal.stdout
    assert terminal.stderr == "interactive warning\n"


def test_interactive_timeout_returns_bounded_process_result(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = AttachedInteractiveClineSessionRunner().run(
        _request(fake_cline(FakeClineRequest("delayed", delay_seconds=10.0)), tmp_path, timeout_seconds=0.1)
    )

    assert result.process_status is ClineSessionProcessStatus.TIMED_OUT
    assert result.exit_code is None
    assert result.timed_out
    assert result.terminal_outcomes == ()


@pytest.mark.skipif(not hasattr(signal, "SIGTERM"), reason="SIGTERM is required")
def test_interactive_signal_termination_is_reported_as_process_exit(
    fake_cline: FakeClineFactory,
    tmp_path: Path,
) -> None:
    result = AttachedInteractiveClineSessionRunner().run(
        _request(fake_cline(FakeClineRequest("interrupted")), tmp_path)
    )

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == -signal.SIGTERM
    assert result.terminal_outcomes == ()


def test_interactive_start_failure_is_typed_without_shell(tmp_path: Path) -> None:
    result = AttachedInteractiveClineSessionRunner().run(
        _request(["/definitely/missing/cline"], tmp_path, timeout_seconds=0.1)
    )

    assert result.process_status is ClineSessionProcessStatus.START_FAILED
    assert result.exit_code is None
    assert result.stderr
