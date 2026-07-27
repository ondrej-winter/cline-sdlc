"""Contract tests for the initial independent implementation-plan review."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanInspectionRequest,
    AuthoredPlanValidationRequest,
    AuthoredPlanValidationResult,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.plan_review import (
    PlanReviewProgressRequest,
    PlanReviewProgressResult,
)
from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase, PlanState, ReviewReadiness
from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionProcessStatus, ClineSessionResult
from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest, InvocationSource
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import (
    PlanReviewRequest,
    PlanReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import StagePreflightRequest
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptObservation,
    SessionAttemptRequest,
    SessionAttemptResult,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.review_plan import ReviewPlan
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionRequest,
    RepositorySnapshot,
)

SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
NOW = datetime(2026, 7, 24, 22, tzinfo=UTC)


@dataclass
class RecordingReader:
    result: AuthoredPlanValidationRequest
    requests: list[AuthoredPlanInspectionRequest]

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        self.requests.append(request)
        return self.result


@dataclass
class SequencedReader:
    results: list[AuthoredPlanValidationRequest]

    def read(self, _request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        return self.results.pop(0)


@dataclass
class RecordingValidator:
    requests: list[AuthoredPlanValidationRequest]

    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        self.requests.append(request)
        return AuthoredPlanValidationResult(
            valid=True,
            plan_path=_plan_path(),
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
        )


@dataclass
class RecordingAttempts:
    result: SessionAttemptResult
    requests: list[SessionAttemptRequest]

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingProgressWriter:
    requests: list[PlanReviewProgressRequest]

    def execute(self, request: PlanReviewProgressRequest) -> PlanReviewProgressResult:
        self.requests.append(request)
        return PlanReviewProgressResult(updated=True, plan_path=request.plan_path, material_digest=MATERIAL_DIGEST)


@dataclass(frozen=True)
class FixedClock:
    def now(self) -> datetime:
        return NOW


def test_initial_ready_review_uses_fresh_read_only_context_and_needs_no_revision() -> None:
    attempts = RecordingAttempts(_completed_attempt(), [])
    progress = RecordingProgressWriter([])

    result = _reviewer(attempts=attempts, progress=progress).execute(plan_review_request())

    assert result.ready
    assert result.readiness is PlanReviewReadiness.READY
    assert result.findings == ()
    assert result.material_digest == MATERIAL_DIGEST
    prompt = attempts.requests[0].session_request.command[-1]
    assert "review-implementation-plan" in prompt
    assert "fresh read-only context" in prompt
    assert "author private reasoning" in prompt
    assert "confirm the author's conclusion" not in prompt
    assert progress.requests[0].updated_at == NOW


def test_initial_major_finding_requires_revision_and_preserves_complete_record() -> None:
    finding = _finding()
    progress = RecordingProgressWriter([])

    result = _reviewer(
        attempts=RecordingAttempts(_completed_attempt(findings=(finding,)), []),
        progress=progress,
    ).execute(plan_review_request())

    assert result.status is PlanReviewStatus.CHANGES_REQUIRED
    assert result.findings == (finding,)
    assert progress.requests[0].findings == (finding,)
    assert progress.requests[0].readiness is PlanReviewReadiness.CHANGES_REQUIRED


def test_observed_reviewer_write_blocks_progress_update() -> None:
    progress = RecordingProgressWriter([])
    result = _reviewer(
        attempts=RecordingAttempts(_completed_attempt(dirty_after=("docs/plans/example-plan.md",)), []),
        progress=progress,
    ).execute(plan_review_request())

    assert result.status is PlanReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "reviewer_write_observed"
    assert progress.requests == []


def test_wrong_session_role_blocks_progress_update() -> None:
    progress = RecordingProgressWriter([])
    result = _reviewer(
        attempts=RecordingAttempts(_completed_attempt(role=SessionRole.PLAN_AUTHOR), []),
        progress=progress,
    ).execute(plan_review_request())

    assert result.status is PlanReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "unexpected_session_role"
    assert progress.requests == []


def test_re_review_blocks_when_prior_finding_is_omitted() -> None:
    progress = RecordingProgressWriter([])
    request = replace(
        plan_review_request(),
        previous_plan_state=_reviewing_state(),
        prior_findings=(_finding(),),
        initial_review=False,
    )

    result = _reviewer(
        attempts=RecordingAttempts(_completed_attempt(), []),
        progress=progress,
    ).execute(request)

    assert result.status is PlanReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "finding_traceability_mismatch"
    assert progress.requests == []


def test_re_review_blocks_when_prior_findings_are_reordered() -> None:
    first = _finding()
    second = _finding(finding_id="PLAN-002")
    progress = RecordingProgressWriter([])
    request = replace(
        plan_review_request(),
        previous_plan_state=_reviewing_state(),
        prior_findings=(first, second),
        initial_review=False,
    )

    result = _reviewer(
        attempts=RecordingAttempts(_completed_attempt(findings=(second, first)), []),
        progress=progress,
    ).execute(request)

    assert result.status is PlanReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "finding_traceability_mismatch"
    assert progress.requests == []


def test_re_review_allows_new_findings_after_preserved_prior_findings() -> None:
    first = _finding()
    second = _finding(finding_id="PLAN-002")
    progress = RecordingProgressWriter([])
    request = replace(
        plan_review_request(),
        previous_plan_state=_reviewing_state(),
        prior_findings=(first,),
        initial_review=False,
    )

    result = _reviewer(
        attempts=RecordingAttempts(_completed_attempt(findings=(first, second)), []),
        progress=progress,
    ).execute(request)

    assert result.status is PlanReviewStatus.CHANGES_REQUIRED
    assert result.findings == (first, second)
    assert progress.requests[0].initial_review is False


def test_unchanged_dirty_paths_do_not_hide_reviewer_content_write() -> None:
    progress = RecordingProgressWriter([])
    initial = _content()
    changed = AuthoredPlanValidationRequest(
        specification_path=initial.specification_path,
        specification_content=initial.specification_content,
        plan_path=initial.plan_path,
        plan_content=b"reviewer changed the plan",
        plan_state=initial.plan_state,
    )
    dirty_paths = (_plan_path(),)
    reviewer = ReviewPlan(
        content_reader=SequencedReader([initial, changed]),
        plan_validator=RecordingValidator([]),
        session_attempts=RecordingAttempts(
            _completed_attempt(dirty_before=dirty_paths, dirty_after=dirty_paths),
            [],
        ),
        progress_writer=progress,
        clock=FixedClock(),
    )

    result = reviewer.execute(plan_review_request())

    assert result.status is PlanReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "reviewer_write_observed"
    assert progress.requests == []


def _reviewer(
    *,
    attempts: RecordingAttempts | None = None,
    progress: RecordingProgressWriter | None = None,
) -> ReviewPlan:
    return ReviewPlan(
        content_reader=RecordingReader(_content(), []),
        plan_validator=RecordingValidator([]),
        session_attempts=attempts or RecordingAttempts(_completed_attempt(), []),
        progress_writer=progress or RecordingProgressWriter([]),
        clock=FixedClock(),
    )


def plan_review_request() -> PlanReviewRequest:
    invocation = InvocationRequest(
        source=InvocationSource.from_spec_file(Path(_spec_path())),
        timeout_seconds=30,
        cline_command="cline",
        stage=LifecycleStage.PLAN_CREATION_AND_REVIEW,
    )
    return PlanReviewRequest(
        invocation=invocation,
        preflight_request=StagePreflightRequest(
            invocation=invocation,
            artifact_location_request=None,
            repository_request=RepositoryInspectionRequest(
                working_directory=Path("/repo"),
                input_paths=(Path(_spec_path()),),
                managed_paths=(Path("docs/plans"),),
            ),
            cline_preflight_request=ClinePreflightRequest(
                command=("cline",),
                required_skills=("review-implementation-plan",),
            ),
        ),
        plan_path=_plan_path(),
    )


def _completed_attempt(
    *,
    findings: tuple[Finding, ...] = (),
    role: SessionRole = SessionRole.PLAN_REVIEWER,
    dirty_before: tuple[str, ...] = (),
    dirty_after: tuple[str, ...] = (),
) -> SessionAttemptResult:
    readiness = PlanReviewReadiness.CHANGES_REQUIRED if findings else PlanReviewReadiness.READY
    outcome = SessionOutcome(
        session_role=role,
        status=SessionStatus.COMPLETED,
        reason=readiness.value,
        artifact_paths=(_plan_path(),),
        findings=findings if role is SessionRole.PLAN_REVIEWER else (),
        finding_ids=tuple(finding.id for finding in findings) if role is SessionRole.PLAN_REVIEWER else (),
        review_readiness=readiness if role is SessionRole.PLAN_REVIEWER else None,
    )
    session = ClineSessionResult(
        process_status=ClineSessionProcessStatus.EXITED,
        exit_code=0,
        terminal_outcomes=(outcome,),
    )
    before = _snapshot(dirty_paths=dirty_before)
    after = _snapshot(dirty_paths=dirty_after)
    return SessionAttemptResult(
        status=SessionAttemptStatus.COMPLETED,
        attempts=(
            SessionAttemptObservation(
                attempt_number=1,
                before_snapshot=before,
                session_result=session,
                after_snapshot=after,
            ),
        ),
        terminal_session_result=session,
    )


def _content() -> AuthoredPlanValidationRequest:
    return AuthoredPlanValidationRequest(
        specification_path=_spec_path(),
        specification_content=b"specification",
        plan_path=_plan_path(),
        plan_content=b"plan",
        plan_state=PlanState(
            work_id="example-work",
            phase=PlanPhase.DRAFTING,
            specification=_spec_path(),
            specification_digest=SPECIFICATION_DIGEST,
            plan_revision=1,
            review_iteration=1,
            review_readiness=ReviewReadiness.NOT_REVIEWED,
            material_digest=MATERIAL_DIGEST,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def _finding(*, finding_id: str = "PLAN-001") -> Finding:
    return Finding(
        id=finding_id,
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="Validation scope is incomplete.",
        evidence="The plan omits the broad quality gate.",
        required_correction="Add the broad quality gate.",
        affected_sections=("Verification",),
    )


def _reviewing_state() -> PlanState:
    return PlanState(
        work_id="example-work",
        phase=PlanPhase.REVIEWING,
        specification=_spec_path(),
        specification_digest=SPECIFICATION_DIGEST,
        plan_revision=1,
        review_iteration=1,
        review_readiness=ReviewReadiness.CHANGES_REQUIRED,
        material_digest=MATERIAL_DIGEST,
        created_at=NOW,
        updated_at=NOW,
    )


def _snapshot(*, dirty_paths: tuple[str, ...] = ()) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_root="/repo",
        head_commit="abc123",
        branch="feature/plan",
        dirty_paths=dirty_paths,
    )


def _spec_path() -> str:
    return "docs/specs/example-spec.md"


def _plan_path() -> str:
    return "docs/plans/example-plan.md"
