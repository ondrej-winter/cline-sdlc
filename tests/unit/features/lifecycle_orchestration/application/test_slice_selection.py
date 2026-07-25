"""Tests for deterministic plan-slice selection."""

from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PartialSliceProgress,
    PlanSliceDefinition,
    PlanTaskDefinition,
    SliceCompletionEvidence,
    SliceSelectionRequest,
    SliceSelectionResult,
    SliceSelectionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_slice import SelectSlice


def test_selects_valid_partial_slice_before_other_ready_work() -> None:
    request = _request(
        completed_slice_ids=("slice-1",),
        completion_evidence=(SliceCompletionEvidence(slice_id="slice-1", completed=True),),
        partial_slice=PartialSliceProgress(
            task_id="task-2",
            slice_id="slice-2",
            paths=("src/partial.py",),
        ),
    )

    result = SelectSlice().execute(request)

    assert result.status is SliceSelectionStatus.SELECTED
    assert result.selection is not None
    assert result.selection.slice_id == "slice-2"
    assert result.selection.resuming_partial


def test_selects_earliest_dependency_ready_incomplete_slice() -> None:
    request = _request(
        completed_slice_ids=("slice-1",),
        completion_evidence=(SliceCompletionEvidence(slice_id="slice-1", completed=True),),
    )

    result = SelectSlice().execute(request)

    assert result.status is SliceSelectionStatus.SELECTED
    assert result.selection is not None
    assert result.selection.task_id == "task-2"
    assert result.selection.slice_id == "slice-2"
    assert not result.selection.resuming_partial


def test_skips_incomplete_slice_with_unsatisfied_dependencies() -> None:
    request = SliceSelectionRequest(
        tasks=(
            PlanTaskDefinition(
                task_id="task-1",
                slices=(PlanSliceDefinition(slice_id="blocked-first", dependencies=("later-ready",)),),
            ),
            PlanTaskDefinition(
                task_id="task-2",
                slices=(PlanSliceDefinition(slice_id="later-ready"),),
            ),
        )
    )

    result = SelectSlice().execute(request)

    assert result.selection is not None
    assert result.selection.slice_id == "later-ready"


def test_returns_complete_when_every_slice_has_matching_completion_evidence() -> None:
    request = _request(
        completed_slice_ids=("slice-1", "slice-2", "slice-3"),
        completion_evidence=tuple(
            SliceCompletionEvidence(slice_id=slice_id, completed=True) for slice_id in ("slice-1", "slice-2", "slice-3")
        ),
    )

    result = SelectSlice().execute(request)

    assert result.status is SliceSelectionStatus.COMPLETE
    assert result.selection is None
    assert result.blocker is None


def test_repeated_selection_is_deterministic_and_never_selects_completed_slice() -> None:
    request = _request(
        completed_slice_ids=("slice-1",),
        completion_evidence=(SliceCompletionEvidence(slice_id="slice-1", completed=True),),
    )
    selector = SelectSlice()

    first = selector.execute(request)
    second = selector.execute(request)

    assert first == second
    assert first.selection is not None
    assert first.selection.slice_id != "slice-1"


def test_blocks_duplicate_task_identifiers() -> None:
    task = PlanTaskDefinition(task_id="task-1", slices=(PlanSliceDefinition(slice_id="slice-1"),))

    result = SelectSlice().execute(SliceSelectionRequest(tasks=(task, task)))

    assert _blocker_code(result) == "duplicate_task_id"


def test_blocks_empty_plan_or_task_definitions() -> None:
    empty_plan = SliceSelectionRequest(tasks=())
    empty_task = SliceSelectionRequest(tasks=(PlanTaskDefinition(task_id="task-1", slices=()),))

    assert _blocker_code(SelectSlice().execute(empty_plan)) == "plan_tasks_missing"
    assert _blocker_code(SelectSlice().execute(empty_task)) == "task_slices_missing"


def test_blocks_duplicate_slice_identifiers_across_tasks() -> None:
    result = SelectSlice().execute(
        SliceSelectionRequest(
            tasks=(
                PlanTaskDefinition(task_id="task-1", slices=(PlanSliceDefinition(slice_id="same"),)),
                PlanTaskDefinition(task_id="task-2", slices=(PlanSliceDefinition(slice_id="same"),)),
            )
        )
    )

    assert _blocker_code(result) == "duplicate_slice_id"


def test_blocks_duplicate_dependency_identifiers() -> None:
    result = SelectSlice().execute(
        SliceSelectionRequest(
            tasks=(
                PlanTaskDefinition(
                    task_id="task-1",
                    slices=(PlanSliceDefinition(slice_id="slice-1", dependencies=("slice-2", "slice-2")),),
                ),
                PlanTaskDefinition(task_id="task-2", slices=(PlanSliceDefinition(slice_id="slice-2"),)),
            )
        )
    )

    assert _blocker_code(result) == "duplicate_slice_dependency"


def test_blocks_unknown_dependency() -> None:
    result = SelectSlice().execute(
        SliceSelectionRequest(
            tasks=(
                PlanTaskDefinition(
                    task_id="task-1",
                    slices=(PlanSliceDefinition(slice_id="slice-1", dependencies=("missing",)),),
                ),
            )
        )
    )

    assert _blocker_code(result) == "unknown_slice_dependency"


def test_blocks_self_dependency_and_multi_slice_cycle() -> None:
    self_dependency = SliceSelectionRequest(
        tasks=(
            PlanTaskDefinition(
                task_id="task-1",
                slices=(PlanSliceDefinition(slice_id="slice-1", dependencies=("slice-1",)),),
            ),
        )
    )
    cycle = SliceSelectionRequest(
        tasks=(
            PlanTaskDefinition(
                task_id="task-1",
                slices=(PlanSliceDefinition(slice_id="slice-1", dependencies=("slice-2",)),),
            ),
            PlanTaskDefinition(
                task_id="task-2",
                slices=(PlanSliceDefinition(slice_id="slice-2", dependencies=("slice-1",)),),
            ),
        )
    )

    assert _blocker_code(SelectSlice().execute(self_dependency)) == "slice_dependency_cycle"
    assert _blocker_code(SelectSlice().execute(cycle)) == "slice_dependency_cycle"


def test_blocks_unknown_or_conflicting_completion_evidence() -> None:
    unknown = _request(completed_slice_ids=("missing",))
    conflict = _request(
        completed_slice_ids=("slice-1",),
        completion_evidence=(SliceCompletionEvidence(slice_id="slice-1", completed=False),),
    )

    assert _blocker_code(SelectSlice().execute(unknown)) == "unknown_completed_slice"
    assert _blocker_code(SelectSlice().execute(conflict)) == "completion_evidence_conflict"


def test_blocks_completed_slice_with_incomplete_dependency() -> None:
    result = SelectSlice().execute(
        _request(
            completed_slice_ids=("slice-2",),
            completion_evidence=(SliceCompletionEvidence(slice_id="slice-2", completed=True),),
        )
    )

    assert _blocker_code(result) == "completed_slice_dependency_incomplete"


def test_completion_conflict_evidence_follows_declared_progress_order() -> None:
    request = _request(completed_slice_ids=("slice-2", "slice-1"))

    result = SelectSlice().execute(request)

    assert result.blocker is not None
    assert result.blocker.evidence == "slice-2"


def test_blocks_duplicate_completion_evidence() -> None:
    evidence = SliceCompletionEvidence(slice_id="slice-1", completed=True)
    result = SelectSlice().execute(_request(completed_slice_ids=("slice-1",), completion_evidence=(evidence, evidence)))

    assert _blocker_code(result) == "duplicate_completion_evidence"


def test_blocks_partial_slice_that_is_unknown_completed_or_has_wrong_task() -> None:
    unknown = _request(partial_slice=PartialSliceProgress(task_id="task-1", slice_id="missing", paths=("a.py",)))
    completed = _request(
        completed_slice_ids=("slice-1",),
        completion_evidence=(SliceCompletionEvidence(slice_id="slice-1", completed=True),),
        partial_slice=PartialSliceProgress(task_id="task-1", slice_id="slice-1", paths=("a.py",)),
    )
    wrong_task = _request(partial_slice=PartialSliceProgress(task_id="task-3", slice_id="slice-1", paths=("a.py",)))

    assert _blocker_code(SelectSlice().execute(unknown)) == "unknown_partial_slice"
    assert _blocker_code(SelectSlice().execute(completed)) == "partial_slice_already_completed"
    assert _blocker_code(SelectSlice().execute(wrong_task)) == "partial_slice_task_mismatch"


def test_blocks_partial_slice_without_owned_paths() -> None:
    result = SelectSlice().execute(_request(partial_slice=PartialSliceProgress(task_id="task-1", slice_id="slice-1")))

    assert _blocker_code(result) == "partial_slice_paths_missing"


def test_long_acyclic_dependency_chain_is_validated_without_recursion() -> None:
    slice_count = 1200
    slices = tuple(
        PlanSliceDefinition(
            slice_id=f"slice-{index}",
            dependencies=() if index == 0 else (f"slice-{index - 1}",),
        )
        for index in range(slice_count)
    )

    result = SelectSlice().execute(SliceSelectionRequest(tasks=(PlanTaskDefinition(task_id="task-1", slices=slices),)))

    assert result.status is SliceSelectionStatus.SELECTED
    assert result.selection is not None
    assert result.selection.slice_id == "slice-0"


def _request(
    *,
    completed_slice_ids: tuple[str, ...] = (),
    completion_evidence: tuple[SliceCompletionEvidence, ...] = (),
    partial_slice: PartialSliceProgress | None = None,
) -> SliceSelectionRequest:
    return SliceSelectionRequest(
        tasks=(
            PlanTaskDefinition(task_id="task-1", slices=(PlanSliceDefinition(slice_id="slice-1"),)),
            PlanTaskDefinition(
                task_id="task-2",
                slices=(PlanSliceDefinition(slice_id="slice-2", dependencies=("slice-1",)),),
            ),
            PlanTaskDefinition(task_id="task-3", slices=(PlanSliceDefinition(slice_id="slice-3"),)),
        ),
        completed_slice_ids=completed_slice_ids,
        completion_evidence=completion_evidence,
        partial_slice=partial_slice,
    )


def _blocker_code(result: SliceSelectionResult) -> str:
    assert result.status is SliceSelectionStatus.BLOCKED
    assert result.blocker is not None
    return result.blocker.code
