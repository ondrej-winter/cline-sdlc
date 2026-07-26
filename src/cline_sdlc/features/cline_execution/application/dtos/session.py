"""DTOs for one supervised Cline subprocess session."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome


class ClineSessionProcessStatus(StrEnum):
    """Observable process-level status for one Cline session."""

    EXITED = "exited"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"
    START_FAILED = "start_failed"


@dataclass(frozen=True)
class ClineSessionRequest:
    """Application request to execute one explicit Cline argument array."""

    command: tuple[str, ...]
    working_directory: Path
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not self.command:
            message = "session command must not be empty"
            raise ValueError(message)
        if any(not argument for argument in self.command):
            message = "session command arguments must not be empty"
            raise ValueError(message)
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            message = "session timeout must be a finite positive number of seconds"
            raise ValueError(message)


@dataclass(frozen=True)
class ClineSessionResult:
    """Process observations returned by a supervised Cline session adapter."""

    process_status: ClineSessionProcessStatus
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    terminal_outcomes: tuple[SessionOutcome, ...] = field(default_factory=tuple)
    malformed_output_lines: tuple[str, ...] = field(default_factory=tuple)

    @property
    def timed_out(self) -> bool:
        """Return whether the parent bounded the child by timeout."""
        return self.process_status is ClineSessionProcessStatus.TIMED_OUT

    @property
    def interrupted(self) -> bool:
        """Return whether the parent stopped the child after an interruption request."""
        return self.process_status is ClineSessionProcessStatus.INTERRUPTED

    @property
    def has_exactly_one_terminal_outcome(self) -> bool:
        """Return whether the captured stream contained exactly one validated outcome."""
        return len(self.terminal_outcomes) == 1
