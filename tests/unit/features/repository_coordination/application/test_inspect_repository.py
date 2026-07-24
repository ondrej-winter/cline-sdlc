"""Tests for repository inspection use case."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    RepositoryInspectionBlocker,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
    RepositoryInspectionStatus,
    RepositorySnapshot,
)
from cline_sdlc.features.repository_coordination.application.use_cases.inspect_repository import InspectRepository


@dataclass
class RecordingInspector:
    result: RepositoryInspectionResult
    request: RepositoryInspectionRequest | None = None

    def inspect(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        self.request = request
        return self.result


def test_delegates_repository_inspection_to_port() -> None:
    request = RepositoryInspectionRequest(working_directory=Path("/repo"), input_paths=(Path("/repo/docs/spec.md"),))
    snapshot = RepositorySnapshot(repository_root="/repo", head_commit="abc123", branch="feature")
    inspector = RecordingInspector(
        RepositoryInspectionResult(status=RepositoryInspectionStatus.READY, snapshot=snapshot)
    )

    result = InspectRepository(inspector).execute(request)

    assert result.ready
    assert result.snapshot == snapshot
    assert inspector.request == request


def test_returns_blockers_from_repository_inspector() -> None:
    blocker = RepositoryInspectionBlocker(code="git_head_unavailable", summary="HEAD is unavailable")
    inspector = RecordingInspector(
        RepositoryInspectionResult(status=RepositoryInspectionStatus.FAILED, blockers=(blocker,))
    )

    result = InspectRepository(inspector).execute(RepositoryInspectionRequest(working_directory=Path("/repo")))

    assert not result.ready
    assert result.blockers == (blocker,)
