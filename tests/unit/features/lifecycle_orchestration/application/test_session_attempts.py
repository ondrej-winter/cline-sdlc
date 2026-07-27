"""Tests for bounded lifecycle session attempts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionRequest,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import (
    SessionBlocker,
    SessionOutcome,
    SessionRole,
    SessionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
    SessionRetryReason,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_session_attempts import RunSessionAttempts
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
    RepositoryInspectionStatus,
    RepositorySnapshot,
)

EXPECTED_RETRIED_ATTEMPTS = 2


@dataclass
class RecordingRunner:
    results: list[ClineSessionResult]
    requests: list[ClineSessionRequest]

    def run(self, request: ClineSessionRequest) -> ClineSessionResult:
        self.requests.append(request)
        return self.results.pop(0)


@dataclass
class RecordingRepositoryInspector:
    snapshots: list[RepositorySnapshot]
    requests: list[RepositoryInspectionRequest]

    def inspect(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        self.requests.append(request)
        return RepositoryInspectionResult(
            status=RepositoryInspectionStatus.READY,
            snapshot=self.snapshots.pop(0),
        )


def test_completed_session_returns_one_attempt_without_retry() -> None:
    runner = RecordingRunner(results=[_completed_result(changed_paths=("src/app.py",))], requests=[])
    inspector = RecordingRepositoryInspector(snapshots=[_snapshot(), _snapshot()], requests=[])

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.completed
    assert result.status is SessionAttemptStatus.COMPLETED
    assert len(result.attempts) == 1
    assert len(runner.requests) == 1
    assert result.changed_paths == ("src/app.py",)


def test_retries_protocol_output_failure_once_when_repository_is_unchanged() -> None:
    runner = RecordingRunner(
        results=[
            ClineSessionResult(
                process_status=ClineSessionProcessStatus.EXITED,
                exit_code=0,
                malformed_output_lines=("not-json",),
            ),
            _completed_result(),
        ],
        requests=[],
    )
    inspector = RecordingRepositoryInspector(
        snapshots=[_snapshot(), _snapshot(), _snapshot(), _snapshot()],
        requests=[],
    )

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.completed
    assert len(result.attempts) == EXPECTED_RETRIED_ATTEMPTS
    assert result.attempts[0].retry_reason is SessionRetryReason.PROTOCOL_OUTPUT
    assert len(runner.requests) == EXPECTED_RETRIED_ATTEMPTS


def test_retries_transient_startup_failure_once_when_repository_is_unchanged() -> None:
    runner = RecordingRunner(
        results=[
            ClineSessionResult(process_status=ClineSessionProcessStatus.EXITED, exit_code=1),
            _completed_result(),
        ],
        requests=[],
    )
    inspector = RecordingRepositoryInspector(
        snapshots=[_snapshot(), _snapshot(), _snapshot(), _snapshot()],
        requests=[],
    )

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.completed
    assert result.attempts[0].retry_reason is SessionRetryReason.TRANSIENT_STARTUP


def test_blocks_retry_when_repository_state_changes_after_protocol_failure() -> None:
    runner = RecordingRunner(
        results=[
            ClineSessionResult(
                process_status=ClineSessionProcessStatus.EXITED,
                exit_code=0,
                malformed_output_lines=("not-json",),
            )
        ],
        requests=[],
    )
    inspector = RecordingRepositoryInspector(snapshots=[_snapshot(), _snapshot(dirty_paths=("plan.md",))], requests=[])

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.status is SessionAttemptStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "session_retry_not_safe"
    assert len(runner.requests) == 1


def test_timeout_interrupts_without_retry_and_preserves_dirty_paths() -> None:
    runner = RecordingRunner(
        results=[ClineSessionResult(process_status=ClineSessionProcessStatus.TIMED_OUT, exit_code=None)],
        requests=[],
    )
    inspector = RecordingRepositoryInspector(
        snapshots=[_snapshot(), _snapshot(dirty_paths=("src/partial.py",))],
        requests=[],
    )

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.status is SessionAttemptStatus.INTERRUPTED
    assert result.blocker is not None
    assert result.blocker.code == "session_timed_out"
    assert result.changed_paths == ("src/partial.py",)
    assert len(runner.requests) == 1


def test_signal_interruption_stops_without_retry() -> None:
    runner = RecordingRunner(
        results=[ClineSessionResult(process_status=ClineSessionProcessStatus.INTERRUPTED, exit_code=None)],
        requests=[],
    )
    inspector = RecordingRepositoryInspector(snapshots=[_snapshot(), _snapshot()], requests=[])

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.status is SessionAttemptStatus.INTERRUPTED
    assert result.blocker is not None
    assert result.blocker.code == "session_interrupted"
    assert len(runner.requests) == 1


def test_approval_required_outcome_blocks_without_retry() -> None:
    runner = RecordingRunner(
        results=[
            ClineSessionResult(
                process_status=ClineSessionProcessStatus.EXITED,
                exit_code=0,
                terminal_outcomes=(
                    SessionOutcome(
                        session_role=SessionRole.IMPLEMENTATION,
                        status=SessionStatus.APPROVAL_REQUIRED,
                        reason="manual approval required",
                        blocker=_approval_blocker(),
                    ),
                ),
            )
        ],
        requests=[],
    )
    inspector = RecordingRepositoryInspector(snapshots=[_snapshot(), _snapshot()], requests=[])

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.status is SessionAttemptStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "session_approval_required"
    assert len(runner.requests) == 1


def test_exhausts_single_bounded_retry() -> None:
    runner = RecordingRunner(
        results=[
            ClineSessionResult(process_status=ClineSessionProcessStatus.EXITED, exit_code=0),
            ClineSessionResult(process_status=ClineSessionProcessStatus.EXITED, exit_code=0),
        ],
        requests=[],
    )
    inspector = RecordingRepositoryInspector(
        snapshots=[_snapshot(), _snapshot(), _snapshot(), _snapshot()],
        requests=[],
    )

    result = RunSessionAttempts(runner=runner, repository_inspector=inspector).execute(_request())

    assert result.status is SessionAttemptStatus.FAILED
    assert result.blocker is not None
    assert result.blocker.code == "session_retry_exhausted"
    assert result.blocker.evidence == (
        "attempt=1 process_status=exited exit_code=0 terminal_outcomes=0 "
        "malformed_output_lines=0 retry_reason=protocol_output; "
        "attempt=2 process_status=exited exit_code=0 terminal_outcomes=0 "
        "malformed_output_lines=0 retry_reason=protocol_output"
    )
    assert len(result.attempts) == EXPECTED_RETRIED_ATTEMPTS


def _request() -> SessionAttemptRequest:
    return SessionAttemptRequest(
        session_request=ClineSessionRequest(
            command=("cline", "--json"),
            working_directory=Path("/repo"),
            timeout_seconds=30,
        ),
        repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
    )


def _snapshot(*, dirty_paths: tuple[str, ...] = ()) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_root="/repo",
        head_commit="abc123",
        branch="feature/test",
        dirty_paths=dirty_paths,
    )


def _completed_result(*, changed_paths: tuple[str, ...] = ()) -> ClineSessionResult:
    return ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(
            SessionOutcome(
                session_role=SessionRole.IMPLEMENTATION,
                status=SessionStatus.COMPLETED,
                reason="slice completed",
                changed_paths=changed_paths,
            ),
        ),
    )


def _approval_blocker() -> SessionBlocker:
    return SessionBlocker(code="approval_required", summary="manual approval required", proposed_operation="git commit")
