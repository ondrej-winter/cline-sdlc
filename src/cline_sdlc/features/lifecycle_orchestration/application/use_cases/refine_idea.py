"""Coordinate one supervised rough-idea refinement lifecycle stage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.idea_stage import (
    IdeaRefinementBlocker,
    IdeaRefinementRequest,
    IdeaRefinementResult,
    IdeaRefinementStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import (
        StagePreflightRequest,
        StagePreflightResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import SessionAttemptResult


class StagePreflightPort(Protocol):
    """Published lifecycle boundary for ordered no-write stage preflight."""

    def execute(self, request: StagePreflightRequest) -> StagePreflightResult:
        """Return stage authorization or an actionable preflight blocker."""


class SessionAttemptsPort(Protocol):
    """Published lifecycle boundary for bounded Cline session attempts."""

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        """Return typed session-attempt evidence without deciding artifact completion."""


class RefineIdea:
    """Run exactly one supervised idea-refinement stage and verify its artifact boundary."""

    def __init__(self, *, preflight: StagePreflightPort, session_attempts: SessionAttemptsPort) -> None:
        self._preflight = preflight
        self._session_attempts = session_attempts

    def execute(self, request: IdeaRefinementRequest) -> IdeaRefinementResult:
        """Return completion only when the idea-refiner reports one changed idea brief."""
        rough_idea = str(request.invocation.source.value).strip()
        if not rough_idea:
            return _blocked(code="empty_idea", summary="rough idea must not be empty")

        preflight_result = self._preflight.execute(request.preflight_request)
        if not preflight_result.authorized:
            return _blocked(
                code="idea_preflight_failed",
                summary="idea refinement preflight failed before Cline could start",
                evidence=_joined_preflight_blockers(preflight_result),
            )

        session_result = self._session_attempts.execute(_session_attempt_request(request, rough_idea))
        if (
            session_result.status is not SessionAttemptStatus.COMPLETED
            or session_result.terminal_session_result is None
        ):
            blocker = session_result.blocker
            return IdeaRefinementResult(
                status=IdeaRefinementStatus.BLOCKED
                if session_result.status is SessionAttemptStatus.BLOCKED
                else IdeaRefinementStatus.FAILED,
                blocker=IdeaRefinementBlocker(
                    code=blocker.code if blocker is not None else "idea_session_failed",
                    summary=blocker.summary if blocker is not None else "idea refinement session did not complete",
                ),
            )

        return _verified_completion(request, session_result)


def _session_attempt_request(request: IdeaRefinementRequest, rough_idea: str) -> SessionAttemptRequest:
    return SessionAttemptRequest(
        session_request=ClineSessionRequest(
            command=(request.invocation.cline_command, "--json", "--task", _prompt(request, rough_idea)),
            working_directory=request.preflight_request.repository_request.working_directory,
            timeout_seconds=request.invocation.timeout_seconds,
        ),
        repository_request=request.preflight_request.repository_request,
    )


def _prompt(request: IdeaRefinementRequest, rough_idea: str) -> str:
    return "\n".join(
        (
            "Use the idea-refine skill to refine this rough idea into an accepted idea brief.",
            "Stop after the accepted idea brief artifact boundary; do not create a specification or plan.",
            f"Lifecycle stage: {LifecycleStage.IDEA_REFINEMENT.value}",
            f"Write the idea brief to: {request.output_artifact.path}",
            "Rough idea:",
            rough_idea,
        )
    )


def _verified_completion(
    request: IdeaRefinementRequest,
    session_result: SessionAttemptResult,
) -> IdeaRefinementResult:
    if (
        session_result.terminal_session_result is None
        or len(session_result.terminal_session_result.terminal_outcomes) != 1
    ):
        return _blocked(
            code="idea_terminal_outcome_unavailable",
            summary="idea refinement requires exactly one typed session outcome",
        )

    outcome = session_result.terminal_session_result.terminal_outcomes[0]
    expected_path = request.output_artifact.path
    if outcome.session_role is not SessionRole.IDEA_REFINER:
        return _blocked(
            code="unexpected_session_role",
            summary="idea refinement must complete as an idea_refiner session",
        )
    if outcome.artifact_paths != (expected_path,) or session_result.changed_paths != (expected_path,):
        return _blocked(
            code="idea_artifact_not_verified",
            summary="idea refinement must report exactly one changed selected idea-brief artifact",
            evidence=expected_path,
        )

    return IdeaRefinementResult(status=IdeaRefinementStatus.COMPLETED, output_paths=(expected_path,))


def _joined_preflight_blockers(preflight_result: StagePreflightResult) -> str | None:
    if not preflight_result.blockers:
        return None
    return "; ".join(f"{blocker.step.value}:{blocker.code}" for blocker in preflight_result.blockers)


def _blocked(*, code: str, summary: str, evidence: str | None = None) -> IdeaRefinementResult:
    return IdeaRefinementResult(
        status=IdeaRefinementStatus.BLOCKED,
        blocker=IdeaRefinementBlocker(code=code, summary=summary, evidence=evidence),
    )
