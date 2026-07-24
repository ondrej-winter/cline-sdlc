"""DTOs for public lifecycle invocation terminal results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage
    from cline_sdlc.features.lifecycle_orchestration.domain.terminal_result import TerminalStatus


TERMINAL_RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TerminalBlocker:
    """Actionable blocker or diagnostic attached to a terminal result."""

    code: str
    summary: str

    def to_payload(self) -> dict[str, str]:
        """Return the JSON-compatible blocker payload."""
        return {"code": self.code, "summary": self.summary}


@dataclass(frozen=True)
class TerminalResult:
    """Public terminal result for one bounded lifecycle invocation."""

    status: TerminalStatus
    reason: str
    stage: LifecycleStage | None = None
    input_path: str | None = None
    output_paths: Sequence[str] = field(default_factory=tuple)
    specification_digest: str | None = None
    plan_material_digest: str | None = None
    blocker: TerminalBlocker | None = None

    def to_payload(self) -> dict[str, object]:
        """Return the stable schema-versioned JSON-compatible payload."""
        return {
            "schema_version": TERMINAL_RESULT_SCHEMA_VERSION,
            "status": self.status.value,
            "stage": self.stage.value if self.stage is not None else None,
            "reason": self.reason,
            "input_path": self.input_path,
            "output_paths": list(self.output_paths),
            "specification_digest": self.specification_digest,
            "plan_material_digest": self.plan_material_digest,
            "blocker": self.blocker.to_payload() if self.blocker is not None else None,
        }
