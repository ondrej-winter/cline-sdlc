"""DTOs for supervised Cline CLI capability probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class CapabilityProbeRequest:
    """Request to inspect one explicit Cline executable command."""

    command: tuple[str, ...] = ("cline",)
    required_skills: tuple[str, ...] = ()
    supervised_session_probe: bool = False
    repository_root: Path | None = None
    data_directory: Path | None = None
    hooks_directory: Path | None = None
    session_timeout_seconds: float = 10.0
    probe_prompt: str = "Emit one machine-readable capability outcome."
