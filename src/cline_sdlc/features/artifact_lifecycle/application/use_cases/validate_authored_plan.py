"""Validate an initially authored implementation plan without performing I/O."""

from __future__ import annotations

import re

from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanBlocker,
    AuthoredPlanValidationRequest,
    AuthoredPlanValidationResult,
)
from cline_sdlc.features.artifact_lifecycle.application.use_cases.apply_plan_revision import validate_plan_revision
from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase, ReviewReadiness
from cline_sdlc.features.artifact_lifecycle.domain.regions import parse_plan_regions

_REQUIRED_SECTION_GROUPS = (
    ("objective",),
    ("scope",),
    ("non-goals", "non goals"),
    ("repository context", "context and constraints", "repository context and constraints"),
    ("decisions", "material decisions", "decisions and risks", "material decisions and risks"),
    ("tasks", "implementation tasks", "implementation slices", "tasks and slices"),
    ("verification", "validation"),
)
_HEADING_PATTERN = re.compile(r"^#{2,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)


class ValidateAuthoredPlan:
    """Verify plan structure, initial state, specification identity, and digests."""

    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        """Return fail-closed validation evidence for one authored plan."""
        try:
            markdown = request.plan_content.decode("utf-8", errors="strict")
            parse_plan_regions(markdown.replace("\r\n", "\n").replace("\r", "\n"))
            state = request.plan_state
            _validate_state(request)
            _validate_required_sections(markdown)
            _validate_specification_identity(request.specification_path, state.specification)
            specification_digest = compute_specification_digest(request.specification_content)
            _validate_digest(
                expected=specification_digest,
                observed=state.specification_digest,
                message="stored specification digest does not match the accepted specification",
            )
            material_digest = compute_plan_material_digest(
                PlanMaterialDigestInput(
                    plan_markdown=request.plan_content,
                    plan_revision=state.plan_revision,
                    specification=state.specification,
                    specification_digest=state.specification_digest,
                    digest_schema_version=state.digest_schema_version,
                )
            )
            _validate_digest(
                expected=material_digest,
                observed=state.material_digest,
                message="stored material digest does not match authored plan material",
            )
        except (UnicodeDecodeError, ValueError) as err:
            return AuthoredPlanValidationResult(
                valid=False,
                plan_path=request.plan_path,
                blockers=(
                    AuthoredPlanBlocker(
                        code="invalid_authored_plan",
                        summary="authored plan failed structural or digest validation",
                        evidence=str(err),
                    ),
                ),
            )
        return AuthoredPlanValidationResult(
            valid=True,
            plan_path=request.plan_path,
            specification_digest=specification_digest,
            material_digest=material_digest,
        )


def _validate_initial_state(phase: PlanPhase, readiness: ReviewReadiness) -> None:
    if phase is not PlanPhase.DRAFTING or readiness is not ReviewReadiness.NOT_REVIEWED:
        message = "initial authored plan must be drafting and not_reviewed"
        raise ValueError(message)


def _validate_state(request: AuthoredPlanValidationRequest) -> None:
    if request.previous_plan_state is None:
        _validate_initial_state(request.plan_state.phase, request.plan_state.review_readiness)
        return
    validate_plan_revision(request.previous_plan_state, request.plan_state)


def _validate_required_sections(markdown: str) -> None:
    headings = {match.group("title").strip().lower() for match in _HEADING_PATTERN.finditer(markdown)}
    missing = tuple(
        group[0] for group in _REQUIRED_SECTION_GROUPS if not any(candidate in headings for candidate in group)
    )
    if missing:
        message = f"authored plan is missing required sections: {', '.join(missing)}"
        raise ValueError(message)


def _validate_specification_identity(expected: str, observed: str) -> None:
    if observed != expected:
        message = "plan state specification path does not match the accepted specification"
        raise ValueError(message)


def _validate_digest(*, expected: str, observed: str, message: str) -> None:
    if observed != expected:
        raise ValueError(message)
