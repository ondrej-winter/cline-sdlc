"""DTOs for legacy Cline CLI discovery probes.

These DTOs support compatibility checks for existing supervised CLI surfaces.
They must not be treated as SDK-first execution readiness evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class CapabilityProbeRequest:
    """Request to inspect one explicit legacy Cline CLI command."""

    command: tuple[str, ...] = ("cline",)
    required_skills: tuple[str, ...] = ()
    supervised_session_probe: bool = False
    repository_root: Path | None = None
    data_directory: Path | None = None
    hooks_directory: Path | None = None
    session_timeout_seconds: float = 10.0
    probe_prompt: str = "Write one machine-readable capability status sidecar."
