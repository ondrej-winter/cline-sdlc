"""Terminal status and exit-category contracts for lifecycle invocations."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class TerminalStatus(StrEnum):
    """Allowed terminal statuses in the public runner result schema."""

    COMPLETED = "completed"
    INVALID_INVOCATION = "invalid_invocation"
    PREFLIGHT_FAILED = "preflight_failed"
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    INTERNAL_ERROR = "internal_error"


class ExitCategory(IntEnum):
    """Stable process exit categories for the public CLI contract."""

    COMPLETED = 0
    USAGE_ERROR = 2
    PREFLIGHT_FAILED = 3
    BLOCKED = 4
    STAGE_FAILED = 5
    INTERRUPTED = 6
    INTERNAL_ERROR = 7


def exit_category_for_status(status: TerminalStatus) -> ExitCategory:
    """Map a terminal status to its stable process exit category."""
    return {
        TerminalStatus.COMPLETED: ExitCategory.COMPLETED,
        TerminalStatus.INVALID_INVOCATION: ExitCategory.USAGE_ERROR,
        TerminalStatus.PREFLIGHT_FAILED: ExitCategory.PREFLIGHT_FAILED,
        TerminalStatus.BLOCKED: ExitCategory.BLOCKED,
        TerminalStatus.APPROVAL_REQUIRED: ExitCategory.BLOCKED,
        TerminalStatus.FAILED: ExitCategory.STAGE_FAILED,
        TerminalStatus.INTERRUPTED: ExitCategory.INTERRUPTED,
        TerminalStatus.INTERNAL_ERROR: ExitCategory.INTERNAL_ERROR,
    }[status]
