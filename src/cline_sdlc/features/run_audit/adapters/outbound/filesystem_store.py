"""Filesystem-backed run audit store."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from cline_sdlc.features.run_audit.application.dtos.run_audit import (
    RunAuditBlocker,
    RunAuditRecord,
    RunAuditRequest,
    RunAuditResult,
    RunAuditStatus,
)

if TYPE_CHECKING:
    from pathlib import Path

AUDIT_ROOT = ".cline-sdlc"
RUNS_DIRECTORY = "runs"
SUMMARY_FILENAME = "summary.json"
IGNORE_RULE = f"{AUDIT_ROOT}/"


class FilesystemRunAuditStore:
    """Persist ignored run summaries under `.cline-sdlc/runs/<run-id>/`."""

    def store(self, request: RunAuditRequest, record: RunAuditRecord) -> RunAuditResult:
        """Create an ignored run directory and write a versioned JSON summary."""
        blocker = _validate_run_id(request.run_id)
        if blocker is not None:
            return _failed(blocker)

        repository_root = request.repository_root.resolve(strict=False)
        run_directory = repository_root / AUDIT_ROOT / RUNS_DIRECTORY / request.run_id
        summary_path = run_directory / SUMMARY_FILENAME
        blocker = _path_blocker(repository_root, run_directory)
        if blocker is not None:
            return _failed(blocker)

        ignore_blocker = _ensure_ignore_rule(repository_root)
        if ignore_blocker is not None:
            return _failed(ignore_blocker)

        run_directory.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(_record_payload(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        relative_summary_path = summary_path.relative_to(repository_root).as_posix()
        return RunAuditResult(
            status=RunAuditStatus.RECORDED,
            summary_path=relative_summary_path,
            record=record,
        )


def _record_payload(record: RunAuditRecord) -> dict[str, object]:
    payload = asdict(record)
    payload["events"] = [
        {"category": event.category, "message": event.message, "metadata": dict(event.metadata)}
        for event in record.events
    ]
    return payload


def _validate_run_id(run_id: str) -> RunAuditBlocker | None:
    if not run_id.strip() or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        return RunAuditBlocker(
            code="invalid_run_id",
            summary="run identifier must be one safe path segment",
            path=run_id,
        )
    return None


def _path_blocker(repository_root: Path, run_directory: Path) -> RunAuditBlocker | None:
    if _first_symlink_path(repository_root, run_directory) is not None:
        return RunAuditBlocker(
            code="audit_path_symlink_escape",
            summary="audit path must not traverse symlinks before writing",
            path=run_directory.as_posix(),
        )
    try:
        run_directory.resolve(strict=False).relative_to(repository_root)
    except ValueError:
        return RunAuditBlocker(
            code="audit_path_outside_repository",
            summary="audit path must stay inside the repository",
            path=run_directory.as_posix(),
        )
    return None


def _ensure_ignore_rule(repository_root: Path) -> RunAuditBlocker | None:
    gitignore_path = repository_root / ".gitignore"
    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    rules = {line.strip() for line in existing.splitlines()}
    if IGNORE_RULE in rules:
        return None
    suffix = "" if not existing or existing.endswith("\n") else "\n"
    gitignore_path.write_text(f"{existing}{suffix}{IGNORE_RULE}\n", encoding="utf-8")
    return None


def _first_symlink_path(repository_root: Path, candidate: Path) -> str | None:
    current = repository_root
    try:
        relative_parts = candidate.relative_to(repository_root).parts
    except ValueError:
        return None
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            return current.relative_to(repository_root).as_posix()
        if not current.exists():
            return None
    return None


def _failed(blocker: RunAuditBlocker) -> RunAuditResult:
    return RunAuditResult(status=RunAuditStatus.FAILED, blockers=(blocker,))
