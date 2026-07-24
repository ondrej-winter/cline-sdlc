"""Lifecycle stage selection rules for explicit invocation inputs."""

from enum import StrEnum


class StageInputKind(StrEnum):
    """Supported explicit input forms for one invocation."""

    IDEA = "idea"
    IDEA_FILE = "idea_file"
    SPEC_FILE = "spec_file"
    PLAN_FILE = "plan_file"


class LifecycleStage(StrEnum):
    """Major lifecycle stages selected by invocation input."""

    IDEA_REFINEMENT = "idea_refinement"
    SPECIFICATION_CREATION = "specification_creation"
    PLAN_CREATION_AND_REVIEW = "plan_creation_and_review"
    PLAN_IMPLEMENTATION = "plan_implementation"


def stage_for_input_kind(input_kind: StageInputKind) -> LifecycleStage:
    """Return the lifecycle stage selected by an explicit input kind."""
    return {
        StageInputKind.IDEA: LifecycleStage.IDEA_REFINEMENT,
        StageInputKind.IDEA_FILE: LifecycleStage.SPECIFICATION_CREATION,
        StageInputKind.SPEC_FILE: LifecycleStage.PLAN_CREATION_AND_REVIEW,
        StageInputKind.PLAN_FILE: LifecycleStage.PLAN_IMPLEMENTATION,
    }[input_kind]
