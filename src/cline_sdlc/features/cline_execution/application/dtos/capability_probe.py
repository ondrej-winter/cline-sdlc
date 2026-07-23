"""DTOs for supervised Cline CLI capability probes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityProbeRequest:
    """Request to inspect one explicit Cline executable command."""

    command: tuple[str, ...] = ("cline",)
    required_skills: tuple[str, ...] = ()
