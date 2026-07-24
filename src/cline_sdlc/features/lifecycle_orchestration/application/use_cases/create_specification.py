"""Coordinate one supervised idea-to-specification lifecycle stage."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.specification_stage import (
    SpecificationCreationBlocker,
    SpecificationCreationRequest,
    SpecificationCreationResult,
    SpecificationCreationStatus,
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


class CreateSpecification:
    """Run exactly one supervised specification-author stage and verify its artifact boundary."""

    def __init__(self, *, preflight: StagePreflightPort, session_attempts: SessionAttemptsPort) -> None:
        self._preflight = preflight
        self._session_attempts = session_attempts

    def execute(self, request: SpecificationCreationRequest) -> SpecificationCreationResult:
        """Return completion only when the spec author reports one changed specification."""
        preflight_result = self._preflight.execute(request.preflight_request)
        if not preflight_result.authorized:
            return _blocked(
                code="specification_preflight_failed",
                summary="specification creation preflight failed before Cline could start",
                evidence=_joined_preflight_blockers(preflight_result),
            )

        session_result = self._session_attempts.execute(_session_attempt_request(request))
        if (
            session_result.status is not SessionAttemptStatus.COMPLETED
            or session_result.terminal_session_result is None
        ):
            blocker = session_result.blocker
            return SpecificationCreationResult(
                status=SpecificationCreationStatus.BLOCKED
                if session_result.status is SessionAttemptStatus.BLOCKED
                else SpecificationCreationStatus.FAILED,
                blocker=SpecificationCreationBlocker(
                    code=blocker.code if blocker is not None else "specification_session_failed",
                    summary=blocker.summary
                    if blocker is not None
                    else "specification creation session did not complete",
                ),
            )

        return _verified_completion(request, session_result)


def _session_attempt_request(request: SpecificationCreationRequest) -> SessionAttemptRequest:
    return SessionAttemptRequest(
        session_request=ClineSessionRequest(
            command=(request.invocation.cline_command, "--json", "--task", _prompt(request)),
            working_directory=request.preflight_request.repository_request.working_directory,
            timeout_seconds=request.invocation.timeout_seconds,
        ),
        repository_request=request.preflight_request.repository_request,
    )


def _prompt(request: SpecificationCreationRequest) -> str:
    idea_path = Path(request.invocation.source.value).as_posix()
    return "\n".join(
        (
            "Use the spec-driven-development skill to turn the accepted idea brief into an accepted specification.",
            "Stop after the accepted specification artifact boundary; do not create a plan.",
            f"Lifecycle stage: {LifecycleStage.SPECIFICATION_CREATION.value}",
            f"Read the accepted idea brief from: {idea_path}",
            f"Write the specification to: {request.output_artifact.path}",
        )
    )


def _verified_completion(
    request: SpecificationCreationRequest,
    session_result: SessionAttemptResult,
) -> SpecificationCreationResult:
    if (
        session_result.terminal_session_result is None
        or len(session_result.terminal_session_result.terminal_outcomes) != 1
    ):
        return _blocked(
            code="specification_terminal_outcome_unavailable",
            summary="specification creation requires exactly one typed session outcome",
        )

    outcome = session_result.terminal_session_result.terminal_outcomes[0]
    expected_path = request.output_artifact.path
    if outcome.session_role is not SessionRole.SPEC_AUTHOR:
        return _blocked(
            code="unexpected_session_role",
            summary="specification creation must complete as a spec_author session",
        )
    if outcome.artifact_paths != (expected_path,) or session_result.changed_paths != (expected_path,):
        return _blocked(
            code="specification_artifact_not_verified",
            summary="specification creation must report exactly one changed selected specification artifact",
            evidence=expected_path,
        )

    return SpecificationCreationResult(status=SpecificationCreationStatus.COMPLETED, output_paths=(expected_path,))


def _joined_preflight_blockers(preflight_result: StagePreflightResult) -> str | None:
    if not preflight_result.blockers:
        return None
    return "; ".join(f"{blocker.step.value}:{blocker.code}" for blocker in preflight_result.blockers)


def _blocked(*, code: str, summary: str, evidence: str | None = None) -> SpecificationCreationResult:
    return SpecificationCreationResult(
        status=SpecificationCreationStatus.BLOCKED,
        blocker=SpecificationCreationBlocker(code=code, summary=summary, evidence=evidence),
    )
