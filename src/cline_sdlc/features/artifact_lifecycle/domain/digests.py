"""Deterministic artifact digest calculation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cline_sdlc.features.artifact_lifecycle.domain.plan_state import DIGEST_SCHEMA_VERSION
from cline_sdlc.features.artifact_lifecycle.domain.regions import parse_plan_regions


@dataclass(frozen=True)
class PlanMaterialDigestInput:
    """Inputs that define canonical plan material digest payload version 1."""

    plan_markdown: bytes
    plan_revision: int
    specification: str
    specification_digest: str
    digest_schema_version: int = DIGEST_SCHEMA_VERSION


def compute_specification_digest(specification_content: bytes) -> str:
    """Compute the version-1 digest for accepted specification bytes."""
    canonical_text = _decode_and_normalize_text(specification_content)
    return _format_sha256(canonical_text.encode("utf-8"))


def compute_plan_material_digest(digest_input: PlanMaterialDigestInput) -> str:
    """Compute the version-1 digest for canonical implementation-plan material."""
    if digest_input.digest_schema_version != DIGEST_SCHEMA_VERSION:
        message = "unsupported material digest schema version"
        raise ValueError(message)
    if digest_input.plan_revision < 1:
        message = "plan_revision must be a positive integer"
        raise ValueError(message)

    markdown = _decode_and_normalize_text(digest_input.plan_markdown)
    regions = parse_plan_regions(markdown)
    payload = {
        "digest_schema_version": digest_input.digest_schema_version,
        "material_content": regions.material_content,
        "plan_revision": digest_input.plan_revision,
        "specification": digest_input.specification,
        "specification_digest": digest_input.specification_digest,
    }
    canonical_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return _format_sha256(canonical_payload.encode("utf-8"))


def _decode_and_normalize_text(content: bytes) -> str:
    text = content.decode("utf-8", errors="strict")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _format_sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
