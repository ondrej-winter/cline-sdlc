"""Contract tests for rough-idea refinement stage orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationResult,
    ArtifactLocationSource,
    SelectArtifactLocationRequest,
)
from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.idea_stage import (
    IdeaRefinementRequest,
    IdeaRefinementStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest, InvocationSource
from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import (
    StagePreflightBlocker,
    StagePreflightRequest,
    StagePreflightResult,
    StagePreflightStatus,
    StagePreflightStep,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptBlocker,
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.refine_idea import RefineIdea
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositorySnapshot,
)


@dataclass
class RecordingPreflight:
    result: StagePreflightResult
    requests: list[StagePreflightRequest]

    def execute(self, request: StagePreflightRequest) -> StagePreflightResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingSessionAttempts:
    result: SessionAttemptResult
    requests: list[SessionAttemptRequest]

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        return self.result


def test_refines_rough_idea_to_exactly_one_selected_idea_brief() -> None:
    preflight = RecordingPreflight(_authorized_preflight(), [])
    attempts = RecordingSessionAttempts(_completed_attempt(), [])

    result = RefineIdea(preflight=preflight, session_attempts=attempts).execute(_request())

    assert result.completed
    assert result.status is IdeaRefinementStatus.COMPLETED
    assert result.output_paths == (_idea_artifact().path,)
    assert len(preflight.requests) == 1
    assert len(attempts.requests) == 1
    assert attempts.requests[0].session_request.working_directory == Path("/repo")
    assert attempts.requests[0].session_request.command[:3] == ("cline", "--json", "--task")
    assert "idea-refine" in attempts.requests[0].session_request.command[3]
    assert "do not create a specification or plan" in attempts.requests[0].session_request.command[3]


def test_empty_rough_idea_is_rejected_before_preflight_or_session() -> None:
    preflight = RecordingPreflight(_authorized_preflight(), [])
    attempts = RecordingSessionAttempts(_completed_attempt(), [])

    with pytest.raises(ValueError, match="rough idea must not be empty"):
        RefineIdea(preflight=preflight, session_attempts=attempts).execute(_request(idea="   "))

    assert preflight.requests == []
    assert attempts.requests == []


def test_preflight_blocker_prevents_session_start() -> None:
    preflight = RecordingPreflight(
        StagePreflightResult(
            status=StagePreflightStatus.BLOCKED,
            blockers=(
                StagePreflightBlocker(
                    step=StagePreflightStep.CLINE_CAPABILITY,
                    code="missing_skill",
                    summary="idea-refine is unavailable",
                ),
            ),
        ),
        [],
    )
    attempts = RecordingSessionAttempts(_completed_attempt(), [])

    result = RefineIdea(preflight=preflight, session_attempts=attempts).execute(_request())

    assert result.status is IdeaRefinementStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "idea_preflight_failed"
    assert result.blocker.evidence == "cline_capability:missing_skill"
    assert attempts.requests == []


def test_blocked_session_outcome_stops_at_idea_stage_boundary() -> None:
    result = RefineIdea(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            SessionAttemptResult(
                status=SessionAttemptStatus.BLOCKED,
                attempts=(),
                blocker=SessionAttemptBlocker(code="session_blocked", summary="user declined acceptance"),
            ),
            [],
        ),
    ).execute(_request())

    assert result.status is IdeaRefinementStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "session_blocked"


def test_wrong_session_role_does_not_complete_idea_stage() -> None:
    result = RefineIdea(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            _completed_attempt(role=SessionRole.SPEC_AUTHOR),
            [],
        ),
    ).execute(_request())

    assert result.status is IdeaRefinementStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "unexpected_session_role"


def test_missing_or_mismatched_idea_artifact_does_not_complete() -> None:
    result = RefineIdea(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            _completed_attempt(
                artifact_paths=("docs/specs/not-allowed-spec.md",),
                changed_paths=("docs/specs/not-allowed-spec.md",),
            ),
            [],
        ),
    ).execute(_request())

    assert result.status is IdeaRefinementStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "idea_artifact_not_verified"


def test_multiple_artifacts_do_not_complete_idea_stage() -> None:
    result = RefineIdea(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            _completed_attempt(
                artifact_paths=(_idea_artifact().path, "docs/ideas/extra-idea.md"),
                changed_paths=(_idea_artifact().path, "docs/ideas/extra-idea.md"),
            ),
            [],
        ),
    ).execute(_request())

    assert result.status is IdeaRefinementStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "idea_artifact_not_verified"


def _request(*, idea: str = "Build a portable Cline SDLC workflow runner") -> IdeaRefinementRequest:
    invocation = InvocationRequest(
        source=InvocationSource.from_idea(idea),
        timeout_seconds=30,
        cline_command="cline",
        stage=LifecycleStage.IDEA_REFINEMENT,
    )
    return IdeaRefinementRequest(
        invocation=invocation,
        preflight_request=_preflight_request(invocation),
        output_artifact=_idea_artifact(),
    )


def _preflight_request(invocation: InvocationRequest) -> StagePreflightRequest:
    return StagePreflightRequest(
        invocation=invocation,
        artifact_location_request=SelectArtifactLocationRequest(
            artifact_kind=ArtifactKind.IDEA_BRIEF,
            artifact_stem="cline-sdlc-orchestrator",
        ),
        repository_request=RepositoryInspectionRequest(
            working_directory=Path("/repo"),
            managed_paths=(Path("docs/ideas"),),
        ),
        cline_preflight_request=ClinePreflightRequest(command=("cline",), required_skills=("idea-refine",)),
    )


def _idea_artifact() -> ArtifactLocationResult:
    return ArtifactLocationResult(
        artifact_kind=ArtifactKind.IDEA_BRIEF,
        path="docs/ideas/cline-sdlc-orchestrator-idea.md",
        directory="docs/ideas",
        source=ArtifactLocationSource.PORTABLE_DEFAULT,
    )


def _authorized_preflight() -> StagePreflightResult:
    return StagePreflightResult(
        status=StagePreflightStatus.AUTHORIZED,
        repository_snapshot=RepositorySnapshot(repository_root="/repo", head_commit="abc123", branch="feature/idea"),
        artifact_location=_idea_artifact(),
    )


def _completed_attempt(
    *,
    role: SessionRole = SessionRole.IDEA_REFINER,
    artifact_paths: tuple[str, ...] | None = None,
    changed_paths: tuple[str, ...] | None = None,
) -> SessionAttemptResult:
    selected_artifact = _idea_artifact().path
    reported_artifacts = (selected_artifact,) if artifact_paths is None else artifact_paths
    reported_changes = (selected_artifact,) if changed_paths is None else changed_paths
    session_result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(
            SessionOutcome(
                session_role=role,
                status=SessionStatus.COMPLETED,
                reason="idea accepted",
                artifact_paths=reported_artifacts,
                changed_paths=reported_changes,
            ),
        ),
    )
    return SessionAttemptResult(
        status=SessionAttemptStatus.COMPLETED,
        attempts=(),
        terminal_session_result=session_result,
        changed_paths=reported_changes,
    )
