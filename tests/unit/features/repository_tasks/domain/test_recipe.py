"""Tests for repository task recipe contracts and registry policy."""

from __future__ import annotations

import pytest

from cline_sdlc.features.repository_tasks.application.dtos.recipe import RecipeDefinitionDTO
from cline_sdlc.features.repository_tasks.domain.policy import (
    BUILT_IN_RECIPE_REGISTRY,
    CONVENTIONAL_COMMIT_STAGED_RECIPE_ID,
    get_builtin_recipe,
)
from cline_sdlc.features.repository_tasks.domain.recipe import (
    ACCEPTED_SPECIFICATION_DIGEST,
    HookPoint,
    InvocationMode,
    PrimitiveCategory,
    RecipeKind,
    parse_hook_point,
    parse_invocation_mode,
    parse_primitive_category,
    parse_recipe_id,
)


def test_builtin_conventional_commit_staged_recipe_is_registered() -> None:
    recipe = get_builtin_recipe(CONVENTIONAL_COMMIT_STAGED_RECIPE_ID)

    assert recipe.recipe_id == CONVENTIONAL_COMMIT_STAGED_RECIPE_ID
    assert recipe.kind is RecipeKind.CONVENTIONAL_COMMIT_STAGED
    assert recipe.allowed_invocation_modes == (InvocationMode.STANDALONE,)
    assert recipe.deferred_hook_points == (HookPoint.BEFORE_SLICE_COMMIT,)
    assert recipe.accepted_specification_digest == ACCEPTED_SPECIFICATION_DIGEST
    assert recipe.has_state_changes is True
    assert {CONVENTIONAL_COMMIT_STAGED_RECIPE_ID: recipe} == BUILT_IN_RECIPE_REGISTRY


def test_builtin_recipe_uses_only_closed_mvp_primitive_categories_in_order() -> None:
    recipe = get_builtin_recipe(CONVENTIONAL_COMMIT_STAGED_RECIPE_ID)

    assert tuple(step.category for step in recipe.steps) == (
        PrimitiveCategory.GIT_INSPECTION,
        PrimitiveCategory.SKILL_PROPOSAL,
        PrimitiveCategory.VALIDATION,
        PrimitiveCategory.APPROVAL,
        PrimitiveCategory.GIT_MUTATION,
        PrimitiveCategory.EVIDENCE,
    )
    assert tuple(category.value for category in PrimitiveCategory) == (
        "skill_proposal",
        "git_inspection",
        "validation",
        "approval",
        "git_mutation",
        "evidence",
    )


def test_recipe_definition_is_static_linear_and_does_not_model_workflow_control() -> None:
    recipe = get_builtin_recipe(CONVENTIONAL_COMMIT_STAGED_RECIPE_ID)

    assert all(step.order == index for index, step in enumerate(recipe.steps, start=1))
    assert all(step.is_static for step in recipe.steps)
    assert all(not step.repository_configurable for step in recipe.steps)
    assert not hasattr(recipe, "branches")
    assert not hasattr(recipe, "loops")
    assert not hasattr(recipe, "commands")
    assert not hasattr(recipe, "imports")
    assert not hasattr(recipe, "prompts")


@pytest.mark.parametrize(
    ("parser", "value"),
    [
        (parse_recipe_id, "unknown-recipe"),
        (parse_hook_point, "after_artifact_written"),
        (parse_primitive_category, "shell_command"),
        (parse_invocation_mode, "embedded"),
    ],
)
def test_unknown_recipe_policy_values_fail_closed(parser: object, value: str) -> None:
    with pytest.raises(ValueError, match=r"unsupported|unknown"):
        parser(value)  # type: ignore[operator]


def test_recipe_dto_preserves_safe_serialization_shape() -> None:
    recipe = get_builtin_recipe(CONVENTIONAL_COMMIT_STAGED_RECIPE_ID)

    dto = RecipeDefinitionDTO.from_domain(recipe)

    assert dto.recipe_id == "conventional-commit-staged"
    assert dto.kind == "conventional_commit_staged"
    assert dto.allowed_invocation_modes == ("standalone",)
    assert dto.deferred_hook_points == ("before_slice_commit",)
    assert dto.step_categories == (
        "git_inspection",
        "skill_proposal",
        "validation",
        "approval",
        "git_mutation",
        "evidence",
    )
    assert dto.state_changing_step_categories == ("git_mutation",)
