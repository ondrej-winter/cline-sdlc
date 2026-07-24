"""Tests for deterministic artifact digest calculation."""

import pytest

from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)

SPEC_DIGEST = "sha256:" + "a" * 64
SHA256_FORMATTED_LENGTH = 71


def plan_bytes(
    *, material: str = "## Objective\n\nShip the slice.", progress: str = "## Progress\n- [ ] Task"
) -> bytes:
    return (
        "# Plan\n\n"
        "<!-- cline-sdlc-material:start -->\n"
        f"{material}\n"
        "<!-- cline-sdlc-material:end -->\n\n"
        "<!-- cline-sdlc-progress:start -->\n"
        f"{progress}\n"
        "<!-- cline-sdlc-progress:end -->\n"
    ).encode()


def material_digest(
    *,
    plan_markdown: bytes | None = None,
    plan_revision: int = 1,
    specification: str = "docs/specs/example.md",
    specification_digest: str = SPEC_DIGEST,
    digest_schema_version: int = 1,
) -> str:
    return compute_plan_material_digest(
        PlanMaterialDigestInput(
            plan_markdown=plan_markdown or plan_bytes(),
            plan_revision=plan_revision,
            specification=specification,
            specification_digest=specification_digest,
            digest_schema_version=digest_schema_version,
        )
    )


def test_specification_digest_normalizes_supported_line_endings() -> None:
    lf_digest = compute_specification_digest(b"# Spec\nLine\n")

    assert compute_specification_digest(b"# Spec\r\nLine\r\n") == lf_digest
    assert compute_specification_digest(b"# Spec\rLine\r") == lf_digest
    assert lf_digest.startswith("sha256:")
    assert len(lf_digest) == SHA256_FORMATTED_LENGTH


def test_specification_digest_rejects_invalid_utf8() -> None:
    with pytest.raises(UnicodeDecodeError):
        compute_specification_digest(b"\xff")


def test_progress_only_edits_preserve_material_digest() -> None:
    original = material_digest()

    changed_progress = material_digest(plan_markdown=plan_bytes(progress="## Progress\n- [x] Task\nupdated_at: now"))

    assert changed_progress == original


def test_material_digest_changes_for_material_whitespace() -> None:
    assert material_digest(plan_markdown=plan_bytes(material="## Objective\n\nShip the slice. ")) != material_digest()


def test_material_digest_changes_for_material_text() -> None:
    changed_digest = material_digest(plan_markdown=plan_bytes(material="## Objective\n\nShip a different slice."))

    assert changed_digest != material_digest()


def test_material_digest_changes_for_revision() -> None:
    assert material_digest(plan_revision=2) != material_digest()


def test_material_digest_changes_for_specification_identity() -> None:
    assert material_digest(specification="docs/specs/other.md") != material_digest()


def test_material_digest_changes_for_specification_digest() -> None:
    assert material_digest(specification_digest="sha256:" + "b" * 64) != material_digest()


def test_material_digest_normalizes_plan_line_endings() -> None:
    lf_digest = material_digest()

    crlf_plan = plan_bytes().decode().replace("\n", "\r\n").encode()
    cr_plan = plan_bytes().decode().replace("\n", "\r").encode()

    assert material_digest(plan_markdown=crlf_plan) == lf_digest
    assert material_digest(plan_markdown=cr_plan) == lf_digest


def test_material_digest_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError, match="schema version"):
        material_digest(digest_schema_version=2)
