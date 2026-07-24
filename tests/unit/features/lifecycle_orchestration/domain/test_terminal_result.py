"""Tests for lifecycle terminal status and exit-category contracts."""

from cline_sdlc.features.lifecycle_orchestration.domain.terminal_result import (
    ExitCategory,
    TerminalStatus,
    exit_category_for_status,
)


def test_maps_every_terminal_status_to_documented_exit_category() -> None:
    assert {status: exit_category_for_status(status) for status in TerminalStatus} == {
        TerminalStatus.COMPLETED: ExitCategory.COMPLETED,
        TerminalStatus.INVALID_INVOCATION: ExitCategory.USAGE_ERROR,
        TerminalStatus.PREFLIGHT_FAILED: ExitCategory.PREFLIGHT_FAILED,
        TerminalStatus.BLOCKED: ExitCategory.BLOCKED,
        TerminalStatus.APPROVAL_REQUIRED: ExitCategory.BLOCKED,
        TerminalStatus.FAILED: ExitCategory.STAGE_FAILED,
        TerminalStatus.INTERRUPTED: ExitCategory.INTERRUPTED,
        TerminalStatus.INTERNAL_ERROR: ExitCategory.INTERNAL_ERROR,
    }


def test_rejects_unknown_terminal_status_value() -> None:
    unknown_status = "not_a_status"

    assert unknown_status not in {status.value for status in TerminalStatus}
