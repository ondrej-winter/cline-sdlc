"""Subprocess-backed supervised Cline session runner."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.cline_execution.adapters.outbound.terminal_outcome_parser import (
    parse_terminal_outcomes,
)
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest

_POLL_INTERVAL_SECONDS = 0.05
_TERMINATION_GRACE_SECONDS = 1.0


class InterruptionPort(Protocol):
    """Expose whether the parent received a stop request."""

    def is_set(self) -> bool:
        """Return whether active work should stop."""


class SubprocessClineSessionRunner:
    """Execute one explicit Cline argument array with a finite timeout."""

    def __init__(self, interruption: InterruptionPort | None = None) -> None:
        self._interruption = interruption

    def run(self, request: ClineSessionRequest) -> ClineSessionResult:
        """Run the subprocess and convert captured output into typed observations."""
        try:
            process = subprocess.Popen(  # noqa: S603
                list(request.command),
                cwd=request.working_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as err:
            return ClineSessionResult(
                process_status=ClineSessionProcessStatus.START_FAILED,
                exit_code=None,
                stderr=str(err),
            )

        deadline = time.monotonic() + request.timeout_seconds
        while True:
            if self._interruption is not None and self._interruption.is_set():
                stdout, stderr = _stop_process(process)
                return ClineSessionResult(
                    process_status=ClineSessionProcessStatus.INTERRUPTED,
                    exit_code=None,
                    stdout=stdout,
                    stderr=stderr,
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stdout, stderr = _stop_process(process)
                return ClineSessionResult(
                    process_status=ClineSessionProcessStatus.TIMED_OUT,
                    exit_code=None,
                    stdout=stdout,
                    stderr=stderr,
                )
            try:
                stdout, stderr = process.communicate(timeout=min(_POLL_INTERVAL_SECONDS, remaining))
                break
            except subprocess.TimeoutExpired:
                continue

        parsed = parse_terminal_outcomes(stdout)
        return ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            terminal_outcomes=parsed.outcomes,
            malformed_output_lines=parsed.malformed_lines,
        )


def _stop_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    """Terminate the child's process group, escalating after a bounded grace period."""
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        stdout, stderr = process.communicate(timeout=_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    return stdout, stderr
