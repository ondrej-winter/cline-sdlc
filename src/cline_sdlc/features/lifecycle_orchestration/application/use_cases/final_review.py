"""Run one fresh read-only final review and classify bounded remediation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.domain.findings import FindingSeverity
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole, SessionStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
    FinalReviewBlocker,
    FinalReviewRequest,
    FinalReviewResult,
    FinalReviewStatus,
    RemediationRecord,
    finding_is_open,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.findings import Finding
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import ApprovedRemediationScope
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import SessionAttemptResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import ValidationCommand


class SessionAttemptsPort(Protocol):
    """Boundary for one bounded fresh Cline review session."""

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        """Return typed process, repository, and outcome evidence."""


class RunFinalReview:
    """Require read-only final evidence and classify only pre-bounded corrections."""

    def __init__(self, *, session_attempts: SessionAttemptsPort) -> None:
        self._session_attempts = session_attempts

    def execute(self, request: FinalReviewRequest) -> FinalReviewResult:
        """Return clean, bounded remediation, or the first fail-closed blocker."""
        approval_failure = _approval_failure(request)
        if approval_failure is not None:
            return _blocked(approval_failure)

        session_result = self._session_attempts.execute(_session_request(request))
        session_failure = _session_failure(session_result)
        if session_failure is not None:
            return session_failure
        return _review_result(request, session_result)


def _review_result(request: FinalReviewRequest, session_result: SessionAttemptResult) -> FinalReviewResult:
    terminal_result = session_result.terminal_session_result
    if terminal_result is None or len(terminal_result.terminal_outcomes) != 1:
        return _blocked(FinalReviewBlocker("final_review_outcome_unavailable", "final review requires one outcome"))
    terminal = terminal_result.terminal_outcomes[0]
    shape_failure = _outcome_shape_failure(request, session_result)
    if shape_failure is not None:
        return _blocked(shape_failure)
    classified = _classify_findings(terminal.findings, request.remediation_scopes)
    if isinstance(classified, FinalReviewBlocker):
        return FinalReviewResult(
            status=FinalReviewStatus.BLOCKED,
            readiness=terminal.review_readiness,
            findings=terminal.findings,
            blocker=classified,
        )
    status = FinalReviewStatus.REMEDIATION_REQUIRED if classified else FinalReviewStatus.CLEAN
    return FinalReviewResult(
        status=status,
        readiness=terminal.review_readiness,
        findings=terminal.findings,
        remediation_records=classified,
    )


def _outcome_shape_failure(
    request: FinalReviewRequest,
    session_result: SessionAttemptResult,
) -> FinalReviewBlocker | None:
    terminal_result = session_result.terminal_session_result
    if terminal_result is None or len(terminal_result.terminal_outcomes) != 1:
        return FinalReviewBlocker("final_review_outcome_unavailable", "final review requires one outcome")
    terminal = terminal_result.terminal_outcomes[0]
    failures = (
        (
            terminal.session_role is not SessionRole.FINAL_REVIEWER,
            FinalReviewBlocker("unexpected_session_role", "final review requires final_reviewer role"),
        ),
        (
            terminal.status is not SessionStatus.COMPLETED,
            FinalReviewBlocker("final_review_not_completed", "final reviewer did not complete"),
        ),
        (
            _reviewer_changed_repository(session_result),
            FinalReviewBlocker("reviewer_write_observed", "read-only final reviewer changed repository state"),
        ),
        (
            terminal.artifact_paths not in {(), (request.plan_path,)},
            FinalReviewBlocker("unexpected_review_artifact", "final reviewer named an unexpected artifact"),
        ),
        (
            any(not finding.id.startswith("FINAL-") for finding in terminal.findings),
            FinalReviewBlocker("invalid_final_finding_id", "final findings must use stable FINAL- IDs"),
        ),
    )
    return next((blocker for failed, blocker in failures if failed), None)


def _classify_findings(
    findings: tuple[Finding, ...],
    scopes: tuple[ApprovedRemediationScope, ...],
) -> tuple[RemediationRecord, ...] | FinalReviewBlocker:
    records: list[RemediationRecord] = []
    for finding in findings:
        if not finding_is_open(finding):
            continue
        classification = _classify_finding(finding, scopes)
        if isinstance(classification, FinalReviewBlocker):
            return classification
        records.append(classification)
    return tuple(records)


def _approval_failure(request: FinalReviewRequest) -> FinalReviewBlocker | None:
    if request.specification_digest != request.approval.specification_digest:
        return FinalReviewBlocker("specification_digest_diverged", "specification digest diverged from approval")
    if request.material_digest != request.approval.material_digest:
        return FinalReviewBlocker("material_digest_diverged", "plan material digest diverged from approval")
    return None


def _session_request(request: FinalReviewRequest) -> SessionAttemptRequest:
    return SessionAttemptRequest(
        session_request=ClineSessionRequest(
            command=(request.cline_command, "--json", "--task", _prompt(request)),
            working_directory=request.working_directory,
            timeout_seconds=request.timeout_seconds,
        ),
        repository_request=request.repository_request,
        max_attempts=1,
    )


def _prompt(request: FinalReviewRequest) -> str:
    broad_evidence = "\n".join(
        f"- {_evidence_command(item.command)}: {item.status.value} (exit={item.exit_code})"
        for item in request.final_validation.evidence
    )
    return "\n".join(
        (
            "Use the code-review-and-quality skill for one fresh final implementation review.",
            "This is read-only. Do not modify any repository file.",
            "Report every finding with a stable FINAL- identifier and complete finding fields.",
            "New scope, architecture, dependency, contract, migration, or sequencing decisions are blockers.",
            f"Accepted specification ({request.specification_path}):\n{request.specification_content}",
            f"Ready plan ({request.plan_path}):\n{request.plan_content}",
            f"Repository rules:\n{request.repository_rules}",
            f"Reviewed commit range: {request.start_commit}..{request.end_commit}",
            f"Broad validation evidence:\n{broad_evidence}",
        )
    )


def _evidence_command(command: ValidationCommand | None) -> str:
    return command.display if command is not None else "command unavailable"


def _session_failure(session_result: SessionAttemptResult) -> FinalReviewResult | None:
    if session_result.status is SessionAttemptStatus.COMPLETED and session_result.terminal_session_result is not None:
        return None
    blocker = session_result.blocker
    return FinalReviewResult(
        status=(
            FinalReviewStatus.BLOCKED
            if session_result.status is SessionAttemptStatus.BLOCKED
            else FinalReviewStatus.FAILED
        ),
        blocker=FinalReviewBlocker(
            code=blocker.code if blocker is not None else "final_reviewer_session_failed",
            summary=blocker.summary if blocker is not None else "final reviewer session did not complete",
        ),
    )


def _reviewer_changed_repository(session_result: SessionAttemptResult) -> bool:
    if session_result.changed_paths:
        return True
    return any(
        observation.after_snapshot is None or observation.after_snapshot != observation.before_snapshot
        for observation in session_result.attempts
    )


def _classify_finding(
    finding: Finding,
    scopes: tuple[ApprovedRemediationScope, ...],
) -> RemediationRecord | FinalReviewBlocker:
    if finding.severity is FindingSeverity.MINOR:
        return FinalReviewBlocker(
            "minor_finding_requires_manual_disposition",
            "minor final findings are not automatic remediation transactions",
            finding.id,
        )
    matching = tuple(scope for scope in scopes if scope.affected_section in finding.affected_sections)
    if len(matching) != 1:
        return FinalReviewBlocker(
            "remediation_scope_unavailable",
            "final finding does not map uniquely to an approved bounded requirement",
            finding.id,
        )
    scope = matching[0]
    return RemediationRecord(
        finding_id=finding.id,
        requirement=scope.requirement,
        path_scope=scope.path_scope,
        correction=finding.required_correction,
        verification=scope.verification,
    )


def _blocked(blocker: FinalReviewBlocker) -> FinalReviewResult:
    return FinalReviewResult(status=FinalReviewStatus.BLOCKED, blocker=blocker)
