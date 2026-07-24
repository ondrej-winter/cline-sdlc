"""Subprocess-backed validation command runner."""

from __future__ import annotations

import subprocess

from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommandRunRequest,
    ValidationCommandRunResult,
    ValidationCommandRunStatus,
)


class SubprocessValidationCommandRunner:
    """Execute one structured validation command with an explicit working directory."""

    def run(self, request: ValidationCommandRunRequest) -> ValidationCommandRunResult:
        """Return process observations without interpreting workflow success."""
        try:
            completed = subprocess.run(  # noqa: S603
                [request.command.executable, *request.command.arguments],
                cwd=request.working_directory,
                capture_output=True,
                check=False,
                text=True,
                timeout=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired as err:
            return ValidationCommandRunResult(
                status=ValidationCommandRunStatus.TIMED_OUT,
                exit_code=None,
                stdout=_timeout_output(err.stdout),
                stderr=_timeout_output(err.stderr),
            )
        except OSError as err:
            return ValidationCommandRunResult(
                status=ValidationCommandRunStatus.START_FAILED,
                exit_code=None,
                stderr=str(err),
            )
        return ValidationCommandRunResult(
            status=ValidationCommandRunStatus.EXITED,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
