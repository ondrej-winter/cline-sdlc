"""Strict artifact adapter for plan-reconciliation evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import (
    StrictStateYAMLError,
    parse_plan_state_from_markdown,
)
from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase
from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import (
    PlanArtifactEvidence,
    PlanArtifactInspection,
)

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState

_SPECIFICATION_REFERENCE_PATTERN = re.compile(r"`(?P<path>docs/specs/[^`]+\.md)`")


class StrictPlanArtifactInspector:
    """Parse plan evidence from embedded state or plain accepted plan content."""

    def inspect(self, plan_content: bytes, specification_content: bytes) -> PlanArtifactInspection:
        """Return normalized evidence, optionally verifying specification bytes."""
        try:
            state, material_digest = _validated_state(plan_content, specification_content)
        except StrictStateYAMLError as err:
            if str(err) != "plan must contain exactly one cline-sdlc-state block":
                return PlanArtifactInspection(error=str(err))
            try:
                return _legacy_inspection(plan_content, specification_content)
            except (UnicodeDecodeError, ValueError) as legacy_err:
                return PlanArtifactInspection(error=str(legacy_err))
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


def _legacy_inspection(plan_content: bytes, specification_content: bytes) -> PlanArtifactInspection:
    markdown = plan_content.decode("utf-8", errors="strict")
    specification_path = _legacy_specification_path(markdown)
    specification_digest = compute_specification_digest(specification_content)
    material_digest = _legacy_material_digest(
        plan_markdown=markdown,
        specification=specification_path,
        specification_digest=specification_digest,
    )
    now = datetime.now(UTC)
    return PlanArtifactInspection(
        evidence=PlanArtifactEvidence(
            work_id=_legacy_work_id(markdown),
            specification_path=specification_path,
            specification_digest=specification_digest,
            material_digest=material_digest,
            phase=PlanPhase.READY,
            completed_slice_ids=(),
            current_task=None,
            current_slice=None,
            slice_start_commit=None,
            partial_slice_paths=(),
            remediation_records=(),
            validation_evidence=(),
            blocker=None,
            updated_at=now,
            completed_at=None,
        )
    )


def _legacy_specification_path(markdown: str) -> str:
    matches = tuple(_SPECIFICATION_REFERENCE_PATTERN.finditer(markdown))
    if not matches:
        message = "plain plan must reference an accepted specification under docs/specs"
        raise ValueError(message)
    return matches[0].group("path")


def _legacy_work_id(markdown: str) -> str:
    title = next((line.removeprefix("# ").strip() for line in markdown.splitlines() if line.startswith("# ")), "")
    words = re.findall(r"[a-z0-9]+", title.lower())
    if not words:
        message = "plain plan title must contain a stable work id"
        raise ValueError(message)
    return "-".join(words[:8])


def _legacy_material_digest(*, plan_markdown: str, specification: str, specification_digest: str) -> str:
    normalized = plan_markdown.replace("\r\n", "\n").replace("\r", "\n")
    payload = json.dumps(
        {
            "legacy_plan_markdown": normalized,
            "plan_revision": 1,
            "specification": specification,
            "specification_digest": specification_digest,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
