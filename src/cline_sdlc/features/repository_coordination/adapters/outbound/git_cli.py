"""Git CLI adapter for repository inspection."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryFileObservation,
    RepositoryInspectionBlocker,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
    RepositoryInspectionStatus,
    RepositorySnapshot,
)

GIT_COMMAND = "git"
GIT_STATUS_PATH_START = 3
GIT_STATUS_MINIMUM_LINE_LENGTH = 4


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
        input_observations = tuple(_inspect_input(repository_root, path, blockers) for path in request.input_paths)
        if blockers:
            return RepositoryInspectionResult(status=RepositoryInspectionStatus.FAILED, blockers=tuple(blockers))

        snapshot = RepositorySnapshot(
            repository_root=repository_root.as_posix(),
            head_commit=head_result.stdout.strip(),
            branch=branch_result.stdout.strip() or None,
            dirty_paths=_dirty_paths(status_result.stdout),
            input_files=input_observations,
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
