"""Tests for managed artifact location selection."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationBlocker,
    ArtifactLocationConvention,
    ArtifactLocationResult,
    ArtifactLocationSource,
    SelectArtifactLocationRequest,
)
from cline_sdlc.features.artifact_lifecycle.application.use_cases.select_artifact_location import SelectArtifactLocation


@dataclass(frozen=True)
class FakeConventionProvider:
    conventions: tuple[ArtifactLocationConvention, ...]

    def discover_conventions(self) -> tuple[ArtifactLocationConvention, ...]:
        return self.conventions


def select_location(
    *,
    artifact_kind: ArtifactKind = ArtifactKind.PLAN,
    artifact_stem: str = "cline-sdlc-orchestrator",
    explicit_path: str | None = None,
    conventions: tuple[ArtifactLocationConvention, ...] = (),
) -> ArtifactLocationResult | ArtifactLocationBlocker:
    return SelectArtifactLocation(FakeConventionProvider(conventions)).execute(
        SelectArtifactLocationRequest(
            artifact_kind=artifact_kind,
            artifact_stem=artifact_stem,
            explicit_path=explicit_path,
        )
    )


@pytest.mark.parametrize(
    ("artifact_kind", "expected_path"),
    [
        (ArtifactKind.IDEA_BRIEF, "docs/ideas/example-idea.md"),
        (ArtifactKind.SPECIFICATION, "docs/specs/example-spec.md"),
        (ArtifactKind.PLAN, "docs/plans/example-plan.md"),
    ],
)
def test_selects_portable_default_for_each_artifact_kind(
    artifact_kind: ArtifactKind,
    expected_path: str,
) -> None:
    result = select_location(artifact_kind=artifact_kind, artifact_stem="Example")

    assert isinstance(result, ArtifactLocationResult)
    assert result.path == expected_path
    assert result.source is ArtifactLocationSource.PORTABLE_DEFAULT


def test_explicit_file_path_takes_precedence_over_convention() -> None:
    result = select_location(
        explicit_path="project/plans/custom.md",
        conventions=(ArtifactLocationConvention(kind=ArtifactKind.PLAN, directory="docs/host-plans"),),
    )

    assert isinstance(result, ArtifactLocationResult)
    assert result.path == "project/plans/custom.md"
    assert result.directory == "project/plans"
    assert result.source is ArtifactLocationSource.EXPLICIT


def test_explicit_directory_path_takes_precedence_and_uses_default_filename() -> None:
    result = select_location(explicit_path="project/plans/")

    assert isinstance(result, ArtifactLocationResult)
    assert result.path == "project/plans/cline-sdlc-orchestrator-plan.md"
    assert result.source is ArtifactLocationSource.EXPLICIT


def test_safe_host_convention_takes_precedence_over_portable_default() -> None:
    result = select_location(
        conventions=(ArtifactLocationConvention(kind=ArtifactKind.PLAN, directory="project/docs/plans"),),
    )

    assert isinstance(result, ArtifactLocationResult)
    assert result.path == "project/docs/plans/cline-sdlc-orchestrator-plan.md"
    assert result.source is ArtifactLocationSource.HOST_CONVENTION


def test_conventions_for_other_artifact_kinds_are_ignored() -> None:
    result = select_location(
        conventions=(ArtifactLocationConvention(kind=ArtifactKind.SPECIFICATION, directory="project/specs"),),
    )

    assert isinstance(result, ArtifactLocationResult)
    assert result.path == "docs/plans/cline-sdlc-orchestrator-plan.md"
    assert result.source is ArtifactLocationSource.PORTABLE_DEFAULT


@pytest.mark.parametrize("explicit_path", ["../plan.md", "/absolute/plan.md", "docs\\plans\\plan.md", "docs//plans"])
def test_rejects_unsafe_explicit_paths(explicit_path: str) -> None:
    result = select_location(explicit_path=explicit_path)

    assert isinstance(result, ArtifactLocationBlocker)
    assert result.code == "unsafe_artifact_path"


def test_rejects_ambiguous_host_conventions() -> None:
    result = select_location(
        conventions=(
            ArtifactLocationConvention(kind=ArtifactKind.PLAN, directory="docs/plans"),
            ArtifactLocationConvention(kind=ArtifactKind.PLAN, directory="project/plans"),
        ),
    )

    assert isinstance(result, ArtifactLocationBlocker)
    assert result.code == "ambiguous_artifact_convention"


def test_rejects_unsafe_host_conventions() -> None:
    result = select_location(
        conventions=(
            ArtifactLocationConvention(
                kind=ArtifactKind.PLAN,
                directory="docs/plans",
                is_safe=False,
                reason="symlink escape",
            ),
        ),
    )

    assert isinstance(result, ArtifactLocationBlocker)
    assert result.code == "unsafe_artifact_convention"
    assert "symlink escape" in result.summary


@pytest.mark.parametrize("artifact_stem", ["", "../plan", "Project: Plan"])
def test_rejects_unsafe_artifact_stems(artifact_stem: str) -> None:
    result = select_location(artifact_stem=artifact_stem)

    assert isinstance(result, ArtifactLocationBlocker)
    assert result.code == "unsafe_artifact_stem"
