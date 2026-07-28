"""Tests for structured terminal outcome parsing."""

import json

from cline_sdlc.features.artifact_lifecycle.domain.findings import PlanReviewReadiness
from cline_sdlc.features.cline_execution.adapters.outbound.terminal_outcome_parser import parse_terminal_outcomes


def test_parses_complete_plan_reviewer_findings() -> None:
    payload = {
        "schema_version": 1,
        "session_role": "plan_reviewer",
        "status": "completed",
        "reason": "changes_required",
        "artifact_paths": ["docs/plans/example.md"],
        "changed_paths": [],
        "validation": [],
        "findings": [
            {
                "id": "PLAN-001",
                "severity": "major",
                "status": "open",
                "summary": "Validation scope is incomplete.",
                "evidence": "The plan omits the broad quality gate.",
                "required_correction": "Add the broad quality gate.",
                "affected_sections": ["Verification"],
                "disposition": None,
            }
        ],
        "finding_ids": ["PLAN-001"],
        "review_readiness": "changes_required",
        "blocker": None,
        "retryable": False,
    }

    parsed = parse_terminal_outcomes(json.dumps(payload))

    assert not parsed.malformed_lines
    assert parsed.outcomes[0].findings[0].id == "PLAN-001"
    assert parsed.outcomes[0].review_readiness is PlanReviewReadiness.CHANGES_REQUIRED
