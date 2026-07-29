"""Tests for the Cline SDK event diagnostic script."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionBlocker,
    ClineSessionDiagnosticReference,
    ClineSessionEvidence,
    ClineSessionEvidenceType,
    ClineSessionProcessStatus,
    ClineSessionResult,
    ClineSessionTerminalStatus,
)
from scripts import diagnose_cline_sdk_events

if TYPE_CHECKING:
    import pytest

USAGE_ERROR_EXIT_CODE = 2
INTERRUPTED_EXIT_CODE = 6


@dataclass(frozen=True)
class _FakeRunner:
    result: ClineSessionResult

    def run(self, _request: object) -> ClineSessionResult:
        return self.result


def test_diagnostic_prints_safe_normalized_event_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        stdout="raw stdout should not be printed",
        stderr="raw stderr should not be printed",
        sdk_terminal_status=ClineSessionTerminalStatus.COMPLETED,
        events=(
            ClineSessionEvidence(
                evidence_type=ClineSessionEvidenceType.ASSISTANT_OUTPUT,
                summary="safe assistant output observed",
                sdk_event_type="assistant-text-delta",
                paths=("src/cline_sdlc/__init__.py",),
            ),
        ),
        diagnostic_references=(
            ClineSessionDiagnosticReference(kind="run", value="run-123", summary="SDK run identifier"),
        ),
    )
    monkeypatch.setattr(diagnose_cline_sdk_events, "ClineSdkSessionRunner", lambda **_: _FakeRunner(result))

    exit_code = diagnose_cline_sdk_events.main(["--repository-root", ".", "--safe-context", "slice=task-8"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["sdk_terminal_status"] == "completed"
    assert payload["events"] == [
        {
            "normalized_event_type": "assistant_output",
            "summary": "safe assistant output observed",
            "sdk_event_type": "assistant-text-delta",
            "paths": ["src/cline_sdlc/__init__.py"],
            "diagnostic_only": False,
        }
    ]
    assert payload["authoritative_lifecycle_evidence"] is False
    assert "raw stdout" not in captured.out
    assert "raw stderr" not in captured.out


def test_diagnostic_reports_unknown_sdk_events_as_diagnostic_observations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        sdk_terminal_status=ClineSessionTerminalStatus.COMPLETED,
        events=(
            ClineSessionEvidence(
                evidence_type=ClineSessionEvidenceType.DIAGNOSTIC,
                summary="unknown SDK event recorded as diagnostic only",
                sdk_event_type="future-sensitive-event",
            ),
        ),
    )
    monkeypatch.setattr(diagnose_cline_sdk_events, "ClineSdkSessionRunner", lambda **_: _FakeRunner(result))

    exit_code = diagnose_cline_sdk_events.main(["--repository-root", "."])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["unknown_sdk_event_observations"] == [
        {
            "normalized_event_type": "diagnostic",
            "summary": "unknown SDK event recorded as diagnostic only",
            "sdk_event_type": "future-sensitive-event",
            "paths": [],
            "diagnostic_only": True,
        }
    ]
    assert payload["authoritative_lifecycle_evidence"] is False


def test_diagnostic_returns_nonzero_for_structured_blocker(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=1,
        sdk_terminal_status=ClineSessionTerminalStatus.FAILED,
        blockers=(
            ClineSessionBlocker(
                code="missing_sdk_configuration",
                summary="Missing required Cline SDK runner environment variable.",
            ),
        ),
    )
    monkeypatch.setattr(diagnose_cline_sdk_events, "ClineSdkSessionRunner", lambda **_: _FakeRunner(result))

    exit_code = diagnose_cline_sdk_events.main(["--repository-root", "."])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["blockers"][0]["code"] == "missing_sdk_configuration"


def test_diagnostic_returns_interrupted_category_for_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.TIMED_OUT,
        exit_code=None,
        sdk_terminal_status=ClineSessionTerminalStatus.TIMED_OUT,
    )
    monkeypatch.setattr(diagnose_cline_sdk_events, "ClineSdkSessionRunner", lambda **_: _FakeRunner(result))

    exit_code = diagnose_cline_sdk_events.main(["--repository-root", "."])

    assert exit_code == INTERRUPTED_EXIT_CODE


def test_diagnostic_returns_usage_error_for_invalid_request(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = diagnose_cline_sdk_events.main(["--repository-root", ".", "--timeout-seconds", "0"])

    captured = capsys.readouterr()
    assert exit_code == USAGE_ERROR_EXIT_CODE
    assert "usage error:" in captured.err
