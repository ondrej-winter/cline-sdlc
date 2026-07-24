"""Coordinate bounded Cline session attempts without owning I/O adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionProcessStatus
from cline_sdlc.features.cline_execution.domain.outcome import SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptBlocker,
    SessionAttemptObservation,
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
    SessionRetryReason,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionResult
    from cline_sdlc.features.cline_execution.application.ports.session_runner import ClineSessionRunnerPort
    from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositorySnapshot
    from cline_sdlc.features.repository_coordination.application.ports.git import GitRepositoryInspectorPort


class RunSessionAttempts:
    """Run one Cline session and permit only the documented safe retry cases."""

    def __init__(self, *, runner: ClineSessionRunnerPort, repository_inspector: GitRepositoryInspectorPort) -> None:
        self._runner = runner
        self._repository_inspector = repository_inspector

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        """Return completed session evidence or a typed blocker without deciding commits."""
        observations: list[SessionAttemptObservation] = []
        attempt_number = 1
        while attempt_number <= request.max_attempts:
            before_result = self._repository_inspector.inspect(request.repository_request)
            if before_result.snapshot is None:
                return _blocked(
                    observations,
                    code="repository_pre_session_unavailable",
                    summary="repository state must be observable before starting a session",
                )

            session_result = self._runner.run(request.session_request)
            after_result = self._repository_inspector.inspect(request.repository_request)
            after_snapshot = after_result.snapshot
            retry_reason = _retry_reason(
                request=request,
                session_result=session_result,
                before_snapshot=before_result.snapshot,
                after_snapshot=after_snapshot,
            )
            observation = SessionAttemptObservation(
                attempt_number=attempt_number,
                before_snapshot=before_result.snapshot,
                session_result=session_result,
                after_snapshot=after_snapshot,
                retry_reason=retry_reason,
            )
            observations.append(observation)

            if session_result.has_exactly_one_terminal_outcome:
                return _result_for_terminal_outcome(observations, session_result)
            if retry_reason is None:
                return _blocked(
                    observations,
                    code="session_retry_not_safe",
                    summary="session did not produce one terminal outcome and retry safety could not be proven",
                )
            if attempt_number == request.max_attempts:
                return _failed(
                    observations,
                    code="session_retry_exhausted",
                    summary="bounded retry was exhausted before one terminal outcome was observed",
                )
            attempt_number += 1

        return _failed(observations, code="session_attempts_exhausted", summary="session attempts were exhausted")


def _result_for_terminal_outcome(
    observations: list[SessionAttemptObservation],
    session_result: ClineSessionResult,
) -> SessionAttemptResult:
    outcome = session_result.terminal_outcomes[0]
    if outcome.status is SessionStatus.COMPLETED:
        return SessionAttemptResult(
            status=SessionAttemptStatus.COMPLETED,
            attempts=tuple(observations),
            terminal_session_result=session_result,
            changed_paths=outcome.changed_paths,
        )
    status = SessionAttemptStatus.FAILED if outcome.status is SessionStatus.FAILED else SessionAttemptStatus.BLOCKED
    return SessionAttemptResult(
        status=status,
        attempts=tuple(observations),
        terminal_session_result=session_result,
        blocker=SessionAttemptBlocker(
            code=f"session_{outcome.status.value}",
            summary=outcome.reason,
        ),
        changed_paths=outcome.changed_paths,
    )


def _retry_reason(
    *,
    request: SessionAttemptRequest,
    session_result: ClineSessionResult,
    before_snapshot: RepositorySnapshot,
    after_snapshot: RepositorySnapshot | None,
) -> SessionRetryReason | None:
    if _retry_is_unsafe(session_result, before_snapshot, after_snapshot):
        return None
    if session_result.malformed_output_lines:
        return SessionRetryReason.PROTOCOL_OUTPUT
    if session_result.process_status is ClineSessionProcessStatus.EXITED:
        if session_result.exit_code in request.transient_startup_exit_codes and not session_result.stdout.strip():
            return SessionRetryReason.TRANSIENT_STARTUP
        return SessionRetryReason.PROTOCOL_OUTPUT
    return None


def _retry_is_unsafe(
    session_result: ClineSessionResult,
    before_snapshot: RepositorySnapshot,
    after_snapshot: RepositorySnapshot | None,
) -> bool:
    return (
        after_snapshot is None
        or not _repository_unchanged(before_snapshot, after_snapshot)
        or session_result.timed_out
        or bool(session_result.terminal_outcomes)
    )


def _repository_unchanged(before_snapshot: RepositorySnapshot, after_snapshot: RepositorySnapshot) -> bool:
    return (
        before_snapshot.head_commit == after_snapshot.head_commit
        and before_snapshot.dirty_paths == after_snapshot.dirty_paths
        and before_snapshot.operation_states == after_snapshot.operation_states
        and before_snapshot.nested_repository_paths == after_snapshot.nested_repository_paths
    )


def _blocked(observations: list[SessionAttemptObservation], *, code: str, summary: str) -> SessionAttemptResult:
    return SessionAttemptResult(
        status=SessionAttemptStatus.BLOCKED,
        attempts=tuple(observations),
        blocker=SessionAttemptBlocker(code=code, summary=summary),
    )


def _failed(observations: list[SessionAttemptObservation], *, code: str, summary: str) -> SessionAttemptResult:
    return SessionAttemptResult(
        status=SessionAttemptStatus.FAILED,
        attempts=tuple(observations),
        blocker=SessionAttemptBlocker(code=code, summary=summary),
    )
