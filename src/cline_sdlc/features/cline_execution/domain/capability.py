"""Legacy Cline CLI discovery evidence retained outside SDK readiness."""

from dataclasses import dataclass
from enum import StrEnum


class CapabilityStatus(StrEnum):
    """Evidence strength for one legacy Cline CLI discovery observation."""

    PROVEN = "proven"
    ADVERTISED = "advertised"
    MISSING = "missing"
    UNPROVEN = "unproven"


class CapabilityCriticality(StrEnum):
    """Whether a legacy CLI discovery observation blocks supervised compatibility."""

    CRITICAL = "critical"
    SUPPORTING = "supporting"


@dataclass(frozen=True)
class CapabilityObservation:
    """Observed evidence for a legacy Cline CLI behavior."""

    name: str
    status: CapabilityStatus
    criticality: CapabilityCriticality
    evidence: str

    @property
    def is_satisfied(self) -> bool:
        """Return whether this observation satisfies implementation readiness."""
        return self.status is CapabilityStatus.PROVEN


@dataclass(frozen=True)
class ClineCapabilityReport:
    """Aggregated legacy CLI discovery result.

    CLI probe reports are compatibility and discovery evidence only. They are not
    production-equivalent SDK readiness evidence; ADR 0002 rejects CLI probing as
    the SDK-first execution contract.
    """

    executable: str
    version: str | None
    observations: tuple[CapabilityObservation, ...]
    limitations: tuple[str, ...]

    @property
    def sdk_readiness_evidence(self) -> bool:
        """Return whether this report can prove SDK-first execution readiness."""
        return False

    @property
    def critical_capabilities_proven(self) -> bool:
        """Return whether every critical capability has proof-level evidence."""
        return all(
            observation.is_satisfied
            for observation in self.observations
            if observation.criticality is CapabilityCriticality.CRITICAL
        )

    @property
    def blocking_observations(self) -> tuple[CapabilityObservation, ...]:
        """Return critical observations that still block Checkpoint A."""
        return tuple(
            observation
            for observation in self.observations
            if observation.criticality is CapabilityCriticality.CRITICAL and not observation.is_satisfied
        )

    @property
    def first_unproven_observation(self) -> CapabilityObservation | None:
        """Return the first explicitly unproven observation, if any."""
        return next(
            (observation for observation in self.observations if observation.status is CapabilityStatus.UNPROVEN),
            None,
        )
