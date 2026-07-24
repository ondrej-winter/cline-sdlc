"""Contract tests for initial implementation-plan authoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationResult,
    ArtifactLocationSource,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanBlocker,
    AuthoredPlanInspectionRequest,
    AuthoredPlanValidationRequest,
    AuthoredPlanValidationResult,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import (
    PlanPhase,
    PlanState,
    ReviewReadiness,
)
from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionProcessStatus, ClineSessionResult
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest, InvocationSource
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_authoring import (
    PlanAuthoringRequest,
    PlanAuthoringStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import (
    StagePreflightRequest,
    StagePreflightResult,
    StagePreflightStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationDiscoveryBlocker,
    ValidationDiscoveryRequest,
    ValidationDiscoveryResult,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.author_plan import AuthorPlan
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositorySnapshot,
)

SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"


@dataclass
class RecordingPreflight:
    result: StagePreflightResult
    requests: list[StagePreflightRequest]

    def execute(self, request: StagePreflightRequest) -> StagePreflightResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingDiscovery:
    result: ValidationDiscoveryResult
    requests: list[ValidationDiscoveryRequest]

    def execute(self, request: ValidationDiscoveryRequest) -> ValidationDiscoveryResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingAttempts:
    result: SessionAttemptResult
    requests: list[SessionAttemptRequest]

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingValidator:
    result: AuthoredPlanValidationResult
    requests: list[AuthoredPlanValidationRequest]

    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingContentReader:
    result: AuthoredPlanValidationRequest
    requests: list[AuthoredPlanInspectionRequest]

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        self.requests.append(request)
        return self.result


@dataclass
class FailingContentReader:
    error: ValueError

    def read(self, _request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        raise self.error


def test_authors_and_independently_validates_initial_plan() -> None:
    preflight = RecordingPreflight(_authorized_preflight(), [])
    discovery = RecordingDiscovery(_discovery(), [])
    attempts = RecordingAttempts(_completed_attempt(), [])
    reader = RecordingContentReader(_content(), [])
    validator = RecordingValidator(_valid_plan(), [])

    result = AuthorPlan(
        preflight=preflight,
        validation_discovery=discovery,
        session_attempts=attempts,
        content_reader=reader,
        plan_validator=validator,
    ).execute(_request())

    assert result.completed
    assert result.output_paths == (_plan_artifact().path,)
    assert result.specification_digest == SPECIFICATION_DIGEST
    assert result.material_digest == MATERIAL_DIGEST
    assert len(attempts.requests) == 1
    session_request = attempts.requests[0]
    assert isinstance(session_request, SessionAttemptRequest)
    prompt = session_request.session_request.command[3]
    assert "planning-and-task-breakdown" in prompt
    assert "do not review or implement" in prompt
    assert _spec_path().as_posix() in prompt
    assert "uv run pytest" in prompt
    assert reader.requests == [
        AuthoredPlanInspectionRequest(specification_path=_spec_path().as_posix(), plan_path=_plan_artifact().path)
    ]
    assert validator.requests == [_content()]


def test_preflight_blocker_starts_no_later_work() -> None:
    discovery = RecordingDiscovery(_discovery(), [])
    attempts = RecordingAttempts(_completed_attempt(), [])
    reader = RecordingContentReader(_content(), [])

    result = _author_plan(
        preflight=RecordingPreflight(StagePreflightResult(status=StagePreflightStatus.BLOCKED), []),
        discovery=discovery,
        attempts=attempts,
        reader=reader,
    ).execute(_request())

    assert result.status is PlanAuthoringStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "plan_authoring_preflight_failed"
    assert discovery.requests == []
    assert attempts.requests == []
    assert reader.requests == []


def test_validation_discovery_failure_starts_no_session() -> None:
    attempts = RecordingAttempts(_completed_attempt(), [])
    discovery = ValidationDiscoveryResult(
        blockers=(ValidationDiscoveryBlocker(code="unsafe_command", summary="command is not allowed"),)
    )

    result = _author_plan(discovery=RecordingDiscovery(discovery, []), attempts=attempts).execute(_request())

    assert result.status is PlanAuthoringStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "validation_discovery_failed"
    assert attempts.requests == []


def test_wrong_role_or_path_does_not_validate_plan() -> None:
    reader = RecordingContentReader(_content(), [])
    result = _author_plan(
        attempts=RecordingAttempts(
            _completed_attempt(role=SessionRole.PLAN_REVIEWER, path="docs/plans/other.md"),
            [],
        ),
        reader=reader,
    ).execute(_request())

    assert result.status is PlanAuthoringStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "unexpected_session_role"
    assert reader.requests == []


def test_mismatched_plan_path_does_not_validate_plan() -> None:
    reader = RecordingContentReader(_content(), [])
    result = _author_plan(
        attempts=RecordingAttempts(_completed_attempt(path="docs/plans/other.md"), []),
        reader=reader,
    ).execute(_request())

    assert result.status is PlanAuthoringStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "plan_artifact_not_verified"
    assert reader.requests == []


def test_invalid_authored_plan_blocks_before_review() -> None:
    validator = RecordingValidator(
        AuthoredPlanValidationResult(
            valid=False,
            plan_path=_plan_artifact().path,
            blockers=(
                AuthoredPlanBlocker(
                    code="invalid_authored_plan",
                    summary="invalid plan",
                    evidence="stored material digest does not match",
                ),
            ),
        ),
        [],
    )

    result = _author_plan(validator=validator).execute(_request())

    assert result.status is PlanAuthoringStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "authored_plan_invalid"
    assert result.blocker.evidence == "stored material digest does not match"


def test_unreadable_authored_plan_blocks_before_validation() -> None:
    validator = RecordingValidator(_valid_plan(), [])
    result = AuthorPlan(
        preflight=RecordingPreflight(_authorized_preflight(), []),
        validation_discovery=RecordingDiscovery(_discovery(), []),
        session_attempts=RecordingAttempts(_completed_attempt(), []),
        content_reader=FailingContentReader(ValueError("invalid state block")),
        plan_validator=validator,
    ).execute(_request())

    assert result.status is PlanAuthoringStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "authored_plan_content_unavailable"
    assert validator.requests == []


def _author_plan(
    *,
    preflight: RecordingPreflight | None = None,
    discovery: RecordingDiscovery | None = None,
    attempts: RecordingAttempts | None = None,
    reader: RecordingContentReader | None = None,
    validator: RecordingValidator | None = None,
) -> AuthorPlan:
    return AuthorPlan(
        preflight=preflight or RecordingPreflight(_authorized_preflight(), []),
        validation_discovery=discovery or RecordingDiscovery(_discovery(), []),
        session_attempts=attempts or RecordingAttempts(_completed_attempt(), []),
        content_reader=reader or RecordingContentReader(_content(), []),
        plan_validator=validator or RecordingValidator(_valid_plan(), []),
    )


def _request() -> PlanAuthoringRequest:
    invocation = InvocationRequest(
        source=InvocationSource.from_spec_file(_spec_path()),
        timeout_seconds=30,
        cline_command="cline",
        stage=LifecycleStage.PLAN_CREATION_AND_REVIEW,
    )
    return PlanAuthoringRequest(
        invocation=invocation,
        preflight_request=StagePreflightRequest(
            invocation=invocation,
            artifact_location_request=None,
            repository_request=RepositoryInspectionRequest(
                working_directory=Path("/repo"),
                input_paths=(_spec_path(),),
                managed_paths=(Path("docs/plans"),),
            ),
            cline_preflight_request=ClinePreflightRequest(
                command=("cline",),
                required_skills=("planning-and-task-breakdown",),
            ),
        ),
        validation_discovery_request=ValidationDiscoveryRequest(changed_paths=(_spec_path().as_posix(),)),
        output_artifact=_plan_artifact(),
    )


def _authorized_preflight() -> StagePreflightResult:
    return StagePreflightResult(
        status=StagePreflightStatus.AUTHORIZED,
        repository_snapshot=RepositorySnapshot(repository_root="/repo", head_commit="abc123", branch="feature/plan"),
        artifact_location=_plan_artifact(),
    )


def _discovery() -> ValidationDiscoveryResult:
    return ValidationDiscoveryResult(
        commands=(
            ValidationCommandCandidate(
                scope=ValidationScope.BROAD,
                command=ValidationCommand(executable="uv", arguments=("run", "pytest")),
                source=ValidationCommandSource.DEFAULT,
                reason="repository quality gate",
            ),
        )
    )


def _completed_attempt(
    *,
    role: SessionRole = SessionRole.PLAN_AUTHOR,
    path: str | None = None,
) -> SessionAttemptResult:
    artifact_path = path or _plan_artifact().path
    session_result = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(
            SessionOutcome(
                session_role=role,
                status=SessionStatus.COMPLETED,
                reason="initial_plan_authored",
                artifact_paths=(artifact_path,),
                changed_paths=(artifact_path,) if role is not SessionRole.PLAN_REVIEWER else (),
            ),
        ),
    )
    return SessionAttemptResult(
        status=SessionAttemptStatus.COMPLETED,
        attempts=(),
        terminal_session_result=session_result,
        changed_paths=(artifact_path,),
    )


def _content() -> AuthoredPlanValidationRequest:
    return AuthoredPlanValidationRequest(
        specification_path=_spec_path().as_posix(),
        specification_content=b"specification",
        plan_path=_plan_artifact().path,
        plan_content=b"plan",
        plan_state=PlanState(
            work_id="example-work",
            phase=PlanPhase.DRAFTING,
            specification=_spec_path().as_posix(),
            specification_digest=SPECIFICATION_DIGEST,
            plan_revision=1,
            review_iteration=1,
            review_readiness=ReviewReadiness.NOT_REVIEWED,
            material_digest=MATERIAL_DIGEST,
            created_at=datetime(2026, 7, 24, tzinfo=UTC),
            updated_at=datetime(2026, 7, 24, tzinfo=UTC),
        ),
    )


def _valid_plan() -> AuthoredPlanValidationResult:
    return AuthoredPlanValidationResult(
        valid=True,
        plan_path=_plan_artifact().path,
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
    )


def _spec_path() -> Path:
    return Path("docs/specs/example-spec.md")


def _plan_artifact() -> ArtifactLocationResult:
    return ArtifactLocationResult(
        artifact_kind=ArtifactKind.PLAN,
        path="docs/plans/example-plan.md",
        directory="docs/plans",
        source=ArtifactLocationSource.PORTABLE_DEFAULT,
    )
