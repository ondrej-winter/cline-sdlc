"""Deterministic Conventional Commit message validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

ALLOWED_CONVENTIONAL_COMMIT_TYPES = frozenset(("build", "chore", "docs", "feat", "fix", "refactor", "test"))
BODY_START_INDEX = 2
CONTROL_CHARACTER_ORDINAL_LIMIT = 32
_SUBJECT_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9._-]+)\))?(?P<breaking>!)?: (?P<description>\S.*)$"
)
_STANDARD_FOOTER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]*(?:-[A-Za-z0-9-]+)*: \S.*$")
_BREAKING_CHANGE_PATTERN = re.compile(r"^BREAKING CHANGE: \S.*$")
_CLINE_SDLC_TRAILER_PATTERN = re.compile(r"^Cline-SDLC-[A-Za-z0-9-]+: \S.*$")


class CommitMessageValidationCode(StrEnum):
    """Machine-readable Conventional Commit validation outcomes."""

    VALID = "valid"
    EMPTY_MESSAGE = "empty_message"
    UNSAFE_CONTROL_CHARACTER = "unsafe_control_character"
    MISSING_CONVENTIONAL_SUBJECT = "missing_conventional_subject"
    UNSUPPORTED_TYPE = "unsupported_type"
    INVALID_MULTILINE_SPACING = "invalid_multiline_spacing"
    INVALID_FOOTER = "invalid_footer"


@dataclass(frozen=True)
class ConventionalCommitValidationResult:
    """Result of deterministic commit-message validation."""

    valid: bool
    code: CommitMessageValidationCode
    summary: str
    normalized_message: str | None = None
    commit_type: str | None = None
    scope: str | None = None
    breaking_change: bool = False
    footers: tuple[str, ...] = field(default_factory=tuple)


def validate_conventional_commit_message(message: str) -> ConventionalCommitValidationResult:
    """Validate a Conventional Commit message for non-interactive Git commit use."""
    normalized_message = _normalize_message(message)
    if not normalized_message:
        result = _invalid(CommitMessageValidationCode.EMPTY_MESSAGE, "commit message must not be empty")
    elif _has_unsafe_control_character(normalized_message):
        result = _invalid(
            CommitMessageValidationCode.UNSAFE_CONTROL_CHARACTER,
            "commit message must not contain unsafe control characters",
        )
    else:
        result = _validate_safe_message(normalized_message)
    return result


def _validate_safe_message(normalized_message: str) -> ConventionalCommitValidationResult:
    lines = normalized_message.split("\n")
    subject_match = _SUBJECT_PATTERN.fullmatch(lines[0])
    if subject_match is None:
        result = _invalid(
            CommitMessageValidationCode.MISSING_CONVENTIONAL_SUBJECT,
            "commit message subject must use Conventional Commit syntax",
        )
    else:
        result = _validate_subject_match(normalized_message, lines, subject_match)
    return result


def _validate_subject_match(
    normalized_message: str,
    lines: list[str],
    subject_match: re.Match[str],
) -> ConventionalCommitValidationResult:
    commit_type = subject_match.group("type")
    if commit_type not in ALLOWED_CONVENTIONAL_COMMIT_TYPES:
        result = _invalid(
            CommitMessageValidationCode.UNSUPPORTED_TYPE,
            f"unsupported Conventional Commit type: {commit_type}",
        )
    elif len(lines) > 1 and lines[1] != "":
        result = _invalid(
            CommitMessageValidationCode.INVALID_MULTILINE_SPACING,
            "multiline commit messages require a blank line after the subject",
        )
    else:
        result = _validate_body_and_footers(normalized_message, lines, subject_match, commit_type)
    return result


def _validate_body_and_footers(
    normalized_message: str,
    lines: list[str],
    subject_match: re.Match[str],
    commit_type: str,
) -> ConventionalCommitValidationResult:
    footer_result = _collect_footers(lines[BODY_START_INDEX:]) if len(lines) > BODY_START_INDEX else ()
    if footer_result is None:
        result = _invalid(
            CommitMessageValidationCode.INVALID_FOOTER,
            "footer-like lines must use supported Conventional Commit trailer syntax",
        )
    else:
        result = _valid(normalized_message, subject_match, commit_type, footer_result)
    return result


def _valid(
    normalized_message: str,
    subject_match: re.Match[str],
    commit_type: str,
    footers: tuple[str, ...],
) -> ConventionalCommitValidationResult:
    has_breaking_footer = any(_BREAKING_CHANGE_PATTERN.fullmatch(footer) for footer in footers)
    return ConventionalCommitValidationResult(
        valid=True,
        code=CommitMessageValidationCode.VALID,
        summary="commit message is valid",
        normalized_message=normalized_message,
        commit_type=commit_type,
        scope=subject_match.group("scope"),
        breaking_change=subject_match.group("breaking") is not None or has_breaking_footer,
        footers=footers,
    )


def _normalize_message(message: str) -> str:
    return message.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _has_unsafe_control_character(message: str) -> bool:
    return any(ord(character) < CONTROL_CHARACTER_ORDINAL_LIMIT and character != "\n" for character in message)


def _collect_footers(lines: list[str]) -> tuple[str, ...] | None:
    footers: list[str] = []
    in_footer_block = False
    for line in lines:
        if not line:
            continue
        if _is_supported_footer(line):
            in_footer_block = True
            footers.append(line)
            continue
        if in_footer_block:
            return None
    return tuple(footers)


def _is_supported_footer(line: str) -> bool:
    return bool(
        _STANDARD_FOOTER_PATTERN.fullmatch(line)
        or _BREAKING_CHANGE_PATTERN.fullmatch(line)
        or _CLINE_SDLC_TRAILER_PATTERN.fullmatch(line)
    )


def _invalid(code: CommitMessageValidationCode, summary: str) -> ConventionalCommitValidationResult:
    return ConventionalCommitValidationResult(valid=False, code=code, summary=summary)
