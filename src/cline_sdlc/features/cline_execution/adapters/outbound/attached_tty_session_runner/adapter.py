"""Attached TTY subprocess runner for interactive Cline sessions."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest


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
