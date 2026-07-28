"""DTOs for repository task recipe definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.repository_tasks.domain.recipe import RecipeDefinition


@dataclass(frozen=True)
class RecipeDefinitionDTO:
    """Serialization-friendly view of a static repository task recipe."""

    recipe_id: str
    kind: str
    allowed_invocation_modes: tuple[str, ...]
    deferred_hook_points: tuple[str, ...]
    step_categories: tuple[str, ...]
    state_changing_step_categories: tuple[str, ...]
    accepted_specification_digest: str

    def __post_init__(self) -> None:
        if not self.recipe_id.strip():
            message = "recipe DTO recipe_id must not be empty"
            raise ValueError(message)
        if not self.kind.strip():
            message = "recipe DTO kind must not be empty"
            raise ValueError(message)
        if not self.allowed_invocation_modes:
            message = "recipe DTO must include at least one invocation mode"
            raise ValueError(message)
        if not self.step_categories:
            message = "recipe DTO must include at least one step category"
            raise ValueError(message)
        if not self.accepted_specification_digest.strip():
            message = "recipe DTO accepted specification digest must not be empty"
            raise ValueError(message)

    @classmethod
    def from_domain(cls, recipe: RecipeDefinition) -> RecipeDefinitionDTO:
        """Create a DTO from a domain recipe definition."""
        return cls(
            recipe_id=recipe.recipe_id,
            kind=recipe.kind.value,
            allowed_invocation_modes=tuple(mode.value for mode in recipe.allowed_invocation_modes),
            deferred_hook_points=tuple(hook.value for hook in recipe.deferred_hook_points),
            step_categories=tuple(step.category.value for step in recipe.steps),
            state_changing_step_categories=tuple(step.category.value for step in recipe.steps if step.state_changing),
            accepted_specification_digest=recipe.accepted_specification_digest,
        )
