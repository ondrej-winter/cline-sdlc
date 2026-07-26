"""Integration tests for progress-only plan finalization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import parse_plan_state_from_markdown
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase
from cline_sdlc.features.repository_coordination.adapters.outbound.git_finalization import (
    GitCliFinalizationHistoryReader,
    GitCliFinalizer,
)
from cline_sdlc.features.repository_coordination.adapters.outbound.plan_artifact import StrictPlanArtifactInspector
from cline_sdlc.features.repository_coordination.application.dtos.finalization import FinalizationStatus
from cline_sdlc.features.repository_coordination.application.use_cases.finalize_plan import FinalizePlan
from tests.finalization_support import (
    PLAN_PATH,
    complete_noop_request,
    finalization_request,
    git,
    git_stdout,
    initialized_repository,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_creates_one_explicit_finalization_commit_and_verifies_history(tmp_path: Path) -> None:
    repository = initialized_repository(tmp_path)
    request = finalization_request(repository)
    starting_head = request.approval.starting_head

    result = use_case().execute(request)

    assert result.status is FinalizationStatus.FINALIZED
    assert result.commit == git_stdout(repository, "rev-parse", "HEAD")
    assert result.commit != starting_head
    assert git_stdout(repository, "status", "--porcelain=v1") == ""
    assert git_stdout(repository, "show", "--format=", "--name-only", "HEAD") == PLAN_PATH
    message = git_stdout(repository, "show", "-s", "--format=%B", "HEAD")
    assert "Cline-SDLC-Plan-Finalization: true" in message
    assert message.count("Cline-SDLC-Work-ID:") == 1
    state = parse_plan_state_from_markdown((repository / PLAN_PATH).read_text(encoding="utf-8"))
    assert state.phase is PlanPhase.COMPLETE
    assert state.completed_at is not None

    noop = use_case().execute(complete_noop_request(repository))

    assert noop.status is FinalizationStatus.ALREADY_COMPLETE
    assert noop.commit == result.commit
    assert git_stdout(repository, "rev-parse", "HEAD") == result.commit


def test_hook_failure_writes_recoverable_partial_finalization(tmp_path: Path) -> None:
    repository = initialized_repository(tmp_path)
    request = finalization_request(repository)
    hook = repository / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\necho finalization rejected >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    result = use_case().execute(request)

    assert result.status is FinalizationStatus.RECOVERY_REQUIRED
    assert result.blocker is not None
    assert "finalization rejected" in (result.blocker.evidence or "")
    assert git_stdout(repository, "rev-parse", "HEAD") == request.approval.starting_head
    assert git_stdout(repository, "diff", "--cached", "--name-only") == ""
    state = parse_plan_state_from_markdown((repository / PLAN_PATH).read_text(encoding="utf-8"))
    assert state.phase is PlanPhase.BLOCKED
    assert state.current_task == "finalization"
    assert state.current_slice == "finalization"
    assert state.partial_slice_paths == (PLAN_PATH,)
    assert state.completed_at is None


def test_unrelated_dirty_path_prevents_plan_write_or_commit(tmp_path: Path) -> None:
    repository = initialized_repository(tmp_path)
    request = finalization_request(repository)
    original = (repository / PLAN_PATH).read_bytes()
    (repository / "unrelated.txt").write_text("human work\n", encoding="utf-8")

    result = use_case().execute(request)

    assert result.status is FinalizationStatus.RECOVERY_REQUIRED
    assert (repository / PLAN_PATH).read_bytes() == original
    assert git_stdout(repository, "rev-parse", "HEAD") == request.approval.starting_head


def test_complete_plan_without_reachable_finalization_commit_is_blocked(tmp_path: Path) -> None:
    repository = initialized_repository(tmp_path)
    request = finalization_request(repository)
    (repository / PLAN_PATH).write_bytes(request.completed_plan_content or b"")
    git(repository, "add", PLAN_PATH)
    git(repository, "commit", "-m", "Mark complete without finalization trailers")

    result = use_case().execute(complete_noop_request(repository))

    assert result.status is FinalizationStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "finalization_commit_missing"


def use_case() -> FinalizePlan:
    """Construct the production finalization boundary."""
    return FinalizePlan(
        StrictPlanArtifactInspector(),
        GitCliFinalizer(),
        GitCliFinalizationHistoryReader(),
    )
