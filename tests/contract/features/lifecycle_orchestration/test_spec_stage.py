"""Contract tests for idea-to-specification stage orchestration."""

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
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionProcessStatus,
    ClineSessionResult,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
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
    SessionAttemptObservation,
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.specification_stage import (
    SpecificationCreationRequest,
    SpecificationCreationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.create_specification import CreateSpecification
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


def test_creates_specification_from_accepted_idea_file() -> None:
    preflight = RecordingPreflight(_authorized_preflight(), [])
    attempts = RecordingSessionAttempts(_completed_attempt(), [])

    result = CreateSpecification(preflight=preflight, session_attempts=attempts).execute(_request())

    assert result.completed
    assert result.status is SpecificationCreationStatus.COMPLETED
    assert result.output_paths == (_spec_artifact().path,)
    assert len(preflight.requests) == 1
    assert len(attempts.requests) == 1
    assert attempts.requests[0].session_request.working_directory == Path("/repo")
    assert attempts.requests[0].session_request.command[:3] == ("cline", "--tui", "--plan")
    assert "spec-driven-development" in attempts.requests[0].session_request.command[-1]
    assert _idea_path().as_posix() in attempts.requests[0].session_request.command[-1]
    assert "do not create a plan" in attempts.requests[0].session_request.command[-1]


def test_requires_idea_file_invocation_source() -> None:
    invocation = InvocationRequest(
        source=InvocationSource.from_idea("not a file"),
        timeout_seconds=30,
        cline_command="cline",
        stage=LifecycleStage.SPECIFICATION_CREATION,
    )

    with pytest.raises(ValueError, match="idea-file invocation source"):
        SpecificationCreationRequest(
            invocation=invocation,
            preflight_request=_preflight_request(invocation),
            output_artifact=_spec_artifact(),
        )


def test_preflight_blocker_prevents_session_start() -> None:
    preflight = RecordingPreflight(
        StagePreflightResult(
            status=StagePreflightStatus.BLOCKED,
            blockers=(
                StagePreflightBlocker(
                    step=StagePreflightStep.REPOSITORY,
                    code="dirty_tree",
                    summary="repository is not ready",
                ),
            ),
        ),
        [],
    )
    attempts = RecordingSessionAttempts(_completed_attempt(), [])

    result = CreateSpecification(preflight=preflight, session_attempts=attempts).execute(_request())

    assert result.status is SpecificationCreationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "specification_preflight_failed"
    assert result.blocker.evidence == "repository:dirty_tree"
    assert attempts.requests == []


def test_blocked_session_outcome_stops_at_specification_boundary() -> None:
    result = CreateSpecification(
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

    assert result.status is SpecificationCreationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "session_blocked"


def test_interactive_specification_completion_accepts_exact_selected_artifact_change() -> None:
    result = CreateSpecification(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(_interactive_attempt(dirty_paths=(_spec_artifact().path,)), []),
    ).execute(_request())

    assert result.completed
    assert result.status is SpecificationCreationStatus.COMPLETED
    assert result.output_paths == (_spec_artifact().path,)


def test_interactive_specification_completion_rejects_unexpected_changes() -> None:
    result = CreateSpecification(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            _interactive_attempt(dirty_paths=(_spec_artifact().path, "docs/plans/unexpected-plan.md")),
            [],
        ),
    ).execute(_request())

    assert result.status is SpecificationCreationStatus.FAILED
    assert result.blocker is not None
    assert result.blocker.code == "specification_session_failed"


def test_wrong_session_role_does_not_complete_specification_stage() -> None:
    result = CreateSpecification(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            _completed_attempt(role=SessionRole.PLAN_AUTHOR),
            [],
        ),
    ).execute(_request())

    assert result.status is SpecificationCreationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "unexpected_session_role"


def test_missing_or_mismatched_specification_artifact_does_not_complete() -> None:
    result = CreateSpecification(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            _completed_attempt(
                artifact_paths=("docs/plans/not-allowed-plan.md",),
                changed_paths=("docs/plans/not-allowed-plan.md",),
            ),
            [],
        ),
    ).execute(_request())

    assert result.status is SpecificationCreationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "specification_artifact_not_verified"


def test_multiple_artifacts_do_not_complete_specification_stage() -> None:
    result = CreateSpecification(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        session_attempts=RecordingSessionAttempts(
            _completed_attempt(
                artifact_paths=(_spec_artifact().path, "docs/specs/extra-spec.md"),
                changed_paths=(_spec_artifact().path, "docs/specs/extra-spec.md"),
            ),
            [],
        ),
    ).execute(_request())

    assert result.status is SpecificationCreationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "specification_artifact_not_verified"


def _request() -> SpecificationCreationRequest:
    invocation = InvocationRequest(
        source=InvocationSource.from_idea_file(_idea_path()),
        timeout_seconds=30,
        cline_command="cline",
        stage=LifecycleStage.SPECIFICATION_CREATION,
    )
    return SpecificationCreationRequest(
        invocation=invocation,
        preflight_request=_preflight_request(invocation),
        output_artifact=_spec_artifact(),
    )


def _preflight_request(invocation: InvocationRequest) -> StagePreflightRequest:
    return StagePreflightRequest(
        invocation=invocation,
        artifact_location_request=SelectArtifactLocationRequest(
            artifact_kind=ArtifactKind.SPECIFICATION,
            artifact_stem="cline-sdlc-orchestrator",
        ),
        repository_request=RepositoryInspectionRequest(
            working_directory=Path("/repo"),
            input_paths=(_idea_path(),),
            managed_paths=(Path("docs/specs"),),
        ),
    )


def _idea_path() -> Path:
    return Path("docs/ideas/cline-sdlc-orchestrator-idea.md")


def _spec_artifact() -> ArtifactLocationResult:
    return ArtifactLocationResult(
        artifact_kind=ArtifactKind.SPECIFICATION,
        path="docs/specs/cline-sdlc-orchestrator-spec.md",
        directory="docs/specs",
        source=ArtifactLocationSource.PORTABLE_DEFAULT,
    )


def _authorized_preflight() -> StagePreflightResult:
    return StagePreflightResult(
        status=StagePreflightStatus.AUTHORIZED,
        repository_snapshot=RepositorySnapshot(repository_root="/repo", head_commit="abc123", branch="feature/spec"),
        artifact_location=_spec_artifact(),
    )


def _completed_attempt(
    *,
    role: SessionRole = SessionRole.SPEC_AUTHOR,
    artifact_paths: tuple[str, ...] | None = None,
    changed_paths: tuple[str, ...] | None = None,
) -> SessionAttemptResult:
    selected_artifact = _spec_artifact().path
    reported_artifacts = (selected_artifact,) if artifact_paths is None else artifact_paths
    reported_changes = (selected_artifact,) if changed_paths is None else changed_paths
    session_result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(
            SessionOutcome(
                session_role=role,
                status=SessionStatus.COMPLETED,
                reason="specification accepted",
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


def _interactive_attempt(*, dirty_paths: tuple[str, ...]) -> SessionAttemptResult:
    session_result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
    )
    return SessionAttemptResult(
        status=SessionAttemptStatus.FAILED,
        attempts=(
            SessionAttemptObservation(
                attempt_number=1,
                before_snapshot=RepositorySnapshot(
                    repository_root="/repo", head_commit="abc123", branch="feature/spec"
                ),
                session_result=session_result,
                after_snapshot=RepositorySnapshot(
                    repository_root="/repo",
                    head_commit="abc123",
                    branch="feature/spec",
                    dirty_paths=dirty_paths,
                ),
            ),
        ),
    )
