"""DTOs for selecting managed lifecycle artifact locations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactKind(StrEnum):
    """Lifecycle artifact kinds with portable default directories."""

    IDEA_BRIEF = "idea_brief"
    SPECIFICATION = "specification"
    PLAN = "plan"


class ArtifactLocationSource(StrEnum):
    """Reason a managed artifact location was selected."""

    EXPLICIT = "explicit"
    HOST_CONVENTION = "host_convention"
    PORTABLE_DEFAULT = "portable_default"


@dataclass(frozen=True)
class ArtifactLocationConvention:
    """Already-discovered host convention candidate for one artifact kind."""

    kind: ArtifactKind
    directory: str
    is_safe: bool = True
    reason: str = "host convention"


@dataclass(frozen=True)
class SelectArtifactLocationRequest:
    """Application request for one managed artifact output location."""

    artifact_kind: ArtifactKind
    artifact_stem: str
    explicit_path: str | None = None


@dataclass(frozen=True)
class ArtifactLocationResult:
    """Selected normalized repository-relative artifact path."""

    artifact_kind: ArtifactKind
    path: str
    directory: str
    source: ArtifactLocationSource


@dataclass(frozen=True)
class ArtifactLocationBlocker:
    """Actionable artifact-location selection failure."""

    code: str
    summary: str
