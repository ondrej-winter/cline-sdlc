"""JSON protocol for the adapter-owned Cline SDK runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionBlocker,
    ClineSessionDiagnosticReference,
    ClineSessionEvidence,
    ClineSessionEvidenceType,
    ClineSessionProcessStatus,
    ClineSessionResult,
    ClineSessionTerminalStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest

PROTOCOL_SCHEMA_VERSION = 1


@dataclass
class _OutputAccumulator:
    """Mutable parsing state for one SDK runner output stream."""

    stdout: str
    stderr: str
    exit_code: int | None
    events: list[ClineSessionEvidence] = field(default_factory=list)
    blockers: list[ClineSessionBlocker] = field(default_factory=list)
    diagnostics: list[ClineSessionDiagnosticReference] = field(default_factory=list)
    malformed_lines: list[str] = field(default_factory=list)
    terminal_status: ClineSessionTerminalStatus | None = None

    def invalid_result(self, *, code: str, summary: str) -> ClineSessionResult:
        """Return a fail-closed result preserving safe accumulated evidence."""
        return ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=self.exit_code,
            stdout=self.stdout,
            stderr=self.stderr,
            malformed_output_lines=tuple(self.malformed_lines),
            events=tuple(self.events),
            sdk_terminal_status=ClineSessionTerminalStatus.INVALID_OUTPUT,
            blockers=(*self.blockers, ClineSessionBlocker(code=code, summary=summary)),
            diagnostic_references=tuple(self.diagnostics),
        )

    def valid_result(self) -> ClineSessionResult:
        """Return a valid parsed result after exactly one terminal result."""
        return ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=self.exit_code,
            stdout=self.stdout,
            stderr=self.stderr,
            events=tuple(self.events),
            sdk_terminal_status=self.terminal_status,
            blockers=tuple(self.blockers),
            diagnostic_references=tuple(self.diagnostics),
        )


def serialize_runner_request(request: ClineSessionRequest) -> str:
    """Serialize one application session request for the Node SDK runner."""
    payload = {
        "schemaVersion": PROTOCOL_SCHEMA_VERSION,
        "role": request.session_role.value if request.session_role is not None else None,
        "instructions": request.instructions,
        "outcomeContract": request.outcome_contract,
        "timeoutSeconds": request.timeout_seconds,
        "workingDirectory": request.working_directory.as_posix(),
        "requiredSkills": list(request.required_skills),
        "artifactContext": [
            {
                "path": artifact.path,
                "digest": artifact.digest,
                "description": artifact.description,
            }
            for artifact in request.artifact_context
        ],
        "executionMode": request.execution_mode.value,
        "safeContext": list(request.safe_context),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def parse_runner_output(stdout: str, *, exit_code: int | None = 0, stderr: str = "") -> ClineSessionResult:
    """Parse JSONL emitted by the Node SDK runner into application DTOs.

    The runner protocol is fail-closed: malformed records, missing terminal
    results, duplicate terminal results, unsupported enum values, and unsafe
    paths all produce an ``INVALID_OUTPUT`` terminal status with a safe blocker.
    """
    accumulator = _OutputAccumulator(stdout=stdout, stderr=stderr, exit_code=exit_code)

    for line in stdout.splitlines():
        record = _parse_jsonl_record(line, accumulator)
        if record is None:
            continue
        try:
            invalid_result = _apply_protocol_record(record, accumulator)
            if invalid_result is not None:
                return invalid_result
        except (TypeError, ValueError) as err:
            return accumulator.invalid_result(code="invalid_protocol_record", summary=str(err))

    if accumulator.malformed_lines:
        return accumulator.invalid_result(
            code="malformed_protocol_json",
            summary="SDK runner emitted malformed JSON protocol output.",
        )
    if accumulator.terminal_status is None:
        return accumulator.invalid_result(
            code="missing_terminal_result",
            summary="SDK runner did not emit a terminal result.",
        )

    return accumulator.valid_result()


def _parse_jsonl_record(line: str, accumulator: _OutputAccumulator) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        record = json.loads(stripped)
    except json.JSONDecodeError:
        accumulator.malformed_lines.append(stripped)
        return None
    if not isinstance(record, dict):
        accumulator.malformed_lines.append(stripped)
        return None
    return record


def _apply_protocol_record(record: dict[str, Any], accumulator: _OutputAccumulator) -> ClineSessionResult | None:
    record_type = _required_string(record, "type")
    if record_type == "event":
        accumulator.events.append(_parse_event(record))
        return None
    if record_type == "blocker":
        accumulator.blockers.append(_parse_blocker(record))
        return None
    if record_type == "diagnostic":
        accumulator.diagnostics.append(_parse_diagnostic(record))
        return None
    if record_type == "terminal_result":
        return _apply_terminal_result(record, accumulator)
    return accumulator.invalid_result(
        code="unknown_record_type",
        summary="SDK runner emitted an unsupported protocol record type.",
    )


def _apply_terminal_result(record: dict[str, Any], accumulator: _OutputAccumulator) -> ClineSessionResult | None:
    if accumulator.terminal_status is not None:
        return accumulator.invalid_result(
            code="duplicate_terminal_result",
            summary="SDK runner emitted more than one terminal result.",
        )
    accumulator.terminal_status = ClineSessionTerminalStatus(_required_string(record, "status"))
    return None


def _parse_event(record: dict[str, Any]) -> ClineSessionEvidence:
    return ClineSessionEvidence(
        evidence_type=ClineSessionEvidenceType(_required_string(record, "evidenceType")),
        summary=_required_string(record, "summary"),
        sdk_event_type=_optional_string(record, "sdkEventType"),
        paths=_string_tuple(record.get("paths", []), field_name="paths"),
    )


def _parse_blocker(record: dict[str, Any]) -> ClineSessionBlocker:
    return ClineSessionBlocker(
        code=_required_string(record, "code"),
        summary=_required_string(record, "summary"),
        evidence=_optional_string(record, "evidence"),
    )


def _parse_diagnostic(record: dict[str, Any]) -> ClineSessionDiagnosticReference:
    return ClineSessionDiagnosticReference(
        kind=_required_string(record, "kind"),
        value=_required_string(record, "value"),
        summary=_required_string(record, "summary"),
    )


def _required_string(record: dict[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value.strip():
        message = f"SDK runner protocol field {field_name!r} must be a non-empty string"
        raise ValueError(message)
    return value


def _optional_string(record: dict[str, Any], field_name: str) -> str | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        message = f"SDK runner protocol field {field_name!r} must be a non-empty string when present"
        raise ValueError(message)
    return value


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        message = f"SDK runner protocol field {field_name!r} must be a list of strings"
        raise TypeError(message)
    if not all(isinstance(item, str) for item in value):
        message = f"SDK runner protocol field {field_name!r} must contain only strings"
        raise TypeError(message)
    return tuple(value)
