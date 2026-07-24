"""Integration tests for Git repository inspection."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cline_sdlc.features.repository_coordination.adapters.outbound.git_cli import GitCliRepositoryInspector
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
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


def test_rejects_default_protected_branch(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path, branch="main")
    _commit_file(repository, "README.md", "# Test repository\n")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository)
    )

    assert result.status is RepositoryInspectionStatus.FAILED
    assert _blocker_codes(result) == ("protected_branch",)


def test_allows_custom_protected_branch_patterns(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path, branch="main")
    _commit_file(repository, "README.md", "# Test repository\n")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository, protected_branch_patterns=("production",))
    )

    assert result.status is RepositoryInspectionStatus.READY
    assert result.snapshot is not None
    assert result.snapshot.branch == "main"


def test_rejects_detached_head(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    _commit_file(repository, "README.md", "# Test repository\n")
    head = _git_stdout(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "--detach", head)

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository)
    )

    assert result.status is RepositoryInspectionStatus.FAILED
    assert _blocker_codes(result) == ("detached_head",)


def test_rejects_unresolved_git_operation_state(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    _commit_file(repository, "README.md", "# Test repository\n")
    (repository / ".git" / "MERGE_HEAD").write_text("0" * 40, encoding="utf-8")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository)
    )

    assert result.status is RepositoryInspectionStatus.FAILED
    assert _blocker_codes(result) == ("git_operation_in_progress",)
    assert result.blockers[0].evidence == "merge"


def test_rejects_nested_repository_change(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    _commit_file(repository, "README.md", "# Test repository\n")
    nested_repository = repository / "vendor" / "tool"
    nested_repository.mkdir(parents=True)
    _git(nested_repository, "init")
    _git(nested_repository, "config", "user.email", "cline-sdlc@example.test")
    _git(nested_repository, "config", "user.name", "Cline SDLC Tests")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository)
    )

    assert result.status is RepositoryInspectionStatus.FAILED
    assert _blocker_codes(result) == ("nested_repository_change",)
    assert result.blockers[0].path == "vendor/tool"


def test_rejects_managed_path_traversal(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    _commit_file(repository, "README.md", "# Test repository\n")

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository, managed_paths=(Path("../outside.md"),))
    )

    assert result.status is RepositoryInspectionStatus.FAILED
    assert _blocker_codes(result) == ("managed_path_traversal",)


def test_rejects_managed_path_symlink_escape(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    _commit_file(repository, "README.md", "# Test repository\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (repository / "link").symlink_to(outside, target_is_directory=True)

    result = InspectRepository(GitCliRepositoryInspector()).execute(
        RepositoryInspectionRequest(working_directory=repository, managed_paths=(repository / "link" / "artifact.md",))
    )

    assert result.status is RepositoryInspectionStatus.FAILED
    assert _blocker_codes(result) == ("managed_path_symlink_escape",)
    assert result.blockers[0].evidence == "link"


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


def _initialized_repository(tmp_path: Path, *, branch: str = "feature/test") -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--initial-branch", branch)
    _git(repository, "config", "user.email", "cline-sdlc@example.test")
    _git(repository, "config", "user.name", "Cline SDLC Tests")
    return repository


def _commit_file(repository: Path, relative_path: str, content: str) -> None:
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repository, "add", relative_path)
    _git(repository, "commit", "-m", f"Add {relative_path}")


def _blocker_codes(result: RepositoryInspectionResult) -> tuple[str, ...]:
    return tuple(blocker.code for blocker in result.blockers)


def _git(cwd: Path, *arguments: str) -> None:
    subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()
