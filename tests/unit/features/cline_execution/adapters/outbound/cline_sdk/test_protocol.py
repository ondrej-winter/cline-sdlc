"""Tests for the Cline SDK runner JSON protocol."""

from __future__ import annotations

import json
from pathlib import Path

from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk.protocol import (
    PROTOCOL_SCHEMA_VERSION,
    parse_runner_output,
    serialize_runner_request,
)
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionArtifactContext,
    ClineSessionExecutionMode,
    ClineSessionRequest,
    ClineSessionTerminalStatus,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole


def test_serialize_runner_request_includes_sdk_session_contract_fields() -> None:
    request = ClineSessionRequest(
        command=("node", "runner.mjs"),
        working_directory=Path("/repo"),
        timeout_seconds=45.0,
        session_role=SessionRole.IMPLEMENTATION,
        instructions="Implement the accepted slice.",
        outcome_contract="Return exactly one typed terminal result.",
        required_skills=("test-driven-development",),
        artifact_context=(
            ClineSessionArtifactContext(
                path="docs/plans/accepted-plan.md",
                digest="sha256:" + "a" * 64,
                description="accepted implementation plan",
            ),
        ),
        execution_mode=ClineSessionExecutionMode.WRITE_CAPABLE,
        safe_context=("slice=task-3",),
    )

    payload = json.loads(serialize_runner_request(request))

    assert payload == {
        "schemaVersion": PROTOCOL_SCHEMA_VERSION,
        "role": "implementation",
        "instructions": "Implement the accepted slice.",
        "outcomeContract": "Return exactly one typed terminal result.",
        "timeoutSeconds": 45.0,
        "workingDirectory": "/repo",
        "requiredSkills": ["test-driven-development"],
        "artifactContext": [
            {
                "path": "docs/plans/accepted-plan.md",
                "digest": "sha256:" + "a" * 64,
                "description": "accepted implementation plan",
            }
        ],
        "executionMode": "write_capable",
        "safeContext": ["slice=task-3"],
    }


def test_parse_runner_output_accepts_events_blockers_diagnostics_and_terminal_result() -> None:
    output = "\n".join(
        (
            json.dumps(
                {
                    "type": "event",
                    "evidenceType": "assistant_output",
                    "summary": "assistant produced safe progress output",
                    "sdkEventType": "assistant-text-delta",
                    "paths": ["src/cline_sdlc/__init__.py"],
                }
            ),
            json.dumps({"type": "blocker", "code": "sdk_notice", "summary": "SDK emitted a safe notice."}),
            json.dumps({"type": "diagnostic", "kind": "run", "value": "run-123", "summary": "SDK run identifier"}),
            json.dumps({"type": "terminal_result", "status": "completed"}),
        )
    )

    result = parse_runner_output(output, exit_code=0)

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.COMPLETED
    assert result.events[0].sdk_event_type == "assistant-text-delta"
    assert result.events[0].paths == ("src/cline_sdlc/__init__.py",)
    assert result.blockers[0].code == "sdk_notice"
    assert result.diagnostic_references[0].value == "run-123"
    assert result.malformed_output_lines == ()


def test_parse_runner_output_fails_closed_for_malformed_json() -> None:
    result = parse_runner_output("{not-json}\n", exit_code=0)

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.INVALID_OUTPUT
    assert result.blockers[-1].code == "malformed_protocol_json"
    assert result.malformed_output_lines == ("{not-json}",)


def test_parse_runner_output_fails_closed_for_missing_terminal_result() -> None:
    result = parse_runner_output(json.dumps({"type": "event", "evidenceType": "diagnostic", "summary": "observed"}))

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.INVALID_OUTPUT
    assert result.blockers[-1].code == "missing_terminal_result"


def test_parse_runner_output_fails_closed_for_duplicate_terminal_result() -> None:
    output = "\n".join(
        (
            json.dumps({"type": "terminal_result", "status": "completed"}),
            json.dumps({"type": "terminal_result", "status": "failed"}),
        )
    )

    result = parse_runner_output(output)

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.INVALID_OUTPUT
    assert result.blockers[-1].code == "duplicate_terminal_result"


def test_parse_runner_output_fails_closed_for_unknown_status() -> None:
    result = parse_runner_output(json.dumps({"type": "terminal_result", "status": "not-a-status"}))

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.INVALID_OUTPUT
    assert result.blockers[-1].code == "invalid_protocol_record"


def test_parse_runner_output_fails_closed_for_unsafe_event_paths() -> None:
    result = parse_runner_output(
        json.dumps(
            {
                "type": "event",
                "evidenceType": "file_change",
                "summary": "changed an unsafe path",
                "paths": ["../secret.txt"],
            }
        )
    )

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.INVALID_OUTPUT
    assert result.blockers[-1].code == "invalid_protocol_record"


def test_parse_runner_output_does_not_promote_unknown_sdk_events_to_reconciliation_evidence() -> None:
    output = "\n".join(
        (
            json.dumps(
                {
                    "type": "event",
                    "evidenceType": "diagnostic",
                    "summary": "unknown SDK event recorded as diagnostic only",
                    "sdkEventType": "future-sensitive-event",
                }
            ),
            json.dumps({"type": "terminal_result", "status": "completed"}),
        )
    )

    result = parse_runner_output(output)

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.COMPLETED
    assert result.events[0].evidence_type.value == "diagnostic"
    assert result.events[0].sdk_event_type == "future-sensitive-event"
