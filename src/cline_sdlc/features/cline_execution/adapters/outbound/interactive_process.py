"""Attached subprocess runner for interactive Cline sessions."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.adapters.outbound.terminal_outcomes import (
    parse_terminal_outcomes,
    timeout_output,
)
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
    from cline_sdlc.features.cline_execution.application.ports.terminal import TerminalOutputPort


class AttachedInteractiveClineSessionRunner:
    """Run Cline with inherited stdin while preserving typed terminal outcomes."""

    def __init__(self, terminal: TerminalOutputPort | None = None) -> None:
        self._terminal = terminal

    def run(self, request: ClineSessionRequest) -> ClineSessionResult:
        """Run an attached process and return captured structured observations."""
        try:
            completed = subprocess.run(  # noqa: S603
                list(request.command),
                cwd=request.working_directory,
                stdin=None,
                capture_output=True,
                check=False,
                text=True,
                timeout=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired as err:
            stdout = timeout_output(err.stdout)
            stderr = timeout_output(err.stderr)
            self._forward_captured_output(stdout=stdout, stderr=stderr)
            return ClineSessionResult(
                process_status=ClineSessionProcessStatus.TIMED_OUT,
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
            )
        except OSError as err:
            return ClineSessionResult(
                process_status=ClineSessionProcessStatus.START_FAILED,
                exit_code=None,
                stderr=str(err),
            )

        parsed = parse_terminal_outcomes(completed.stdout)
        self._forward_captured_output(
            stdout="".join(f"{line}\n" for line in parsed.non_outcome_lines),
            stderr=completed.stderr,
        )
        return ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            terminal_outcomes=parsed.outcomes,
            malformed_output_lines=parsed.malformed_lines,
        )

    def _forward_captured_output(self, *, stdout: str, stderr: str) -> None:
        if self._terminal is None:
            return
        if stdout:
            self._terminal.write_stdout(stdout)
        if stderr:
            self._terminal.write_stderr(stderr)


class AttachedTtyClineSessionRunner:
    """Run Cline with inherited terminal streams for true TUI sessions."""

    def run(self, request: ClineSessionRequest) -> ClineSessionResult:
        """Run an attached TTY process and return process-level evidence only."""
        try:
            completed = subprocess.run(  # noqa: S603
                list(request.command),
                cwd=request.working_directory,
                stdin=None,
                stdout=None,
                stderr=None,
                check=False,
                timeout=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ClineSessionResult(
                process_status=ClineSessionProcessStatus.TIMED_OUT,
                exit_code=None,
            )
        except OSError as err:
            return ClineSessionResult(
                process_status=ClineSessionProcessStatus.START_FAILED,
                exit_code=None,
                stderr=str(err),
            )

        return ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=completed.returncode,
        )
