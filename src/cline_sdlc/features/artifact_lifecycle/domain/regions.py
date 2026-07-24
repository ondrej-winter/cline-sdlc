"""Implementation-plan material and progress region parsing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MATERIAL_START_MARKER = "<!-- cline-sdlc-material:start -->"
MATERIAL_END_MARKER = "<!-- cline-sdlc-material:end -->"
PROGRESS_START_MARKER = "<!-- cline-sdlc-progress:start -->"
PROGRESS_END_MARKER = "<!-- cline-sdlc-progress:end -->"


class PlanRegionKind(StrEnum):
    """Supported implementation-plan region kinds."""

    MATERIAL = "material"
    PROGRESS = "progress"


@dataclass(frozen=True)
class PlanRegion:
    """A validated non-nesting implementation-plan region."""

    kind: PlanRegionKind
    body: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class PlanRegions:
    """Parsed material and progress regions in document order."""

    material: tuple[PlanRegion, ...]
    progress: PlanRegion

    @property
    def material_content(self) -> str:
        """Return canonical material-region content in document order."""
        return "\n".join(region.body for region in self.material)


@dataclass
class _RegionParseState:
    regions: list[PlanRegion]
    active_kind: PlanRegionKind | None = None
    active_start_line: int = 0
    active_body_lines: list[str] | None = None
    seen_region: bool = False


def parse_plan_regions(markdown: str) -> PlanRegions:
    """Parse strict material/progress regions from normalized Markdown text."""
    lines = _split_preserving_line_content(markdown)
    _validate_title_prefix(lines)
    state = _RegionParseState(regions=[])

    for line_number, line in enumerate(lines, start=1):
        _parse_region_line(state, line=line, line_number=line_number)

    if state.active_kind is not None:
        message = "plan region start marker is missing its end marker"
        raise ValueError(message)

    material_regions = tuple(region for region in state.regions if region.kind is PlanRegionKind.MATERIAL)
    progress_regions = tuple(region for region in state.regions if region.kind is PlanRegionKind.PROGRESS)
    if not material_regions:
        message = "plan must contain at least one material region"
        raise ValueError(message)
    if len(progress_regions) != 1:
        message = "plan must contain exactly one progress region"
        raise ValueError(message)
    return PlanRegions(material=material_regions, progress=progress_regions[0])


def _parse_region_line(state: _RegionParseState, *, line: str, line_number: int) -> None:
    marker = _marker_for_line(line)
    if marker is None:
        _parse_non_marker_line(state, line=line)
        return

    marker_kind, is_start = marker
    if is_start:
        _start_region(state, marker_kind=marker_kind, line_number=line_number)
        return
    _end_region(state, marker_kind=marker_kind, line_number=line_number)


def _parse_non_marker_line(state: _RegionParseState, *, line: str) -> None:
    if state.active_kind is None:
        if state.seen_region and line.strip():
            message = "non-blank content outside plan regions is not allowed"
            raise ValueError(message)
        return
    if state.active_body_lines is None:
        message = "active region body was not initialized"
        raise ValueError(message)
    state.active_body_lines.append(line)


def _start_region(state: _RegionParseState, *, marker_kind: PlanRegionKind, line_number: int) -> None:
    if state.active_kind is not None:
        message = "plan regions must not overlap or nest"
        raise ValueError(message)
    state.active_kind = marker_kind
    state.active_start_line = line_number
    state.active_body_lines = []
    state.seen_region = True


def _end_region(state: _RegionParseState, *, marker_kind: PlanRegionKind, line_number: int) -> None:
    if state.active_kind is None:
        message = "plan region end marker appeared before a matching start marker"
        raise ValueError(message)
    if marker_kind is not state.active_kind:
        message = "plan region end marker does not match the active region"
        raise ValueError(message)
    if state.active_body_lines is None:
        message = "active region body was not initialized"
        raise ValueError(message)
    state.regions.append(
        PlanRegion(
            kind=state.active_kind,
            body="\n".join(state.active_body_lines),
            start_line=state.active_start_line,
            end_line=line_number,
        )
    )
    state.active_kind = None
    state.active_body_lines = None


def _split_preserving_line_content(markdown: str) -> list[str]:
    return markdown.split("\n")


def _validate_title_prefix(lines: list[str]) -> None:
    title_seen = False
    for line in lines:
        if _marker_for_line(line) is not None:
            return
        if not line.strip():
            continue
        if not title_seen and line.startswith("# "):
            title_seen = True
            continue
        message = "non-blank content after the document title must be inside a plan region"
        raise ValueError(message)


def _marker_for_line(line: str) -> tuple[PlanRegionKind, bool] | None:
    stripped = line.strip()
    if stripped == MATERIAL_START_MARKER:
        return PlanRegionKind.MATERIAL, True
    if stripped == MATERIAL_END_MARKER:
        return PlanRegionKind.MATERIAL, False
    if stripped == PROGRESS_START_MARKER:
        return PlanRegionKind.PROGRESS, True
    if stripped == PROGRESS_END_MARKER:
        return PlanRegionKind.PROGRESS, False
    return None
