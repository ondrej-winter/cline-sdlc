"""Capability evidence collected from a supervised Cline CLI spike."""

from dataclasses import dataclass
from enum import StrEnum


class CapabilityStatus(StrEnum):
    """Evidence strength for one Cline CLI capability."""

    PROVEN = "proven"
    ADVERTISED = "advertised"
    MISSING = "missing"
    UNPROVEN = "unproven"


class CapabilityCriticality(StrEnum):
    """Whether a capability blocks the CLI-wrapper architecture."""

    CRITICAL = "critical"
    SUPPORTING = "supporting"


@dataclass(frozen=True)
class CapabilityObservation:
    """Observed evidence for a required Cline CLI behavior."""

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
    """Aggregated capability-spike result for the CLI-wrapper viability gate."""

    executable: str
    version: str | None
    observations: tuple[CapabilityObservation, ...]
    limitations: tuple[str, ...]

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
