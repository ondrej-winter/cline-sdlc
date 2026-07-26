"""End-to-end application tests for bounded final-review remediation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
    FinalReviewRequest,
    FinalReviewResult,
    FinalReviewStatus,
    RemediationRecord,
    RemediationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import (
    FinalValidationRequest,
    FinalValidationResult,
    FinalValidationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.remediation import (
    RemediationExecutionStatus,
    RemediationRequest,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionBlocker,
    SliceExecutionRequest,
    SliceExecutionResult,
    SliceExecutionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    SliceCommitCandidate,
    SliceKind,
    SliceReconciliationRequest,
    SliceReconciliationResult,
    SliceReconciliationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.remediate import RemediateFinalReview
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
    SliceCommitRequest,
    SliceCommitResult,
    SliceCommitStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SelectedSlice

START = "a" * 40
COMMITS = ("b" * 40, "c" * 40)
SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
PLAN_PATH = "docs/plans/work.md"


@dataclass
class RecordingExecution:
    results: list[SliceExecutionResult]
    requests: list[SliceExecutionRequest] = field(default_factory=list)

    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        self.requests.append(request)
        return self.results.pop(0)


@dataclass
class RecordingReconciliation:
    requests: list[SliceReconciliationRequest] = field(default_factory=list)

    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
        self.requests.append(request)
        return SliceReconciliationResult(
            status=SliceReconciliationStatus.COMMIT_CANDIDATE,
            commit_candidate=SliceCommitCandidate(
                work_id=request.work_id,
                task_id=request.selection.task_id,
                slice_id=request.selection.slice_id,
                starting_head=request.slice_start_commit,
                material_digest=request.material_digest,
                paths=request.expected_paths,
                validation_evidence=(),
                kind=request.kind,
            ),
        )


@dataclass
class RecordingCommit:
    commits: list[str]
    requests: list[SliceCommitRequest] = field(default_factory=list)

    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        self.requests.append(request)
        return SliceCommitResult(status=SliceCommitStatus.COMMITTED, commit=self.commits.pop(0))


@dataclass
class RecordingFinalValidation:
    result: FinalValidationResult
    requests: list[FinalValidationRequest] = field(default_factory=list)

    def execute(self, request: FinalValidationRequest) -> FinalValidationResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingFinalReview:
    result: FinalReviewResult
    requests: list[FinalReviewRequest] = field(default_factory=list)

    def execute(self, request: FinalReviewRequest) -> FinalReviewResult:
        self.requests.append(request)
        return self.result


@dataclass
class RecordingProgress:
    current_head: str = START
    approval_ids: list[int] = field(default_factory=list)

    def prepare_execution(
        self, approval: InvocationApproval, record: RemediationRecord, selection: SelectedSlice
    ) -> SliceExecutionRequest:
        self.approval_ids.append(id(approval))
        return SliceExecutionRequest(
            approval=approval,
            selection=selection,
            specification_path="docs/specs/work.md",
            specification_content="Accepted specification",
            specification_digest=SPECIFICATION_DIGEST,
            plan_path=PLAN_PATH,
            plan_content="Accepted plan",
            material_digest=MATERIAL_DIGEST,
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
            cline_command="cline",
            timeout_seconds=30,
            focused_validation_commands=(_focused_validation(record.verification),),
            expected_paths=(PLAN_PATH, *record.path_scope),
            session_role=SessionRole.REMEDIATION,
        )

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        record: RemediationRecord,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        self.approval_ids.append(id(approval))
        return SliceReconciliationRequest(
            work_id="remediation-work",
            approval=approval,
            selection=selection,
            slice_start_commit=self.current_head,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
            plan_path=PLAN_PATH,
            expected_paths=(PLAN_PATH, *record.path_scope),
            execution=execution,
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
            kind=SliceKind.REMEDIATION,
        )

    def prepare_commit(
        self, approval: InvocationApproval, record: RemediationRecord, candidate: SliceCommitCandidate
    ) -> SliceCommitRequest:
        self.approval_ids.append(id(approval))
        return SliceCommitRequest(
            repository_root=Path("/repo"),
            plan_path=PLAN_PATH,
            current_plan_content=f"pending {record.finding_id}".encode(),
            updated_plan_content=f"completed {record.finding_id}".encode(),
            candidate=candidate,
            short_description=record.correction,
        )

    def prepare_validation(self, approval: InvocationApproval, end_commit: str) -> FinalValidationRequest:
        self.approval_ids.append(id(approval))
        self.current_head = end_commit
        return FinalValidationRequest(
            approval=approval,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
            start_commit=START,
            end_commit=end_commit,
            working_directory=Path("/repo"),
        )

    def prepare_confirmation(
        self, approval: InvocationApproval, end_commit: str, validation: FinalValidationResult
    ) -> FinalReviewRequest:
        self.approval_ids.append(id(approval))
        return FinalReviewRequest(
            approval=approval,
            specification_path="docs/specs/work.md",
            specification_content="Accepted specification",
            specification_digest=SPECIFICATION_DIGEST,
            plan_path=PLAN_PATH,
            plan_content="Accepted plan",
            material_digest=MATERIAL_DIGEST,
            repository_rules="Preserve boundaries.",
            repository_request=RepositoryInspectionRequest(working_directory=Path("/repo")),
            cline_command="cline",
            timeout_seconds=30,
            start_commit=START,
            end_commit=end_commit,
            final_validation=validation,
        )


def test_remediates_each_finding_once_then_revalidates_and_confirms_once() -> None:
    approval = _approval()
    records = (_record("FINAL-001", "src/one.py"), _record("FINAL-002", "src/two.py"))
    validation_result = _validation_result(COMMITS[-1])
    execution = RecordingExecution([_completed_execution(), _completed_execution()])
    reconciliation = RecordingReconciliation()
    commit = RecordingCommit(list(COMMITS))
    validation = RecordingFinalValidation(validation_result)
    review = RecordingFinalReview(_clean_review())
    progress = RecordingProgress()

    result = _use_case(progress, execution, reconciliation, commit, validation, review).execute(
        _request(approval, records)
    )

    assert result.status is RemediationExecutionStatus.COMPLETED
    assert result.commits == COMMITS
    assert result.final_validation is validation_result
    assert all(record.status is RemediationStatus.COMPLETED for record in result.remediation_records)
    assert all(record.attempt_count == 1 for record in result.remediation_records)
    assert [request.session_role for request in execution.requests] == [SessionRole.REMEDIATION] * 2
    assert [request.kind for request in reconciliation.requests] == [SliceKind.REMEDIATION] * 2
    assert [request.candidate.kind for request in commit.requests] == [SliceKind.REMEDIATION] * 2
    assert [request.candidate.slice_id for request in commit.requests] == ["FINAL-001", "FINAL-002"]
    assert all(request.material_digest == MATERIAL_DIGEST for request in execution.requests)
    assert len(validation.requests) == 1
    assert validation.requests[0].end_commit == COMMITS[-1]
    assert len(review.requests) == 1
    assert review.requests[0].final_validation is validation_result
    assert set(progress.approval_ids) == {id(approval)}


def test_failed_remediation_starts_no_later_work_validation_or_confirmation() -> None:
    execution = RecordingExecution(
        [
            SliceExecutionResult(
                status=SliceExecutionStatus.FAILED,
                blocker=SliceExecutionBlocker("focused_validation_failed", "focused validation failed"),
            )
        ]
    )
    reconciliation = RecordingReconciliation()
    commit = RecordingCommit(list(COMMITS))
    validation = RecordingFinalValidation(_validation_result(COMMITS[-1]))
    review = RecordingFinalReview(_clean_review())

    result = _use_case(RecordingProgress(), execution, reconciliation, commit, validation, review).execute(
        _request(_approval(), (_record("FINAL-001", "src/one.py"), _record("FINAL-002", "src/two.py")))
    )

    assert result.status is RemediationExecutionStatus.FAILED
    assert result.commits == ()
    assert len(execution.requests) == 1
    assert reconciliation.requests == []
    assert commit.requests == []
    assert validation.requests == []
    assert review.requests == []


@pytest.mark.parametrize(
    ("finding_id", "severity", "expected_code"),
    [
        ("FINAL-001", FindingSeverity.MINOR, "repeated_final_finding"),
        ("FINAL-099", FindingSeverity.MAJOR, "new_unresolved_final_finding"),
        ("FINAL-100", FindingSeverity.BLOCKING, "new_unresolved_final_finding"),
    ],
)
def test_confirmation_blocks_repeated_or_new_unresolved_findings(
    finding_id: str, severity: FindingSeverity, expected_code: str
) -> None:
    validation_result = _validation_result(COMMITS[0])
    review_result = FinalReviewResult(
        status=FinalReviewStatus.BLOCKED,
        readiness=PlanReviewReadiness.CHANGES_REQUIRED,
        findings=(_finding(finding_id, severity),),
    )
    result = _use_case(
        RecordingProgress(),
        RecordingExecution([_completed_execution()]),
        RecordingReconciliation(),
        RecordingCommit([COMMITS[0]]),
        RecordingFinalValidation(validation_result),
        RecordingFinalReview(review_result),
    ).execute(_request(_approval(), (_record("FINAL-001", "src/one.py"),)))

    assert result.status is RemediationExecutionStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == expected_code
    assert result.final_validation is validation_result
    assert result.confirmation_review is review_result


def test_request_rejects_a_remediation_record_with_a_prior_attempt() -> None:
    attempted = replace(_record("FINAL-001", "src/one.py"), status=RemediationStatus.COMPLETED, attempt_count=1)

    with pytest.raises(ValueError, match="no prior attempt"):
        _request(_approval(), (attempted,))


def _use_case(  # noqa: PLR0913 - Test construction keeps each recording boundary explicit.
    progress: RecordingProgress,
    execution: RecordingExecution,
    reconciliation: RecordingReconciliation,
    commit: RecordingCommit,
    validation: RecordingFinalValidation,
    review: RecordingFinalReview,
) -> RemediateFinalReview:
    return RemediateFinalReview(
        progress=progress,
        slice_execution=execution,
        slice_reconciliation=reconciliation,
        slice_commit=commit,
        final_validation=validation,
        final_review=review,
    )


def _request(approval: InvocationApproval, records: tuple[RemediationRecord, ...]) -> RemediationRequest:
    return RemediationRequest(
        approval=approval,
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        initial_review=FinalReviewResult(
            status=FinalReviewStatus.REMEDIATION_REQUIRED,
            readiness=PlanReviewReadiness.CHANGES_REQUIRED,
            findings=tuple(_finding(record.finding_id, FindingSeverity.MAJOR) for record in records),
            remediation_records=records,
        ),
    )


def _approval() -> InvocationApproval:
    return InvocationApproval(
        run_id="run-remediation",
        profile="balanced",
        starting_head=START,
        approved_at=datetime(2026, 7, 26, 18, tzinfo=UTC),
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )


def _record(finding_id: str, path: str) -> RemediationRecord:
    return RemediationRecord(
        finding_id=finding_id,
        requirement=f"Requirement for {finding_id}",
        path_scope=(path,),
        correction=f"Correct {finding_id}",
        verification=f"uv run pytest tests/{finding_id.lower()}.py",
    )


def _finding(finding_id: str, severity: FindingSeverity) -> Finding:
    return Finding(
        id=finding_id,
        severity=severity,
        status=FindingStatus.OPEN,
        summary=f"Finding {finding_id}",
        evidence="Observed confirmation evidence.",
        required_correction="Correct the finding.",
        affected_sections=("Task 5.3",),
    )


def _completed_execution() -> SliceExecutionResult:
    return SliceExecutionResult(status=SliceExecutionStatus.COMPLETED)


def _focused_validation(command: str) -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand("uv", ("run", "pytest", command.rsplit(" ", maxsplit=1)[-1])),
        source=ValidationCommandSource.EXPLICIT,
        reason="approved remediation verification",
    )


def _validation_result(end_commit: str) -> FinalValidationResult:
    evidence = ValidationEvidence(
        scope=ValidationScope.BROAD,
        command=ValidationCommand("uv", ("run", "pytest")),
        status=ValidationEvidenceStatus.PASSED,
        summary="affected broad validation passed",
        exit_code=0,
        recorded_at=datetime(2026, 7, 26, 18, 30, tzinfo=UTC),
    )
    return FinalValidationResult(
        status=FinalValidationStatus.COMPLETED,
        run_id="run-remediation",
        commit_range=(START, end_commit),
        evidence=(evidence,),
    )


def _clean_review() -> FinalReviewResult:
    return FinalReviewResult(status=FinalReviewStatus.CLEAN, readiness=PlanReviewReadiness.READY)
