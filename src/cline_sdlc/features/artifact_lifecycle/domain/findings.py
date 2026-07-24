"""Plan-review finding schema values."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FindingSeverity(StrEnum):
    """Allowed review finding severities."""

    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"


class FindingStatus(StrEnum):
    """Allowed review finding lifecycle statuses."""

    OPEN = "open"
    RESOLVED = "resolved"
    ACCEPTED_RISK = "accepted_risk"
    NOT_APPLICABLE = "not_applicable"


class PlanReviewReadiness(StrEnum):
    """Readiness classification derived from validated findings."""

    READY = "ready"
    CHANGES_REQUIRED = "changes_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Finding:
    """Validated plan-review finding record."""

    id: str
    severity: FindingSeverity
    status: FindingStatus
    summary: str
    evidence: str
    required_correction: str
    affected_sections: tuple[str, ...] = field(default_factory=tuple)
    disposition: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("summary", self.summary),
            ("evidence", self.evidence),
            ("required_correction", self.required_correction),
        ):
            if not value.strip():
                message = f"finding {field_name} must not be empty"
                raise ValueError(message)
        affected_sections = _non_empty_unique_values(self.affected_sections, field_name="affected_sections")
        object.__setattr__(self, "affected_sections", affected_sections)
        if self.status is FindingStatus.OPEN and self.disposition is not None:
            message = "open findings must not include a disposition"
            raise ValueError(message)
        if self.status is not FindingStatus.OPEN and (self.disposition is None or not self.disposition.strip()):
            message = "non-open findings must include a disposition"
            raise ValueError(message)

    @property
    def blocks_unattended_readiness(self) -> bool:
        """Return whether this finding prevents an unattended-ready plan review result."""
        if self.status is FindingStatus.OPEN:
            return self.severity in {FindingSeverity.BLOCKING, FindingSeverity.MAJOR}
        if self.status in {FindingStatus.ACCEPTED_RISK, FindingStatus.NOT_APPLICABLE}:
            return self.severity in {FindingSeverity.BLOCKING, FindingSeverity.MAJOR}
        return False


@dataclass(frozen=True)
class FindingSet:
    """Collection of findings with stable unique identifiers."""

    findings: tuple[Finding, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        ids = tuple(finding.id for finding in self.findings)
        if len(set(ids)) != len(ids):
            message = "finding IDs must be unique"
            raise ValueError(message)

    def readiness(self, *, review_limit_exhausted: bool = False) -> PlanReviewReadiness:
        """Return the review readiness implied by the current findings."""
        if any(finding.blocks_unattended_readiness for finding in self.findings):
            return PlanReviewReadiness.BLOCKED if review_limit_exhausted else PlanReviewReadiness.CHANGES_REQUIRED
        return PlanReviewReadiness.READY


def _non_empty_unique_values(raw_values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    values = tuple(value.strip() for value in raw_values)
    if any(not value for value in values):
        message = f"{field_name} must not contain empty values"
        raise ValueError(message)
    if len(set(values)) != len(values):
        message = f"{field_name} must be unique"
        raise ValueError(message)
    return values
