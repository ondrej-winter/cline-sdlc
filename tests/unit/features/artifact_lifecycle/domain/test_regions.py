"""Tests for implementation-plan material and progress region parsing."""

import pytest

from cline_sdlc.features.artifact_lifecycle.domain.regions import PlanRegionKind, parse_plan_regions


def valid_plan(*, progress: str = "## Progress\n") -> str:
    return (
        "# Plan\n\n"
        "<!-- cline-sdlc-material:start -->\n"
        "## Objective\n\nShip the slice.\n"
        "<!-- cline-sdlc-material:end -->\n\n"
        "<!-- cline-sdlc-progress:start -->\n"
        f"{progress}"
        "<!-- cline-sdlc-progress:end -->\n"
    )


def test_parses_material_and_progress_regions() -> None:
    regions = parse_plan_regions(valid_plan())

    assert len(regions.material) == 1
    assert regions.material[0].kind is PlanRegionKind.MATERIAL
    assert regions.material_content == "## Objective\n\nShip the slice."
    assert regions.progress.body == "## Progress"


def test_concatenates_multiple_material_regions_with_one_lf() -> None:
    markdown = (
        "# Plan\n\n"
        "<!-- cline-sdlc-material:start -->\n"
        "one\n"
        "<!-- cline-sdlc-material:end -->\n"
        "<!-- cline-sdlc-material:start -->\n"
        "two\n"
        "<!-- cline-sdlc-material:end -->\n"
        "<!-- cline-sdlc-progress:start -->\n"
        "state\n"
        "<!-- cline-sdlc-progress:end -->\n"
    )

    regions = parse_plan_regions(markdown)

    assert regions.material_content == "one\ntwo"


@pytest.mark.parametrize(
    ("markdown", "match"),
    [
        ("# Plan\n\n<!-- cline-sdlc-progress:start -->\nstate\n<!-- cline-sdlc-progress:end -->\n", "material"),
        ("# Plan\n\n<!-- cline-sdlc-material:start -->\nbody\n<!-- cline-sdlc-material:end -->\n", "progress"),
        (valid_plan() + "after\n", "outside"),
        ("# Plan\n\nOutside\n" + valid_plan(), "document title"),
    ],
)
def test_rejects_missing_regions_and_outside_content(markdown: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_plan_regions(markdown)


@pytest.mark.parametrize(
    ("markdown", "match"),
    [
        (
            "# Plan\n\n"
            "<!-- cline-sdlc-material:start -->\n"
            "<!-- cline-sdlc-progress:start -->\n"
            "nested\n"
            "<!-- cline-sdlc-progress:end -->\n"
            "<!-- cline-sdlc-material:end -->\n",
            "overlap|nest",
        ),
        (
            "# Plan\n\n<!-- cline-sdlc-material:start -->\nbody\n<!-- cline-sdlc-progress:end -->\n",
            "does not match",
        ),
        (
            "# Plan\n\n"
            "<!-- cline-sdlc-material:end -->\n"
            "<!-- cline-sdlc-progress:start -->\n"
            "state\n"
            "<!-- cline-sdlc-progress:end -->\n",
            "before a matching start",
        ),
        (
            "# Plan\n\n<!-- cline-sdlc-material:start -->\nbody\n",
            "missing its end",
        ),
    ],
)
def test_rejects_nested_overlapping_and_unmatched_regions(markdown: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_plan_regions(markdown)
