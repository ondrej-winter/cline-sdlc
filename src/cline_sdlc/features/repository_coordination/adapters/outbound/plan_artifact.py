"""Strict artifact adapter for plan-reconciliation evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import parse_plan_state_from_markdown
from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import (
    PlanArtifactEvidence,
    PlanArtifactInspection,
)

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState


class StrictPlanArtifactInspector:
    """Parse strict plan state and independently recompute stored digests."""

    def inspect(self, plan_content: bytes, specification_content: bytes) -> PlanArtifactInspection:
        """Return normalized evidence, optionally verifying specification bytes."""
        try:
            state, material_digest = _validated_state(plan_content, specification_content)
        except (UnicodeDecodeError, ValueError) as err:
            return PlanArtifactInspection(error=str(err))
        return PlanArtifactInspection(
            evidence=PlanArtifactEvidence(
                work_id=state.work_id,
                specification_path=state.specification,
                specification_digest=state.specification_digest,
                material_digest=material_digest,
                phase=state.phase,
                completed_slice_ids=state.completed_slices,
                current_task=state.current_task,
                current_slice=state.current_slice,
                slice_start_commit=state.slice_start_commit,
                partial_slice_paths=state.partial_slice_paths,
                remediation_records=state.remediation_records,
                validation_evidence=state.validation_evidence,
                blocker=state.blocker,
                updated_at=state.updated_at,
                completed_at=state.completed_at,
            )
        )


def _validated_state(plan_content: bytes, specification_content: bytes) -> tuple[PlanState, str]:
    markdown = plan_content.decode("utf-8", errors="strict")
    state = parse_plan_state_from_markdown(markdown)
    if specification_content and compute_specification_digest(specification_content) != state.specification_digest:
        message = "stored specification digest does not match specification content"
        raise ValueError(message)
    material_digest = compute_plan_material_digest(
        PlanMaterialDigestInput(
            plan_markdown=plan_content,
            plan_revision=state.plan_revision,
            specification=state.specification,
            specification_digest=state.specification_digest,
            digest_schema_version=state.digest_schema_version,
        )
    )
    if material_digest != state.material_digest:
        message = "stored material digest does not match plan content"
        raise ValueError(message)
    return state, material_digest
