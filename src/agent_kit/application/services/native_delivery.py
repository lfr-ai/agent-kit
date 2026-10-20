"""Render strict portable agent role assets into runtime-owned adapters."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Literal, TypeGuard

from agent_kit.core.errors import DuplicateJsonFieldError, InputTypeError
from agent_kit.core.text import visible_text

_ASSET_PATH = re.compile(r"(?:[^/]+/)*\.apm/skills/[^/\\]+/assets/agents\.json\Z")
_ROLE_ID = re.compile(r"kit-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_RUNTIMES = frozenset({"copilot", "claude"})
_COPILOT_MODELS = frozenset({"GPT-5 mini", "Claude Haiku 4.5"})
_CLAUDE_MODELS = frozenset({"haiku"})
_MAX_ROLE_BODY_LINES = 125
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|secret|token|"
        r"password|passwd|private[_-]?key)"
        r"\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


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


class InvalidNativeJsonError(ValueError):
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


@dataclass(frozen=True, kw_only=True, slots=True)
class _NativeRole:
    """Validated role data shared by provider-specific adapters."""

    body: str
    claude_model: str | None
    copilot_models: tuple[str, ...] | None
    description: str
    identifier: str
    kind: str
    tier: str
    workers: tuple[str, ...]


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow decoded JSON to a string-keyed object."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject repeated JSON keys rather than accepting the final value."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonFieldError(key)
        result[key] = value
    return result


def _checked_runtimes(runtimes: tuple[str, ...]) -> tuple[str, ...]:
    """Require one or more unique, supported runtime targets."""
    if not runtimes:
        raise NativeRuntimeError
    seen: set[str] = set()
    for runtime in runtimes:
        if not isinstance(runtime, str):
            raise InputTypeError(location="runtime target", expected="a string")
        if runtime not in _RUNTIMES:
            raise NativeRuntimeError
        if runtime in seen:
            raise NativeRuntimeError
        seen.add(runtime)
    return runtimes


def _require_fields(
    value: object,
    required: set[str],
    optional: set[str],
    location: str,
) -> dict[str, object]:
    """Validate an object's exact required and optional field set."""
    if not _mapping(value):
        raise InputTypeError(location=location, expected="an object")
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise MissingNativeFieldError(location=location, field=missing[0])
    if unknown:
        raise UnknownNativeFieldError(location=location, field=unknown[0])
    return value


def _check_text(value: object, location: str, *, maximum: int | None) -> str:
    """Require bounded visible text without secret-like credential material."""
    if not isinstance(value, str):
        raise InputTypeError(location=location, expected="a string")
    if not value.strip():
        raise NativeRoleError(location=location, issue=NativeRoleIssue.EMPTY_TEXT)
    if not visible_text(value):
        raise NativeRoleError(
            location=location, issue=NativeRoleIssue.CONTROL_CHARACTERS
        )
    if maximum is not None and len(value) > maximum:
        raise NativeTextLimitError(
            location=location, maximum=maximum, unit="characters"
        )
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise NativeRoleError(location=location, issue=NativeRoleIssue.CREDENTIAL)
    return value


def _model_settings(  # noqa: C901
    value: object, location: str
) -> tuple[tuple[str, ...] | None, str | None]:
    """Validate only the explicitly supported native model declarations."""
    if not _mapping(value):
        raise InputTypeError(location=f"{location}.models", expected="an object")
    unknown = sorted(value.keys() - {"copilot", "claude"})
    if unknown:
        raise UnknownNativeFieldError(
            location=f"{location}.models", field=unknown[0], kind="provider"
        )
    if not value:
        raise NativeRoleError(
            location=f"{location}.models", issue=NativeRoleIssue.EMPTY_MODELS
        )

    copilot_models: tuple[str, ...] | None = None
    if "copilot" in value:
        raw_copilot = value["copilot"]
        if not isinstance(raw_copilot, list):
            raise InputTypeError(
                location=f"{location}.models.copilot", expected="a list"
            )
        if not raw_copilot:
            raise NativeRoleError(
                location=f"{location}.models.copilot",
                issue=NativeRoleIssue.EMPTY_MODEL_LIST,
            )
        if any(not isinstance(model, str) for model in raw_copilot):
            raise InputTypeError(
                location=f"{location}.models.copilot entries", expected="strings"
            )
        models = tuple(raw_copilot)
        if len(set(models)) != len(models):
            raise NativeRoleError(
                location=f"{location}.models.copilot",
                issue=NativeRoleIssue.DUPLICATE_MODELS,
            )
        if any(model not in _COPILOT_MODELS for model in models):
            raise NativeRoleError(
                location=location, issue=NativeRoleIssue.COPILOT_MODEL
            )
        copilot_models = models

    claude_model: str | None = None
    if "claude" in value:
        raw_claude = value["claude"]
        if not isinstance(raw_claude, str):
            raise InputTypeError(
                location=f"{location}.models.claude", expected="a string"
            )
        if raw_claude not in _CLAUDE_MODELS:
            raise NativeRoleError(location=location, issue=NativeRoleIssue.CLAUDE_MODEL)
        claude_model = raw_claude
    return copilot_models, claude_model


def _parse_role(value: object, asset_path: str, index: int) -> _NativeRole:  # noqa: C901, PLR0912
    """Validate one role against the closed role schema."""
    location = f"{asset_path}:roles[{index}]"
    role = _require_fields(
        value,
        {"id", "kind", "tier", "description", "body", "workers"},
        {"models"},
        location,
    )
    identifier = role["id"]
    if not isinstance(identifier, str):
        raise InputTypeError(location=f"{location}.id", expected="a string")
    if not _ROLE_ID.fullmatch(identifier):
        raise NativeRoleError(location=location, issue=NativeRoleIssue.IDENTIFIER)

    kind_value = role["kind"]
    if not isinstance(kind_value, str):
        raise InputTypeError(location=f"{location}.kind", expected="a string")
    if kind_value not in {"primary", "worker"}:
        raise NativeRoleError(location=location, issue=NativeRoleIssue.KIND)
    tier_value = role["tier"]
    if not isinstance(tier_value, str):
        raise InputTypeError(location=f"{location}.tier", expected="a string")
    if tier_value not in {
        "readonly",
        "implementer",
        "coordinator",
    }:
        raise NativeRoleError(location=location, issue=NativeRoleIssue.TIER)
    kind = kind_value
    tier = tier_value

    description = _check_text(
        role["description"], f"{location}.description", maximum=180
    )
    if "\n" in description or "\r" in description:
        raise NativeRoleError(
            location=f"{location}.description", issue=NativeRoleIssue.MULTILINE
        )
    body = _check_text(role["body"], f"{location}.body", maximum=None)
    if len(body.splitlines()) > _MAX_ROLE_BODY_LINES:
        raise NativeTextLimitError(
            location=f"{location}.body", maximum=_MAX_ROLE_BODY_LINES, unit="lines"
        )

    raw_workers = role["workers"]
    if not isinstance(raw_workers, list):
        raise InputTypeError(location=f"{location}.workers", expected="a list")
    workers: list[str] = []
    for worker in raw_workers:
        if not isinstance(worker, str):
            raise InputTypeError(
                location=f"{location}.workers entry", expected="a string"
            )
        if not _ROLE_ID.fullmatch(worker):
            raise NativeRoleError(
                location=location, issue=NativeRoleIssue.WORKER_IDENTIFIER
            )
        workers.append(worker)
    if len(set(workers)) != len(workers):
        raise NativeRoleError(
            location=f"{location}.workers", issue=NativeRoleIssue.DUPLICATE_WORKERS
        )
    if tier == "coordinator":
        if kind != "primary":
            raise NativeRoleError(
                location=location, issue=NativeRoleIssue.WORKER_COORDINATION
            )
        if not workers:
            raise NativeRoleError(
                location=location, issue=NativeRoleIssue.MISSING_WORKERS
            )
    elif workers:
        raise NativeRoleError(
            location=f"{location}.workers", issue=NativeRoleIssue.UNEXPECTED_WORKERS
        )

    copilot_models: tuple[str, ...] | None = None
    claude_model: str | None = None
    if "models" in role:
        copilot_models, claude_model = _model_settings(role["models"], location)
    return _NativeRole(
        body=body,
        claude_model=claude_model,
        copilot_models=copilot_models,
        description=description,
        identifier=identifier,
        kind=kind,
        tier=tier,
        workers=tuple(workers),
    )


def _load_roles(files: dict[str, bytes]) -> tuple[_NativeRole, ...]:  # noqa: C901
    """Decode every matching authored asset and resolve explicit worker links."""
    roles: dict[str, _NativeRole] = {}
    for path in sorted(path for path in files if _ASSET_PATH.fullmatch(path)):
        try:
            decoded: object = json.loads(
                files[path].decode("utf-8"), object_pairs_hook=_object_pairs
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            RecursionError,
            ValueError,
        ) as error:
            raise InvalidNativeJsonError(path=path, cause=error) from error
        asset = _require_fields(decoded, {"schema_version", "roles"}, set(), path)
        if type(asset["schema_version"]) is not int:
            raise InputTypeError(
                location=f"native asset '{path}'.schema_version", expected="an integer"
            )
        if asset["schema_version"] != 1:
            raise NativeRoleError(
                location=f"native asset '{path}'", issue=NativeRoleIssue.SCHEMA_VERSION
            )
        raw_roles = asset["roles"]
        if not isinstance(raw_roles, list):
            raise InputTypeError(
                location=f"native asset '{path}'.roles", expected="a list"
            )
        for index, raw_role in enumerate(raw_roles):
            role = _parse_role(raw_role, path, index)
            if role.identifier in roles:
                raise DuplicateRoleError(role.identifier)
            roles[role.identifier] = role

    for role in roles.values():
        for worker_id in role.workers:
            worker = roles.get(worker_id)
            if worker is None:
                raise UnavailableWorkerError(worker_id)
            if worker.kind != "worker":
                raise InvalidWorkerTargetError(worker_id)
    return tuple(roles[key] for key in sorted(roles))


def validate_native_assets(files: dict[str, bytes], runtimes: tuple[str, ...]) -> None:
    """Validate all matching role assets and their explicit links for targets."""
    _checked_runtimes(runtimes)
    _load_roles(files)


def _yaml_string(value: str) -> str:
    """Quote a scalar using JSON syntax, which is also valid YAML."""
    return json.dumps(value, ensure_ascii=False)


def _copilot_metadata(role: _NativeRole) -> str:
    """Render recognized Copilot agent frontmatter with bounded tool grants."""
    if role.tier == "readonly":
        tools = ["read", "search"]
    elif role.tier == "implementer":
        tools = ["read", "search", "edit", "execute"]
    else:
        tools = ["read", "search", "edit", "execute", "agent"]
    is_primary = role.kind == "primary"
    lines = [
        "---",
        f"name: {role.identifier}",
        f"description: {_yaml_string(role.description)}",
        f"tools: {json.dumps(tools)}",
        f"agents: {json.dumps(list(role.workers))}",
        f"user-invocable: {'true' if is_primary else 'false'}",
        f"disable-model-invocation: {'true' if is_primary else 'false'}",
    ]
    if role.copilot_models is not None:
        lines.append(f"model: {json.dumps(list(role.copilot_models))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _claude_metadata(role: _NativeRole) -> str:
    """Render recognized Claude agent frontmatter with scoped tools only."""
    if role.tier == "readonly":
        tools = "Read, Grep, Glob"
    elif role.tier == "implementer":
        tools = "Read, Grep, Glob, Edit, Write, Bash"
    else:
        worker_tool = f"Agent({', '.join(role.workers)})"
        tools = f"{worker_tool}, Read, Grep, Glob, Edit, Write, Bash"
    lines = [
        "---",
        f"name: {role.identifier}",
        f"description: {_yaml_string(role.description)}",
        f"tools: {_yaml_string(tools)}",
    ]
    if role.claude_model is not None:
        lines.append(f"model: {_yaml_string(role.claude_model)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _render(metadata: str, body: str) -> bytes:
    """Join provider metadata to the exact shared UTF-8 role body."""
    return metadata.encode("utf-8") + body.encode("utf-8")


def render_native_agents(
    files: dict[str, bytes], runtimes: tuple[str, ...]
) -> dict[str, bytes]:
    """Render selected runtime adapters from strict, selected source assets."""
    targets = _checked_runtimes(runtimes)
    roles = _load_roles(files)
    rendered: dict[str, bytes] = {}
    for role in roles:
        subagent = role.kind == "worker"
        if "copilot" in targets:
            directory = ".github/agents/subagents" if subagent else ".github/agents"
            path = f"{directory}/{role.identifier}.agent.md"
            rendered[path] = _render(_copilot_metadata(role), role.body)
        if "claude" in targets:
            directory = ".claude/agents/subagents" if subagent else ".claude/agents"
            path = f"{directory}/{role.identifier}.md"
            rendered[path] = _render(_claude_metadata(role), role.body)
    return rendered
