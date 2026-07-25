"""Git CLI adapter for one explicit atomic implementation-slice commit."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import GitSliceCommitObservation

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import GitSliceCommitRequest

_STATUS_MINIMUM_LENGTH = 4
_STATUS_PATH_START = 3


class GitCliSliceCommitter:
    """Write validated progress and commit only explicitly authorized paths."""

    def commit(self, request: GitSliceCommitRequest) -> GitSliceCommitObservation:
        """Create one hook-enabled non-interactive commit or leave changes recoverable."""
        root = request.repository_root.resolve()
        try:
            _verify_preconditions(root, request)
            plan_path = _resolved_file(root, request.plan_path)
            _atomic_write(plan_path, request.updated_plan_content)
            _require_paths(root, request.paths, cached=False)
            _git(root, "add", "--", *request.paths).require_success("explicit staging failed")
            _require_paths(root, request.paths, cached=True)
            commit_result = _git(root, "commit", "--no-edit", "-m", request.message)
            if not commit_result.succeeded:
                _unstage(root, request.paths)
                return GitSliceCommitObservation(committed=False, error=commit_result.stderr.strip())
            commit = _git(root, "rev-parse", "HEAD").require_stdout("created commit hash is unavailable").strip()
            committed_paths = _lines(
                _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).require_stdout(
                    "created commit paths are unavailable",
                    allow_empty=True,
                )
            )
            message = _git(root, "show", "-s", "--format=%B", commit).require_stdout(
                "created commit message is unavailable"
            )
        except (OSError, ValueError) as err:
            _unstage(root, request.paths)
            return GitSliceCommitObservation(committed=False, error=str(err))
        return GitSliceCommitObservation(
            committed=True,
            commit=commit,
            committed_paths=committed_paths,
            commit_message=message.strip(),
        )


def _verify_preconditions(root: Path, request: GitSliceCommitRequest) -> None:
    head = _git(root, "rev-parse", "HEAD").require_stdout("repository HEAD is unavailable").strip()
    if head != request.starting_head:
        message = "repository HEAD moved before explicit slice commit"
        raise ValueError(message)
    _require_paths(root, request.paths, cached=False)
    if _lines(_git(root, "diff", "--cached", "--name-only").require_stdout("index is unavailable", allow_empty=True)):
        message = "Git index must be empty before explicit slice staging"
        raise ValueError(message)
    plan_path = _resolved_file(root, request.plan_path)
    if plan_path.read_bytes() != request.expected_plan_content:
        message = "progress plan changed after slice reconciliation"
        raise ValueError(message)


def _resolved_file(root: Path, relative_path: str) -> Path:
    candidate = root / relative_path
    if candidate.is_symlink():
        message = "slice commit plan path must not be a symlink"
        raise ValueError(message)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        message = "slice commit plan path must be a regular repository file"
        raise ValueError(message)
    return resolved


def _require_paths(root: Path, expected: tuple[str, ...], *, cached: bool) -> None:
    command = ("diff", "--cached", "--name-only") if cached else ("status", "--porcelain=v1", "--untracked-files=all")
    output = _git(root, *command).require_stdout("repository changed paths are unavailable", allow_empty=True)
    observed = _lines(output) if cached else _status_paths(output)
    if tuple(sorted(observed)) != tuple(sorted(expected)):
        message = f"repository paths differ from commit candidate: observed={','.join(observed) or '<none>'}"
        raise ValueError(message)


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


def _unstage(root: Path, paths: tuple[str, ...]) -> None:
    _git(root, "reset", "--quiet", "HEAD", "--", *paths)


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
