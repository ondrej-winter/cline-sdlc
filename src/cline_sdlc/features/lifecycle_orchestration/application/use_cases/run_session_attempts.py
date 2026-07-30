"""Coordinate bounded Cline session attempts without owning I/O adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionProcessStatus
from cline_sdlc.features.cline_execution.domain.outcome import SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptBlocker,
    SessionAttemptObservation,
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptSdkEvidence,
    SessionAttemptStatus,
    SessionRetryReason,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionResult
    from cline_sdlc.features.cline_execution.application.ports.session_runner import ClineSessionRunnerPort
    from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositorySnapshot
    from cline_sdlc.features.repository_coordination.application.ports.git import GitRepositoryInspectorPort


@dataclass(frozen=True)
class _AttemptControl:
    """Bounded retry state for one observed session attempt."""

    retry_reason: SessionRetryReason | None
    attempt_number: int
    max_attempts: int


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
                sdk_evidence=_sdk_evidence(session_result),
            )
            observations.append(observation)

            attempt_result = _attempt_result_after_session(
                observations=observations,
                session_result=session_result,
                after_snapshot=after_snapshot,
                control=_AttemptControl(
                    retry_reason=retry_reason,
                    attempt_number=attempt_number,
                    max_attempts=request.max_attempts,
                ),
            )
            if attempt_result is not None:
                return attempt_result
            attempt_number += 1

        return _failed(observations, code="session_attempts_exhausted", summary="session attempts were exhausted")


def _attempt_result_after_session(
    *,
    observations: list[SessionAttemptObservation],
    session_result: ClineSessionResult,
    after_snapshot: RepositorySnapshot | None,
    control: _AttemptControl,
) -> SessionAttemptResult | None:
    if session_result.interrupted or session_result.timed_out:
        return SessionAttemptResult(
            status=SessionAttemptStatus.INTERRUPTED,
            attempts=tuple(observations),
            blocker=SessionAttemptBlocker(
                code="session_interrupted" if session_result.interrupted else "session_timed_out",
                summary="the active session was interrupted safely",
            ),
            changed_paths=after_snapshot.dirty_paths if after_snapshot is not None else (),
        )
    if session_result.has_exactly_one_terminal_outcome:
        return _result_for_terminal_outcome(observations, session_result)
    sdk_blocker = _sdk_blocker_without_terminal_outcome(session_result)
    if sdk_blocker is not None:
        return _blocked_from_session_blocker(observations, sdk_blocker)
    if control.retry_reason is None:
        return _blocked(
            observations,
            code="session_retry_not_safe",
            summary="session did not produce one terminal outcome and retry safety could not be proven",
        )
    if control.attempt_number == control.max_attempts:
        return _failed(
            observations,
            code="session_retry_exhausted",
            summary="bounded retry was exhausted before one terminal outcome was observed",
        )
    return None


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


def _sdk_evidence(session_result: ClineSessionResult) -> SessionAttemptSdkEvidence:
    return SessionAttemptSdkEvidence(
        sdk_terminal_status=(
            session_result.sdk_terminal_status.value if session_result.sdk_terminal_status is not None else None
        ),
        event_count=len(session_result.events),
        blocker_codes=tuple(blocker.code for blocker in session_result.blockers),
        diagnostic_references=tuple(
            f"{reference.kind}:{reference.value}" for reference in session_result.diagnostic_references
        ),
    )


def _sdk_blocker_without_terminal_outcome(session_result: ClineSessionResult) -> SessionAttemptBlocker | None:
    """Return an SDK blocker only when lifecycle terminal outcomes are absent."""
    if session_result.terminal_outcomes or not session_result.blockers:
        return None
    blocker = session_result.blockers[0]
    return SessionAttemptBlocker(
        code=f"sdk_{blocker.code}",
        summary=blocker.summary,
        evidence=blocker.evidence,
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
        blocker=SessionAttemptBlocker(code=code, summary=summary, evidence=_attempt_evidence(observations)),
    )


def _blocked_from_session_blocker(
    observations: list[SessionAttemptObservation],
    blocker: SessionAttemptBlocker,
) -> SessionAttemptResult:
    return _blocked(observations, code=blocker.code, summary=blocker.summary)


def _failed(observations: list[SessionAttemptObservation], *, code: str, summary: str) -> SessionAttemptResult:
    return SessionAttemptResult(
        status=SessionAttemptStatus.FAILED,
        attempts=tuple(observations),
        blocker=SessionAttemptBlocker(code=code, summary=summary, evidence=_attempt_evidence(observations)),
    )


def _attempt_evidence(observations: list[SessionAttemptObservation]) -> str | None:
    if not observations:
        return None
    return "; ".join(_observation_evidence(observation) for observation in observations)


def _observation_evidence(observation: SessionAttemptObservation) -> str:
    result = observation.session_result
    retry_reason = observation.retry_reason.value if observation.retry_reason is not None else "none"
    diagnostic = _process_diagnostic(result)
    diagnostic_suffix = f" diagnostic={diagnostic}" if diagnostic else ""
    return (
        f"attempt={observation.attempt_number} "
        f"process_status={result.process_status.value} "
        f"exit_code={result.exit_code} "
        f"terminal_outcomes={len(result.terminal_outcomes)} "
        f"malformed_output_lines={len(result.malformed_output_lines)} "
        f"retry_reason={retry_reason}"
        f"{diagnostic_suffix}"
    )


def _process_diagnostic(result: ClineSessionResult) -> str | None:
    diagnostic = _first_error_message(result.stdout) or _first_non_empty_line(result.stderr)
    if diagnostic is None:
        return None
    return diagnostic[:240]


def _first_error_message(stdout: str) -> str | None:
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        message = value.get("message")
        if isinstance(message, str) and value.get("type") == "error":
            return message
        text = value.get("text")
        if isinstance(text, str) and value.get("type") == "run_result":
            return text
    return None


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None
