"""Repository task recipe domain contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

ACCEPTED_SPECIFICATION_DIGEST = "sha256:2d57219c951290dd6f80947f3e31b7d8927523455edf616e545c85a25713bfbc"


class RecipeKind(StrEnum):
    """Known orchestrator-owned repository task recipe kinds."""

    CONVENTIONAL_COMMIT_STAGED = "conventional_commit_staged"


class InvocationMode(StrEnum):
    """Implemented repository task invocation modes for the standalone-first slice."""

    STANDALONE = "standalone"


class HookPoint(StrEnum):
    """Known deferred lifecycle hook points for recipe metadata."""

    BEFORE_SLICE_COMMIT = "before_slice_commit"


class PrimitiveCategory(StrEnum):
    """Closed MVP primitive taxonomy for repository task recipes."""

    SKILL_PROPOSAL = "skill_proposal"
    GIT_INSPECTION = "git_inspection"
    VALIDATION = "validation"
    APPROVAL = "approval"
    GIT_MUTATION = "git_mutation"
    EVIDENCE = "evidence"


@dataclass(frozen=True)
class RecipeStep:
    """One static linear recipe step owned by orchestrator code."""

    order: int
    category: PrimitiveCategory
    operation_name: str
    read_only: bool
    repository_configurable: bool = False

    def __post_init__(self) -> None:
        if self.order < 1:
            message = "recipe step order must be positive"
            raise ValueError(message)
        if not self.operation_name.strip():
            message = "recipe step operation_name must not be empty"
            raise ValueError(message)
        if self.repository_configurable:
            message = "recipe steps must not be repository configurable"
            raise ValueError(message)

    @property
    def is_static(self) -> bool:
        """Return whether the step is a static orchestrator-owned contract step."""
        return not self.repository_configurable

    @property
    def state_changing(self) -> bool:
        """Return whether this step can mutate repository state."""
        return not self.read_only


@dataclass(frozen=True)
class RecipeDefinition:
    """Static, linear definition for an orchestrator-owned repository task recipe."""

    recipe_id: str
    kind: RecipeKind
    allowed_invocation_modes: tuple[InvocationMode, ...]
    deferred_hook_points: tuple[HookPoint, ...]
    steps: tuple[RecipeStep, ...]
    accepted_specification_digest: str
    required_preconditions: tuple[str, ...] = field(default_factory=tuple)
    completion_evidence_requirements: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.recipe_id.strip():
            message = "recipe_id must not be empty"
            raise ValueError(message)
        if not self.allowed_invocation_modes:
            message = "recipe must declare at least one allowed invocation mode"
            raise ValueError(message)
        if not self.steps:
            message = "recipe must declare at least one step"
            raise ValueError(message)
        expected_orders = tuple(range(1, len(self.steps) + 1))
        actual_orders = tuple(step.order for step in self.steps)
        if actual_orders != expected_orders:
            message = "recipe steps must be static and linear with contiguous ordering"
            raise ValueError(message)
        if any(step.repository_configurable for step in self.steps):
            message = "recipe topology must be orchestrator-owned and static"
            raise ValueError(message)
        if any(not requirement.strip() for requirement in self.required_preconditions):
            message = "recipe preconditions must not contain empty values"
            raise ValueError(message)
        if any(not requirement.strip() for requirement in self.completion_evidence_requirements):
            message = "recipe evidence requirements must not contain empty values"
            raise ValueError(message)
        if self.accepted_specification_digest != ACCEPTED_SPECIFICATION_DIGEST:
            message = "recipe accepted specification digest is unsupported"
            raise ValueError(message)

    @property
    def has_state_changes(self) -> bool:
        """Return whether any recipe step can mutate repository state."""
        return any(step.state_changing for step in self.steps)


def parse_recipe_id(value: str) -> str:
    """Parse a known recipe id, failing closed for unknown identifiers."""
    if value == "conventional-commit-staged":
        return value
    message = f"unknown recipe id: {value}"
    raise ValueError(message)


def parse_invocation_mode(value: str) -> InvocationMode:
    """Parse an implemented invocation mode, failing closed for unknown modes."""
    try:
        return InvocationMode(value)
    except ValueError as err:
        message = f"unsupported invocation mode: {value}"
        raise ValueError(message) from err


def parse_hook_point(value: str) -> HookPoint:
    """Parse a known deferred hook point, failing closed for unknown hooks."""
    try:
        return HookPoint(value)
    except ValueError as err:
        message = f"unsupported hook point: {value}"
        raise ValueError(message) from err


def parse_primitive_category(value: str) -> PrimitiveCategory:
    """Parse a primitive category from the closed MVP taxonomy."""
    try:
        return PrimitiveCategory(value)
    except ValueError as err:
        message = f"unsupported primitive category: {value}"
        raise ValueError(message) from err
