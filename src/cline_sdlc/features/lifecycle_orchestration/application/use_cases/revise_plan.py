"""Coordinate one fresh bounded material plan revision."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import AuthoredPlanInspectionRequest
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_revision import (
    PlanRevisionRequest,
    PlanRevisionResult,
    PlanRevisionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
        AuthoredPlanValidationRequest,
        AuthoredPlanValidationResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import SessionAttemptResult


class AuthoredPlanContentPort(Protocol):
    """Boundary for reading revised plan content."""

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        """Return strict specification and plan content."""


class AuthoredPlanValidatorPort(Protocol):
    """Boundary for independent material revision validation."""

    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        """Return structural, identity, revision, and digest evidence."""


class SessionAttemptsPort(Protocol):
    """Boundary for one bounded fresh author session."""

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        """Return typed process and repository observations."""


class RevisePlan:
    """Run and independently validate one material plan correction."""

    def __init__(
        self,
        *,
        content_reader: AuthoredPlanContentPort,
        plan_validator: AuthoredPlanValidatorPort,
        session_attempts: SessionAttemptsPort,
    ) -> None:
        self._content_reader = content_reader
        self._plan_validator = plan_validator
        self._session_attempts = session_attempts

    def execute(self, request: PlanRevisionRequest) -> PlanRevisionResult:
        """Return completion only for a verified one-step material revision."""
        session_result = self._session_attempts.execute(_session_request(request))
        if session_result.status is not SessionAttemptStatus.COMPLETED:
            return _failure(session_result)
        outcome_failure = _validate_outcome(request, session_result)
        if outcome_failure is not None:
            return outcome_failure
        try:
            content = self._content_reader.read(
                AuthoredPlanInspectionRequest(
                    specification_path=Path(request.review_request.invocation.source.value).as_posix(),
                    plan_path=request.review_request.plan_path,
                )
            )
        except (OSError, UnicodeError, ValueError) as err:
            return _blocked("revised_plan_content_unavailable", str(err))
        validation = self._plan_validator.execute(replace(content, previous_plan_state=request.prior_state))
        if not validation.valid:
            evidence = "; ".join(blocker.evidence or blocker.code for blocker in validation.blockers)
            return _blocked("revised_plan_invalid", evidence)
        return PlanRevisionResult(
            status=PlanRevisionStatus.COMPLETED,
            plan_state=content.plan_state,
            output_paths=(request.review_request.plan_path,),
        )


def _session_request(request: PlanRevisionRequest) -> SessionAttemptRequest:
    review_request = request.review_request
    return SessionAttemptRequest(
        session_request=ClineSessionRequest(
            command=(review_request.invocation.cline_command, "--json", _prompt(request)),
            working_directory=review_request.preflight_request.repository_request.working_directory,
            timeout_seconds=review_request.invocation.timeout_seconds,
        ),
        repository_request=review_request.preflight_request.repository_request,
    )


def _prompt(request: PlanRevisionRequest) -> str:
    finding_lines = tuple(
        f"- {finding.id}: {finding.required_correction} (evidence: {finding.evidence})" for finding in request.findings
    )
    return "\n".join(
        (
            "Use the planning-and-task-breakdown skill to revise the implementation plan only.",
            "This is a fresh author context. Do not review or implement the plan.",
            "Address every listed finding, preserve its stable ID, increment plan_revision exactly once,",
            "and recompute the material digest without changing the accepted specification identity.",
            f"Plan: {request.review_request.plan_path}",
            "Required corrections:",
            *finding_lines,
        )
    )


def _validate_outcome(request: PlanRevisionRequest, result: SessionAttemptResult) -> PlanRevisionResult | None:
    terminal = result.terminal_session_result
    if terminal is None or len(terminal.terminal_outcomes) != 1:
        return _blocked("plan_revision_outcome_unavailable", "plan revision requires one typed outcome")
    outcome = terminal.terminal_outcomes[0]
    expected_ids = tuple(finding.id for finding in request.findings)
    if outcome.session_role is not SessionRole.PLAN_AUTHOR or outcome.status is not SessionStatus.COMPLETED:
        return _blocked("unexpected_revision_outcome", "plan revision must complete as a plan_author session")
    if outcome.finding_ids != expected_ids:
        return _blocked("finding_traceability_mismatch", "plan author must report every prior finding ID in order")
    plan_path = request.review_request.plan_path
    if outcome.artifact_paths != (plan_path,) or result.changed_paths != (plan_path,):
        return _blocked("revised_plan_not_verified", "plan revision must change only the selected plan artifact")
    return None


def _failure(result: SessionAttemptResult) -> PlanRevisionResult:
    blocker = result.blocker
    status = PlanRevisionStatus.BLOCKED if result.status is SessionAttemptStatus.BLOCKED else PlanRevisionStatus.FAILED
    return PlanRevisionResult(
        status=status,
        blocker_code=blocker.code if blocker is not None else "plan_revision_session_failed",
        blocker_summary=blocker.summary if blocker is not None else "plan revision session did not complete",
    )


def _blocked(code: str, summary: str) -> PlanRevisionResult:
    return PlanRevisionResult(status=PlanRevisionStatus.BLOCKED, blocker_code=code, blocker_summary=summary)
