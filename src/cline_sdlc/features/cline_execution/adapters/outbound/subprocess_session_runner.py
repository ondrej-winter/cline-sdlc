"""Subprocess-backed supervised Cline session runner."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import (
    SESSION_OUTCOME_SCHEMA_VERSION,
    SessionBlocker,
    SessionOutcome,
    SessionRole,
    SessionStatus,
    SessionValidationEvidence,
    SessionValidationResult,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest


class SubprocessClineSessionRunner:
    """Execute one explicit Cline argument array with a finite timeout."""

    def run(self, request: ClineSessionRequest) -> ClineSessionResult:
        """Run the subprocess and convert captured output into typed observations."""
        try:
            completed = subprocess.run(  # noqa: S603
                list(request.command),
                cwd=request.working_directory,
                capture_output=True,
                check=False,
                text=True,
                timeout=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired as err:
            return ClineSessionResult(
                process_status=ClineSessionProcessStatus.TIMED_OUT,
                exit_code=None,
                stdout=_timeout_output(err.stdout),
                stderr=_timeout_output(err.stderr),
            )

        parsed = _parse_terminal_outcomes(completed.stdout)
        return ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            terminal_outcomes=parsed.outcomes,
            malformed_output_lines=parsed.malformed_lines,
        )


def _timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


@dataclass(frozen=True)
class _ParsedOutcomes:
    outcomes: tuple[SessionOutcome, ...]
    malformed_lines: tuple[str, ...]


def _parse_terminal_outcomes(stdout: str) -> _ParsedOutcomes:
    outcomes: list[SessionOutcome] = []
    malformed_lines: list[str] = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines.append(line)
            continue
        for candidate in _candidate_outcomes(value):
            try:
                outcomes.append(_outcome_from_mapping(candidate))
            except TypeError, ValueError:
                malformed_lines.append(line)
    return _ParsedOutcomes(outcomes=tuple(outcomes), malformed_lines=tuple(malformed_lines))


def _candidate_outcomes(value: object) -> tuple[dict[str, object], ...]:
    if _is_terminal_outcome_mapping(value):
        return (value,)
    if not isinstance(value, dict):
        return ()

    candidates = (
        value.get("message"),
        value.get("content"),
        value.get("text"),
        value.get("data"),
        value.get("payload"),
    )
    outcomes: list[dict[str, object]] = []
    for candidate in candidates:
        if _is_terminal_outcome_mapping(candidate):
            outcomes.append(candidate)
        elif isinstance(candidate, str):
            parsed = _json_object_from_text(candidate)
            if _is_terminal_outcome_mapping(parsed):
                outcomes.append(parsed)
    return tuple(outcomes)


def _json_object_from_text(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def _is_terminal_outcome_mapping(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and value.get("schema_version") == SESSION_OUTCOME_SCHEMA_VERSION


def _outcome_from_mapping(value: dict[str, object]) -> SessionOutcome:
    return SessionOutcome(
        schema_version=_required_int(value, "schema_version"),
        session_role=SessionRole(_required_str(value, "session_role")),
        status=SessionStatus(_required_str(value, "status")),
        reason=_required_str(value, "reason"),
        artifact_paths=_string_tuple(value.get("artifact_paths")),
        changed_paths=_string_tuple(value.get("changed_paths")),
        validation=tuple(_validation_from_mapping(item) for item in _mapping_sequence(value.get("validation"))),
        finding_ids=_string_tuple(value.get("finding_ids")),
        blocker=_blocker_from_mapping(value.get("blocker")),
        retryable=bool(value.get("retryable", False)),
    )


def _validation_from_mapping(value: dict[str, object]) -> SessionValidationEvidence:
    exit_code = value.get("exit_code")
    if exit_code is not None and not isinstance(exit_code, int):
        message = "validation exit code must be an integer or null"
        raise TypeError(message)
    return SessionValidationEvidence(
        command=_required_str(value, "command"),
        result=SessionValidationResult(_required_str(value, "result")),
        exit_code=exit_code,
    )


def _blocker_from_mapping(value: object) -> SessionBlocker | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        message = "blocker must be an object or null"
        raise TypeError(message)
    proposed_operation = value.get("proposed_operation")
    return SessionBlocker(
        code=_required_str(value, "code"),
        summary=_required_str(value, "summary"),
        proposed_operation=_proposed_operation_text(proposed_operation),
    )


def _proposed_operation_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _mapping_sequence(value: object) -> tuple[dict[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        message = "expected a list of objects"
        raise TypeError(message)
    if not all(isinstance(item, dict) for item in value):
        message = "expected a list of objects"
        raise TypeError(message)
    return tuple(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        message = "expected a list of strings"
        raise TypeError(message)
    if not all(isinstance(item, str) for item in value):
        message = "expected a list of strings"
        raise TypeError(message)
    return tuple(value)


def _required_str(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        message = f"{key} must be a string"
        raise TypeError(message)
    return item


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        message = f"{key} must be an integer"
        raise TypeError(message)
    return item
