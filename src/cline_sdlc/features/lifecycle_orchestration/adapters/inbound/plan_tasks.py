"""Parse implementation-plan task headings into slice-selection definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PlanSliceDefinition,
    PlanTaskDefinition,
)

_TASK_HEADING_PATTERN = re.compile(r"^## Task (?P<number>[1-9][0-9]*): (?P<title>\S.*)$", re.MULTILINE)
_TASK_HEADING_MISSING_MESSAGE = "plan must contain at least one '## Task N: Title' heading"


@dataclass(frozen=True)
class PlanTaskParseError(ValueError):
    """Actionable failure encountered while extracting plan task metadata."""

    message: str

    def __str__(self) -> str:
        return self.message


def parse_plan_task_definitions(markdown: str) -> tuple[PlanTaskDefinition, ...]:
    """Extract deterministic task/slice definitions from an accepted markdown plan.

    The current supervised implementation boundary accepts only the established
    ``## Task N: Title`` plan shape. It intentionally derives one linear slice
    per task and does not interpret arbitrary repository workflow content.
    """
    matches = tuple(_TASK_HEADING_PATTERN.finditer(markdown))
    if not matches:
        raise PlanTaskParseError(_TASK_HEADING_MISSING_MESSAGE)

    seen_numbers: set[int] = set()
    tasks: list[PlanTaskDefinition] = []
    previous_slice_id: str | None = None
    for match in matches:
        task_number = int(match.group("number"))
        if task_number in seen_numbers:
            message = f"plan task number must be unique: {task_number}"
            raise PlanTaskParseError(message)
        seen_numbers.add(task_number)

        task_id = f"task-{task_number}"
        dependencies = () if previous_slice_id is None else (previous_slice_id,)
        slice_definition = PlanSliceDefinition(slice_id=task_id, dependencies=dependencies)
        tasks.append(PlanTaskDefinition(task_id=task_id, slices=(slice_definition,)))
        previous_slice_id = task_id

    return tuple(tasks)
