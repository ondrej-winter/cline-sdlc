"""Pure redaction helpers for persisted run audit summaries."""

from __future__ import annotations

import re
from dataclasses import dataclass

SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?P<key>api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>[^\s,;]+)"
)
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
REDACTION_MARKER = "<redacted>"


@dataclass(frozen=True)
class RedactionPolicy:
    """Allowlisted redaction policy for summary text and explicit sensitive fragments."""

    sensitive_fragments: tuple[str, ...] = ()

    def redact(self, text: str) -> str:
        """Return text with known sensitive assignments and explicit fragments removed."""
        redacted = BEARER_PATTERN.sub(f"Bearer {REDACTION_MARKER}", text)
        redacted = SENSITIVE_ASSIGNMENT_PATTERN.sub(_redact_assignment, redacted)
        for fragment in self.sensitive_fragments:
            if fragment:
                redacted = redacted.replace(fragment, REDACTION_MARKER)
        return redacted


def _redact_assignment(match: re.Match[str]) -> str:
    return f"{match.group('key')}{match.group('separator')}{REDACTION_MARKER}"
