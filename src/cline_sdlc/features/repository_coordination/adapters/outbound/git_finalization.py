"""Git CLI adapters for plan finalization and complete-history verification."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
    FinalizationCommitCandidate,
    FinalizationHistoryObservation,
    GitFinalizationObservation,
)

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
        FinalizationHistoryRequest,
        GitFinalizationRequest,
    )

_TRAILER_SEPARATOR = "\x1f"
_RECORD_SEPARATOR = "\x1e"
_STATUS_PATH_START = 3
_STATUS_MINIMUM_LENGTH = 4


class GitCliFinalizer:
    """Write and commit one plan, falling back to explicit recovery bytes."""

    def finalize(self, request: GitFinalizationRequest) -> GitFinalizationObservation:
        """Create one hook-enabled finalization commit or persist recovery state."""
        root = request.repository_root.resolve()
        plan_path: Path | None = None
        try:
            _verify_preconditions(root, request)
            plan_path = _resolved_file(root, request.plan_path)
            _atomic_write(plan_path, request.completed_plan_content)
            _git(root, "add", "--", request.plan_path).require_success("explicit finalization staging failed")
            _require_staged_plan_only(root, request.plan_path)
            commit_result = _git(root, "commit", "--no-edit", "-m", request.message)
            if not commit_result.succeeded:
                _unstage(root, request.plan_path)
                _atomic_write(plan_path, request.recovery_plan_content)
                return GitFinalizationObservation(
                    committed=False,
                    recovery_written=True,
                    error=commit_result.stderr.strip(),
                )
            commit = _git(root, "rev-parse", "HEAD").require_stdout("finalization commit hash unavailable").strip()
            paths = _lines(
                _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).require_stdout(
                    "finalization commit paths unavailable",
                    allow_empty=True,
                )
            )
            message = _git(root, "show", "-s", "--format=%B", commit).require_stdout(
                "finalization commit message unavailable"
            )
        except (OSError, ValueError) as err:
            _unstage(root, request.plan_path)
            recovery_written = False
            if plan_path is not None:
                try:
                    _atomic_write(plan_path, request.recovery_plan_content)
                    recovery_written = True
                except OSError:
                    recovery_written = False
            return GitFinalizationObservation(
                committed=False,
                recovery_written=recovery_written,
                error=str(err),
            )
        return GitFinalizationObservation(
            committed=True,
            commit=commit,
            committed_paths=paths,
            commit_message=message.strip(),
        )


class GitCliFinalizationHistoryReader:
    """Observe reachable finalization trailer claims and plan transitions."""

    def observe(self, request: FinalizationHistoryRequest) -> FinalizationHistoryObservation:
        """Return all reachable candidates without changing repository state."""
        root = request.repository_root.resolve()
        head = _git(root, "rev-parse", "HEAD").require_stdout("repository HEAD unavailable").strip()
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").require_stdout(
            "repository status unavailable",
            allow_empty=True,
        )
        candidates = tuple(
            candidate
            for commit, message in _commit_messages(root)
            if (candidate := _candidate(root, request.plan_path, commit, message)) is not None
        )
        return FinalizationHistoryObservation(
            head_commit=head,
            dirty_paths=_status_paths(status),
            candidates=candidates,
        )


def _verify_preconditions(root: Path, request: GitFinalizationRequest) -> None:
    head = _git(root, "rev-parse", "HEAD").require_stdout("repository HEAD unavailable").strip()
    if head != request.starting_head:
        message = "repository HEAD moved before finalization"
        raise ValueError(message)
    if _lines(_git(root, "diff", "--cached", "--name-only").require_stdout("index unavailable", allow_empty=True)):
        message = "Git index must be empty before finalization"
        raise ValueError(message)
    status = _status_paths(
        _git(root, "status", "--porcelain=v1", "--untracked-files=all").require_stdout(
            "repository status unavailable",
            allow_empty=True,
        )
    )
    if status:
        message = f"finalization requires a clean tree: observed={','.join(status)}"
        raise ValueError(message)
    plan_path = _resolved_file(root, request.plan_path)
    if plan_path.read_bytes() != request.expected_plan_content:
        message = "plan changed after finalization authorization"
        raise ValueError(message)


def _require_staged_plan_only(root: Path, plan_path: str) -> None:
    observed = _lines(
        _git(root, "diff", "--cached", "--name-only").require_stdout(
            "index unavailable",
            allow_empty=True,
        )
    )
    if observed != (plan_path,):
        message = "finalization index must contain only the plan"
        raise ValueError(message)


def _commit_messages(repository_root: Path) -> tuple[tuple[str, str], ...]:
    output = _git(repository_root, "log", "--format=%H%x1f%B%x1e", "HEAD").require_stdout(
        "repository history unavailable",
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


def _candidate(root: Path, plan_path: str, commit: str, message: str) -> FinalizationCommitCandidate | None:
    trailers = _trailers(message)
    values = tuple(
        trailers.get(key)
        for key in ("Cline-SDLC-Work-ID", "Cline-SDLC-Plan-Finalization", "Cline-SDLC-Material-Digest")
    )
    if any(value is None or not value for value in values):
        return None
    work_id, finalization, material_digest = cast("tuple[str, str, str]", values)
    if finalization != "true":
        return None
    plan = _git(root, "show", f"{commit}:{plan_path}")
    if not plan.succeeded:
        return None
    parent = _git(root, "show", f"{commit}^:{plan_path}")
    return FinalizationCommitCandidate(
        commit=commit,
        work_id=work_id,
        material_digest=material_digest,
        plan_content=plan.stdout.encode(),
        parent_plan_content=parent.stdout.encode() if parent.succeeded else None,
    )


def _trailers(message: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in message.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.startswith("Cline-SDLC-"):
            result[key] = "" if key in result else value.strip()
    return result


def _resolved_file(root: Path, relative_path: str) -> Path:
    candidate = root / relative_path
    if candidate.is_symlink():
        message = "finalization plan path must not be a symlink"
        raise ValueError(message)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        message = "finalization plan path must be a regular repository file"
        raise ValueError(message)
    return resolved


def _status_paths(output: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < _STATUS_MINIMUM_LENGTH:
            continue
        path = line[_STATUS_PATH_START:]
        if " -> " in path:
            path = path.rsplit(" -> ", maxsplit=1)[1]
        paths.append(path)
    return tuple(paths)


def _lines(output: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def _atomic_write(path: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _unstage(root: Path, plan_path: str) -> None:
    _git(root, "reset", "--quiet", "HEAD", "--", plan_path)


@dataclass(frozen=True)
class _GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0

    def require_success(self, message: str) -> None:
        if not self.succeeded:
            error_message = f"{message}: {self.stderr.strip()}"
            raise ValueError(error_message)

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
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"},
    )
    return _GitResult(completed.returncode, completed.stdout, completed.stderr)
