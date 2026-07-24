"""Tests for console entry point wiring."""

from __future__ import annotations

import io
import json

from cline_sdlc.bootstrap.cli import main
from cline_sdlc.features.lifecycle_orchestration.domain.terminal_result import ExitCategory


def test_main_writes_json_stdout_and_returns_exit_code() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(["--idea", "Preview", "--json"], stdout=stdout, stderr=stderr)

    assert exit_code == ExitCategory.BLOCKED
    assert stderr.getvalue() == ""
    assert len(stdout.getvalue().splitlines()) == 1
    assert json.loads(stdout.getvalue())["status"] == "blocked"


def test_main_returns_usage_exit_for_invalid_invocation() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main([], stdout=stdout, stderr=stderr)

    assert exit_code == ExitCategory.USAGE_ERROR
    assert stderr.getvalue() == ""
    assert "invalid_invocation" in stdout.getvalue()
