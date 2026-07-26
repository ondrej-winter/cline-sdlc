"""Portable disposable-host fixtures for end-to-end workflow proofs."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

IDEA_PATH = "product/briefs/portable-runner.md"
SPECIFICATION_PATH = "engineering/specifications/portable-runner.md"
PLAN_PATH = "delivery/plans/portable-runner.md"
HOST_CHECK = "tools/verify-host"
STATUS_PATH_OFFSET = 3


@dataclass(frozen=True)
class ExternalHost:
    """Disposable unrelated host repository with isolated Git configuration."""

    root: Path
    environment: dict[str, str]

    def write_text(self, relative_path: str, content: str) -> Path:
        """Write UTF-8 fixture content below the host root."""
        destination = self.root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    def read_text(self, relative_path: str) -> str:
        """Read one UTF-8 host file."""
        return (self.root / relative_path).read_text(encoding="utf-8")

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Run non-interactive Git without developer-global configuration."""
        return subprocess.run(  # noqa: S603
            ("git", "--no-pager", *arguments),  # noqa: S607
            cwd=self.root,
            env=self.environment,
            check=True,
            capture_output=True,
            text=True,
        )

    def commit_all(self, message: str) -> str:
        """Commit all current fixture paths and return the full object identifier."""
        self.git("add", "--all")
        self.git("commit", "--no-gpg-sign", "-m", message)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def status_paths(self) -> tuple[str, ...]:
        """Return normalized dirty paths from porcelain status."""
        output = self.git("status", "--porcelain=v1", "--untracked-files=all").stdout
        return tuple(line[STATUS_PATH_OFFSET:] for line in output.splitlines() if len(line) > STATUS_PATH_OFFSET)

    def history_text(self) -> str:
        """Return commit messages and committed patch content for leak checks."""
        messages = self.git("log", "--format=%B").stdout
        patches = self.git("log", "-p", "--all", "--no-ext-diff").stdout
        return f"{messages}\n{patches}"


@pytest.fixture
def external_host(tmp_path: Path) -> ExternalHost:
    """Create a host with non-default artifacts and a non-uv command surface."""
    root = tmp_path / "external-host"
    home = tmp_path / "isolated-home"
    root.mkdir()
    home.mkdir()
    environment = {
        **os.environ,
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_EDITOR": "true",
        "GIT_PAGER": "cat",
    }
    host = ExternalHost(root=root, environment=environment)
    host.git("init", "--initial-branch", "feature/portable-proof")
    host.git("config", "user.name", "Portable Host Tests")
    host.git("config", "user.email", "portable-host@example.test")
    host.git("config", "commit.gpgSign", "false")
    host.write_text(
        "HOST_WORKFLOW.md",
        "# External host\n\nArtifacts live outside docs/. Run `tools/verify-host --all`.\n",
    )
    host.write_text(HOST_CHECK, "#!/bin/sh\nexit 0\n")
    (root / HOST_CHECK).chmod(0o755)
    host.write_text(".gitignore", ".cline-sdlc/\n")
    host.commit_all("Initialize unrelated portable host")
    return host
