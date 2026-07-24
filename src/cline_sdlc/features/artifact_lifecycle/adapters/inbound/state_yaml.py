"""Strict parser for embedded implementation-plan lifecycle state blocks."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from io import StringIO
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, TaggedScalar
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError
from ruamel.yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from cline_sdlc.features.artifact_lifecycle.domain.plan_state import (
    DIGEST_SCHEMA_VERSION,
    PLAN_STATE_SCHEMA_VERSION,
    PlanBlocker,
    PlanPhase,
    PlanProfile,
    PlanState,
    ReviewReadiness,
    ValidationEvidence,
)

STATE_BLOCK_PATTERN = re.compile(r"^```cline-sdlc-state\n(?P<body>.*?)\n```\s*$", re.MULTILINE | re.DOTALL)

_EXPECTED_FIELDS = frozenset(
    {
        "schema_version",
        "work_id",
        "profile",
        "phase",
        "specification",
        "specification_digest",
        "plan_revision",
        "review_iteration",
        "review_readiness",
        "digest_schema_version",
        "material_digest",
        "current_task",
        "current_slice",
        "slice_start_commit",
        "partial_slice_paths",
        "completed_slices",
        "remediation_records",
        "validation_evidence",
        "blocker",
        "created_at",
        "updated_at",
        "completed_at",
    },
)


class StrictStateYAMLError(ValueError):
    """Raised when an embedded lifecycle state block is absent or invalid."""


class _StrictYAML(YAML):
    def __init__(self) -> None:
        super().__init__(typ="safe", pure=True)
        self.allow_duplicate_keys = False

    def compose(self, stream: Any) -> Node | None:
        node = cast("Node | None", super().compose(stream))
        if node is not None:
            _reject_aliases_and_custom_tags(node)
        return node


def parse_plan_state_from_markdown(markdown: str) -> PlanState:
    """Extract and parse exactly one embedded `cline-sdlc-state` block."""
    matches = tuple(STATE_BLOCK_PATTERN.finditer(markdown))
    if len(matches) != 1:
        message = "plan must contain exactly one cline-sdlc-state block"
        raise StrictStateYAMLError(message)
    return parse_plan_state_yaml(matches[0].group("body"))


def parse_plan_state_yaml(raw_yaml: str) -> PlanState:
    """Parse one strict YAML lifecycle state document into a domain value."""
    _reject_anchor_and_alias_tokens(raw_yaml)
    yaml = _StrictYAML()
    try:
        loaded = yaml.load(StringIO(raw_yaml))
    except (DuplicateKeyError, YAMLError) as err:
        message = "invalid cline-sdlc-state YAML"
        raise StrictStateYAMLError(message) from err
    if not isinstance(loaded, dict):
        message = "cline-sdlc-state must be a mapping"
        raise StrictStateYAMLError(message)
    try:
        return _coerce_state_mapping(loaded)
    except (TypeError, ValueError) as err:
        message = str(err) or "invalid cline-sdlc-state"
        raise StrictStateYAMLError(message) from err


def _reject_anchor_and_alias_tokens(raw_yaml: str) -> None:
    if re.search(r"(?m)(?:^|[:\[,{\s])&[A-Za-z0-9_-]+\b|(?:^|[:\[,{\s])\*[A-Za-z0-9_-]+\b", raw_yaml):
        message = "cline-sdlc-state must not contain aliases"
        raise StrictStateYAMLError(message)


def _reject_aliases_and_custom_tags(node: Node, *, seen: set[int] | None = None) -> None:
    seen_nodes = seen or set()
    if id(node) in seen_nodes:
        message = "cline-sdlc-state must not contain aliases"
        raise StrictStateYAMLError(message)
    seen_nodes.add(id(node))

    tag = str(node.tag)
    if not tag.startswith("tag:yaml.org,2002:"):
        message = "cline-sdlc-state must not contain custom tags"
        raise StrictStateYAMLError(message)
    if isinstance(node, ScalarNode):
        return
    if isinstance(node, SequenceNode):
        for item in node.value:
            _reject_aliases_and_custom_tags(item, seen=seen_nodes)
        return
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            _reject_aliases_and_custom_tags(key_node, seen=seen_nodes)
            _reject_aliases_and_custom_tags(value_node, seen=seen_nodes)


def _coerce_state_mapping(raw: dict[object, object]) -> PlanState:
    state = _plain_mapping(raw, field_name="cline-sdlc-state")
    unknown_fields = set(state) - _EXPECTED_FIELDS
    if unknown_fields:
        message = f"unknown plan state fields: {', '.join(sorted(unknown_fields))}"
        raise ValueError(message)
    missing_fields = _EXPECTED_FIELDS - set(state)
    if missing_fields:
        message = f"missing plan state fields: {', '.join(sorted(missing_fields))}"
        raise ValueError(message)
    if state["schema_version"] != PLAN_STATE_SCHEMA_VERSION:
        message = "unsupported plan state schema version"
        raise ValueError(message)
    if state["digest_schema_version"] != DIGEST_SCHEMA_VERSION:
        message = "unsupported plan state digest schema version"
        raise ValueError(message)
    return PlanState(
        schema_version=_require_int(state["schema_version"], field_name="schema_version"),
        work_id=_require_string(state["work_id"], field_name="work_id"),
        profile=PlanProfile(_require_string(state["profile"], field_name="profile")),
        phase=PlanPhase(_require_string(state["phase"], field_name="phase")),
        specification=_require_string(state["specification"], field_name="specification"),
        specification_digest=_require_string(state["specification_digest"], field_name="specification_digest"),
        plan_revision=_require_int(state["plan_revision"], field_name="plan_revision"),
        review_iteration=_require_int(state["review_iteration"], field_name="review_iteration"),
        review_readiness=ReviewReadiness(_require_string(state["review_readiness"], field_name="review_readiness")),
        digest_schema_version=_require_int(state["digest_schema_version"], field_name="digest_schema_version"),
        material_digest=_require_string(state["material_digest"], field_name="material_digest"),
        current_task=_optional_string(state["current_task"], field_name="current_task"),
        current_slice=_optional_string(state["current_slice"], field_name="current_slice"),
        slice_start_commit=_optional_string(state["slice_start_commit"], field_name="slice_start_commit"),
        partial_slice_paths=_string_tuple(state["partial_slice_paths"], field_name="partial_slice_paths"),
        completed_slices=_string_tuple(state["completed_slices"], field_name="completed_slices"),
        remediation_records=tuple(_sequence(state["remediation_records"], field_name="remediation_records")),
        validation_evidence=_validation_evidence_tuple(state["validation_evidence"]),
        blocker=_optional_blocker(state["blocker"]),
        created_at=_timestamp(state["created_at"], field_name="created_at"),
        updated_at=_timestamp(state["updated_at"], field_name="updated_at"),
        completed_at=_optional_timestamp(state["completed_at"], field_name="completed_at"),
    )


def _plain_mapping(value: object, *, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or isinstance(value, CommentedMap):
        message = f"{field_name} must be a plain mapping"
        raise TypeError(message)
    mapped: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            message = f"{field_name} keys must be strings"
            raise TypeError(message)
        mapped[key] = item
    return mapped


def _require_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or isinstance(value, TaggedScalar):
        message = f"{field_name} must be a string"
        raise TypeError(message)
    return value


def _optional_string(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name=field_name)


def _require_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        message = f"{field_name} must be an integer"
        raise TypeError(message)
    return value


def _sequence(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list) or isinstance(value, CommentedSeq):
        message = f"{field_name} must be a sequence"
        raise TypeError(message)
    return value


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    return tuple(_require_string(item, field_name=field_name) for item in _sequence(value, field_name=field_name))


def _validation_evidence_tuple(value: object) -> tuple[ValidationEvidence, ...]:
    evidence: list[ValidationEvidence] = []
    for item in _sequence(value, field_name="validation_evidence"):
        mapped = _plain_mapping(item, field_name="validation_evidence item")
        expected = {"slice_id", "command", "result", "exit_code", "recorded_at"}
        if set(mapped) != expected:
            message = (
                "validation_evidence items must contain exactly slice_id, command, result, exit_code, and recorded_at"
            )
            raise ValueError(message)
        evidence.append(
            ValidationEvidence(
                slice_id=_require_string(mapped["slice_id"], field_name="validation_evidence slice_id"),
                command=_require_string(mapped["command"], field_name="validation_evidence command"),
                result=_require_string(mapped["result"], field_name="validation_evidence result"),
                exit_code=None
                if mapped["exit_code"] is None
                else _require_int(mapped["exit_code"], field_name="validation_evidence exit_code"),
                recorded_at=_timestamp(mapped["recorded_at"], field_name="validation_evidence recorded_at"),
            )
        )
    return tuple(evidence)


def _optional_blocker(value: object) -> PlanBlocker | None:
    if value is None:
        return None
    mapped = _plain_mapping(value, field_name="blocker")
    if set(mapped) != {"code", "summary"}:
        message = "blocker must contain exactly code and summary"
        raise ValueError(message)
    return PlanBlocker(
        code=_require_string(mapped["code"], field_name="blocker code"),
        summary=_require_string(mapped["summary"], field_name="blocker summary"),
    )


def _timestamp(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = _parse_rfc3339(value, field_name=field_name)
    else:
        message = f"{field_name} must be a UTC RFC 3339 timestamp"
        raise TypeError(message)
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        message = f"{field_name} must be a UTC RFC 3339 timestamp"
        raise ValueError(message)
    return timestamp.astimezone(UTC)


def _optional_timestamp(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, field_name=field_name)


def _parse_rfc3339(value: str, *, field_name: str) -> datetime:
    if not value.endswith("Z"):
        message = f"{field_name} must be a UTC RFC 3339 timestamp"
        raise ValueError(message)
    try:
        return datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as err:
        message = f"{field_name} must be a UTC RFC 3339 timestamp"
        raise ValueError(message) from err
