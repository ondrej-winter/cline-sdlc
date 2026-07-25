"""DTOs for balanced-profile operation classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlannedOperationKind(StrEnum):
    """Accepted-plan operation classes eligible for narrow authorization."""

    DEPENDENCY = "dependency"
    NETWORK = "network"


@dataclass(frozen=True)
class PlannedOperationAuthorization:
    """Exact operation authorized by one accepted material requirement."""

    kind: PlannedOperationKind
    material_requirement: str
    executable: str
    arguments: tuple[str, ...]
    destination: str | None = None
    owned_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.material_requirement.strip():
            message = "planned operation material_requirement must not be empty"
            raise ValueError(message)
        if not self.executable.strip():
            message = "planned operation executable must not be empty"
            raise ValueError(message)
        if any(not argument.strip() for argument in self.arguments):
            message = "planned operation arguments must not contain empty values"
            raise ValueError(message)
        if any("\x00" in value for value in (self.executable, *self.arguments, *self.owned_paths)):
            message = "planned operation values must not contain NUL bytes"
            raise ValueError(message)
        if len(set(self.owned_paths)) != len(self.owned_paths):
            message = "planned operation owned_paths must be unique"
            raise ValueError(message)
        if any(path.startswith(("/", "../")) or "/../" in path or "\\" in path for path in self.owned_paths):
            message = "planned operation owned_paths must be normalized repository-relative paths"
            raise ValueError(message)
        if self.kind is PlannedOperationKind.NETWORK and not (self.destination and self.destination.strip()):
            message = "planned network operation must include a destination"
            raise ValueError(message)
        if self.kind is PlannedOperationKind.DEPENDENCY and self.destination is not None:
            message = "planned dependency operation must not include a network destination"
            raise ValueError(message)
        if self.destination is not None and "\x00" in self.destination:
            message = "planned operation destination must not contain NUL bytes"
            raise ValueError(message)


@dataclass(frozen=True)
class ClassifyOperationRequest:
    """Application request to classify one structured command operation."""

    executable: str
    arguments: tuple[str, ...] = ()
    authorization: PlannedOperationAuthorization | None = None
