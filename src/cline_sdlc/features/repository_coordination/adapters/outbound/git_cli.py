"""Git CLI adapter for repository inspection."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import TYPE_CHECKING

from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryFileObservation,
    RepositoryInspectionBlocker,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
    RepositoryInspectionStatus,
    RepositorySnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

GIT_COMMAND = "git"
GIT_STATUS_PATH_START = 3
GIT_STATUS_MINIMUM_LINE_LENGTH = 4
OPERATION_GIT_PATHS = {
    "merge": "MERGE_HEAD",
    "rebase": "rebase-merge",
    "rebase_apply": "rebase-apply",
    "cherry_pick": "CHERRY_PICK_HEAD",
    "revert": "REVERT_HEAD",
    "bisect": "BISECT_LOG",
}


class GitCliRepositoryInspector:
    """Inspect repository state through non-interactive Git argument arrays."""

    def inspect(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        """Return a repository snapshot or typed blockers for expected Git failures."""
        root_result = _git(request.working_directory, "rev-parse", "--show-toplevel")
        if not root_result.succeeded:
            return _failed(
                "git_repository_unavailable",
                "working directory is not inside a readable Git repository",
                root_result.stderr,
            )

        repository_root = Path(root_result.stdout.strip()).resolve()
        head_result = _git(repository_root, "rev-parse", "HEAD")
        if not head_result.succeeded:
            return _failed("git_head_unavailable", "repository HEAD is unavailable", head_result.stderr)

        branch_result = _git(repository_root, "branch", "--show-current")
        status_result = _git(repository_root, "status", "--porcelain=v1", "--untracked-files=all")
        if not status_result.succeeded:
            return _failed("git_status_unavailable", "repository status is unavailable", status_result.stderr)

        blockers: list[RepositoryInspectionBlocker] = []
        branch = branch_result.stdout.strip() or None
        if branch is None:
            blockers.append(
                RepositoryInspectionBlocker(
                    code="detached_head",
                    summary="repository must be on a named non-detached branch",
                )
            )
        elif _matches_protected_branch(branch, request.protected_branch_patterns):
            blockers.append(
                RepositoryInspectionBlocker(
                    code="protected_branch",
                    summary="repository branch is protected for automated lifecycle writes",
                    evidence=branch,
                )
            )

        dirty_paths = _dirty_paths(status_result.stdout)
        operation_states = _operation_states(repository_root)
        blockers.extend(
            RepositoryInspectionBlocker(
                code="git_operation_in_progress",
                summary="repository has an unresolved Git operation in progress",
                evidence=operation_state,
            )
            for operation_state in operation_states
        )

        nested_repository_paths = _nested_repository_paths(repository_root, dirty_paths)
        blockers.extend(
            RepositoryInspectionBlocker(
                code="nested_repository_change",
                summary="nested repository or submodule changes are not supported by this preflight slice",
                path=nested_path,
            )
            for nested_path in nested_repository_paths
        )

        blockers.extend(_managed_path_blockers(repository_root, request.managed_paths))
        input_observations = tuple(_inspect_input(repository_root, path, blockers) for path in request.input_paths)
        if blockers:
            return RepositoryInspectionResult(status=RepositoryInspectionStatus.FAILED, blockers=tuple(blockers))

        snapshot = RepositorySnapshot(
            repository_root=repository_root.as_posix(),
            head_commit=head_result.stdout.strip(),
            branch=branch,
            dirty_paths=dirty_paths,
            input_files=input_observations,
            operation_states=operation_states,
            nested_repository_paths=nested_repository_paths,
        )
        return RepositoryInspectionResult(status=RepositoryInspectionStatus.READY, snapshot=snapshot)


def _inspect_input(
    repository_root: Path,
    path: Path,
    blockers: list[RepositoryInspectionBlocker],
) -> RepositoryFileObservation:
    resolved_path = path.resolve()
    relative_path = _relative_path(repository_root, resolved_path)
    is_regular_file = resolved_path.is_file()
    if relative_path is None:
        blockers.append(
            RepositoryInspectionBlocker(
                code="input_outside_repository",
                summary="input file is outside the inspected repository",
                path=path.as_posix(),
            )
        )
        observation_path = path.as_posix()
    else:
        observation_path = relative_path
    if relative_path is not None and not is_regular_file:
        blockers.append(
            _input_blocker("input_not_regular_file", "input path must be a readable regular file", relative_path)
        )

    tracked = False
    committed = False
    matches_head = False
    if relative_path is not None:
        tracked = _git(repository_root, "ls-files", "--error-unmatch", "--", relative_path).succeeded
        committed = tracked and _git(repository_root, "cat-file", "-e", f"HEAD:{relative_path}").succeeded
        matches_head = committed and _git(repository_root, "diff", "--quiet", "HEAD", "--", relative_path).succeeded

    if relative_path is not None and is_regular_file:
        if not tracked:
            blockers.append(_input_blocker("input_not_tracked", "input file must be tracked by Git", relative_path))
        elif not committed:
            blockers.append(
                _input_blocker("input_not_committed_at_head", "input file must exist at HEAD", relative_path)
            )
        elif not matches_head:
            blockers.append(
                _input_blocker("input_differs_from_head", "input file must match committed HEAD content", relative_path)
            )

    return RepositoryFileObservation(
        path=observation_path,
        is_regular_file=is_regular_file,
        is_tracked=tracked,
        is_committed_at_head=committed,
        matches_head=matches_head,
    )


def _input_blocker(code: str, summary: str, path: str) -> RepositoryInspectionBlocker:
    return RepositoryInspectionBlocker(code=code, summary=summary, path=path)


def _relative_path(repository_root: Path, path: Path) -> str | None:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return None


def _matches_protected_branch(branch: str, patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(branch, pattern) for pattern in patterns)


def _operation_states(repository_root: Path) -> tuple[str, ...]:
    states: list[str] = []
    for state, git_path in OPERATION_GIT_PATHS.items():
        path_result = _git(repository_root, "rev-parse", "--git-path", git_path)
        if path_result.succeeded and (repository_root / path_result.stdout.strip()).exists():
            states.append(state)
    return tuple(states)


def _nested_repository_paths(repository_root: Path, dirty_paths: Iterable[str]) -> tuple[str, ...]:
    nested_paths: list[str] = []
    for dirty_path in dirty_paths:
        candidate = repository_root / dirty_path
        if (candidate / ".git").exists():
            nested_paths.append(dirty_path.rstrip("/"))
    return tuple(nested_paths)


def _managed_path_blockers(
    repository_root: Path,
    managed_paths: Iterable[Path],
) -> tuple[RepositoryInspectionBlocker, ...]:
    blockers: list[RepositoryInspectionBlocker] = []
    for path in managed_paths:
        candidate = path if path.is_absolute() else repository_root / path
        if ".." in path.parts:
            blockers.append(
                RepositoryInspectionBlocker(
                    code="managed_path_traversal",
                    summary="managed paths must not contain traversal segments",
                    path=path.as_posix(),
                )
            )
            continue
        symlink_path = _first_symlink_path(repository_root, candidate)
        if symlink_path is not None:
            blockers.append(
                RepositoryInspectionBlocker(
                    code="managed_path_symlink_escape",
                    summary="managed path must not traverse symlinks before writing",
                    path=path.as_posix(),
                    evidence=symlink_path,
                )
            )
            continue
        relative_path = _relative_path(repository_root, candidate.resolve(strict=False))
        if relative_path is None:
            blockers.append(
                RepositoryInspectionBlocker(
                    code="managed_path_outside_repository",
                    summary="managed path must stay inside the inspected repository",
                    path=path.as_posix(),
                )
            )
            continue
    return tuple(blockers)


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


def _dirty_paths(stdout: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in stdout.splitlines():
        if len(line) < GIT_STATUS_MINIMUM_LINE_LENGTH:
            continue
        path = line[GIT_STATUS_PATH_START:]
        if " -> " in path:
            path = path.rsplit(" -> ", maxsplit=1)[1]
        paths.append(path)
    return tuple(paths)


def _failed(code: str, summary: str, evidence: str) -> RepositoryInspectionResult:
    return RepositoryInspectionResult(
        status=RepositoryInspectionStatus.FAILED,
        blockers=(RepositoryInspectionBlocker(code=code, summary=summary, evidence=evidence.strip()),),
    )


@dataclass(frozen=True)
class _GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def _git(cwd: Path, *arguments: str) -> _GitResult:
    completed = subprocess.run(  # noqa: S603
        (GIT_COMMAND, "--no-pager", *arguments),
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    return _GitResult(completed.returncode, completed.stdout, completed.stderr)
