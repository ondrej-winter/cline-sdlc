"""Integration tests for filesystem run audit storage."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from cline_sdlc.features.run_audit.adapters.outbound.filesystem_store import FilesystemRunAuditStore
from cline_sdlc.features.run_audit.application.dtos.run_audit import (
    RunAuditEvent,
    RunAuditRecord,
    RunAuditRequest,
    RunAuditStatus,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_writes_versioned_summary_under_ignored_run_directory(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    (repository / ".gitignore").write_text("dist/\n", encoding="utf-8")
    record = RunAuditRecord(
        schema_version=1,
        run_id="run-1",
        terminal_status="blocked",
        events=(RunAuditEvent(category="session", message="blocked safely", metadata=(("paths", "0"),)),),
    )

    result = FilesystemRunAuditStore().store(
        RunAuditRequest(repository_root=repository, run_id="run-1", terminal_status="blocked"),
        record,
    )

    assert result.status is RunAuditStatus.RECORDED
    assert result.summary_path == ".cline-sdlc/runs/run-1/summary.json"
    assert (repository / ".gitignore").read_text(encoding="utf-8") == "dist/\n.cline-sdlc/\n"
    payload = json.loads((repository / result.summary_path).read_text(encoding="utf-8"))
    assert payload == {
        "events": [{"category": "session", "message": "blocked safely", "metadata": {"paths": "0"}}],
        "run_id": "run-1",
        "schema_version": 1,
        "terminal_status": "blocked",
    }
    assert _git_stdout(repository, "status", "--porcelain", "--ignored", ".cline-sdlc").startswith("!! .cline-sdlc/")


def test_preserves_existing_ignore_rule_without_duplicate(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    (repository / ".gitignore").write_text(".cline-sdlc/\n", encoding="utf-8")

    result = FilesystemRunAuditStore().store(
        RunAuditRequest(repository_root=repository, run_id="run-2", terminal_status="blocked"),
        RunAuditRecord(schema_version=1, run_id="run-2", terminal_status="blocked"),
    )

    assert result.recorded
    assert (repository / ".gitignore").read_text(encoding="utf-8") == ".cline-sdlc/\n"


def test_rejects_invalid_run_id_before_writing(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)

    result = FilesystemRunAuditStore().store(
        RunAuditRequest(repository_root=repository, run_id="../escape", terminal_status="blocked"),
        RunAuditRecord(schema_version=1, run_id="../escape", terminal_status="blocked"),
    )

    assert result.status is RunAuditStatus.FAILED
    assert result.blockers[0].code == "invalid_run_id"
    assert not (repository / ".cline-sdlc").exists()


def test_rejects_audit_root_symlink_escape(tmp_path: Path) -> None:
    repository = _initialized_repository(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repository / ".cline-sdlc").symlink_to(outside, target_is_directory=True)

    result = FilesystemRunAuditStore().store(
        RunAuditRequest(repository_root=repository, run_id="run-3", terminal_status="blocked"),
        RunAuditRecord(schema_version=1, run_id="run-3", terminal_status="blocked"),
    )

    assert result.status is RunAuditStatus.FAILED
    assert result.blockers[0].code == "audit_path_symlink_escape"


def _initialized_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--initial-branch", "feature/test")
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


def _git_stdout(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()
