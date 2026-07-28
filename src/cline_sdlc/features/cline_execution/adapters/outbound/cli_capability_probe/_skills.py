"""Private required-skill probing helpers for the Cline CLI probe adapter."""

import re
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    CapabilityObservation,
    CapabilityStatus,
)

from ._subprocess import run

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

_ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def skill_observations(
    command: Sequence[str], required_skills: tuple[str, ...], repository_root: Path | None
) -> tuple[CapabilityObservation, ...]:
    """Return critical observations for required skill availability."""
    if not required_skills:
        return ()

    skill_result = run((*command, "skill", "list"))
    skill_text = skill_result.stdout + skill_result.stderr
    available_skills = _available_skill_names(skill_text)

    return tuple(
        CapabilityObservation(
            name=f"required_skill:{skill}",
            status=_skill_status(skill_result.returncode, skill, available_skills, repository_root),
            criticality=CapabilityCriticality.CRITICAL,
            evidence=_skill_evidence(skill_result.returncode, skill, repository_root),
        )
        for skill in required_skills
    )


def _skill_status(
    return_code: int, skill: str, available_skills: frozenset[str], repository_root: Path | None
) -> CapabilityStatus:
    if return_code != 0:
        if _local_skill_exists(repository_root, skill):
            return CapabilityStatus.PROVEN
        return CapabilityStatus.UNPROVEN
    if skill in available_skills:
        return CapabilityStatus.PROVEN
    if _local_skill_exists(repository_root, skill):
        return CapabilityStatus.PROVEN
    return CapabilityStatus.MISSING


def _available_skill_names(skill_text: str) -> frozenset[str]:
    skill_names: set[str] = set()
    for line in skill_text.splitlines():
        stripped = _strip_ansi_escape_sequences(line).strip()
        if not stripped or stripped in {"Project Skills", "Global Skills"} or stripped.startswith("Agents:"):
            continue
        skill_names.add(stripped.split(maxsplit=1)[0])
    return frozenset(skill_names)


def _strip_ansi_escape_sequences(text: str) -> str:
    return _ANSI_ESCAPE_PATTERN.sub("", text)


def _skill_evidence(return_code: int, skill: str, repository_root: Path | None) -> str:
    if _local_skill_exists(repository_root, skill):
        return f"Repository-local skill file was found for required skill {skill!r}."
    if return_code != 0:
        return "Skill list command did not complete successfully; availability is unproven."
    return f"Skill list output was inspected for required skill {skill!r}."


def _local_skill_exists(repository_root: Path | None, skill: str) -> bool:
    if repository_root is None or not _is_safe_skill_name(skill):
        return False

    root = repository_root.resolve()
    skills_root = root / ".agents" / "skills"
    skill_file = skills_root / skill / "SKILL.md"
    try:
        skill_file.resolve(strict=True).relative_to(skills_root.resolve(strict=False))
    except OSError, ValueError:
        return False
    return skill_file.is_file()


def _is_safe_skill_name(skill: str) -> bool:
    return bool(skill) and "/" not in skill and "\\" not in skill and skill not in {".", ".."}
