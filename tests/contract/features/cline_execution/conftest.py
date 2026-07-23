"""Fixtures for fake-Cline subprocess contract tests."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pytest


@dataclass(frozen=True)
class FakeClineRequest:
    """Explicit configuration for one fake-Cline process."""

    scenario: str
    repository_root: Path | None = None
    write_paths: tuple[str, ...] = ()
    reported_changed_paths: tuple[str, ...] = ()
    write_content: str = "fake Cline write\n"
    delay_seconds: float = 0.0
    exit_code: int = 0


class FakeClineFactory(Protocol):
    """Build an argument array from an explicit fake-Cline request."""

    def __call__(self, request: FakeClineRequest) -> list[str]: ...


@pytest.fixture
def fake_cline(tmp_path: Path) -> FakeClineFactory:
    """Build an argument array for one explicit fake-Cline scenario."""
    executable = Path(__file__).with_name("fake_cline.py")

    def build(request: FakeClineRequest) -> list[str]:
        root = request.repository_root or tmp_path
        arguments = [
            sys.executable,
            str(executable),
            "--scenario",
            request.scenario,
            "--repository-root",
            str(root),
            "--write-content",
            request.write_content,
            "--delay-seconds",
            str(request.delay_seconds),
            "--exit-code",
            str(request.exit_code),
        ]
        for path in request.write_paths:
            arguments.extend(("--write-path", path))
        for path in request.reported_changed_paths:
            arguments.extend(("--reported-changed-path", path))
        return arguments

    return build
