"""Coordinate one fresh read-only initial implementation-plan review."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanInspectionRequest,
    AuthoredPlanValidationRequest,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.plan_review import PlanReviewProgressRequest
from cline_sdlc.features.artifact_lifecycle.domain.findings import PlanReviewReadiness
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import (
    PlanReviewBlocker,
    PlanReviewRequest,
    PlanReviewResult,
    PlanReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
)

if TYPE_CHECKING:
    from datetime import datetime

    from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import AuthoredPlanValidationResult
    from cline_sdlc.features.artifact_lifecycle.application.dtos.plan_review import PlanReviewProgressResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import SessionAttemptResult


class AuthoredPlanContentPort(Protocol):
    """Boundary for reading plan and specification content before review."""

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        """Return strict content and parsed initial plan state."""


class AuthoredPlanValidatorPort(Protocol):
    """Published artifact-lifecycle boundary for initial plan validation."""

    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        """Return structural and digest validation evidence."""


class SessionAttemptsPort(Protocol):
    """Published lifecycle boundary for bounded fresh Cline sessions."""

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        """Return typed process, repository, and outcome evidence."""


class PlanReviewProgressPort(Protocol):
    """Published artifact boundary for orchestrator-owned progress updates."""

    def execute(self, request: PlanReviewProgressRequest) -> PlanReviewProgressResult:
        """Persist findings and review state without changing material content."""


class ClockPort(Protocol):
    """Application boundary for deterministic UTC timestamps."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC timestamp."""


class ReviewPlan:
    """Validate, independently review, and reconcile one initial plan revision."""

    def __init__(
        self,
        *,
        content_reader: AuthoredPlanContentPort,
        plan_validator: AuthoredPlanValidatorPort,
        session_attempts: SessionAttemptsPort,
        progress_writer: PlanReviewProgressPort,
        clock: ClockPort,
    ) -> None:
        self._content_reader = content_reader
        self._plan_validator = plan_validator
        self._session_attempts = session_attempts
        self._progress_writer = progress_writer
        self._clock = clock

    def execute(self, request: PlanReviewRequest) -> PlanReviewResult:
        """Return ready only after read-only evidence and progress reconciliation agree."""
        content_result = self._validated_content(request)
        if isinstance(content_result, PlanReviewResult):
            return content_result

        session_result = self._session_attempts.execute(_session_request(request))
        session_failure = _session_failure(session_result)
        if session_failure is not None:
            return session_failure
        outcome_result = _review_outcome(request, session_result)
        if isinstance(outcome_result, PlanReviewResult):
            return outcome_result
        content_failure = self._validate_unchanged_content(request, expected=content_result)
        if content_failure is not None:
            return content_failure

        progress_result = self._progress_writer.execute(
            PlanReviewProgressRequest(
                plan_path=request.plan_path,
                findings=outcome_result.findings,
                readiness=outcome_result.review_readiness,
                updated_at=self._clock.now(),
            )
        )
        if not progress_result.updated:
            return _blocked(
                "plan_review_progress_update_failed",
                "validated review evidence could not be applied without changing plan material",
                "; ".join(progress_result.blockers),
            )
        status = (
            PlanReviewStatus.READY
            if outcome_result.review_readiness is PlanReviewReadiness.READY
            else PlanReviewStatus.CHANGES_REQUIRED
        )
        return PlanReviewResult(
            status=status,
            readiness=outcome_result.review_readiness,
            findings=outcome_result.findings,
            output_paths=(request.plan_path,),
            material_digest=progress_result.material_digest,
        )

    def _validated_content(self, request: PlanReviewRequest) -> AuthoredPlanValidationRequest | PlanReviewResult:
        specification_path = Path(request.invocation.source.value).as_posix()
        try:
            content = self._content_reader.read(
                AuthoredPlanInspectionRequest(specification_path=specification_path, plan_path=request.plan_path)
            )
        except (OSError, UnicodeError, ValueError) as err:
            return _blocked("plan_review_content_unavailable", "plan review input could not be read safely", str(err))
        validation = self._plan_validator.execute(content)
        if not validation.valid:
            evidence = "; ".join(blocker.evidence or blocker.code for blocker in validation.blockers)
            return _blocked("plan_review_input_invalid", "plan must pass initial validation before review", evidence)
        return content

    def _validate_unchanged_content(
        self,
        request: PlanReviewRequest,
        *,
        expected: AuthoredPlanValidationRequest,
    ) -> PlanReviewResult | None:
        observed = self._validated_content(request)
        if isinstance(observed, PlanReviewResult):
            return observed
        if observed != expected:
            return _blocked(
                "reviewer_write_observed",
                "read-only plan reviewer changed review input content",
            )
        return None


def _session_request(request: PlanReviewRequest) -> SessionAttemptRequest:
    return SessionAttemptRequest(
        session_request=ClineSessionRequest(
            command=(request.invocation.cline_command, "--json", "--task", _prompt(request)),
            working_directory=request.preflight_request.repository_request.working_directory,
            timeout_seconds=request.invocation.timeout_seconds,
        ),
        repository_request=request.preflight_request.repository_request,
    )


def _prompt(request: PlanReviewRequest) -> str:
    specification_path = Path(request.invocation.source.value).as_posix()
    return "\n".join(
        (
            "Use the review-implementation-plan skill for one independent initial review.",
            "This is a fresh read-only context. Do not modify any repository file.",
            "Evaluate the plan against the accepted specification and repository rules.",
            "Do not confirm an author conclusion or use author private reasoning.",
            "Return every finding as a complete record with stable ID, severity, status, summary, evidence,",
            "required_correction, affected_sections, and disposition, plus review_readiness.",
            f"Accepted specification: {specification_path}",
            f"Proposed implementation plan: {request.plan_path}",
        )
    )


def _session_failure(session_result: SessionAttemptResult) -> PlanReviewResult | None:
    if session_result.status is SessionAttemptStatus.COMPLETED and session_result.terminal_session_result is not None:
        return None
    blocker = session_result.blocker
    status = (
        PlanReviewStatus.BLOCKED if session_result.status is SessionAttemptStatus.BLOCKED else PlanReviewStatus.FAILED
    )
    return PlanReviewResult(
        status=status,
        blocker=PlanReviewBlocker(
            code=blocker.code if blocker is not None else "plan_reviewer_session_failed",
            summary=blocker.summary if blocker is not None else "plan reviewer session did not complete",
        ),
    )


def _review_outcome(request: PlanReviewRequest, session_result: SessionAttemptResult):  # type: ignore[no-untyped-def]
    terminal = session_result.terminal_session_result
    if terminal is None or len(terminal.terminal_outcomes) != 1:
        return _blocked("plan_review_outcome_unavailable", "initial review requires one typed terminal outcome")
    outcome = terminal.terminal_outcomes[0]
    if outcome.session_role is not SessionRole.PLAN_REVIEWER:
        return _blocked("unexpected_session_role", "initial review must use a plan_reviewer session")
    if outcome.artifact_paths not in {(), (request.plan_path,)}:
        return _blocked("unexpected_review_artifact", "reviewer may identify only the selected plan artifact")
    if _reviewer_changed_repository(session_result):
        return _blocked("reviewer_write_observed", "read-only plan reviewer changed repository state")
    if outcome.review_readiness is None:
        return _blocked("review_readiness_missing", "plan reviewer must report validated readiness")
    return outcome


def _reviewer_changed_repository(session_result: SessionAttemptResult) -> bool:
    if session_result.changed_paths:
        return True
    for attempt in session_result.attempts:
        after = attempt.after_snapshot
        before = attempt.before_snapshot
        if after is None:
            return True
        if after != before:
            return True
    return False


def _blocked(code: str, summary: str, evidence: str | None = None) -> PlanReviewResult:
    return PlanReviewResult(
        status=PlanReviewStatus.BLOCKED,
        blocker=PlanReviewBlocker(code=code, summary=summary, evidence=evidence),
    )
