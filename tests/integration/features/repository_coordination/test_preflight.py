"""Integration tests for Git repository inspection."""

from __future__ import annotations

import subprocess
from pathlib import Path  # noqa: TC003 - Pytest fixtures and helpers use Path at runtime.

from cline_sdlc.features.repository_coordination.adapters.outbound.git_cli import GitCliRepositoryInspector
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositoryInspectionStatus,
)
from cline_sdlc.features.repository_coordination.application.use_cases.inspect_repository import InspectRepository


def test_inspects_clean_repository_with_committed_input(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    input_path = repository / "docs" / "spec.md"
    input_path.parent.mkdir()
    input_path.write_text("# Spec\n", encoding="utf-8")
    _git(repository, "add", "docs/spec.md")
    _git(repository, "commit", "-m", "Add spec")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository, input_paths=(input_path,))
    )

    assert result.status is RepositoryInspectionStatus.READY
    assert result.snapshot is not None
    assert result.snapshot.repository_root == repository.resolve().as_posix()
    assert result.snapshot.is_clean
    assert result.snapshot.input_files[0].path == "docs/spec.md"
    assert result.snapshot.input_files[0].matches_head


def test_rejects_untracked_input_file(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    readme_path = repository / "README.md"
    readme_path.write_text("# Test repository\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "Create baseline")
    input_path = repository / "docs" / "idea.md"
    input_path.parent.mkdir()
    input_path.write_text("# Idea\n", encoding="utf-8")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository, input_paths=(input_path,))
    )

    assert result.status is RepositoryInspectionStatus.FAILED
    assert result.blockers[0].code == "input_not_tracked"


def test_reports_dirty_paths_when_repository_has_modified_content(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    tracked_path = repository / "plan.md"
    tracked_path.write_text("one\n", encoding="utf-8")
    _git(repository, "add", "plan.md")
    _git(repository, "commit", "-m", "Add plan")
    tracked_path.write_text("two\n", encoding="utf-8")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository)
    )

    assert result.status is RepositoryInspectionStatus.READY
    assert result.snapshot is not None
    assert result.snapshot.dirty_paths == ("plan.md",)


def _initialized_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "cline-sdlc@example.test")
    _git(repository, "config", "user.name", "Cline SDLC Tests")
    return repository


def _git(cwd: Path, *arguments: str) -> None:
    subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
