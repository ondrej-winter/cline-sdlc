"""Filesystem adapter for authored-plan validation content."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import parse_plan_state_from_markdown
from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanInspectionRequest,
    AuthoredPlanValidationRequest,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class FilesystemAuthoredPlanContentReader:
    """Read selected artifacts beneath one repository root for validation."""

    repository_root: Path

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        """Return strict artifact content and parsed plan state."""
        specification_path = self._resolve(request.specification_path)
        plan_path = self._resolve(request.plan_path)
        specification_content = specification_path.read_bytes()
        plan_content = plan_path.read_bytes()
        plan_markdown = plan_content.decode("utf-8", errors="strict")
        return AuthoredPlanValidationRequest(
            specification_path=request.specification_path,
            specification_content=specification_content,
            plan_path=request.plan_path,
            plan_content=plan_content,
            plan_state=parse_plan_state_from_markdown(plan_markdown),
        )

    def _resolve(self, repository_path: str) -> Path:
        root = self.repository_root.resolve(strict=True)
        candidate = (root / repository_path).resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            message = "authored-plan content paths must be regular files inside the repository"
            raise ValueError(message)
        return candidate
