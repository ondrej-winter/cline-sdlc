"""Application end-to-end proofs for lifecycle boundaries in an unrelated host."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationResult,
    ArtifactLocationSource,
    SelectArtifactLocationRequest,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanInspectionRequest,
    AuthoredPlanValidationRequest,
    AuthoredPlanValidationResult,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.plan_review import (
    PlanReviewProgressRequest,
    PlanReviewProgressResult,
)
from cline_sdlc.features.artifact_lifecycle.domain.findings import PlanReviewReadiness
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase, PlanState, ReviewReadiness
from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionProcessStatus, ClineSessionResult
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.idea_stage import IdeaRefinementRequest
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest, InvocationSource
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_authoring import PlanAuthoringRequest
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import PlanReviewRequest, PlanReviewStatus
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
from cline_sdlc.features.lifecycle_orchestration.application.dtos.specification_stage import (
    SpecificationCreationRequest,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationDiscoveryRequest,
    ValidationDiscoveryResult,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.author_plan import AuthorPlan
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.create_specification import CreateSpecification
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.refine_idea import RefineIdea
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.review_plan import ReviewPlan
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositorySnapshot,
)
from tests.e2e.conftest import HOST_CHECK, IDEA_PATH, PLAN_PATH, SPECIFICATION_PATH

if TYPE_CHECKING:
    from tests.e2e.conftest import ExternalHost

NOW = datetime(2026, 7, 26, 19, 30, tzinfo=UTC)
SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"


@dataclass
class AuthorizedPreflight:
    host: ExternalHost
    requests: list[StagePreflightRequest] = field(default_factory=list)

    def execute(self, request: StagePreflightRequest) -> StagePreflightResult:
        self.requests.append(request)
        return StagePreflightResult(
            status=StagePreflightStatus.AUTHORIZED,
            repository_snapshot=_snapshot(self.host),
        )


@dataclass
class ArtifactWritingSession:
    host: ExternalHost
    role: SessionRole
    path: str
    content: str
    requests: list[SessionAttemptRequest] = field(default_factory=list)

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        self.host.write_text(self.path, self.content)
        outcome = SessionOutcome(
            session_role=self.role,
            status=SessionStatus.COMPLETED,
            reason="accepted_artifact_written",
            artifact_paths=(self.path,),
            changed_paths=(self.path,),
        )
        terminal = ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=0,
            terminal_outcomes=(outcome,),
        )
        return SessionAttemptResult(
            status=SessionAttemptStatus.COMPLETED,
            attempts=(),
            terminal_session_result=terminal,
            changed_paths=(self.path,),
        )


@dataclass
class StaticDiscovery:
    requests: list[ValidationDiscoveryRequest] = field(default_factory=list)

    def execute(self, request: ValidationDiscoveryRequest) -> ValidationDiscoveryResult:
        self.requests.append(request)
        return ValidationDiscoveryResult(
            commands=(
                ValidationCommandCandidate(
                    scope=ValidationScope.BROAD,
                    command=ValidationCommand(HOST_CHECK, ("--all",)),
                    source=ValidationCommandSource.DISCOVERED,
                    reason="external host instructions",
                ),
            )
        )


@dataclass
class HostPlanContent:
    host: ExternalHost
    state: PlanState
    requests: list[AuthoredPlanInspectionRequest] = field(default_factory=list)

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        self.requests.append(request)
        return AuthoredPlanValidationRequest(
            specification_path=request.specification_path,
            specification_content=self.host.read_text(request.specification_path).encode(),
            plan_path=request.plan_path,
            plan_content=self.host.read_text(request.plan_path).encode(),
            plan_state=self.state,
        )


class ValidPlan:
    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        return AuthoredPlanValidationResult(
            valid=True,
            plan_path=request.plan_path,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
        )


@dataclass
class ReadOnlyReviewSession:
    host: ExternalHost
    requests: list[SessionAttemptRequest] = field(default_factory=list)

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        outcome = SessionOutcome(
            session_role=SessionRole.PLAN_REVIEWER,
            status=SessionStatus.COMPLETED,
            reason="ready",
            artifact_paths=(PLAN_PATH,),
            review_readiness=PlanReviewReadiness.READY,
        )
        terminal = ClineSessionResult(
            process_status=ClineSessionProcessStatus.EXITED,
            exit_code=0,
            terminal_outcomes=(outcome,),
        )
        return SessionAttemptResult(
            status=SessionAttemptStatus.COMPLETED,
            attempts=(),
            terminal_session_result=terminal,
        )


class ReadyProgressWriter:
    def execute(self, request: PlanReviewProgressRequest) -> PlanReviewProgressResult:
        return PlanReviewProgressResult(
            updated=True,
            plan_path=request.plan_path,
            material_digest=MATERIAL_DIGEST,
            plan_state=_plan_state(PlanPhase.READY, ReviewReadiness.READY),
        )


class FixedClock:
    def now(self) -> datetime:
        return NOW


def test_idea_input_reaches_only_non_default_idea_boundary(external_host: ExternalHost) -> None:
    preflight = AuthorizedPreflight(external_host)
    session = ArtifactWritingSession(external_host, SessionRole.IDEA_REFINER, IDEA_PATH, _idea_content())
    invocation = _invocation(InvocationSource.from_idea("Portable workflow runner"), LifecycleStage.IDEA_REFINEMENT)

    result = RefineIdea(preflight=preflight, session_attempts=session).execute(
        IdeaRefinementRequest(
            invocation=invocation,
            preflight_request=_preflight(invocation, external_host, ArtifactKind.IDEA_BRIEF),
            output_artifact=_artifact(ArtifactKind.IDEA_BRIEF, IDEA_PATH),
        )
    )

    assert result.completed
    assert result.output_paths == (IDEA_PATH,)
    assert external_host.status_paths() == (IDEA_PATH,)
    assert not (external_host.root / SPECIFICATION_PATH).exists()
    assert not (external_host.root / PLAN_PATH).exists()
    assert "Problem" in external_host.read_text(IDEA_PATH)


def test_idea_file_reaches_only_non_default_specification_boundary(external_host: ExternalHost) -> None:
    external_host.write_text(IDEA_PATH, _idea_content())
    external_host.commit_all("Accept portable idea brief")
    preflight = AuthorizedPreflight(external_host)
    session = ArtifactWritingSession(
        external_host,
        SessionRole.SPEC_AUTHOR,
        SPECIFICATION_PATH,
        _specification_content(),
    )
    invocation = _invocation(
        InvocationSource.from_idea_file(external_host.root / IDEA_PATH),
        LifecycleStage.SPECIFICATION_CREATION,
    )

    result = CreateSpecification(preflight=preflight, session_attempts=session).execute(
        SpecificationCreationRequest(
            invocation=invocation,
            preflight_request=_preflight(invocation, external_host, ArtifactKind.SPECIFICATION),
            output_artifact=_artifact(ArtifactKind.SPECIFICATION, SPECIFICATION_PATH),
        )
    )

    assert result.completed
    assert result.output_paths == (SPECIFICATION_PATH,)
    assert external_host.status_paths() == (SPECIFICATION_PATH,)
    assert not (external_host.root / PLAN_PATH).exists()
    assert "Success criteria" in external_host.read_text(SPECIFICATION_PATH)


def test_spec_file_authors_and_read_only_reviews_without_implementation(external_host: ExternalHost) -> None:
    external_host.write_text(SPECIFICATION_PATH, _specification_content())
    external_host.commit_all("Accept portable specification")
    invocation = _invocation(
        InvocationSource.from_spec_file(external_host.root / SPECIFICATION_PATH),
        LifecycleStage.PLAN_CREATION_AND_REVIEW,
    )
    preflight = AuthorizedPreflight(external_host)
    author_session = ArtifactWritingSession(external_host, SessionRole.PLAN_AUTHOR, PLAN_PATH, _plan_content())
    discovery = StaticDiscovery()
    plan_state = _plan_state(PlanPhase.DRAFTING, ReviewReadiness.NOT_REVIEWED)
    content = HostPlanContent(external_host, plan_state)

    authored = AuthorPlan(
        preflight=preflight,
        validation_discovery=discovery,
        session_attempts=author_session,
        content_reader=content,
        plan_validator=ValidPlan(),
    ).execute(
        PlanAuthoringRequest(
            invocation=invocation,
            preflight_request=_preflight(invocation, external_host, ArtifactKind.PLAN),
            validation_discovery_request=ValidationDiscoveryRequest(
                changed_paths=(SPECIFICATION_PATH,),
                include_build_command=False,
            ),
            output_artifact=_artifact(ArtifactKind.PLAN, PLAN_PATH),
        )
    )
    reviewer = ReadOnlyReviewSession(external_host)
    reviewed = ReviewPlan(
        content_reader=content,
        plan_validator=ValidPlan(),
        session_attempts=reviewer,
        progress_writer=ReadyProgressWriter(),
        clock=FixedClock(),
    ).execute(
        PlanReviewRequest(
            invocation=invocation,
            preflight_request=_preflight(invocation, external_host, ArtifactKind.PLAN),
            plan_path=PLAN_PATH,
        )
    )

    assert authored.completed
    assert reviewed.status is PlanReviewStatus.READY
    assert len(author_session.requests) == 1
    assert len(reviewer.requests) == 1
    assert HOST_CHECK in author_session.requests[0].session_request.command[-1]
    assert external_host.status_paths() == (PLAN_PATH,)
    assert not (external_host.root / "src").exists()
    assert "Recovery" in external_host.read_text(PLAN_PATH)


def _invocation(source: InvocationSource, stage: LifecycleStage) -> InvocationRequest:
    return InvocationRequest(source=source, timeout_seconds=30, cline_command="fake-cline", stage=stage)


def _preflight(
    invocation: InvocationRequest,
    host: ExternalHost,
    artifact_kind: ArtifactKind,
) -> StagePreflightRequest:
    input_paths = () if isinstance(invocation.source.value, str) else (Path(invocation.source.value),)
    return StagePreflightRequest(
        invocation=invocation,
        artifact_location_request=SelectArtifactLocationRequest(artifact_kind, "portable-runner"),
        repository_request=RepositoryInspectionRequest(working_directory=host.root, input_paths=input_paths),
        cline_preflight_request=ClinePreflightRequest(command=("fake-cline",), required_skills=("fixture-skill",)),
    )


def _artifact(kind: ArtifactKind, path: str) -> ArtifactLocationResult:
    return ArtifactLocationResult(
        artifact_kind=kind,
        path=path,
        directory=Path(path).parent.as_posix(),
        source=ArtifactLocationSource.HOST_CONVENTION,
    )


def _snapshot(host: ExternalHost) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_root=host.root.as_posix(),
        head_commit=host.git("rev-parse", "HEAD").stdout.strip(),
        branch="feature/portable-proof",
        dirty_paths=host.status_paths(),
    )


def _plan_state(phase: PlanPhase, readiness: ReviewReadiness) -> PlanState:
    return PlanState(
        work_id="portable-host",
        phase=phase,
        specification=SPECIFICATION_PATH,
        specification_digest=SPECIFICATION_DIGEST,
        plan_revision=1,
        review_iteration=1,
        review_readiness=readiness,
        material_digest=MATERIAL_DIGEST,
        created_at=NOW,
        updated_at=NOW,
    )


def _idea_content() -> str:
    return "# Idea\n\n## Problem\nPortable coordination.\n\n## MVP scope\nOne bounded stage.\n"


def _specification_content() -> str:
    return (
        "# Specification\n\n## Objective\nPortable proof.\n\n"
        "## Boundaries\nNo remote effects.\n\n"
        "## Success criteria\nHost check passes.\n"
    )


def _plan_content() -> str:
    return (
        "# Plan\n\n## Objective\nImplement the accepted specification.\n\n## Slice host-1\n"
        "Use tools/verify-host --all.\n\n## Recovery\nResume attributable writes only.\n"
    )
