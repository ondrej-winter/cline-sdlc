"""Coordinate ordered no-write preflight before lifecycle stage sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import ArtifactLocationBlocker
from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import (
    StagePreflightBlocker,
    StagePreflightEvidence,
    StagePreflightRequest,
    StagePreflightResult,
    StagePreflightStatus,
    StagePreflightStep,
)
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionStatus
from cline_sdlc.features.run_audit.application.dtos.run_audit import RunAuditStatus

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
        ArtifactLocationResult,
        SelectArtifactLocationRequest,
    )
    from cline_sdlc.features.repository_coordination.application.dtos.repository import (
        RepositoryInspectionRequest,
        RepositoryInspectionResult,
    )
    from cline_sdlc.features.run_audit.application.dtos.run_audit import RunAuditRequest, RunAuditResult

type ArtifactSelection = tuple[ArtifactLocationResult | None, tuple[StagePreflightBlocker, ...]]
type AuditSetup = tuple[str | None, tuple[StagePreflightBlocker, ...]]
type PreflightChecks = tuple[
    ArtifactLocationResult | None,
    RepositoryInspectionResult | None,
    str | None,
    tuple[StagePreflightBlocker, ...],
]


class ArtifactLocationSelectorPort(Protocol):
    """Published artifact-lifecycle boundary for selecting managed artifact paths."""

    def execute(self, request: SelectArtifactLocationRequest) -> ArtifactLocationResult | ArtifactLocationBlocker:
        """Return a safe artifact location or an actionable blocker."""


class RepositoryInspectionPort(Protocol):
    """Published repository-coordination boundary for no-write repository inspection."""

    def execute(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        """Return repository readiness evidence or blockers."""


class RunAuditRecorderPort(Protocol):
    """Published run-audit boundary for establishing an ignored run summary destination."""

    def execute(self, request: RunAuditRequest) -> RunAuditResult:
        """Return ignored audit summary persistence evidence or blockers."""


class PreflightLifecycleStage:
    """Authorize one stage after repository and artifact preflight checks pass."""

    def __init__(
        self,
        *,
        repository_inspector: RepositoryInspectionPort,
        artifact_location_selector: ArtifactLocationSelectorPort | None = None,
        run_audit_recorder: RunAuditRecorderPort | None = None,
    ) -> None:
        self._artifact_location_selector = artifact_location_selector
        self._repository_inspector = repository_inspector
        self._run_audit_recorder = run_audit_recorder

    def execute(self, request: StagePreflightRequest) -> StagePreflightResult:
        """Return stage authorization or the first ordered preflight blocker."""
        evidence = [_evidence(StagePreflightStep.INVOCATION, "lifecycle invocation selected a bounded stage")]
        artifact_location, repository_result, audit_summary_path, blockers = self._run_ordered_checks(request, evidence)

        if blockers:
            return _blocked(evidence, *blockers)

        if repository_result is None or repository_result.snapshot is None:
            message = "repository snapshot must exist after successful repository preflight"
            raise RuntimeError(message)

        return StagePreflightResult(
            status=StagePreflightStatus.AUTHORIZED,
            evidence=tuple(evidence),
            artifact_location=artifact_location,
            repository_snapshot=repository_result.snapshot,
            audit_summary_path=audit_summary_path,
        )

    def _run_ordered_checks(
        self,
        request: StagePreflightRequest,
        evidence: list[StagePreflightEvidence],
    ) -> PreflightChecks:
        blockers = _invocation_blockers(request)
        artifact_location = None
        repository_result = None
        audit_summary_path = None

        if not blockers:
            artifact_location, blockers = self._select_artifact_location(request)
        if artifact_location is not None:
            evidence.append(_evidence(StagePreflightStep.ARTIFACT_LOCATION, f"selected {artifact_location.path}"))

        if not blockers:
            repository_result = self._repository_inspector.execute(request.repository_request)
            blockers = _repository_blockers(repository_result)
        if repository_result is not None and not blockers:
            evidence.append(_evidence(StagePreflightStep.REPOSITORY, "repository preflight passed"))

        if not blockers:
            audit_summary_path, blockers = self._set_up_run_audit(request)
        if request.run_audit_request is not None and not blockers:
            evidence.append(_evidence(StagePreflightStep.RUN_AUDIT, "ignored run audit destination is ready"))

        return artifact_location, repository_result, audit_summary_path, blockers

    def _select_artifact_location(self, request: StagePreflightRequest) -> ArtifactSelection:
        if request.artifact_location_request is None:
            return None, ()
        if self._artifact_location_selector is None:
            return None, (
                StagePreflightBlocker(
                    step=StagePreflightStep.ARTIFACT_LOCATION,
                    code="artifact_location_selector_unavailable",
                    summary="artifact location selection is required but no selector was configured",
                ),
            )
        artifact_result = self._artifact_location_selector.execute(request.artifact_location_request)
        if isinstance(artifact_result, ArtifactLocationBlocker):
            return None, (
                StagePreflightBlocker(
                    step=StagePreflightStep.ARTIFACT_LOCATION,
                    code=artifact_result.code,
                    summary=artifact_result.summary,
                ),
            )
        return artifact_result, ()

    def _set_up_run_audit(self, request: StagePreflightRequest) -> AuditSetup:
        if request.run_audit_request is None:
            return None, ()
        if self._run_audit_recorder is None:
            return None, (
                StagePreflightBlocker(
                    step=StagePreflightStep.RUN_AUDIT,
                    code="run_audit_recorder_unavailable",
                    summary="run audit setup is required but no recorder was configured",
                ),
            )
        audit_result = self._run_audit_recorder.execute(request.run_audit_request)
        if audit_result.status is not RunAuditStatus.RECORDED:
            return None, _audit_blockers(audit_result)
        return audit_result.summary_path, ()


def _invocation_blockers(request: StagePreflightRequest) -> tuple[StagePreflightBlocker, ...]:
    if request.invocation.stage is not None:
        return ()
    return (
        StagePreflightBlocker(
            step=StagePreflightStep.INVOCATION,
            code="stage_not_selected",
            summary="lifecycle invocation must select exactly one stage before preflight",
        ),
    )


def _repository_blockers(result: RepositoryInspectionResult) -> tuple[StagePreflightBlocker, ...]:
    if result.status is RepositoryInspectionStatus.READY and result.snapshot is not None:
        return ()
    if result.blockers:
        return tuple(
            StagePreflightBlocker(
                step=StagePreflightStep.REPOSITORY,
                code=blocker.code,
                summary=blocker.summary,
                evidence=blocker.evidence,
            )
            for blocker in result.blockers
        )
    return (
        StagePreflightBlocker(
            step=StagePreflightStep.REPOSITORY,
            code="repository_snapshot_unavailable",
            summary="repository inspection did not return an observable snapshot",
        ),
    )


def _audit_blockers(result: RunAuditResult) -> tuple[StagePreflightBlocker, ...]:
    if result.blockers:
        return tuple(
            StagePreflightBlocker(
                step=StagePreflightStep.RUN_AUDIT,
                code=blocker.code,
                summary=blocker.summary,
                evidence=blocker.evidence,
            )
            for blocker in result.blockers
        )
    return (
        StagePreflightBlocker(
            step=StagePreflightStep.RUN_AUDIT,
            code="run_audit_not_recorded",
            summary="run audit setup did not produce a recorded summary destination",
        ),
    )


def _evidence(step: StagePreflightStep, summary: str) -> StagePreflightEvidence:
    return StagePreflightEvidence(step=step, summary=summary)


def _blocked(evidence: list[StagePreflightEvidence], *blockers: StagePreflightBlocker) -> StagePreflightResult:
    return StagePreflightResult(
        status=StagePreflightStatus.BLOCKED,
        evidence=tuple(evidence),
        blockers=blockers,
    )
