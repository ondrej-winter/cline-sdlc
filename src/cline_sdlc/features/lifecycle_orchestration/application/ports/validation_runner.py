"""Outbound port for validation command execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
        ValidationCommandRunRequest,
        ValidationCommandRunResult,
    )


class ValidationCommandRunnerPort(Protocol):
    """Execute structured validation commands without workflow decisions."""

    def run(self, request: ValidationCommandRunRequest) -> ValidationCommandRunResult:
        """Return typed process observations for one validation command."""
