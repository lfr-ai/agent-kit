"""Closed native-role violations and the errors raised while validating roles."""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Literal


@unique
class NativeRoleIssue(StrEnum):
    """Closed set of native-role value and relationship violations."""

    EMPTY_TEXT = "must be non-empty text"
    CONTROL_CHARACTERS = "contains unsupported control characters"
    CREDENTIAL = "contains secret-like credential material"
    EMPTY_MODELS = "must not be empty"
    EMPTY_MODEL_LIST = "must be a non-empty list"
    DUPLICATE_MODELS = "contains duplicate models"
    COPILOT_MODEL = "declares an unsupported Copilot model"
    CLAUDE_MODEL = "declares an unsupported Claude model"
    IDENTIFIER = "has an invalid role identifier"
    KIND = "has invalid kind"
    TIER = "has invalid tier"
    MULTILINE = "must be a single line"
    WORKER_IDENTIFIER = "has an invalid worker identifier"
    DUPLICATE_WORKERS = "contains duplicate identifiers"
    WORKER_COORDINATION = "worker roles cannot coordinate other agents"
    MISSING_WORKERS = "coordinator must name required workers"
    UNEXPECTED_WORKERS = "are only allowed for coordinators"
    OVERLAPPING_WORKERS = "repeat a required worker"
    SCHEMA_VERSION = "has unsupported schema_version"


class NativeRoleError(ValueError):
    """A native role violates a closed schema or coordination invariant."""

    def __init__(self, *, location: str, issue: NativeRoleIssue) -> None:
        """Identify a violation without accepting arbitrary diagnostic text.

        Args:
            location (str): Safe asset, role or field location.
            issue (NativeRoleIssue): Violated native-role invariant.
        """
        self.location = location
        self.issue = issue
        super().__init__(f"{location} {issue}")


class NativeRuntimeError(ValueError):
    """A native delivery target selection is empty, repeated or unsupported."""

    def __init__(self) -> None:
        """Describe the supported runtime selection contract."""
        super().__init__("runtime targets must be non-empty, unique, and supported")


class MissingNativeFieldError(ValueError):
    """A native object omits a required field."""

    def __init__(self, *, location: str, field: str) -> None:
        """Identify the missing field.

        Args:
            location (str): Object location.
            field (str): Required field name.
        """
        super().__init__(f"{location} is missing field '{field}'")


class UnknownNativeFieldError(ValueError):
    """A native object declares an unrecognized field or model provider."""

    def __init__(
        self, *, location: str, field: str, kind: Literal["field", "provider"] = "field"
    ) -> None:
        """Identify an unsupported schema member.

        Args:
            location (str): Object location.
            field (str): Unknown member name.
            kind (Literal["field", "provider"]): Schema member category.
        """
        super().__init__(f"{location} has unknown {kind} '{field}'")


class NativeTextLimitError(ValueError):
    """A role's visible text exceeds its explicitly bounded footprint."""

    def __init__(
        self, *, location: str, maximum: int, unit: Literal["characters", "lines"]
    ) -> None:
        """Report the exceeded text bound.

        Args:
            location (str): Text field location.
            maximum (int): Maximum allowed size.
            unit (Literal["characters", "lines"]): Text measurement unit.
        """
        super().__init__(f"{location} exceeds {maximum} {unit}")


class InvalidNativeJSONError(ValueError):
    """A native asset cannot be decoded unambiguously."""

    def __init__(self, *, path: str, cause: Exception) -> None:
        """Identify the failed asset and its parser diagnostic.

        Args:
            path (str): Source-relative asset path.
            cause (Exception): Original decoding failure.
        """
        super().__init__(f"native asset '{path}' is invalid JSON: {cause}")


class DuplicateRoleError(ValueError):
    """Multiple assets declare the same role identity."""

    def __init__(self, identifier: str) -> None:
        """Identify the repeated role.

        Args:
            identifier (str): Repeated role identifier.
        """
        super().__init__(f"duplicate role id '{identifier}'")


class UnavailableWorkerError(ValueError):
    """A coordinator references an absent worker."""

    def __init__(self, identifier: str) -> None:
        """Identify the missing dependency.

        Args:
            identifier (str): Required worker identifier.
        """
        super().__init__(f"required worker '{identifier}' is unavailable")


class InvalidWorkerTargetError(ValueError):
    """A coordinator targets a primary role instead of a worker."""

    def __init__(self, identifier: str) -> None:
        """Identify the invalid coordinator target.

        Args:
            identifier (str): Target role identifier.
        """
        super().__init__(f"coordinator target '{identifier}' is not a worker")
