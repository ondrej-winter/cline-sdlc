"""Use case for running one supervised Cline session."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest, ClineSessionResult
    from cline_sdlc.features.cline_execution.application.ports.session_runner import ClineSessionRunnerPort


class RunClineSession:
    """Run one bounded Cline session through an application-owned port."""

    def __init__(self, runner: ClineSessionRunnerPort) -> None:
        self._runner = runner

    def execute(self, request: ClineSessionRequest) -> ClineSessionResult:
        """Return process and terminal-outcome observations for the request."""
        return self._runner.run(request)
