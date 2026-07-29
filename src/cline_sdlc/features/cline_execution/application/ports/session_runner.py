"""Outbound port for bounded Cline session execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest, ClineSessionResult


class ClineSessionRunnerPort(Protocol):
    """Run one bounded Cline session and return typed application observations."""

    def run(self, request: ClineSessionRequest) -> ClineSessionResult:
        """Execute the requested session once without workflow retry."""
