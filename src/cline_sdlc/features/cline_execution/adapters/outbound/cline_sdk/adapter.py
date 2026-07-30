"""Python subprocess adapter for the adapter-owned Cline SDK Node runner."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk.protocol import (
    parse_runner_output,
    serialize_runner_request,
)
from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import DEFAULT_NODE_RUNNER_DIRECTORY
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionBlocker,
    ClineSessionProcessStatus,
    ClineSessionResult,
    ClineSessionTerminalStatus,
)

if TYPE_CHECKING:
    from pathlib import Path

    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest

_POLL_INTERVAL_SECONDS = 0.05
_TERMINATION_GRACE_SECONDS = 1.0
_DEFAULT_RUNNER_SCRIPT = "runner.mjs"


class InterruptionPort(Protocol):
    """Expose whether the parent received a stop request."""

    def is_set(self) -> bool:
        """Return whether active work should stop."""


class ClineSdkSessionRunner:
    """Run one bounded Cline session through the adapter-owned Node SDK runner."""

    def __init__(
        self,
        *,
        node_command: tuple[str, ...] = ("node",),
        runner_directory: Path = DEFAULT_NODE_RUNNER_DIRECTORY,
        runner_script: str = _DEFAULT_RUNNER_SCRIPT,
        interruption: InterruptionPort | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        if not node_command:
            message = "SDK runner node command must not be empty"
            raise ValueError(message)
        if any(not argument for argument in node_command):
            message = "SDK runner node command arguments must not be empty"
            raise ValueError(message)
        if not runner_script.strip():
            message = "SDK runner script must not be empty"
            raise ValueError(message)
        self._node_command = node_command
        self._runner_directory = runner_directory
        self._runner_script = runner_script
        self._interruption = interruption
        self._environment = environment

    def run(self, request: ClineSessionRequest) -> ClineSessionResult:
        """Run the Node runner once and parse its JSONL protocol output."""
        runner_input = serialize_runner_request(request)
        try:
            process = subprocess.Popen(  # noqa: S603
                [*self._node_command, self._runner_script],
                cwd=self._runner_directory,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
                env=self._environment,
            )
        except OSError as err:
            return ClineSessionResult(
                process_status=ClineSessionProcessStatus.START_FAILED,
                exit_code=None,
                stderr=str(err),
                sdk_terminal_status=ClineSessionTerminalStatus.FAILED,
                blockers=(
                    ClineSessionBlocker(
                        code="sdk_runner_start_failed",
                        summary="Cline SDK Node runner could not be started.",
                        evidence=f"error_type={type(err).__name__}",
                    ),
                ),
            )

        _send_runner_input(process, runner_input)
        deadline = time.monotonic() + request.timeout_seconds
        while True:
            if self._interruption is not None and self._interruption.is_set():
                stdout, stderr = _stop_process(process)
                return _stopped_result(
                    process_status=ClineSessionProcessStatus.INTERRUPTED,
                    terminal_status=ClineSessionTerminalStatus.INTERRUPTED,
                    stdout=stdout,
                    stderr=stderr,
                    blocker=ClineSessionBlocker(
                        code="sdk_runner_interrupted",
                        summary="Cline SDK Node runner was interrupted before completion.",
                    ),
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stdout, stderr = _stop_process(process)
                return _stopped_result(
                    process_status=ClineSessionProcessStatus.TIMED_OUT,
                    terminal_status=ClineSessionTerminalStatus.TIMED_OUT,
                    stdout=stdout,
                    stderr=stderr,
                    blocker=ClineSessionBlocker(
                        code="sdk_runner_timeout",
                        summary="Cline SDK Node runner exceeded the configured timeout.",
                    ),
                )
            try:
                stdout, stderr = process.communicate(timeout=min(_POLL_INTERVAL_SECONDS, remaining))
                break
            except subprocess.TimeoutExpired:
                continue

        return parse_runner_output(stdout, exit_code=process.returncode, stderr=stderr)


def _send_runner_input(process: subprocess.Popen[str], runner_input: str) -> None:
    if process.stdin is None:
        return
    with suppress(BrokenPipeError):
        process.stdin.write(runner_input)
    with suppress(BrokenPipeError):
        process.stdin.close()


def _stopped_result(
    *,
    process_status: ClineSessionProcessStatus,
    terminal_status: ClineSessionTerminalStatus,
    stdout: str,
    stderr: str,
    blocker: ClineSessionBlocker,
) -> ClineSessionResult:
    return ClineSessionResult(
        process_status=process_status,
        exit_code=None,
        stdout=stdout,
        stderr=stderr,
        sdk_terminal_status=terminal_status,
        blockers=(blocker,),
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
