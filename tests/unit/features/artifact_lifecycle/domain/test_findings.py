"""Tests for plan-review finding schema values."""

import pytest

from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSet,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)


def test_resolved_blocking_finding_allows_ready_review() -> None:
    findings = FindingSet(
        findings=(
            Finding(
                id="PLAN-001",
                severity=FindingSeverity.BLOCKING,
                status=FindingStatus.RESOLVED,
                summary="Plan lacks validation.",
                evidence="No validation command is listed.",
                required_correction="Add focused validation command.",
                affected_sections=("Task 2.7",),
                disposition="Validation task added.",
            ),
        ),
    )

    assert findings.readiness() is PlanReviewReadiness.READY


def test_open_major_finding_requires_changes_until_review_limit_exhausted() -> None:
    findings = FindingSet(
        findings=(
            Finding(
                id="PLAN-002",
                severity=FindingSeverity.MAJOR,
                status=FindingStatus.OPEN,
                summary="Boundary is unclear.",
                evidence="The adapter owns workflow decisions.",
                required_correction="Move decisions to application use case.",
            ),
        ),
    )

    assert findings.readiness() is PlanReviewReadiness.CHANGES_REQUIRED
    assert findings.readiness(review_limit_exhausted=True) is PlanReviewReadiness.BLOCKED


def test_major_accepted_risk_does_not_count_as_unattended_ready() -> None:
    findings = FindingSet(
        findings=(
            Finding(
                id="PLAN-003",
                severity=FindingSeverity.MAJOR,
                status=FindingStatus.ACCEPTED_RISK,
                summary="Risk remains.",
                evidence="No automated proof exists.",
                required_correction="Add proof or human disposition.",
                disposition="Accepted by reviewer without human approval.",
            ),
        ),
    )

    assert findings.readiness() is PlanReviewReadiness.CHANGES_REQUIRED


def test_finding_rejects_missing_required_text() -> None:
    with pytest.raises(ValueError, match="summary"):
        Finding(
            id="PLAN-004",
            severity=FindingSeverity.MINOR,
            status=FindingStatus.OPEN,
            summary=" ",
            evidence="Evidence.",
            required_correction="Correction.",
        )


def test_finding_rejects_open_disposition() -> None:
    with pytest.raises(ValueError, match="open findings"):
        Finding(
            id="PLAN-005",
            severity=FindingSeverity.MINOR,
            status=FindingStatus.OPEN,
            summary="Minor wording issue.",
            evidence="Phrase is ambiguous.",
            required_correction="Clarify phrase.",
            disposition="Already handled.",
        )


def test_finding_set_rejects_duplicate_ids() -> None:
    finding = Finding(
        id="PLAN-006",
        severity=FindingSeverity.MINOR,
        status=FindingStatus.OPEN,
        summary="Minor issue.",
        evidence="Evidence.",
        required_correction="Correction.",
    )

    with pytest.raises(ValueError, match="unique"):
        FindingSet(findings=(finding, finding))
