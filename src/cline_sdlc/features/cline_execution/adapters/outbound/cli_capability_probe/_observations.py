"""Private capability observation builders for the Cline CLI probe adapter."""

from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    CapabilityObservation,
    CapabilityStatus,
)


def advertised(name: str, token: str, help_text: str) -> CapabilityObservation:
    """Return a supporting observation based on whether help output advertises a token."""
    status = CapabilityStatus.ADVERTISED if token in help_text else CapabilityStatus.MISSING
    evidence = (
        f"Cline help output {'contains' if status is CapabilityStatus.ADVERTISED else 'does not contain'} {token!r}."
    )
    return CapabilityObservation(
        name=name,
        status=status,
        criticality=CapabilityCriticality.SUPPORTING,
        evidence=evidence,
    )


def critical(name: str, status: CapabilityStatus, evidence: str) -> CapabilityObservation:
    """Return a critical observation with the supplied status and evidence."""
    return CapabilityObservation(
        name=name,
        status=status,
        criticality=CapabilityCriticality.CRITICAL,
        evidence=evidence,
    )


def supporting(name: str, status: CapabilityStatus, evidence: str) -> CapabilityObservation:
    """Return a supporting observation with the supplied status and evidence."""
    return CapabilityObservation(
        name=name,
        status=status,
        criticality=CapabilityCriticality.SUPPORTING,
        evidence=evidence,
    )
