"""Filesystem adapter for progress-only initial plan-review updates."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from ruamel.yaml import YAML

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import (
    STATE_BLOCK_PATTERN,
    parse_plan_state_from_markdown,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.plan_review import PlanReviewProgressResult
from cline_sdlc.features.artifact_lifecycle.application.use_cases.apply_initial_plan_review import (
    apply_initial_plan_review,
)
from cline_sdlc.features.artifact_lifecycle.domain.digests import PlanMaterialDigestInput, compute_plan_material_digest
from cline_sdlc.features.artifact_lifecycle.domain.findings import Finding, FindingSet
from cline_sdlc.features.artifact_lifecycle.domain.regions import (
    PROGRESS_END_MARKER,
    PROGRESS_START_MARKER,
    parse_plan_regions,
)

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.dtos.plan_review import PlanReviewProgressRequest
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState

_FINDINGS_HEADING = "### Plan-review findings"


@dataclass(frozen=True)
class FilesystemPlanReviewProgressWriter:
    """Persist validated review evidence while preserving all material content."""

    repository_root: Path

    def execute(self, request: PlanReviewProgressRequest) -> PlanReviewProgressResult:
        """Apply one initial review result to the selected plan."""
        try:
            plan_path = self._resolve(request.plan_path)
            original = plan_path.read_text(encoding="utf-8", errors="strict")
            original_state = parse_plan_state_from_markdown(original)
            original_material = parse_plan_regions(_normalize(original)).material_content
            updated_state = apply_initial_plan_review(
                original_state,
                findings=FindingSet(request.findings),
                readiness=request.readiness,
                updated_at=request.updated_at,
            )
            updated = _updated_markdown(original, request.findings, updated_state)
            _validate_material_content(updated, expected=original_material)
            material_digest = compute_plan_material_digest(
                PlanMaterialDigestInput(
                    plan_markdown=updated.encode(),
                    plan_revision=updated_state.plan_revision,
                    specification=updated_state.specification,
                    specification_digest=updated_state.specification_digest,
                    digest_schema_version=updated_state.digest_schema_version,
                )
            )
            _validate_material_digest(material_digest, expected=original_state.material_digest)
            _validate_updated_document(updated, expected_state=updated_state)
            _atomic_write(plan_path, updated)
        except (OSError, UnicodeError, ValueError) as err:
            return PlanReviewProgressResult(
                updated=False,
                plan_path=request.plan_path,
                blockers=(str(err),),
            )
        return PlanReviewProgressResult(
            updated=True,
            plan_path=request.plan_path,
            plan_state=updated_state,
            material_digest=material_digest,
        )

    def _resolve(self, repository_path: str) -> Path:
        root = self.repository_root.resolve(strict=True)
        candidate = (root / repository_path).resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            message = "plan review path must be a regular file inside the repository"
            raise ValueError(message)
        return candidate


def _updated_markdown(markdown: str, findings: tuple[Finding, ...], state: PlanState) -> str:
    progress_start = markdown.index(PROGRESS_START_MARKER) + len(PROGRESS_START_MARKER)
    progress_end = markdown.index(PROGRESS_END_MARKER, progress_start)
    state_match = STATE_BLOCK_PATTERN.search(markdown)
    if state_match is None:
        message = "plan must contain one state block before review progress can be applied"
        raise ValueError(message)
    if not (progress_start <= state_match.start() < state_match.end() <= progress_end):
        message = "plan state block must be inside the progress region"
        raise ValueError(message)
    findings_start = markdown.find(_FINDINGS_HEADING, progress_start, progress_end)
    if findings_start > state_match.start():
        message = "plan-review findings must precede the state block"
        raise ValueError(message)
    prefix_end = findings_start if findings_start >= 0 else state_match.start()
    prefix = markdown[:prefix_end].rstrip()
    suffix = markdown[state_match.end() :]
    findings_section = _render_findings(findings)
    state_block = f"```cline-sdlc-state\n{_render_state(state)}```"
    return f"{prefix}\n\n{findings_section}\n\n{state_block}{suffix}"


def _render_findings(findings: tuple[Finding, ...]) -> str:
    lines = [_FINDINGS_HEADING, ""]
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines)
    for finding in findings:
        lines.extend(
            (
                f"- id: {_quoted(finding.id)}",
                f"  severity: {finding.severity.value}",
                f"  status: {finding.status.value}",
                f"  summary: {_quoted(finding.summary)}",
                f"  evidence: {_quoted(finding.evidence)}",
                f"  required_correction: {_quoted(finding.required_correction)}",
                "  affected_sections:",
            )
        )
        lines.extend(f"    - {_quoted(section)}" for section in finding.affected_sections)
        disposition = "null" if finding.disposition is None else _quoted(finding.disposition)
        lines.append(f"  disposition: {disposition}")
    return "\n".join(lines)


def _render_state(state: PlanState) -> str:
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    stream = StringIO()
    yaml.dump(_state_mapping(state), stream)
    return stream.getvalue()


def _state_mapping(state: PlanState) -> dict[str, object]:
    return {
        "schema_version": state.schema_version,
        "work_id": state.work_id,
        "profile": state.profile.value,
        "phase": state.phase.value,
        "specification": state.specification,
        "specification_digest": state.specification_digest,
        "plan_revision": state.plan_revision,
        "review_iteration": state.review_iteration,
        "review_readiness": state.review_readiness.value,
        "digest_schema_version": state.digest_schema_version,
        "material_digest": state.material_digest,
        "current_task": state.current_task,
        "current_slice": state.current_slice,
        "slice_start_commit": state.slice_start_commit,
        "partial_slice_paths": list(state.partial_slice_paths),
        "completed_slices": list(state.completed_slices),
        "remediation_records": list(state.remediation_records),
        "validation_evidence": [
            {
                "slice_id": item.slice_id,
                "command": item.command,
                "result": item.result,
                "exit_code": item.exit_code,
                "recorded_at": item.recorded_at.isoformat().replace("+00:00", "Z"),
            }
            for item in state.validation_evidence
        ],
        "blocker": None if state.blocker is None else {"code": state.blocker.code, "summary": state.blocker.summary},
        "created_at": state.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": state.updated_at.isoformat().replace("+00:00", "Z"),
        "completed_at": None if state.completed_at is None else state.completed_at.isoformat().replace("+00:00", "Z"),
    }


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _validate_material_content(markdown: str, *, expected: str) -> None:
    if parse_plan_regions(_normalize(markdown)).material_content != expected:
        message = "initial review update changed plan material content"
        raise ValueError(message)


def _validate_material_digest(observed: str, *, expected: str) -> None:
    if observed != expected:
        message = "initial review update changed the plan material digest"
        raise ValueError(message)


def _validate_updated_document(markdown: str, *, expected_state: PlanState) -> None:
    parse_plan_regions(_normalize(markdown))
    if parse_plan_state_from_markdown(markdown) != expected_state:
        message = "initial review update produced unexpected plan state"
        raise ValueError(message)


def _atomic_write(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(path.stat().st_mode)
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
