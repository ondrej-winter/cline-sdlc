"""Read-only Git CLI adapter for completed-slice ownership evidence."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import (
    OwningCommitCandidate,
    PlanHistoryObservation,
    PlanHistoryRequest,
)

_TRAILER_SEPARATOR = "\x1f"
_RECORD_SEPARATOR = "\x1e"
_STATUS_PATH_START = 3
_STATUS_MINIMUM_LENGTH = 4

if TYPE_CHECKING:
    from pathlib import Path


class GitCliPlanHistoryReader:
    """Observe reachable trailer claims and committed plan transitions."""

    def observe(self, request: PlanHistoryRequest) -> PlanHistoryObservation:
        """Return HEAD, dirty paths, and matching reachable ownership candidates."""
        root = request.repository_root.resolve()
        head = _git(root, "rev-parse", "HEAD").require_stdout("repository HEAD is unavailable")
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").require_stdout(
            "repository status is unavailable",
            allow_empty=True,
        )
        candidates = tuple(
            candidate
            for commit, message in _commit_messages(root)
            if (candidate := _candidate(root, request.plan_path, commit, message)) is not None
            and candidate.slice_id in request.completed_slice_ids
        )
        return PlanHistoryObservation(
            head_commit=head.strip(),
            dirty_paths=_dirty_paths(status),
            owning_candidates=candidates,
        )


def _commit_messages(repository_root: Path) -> tuple[tuple[str, str], ...]:
    output = _git(repository_root, "log", "--format=%H%x1f%B%x1e", "HEAD").require_stdout(
        "repository history is unavailable",
        allow_empty=True,
    )
    records: list[tuple[str, str]] = []
    for raw_record in output.split(_RECORD_SEPARATOR):
        record = raw_record.strip()
        if not record or _TRAILER_SEPARATOR not in record:
            continue
        commit, message = record.split(_TRAILER_SEPARATOR, maxsplit=1)
        records.append((commit.strip(), message.strip()))
    return tuple(records)


def _candidate(repository_root: Path, plan_path: str, commit: str, message: str) -> OwningCommitCandidate | None:
    trailers = _trailers(message)
    values = tuple(
        trailers.get(key)
        for key in (
            "Cline-SDLC-Slice-ID",
            "Cline-SDLC-Work-ID",
            "Cline-SDLC-Slice-Kind",
            "Cline-SDLC-Material-Digest",
        )
    )
    if any(value is None or not value for value in values):
        return None
    slice_id, work_id, slice_kind, material_digest = cast("tuple[str, str, str, str]", values)
    plan = _git(repository_root, "show", f"{commit}:{plan_path}")
    if not plan.succeeded:
        return None
    parent = _git(repository_root, "show", f"{commit}^:{plan_path}")
    return OwningCommitCandidate(
        commit=commit,
        slice_id=slice_id,
        work_id=work_id,
        slice_kind=slice_kind,
        material_digest=material_digest,
        plan_content=plan.stdout.encode("utf-8"),
        parent_plan_content=parent.stdout.encode("utf-8") if parent.succeeded else None,
    )


def _trailers(message: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in message.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.startswith("Cline-SDLC-"):
            result[key] = "" if key in result else value.strip()
    return result


def _dirty_paths(stdout: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in stdout.splitlines():
        if len(line) < _STATUS_MINIMUM_LENGTH:
            continue
        path = line[_STATUS_PATH_START:]
        if " -> " in path:
            path = path.rsplit(" -> ", maxsplit=1)[1]
        paths.append(path)
    return tuple(paths)


@dataclass(frozen=True)
class _GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0

    def require_stdout(self, message: str, *, allow_empty: bool = False) -> str:
        if not self.succeeded or (not allow_empty and not self.stdout.strip()):
            error_message = f"{message}: {self.stderr.strip()}"
            raise ValueError(error_message)
        return self.stdout


def _git(cwd: Path, *arguments: str) -> _GitResult:
    completed = subprocess.run(  # noqa: S603
        ("git", "--no-pager", *arguments),  # noqa: S607
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    return _GitResult(completed.returncode, completed.stdout, completed.stderr)
