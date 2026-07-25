"""Outbound port for one explicit local slice commit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.slice_commit import (
        GitSliceCommitObservation,
        GitSliceCommitRequest,
    )


class GitSliceCommitterPort(Protocol):
    """Apply validated progress bytes and create one explicit Git commit."""

    def commit(self, request: GitSliceCommitRequest) -> GitSliceCommitObservation:
        """Return observable commit evidence without hiding hook failures."""
