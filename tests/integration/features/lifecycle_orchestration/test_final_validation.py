"""Integration tests for final broad-validation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import (
    FinalValidationRequest,
    FinalValidationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationDiscoveryResult,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationExecutionResult,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_final_validation import RunFinalValidation
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval

if TYPE_CHECKING:
    from pathlib import Path

    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
        ValidationDiscoveryRequest,
        ValidationExecutionRequest,
    )

_START = "a" * 40
_END = "b" * 40
_SPECIFICATION_DIGEST = f"sha256:{'1' * 64}"
_MATERIAL_DIGEST = f"sha256:{'2' * 64}"


@dataclass
class StubDiscovery:
    result: ValidationDiscoveryResult
    requests: list[ValidationDiscoveryRequest]

    def execute(self, request: ValidationDiscoveryRequest) -> ValidationDiscoveryResult:
        self.requests.append(request)
        return self.result


@dataclass
class StubExecution:
    result: ValidationExecutionResult
    requests: list[ValidationExecutionRequest]

    def execute(self, request: ValidationExecutionRequest) -> ValidationExecutionResult:
        self.requests.append(request)
        return self.result


def test_runs_every_discovered_broad_check_and_ties_evidence_to_approval(tmp_path: Path) -> None:
    candidate = _candidate(ValidationScope.BROAD)
    evidence = _evidence(candidate, ValidationEvidenceStatus.PASSED, exit_code=0)
    discovery = StubDiscovery(ValidationDiscoveryResult(commands=(candidate,)), [])
    execution = StubExecution(ValidationExecutionResult(evidence=(evidence,)), [])

    result = RunFinalValidation(discovery=discovery, execution=execution).execute(_request(tmp_path))

    assert result.status is FinalValidationStatus.COMPLETED
    assert result.run_id == "run-5.1"
    assert result.commit_range == (_START, _END)
    assert result.evidence == (evidence,)
    assert execution.requests[0].commands == (candidate,)


@pytest.mark.parametrize("scope", [None, ValidationScope.FOCUSED])
def test_blocks_when_authoritative_broad_checks_are_missing(tmp_path: Path, scope: ValidationScope | None) -> None:
    commands = () if scope is None else (_candidate(scope),)
    execution = StubExecution(ValidationExecutionResult(), [])

    result = RunFinalValidation(
        discovery=StubDiscovery(ValidationDiscoveryResult(commands=commands), []),
        execution=execution,
    ).execute(_request(tmp_path))

    assert result.status is FinalValidationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "broad_validation_unavailable"
    assert execution.requests == []


def test_failed_broad_check_never_reports_completion(tmp_path: Path) -> None:
    candidate = _candidate(ValidationScope.BROAD)
    evidence = _evidence(candidate, ValidationEvidenceStatus.FAILED, exit_code=1)
    result = RunFinalValidation(
        discovery=StubDiscovery(ValidationDiscoveryResult(commands=(candidate,)), []),
        execution=StubExecution(ValidationExecutionResult(evidence=(evidence,)), []),
    ).execute(_request(tmp_path))

    assert result.status is FinalValidationStatus.FAILED
    assert result.evidence == (evidence,)
    assert result.blocker is not None
    assert result.blocker.code == "broad_validation_failed"


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        (ValidationEvidenceStatus.BLOCKED, None),
        (ValidationEvidenceStatus.NOT_RUN, None),
    ],
)
def test_blocked_or_unrun_broad_check_never_reports_completion(
    tmp_path: Path,
    status: ValidationEvidenceStatus,
    exit_code: int | None,
) -> None:
    candidate = _candidate(ValidationScope.BROAD)
    evidence = _evidence(candidate, status, exit_code=exit_code)
    result = RunFinalValidation(
        discovery=StubDiscovery(ValidationDiscoveryResult(commands=(candidate,)), []),
        execution=StubExecution(ValidationExecutionResult(evidence=(evidence,)), []),
    ).execute(_request(tmp_path))

    assert result.status is FinalValidationStatus.BLOCKED
    assert result.evidence == (evidence,)
    assert result.blocker is not None
    assert result.blocker.code == "broad_validation_blocked"


def test_digest_divergence_blocks_before_discovery(tmp_path: Path) -> None:
    discovery = StubDiscovery(ValidationDiscoveryResult(), [])
    request = _request(tmp_path, material_digest=f"sha256:{'3' * 64}")

    result = RunFinalValidation(
        discovery=discovery,
        execution=StubExecution(ValidationExecutionResult(), []),
    ).execute(request)

    assert result.status is FinalValidationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "material_digest_diverged"
    assert discovery.requests == []


def test_request_requires_approval_starting_head_as_commit_range_start(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="approval starting HEAD"):
        _request(tmp_path, start_commit="c" * 40)


def _request(
    tmp_path: Path,
    *,
    start_commit: str = _START,
    material_digest: str = _MATERIAL_DIGEST,
) -> FinalValidationRequest:
    return FinalValidationRequest(
        approval=_approval(),
        specification_digest=_SPECIFICATION_DIGEST,
        material_digest=material_digest,
        start_commit=start_commit,
        end_commit=_END,
        working_directory=tmp_path,
        timeout_seconds=10.0,
    )


def _approval() -> InvocationApproval:
    return InvocationApproval(
        run_id="run-5.1",
        profile="balanced",
        starting_head=_START,
        approved_at=datetime(2026, 7, 26, tzinfo=UTC),
        specification_digest=_SPECIFICATION_DIGEST,
        material_digest=_MATERIAL_DIGEST,
        remediation_envelope_applicable=True,
    )


def _candidate(scope: ValidationScope) -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=scope,
        command=ValidationCommand("uv", ("run", "pytest")),
        source=ValidationCommandSource.DEFAULT,
        reason="authoritative repository-wide check",
    )


def _evidence(
    candidate: ValidationCommandCandidate,
    status: ValidationEvidenceStatus,
    *,
    exit_code: int | None,
) -> ValidationEvidence:
    return ValidationEvidence(
        scope=candidate.scope,
        command=candidate.command,
        status=status,
        summary="broad validation result",
        exit_code=exit_code,
        recorded_at=datetime(2026, 7, 26, tzinfo=UTC),
    )
