"""Tests for run audit redaction policies."""

from __future__ import annotations

from cline_sdlc.features.run_audit.domain.redaction import REDACTION_MARKER, RedactionPolicy


def test_redacts_sensitive_assignments_and_bearer_tokens() -> None:
    text = "token=abc123 password:super-secret Authorization=Bearer xyz api_key=key-1 status=blocked"

    redacted = RedactionPolicy().redact(text)

    assert "abc123" not in redacted
    assert "super-secret" not in redacted
    assert "xyz" not in redacted
    assert "key-1" not in redacted
    assert f"token={REDACTION_MARKER}" in redacted
    assert "status=blocked" in redacted


def test_redacts_explicit_sensitive_fragments_without_removing_safe_context() -> None:
    redacted = RedactionPolicy(sensitive_fragments=("private prompt",)).redact(
        "session failed after private prompt in docs/spec.md"
    )

    assert redacted == f"session failed after {REDACTION_MARKER} in docs/spec.md"
