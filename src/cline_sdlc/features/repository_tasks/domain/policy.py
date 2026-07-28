"""Built-in repository task recipe registry policy."""

from __future__ import annotations

from types import MappingProxyType

from cline_sdlc.features.repository_tasks.domain.recipe import (
    ACCEPTED_SPECIFICATION_DIGEST,
    HookPoint,
    InvocationMode,
    PrimitiveCategory,
    RecipeDefinition,
    RecipeKind,
    RecipeStep,
    parse_recipe_id,
)

CONVENTIONAL_COMMIT_STAGED_RECIPE_ID = "conventional-commit-staged"

CONVENTIONAL_COMMIT_STAGED_RECIPE = RecipeDefinition(
    recipe_id=CONVENTIONAL_COMMIT_STAGED_RECIPE_ID,
    kind=RecipeKind.CONVENTIONAL_COMMIT_STAGED,
    allowed_invocation_modes=(InvocationMode.STANDALONE,),
    deferred_hook_points=(HookPoint.BEFORE_SLICE_COMMIT,),
    required_preconditions=(
        "inside_git_repository",
        "staged_changes_present",
        "standalone_explicit_approval_before_mutation",
    ),
    steps=(
        RecipeStep(
            order=1,
            category=PrimitiveCategory.GIT_INSPECTION,
            operation_name="inspect_staged_repository_state",
            read_only=True,
        ),
        RecipeStep(
            order=2,
            category=PrimitiveCategory.SKILL_PROPOSAL,
            operation_name="propose_conventional_commit_message",
            read_only=True,
        ),
        RecipeStep(
            order=3,
            category=PrimitiveCategory.VALIDATION,
            operation_name="validate_conventional_commit_message",
            read_only=True,
        ),
        RecipeStep(
            order=4,
            category=PrimitiveCategory.APPROVAL,
            operation_name="capture_standalone_user_approval",
            read_only=True,
        ),
        RecipeStep(
            order=5,
            category=PrimitiveCategory.GIT_MUTATION,
            operation_name="create_authorized_staged_commit",
            read_only=False,
        ),
        RecipeStep(
            order=6,
            category=PrimitiveCategory.EVIDENCE,
            operation_name="record_recipe_completion_evidence",
            read_only=True,
        ),
    ),
    completion_evidence_requirements=(
        "recipe_id",
        "mode",
        "status",
        "staged_paths",
        "skill_used",
        "commit_message_validation_result",
        "accepted_commit_message_or_blocker",
        "commit_hash_when_created",
    ),
    accepted_specification_digest=ACCEPTED_SPECIFICATION_DIGEST,
)

BUILT_IN_RECIPE_REGISTRY = MappingProxyType(
    {
        CONVENTIONAL_COMMIT_STAGED_RECIPE_ID: CONVENTIONAL_COMMIT_STAGED_RECIPE,
    }
)


def get_builtin_recipe(recipe_id: str) -> RecipeDefinition:
    """Return a built-in recipe definition or fail closed for unknown recipes."""
    known_recipe_id = parse_recipe_id(recipe_id)
    return BUILT_IN_RECIPE_REGISTRY[known_recipe_id]
