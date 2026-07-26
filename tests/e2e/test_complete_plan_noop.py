"""End-to-end proof that verified complete plans are read-only no-ops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.domain.findings import PlanReviewReadiness
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
    FinalReviewResult,
    FinalReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import (
    FinalValidationResult,
    FinalValidationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.finalization import PlanFinalizationRequest
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.finalize_plan import FinalizeImplementationPlan
from cline_sdlc.features.repository_coordination.adapters.outbound.git_finalization import (
    GitCliFinalizationHistoryReader,
    GitCliFinalizer,
)
from cline_sdlc.features.repository_coordination.adapters.outbound.plan_artifact import StrictPlanArtifactInspector
from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
    FinalizationResult,
    FinalizationStatus,
    RepositoryFinalizationRequest,
)
from cline_sdlc.features.repository_coordination.application.use_cases.finalize_plan import FinalizePlan
from tests.finalization_support import (
    APPROVED_AT,
    complete_noop_request,
    finalization_request,
    git_stdout,
    initialized_repository,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class RecordingRepositoryFinalization:
    """Record lifecycle calls while delegating to the real repository use case."""

    delegate: FinalizePlan
    calls: int = 0

    def execute(self, request: RepositoryFinalizationRequest) -> FinalizationResult:
        self.calls += 1
        return self.delegate.execute(request)


def test_verified_complete_plan_returns_without_write_session_or_commit(tmp_path: Path) -> None:
    repository = initialized_repository(tmp_path)
    repository_use_case = production_repository_use_case()
    created = repository_use_case.execute(finalization_request(repository))
    assert created.status is FinalizationStatus.FINALIZED
    complete_request = complete_noop_request(repository)
    head = git_stdout(repository, "rev-parse", "HEAD")
    recording = RecordingRepositoryFinalization(repository_use_case)

    result = FinalizeImplementationPlan(recording).execute(
        PlanFinalizationRequest(
            approval=complete_request.approval,
            final_validation=clean_validation(complete_request, head),
            final_review=FinalReviewResult(
                status=FinalReviewStatus.CLEAN,
                readiness=PlanReviewReadiness.READY,
            ),
            repository_request=complete_request,
        )
    )

    assert result.repository_result.status is FinalizationStatus.ALREADY_COMPLETE
    assert recording.calls == 1
    assert git_stdout(repository, "rev-parse", "HEAD") == head
    assert git_stdout(repository, "status", "--porcelain=v1") == ""


def test_unclean_final_review_blocks_before_repository_finalization(tmp_path: Path) -> None:
    repository = initialized_repository(tmp_path)
    request = finalization_request(repository)
    recording = RecordingRepositoryFinalization(production_repository_use_case())
    validation = clean_validation(request, "b" * 40)

    result = FinalizeImplementationPlan(recording).execute(
        PlanFinalizationRequest(
            approval=request.approval,
            final_validation=validation,
            final_review=FinalReviewResult(status=FinalReviewStatus.BLOCKED),
            repository_request=request,
        )
    )

    assert result.repository_result.status is FinalizationStatus.BLOCKED
    assert recording.calls == 0
    assert git_stdout(repository, "rev-parse", "HEAD") == request.approval.starting_head


def clean_validation(request: RepositoryFinalizationRequest, end_commit: str) -> FinalValidationResult:
    """Return one passing broad evidence result tied to the request approval."""
    return FinalValidationResult(
        status=FinalValidationStatus.COMPLETED,
        run_id=request.approval.run_id,
        commit_range=(request.approval.starting_head, end_commit),
        evidence=(
            ValidationEvidence(
                scope=ValidationScope.BROAD,
                status=ValidationEvidenceStatus.PASSED,
                summary="Broad validation passed.",
                command=ValidationCommand(executable="uv", arguments=("run", "pytest")),
                exit_code=0,
                recorded_at=APPROVED_AT,
            ),
        ),
    )


def production_repository_use_case() -> FinalizePlan:
    """Construct production repository finalization adapters."""
    return FinalizePlan(
        StrictPlanArtifactInspector(),
        GitCliFinalizer(),
        GitCliFinalizationHistoryReader(),
    )
