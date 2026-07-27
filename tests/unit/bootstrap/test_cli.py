"""Tests for console entry point wiring."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

from cline_sdlc.bootstrap.cli import main
from cline_sdlc.features.lifecycle_orchestration.application.dtos.terminal_result import TerminalResult
from cline_sdlc.features.lifecycle_orchestration.domain.terminal_result import ExitCategory, TerminalStatus

if TYPE_CHECKING:
    import pytest

    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest


def test_main_writes_json_stdout_and_returns_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    def fake_run_idea_refinement(request: InvocationRequest, *, cwd: object) -> TerminalResult:
        del cwd
        return TerminalResult(status=TerminalStatus.COMPLETED, reason="idea_brief_accepted", stage=request.stage)

    monkeypatch.setattr(
        "cline_sdlc.features.lifecycle_orchestration.adapters.inbound.cli._run_idea_refinement",
        fake_run_idea_refinement,
    )

    exit_code = main(["--idea", "Preview", "--json"], stdout=stdout, stderr=stderr)

    assert exit_code == ExitCategory.COMPLETED
    assert stderr.getvalue() == ""
    assert len(stdout.getvalue().splitlines()) == 1
    assert json.loads(stdout.getvalue())["status"] == "completed"


def test_main_returns_usage_exit_for_invalid_invocation() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main([], stdout=stdout, stderr=stderr)

    assert exit_code == ExitCategory.USAGE_ERROR
    assert stderr.getvalue() == ""
    assert "invalid_invocation" in stdout.getvalue()
