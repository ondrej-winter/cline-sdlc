"""Tests for supervised runner CLI input parsing and terminal result rendering."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cline_sdlc import __version__
from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationResult,
    ArtifactLocationSource,
)
from cline_sdlc.features.cline_execution.adapters.outbound.attached_tty_session_runner import (
    AttachedTtyClineSessionRunner,
)
from cline_sdlc.features.lifecycle_orchestration.adapters.inbound import cli
from cline_sdlc.features.lifecycle_orchestration.adapters.inbound.cli import parse_cli_invocation, run_cli_invocation
from cline_sdlc.features.lifecycle_orchestration.application.dtos.idea_stage import (
    IdeaRefinementResult,
    IdeaRefinementStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationParseError
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_authoring import (
    PlanAuthoringRequest,
    PlanAuthoringResult,
    PlanAuthoringStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_implementation import (
    PlanImplementationResult,
    PlanImplementationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import (
    PlanReviewRequest,
    PlanReviewResult,
    PlanReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.specification_stage import (
    SpecificationCreationRequest,
    SpecificationCreationResult,
    SpecificationCreationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.terminal_result import TerminalBlocker, TerminalResult
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage, StageInputKind
from cline_sdlc.features.lifecycle_orchestration.domain.terminal_result import ExitCategory, TerminalStatus
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.adapters.inbound.plan_implementation_runtime import (
        PlanImplementationRuntimeRequest,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest

CUSTOM_TIMEOUT_SECONDS = 42.0
EXPECTED_PLAN_STAGE_RUNNER_COUNT = 2


def test_rejects_missing_input() -> None:
    result = parse_cli_invocation([])

    assert isinstance(result, InvocationParseError)
    assert "required" in result.message


def test_version_exits_without_requiring_stage_input() -> None:
    result = run_cli_invocation(["--version"])

    assert result.exit_code == ExitCategory.COMPLETED
    assert result.stdout == f"cline-sdlc {__version__}\n"
    assert result.stderr == ""


def test_rejects_multiple_inputs(tmp_path: Path) -> None:
    idea_file = tmp_path / "idea.md"
    idea_file.write_text("idea", encoding="utf-8")

    result = parse_cli_invocation(["--idea", "rough", "--idea-file", str(idea_file)])

    assert isinstance(result, InvocationParseError)
    assert "not allowed" in result.message


def test_rejects_empty_rough_idea() -> None:
    result = parse_cli_invocation(["--idea", "  "])

    assert isinstance(result, InvocationParseError)
    assert "must not be empty" in result.message


@pytest.mark.parametrize(
    ("option", "expected_kind", "expected_stage"),
    [
        ("--idea-file", StageInputKind.IDEA_FILE, LifecycleStage.SPECIFICATION_CREATION),
        ("--spec-file", StageInputKind.SPEC_FILE, LifecycleStage.PLAN_CREATION_AND_REVIEW),
        ("--plan-file", StageInputKind.PLAN_FILE, LifecycleStage.PLAN_IMPLEMENTATION),
    ],
)
def test_maps_file_input_to_stage(
    tmp_path: Path,
    option: str,
    expected_kind: StageInputKind,
    expected_stage: LifecycleStage,
) -> None:
    input_file = tmp_path / "artifact.md"
    input_file.write_text("artifact", encoding="utf-8")

    result = parse_cli_invocation([option, str(input_file)], cwd=tmp_path)

    assert not isinstance(result, InvocationParseError)
    assert result.request.source.kind is expected_kind
    assert result.request.source.value == input_file
    assert result.request.stage is expected_stage


def test_maps_rough_idea_to_idea_refinement() -> None:
    result = parse_cli_invocation(["--idea", "Build a supervised workflow runner"])

    assert not isinstance(result, InvocationParseError)
    assert result.request.source.kind is StageInputKind.IDEA
    assert result.request.source.value == "Build a supervised workflow runner"
    assert result.request.stage is LifecycleStage.IDEA_REFINEMENT


def test_rejects_missing_file_input(tmp_path: Path) -> None:
    result = parse_cli_invocation(["--spec-file", "missing.md"], cwd=tmp_path)

    assert isinstance(result, InvocationParseError)
    assert "does not exist" in result.message


def test_rejects_directory_file_input(tmp_path: Path) -> None:
    result = parse_cli_invocation(["--plan-file", str(tmp_path)], cwd=tmp_path)

    assert isinstance(result, InvocationParseError)
    assert "not a file" in result.message


def test_accepts_dry_run_friendly_common_options() -> None:
    result = parse_cli_invocation(
        [
            "--idea",
            "Refine this",
            "--timeout",
            str(CUSTOM_TIMEOUT_SECONDS),
            "--cline-command",
            "/opt/bin/cline",
            "--json",
            "--verbose",
            "--dry-run",
        ],
    )

    assert not isinstance(result, InvocationParseError)
    assert result.request.timeout_seconds == CUSTOM_TIMEOUT_SECONDS
    assert result.request.cline_command == "/opt/bin/cline"
    assert result.request.emit_json is True
    assert result.request.verbose is True
    assert result.request.dry_run is True


def test_rejects_non_finite_timeout() -> None:
    result = parse_cli_invocation(["--idea", "rough", "--timeout", "inf"])

    assert isinstance(result, InvocationParseError)
    assert "finite positive" in result.message


def test_invalid_invocation_renders_usage_exit_result_without_json_mode() -> None:
    result = run_cli_invocation([])

    assert result.exit_code == ExitCategory.USAGE_ERROR
    assert result.stderr == ""
    assert result.terminal_result.status.value == "invalid_invocation"
    assert result.stdout.startswith("cline-sdlc: invalid_invocation:")
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload["status"] == "invalid_invocation"
    assert payload["blocker"]["code"] == "invalid_invocation"


def test_dry_run_json_mode_emits_only_one_terminal_result() -> None:
    result = run_cli_invocation(["--idea", "Preview", "--dry-run", "--json"])

    assert result.exit_code == ExitCategory.BLOCKED
    assert result.stderr == ""
    assert result.stdout.endswith("\n")
    assert len(result.stdout.splitlines()) == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "blocker": {
            "code": "dry_run_only",
            "evidence": None,
            "summary": "Dry run selected; lifecycle execution was not started.",
        },
        "input_path": None,
        "output_paths": [],
        "plan_material_digest": None,
        "reason": "dry_run_preview",
        "schema_version": 1,
        "specification_digest": None,
        "stage": "idea_refinement",
        "status": "blocked",
    }


def test_idea_invocation_runs_wired_idea_refinement(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run_idea_refinement(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
        calls.append((request, cwd))
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason="idea_brief_accepted",
            stage=request.stage,
            output_paths=("docs/ideas/preview-idea.md",),
        )

    monkeypatch.setattr(cli, "_run_idea_refinement", fake_run_idea_refinement)

    result = run_cli_invocation(["--idea", "Preview", "--json"])

    assert result.exit_code == ExitCategory.COMPLETED
    assert len(calls) == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert payload["reason"] == "idea_brief_accepted"
    assert payload["output_paths"] == ["docs/ideas/preview-idea.md"]


def test_idea_refinement_uses_attached_tty_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured_runners = []

    class FakeArtifactSelector:
        def execute(self, request: object) -> ArtifactLocationResult:
            _ = request
            return ArtifactLocationResult(
                artifact_kind=ArtifactKind.IDEA_BRIEF,
                path="docs/ideas/preview-idea.md",
                directory="docs/ideas",
                source=ArtifactLocationSource.PORTABLE_DEFAULT,
            )

    class FakeRunSessionAttempts:
        def __init__(self, *, runner: object, repository_inspector: object) -> None:
            _ = repository_inspector
            captured_runners.append(runner)

    class FakeRefineIdea:
        def __init__(self, *, preflight: object, session_attempts: object) -> None:
            _ = preflight, session_attempts

        def execute(self, request: object) -> IdeaRefinementResult:
            _ = request
            return IdeaRefinementResult(
                status=IdeaRefinementStatus.COMPLETED,
                output_paths=("docs/ideas/preview-idea.md",),
            )

    monkeypatch.setattr(cli, "SelectArtifactLocation", FakeArtifactSelector)
    monkeypatch.setattr(cli, "RunSessionAttempts", FakeRunSessionAttempts)
    monkeypatch.setattr(cli, "RefineIdea", FakeRefineIdea)

    result = run_cli_invocation(["--idea", "Preview"], cwd=tmp_path).terminal_result

    assert result.status is TerminalStatus.COMPLETED
    assert len(captured_runners) == 1
    assert isinstance(captured_runners[0], AttachedTtyClineSessionRunner)


def test_idea_file_invocation_runs_wired_specification_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = []
    idea_file = tmp_path / "accepted-idea.md"
    idea_file.write_text("accepted idea", encoding="utf-8")

    def fake_run_specification_creation(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
        calls.append((request, cwd))
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason="specification_accepted",
            stage=request.stage,
            input_path=idea_file.as_posix(),
            output_paths=("docs/specs/accepted-spec.md",),
        )

    monkeypatch.setattr(cli, "_run_specification_creation", fake_run_specification_creation)

    result = run_cli_invocation(["--idea-file", "accepted-idea.md", "--json"], cwd=tmp_path)

    assert result.exit_code == ExitCategory.COMPLETED
    assert len(calls) == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert payload["reason"] == "specification_accepted"
    assert payload["stage"] == "specification_creation"
    assert payload["input_path"] == idea_file.as_posix()
    assert payload["output_paths"] == ["docs/specs/accepted-spec.md"]


def test_specification_creation_uses_attached_tty_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured_runners = []
    captured_requests = []
    captured_specification_requests: list[SpecificationCreationRequest] = []
    idea_file = tmp_path / "configurable-lifecycle-hooks-and-repository-task-recipes-idea.md"
    idea_file.write_text("accepted idea", encoding="utf-8")

    class FakeArtifactSelector:
        def execute(self, request: object) -> ArtifactLocationResult:
            captured_requests.append(request)
            return ArtifactLocationResult(
                artifact_kind=ArtifactKind.SPECIFICATION,
                path="docs/specs/configurable-lifecycle-hooks-and-repository-task-recipes-spec.md",
                directory="docs/specs",
                source=ArtifactLocationSource.PORTABLE_DEFAULT,
            )

    class FakeRunSessionAttempts:
        def __init__(self, *, runner: object, repository_inspector: object) -> None:
            _ = repository_inspector
            captured_runners.append(runner)

    class FakeCreateSpecification:
        def __init__(self, *, preflight: object, session_attempts: object) -> None:
            _ = preflight, session_attempts

        def execute(self, request: SpecificationCreationRequest) -> SpecificationCreationResult:
            captured_specification_requests.append(request)
            return SpecificationCreationResult(
                status=SpecificationCreationStatus.COMPLETED,
                output_paths=("docs/specs/configurable-lifecycle-hooks-and-repository-task-recipes-spec.md",),
            )

    monkeypatch.setattr(cli, "SelectArtifactLocation", FakeArtifactSelector)
    monkeypatch.setattr(cli, "RunSessionAttempts", FakeRunSessionAttempts)
    monkeypatch.setattr(cli, "CreateSpecification", FakeCreateSpecification)

    result = run_cli_invocation(["--idea-file", idea_file.name], cwd=tmp_path).terminal_result

    assert result.status is TerminalStatus.COMPLETED
    assert result.reason == "specification_accepted"
    assert len(captured_runners) == 1
    assert isinstance(captured_runners[0], AttachedTtyClineSessionRunner)
    assert len(captured_requests) == 1
    assert len(captured_specification_requests) == 1
    repository_request = captured_specification_requests[0].preflight_request.repository_request
    assert repository_request.input_paths == ()
    assert repository_request.managed_paths == (Path("docs/specs"),)


def test_spec_file_invocation_runs_wired_plan_creation_and_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = []
    spec_file = tmp_path / "accepted-spec.md"
    spec_file.write_text("accepted spec", encoding="utf-8")

    def fake_run_plan_creation_and_review(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
        calls.append((request, cwd))
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason="plan_ready",
            stage=request.stage,
            input_path=spec_file.as_posix(),
            output_paths=("docs/plans/accepted-plan.md",),
            specification_digest="spec-digest",
            plan_material_digest="plan-digest",
        )

    monkeypatch.setattr(cli, "_run_plan_creation_and_review", fake_run_plan_creation_and_review)

    result = run_cli_invocation(["--spec-file", "accepted-spec.md", "--json"], cwd=tmp_path)

    assert result.exit_code == ExitCategory.COMPLETED
    assert len(calls) == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert payload["reason"] == "plan_ready"
    assert payload["stage"] == "plan_creation_and_review"
    assert payload["input_path"] == spec_file.as_posix()
    assert payload["output_paths"] == ["docs/plans/accepted-plan.md"]
    assert payload["specification_digest"] == "spec-digest"
    assert payload["plan_material_digest"] == "plan-digest"


def test_plan_file_invocation_runs_wired_plan_implementation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = []
    plan_file = tmp_path / "accepted-plan.md"
    plan_file.write_text("accepted plan", encoding="utf-8")

    def fake_run_plan_implementation(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
        calls.append((request, cwd))
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason="plan_implementation_completed",
            stage=request.stage,
            input_path=plan_file.as_posix(),
            output_paths=("docs/plans/accepted-plan.md",),
            plan_material_digest="plan-digest",
        )

    monkeypatch.setattr(cli, "_run_plan_implementation", fake_run_plan_implementation)

    result = run_cli_invocation(["--plan-file", "accepted-plan.md", "--json"], cwd=tmp_path)

    assert result.exit_code == ExitCategory.COMPLETED
    assert len(calls) == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert payload["reason"] == "plan_implementation_completed"
    assert payload["stage"] == "plan_implementation"
    assert payload["input_path"] == plan_file.as_posix()
    assert payload["output_paths"] == ["docs/plans/accepted-plan.md"]
    assert payload["plan_material_digest"] == "plan-digest"


def test_plan_file_invocation_reports_plan_state_blocker_instead_of_unwired_stage(tmp_path: Path) -> None:
    plan_file = tmp_path / "accepted-plan.md"
    plan_file.write_text("accepted plan without state", encoding="utf-8")

    result = run_cli_invocation(["--plan-file", "accepted-plan.md", "--json"], cwd=tmp_path)

    assert result.exit_code == ExitCategory.BLOCKED
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["reason"] == "plan_implementation_blocked"
    assert payload["stage"] == "plan_implementation"
    assert payload["input_path"] == plan_file.as_posix()
    assert payload["blocker"]["code"] == "plan_state_unavailable"


def test_plan_file_invocation_bootstraps_legacy_plan_state_from_spec_reference(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    specs = docs / "specs"
    plans = docs / "plans"
    specs.mkdir(parents=True)
    plans.mkdir(parents=True)
    spec_file = specs / "accepted-spec.md"
    spec_file.write_text("# Accepted Spec\n\nRequirements.\n", encoding="utf-8")
    plan_file = plans / "accepted-plan.md"
    plan_file.write_text(
        "# Implementation Plan\n\nBased on `docs/specs/accepted-spec.md`.\n\n## Task 1\n\n- [ ] Ship it.\n",
        encoding="utf-8",
    )

    result = run_cli_invocation(["--plan-file", "docs/plans/accepted-plan.md", "--json"], cwd=tmp_path)

    assert result.exit_code == ExitCategory.BLOCKED
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["reason"] == "plan_implementation_blocked"
    assert payload["stage"] == "plan_implementation"
    assert payload["input_path"] == plan_file.as_posix()
    assert payload["blocker"]["code"] == "plan_task_definitions_unavailable"
    assert "## Task N: Title" in payload["blocker"]["evidence"]
    assert payload["specification_digest"].startswith("sha256:")
    assert payload["plan_material_digest"].startswith("sha256:")


def test_plan_file_invocation_extracts_legacy_task_metadata_before_runtime_blocker(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    specs = docs / "specs"
    plans = docs / "plans"
    specs.mkdir(parents=True)
    plans.mkdir(parents=True)
    spec_file = specs / "accepted-spec.md"
    spec_file.write_text("# Accepted Spec\n\nRequirements.\n", encoding="utf-8")
    plan_file = plans / "accepted-plan.md"
    plan_file.write_text(
        "# Implementation Plan\n\n"
        "Based on `docs/specs/accepted-spec.md`.\n\n"
        "## Task 1: First slice\n\n- [ ] Ship it.\n\n"
        "## Task 2: Second slice\n\n- [ ] Verify it.\n",
        encoding="utf-8",
    )

    def fake_run_plan_implementation_runtime(request: PlanImplementationRuntimeRequest) -> PlanImplementationResult:
        runtime_request = request
        approval = cli._plan_state_from_markdown_or_legacy_plan(  # noqa: SLF001
            plan_file.read_text(encoding="utf-8"),
            plan_path=plan_file,
            repository_root=tmp_path,
        )
        assert runtime_request.tasks[0].task_id == "task-1"
        return PlanImplementationResult(
            status=PlanImplementationStatus.BLOCKED,
            approval=InvocationApproval(
                run_id="run-test",
                profile="balanced",
                starting_head="a" * 40,
                approved_at=datetime.now(UTC),
                specification_digest=approval.specification_digest,
                material_digest=approval.material_digest,
                remediation_envelope_applicable=True,
            ),
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "run_plan_implementation_runtime", fake_run_plan_implementation_runtime)
    try:
        result = run_cli_invocation(["--plan-file", "docs/plans/accepted-plan.md", "--json"], cwd=tmp_path)
    finally:
        monkeypatch.undo()

    assert result.exit_code == ExitCategory.BLOCKED
    payload = json.loads(result.stdout)
    assert payload["blocker"]["code"] == "plan_implementation_incomplete"


def test_plan_file_invocation_runs_plan_implementation_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    specs = docs / "specs"
    plans = docs / "plans"
    specs.mkdir(parents=True)
    plans.mkdir(parents=True)
    spec_file = specs / "accepted-spec.md"
    spec_file.write_text("# Accepted Spec\n\nRequirements.\n", encoding="utf-8")
    plan_file = plans / "accepted-plan.md"
    plan_file.write_text(
        "# Implementation Plan\n\n"
        "Based on `docs/specs/accepted-spec.md`.\n\n"
        "## Task 1: First slice\n\n"
        "**Likely files/components touched:**\n\n"
        "- `src/example.py`\n",
        encoding="utf-8",
    )
    calls = []

    def fake_run_plan_implementation_runtime(request: PlanImplementationRuntimeRequest) -> PlanImplementationResult:
        calls.append(request)
        return PlanImplementationResult(
            status=PlanImplementationStatus.COMPLETED,
            approval=InvocationApproval(
                run_id="run-test",
                profile="balanced",
                starting_head="a" * 40,
                approved_at=datetime.now(UTC),
                specification_digest=request.plan_state.specification_digest,
                material_digest=request.plan_state.material_digest,
                remediation_envelope_applicable=True,
            ),
        )

    monkeypatch.setattr(cli, "run_plan_implementation_runtime", fake_run_plan_implementation_runtime)

    result = run_cli_invocation(["--plan-file", "docs/plans/accepted-plan.md", "--json"], cwd=tmp_path)

    assert result.exit_code == ExitCategory.COMPLETED
    assert len(calls) == 1
    assert calls[0].tasks[0].slices[0].expected_paths == ("src/example.py",)
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert payload["reason"] == "plan_implementation_completed"


def test_plan_creation_and_review_uses_attached_tty_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured_runners = []
    captured_artifact_requests = []
    captured_authoring_requests: list[PlanAuthoringRequest] = []
    captured_review_requests: list[PlanReviewRequest] = []
    spec_file = tmp_path / "configurable-lifecycle-hooks-and-repository-task-spec.md"
    spec_file.write_text("accepted spec", encoding="utf-8")

    class FakeArtifactSelector:
        def execute(self, request: object) -> ArtifactLocationResult:
            captured_artifact_requests.append(request)
            return ArtifactLocationResult(
                artifact_kind=ArtifactKind.PLAN,
                path="docs/plans/configurable-lifecycle-hooks-and-repository-task-plan.md",
                directory="docs/plans",
                source=ArtifactLocationSource.PORTABLE_DEFAULT,
            )

    class FakeRunSessionAttempts:
        def __init__(self, *, runner: object, repository_inspector: object) -> None:
            _ = repository_inspector
            captured_runners.append(runner)

    class FakeAuthorPlan:
        def __init__(
            self,
            *,
            preflight: object,
            validation_discovery: object,
            session_attempts: object,
            content_reader: object,
            plan_validator: object,
        ) -> None:
            _ = preflight, validation_discovery, session_attempts, content_reader, plan_validator

        def execute(self, request: PlanAuthoringRequest) -> PlanAuthoringResult:
            captured_authoring_requests.append(request)
            return PlanAuthoringResult(
                status=PlanAuthoringStatus.COMPLETED,
                output_paths=("docs/plans/configurable-lifecycle-hooks-and-repository-task-plan.md",),
                specification_digest="spec-digest",
                material_digest="draft-digest",
            )

    class FakeCompletePlanReview:
        def __init__(self, *, reviewer: object, reviser: object) -> None:
            _ = reviewer, reviser

        def execute(self, request: PlanReviewRequest) -> PlanReviewResult:
            captured_review_requests.append(request)
            return PlanReviewResult(
                status=PlanReviewStatus.READY,
                output_paths=(request.plan_path,),
                material_digest="ready-digest",
            )

    monkeypatch.setattr(cli, "SelectArtifactLocation", FakeArtifactSelector)
    monkeypatch.setattr(cli, "RunSessionAttempts", FakeRunSessionAttempts)
    monkeypatch.setattr(cli, "AuthorPlan", FakeAuthorPlan)
    monkeypatch.setattr(cli, "CompletePlanReview", FakeCompletePlanReview)

    result = run_cli_invocation(["--spec-file", spec_file.name], cwd=tmp_path).terminal_result

    assert result.status is TerminalStatus.COMPLETED
    assert result.reason == "plan_ready"
    assert result.specification_digest == "spec-digest"
    assert result.plan_material_digest == "ready-digest"
    assert len(captured_runners) == EXPECTED_PLAN_STAGE_RUNNER_COUNT
    assert all(isinstance(runner, AttachedTtyClineSessionRunner) for runner in captured_runners)
    assert len(captured_artifact_requests) == 1
    assert len(captured_authoring_requests) == 1
    assert len(captured_review_requests) == 1
    repository_request = captured_authoring_requests[0].preflight_request.repository_request
    assert repository_request.input_paths == ()
    assert repository_request.managed_paths == (Path("docs/plans"),)
    assert captured_review_requests[0].plan_path == (
        "docs/plans/configurable-lifecycle-hooks-and-repository-task-plan.md"
    )


def test_idea_invocation_json_preserves_session_failure_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_idea_refinement(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
        _ = cwd
        return TerminalResult(
            status=TerminalStatus.FAILED,
            reason="idea_refinement_failed",
            stage=request.stage,
            blocker=TerminalBlocker(
                code="session_retry_exhausted",
                summary="bounded retry was exhausted before one terminal outcome was observed",
                evidence="attempt=1 process_status=exited exit_code=0 terminal_outcomes=0",
            ),
        )

    monkeypatch.setattr(cli, "_run_idea_refinement", fake_run_idea_refinement)

    result = run_cli_invocation(["--idea", "Preview", "--json"])

    assert result.exit_code == ExitCategory.STAGE_FAILED
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["blocker"] == {
        "code": "session_retry_exhausted",
        "summary": "bounded retry was exhausted before one terminal outcome was observed",
        "evidence": "attempt=1 process_status=exited exit_code=0 terminal_outcomes=0",
    }


def test_terminal_result_preserves_actionable_blocker_evidence() -> None:
    result = TerminalResult(
        status=TerminalStatus.BLOCKED,
        reason="idea_refinement_blocked",
        stage=LifecycleStage.IDEA_REFINEMENT,
        blocker=TerminalBlocker(
            code="idea_preflight_failed",
            summary="idea refinement preflight failed before Cline could start",
            evidence="cline_capability:cline_capability_required_skill:idea-refine",
        ),
    )

    payload = result.to_payload()
    assert payload["blocker"] == {
        "code": "idea_preflight_failed",
        "summary": "idea refinement preflight failed before Cline could start",
        "evidence": "cline_capability:cline_capability_required_skill:idea-refine",
    }


def test_file_input_terminal_result_reports_normalized_input_path(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("plan", encoding="utf-8")

    result = run_cli_invocation(["--plan-file", "plan.md", "--json"], cwd=tmp_path)

    payload = json.loads(result.stdout)
    assert payload["stage"] == "plan_implementation"
    assert payload["input_path"] == plan_file.as_posix()
