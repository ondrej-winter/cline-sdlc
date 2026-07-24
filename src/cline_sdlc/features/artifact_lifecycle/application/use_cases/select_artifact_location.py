"""Use case for selecting portable managed artifact output locations."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationBlocker,
    ArtifactLocationConvention,
    ArtifactLocationResult,
    ArtifactLocationSource,
    SelectArtifactLocationRequest,
)

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.ports.artifact_conventions import ArtifactConventionProvider

_DEFAULT_DIRECTORIES = {
    ArtifactKind.IDEA_BRIEF: "docs/ideas",
    ArtifactKind.SPECIFICATION: "docs/specs",
    ArtifactKind.PLAN: "docs/plans",
}
_ARTIFACT_SUFFIXES = {
    ArtifactKind.IDEA_BRIEF: "idea",
    ArtifactKind.SPECIFICATION: "spec",
    ArtifactKind.PLAN: "plan",
}
_SAFE_STEM_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class SelectArtifactLocation:
    """Select a safe repository-relative location for a lifecycle artifact."""

    def __init__(self, convention_provider: ArtifactConventionProvider | None = None) -> None:
        self._convention_provider = convention_provider

    def execute(self, request: SelectArtifactLocationRequest) -> ArtifactLocationResult | ArtifactLocationBlocker:
        """Return the selected location or a blocker before any artifact write."""
        stem = _safe_artifact_stem(request.artifact_stem)
        if stem is None:
            return ArtifactLocationBlocker(
                code="unsafe_artifact_stem",
                summary="artifact_stem must be lowercase letters, digits, dots, underscores, or hyphens",
            )

        if request.explicit_path is not None:
            return _explicit_result(request=request, stem=stem)

        conventions = self._convention_provider.discover_conventions() if self._convention_provider is not None else ()
        convention = _selected_convention(request.artifact_kind, conventions)
        if isinstance(convention, ArtifactLocationBlocker):
            return convention
        if convention is not None:
            return _directory_result(
                artifact_kind=request.artifact_kind,
                directory=convention.directory,
                stem=stem,
                source=ArtifactLocationSource.HOST_CONVENTION,
            )

        return _directory_result(
            artifact_kind=request.artifact_kind,
            directory=_DEFAULT_DIRECTORIES[request.artifact_kind],
            stem=stem,
            source=ArtifactLocationSource.PORTABLE_DEFAULT,
        )


def _explicit_result(
    *,
    request: SelectArtifactLocationRequest,
    stem: str,
) -> ArtifactLocationResult | ArtifactLocationBlocker:
    path = _normalized_repository_path(request.explicit_path or "")
    if path is None:
        return ArtifactLocationBlocker(
            code="unsafe_artifact_path",
            summary="explicit artifact path must be a safe repository-relative POSIX path",
        )
    if path.endswith("/"):
        return _directory_result(
            artifact_kind=request.artifact_kind,
            directory=path.rstrip("/"),
            stem=stem,
            source=ArtifactLocationSource.EXPLICIT,
        )
    return ArtifactLocationResult(
        artifact_kind=request.artifact_kind,
        path=path,
        directory=PurePosixPath(path).parent.as_posix(),
        source=ArtifactLocationSource.EXPLICIT,
    )


def _selected_convention(
    artifact_kind: ArtifactKind,
    conventions: tuple[ArtifactLocationConvention, ...],
) -> ArtifactLocationConvention | ArtifactLocationBlocker | None:
    matching = tuple(convention for convention in conventions if convention.kind is artifact_kind)
    unsafe = tuple(convention for convention in matching if not convention.is_safe)
    if unsafe:
        return ArtifactLocationBlocker(
            code="unsafe_artifact_convention",
            summary=f"artifact convention is unsafe: {unsafe[0].reason}",
        )
    normalized = tuple((convention, _normalized_repository_path(convention.directory)) for convention in matching)
    invalid = tuple(convention for convention, path in normalized if path is None)
    if invalid:
        return ArtifactLocationBlocker(
            code="unsafe_artifact_convention",
            summary=f"artifact convention path is unsafe: {invalid[0].reason}",
        )
    directories = {path.rstrip("/") for _convention, path in normalized if path is not None}
    if len(directories) > 1:
        return ArtifactLocationBlocker(
            code="ambiguous_artifact_convention",
            summary="multiple artifact conventions match this artifact kind",
        )
    if not normalized:
        return None
    convention, path = normalized[0]
    return ArtifactLocationConvention(
        kind=convention.kind,
        directory=(path or "").rstrip("/"),
        reason=convention.reason,
    )


def _directory_result(
    *,
    artifact_kind: ArtifactKind,
    directory: str,
    stem: str,
    source: ArtifactLocationSource,
) -> ArtifactLocationResult | ArtifactLocationBlocker:
    normalized_directory = _normalized_repository_path(directory)
    if normalized_directory is None:
        return ArtifactLocationBlocker(
            code="unsafe_artifact_path",
            summary="artifact directory must be a safe repository-relative POSIX path",
        )
    directory_path = normalized_directory.rstrip("/")
    artifact_name = f"{stem}-{_ARTIFACT_SUFFIXES[artifact_kind]}.md"
    return ArtifactLocationResult(
        artifact_kind=artifact_kind,
        path=f"{directory_path}/{artifact_name}",
        directory=directory_path,
        source=source,
    )


def _safe_artifact_stem(raw_stem: str) -> str | None:
    stem = raw_stem.strip().lower().replace(" ", "-")
    if _SAFE_STEM_PATTERN.fullmatch(stem) is None:
        return None
    return stem


def _normalized_repository_path(raw_path: str) -> str | None:
    if not raw_path.strip() or raw_path.startswith("/") or "\\" in raw_path or "//" in raw_path:
        return None
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    if raw_path.endswith("/"):
        return f"{path.as_posix()}/"
    return path.as_posix()
