"""DTOs for balanced-profile operation classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassifyOperationRequest:
    """Application request to classify one structured command operation."""

    executable: str
    arguments: tuple[str, ...] = ()
