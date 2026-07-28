"""DTOs for repository task commit-message validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.repository_tasks.domain.conventional_commit import ConventionalCommitValidationResult


@dataclass(frozen=True)
class CommitMessageValidationDTO:
    """Serialization-friendly Conventional Commit validation result."""

    valid: bool
    code: str
    summary: str
    normalized_message: str | None = None
    commit_type: str | None = None
    scope: str | None = None
    breaking_change: bool = False
    footers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "commit message validation code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "commit message validation summary must not be empty"
            raise ValueError(message)

    @classmethod
    def from_domain(cls, result: ConventionalCommitValidationResult) -> CommitMessageValidationDTO:
        """Create a DTO from a domain validation result."""
        return cls(
            valid=result.valid,
            code=result.code.value,
            summary=result.summary,
            normalized_message=result.normalized_message,
            commit_type=result.commit_type,
            scope=result.scope,
            breaking_change=result.breaking_change,
            footers=result.footers,
        )
