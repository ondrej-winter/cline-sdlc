"""Select implementation work from reconciled plan progress without effects."""

from __future__ import annotations

from dataclasses import dataclass

from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PlanSliceDefinition,
    SelectedSlice,
    SliceSelectionBlocker,
    SliceSelectionRequest,
    SliceSelectionResult,
    SliceSelectionStatus,
)


@dataclass(frozen=True)
class _IndexedSlice:
    task_id: str
    definition: PlanSliceDefinition


class SelectSlice:
    """Validate plan progress and deterministically select the next slice."""

    def execute(self, request: SliceSelectionRequest) -> SliceSelectionResult:
        """Return a partial slice first, otherwise the earliest ready incomplete slice."""
        index_result = _index_definitions(request)
        if isinstance(index_result, SliceSelectionResult):
            return index_result
        ordered_slices, slices_by_id = index_result

        definition_blocker = _validate_dependency_definitions(ordered_slices, slices_by_id)
        if definition_blocker is not None:
            return definition_blocker
        for validation in (
            _validate_dependency_cycles(ordered_slices, slices_by_id),
            _validate_completion_evidence(request, slices_by_id),
        ):
            if validation is not None:
                return validation
        completed = frozenset(request.completed_slice_ids)

        partial_result = _select_partial(request, slices_by_id, completed)
        if partial_result is not None:
            return partial_result

        return _select_new_slice(request, ordered_slices, completed)


def _index_definitions(
    request: SliceSelectionRequest,
) -> tuple[tuple[_IndexedSlice, ...], dict[str, _IndexedSlice]] | SliceSelectionResult:
    if not request.tasks:
        return _blocked("plan_tasks_missing", "slice selection requires at least one plan task")
    task_ids: set[str] = set()
    ordered_slices: list[_IndexedSlice] = []
    slices_by_id: dict[str, _IndexedSlice] = {}
    for task in request.tasks:
        if task.task_id in task_ids:
            return _blocked("duplicate_task_id", "plan task identifiers must be unique", task.task_id)
        if not task.slices:
            return _blocked(
                "task_slices_missing", "every selectable plan task requires at least one slice", task.task_id
            )
        task_ids.add(task.task_id)
        for definition in task.slices:
            if definition.slice_id in slices_by_id:
                return _blocked(
                    "duplicate_slice_id",
                    "plan slice identifiers must be globally unique",
                    definition.slice_id,
                )
            indexed = _IndexedSlice(task_id=task.task_id, definition=definition)
            ordered_slices.append(indexed)
            slices_by_id[definition.slice_id] = indexed
    return tuple(ordered_slices), slices_by_id


def _validate_dependency_definitions(
    ordered_slices: tuple[_IndexedSlice, ...],
    slices_by_id: dict[str, _IndexedSlice],
) -> SliceSelectionResult | None:
    for indexed_slice in ordered_slices:
        dependencies = indexed_slice.definition.dependencies
        if len(set(dependencies)) != len(dependencies):
            return _blocked(
                "duplicate_slice_dependency",
                "a slice must not declare the same dependency more than once",
                indexed_slice.definition.slice_id,
            )
        for dependency in dependencies:
            if dependency not in slices_by_id:
                return _blocked(
                    "unknown_slice_dependency",
                    "every dependency must reference a declared slice",
                    dependency,
                )
    return None


def _validate_dependency_cycles(
    ordered_slices: tuple[_IndexedSlice, ...],
    slices_by_id: dict[str, _IndexedSlice],
) -> SliceSelectionResult | None:
    dependency_counts = {
        indexed.definition.slice_id: len(indexed.definition.dependencies) for indexed in ordered_slices
    }
    dependents: dict[str, list[str]] = {slice_id: [] for slice_id in slices_by_id}
    for indexed in ordered_slices:
        for dependency in indexed.definition.dependencies:
            dependents[dependency].append(indexed.definition.slice_id)

    ready = [
        indexed.definition.slice_id for indexed in ordered_slices if dependency_counts[indexed.definition.slice_id] == 0
    ]
    validated_count = 0
    while ready:
        slice_id = ready.pop()
        validated_count += 1
        for dependent in dependents[slice_id]:
            dependency_counts[dependent] -= 1
            if dependency_counts[dependent] == 0:
                ready.append(dependent)

    if validated_count != len(ordered_slices):
        return _blocked("slice_dependency_cycle", "slice dependencies must form an acyclic graph")
    return None


def _validate_completion_evidence(
    request: SliceSelectionRequest,
    slices_by_id: dict[str, _IndexedSlice],
) -> SliceSelectionResult | None:
    if len(set(request.completed_slice_ids)) != len(request.completed_slice_ids):
        return _blocked("duplicate_completed_slice", "completed slice identifiers must be unique")
    unknown_completed = next((item for item in request.completed_slice_ids if item not in slices_by_id), None)
    if unknown_completed is not None:
        return _blocked("unknown_completed_slice", "completed progress references an unknown slice", unknown_completed)

    evidence_result = _index_completion_evidence(request, slices_by_id)
    if isinstance(evidence_result, SliceSelectionResult):
        return evidence_result
    evidence_by_id = evidence_result

    completed = frozenset(request.completed_slice_ids)
    conflict = next(
        (slice_id for slice_id in request.completed_slice_ids if evidence_by_id.get(slice_id) is not True),
        None,
    )
    if conflict is None:
        conflict = next(
            (slice_id for slice_id, value in evidence_by_id.items() if value and slice_id not in completed),
            None,
        )
    if conflict is not None:
        return _blocked(
            "completion_evidence_conflict",
            "completion evidence and completed progress must agree exactly",
            conflict,
        )
    dependency_conflict = next(
        (
            slice_id
            for slice_id in request.completed_slice_ids
            if any(dependency not in completed for dependency in slices_by_id[slice_id].definition.dependencies)
        ),
        None,
    )
    if dependency_conflict is not None:
        return _blocked(
            "completed_slice_dependency_incomplete",
            "completed slices require all declared dependencies to be complete",
            dependency_conflict,
        )
    return None


def _index_completion_evidence(
    request: SliceSelectionRequest,
    slices_by_id: dict[str, _IndexedSlice],
) -> dict[str, bool] | SliceSelectionResult:
    evidence_by_id: dict[str, bool] = {}
    for evidence in request.completion_evidence:
        if evidence.slice_id not in slices_by_id:
            return _blocked(
                "unknown_completion_evidence",
                "completion evidence references an unknown slice",
                evidence.slice_id,
            )
        if evidence.slice_id in evidence_by_id:
            return _blocked(
                "duplicate_completion_evidence",
                "each slice may have at most one completion-evidence record",
                evidence.slice_id,
            )
        evidence_by_id[evidence.slice_id] = evidence.completed
    return evidence_by_id


def _select_partial(
    request: SliceSelectionRequest,
    slices_by_id: dict[str, _IndexedSlice],
    completed: frozenset[str],
) -> SliceSelectionResult | None:
    partial = request.partial_slice
    if partial is None:
        return None
    indexed_slice = slices_by_id.get(partial.slice_id)
    blocker = _partial_blocker(partial.task_id, partial.slice_id, partial.paths, indexed_slice, completed)
    if blocker is not None:
        return blocker
    return SliceSelectionResult(
        status=SliceSelectionStatus.SELECTED,
        selection=SelectedSlice(task_id=partial.task_id, slice_id=partial.slice_id, resuming_partial=True),
        completed_slice_ids=request.completed_slice_ids,
    )


def _partial_blocker(
    task_id: str,
    slice_id: str,
    paths: tuple[str, ...],
    indexed_slice: _IndexedSlice | None,
    completed: frozenset[str],
) -> SliceSelectionResult | None:
    if indexed_slice is None:
        return _blocked("unknown_partial_slice", "partial progress references an unknown slice", slice_id)
    if slice_id in completed:
        return _blocked("partial_slice_already_completed", "a completed slice cannot also be partial", slice_id)
    if indexed_slice.task_id != task_id:
        return _blocked(
            "partial_slice_task_mismatch", "partial progress must match the slice's declared task", slice_id
        )
    if not paths:
        return _blocked("partial_slice_paths_missing", "partial progress must identify owned uncommitted paths")
    if not all(dependency in completed for dependency in indexed_slice.definition.dependencies):
        return _blocked(
            "partial_slice_dependencies_incomplete",
            "a partial slice requires all declared dependencies to remain complete",
            slice_id,
        )
    return None


def _select_new_slice(
    request: SliceSelectionRequest,
    ordered_slices: tuple[_IndexedSlice, ...],
    completed: frozenset[str],
) -> SliceSelectionResult:
    selected = next(
        (
            item
            for item in ordered_slices
            if item.definition.slice_id not in completed
            and all(dependency in completed for dependency in item.definition.dependencies)
        ),
        None,
    )
    if selected is not None:
        return SliceSelectionResult(
            status=SliceSelectionStatus.SELECTED,
            selection=SelectedSlice(
                task_id=selected.task_id,
                slice_id=selected.definition.slice_id,
                resuming_partial=False,
            ),
            completed_slice_ids=request.completed_slice_ids,
        )
    if len(completed) == len(ordered_slices):
        return SliceSelectionResult(
            status=SliceSelectionStatus.COMPLETE,
            completed_slice_ids=request.completed_slice_ids,
        )
    return _blocked(
        "no_dependency_ready_slice",
        "incomplete slices remain but none has all declared dependencies complete",
    )


def _blocked(code: str, summary: str, evidence: str | None = None) -> SliceSelectionResult:
    return SliceSelectionResult(
        status=SliceSelectionStatus.BLOCKED,
        blocker=SliceSelectionBlocker(code=code, summary=summary, evidence=evidence),
    )
