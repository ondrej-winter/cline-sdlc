"""Tests for staged repository task inspection use case."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cline_sdlc.features.repository_coordination.application.dtos.task_repository import (
    StagedChangeSet,
    TaskRepositoryInspectionBlocker,
    TaskRepositoryInspectionRequest,
    TaskRepositoryInspectionResult,
    TaskRepositoryInspectionStatus,
)
from cline_sdlc.features.repository_coordination.application.use_cases.inspect_task_repository import (
    InspectTaskRepository,
)


@dataclass
class RecordingTaskInspector:
    result: TaskRepositoryInspectionResult
    request: TaskRepositoryInspectionRequest | None = None

    def inspect_task_repository(self, request: TaskRepositoryInspectionRequest) -> TaskRepositoryInspectionResult:
        self.request = request
        return self.result


def test_delegates_staged_repository_inspection_to_port() -> None:
    request = TaskRepositoryInspectionRequest(working_directory=Path("/repo"))
    change_set = StagedChangeSet(
        repository_root="/repo",
        head_commit="abc123",
        branch="feature/task",
        staged_paths=("docs/idea.md",),
        staged_diff_digest="sha256:" + "0" * 64,
        staged_diff_summary="1 file changed",
    )
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(status=TaskRepositoryInspectionStatus.READY, change_set=change_set)
    )

    result = InspectTaskRepository(inspector).execute(request)

    assert result.ready
    assert result.change_set == change_set
    assert inspector.request == request


def test_returns_blockers_from_staged_repository_inspector() -> None:
    blocker = TaskRepositoryInspectionBlocker(code="no_staged_changes", summary="repository has no staged changes")
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(status=TaskRepositoryInspectionStatus.FAILED, blockers=(blocker,))
    )

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers == (blocker,)


def test_embedded_authorized_paths_are_part_of_the_task_inspection_request() -> None:
    request = TaskRepositoryInspectionRequest(
        working_directory=Path("/repo"),
        authorized_paths=(Path("src/example.py"), Path("tests/test_example.py")),
    )
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.FAILED,
            blockers=(
                TaskRepositoryInspectionBlocker(
                    code="staged_paths_outside_authorized_scope",
                    summary="staged changes include paths outside the authorized scope",
                    path="README.md",
                ),
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(request)

    assert inspector.request == request
    assert result.blockers[0].code == "staged_paths_outside_authorized_scope"


def test_blocks_when_ready_inspection_has_no_change_set() -> None:
    inspector = RecordingTaskInspector(TaskRepositoryInspectionResult(status=TaskRepositoryInspectionStatus.READY))

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers[0].code == "staged_change_set_unavailable"


def test_blocks_when_ready_inspection_does_not_identify_git_repository() -> None:
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.READY,
            change_set=StagedChangeSet(
                repository_root="",
                head_commit="abc123",
                branch="feature/task",
                staged_paths=("src/example.py",),
                staged_diff_digest="sha256:" + "0" * 64,
                staged_diff_summary="1 file changed",
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers[0].code == "git_repository_unavailable"


def test_blocks_when_ready_inspection_does_not_identify_head() -> None:
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.READY,
            change_set=StagedChangeSet(
                repository_root="/repo",
                head_commit="",
                branch="feature/task",
                staged_paths=("src/example.py",),
                staged_diff_digest="sha256:" + "0" * 64,
                staged_diff_summary="1 file changed",
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers[0].code == "git_head_unavailable"


def test_blocks_when_ready_inspection_reports_mutation() -> None:
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.READY,
            change_set=StagedChangeSet(
                repository_root="/repo",
                head_commit="abc123",
                branch="feature/task",
                staged_paths=("src/example.py",),
                staged_diff_digest="sha256:" + "0" * 64,
                staged_diff_summary="1 file changed",
                read_only=False,
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers[0].code == "staged_inspection_mutated_repository"


def test_blocks_when_ready_inspection_reports_unresolved_git_operation() -> None:
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.READY,
            change_set=StagedChangeSet(
                repository_root="/repo",
                head_commit="abc123",
                branch="feature/task",
                staged_paths=("src/example.py",),
                staged_diff_digest="sha256:" + "0" * 64,
                staged_diff_summary="1 file changed",
                operation_states=("merge",),
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers[0].code == "git_operation_in_progress"
    assert result.blockers[0].evidence == "merge"


def test_blocks_when_ready_inspection_has_no_staged_paths() -> None:
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.READY,
            change_set=StagedChangeSet(
                repository_root="/repo",
                head_commit="abc123",
                branch="feature/task",
                staged_paths=(),
                staged_diff_digest="sha256:" + "0" * 64,
                staged_diff_summary="0 files changed",
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers[0].code == "no_staged_changes"


def test_blocks_when_staged_paths_are_outside_authorized_scope() -> None:
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.READY,
            change_set=StagedChangeSet(
                repository_root="/repo",
                head_commit="abc123",
                branch="feature/task",
                staged_paths=("src/example.py", "README.md"),
                staged_diff_digest="sha256:" + "0" * 64,
                staged_diff_summary="2 files changed",
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(
        TaskRepositoryInspectionRequest(working_directory=Path("/repo"), authorized_paths=(Path("src/example.py"),))
    )

    assert not result.ready
    assert result.blockers[0].code == "staged_paths_outside_authorized_scope"
    assert result.blockers[0].path == "README.md"


def test_blocks_unsafe_staged_paths_before_authorized_scope_check() -> None:
    inspector = RecordingTaskInspector(
        TaskRepositoryInspectionResult(
            status=TaskRepositoryInspectionStatus.READY,
            change_set=StagedChangeSet(
                repository_root="/repo",
                head_commit="abc123",
                branch="feature/task",
                staged_paths=("../outside.py",),
                staged_diff_digest="sha256:" + "0" * 64,
                staged_diff_summary="1 file changed",
            ),
        )
    )

    result = InspectTaskRepository(inspector).execute(TaskRepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers[0].code == "unsafe_staged_path"
    assert result.blockers[0].path == "../outside.py"
