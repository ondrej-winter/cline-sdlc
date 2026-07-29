"""Tests for SDK-shaped Cline session application DTOs."""

from pathlib import Path

import pytest

from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionArtifactContext,
    ClineSessionBlocker,
    ClineSessionDiagnosticReference,
    ClineSessionEvidence,
    ClineSessionEvidenceType,
    ClineSessionExecutionMode,
    ClineSessionProcessStatus,
    ClineSessionRequest,
    ClineSessionResult,
    ClineSessionTerminalStatus,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole


def test_session_request_accepts_sdk_shaped_contract_without_exposing_sdk_types() -> None:
    request = ClineSessionRequest(
        command=("cline", "--json"),
        working_directory=Path.cwd(),
        timeout_seconds=30.0,
        session_role=SessionRole.IMPLEMENTATION,
        instructions="Implement only the accepted slice.",
        outcome_contract="Return exactly one typed implementation outcome.",
        required_skills=("test-driven-development",),
        artifact_context=(
            ClineSessionArtifactContext(
                path="docs/plans/accepted-plan.md",
                digest="sha256:" + "a" * 64,
                description="accepted implementation plan",
            ),
        ),
        execution_mode=ClineSessionExecutionMode.WRITE_CAPABLE,
        safe_context=("slice=task-2",),
    )

    assert request.session_role is SessionRole.IMPLEMENTATION
    assert request.required_skills == ("test-driven-development",)
    assert request.artifact_context[0].path == "docs/plans/accepted-plan.md"
    assert request.execution_mode is ClineSessionExecutionMode.WRITE_CAPABLE


def test_session_request_preserves_existing_subprocess_contract_defaults() -> None:
    request = ClineSessionRequest(command=("cline", "--json"), working_directory=Path.cwd(), timeout_seconds=5.0)

    assert request.command == ("cline", "--json")
    assert request.session_role is None
    assert request.instructions == ""
    assert request.required_skills == ()
    assert request.artifact_context == ()


@pytest.mark.parametrize("path", ["/absolute.md", "../escape.md", "docs/../escape.md", "docs\\escape.md", ""])
def test_session_artifact_context_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError, match=r"repository-relative POSIX paths|traversal|empty"):
        ClineSessionArtifactContext(path=path, digest="sha256:" + "a" * 64, description="unsafe")


def test_session_artifact_context_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError, match="sha256"):
        ClineSessionArtifactContext(path="docs/plan.md", digest="not-a-digest", description="plan")


def test_session_request_rejects_empty_sdk_contract_fields_when_role_is_set() -> None:
    with pytest.raises(ValueError, match="instructions"):
        ClineSessionRequest(
            command=("cline",),
            working_directory=Path.cwd(),
            timeout_seconds=5.0,
            session_role=SessionRole.IMPLEMENTATION,
            instructions=" ",
            outcome_contract="Return one outcome.",
        )

    with pytest.raises(ValueError, match="outcome contract"):
        ClineSessionRequest(
            command=("cline",),
            working_directory=Path.cwd(),
            timeout_seconds=5.0,
            session_role=SessionRole.IMPLEMENTATION,
            instructions="Implement the slice.",
            outcome_contract=" ",
        )


def test_session_result_carries_sdk_evidence_blockers_and_diagnostics() -> None:
    result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        sdk_terminal_status=ClineSessionTerminalStatus.COMPLETED,
        events=(
            ClineSessionEvidence(
                evidence_type=ClineSessionEvidenceType.ASSISTANT_OUTPUT,
                summary="assistant produced safe progress output",
                sdk_event_type="assistant-text-delta",
                paths=("src/cline_sdlc/__init__.py",),
            ),
        ),
        blockers=(ClineSessionBlocker(code="sdk_notice", summary="SDK emitted a safe notice."),),
        diagnostic_references=(
            ClineSessionDiagnosticReference(kind="run", value="run-123", summary="SDK run identifier"),
        ),
    )

    assert result.sdk_terminal_status is ClineSessionTerminalStatus.COMPLETED
    assert result.events[0].sdk_event_type == "assistant-text-delta"
    assert result.events[0].paths == ("src/cline_sdlc/__init__.py",)
    assert result.blockers[0].code == "sdk_notice"
    assert result.diagnostic_references[0].value == "run-123"


def test_session_evidence_rejects_unsafe_paths_and_empty_required_fields() -> None:
    with pytest.raises(ValueError, match="summary"):
        ClineSessionEvidence(evidence_type=ClineSessionEvidenceType.DIAGNOSTIC, summary=" ")

    with pytest.raises(ValueError, match="paths"):
        ClineSessionEvidence(
            evidence_type=ClineSessionEvidenceType.FILE_CHANGE,
            summary="file changed",
            paths=("../secret.txt",),
        )


def test_diagnostic_reference_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="diagnostic reference"):
        ClineSessionDiagnosticReference(kind="run", value=" ", summary="missing value")


def test_session_blocker_requires_safe_non_empty_code_and_summary() -> None:
    with pytest.raises(ValueError, match="blocker code"):
        ClineSessionBlocker(code=" ", summary="blocked")

    with pytest.raises(ValueError, match="blocker summary"):
        ClineSessionBlocker(code="blocked", summary=" ")
