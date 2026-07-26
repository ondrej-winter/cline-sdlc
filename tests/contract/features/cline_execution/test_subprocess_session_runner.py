"""Contract tests for the subprocess-backed Cline session runner."""

import signal
from threading import Event
from typing import TYPE_CHECKING

import pytest

from cline_sdlc.features.cline_execution.adapters.outbound.subprocess_session_runner import SubprocessClineSessionRunner
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionRequest,
)
from cline_sdlc.features.cline_execution.application.use_cases.run_session import RunClineSession
from cline_sdlc.features.cline_execution.domain.outcome import SessionStatus
from tests.contract.features.cline_execution.conftest import FakeClineFactory, FakeClineRequest

if TYPE_CHECKING:
    from pathlib import Path

DUPLICATE_OUTCOME_COUNT = 2
NONZERO_EXIT_CODE = 23


def _request(command: list[str], working_directory: Path, *, timeout_seconds: float = 2.0) -> ClineSessionRequest:
    return ClineSessionRequest(
        command=tuple(command),
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
    )


def test_run_session_delegates_to_runner(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = RunClineSession(SubprocessClineSessionRunner()).execute(
        _request(fake_cline(FakeClineRequest("valid")), tmp_path)
    )

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == 0
    assert result.has_exactly_one_terminal_outcome


def test_valid_session_captures_one_terminal_outcome(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = SubprocessClineSessionRunner().run(_request(fake_cline(FakeClineRequest("valid")), tmp_path))

    assert result.exit_code == 0
    assert result.malformed_output_lines == ()
    assert len(result.terminal_outcomes) == 1
    assert result.terminal_outcomes[0].status is SessionStatus.COMPLETED


def test_missing_outcome_is_observable_without_retry(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = SubprocessClineSessionRunner().run(_request(fake_cline(FakeClineRequest("missing")), tmp_path))

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == 0
    assert result.terminal_outcomes == ()
    assert not result.has_exactly_one_terminal_outcome


def test_malformed_output_is_preserved_as_malformed_line(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = SubprocessClineSessionRunner().run(_request(fake_cline(FakeClineRequest("malformed")), tmp_path))

    assert result.terminal_outcomes == ()
    assert result.malformed_output_lines == ("{not-json}",)


def test_duplicate_outcomes_are_not_collapsed(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = SubprocessClineSessionRunner().run(_request(fake_cline(FakeClineRequest("duplicate")), tmp_path))

    assert len(result.terminal_outcomes) == DUPLICATE_OUTCOME_COUNT
    assert not result.has_exactly_one_terminal_outcome


def test_nonzero_exit_preserves_terminal_outcome(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = SubprocessClineSessionRunner().run(
        _request(fake_cline(FakeClineRequest("valid", exit_code=NONZERO_EXIT_CODE)), tmp_path)
    )

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == NONZERO_EXIT_CODE
    assert result.has_exactly_one_terminal_outcome


def test_timeout_returns_bounded_process_result(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = SubprocessClineSessionRunner().run(
        _request(fake_cline(FakeClineRequest("delayed", delay_seconds=10.0)), tmp_path, timeout_seconds=0.1)
    )

    assert result.process_status is ClineSessionProcessStatus.TIMED_OUT
    assert result.exit_code is None
    assert result.timed_out
    assert result.terminal_outcomes == ()


def test_interruption_request_returns_bounded_process_result(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    interruption = Event()
    interruption.set()

    result = SubprocessClineSessionRunner(interruption).run(
        _request(fake_cline(FakeClineRequest("delayed", delay_seconds=10.0)), tmp_path)
    )

    assert result.process_status is ClineSessionProcessStatus.INTERRUPTED
    assert result.exit_code is None
    assert result.interrupted
    assert result.terminal_outcomes == ()


@pytest.mark.skipif(not hasattr(signal, "SIGTERM"), reason="SIGTERM is required")
def test_signal_termination_is_reported_as_process_exit(fake_cline: FakeClineFactory, tmp_path: Path) -> None:
    result = SubprocessClineSessionRunner().run(_request(fake_cline(FakeClineRequest("interrupted")), tmp_path))

    assert result.process_status is ClineSessionProcessStatus.EXITED
    assert result.exit_code == -signal.SIGTERM
    assert result.terminal_outcomes == ()


def test_controlled_write_and_reported_paths_are_returned_as_outcome_observations(
    fake_cline: FakeClineFactory,
    tmp_path: Path,
) -> None:
    changed_path = "src/generated.txt"
    result = SubprocessClineSessionRunner().run(
        _request(
            fake_cline(
                FakeClineRequest(
                    "valid",
                    repository_root=tmp_path,
                    write_paths=(changed_path,),
                    reported_changed_paths=(changed_path,),
                )
            ),
            tmp_path,
        )
    )

    assert (tmp_path / changed_path).is_file()
    assert result.terminal_outcomes[0].changed_paths == (changed_path,)
