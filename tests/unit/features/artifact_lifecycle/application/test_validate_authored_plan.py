"""Tests for initial authored-plan validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import parse_plan_state_from_markdown
from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import AuthoredPlanValidationRequest
from cline_sdlc.features.artifact_lifecycle.application.use_cases.validate_authored_plan import ValidateAuthoredPlan
from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)

SPECIFICATION_PATH = "docs/specs/example-spec.md"
PLAN_PATH = "docs/plans/example-plan.md"
SPECIFICATION_CONTENT = b"# Accepted specification\n"
PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"


def test_validates_initial_authored_plan() -> None:
    result = ValidateAuthoredPlan().execute(_request())

    assert result.valid
    assert result.specification_digest == compute_specification_digest(SPECIFICATION_CONTENT)
    assert result.material_digest is not None
    assert result.blockers == ()


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("phase: drafting", "phase: reviewing", "drafting and not_reviewed"),
        ("## Verification", "## Evidence", "missing required sections"),
        (f"specification: {SPECIFICATION_PATH}", "specification: docs/specs/other.md", "does not match"),
        ("# Accepted specification", "# Changed specification", "stored specification digest"),
    ],
)
def test_rejects_invalid_authored_plan(old: str, new: str, expected: str) -> None:
    request = _request()
    plan_content = request.plan_content.replace(old.encode(), new.encode())
    specification_content = (
        SPECIFICATION_CONTENT.replace(old.encode(), new.encode())
        if old == "# Accepted specification"
        else SPECIFICATION_CONTENT
    )

    result = ValidateAuthoredPlan().execute(
        AuthoredPlanValidationRequest(
            specification_path=SPECIFICATION_PATH,
            specification_content=specification_content,
            plan_path=PLAN_PATH,
            plan_content=plan_content,
            plan_state=parse_plan_state_from_markdown(plan_content.decode()),
        )
    )

    assert not result.valid
    assert result.blockers[0].code == "invalid_authored_plan"
    assert result.blockers[0].evidence is not None
    assert expected in result.blockers[0].evidence


def test_rejects_stale_material_digest() -> None:
    request = _request()
    changed = request.plan_content.replace(b"Ordered slice 1.", b"Materially changed slice 1.")

    result = ValidateAuthoredPlan().execute(
        AuthoredPlanValidationRequest(
            specification_path=SPECIFICATION_PATH,
            specification_content=SPECIFICATION_CONTENT,
            plan_path=PLAN_PATH,
            plan_content=changed,
            plan_state=request.plan_state,
        )
    )

    assert not result.valid
    assert result.blockers[0].evidence == "stored material digest does not match authored plan material"


def _request() -> AuthoredPlanValidationRequest:
    content = _plan_content(PLACEHOLDER_DIGEST)
    material_digest = compute_plan_material_digest(
        PlanMaterialDigestInput(
            plan_markdown=content,
            plan_revision=1,
            specification=SPECIFICATION_PATH,
            specification_digest=compute_specification_digest(SPECIFICATION_CONTENT),
        )
    )
    return AuthoredPlanValidationRequest(
        specification_path=SPECIFICATION_PATH,
        specification_content=SPECIFICATION_CONTENT,
        plan_path=PLAN_PATH,
        plan_content=_plan_content(material_digest),
        plan_state=parse_plan_state_from_markdown(_plan_content(material_digest).decode()),
    )


def _plan_content(material_digest: str) -> bytes:
    specification_digest = compute_specification_digest(SPECIFICATION_CONTENT)
    timestamp = datetime(2026, 7, 24, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    return f"""# Example plan

<!-- cline-sdlc-material:start -->
## Objective
Deliver the accepted specification.

## Scope
Implement the bounded capability.

## Non-goals
Do not expand scope.

## Repository context and constraints
Follow repository rules.

## Material decisions and risks
Keep boundaries explicit.

## Tasks and slices
Ordered slice 1.

## Verification
Run focused and broad checks.
<!-- cline-sdlc-material:end -->

<!-- cline-sdlc-progress:start -->
```cline-sdlc-state
schema_version: 1
work_id: example-work
profile: balanced
phase: drafting
specification: {SPECIFICATION_PATH}
specification_digest: {specification_digest}
plan_revision: 1
review_iteration: 1
review_readiness: not_reviewed
digest_schema_version: 1
material_digest: {material_digest}
current_task: null
current_slice: null
slice_start_commit: null
partial_slice_paths: []
completed_slices: []
remediation_records: []
validation_evidence: []
blocker: null
created_at: {timestamp}
updated_at: {timestamp}
completed_at: null
```
<!-- cline-sdlc-progress:end -->
""".encode()
