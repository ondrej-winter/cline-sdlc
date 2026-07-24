"""Tests for ordered no-write lifecycle stage preflight."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationBlocker,
    ArtifactLocationResult,
    ArtifactLocationSource,
    SelectArtifactLocationRequest,
)
from cline_sdlc.features.cline_execution.application.dtos.preflight import (
    ClinePreflightBlocker,
    ClinePreflightRequest,
    ClinePreflightResult,
    ClinePreflightStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest, InvocationSource
from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import (
    StagePreflightRequest,
    StagePreflightStatus,
    StagePreflightStep,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.preflight_stage import PreflightLifecycleStage
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage
from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionBlocker,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
    RepositoryInspectionStatus,
    RepositorySnapshot,
)
from cline_sdlc.features.run_audit.application.dtos.run_audit import (
    RunAuditBlocker,
    RunAuditRequest,
    RunAuditResult,
    RunAuditStatus,
)


@dataclass
class RecordingArtifactSelector:
    result: ArtifactLocationResult | ArtifactLocationBlocker
    calls: list[SelectArtifactLocationRequest]

    def execute(self, request: SelectArtifactLocationRequest) -> ArtifactLocationResult | ArtifactLocationBlocker:
        self.calls.append(request)
        return self.result


@dataclass
class RecordingRepositoryInspector:
    result: RepositoryInspectionResult
    calls: list[RepositoryInspectionRequest]

    def execute(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        self.calls.append(request)
        return self.result


@dataclass
class RecordingAuditRecorder:
    result: RunAuditResult
    calls: list[RunAuditRequest]

    def execute(self, request: RunAuditRequest) -> RunAuditResult:
        self.calls.append(request)
        return self.result


@dataclass
class RecordingClinePreflight:
    result: ClinePreflightResult
    calls: list[ClinePreflightRequest]

    def execute(self, request: ClinePreflightRequest) -> ClinePreflightResult:
        self.calls.append(request)
        return self.result


def test_blocks_unselected_invocation_before_downstream_checks() -> None:
    selector = RecordingArtifactSelector(_artifact_location(), [])
    repository = RecordingRepositoryInspector(_repository_ready(), [])
    audit = RecordingAuditRecorder(_audit_recorded(), [])
    cline = RecordingClinePreflight(_cline_ready(), [])

    result = PreflightLifecycleStage(
        artifact_location_selector=selector,
        repository_inspector=repository,
        run_audit_recorder=audit,
        cline_preflight=cline,
    ).execute(_request(invocation=_invocation(stage=None)))

    assert result.status is StagePreflightStatus.BLOCKED
    assert result.blockers[0].step is StagePreflightStep.INVOCATION
    assert selector.calls == []
    assert repository.calls == []
    assert audit.calls == []
    assert cline.calls == []


def test_artifact_location_blocker_stops_before_repository_and_cline_preflight() -> None:
    selector = RecordingArtifactSelector(ArtifactLocationBlocker(code="unsafe_artifact_path", summary="unsafe"), [])
    repository = RecordingRepositoryInspector(_repository_ready(), [])
    cline = RecordingClinePreflight(_cline_ready(), [])

    result = PreflightLifecycleStage(
        artifact_location_selector=selector,
        repository_inspector=repository,
        cline_preflight=cline,
    ).execute(_request(include_run_audit=False))

    assert result.status is StagePreflightStatus.BLOCKED
    assert result.blockers[0].step is StagePreflightStep.ARTIFACT_LOCATION
    assert repository.calls == []
    assert cline.calls == []


def test_repository_blocker_stops_before_audit_setup_and_cline_preflight() -> None:
    selector = RecordingArtifactSelector(_artifact_location(), [])
    repository = RecordingRepositoryInspector(
        RepositoryInspectionResult(
            status=RepositoryInspectionStatus.FAILED,
            blockers=(RepositoryInspectionBlocker(code="dirty_tree", summary="tree is dirty", evidence="M plan.md"),),
        ),
        [],
    )
    audit = RecordingAuditRecorder(_audit_recorded(), [])
    cline = RecordingClinePreflight(_cline_ready(), [])

    result = PreflightLifecycleStage(
        artifact_location_selector=selector,
        repository_inspector=repository,
        run_audit_recorder=audit,
        cline_preflight=cline,
    ).execute(_request())

    assert result.status is StagePreflightStatus.BLOCKED
    assert result.blockers[0].step is StagePreflightStep.REPOSITORY
    assert result.blockers[0].code == "dirty_tree"
    assert audit.calls == []
    assert cline.calls == []


def test_audit_setup_failure_stops_before_cline_preflight() -> None:
    audit = RecordingAuditRecorder(
        RunAuditResult(
            status=RunAuditStatus.FAILED,
            blockers=(RunAuditBlocker(code="audit_path_symlink_escape", summary="unsafe audit path"),),
        ),
        [],
    )
    cline = RecordingClinePreflight(_cline_ready(), [])

    result = PreflightLifecycleStage(
        artifact_location_selector=RecordingArtifactSelector(_artifact_location(), []),
        repository_inspector=RecordingRepositoryInspector(_repository_ready(), []),
        run_audit_recorder=audit,
        cline_preflight=cline,
    ).execute(_request())

    assert result.status is StagePreflightStatus.BLOCKED
    assert result.blockers[0].step is StagePreflightStep.RUN_AUDIT
    assert cline.calls == []


def test_cline_preflight_failure_returns_actionable_blocker_after_prior_checks() -> None:
    cline = RecordingClinePreflight(
        ClinePreflightResult(
            status=ClinePreflightStatus.FAILED,
            executable="cline",
            version="3.0.46",
            blockers=(ClinePreflightBlocker(code="missing_skill", summary="skill missing", evidence="idea-refine"),),
        ),
        [],
    )

    result = PreflightLifecycleStage(
        artifact_location_selector=RecordingArtifactSelector(_artifact_location(), []),
        repository_inspector=RecordingRepositoryInspector(_repository_ready(), []),
        run_audit_recorder=RecordingAuditRecorder(_audit_recorded(), []),
        cline_preflight=cline,
    ).execute(_request())

    assert result.status is StagePreflightStatus.BLOCKED
    assert [item.step for item in result.evidence] == [
        StagePreflightStep.INVOCATION,
        StagePreflightStep.ARTIFACT_LOCATION,
        StagePreflightStep.REPOSITORY,
        StagePreflightStep.RUN_AUDIT,
    ]
    assert result.blockers[0].step is StagePreflightStep.CLINE_CAPABILITY
    assert result.blockers[0].evidence == "idea-refine"


def test_authorizes_stage_after_ordered_preflight_checks_pass() -> None:
    artifact_location = _artifact_location()
    repository = RecordingRepositoryInspector(_repository_ready(), [])
    audit = RecordingAuditRecorder(_audit_recorded(), [])
    cline = RecordingClinePreflight(_cline_ready(), [])

    result = PreflightLifecycleStage(
        artifact_location_selector=RecordingArtifactSelector(artifact_location, []),
        repository_inspector=repository,
        run_audit_recorder=audit,
        cline_preflight=cline,
    ).execute(_request())

    assert result.authorized
    assert result.status is StagePreflightStatus.AUTHORIZED
    assert result.blockers == ()
    assert [item.step for item in result.evidence] == [
        StagePreflightStep.INVOCATION,
        StagePreflightStep.ARTIFACT_LOCATION,
        StagePreflightStep.REPOSITORY,
        StagePreflightStep.RUN_AUDIT,
        StagePreflightStep.CLINE_CAPABILITY,
    ]
    assert result.artifact_location == artifact_location
    assert result.repository_snapshot == _snapshot()
    assert result.audit_summary_path == ".cline-sdlc/runs/run-1/summary.json"
    assert len(repository.calls) == 1
    assert len(audit.calls) == 1
    assert len(cline.calls) == 1


def _request(
    *,
    invocation: InvocationRequest | None = None,
    run_audit_request: RunAuditRequest | None = None,
    include_run_audit: bool = True,
) -> StagePreflightRequest:
    audit_request = run_audit_request or RunAuditRequest(
        repository_root=Path("/repo"),
        run_id="run-1",
        terminal_status="preflight",
    )
    return StagePreflightRequest(
        invocation=invocation or _invocation(),
        artifact_location_request=SelectArtifactLocationRequest(
            artifact_kind=ArtifactKind.PLAN,
            artifact_stem="cline-sdlc-orchestrator",
        ),
        repository_request=RepositoryInspectionRequest(
            working_directory=Path("/repo"),
            managed_paths=(Path("docs/plans"),),
        ),
        run_audit_request=audit_request if include_run_audit else None,
        cline_preflight_request=ClinePreflightRequest(command=("cline",), required_skills=("spec-driven-development",)),
    )


def _invocation(*, stage: LifecycleStage | None = LifecycleStage.PLAN_CREATION_AND_REVIEW) -> InvocationRequest:
    return InvocationRequest(
        source=InvocationSource.from_spec_file(Path("docs/specs/example-spec.md")),
        timeout_seconds=30,
        cline_command="cline",
        stage=stage,
    )


def _artifact_location() -> ArtifactLocationResult:
    return ArtifactLocationResult(
        artifact_kind=ArtifactKind.PLAN,
        path="docs/plans/example-plan.md",
        directory="docs/plans",
        source=ArtifactLocationSource.PORTABLE_DEFAULT,
    )


def _repository_ready() -> RepositoryInspectionResult:
    return RepositoryInspectionResult(status=RepositoryInspectionStatus.READY, snapshot=_snapshot())


def _snapshot() -> RepositorySnapshot:
    return RepositorySnapshot(repository_root="/repo", head_commit="abc123", branch="feature/preflight")


def _audit_recorded() -> RunAuditResult:
    return RunAuditResult(status=RunAuditStatus.RECORDED, summary_path=".cline-sdlc/runs/run-1/summary.json")


def _cline_ready() -> ClinePreflightResult:
    return ClinePreflightResult(status=ClinePreflightStatus.READY, executable="cline", version="3.0.46")
