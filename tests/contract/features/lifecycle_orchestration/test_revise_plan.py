"""Contract tests for one fresh material plan revision session."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanBlocker,
    AuthoredPlanInspectionRequest,
    AuthoredPlanValidationRequest,
    AuthoredPlanValidationResult,
)
from cline_sdlc.features.artifact_lifecycle.domain.findings import Finding, FindingSeverity, FindingStatus
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import (
    PlanPhase,
    PlanState,
    ReviewReadiness,
)
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_revision import (
    PlanRevisionRequest,
    PlanRevisionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.revise_plan import RevisePlan
from tests.contract.features.lifecycle_orchestration.test_plan_review import plan_review_request

NOW = datetime(2026, 7, 25, tzinfo=UTC)


@dataclass
class RecordingAttempts:
    result: SessionAttemptResult
    requests: list[SessionAttemptRequest]

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingReader:
    result: AuthoredPlanValidationRequest
    requests: list[AuthoredPlanInspectionRequest]

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingValidator:
    result: AuthoredPlanValidationResult
    requests: list[AuthoredPlanValidationRequest]

    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        self.requests.append(request)
        return self.result


def test_revision_uses_fresh_author_context_and_validates_prior_state() -> None:
    prior_state = _state(revision=1)
    revised_content = _content(replace(prior_state, plan_revision=2, material_digest=_digest("2")))
    attempts = RecordingAttempts(_completed_attempt(), [])
    reader = RecordingReader(revised_content, [])
    validator = RecordingValidator(_validation(valid=True), [])

    result = RevisePlan(
        content_reader=reader,
        plan_validator=validator,
        session_attempts=attempts,
    ).execute(_request(prior_state))

    assert result.status is PlanRevisionStatus.COMPLETED
    assert result.plan_state == revised_content.plan_state
    prompt = attempts.requests[0].session_request.command[3]
    assert "planning-and-task-breakdown" in prompt
    assert "fresh author context" in prompt
    assert "PLAN-001" in prompt
    assert "increment plan_revision exactly once" in prompt
    assert validator.requests == [replace(revised_content, previous_plan_state=prior_state)]


def test_revision_blocks_wrong_role_or_status_before_content_read() -> None:
    reader = RecordingReader(_content(_state(revision=2)), [])
    attempts = RecordingAttempts(
        _completed_attempt(role=SessionRole.IMPLEMENTATION, status=SessionStatus.FAILED),
        [],
    )

    result = _reviser(attempts=attempts, reader=reader).execute(_request(_state(revision=1)))

    assert result.status is PlanRevisionStatus.BLOCKED
    assert result.blocker_code == "unexpected_revision_outcome"
    assert reader.requests == []


def test_revision_blocks_mismatched_finding_ids_before_content_read() -> None:
    reader = RecordingReader(_content(_state(revision=2)), [])
    attempts = RecordingAttempts(_completed_attempt(finding_ids=("PLAN-002",)), [])

    result = _reviser(attempts=attempts, reader=reader).execute(_request(_state(revision=1)))

    assert result.status is PlanRevisionStatus.BLOCKED
    assert result.blocker_code == "finding_traceability_mismatch"
    assert reader.requests == []


def test_revision_blocks_unexpected_changed_paths_before_content_read() -> None:
    reader = RecordingReader(_content(_state(revision=2)), [])
    attempts = RecordingAttempts(
        _completed_attempt(changed_paths=("docs/plans/example-plan.md", "README.md")),
        [],
    )

    result = _reviser(attempts=attempts, reader=reader).execute(_request(_state(revision=1)))

    assert result.status is PlanRevisionStatus.BLOCKED
    assert result.blocker_code == "revised_plan_not_verified"
    assert reader.requests == []


def test_invalid_revised_plan_returns_validation_evidence() -> None:
    validator = RecordingValidator(
        _validation(
            valid=False,
            blockers=(
                AuthoredPlanBlocker(
                    code="material_digest_unchanged",
                    summary="material digest did not change",
                    evidence="stored material digest matches the prior revision",
                ),
            ),
        ),
        [],
    )

    result = _reviser(validator=validator).execute(_request(_state(revision=1)))

    assert result.status is PlanRevisionStatus.BLOCKED
    assert result.blocker_code == "revised_plan_invalid"
    assert result.blocker_summary == "stored material digest matches the prior revision"


def test_failed_session_starts_no_content_read() -> None:
    reader = RecordingReader(_content(_state(revision=2)), [])
    attempts = RecordingAttempts(SessionAttemptResult(status=SessionAttemptStatus.FAILED, attempts=()), [])

    result = _reviser(attempts=attempts, reader=reader).execute(_request(_state(revision=1)))

    assert result.status is PlanRevisionStatus.FAILED
    assert reader.requests == []


def _reviser(
    *,
    attempts: RecordingAttempts | None = None,
    reader: RecordingReader | None = None,
    validator: RecordingValidator | None = None,
) -> RevisePlan:
    return RevisePlan(
        content_reader=reader or RecordingReader(_content(_state(revision=2)), []),
        plan_validator=validator or RecordingValidator(_validation(valid=True), []),
        session_attempts=attempts or RecordingAttempts(_completed_attempt(), []),
    )


def _request(prior_state: PlanState) -> PlanRevisionRequest:
    return PlanRevisionRequest(
        review_request=plan_review_request(),
        prior_state=prior_state,
        findings=(_finding(),),
    )


def _completed_attempt(
    *,
    role: SessionRole = SessionRole.PLAN_AUTHOR,
    status: SessionStatus = SessionStatus.COMPLETED,
    finding_ids: tuple[str, ...] = ("PLAN-001",),
    changed_paths: tuple[str, ...] = ("docs/plans/example-plan.md",),
) -> SessionAttemptResult:
    outcome = SessionOutcome(
        session_role=role,
        status=status,
        reason="plan revised",
        artifact_paths=("docs/plans/example-plan.md",),
        finding_ids=finding_ids,
    )
    session = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(outcome,),
    )
    return SessionAttemptResult(
        status=SessionAttemptStatus.COMPLETED,
        attempts=(),
        terminal_session_result=session,
        changed_paths=changed_paths,
    )


def _content(state: PlanState) -> AuthoredPlanValidationRequest:
    return AuthoredPlanValidationRequest(
        specification_path="docs/specs/example-spec.md",
        specification_content=b"specification",
        plan_path="docs/plans/example-plan.md",
        plan_content=b"revised plan",
        plan_state=state,
    )


def _validation(
    *,
    valid: bool,
    blockers: tuple[AuthoredPlanBlocker, ...] = (),
) -> AuthoredPlanValidationResult:
    return AuthoredPlanValidationResult(
        valid=valid,
        plan_path="docs/plans/example-plan.md",
        specification_digest=_digest("1") if valid else None,
        material_digest=_digest("2") if valid else None,
        blockers=blockers,
    )


def _state(*, revision: int) -> PlanState:
    return PlanState(
        work_id="example-work",
        phase=PlanPhase.REVIEWING,
        specification="docs/specs/example-spec.md",
        specification_digest=_digest("1"),
        plan_revision=revision,
        review_iteration=1,
        review_readiness=ReviewReadiness.CHANGES_REQUIRED,
        material_digest=_digest(str(revision)),
        created_at=NOW,
        updated_at=NOW,
    )


def _finding() -> Finding:
    return Finding(
        id="PLAN-001",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="Validation scope is incomplete.",
        evidence="The plan omits the broad quality gate.",
        required_correction="Add the broad quality gate.",
    )


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"
