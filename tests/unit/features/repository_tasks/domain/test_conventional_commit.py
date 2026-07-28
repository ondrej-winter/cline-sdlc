"""Tests for deterministic Conventional Commit validation."""

from __future__ import annotations

import pytest

from cline_sdlc.features.repository_tasks.application.dtos.commit_message import CommitMessageValidationDTO
from cline_sdlc.features.repository_tasks.domain.conventional_commit import (
    CommitMessageValidationCode,
    validate_conventional_commit_message,
)


@pytest.mark.parametrize(
    "message",
    [
        "feat: add repository task recipe",
        "fix(parser): handle staged paths",
        "refactor!: simplify commit validation",
        "test(repository_tasks)!: cover commit trailers",
    ],
)
def test_accepts_valid_conventional_commit_subject_forms(message: str) -> None:
    result = validate_conventional_commit_message(message)

    assert result.valid
    assert result.code is CommitMessageValidationCode.VALID
    assert result.normalized_message == message


def test_accepts_valid_multiline_body_and_supported_footers() -> None:
    message = (
        "feat(repository_tasks): validate commit messages\n"
        "\n"
        "Document deterministic validation before Git mutation.\n"
        "\n"
        "Refs: TASK-2\n"
        "BREAKING CHANGE: validation is now authoritative\n"
        "Cline-SDLC-Plan: configurable-lifecycle-hooks-and-repository-task-plan"
    )

    result = validate_conventional_commit_message(message)

    assert result.valid
    assert result.commit_type == "feat"
    assert result.scope == "repository_tasks"
    assert result.breaking_change is True
    assert result.footers == (
        "Refs: TASK-2",
        "BREAKING CHANGE: validation is now authoritative",
        "Cline-SDLC-Plan: configurable-lifecycle-hooks-and-repository-task-plan",
    )


def test_validation_dto_preserves_safe_result_shape() -> None:
    result = validate_conventional_commit_message("docs(readme): explain task command")

    dto = CommitMessageValidationDTO.from_domain(result)

    assert dto.valid is True
    assert dto.code == "valid"
    assert dto.summary == "commit message is valid"
    assert dto.normalized_message == "docs(readme): explain task command"
    assert dto.commit_type == "docs"
    assert dto.scope == "readme"
    assert dto.breaking_change is False


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("", CommitMessageValidationCode.EMPTY_MESSAGE),
        ("update repository task recipe", CommitMessageValidationCode.MISSING_CONVENTIONAL_SUBJECT),
        ("feature: add recipe", CommitMessageValidationCode.UNSUPPORTED_TYPE),
        ("feat(: missing scope", CommitMessageValidationCode.MISSING_CONVENTIONAL_SUBJECT),
        ("feat(BadScope): add recipe", CommitMessageValidationCode.MISSING_CONVENTIONAL_SUBJECT),
        ("feat(scope/unsafe): add recipe", CommitMessageValidationCode.MISSING_CONVENTIONAL_SUBJECT),
        ("feat: add recipe\nbody without blank line", CommitMessageValidationCode.INVALID_MULTILINE_SPACING),
        ("feat: add recipe\x00", CommitMessageValidationCode.UNSAFE_CONTROL_CHARACTER),
        ("feat: add\ttab", CommitMessageValidationCode.UNSAFE_CONTROL_CHARACTER),
    ],
)
def test_rejects_invalid_or_unsafe_commit_messages(
    message: str,
    expected_code: CommitMessageValidationCode,
) -> None:
    result = validate_conventional_commit_message(message)

    assert not result.valid
    assert result.code is expected_code
    assert result.normalized_message is None


def test_rejects_invalid_footer_after_footer_block_starts() -> None:
    result = validate_conventional_commit_message("feat: add recipe\n\nRefs: TASK-2\nnot a valid footer")

    assert not result.valid
    assert result.code is CommitMessageValidationCode.INVALID_FOOTER
