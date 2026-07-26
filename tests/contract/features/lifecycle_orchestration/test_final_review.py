"""Contract tests for fresh final review and remediation classification."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
    ApprovedRemediationScope,
    FinalReviewRequest,
    FinalReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import (
    FinalValidationResult,
    FinalValidationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptObservation,
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.final_review import RunFinalReview
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositorySnapshot,
)

_START = "a" * 40
_END = "b" * 40
_SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
_MATERIAL_DIGEST = f"sha256:{'2' * 64}"


@dataclass
class RecordingAttempts:
    result: SessionAttemptResult
    requests: list[SessionAttemptRequest]

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        return self.result


def test_clean_final_review_uses_one_fresh_read_only_session() -> None:
    attempts = RecordingAttempts(_completed_attempt(), [])

    result = RunFinalReview(session_attempts=attempts).execute(_request())

    assert result.status is FinalReviewStatus.CLEAN
    assert result.readiness is PlanReviewReadiness.READY
    assert result.findings == ()
    assert len(attempts.requests) == 1
    assert attempts.requests[0].max_attempts == 1
    prompt = attempts.requests[0].session_request.command[-1]
    assert "read-only" in prompt
    assert f"{_START}..{_END}" in prompt
    assert "uv run pytest" in prompt


def test_eligible_non_conformance_becomes_bounded_remediation() -> None:
    finding = _finding()
    result = RunFinalReview(session_attempts=RecordingAttempts(_completed_attempt((finding,)), [])).execute(_request())

    assert result.status is FinalReviewStatus.REMEDIATION_REQUIRED
    assert result.findings == (finding,)
    assert len(result.remediation_records) == 1
    record = result.remediation_records[0]
    assert record.finding_id == "FINAL-001"
    assert record.requirement == "Task 5.1 broad validation remains truthful."
    assert record.path_scope == ("src/cline_sdlc/final_validation.py", "tests/test_final_validation.py")
    assert record.correction == finding.required_correction
    assert record.verification == "uv run pytest tests/test_final_validation.py"
    assert record.attempt_count == 0


def test_reviewer_write_is_rejected() -> None:
    result = RunFinalReview(
        session_attempts=RecordingAttempts(_completed_attempt(dirty_after=("src/changed.py",)), [])
    ).execute(_request())

    assert result.status is FinalReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "reviewer_write_observed"


def test_non_final_finding_id_is_rejected() -> None:
    finding = replace(_finding(), id="PLAN-001")
    result = RunFinalReview(session_attempts=RecordingAttempts(_completed_attempt((finding,)), [])).execute(_request())

    assert result.status is FinalReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "invalid_final_finding_id"


def test_material_dependency_finding_blocks_without_approved_scope() -> None:
    finding = replace(
        _finding(),
        id="FINAL-002",
        summary="A new dependency is required.",
        evidence="The proposed implementation requires another package.",
        required_correction="Select and add a new dependency.",
        affected_sections=("Architecture and dependencies",),
    )
    result = RunFinalReview(session_attempts=RecordingAttempts(_completed_attempt((finding,)), [])).execute(_request())

    assert result.status is FinalReviewStatus.BLOCKED
    assert result.remediation_records == ()
    assert result.blocker is not None
    assert result.blocker.code == "remediation_scope_unavailable"


def test_digest_divergence_starts_no_final_reviewer() -> None:
    attempts = RecordingAttempts(_completed_attempt(), [])
    request = replace(_request(), material_digest=f"sha256:{'3' * 64}")

    result = RunFinalReview(session_attempts=attempts).execute(request)

    assert result.status is FinalReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "material_digest_diverged"
    assert attempts.requests == []


def test_request_rejects_incomplete_broad_evidence() -> None:
    request = _request()
    invalid_validation = replace(request.final_validation, evidence=())

    with pytest.raises(ValueError, match="passing broad-validation evidence"):
        replace(request, final_validation=invalid_validation)


def test_wrong_role_is_rejected() -> None:
    result = RunFinalReview(
        session_attempts=RecordingAttempts(_completed_attempt(role=SessionRole.PLAN_REVIEWER), [])
    ).execute(_request())

    assert result.status is FinalReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "unexpected_session_role"


def _request() -> FinalReviewRequest:
    approval = InvocationApproval(
        run_id="run-5.2",
        profile="balanced",
        starting_head=_START,
        approved_at=datetime(2026, 7, 26, 18, tzinfo=UTC),
        specification_digest=_SPECIFICATION_DIGEST,
        material_digest=_MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )
    evidence = ValidationEvidence(
        scope=ValidationScope.BROAD,
        command=ValidationCommand("uv", ("run", "pytest")),
        status=ValidationEvidenceStatus.PASSED,
        summary="broad tests passed",
        exit_code=0,
        recorded_at=datetime(2026, 7, 26, 18, 5, tzinfo=UTC),
    )
    return FinalReviewRequest(
        approval=approval,
        specification_path="docs/specs/example.md",
        specification_content="Accepted specification",
        specification_digest=_SPECIFICATION_DIGEST,
        plan_path="docs/plans/example.md",
        plan_content="Ready implementation plan",
        material_digest=_MATERIAL_DIGEST,
        repository_rules="Use uv and preserve hexagonal boundaries.",
        repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
        cline_command="cline",
        timeout_seconds=30,
        start_commit=_START,
        end_commit=_END,
        final_validation=FinalValidationResult(
            status=FinalValidationStatus.COMPLETED,
            run_id="run-5.2",
            commit_range=(_START, _END),
            evidence=(evidence,),
        ),
        remediation_scopes=(
            ApprovedRemediationScope(
                requirement="Task 5.1 broad validation remains truthful.",
                affected_section="Task 5.1 acceptance criteria",
                path_scope=("src/cline_sdlc/final_validation.py", "tests/test_final_validation.py"),
                verification="uv run pytest tests/test_final_validation.py",
            ),
        ),
    )


def _completed_attempt(
    findings: tuple[Finding, ...] = (),
    *,
    role: SessionRole = SessionRole.FINAL_REVIEWER,
    dirty_after: tuple[str, ...] = (),
) -> SessionAttemptResult:
    readiness = PlanReviewReadiness.CHANGES_REQUIRED if findings else PlanReviewReadiness.READY
    outcome = SessionOutcome(
        session_role=role,
        status=SessionStatus.COMPLETED,
        reason=readiness.value,
        artifact_paths=("docs/plans/example.md",),
        findings=findings,
        finding_ids=tuple(finding.id for finding in findings),
        review_readiness=readiness,
    )
    session = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(outcome,),
    )
    before = _snapshot()
    after = _snapshot(dirty_paths=dirty_after)
    return SessionAttemptResult(
        status=SessionAttemptStatus.COMPLETED,
        attempts=(SessionAttemptObservation(1, before, session, after),),
        terminal_session_result=session,
        changed_paths=dirty_after,
    )


def _finding() -> Finding:
    return Finding(
        id="FINAL-001",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="Broad validation evidence is not preserved correctly.",
        evidence="The result drops one required command.",
        required_correction="Preserve every broad command in final evidence.",
        affected_sections=("Task 5.1 acceptance criteria",),
    )


def _snapshot(*, dirty_paths: tuple[str, ...] = ()) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_root="/repo",
        head_commit=_END,
        branch="feature/final-review",
        dirty_paths=dirty_paths,
    )
