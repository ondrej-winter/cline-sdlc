"""Application-owned terminal output boundary for attached sessions."""

from __future__ import annotations

from typing import Protocol


class TerminalOutputPort(Protocol):
    """Receive human-visible output captured from an attached Cline session."""

    def write_stdout(self, text: str) -> None:
        """Write non-outcome stdout text to the caller's terminal boundary."""

    def write_stderr(self, text: str) -> None:
        """Write stderr text to the caller's terminal boundary."""
