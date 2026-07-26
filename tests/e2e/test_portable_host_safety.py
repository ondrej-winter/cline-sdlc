"""Portable-host end-to-end safety, recovery, and audit proofs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
    FinalReviewBlocker,
    FinalReviewResult,
    FinalReviewStatus,
    RemediationRecord,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_implementation import (
    PlanImplementationRequest,
    PlanImplementationResult,
    PlanImplementationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionBlocker,
    SliceExecutionRequest,
    SliceExecutionResult,
    SliceExecutionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
    PartialSliceRecovery,
    SliceCommitCandidate,
    SliceReconciliationBlocker,
    SliceReconciliationRequest,
    SliceReconciliationResult,
    SliceReconciliationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PartialSliceProgress,
    PlanSliceDefinition,
    PlanTaskDefinition,
    SelectedSlice,
    SliceCompletionEvidence,
    SliceSelectionRequest,
    SliceSelectionResult,
    SliceSelectionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.implement_plan import ImplementPlan
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_slice import SelectSlice
from cline_sdlc.features.operation_policy.application.dtos.operation import (
    ClassifyOperationRequest,
)
from cline_sdlc.features.operation_policy.application.use_cases.classify_operation import ClassifyOperation
from cline_sdlc.features.operation_policy.domain.policy import OperationDecisionStatus
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest
from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
    SliceCommitRequest,
    SliceCommitResult,
    SliceCommitStatus,
)
from cline_sdlc.features.run_audit.adapters.outbound.filesystem_store import FilesystemRunAuditStore
from cline_sdlc.features.run_audit.application.dtos.run_audit import RunAuditEvent, RunAuditRequest
from cline_sdlc.features.run_audit.application.use_cases.record_run_summary import RecordRunSummary
from tests.e2e.conftest import HOST_CHECK, PLAN_PATH, SPECIFICATION_PATH

if TYPE_CHECKING:
    from tests.e2e.conftest import ExternalHost

START = "a" * 40
COMMITS = ("b" * 40, "c" * 40)
SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
MATERIAL_DIGEST = f"sha256:{'2' * 64}"
INJECTED_TEST_SECRET = "fixture-token-super-secret"  # noqa: S105 - Deliberate fake leak-detection fixture.
EXPECTED_IMPLEMENTATION_HISTORY_LENGTH = 3


@dataclass
class SequencedExecution:
    results: list[SliceExecutionResult]
    requests: list[SliceExecutionRequest] = field(default_factory=list)

    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        self.requests.append(request)
        return self.results.pop(0)


class PassingReconciliation:
    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
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
            ),
        )


class ReconciliationPort(Protocol):
    def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
        """Return independent reconciliation evidence."""


@dataclass
class RecordingCommit:
    commits: list[str]
    requests: list[SliceCommitRequest] = field(default_factory=list)

    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        self.requests.append(request)
        return SliceCommitResult(status=SliceCommitStatus.COMMITTED, commit=self.commits.pop(0))


@dataclass
class HostWritingExecution:
    host: ExternalHost
    requests: list[SliceExecutionRequest] = field(default_factory=list)

    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        self.requests.append(request)
        self.host.write_text(request.plan_path, f"active {request.selection.slice_id}\n")
        self.host.write_text(f"app/{request.selection.slice_id}.txt", f"implemented {request.selection.slice_id}\n")
        return SliceExecutionResult(status=SliceExecutionStatus.COMPLETED)


@dataclass
class HostGitCommit:
    host: ExternalHost
    requests: list[SliceCommitRequest] = field(default_factory=list)

    def execute(self, request: SliceCommitRequest) -> SliceCommitResult:
        self.requests.append(request)
        self.host.write_text(request.plan_path, request.updated_plan_content.decode())
        self.host.git("add", "--", *request.candidate.paths)
        self.host.git(
            "commit",
            "--no-gpg-sign",
            "-m",
            f"test(sdlc): complete {request.candidate.slice_id}",
            "-m",
            f"Cline-SDLC-Work-ID: {request.candidate.work_id}\n"
            f"Cline-SDLC-Slice-ID: {request.candidate.slice_id}\n"
            "Cline-SDLC-Slice-Kind: implementation\n"
            f"Cline-SDLC-Material-Digest: {request.candidate.material_digest}",
        )
        return SliceCommitResult(
            status=SliceCommitStatus.COMMITTED,
            commit=self.host.git("rev-parse", "HEAD").stdout.strip(),
        )


@dataclass
class PortableProgress:
    host: ExternalHost
    next_results: list[SliceSelectionResult]
    head: str = START

    def prepare_execution(self, approval: InvocationApproval, selection: SelectedSlice) -> SliceExecutionRequest:
        return SliceExecutionRequest(
            approval=approval,
            selection=selection,
            specification_path=SPECIFICATION_PATH,
            specification_content="# Accepted external-host specification",
            specification_digest=SPECIFICATION_DIGEST,
            plan_path=PLAN_PATH,
            plan_content="# Ready external-host plan",
            material_digest=MATERIAL_DIGEST,
            repository_request=RepositoryInspectionRequest(working_directory=self.host.root),
            cline_command="fake-cline",
            timeout_seconds=30,
            focused_validation_commands=(_host_validation(),),
            expected_paths=(PLAN_PATH, f"app/{selection.slice_id}.txt"),
        )

    def prepare_reconciliation(
        self,
        approval: InvocationApproval,
        selection: SelectedSlice,
        execution: SliceExecutionResult,
    ) -> SliceReconciliationRequest:
        return SliceReconciliationRequest(
            work_id="portable-host",
            approval=approval,
            selection=selection,
            slice_start_commit=self.head,
            specification_digest=SPECIFICATION_DIGEST,
            material_digest=MATERIAL_DIGEST,
            plan_path=PLAN_PATH,
            expected_paths=(PLAN_PATH, f"app/{selection.slice_id}.txt"),
            execution=execution,
            repository_request=RepositoryInspectionRequest(working_directory=self.host.root),
        )

    def prepare_commit(self, _approval: InvocationApproval, candidate: SliceCommitCandidate) -> SliceCommitRequest:
        return SliceCommitRequest(
            repository_root=self.host.root,
            plan_path=PLAN_PATH,
            current_plan_content=f"current {candidate.slice_id}".encode(),
            updated_plan_content=f"completed {candidate.slice_id}".encode(),
            candidate=candidate,
            short_description=f"portable {candidate.slice_id}",
        )

    def select_after_commit(self, _approval: InvocationApproval, commit: str) -> SliceSelectionResult:
        self.head = commit
        return self.next_results.pop(0)


def test_plan_input_completes_serial_external_host_slices_at_plan_boundary(external_host: ExternalHost) -> None:
    selections = (_selected("host-1"), _selected("host-2"))
    execution = SequencedExecution([_completed_execution(), _completed_execution()])
    commit = RecordingCommit(list(COMMITS))
    progress = PortableProgress(
        external_host,
        [
            selections[1],
            SliceSelectionResult(
                status=SliceSelectionStatus.COMPLETE,
                completed_slice_ids=("host-1", "host-2"),
            ),
        ],
    )

    result = ImplementPlan(
        progress=progress,
        slice_execution=execution,
        slice_reconciliation=PassingReconciliation(),
        slice_commit=commit,
    ).execute(
        PlanImplementationRequest(
            approval=_approval(),
            initial_selection=_required_selection(selections[0]),
        )
    )

    assert result.status is PlanImplementationStatus.COMPLETED
    assert result.completed_slice_ids == ("host-1", "host-2")
    assert result.commits == COMMITS
    assert [request.focused_validation_commands[0].command.executable for request in execution.requests] == [
        HOST_CHECK,
        HOST_CHECK,
    ]
    assert all(request.specification_path == SPECIFICATION_PATH for request in execution.requests)
    assert all(request.plan_path == PLAN_PATH for request in execution.requests)


def test_plan_input_records_exact_slice_and_finalization_ownership(external_host: ExternalHost) -> None:
    external_host.write_text(PLAN_PATH, "ready external-host plan\n")
    start = external_host.commit_all("Accept portable implementation plan")
    selections = (_selected("host-1"), _selected("host-2"))
    execution = HostWritingExecution(external_host)
    commit = HostGitCommit(external_host)
    progress = PortableProgress(
        external_host,
        [
            selections[1],
            SliceSelectionResult(
                status=SliceSelectionStatus.COMPLETE,
                completed_slice_ids=("host-1", "host-2"),
            ),
        ],
        head=start,
    )

    result = ImplementPlan(
        progress=progress,
        slice_execution=execution,
        slice_reconciliation=PassingReconciliation(),
        slice_commit=commit,
    ).execute(
        PlanImplementationRequest(
            approval=_approval(starting_head=start),
            initial_selection=_required_selection(selections[0]),
        )
    )
    external_host.write_text(PLAN_PATH, "complete external-host plan\n")
    external_host.git("add", "--", PLAN_PATH)
    external_host.git(
        "commit",
        "--no-gpg-sign",
        "-m",
        "test(sdlc): finalize portable plan",
        "-m",
        "Cline-SDLC-Work-ID: portable-host\nCline-SDLC-Plan-Finalization: true",
    )

    assert result.status is PlanImplementationStatus.COMPLETED
    commits = external_host.git("rev-list", "--reverse", f"{start}..HEAD").stdout.splitlines()
    assert len(commits) == EXPECTED_IMPLEMENTATION_HISTORY_LENGTH
    assert _commit_paths(external_host, commits[0]) == {PLAN_PATH, "app/host-1.txt"}
    assert _commit_paths(external_host, commits[1]) == {PLAN_PATH, "app/host-2.txt"}
    assert _commit_paths(external_host, commits[2]) == {PLAN_PATH}
    assert "Cline-SDLC-Slice-ID: host-1" in _commit_message(external_host, commits[0])
    assert "Cline-SDLC-Slice-ID: host-2" in _commit_message(external_host, commits[1])
    assert "Cline-SDLC-Plan-Finalization: true" in _commit_message(external_host, commits[2])
    assert external_host.status_paths() == ()


def test_malformed_outcome_stops_before_reconciliation_or_later_slice(external_host: ExternalHost) -> None:
    execution = SequencedExecution(
        [
            SliceExecutionResult(
                status=SliceExecutionStatus.FAILED,
                blocker=SliceExecutionBlocker("invalid_session_outcome", "malformed outcome after bounded retry"),
            )
        ]
    )
    commit = RecordingCommit(list(COMMITS))

    result = _implementation(external_host, execution, PassingReconciliation(), commit)

    assert result.status is PlanImplementationStatus.FAILED
    assert result.commits == ()
    assert len(execution.requests) == 1
    assert commit.requests == []


def test_material_drift_records_attributable_recovery_and_stops(external_host: ExternalHost) -> None:
    blocker = SliceReconciliationBlocker("material_digest_diverged", "approved material changed")

    class DriftReconciliation:
        def execute(self, request: SliceReconciliationRequest) -> SliceReconciliationResult:
            return SliceReconciliationResult(
                status=SliceReconciliationStatus.RECOVERY_REQUIRED,
                recovery=PartialSliceRecovery(
                    task_id=request.selection.task_id,
                    slice_id=request.selection.slice_id,
                    slice_start_commit=request.slice_start_commit,
                    paths=request.expected_paths,
                    blocker=blocker,
                ),
                blocker=blocker,
            )

    result = _implementation(
        external_host,
        SequencedExecution([_completed_execution()]),
        DriftReconciliation(),
        RecordingCommit(list(COMMITS)),
    )

    assert result.status is PlanImplementationStatus.RECOVERY_REQUIRED
    assert result.blocker is not None
    assert result.blocker.code == "material_digest_diverged"


def test_prohibited_operation_and_material_finding_fail_closed() -> None:
    policy = ClassifyOperation().execute(
        ClassifyOperationRequest(executable="git", arguments=("push", "origin", "HEAD"))
    )
    material_finding = Finding(
        id="FINAL-900",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="A new persistence architecture is required.",
        evidence="The finding changes an approved architecture boundary.",
        required_correction="Revise material plan content and obtain new approval.",
        affected_sections=("Architecture",),
    )
    review = FinalReviewResult(
        status=FinalReviewStatus.BLOCKED,
        readiness=PlanReviewReadiness.BLOCKED,
        findings=(material_finding,),
        blocker=FinalReviewBlocker("material_finding", "finding requires a new material decision"),
    )

    assert policy.status is OperationDecisionStatus.APPROVAL_REQUIRED
    assert review.status is FinalReviewStatus.BLOCKED
    assert review.remediation_records == ()


def test_remediable_finding_stays_bounded_to_external_host_paths_and_command() -> None:
    record = RemediationRecord(
        finding_id="FINAL-101",
        requirement="The accepted host workflow requires a passing host check.",
        path_scope=("app/host-1.txt",),
        correction="Restore the missing portable host behavior.",
        verification=f"{HOST_CHECK} --focused",
    )
    review = FinalReviewResult(
        status=FinalReviewStatus.REMEDIATION_REQUIRED,
        readiness=PlanReviewReadiness.CHANGES_REQUIRED,
        findings=(
            Finding(
                id=record.finding_id,
                severity=FindingSeverity.MAJOR,
                status=FindingStatus.OPEN,
                summary="Portable host behavior is incomplete.",
                evidence="The accepted host check identifies one bounded defect.",
                required_correction=record.correction,
                affected_sections=("Success criteria",),
            ),
        ),
        remediation_records=(record,),
    )

    assert review.status is FinalReviewStatus.REMEDIATION_REQUIRED
    assert review.remediation_records == (record,)
    assert record.path_scope == ("app/host-1.txt",)
    assert record.verification == "tools/verify-host --focused"


def test_interruption_resume_contract_and_secret_safe_ignored_summary(external_host: ExternalHost) -> None:
    interrupted = SliceExecutionResult(
        status=SliceExecutionStatus.INTERRUPTED,
        changed_paths=(PLAN_PATH, "app/host-1.txt"),
        blocker=SliceExecutionBlocker("session_interrupted", "active child terminated safely"),
    )
    result = _implementation(
        external_host,
        SequencedExecution([interrupted]),
        PassingReconciliation(),
        RecordingCommit(list(COMMITS)),
    )
    audit = RecordRunSummary(FilesystemRunAuditStore()).execute(
        RunAuditRequest(
            repository_root=external_host.root,
            run_id="portable-interruption",
            terminal_status=result.status.value,
            events=(RunAuditEvent("recovery", f"resume {PLAN_PATH}; credential={INJECTED_TEST_SECRET}"),),
            sensitive_fragments=(INJECTED_TEST_SECRET,),
        )
    )

    assert result.status is PlanImplementationStatus.INTERRUPTED
    assert result.commits == ()
    assert audit.recorded
    assert audit.summary_path is not None
    summary = external_host.read_text(audit.summary_path)
    assert "<redacted>" in summary
    assert INJECTED_TEST_SECRET not in summary
    assert INJECTED_TEST_SECRET not in external_host.history_text()
    assert external_host.git("status", "--porcelain", "--ignored", ".cline-sdlc").stdout.startswith("!! .cline-sdlc/")


def test_recorded_external_host_partial_slice_resumes_before_later_work(external_host: ExternalHost) -> None:
    selection = SelectSlice().execute(
        SliceSelectionRequest(
            tasks=(
                PlanTaskDefinition(
                    task_id="portable-task",
                    slices=(
                        PlanSliceDefinition(slice_id="host-1"),
                        PlanSliceDefinition(slice_id="host-2", dependencies=("host-1",)),
                    ),
                ),
            ),
            completed_slice_ids=("host-1",),
            completion_evidence=(SliceCompletionEvidence(slice_id="host-1", completed=True),),
            partial_slice=PartialSliceProgress(
                task_id="portable-task",
                slice_id="host-2",
                paths=(PLAN_PATH, "app/host-2.txt"),
            ),
        )
    )
    assert selection.selection is not None
    execution = SequencedExecution([_completed_execution()])
    progress = PortableProgress(
        external_host,
        [SliceSelectionResult(status=SliceSelectionStatus.COMPLETE, completed_slice_ids=("host-1", "host-2"))],
    )

    result = ImplementPlan(
        progress=progress,
        slice_execution=execution,
        slice_reconciliation=PassingReconciliation(),
        slice_commit=RecordingCommit([COMMITS[0]]),
    ).execute(PlanImplementationRequest(approval=_approval(), initial_selection=selection.selection))

    assert result.status is PlanImplementationStatus.COMPLETED
    assert [request.selection.slice_id for request in execution.requests] == ["host-2"]
    assert execution.requests[0].selection.resuming_partial is True
    assert execution.requests[0].expected_paths == (PLAN_PATH, "app/host-2.txt")


def _implementation(
    host: ExternalHost,
    execution: SequencedExecution,
    reconciliation: ReconciliationPort,
    commit: RecordingCommit,
) -> PlanImplementationResult:
    return ImplementPlan(
        progress=PortableProgress(host, [_selected("host-2")]),
        slice_execution=execution,
        slice_reconciliation=reconciliation,
        slice_commit=commit,
    ).execute(
        PlanImplementationRequest(
            approval=_approval(),
            initial_selection=_required_selection(_selected("host-1")),
        )
    )


def _approval(*, starting_head: str = START) -> InvocationApproval:
    return InvocationApproval(
        run_id="portable-host-run",
        profile="balanced",
        starting_head=starting_head,
        approved_at=datetime(2026, 7, 26, 20, tzinfo=UTC),
        specification_digest=SPECIFICATION_DIGEST,
        material_digest=MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )


def _selected(slice_id: str) -> SliceSelectionResult:
    return SliceSelectionResult(
        status=SliceSelectionStatus.SELECTED,
        selection=SelectedSlice(task_id="portable-task", slice_id=slice_id, resuming_partial=False),
    )


def _required_selection(result: SliceSelectionResult) -> SelectedSlice:
    assert result.selection is not None
    return result.selection


def _completed_execution() -> SliceExecutionResult:
    return SliceExecutionResult(status=SliceExecutionStatus.COMPLETED)


def _host_validation() -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand(HOST_CHECK, ("--focused",)),
        source=ValidationCommandSource.DISCOVERED,
        reason="external host verification",
    )


def _commit_paths(host: ExternalHost, commit: str) -> set[str]:
    return set(host.git("show", "--format=", "--name-only", commit).stdout.splitlines())


def _commit_message(host: ExternalHost, commit: str) -> str:
    return host.git("show", "-s", "--format=%B", commit).stdout
