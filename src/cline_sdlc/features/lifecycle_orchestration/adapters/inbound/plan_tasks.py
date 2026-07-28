"""Parse implementation-plan task headings into slice-selection definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PlanSliceDefinition,
    PlanTaskDefinition,
)

_TASK_HEADING_PATTERN = re.compile(r"^## Task (?P<number>[1-9][0-9]*): (?P<title>\S.*)$", re.MULTILINE)
_LIKELY_FILES_HEADING = "**Likely files/components touched:**"
_NEXT_SECTION_PATTERN = re.compile(r"^##\s+", re.MULTILINE)
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
    for index, match in enumerate(matches):
        task_number = int(match.group("number"))
        if task_number in seen_numbers:
            message = f"plan task number must be unique: {task_number}"
            raise PlanTaskParseError(message)
        seen_numbers.add(task_number)

        task_id = f"task-{task_number}"
        dependencies = () if previous_slice_id is None else (previous_slice_id,)
        task_body_end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        expected_paths = _task_expected_paths(markdown[match.end() : task_body_end])
        slice_definition = PlanSliceDefinition(
            slice_id=task_id,
            dependencies=dependencies,
            expected_paths=expected_paths,
        )
        tasks.append(PlanTaskDefinition(task_id=task_id, slices=(slice_definition,)))
        previous_slice_id = task_id

    return tuple(tasks)


def _task_expected_paths(task_body: str) -> tuple[str, ...]:
    heading_index = task_body.find(_LIKELY_FILES_HEADING)
    if heading_index < 0:
        return ()
    section = task_body[heading_index + len(_LIKELY_FILES_HEADING) :]
    next_section = _NEXT_SECTION_PATTERN.search(section)
    if next_section is not None:
        section = section[: next_section.start()]

    paths: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- `") or "`" not in stripped[3:]:
            continue
        raw_path = stripped[3:].split("`", maxsplit=1)[0]
        normalized = _normalized_repository_path(raw_path)
        if normalized is not None:
            paths.append(normalized)
    return tuple(dict.fromkeys(paths))


def _normalized_repository_path(raw_path: str) -> str | None:
    if not raw_path.strip() or raw_path.startswith(("/", "../")) or "\\" in raw_path:
        return None
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()
