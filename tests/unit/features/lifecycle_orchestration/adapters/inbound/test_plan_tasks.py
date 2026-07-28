"""Tests for extracting implementation task metadata from markdown plans."""

from pathlib import Path

import pytest

from cline_sdlc.features.lifecycle_orchestration.adapters.inbound.plan_tasks import (
    PlanTaskParseError,
    parse_plan_task_definitions,
)

EXPECTED_REPOSITORY_PLAN_TASKS = 13


def test_extracts_repository_plan_task_list() -> None:
    plan = Path("docs/plans/configurable-lifecycle-hooks-and-repository-task-plan.md").read_text(encoding="utf-8")

    tasks = parse_plan_task_definitions(plan)

    assert len(tasks) == EXPECTED_REPOSITORY_PLAN_TASKS
    assert tasks[0].task_id == "task-1"
    assert tasks[-1].task_id == "task-13"
    assert tasks[-1].slices[0].dependencies == ("task-12",)


def test_extracts_linear_task_slice_definitions_from_markdown_headings() -> None:
    tasks = parse_plan_task_definitions(
        """# Implementation Plan

## Task 1: Add repository task recipe domain model and built-in registry

Details.

## Task 2: Add deterministic Conventional Commit validation

Details.

## Task 13: Run full local quality gate and package build

Details.
"""
    )

    assert [task.task_id for task in tasks] == ["task-1", "task-2", "task-13"]
    assert [task.slices[0].slice_id for task in tasks] == ["task-1", "task-2", "task-13"]
    assert tasks[0].slices[0].dependencies == ()
    assert tasks[1].slices[0].dependencies == ("task-1",)
    assert tasks[2].slices[0].dependencies == ("task-2",)


def test_rejects_plan_without_supported_task_headings() -> None:
    with pytest.raises(PlanTaskParseError, match="at least one"):
        parse_plan_task_definitions("# Plan\n\n## Task 1\n\nMissing colon heading.")


def test_rejects_duplicate_task_numbers() -> None:
    with pytest.raises(PlanTaskParseError, match="unique: 1"):
        parse_plan_task_definitions("## Task 1: First\n\n## Task 1: Duplicate\n")
