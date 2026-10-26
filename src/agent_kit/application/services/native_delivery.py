"""Render strict portable agent role assets into runtime-owned adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
import json
import re
from typing import Literal, TypeGuard

from agent_kit.core.errors import DuplicateJsonFieldError, InputTypeError
from agent_kit.core.text import visible_text

_ASSET_PATH = re.compile(r"(?:[^/]+/)*\.apm/skills/[^/\\]+/assets/agents\.json\Z")
_ROLE_ID = re.compile(r"kit-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_RUNTIMES = frozenset({"copilot", "claude"})
_ROLE_KINDS = frozenset({"primary", "worker"})
_ROLE_TIERS = frozenset({"readonly", "implementer", "coordinator"})
_COPILOT_MODELS = frozenset({"GPT-5 mini", "Claude Haiku 4.5"})
_CLAUDE_MODELS = frozenset({"haiku"})
_MAX_ROLE_BODY_LINES = 125
_MAX_ROLE_DESCRIPTION_CHARS = 180
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
    """Reject repeated JSON keys rather than accepting the final value.

    Raises:
        DuplicateJsonFieldError: A JSON object repeats a key.
    """
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonFieldError(key)
        result[key] = value
    return result


def _checked_runtimes(runtimes: tuple[str, ...]) -> tuple[str, ...]:
    """Require one or more unique, supported runtime targets.

    Raises:
        NativeRuntimeError: No target is given, or one is unknown or repeated.
        InputTypeError: A runtime target is not a string.
    """
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
    """Validate an object's exact required and optional field set.

    Raises:
        InputTypeError: The value is not an object.
        MissingNativeFieldError: A required field is absent.
        UnknownNativeFieldError: A field is neither required nor optional.
    """
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
    """Require bounded visible text without secret-like credential material.

    Raises:
        InputTypeError: The value is not a string.
        NativeRoleError: The text is blank, has control characters, or looks
            like a credential.
        NativeTextLimitError: The text exceeds ``maximum`` characters.
    """
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


def _copilot_models(raw: object, location: str) -> tuple[str, ...]:
    """Validate a non-empty, unique list of supported Copilot models.

    Raises:
        InputTypeError: The models are not a list of strings.
        NativeRoleError: The list is empty, repeats, or names an unsupported model.
    """
    field = f"{location}.models.copilot"
    if not isinstance(raw, list):
        raise InputTypeError(location=field, expected="a list")
    if not raw:
        raise NativeRoleError(location=field, issue=NativeRoleIssue.EMPTY_MODEL_LIST)
    models = tuple(model for model in raw if isinstance(model, str))
    if len(models) != len(raw):
        raise InputTypeError(location=f"{field} entries", expected="strings")
    if len(set(models)) != len(models):
        raise NativeRoleError(location=field, issue=NativeRoleIssue.DUPLICATE_MODELS)
    if any(model not in _COPILOT_MODELS for model in models):
        raise NativeRoleError(location=location, issue=NativeRoleIssue.COPILOT_MODEL)
    return models


def _claude_model(raw: object, location: str) -> str:
    """Validate one supported Claude model alias.

    Raises:
        InputTypeError: The model is not a string.
        NativeRoleError: The model alias is unsupported.
    """
    if not isinstance(raw, str):
        raise InputTypeError(location=f"{location}.models.claude", expected="a string")
    if raw not in _CLAUDE_MODELS:
        raise NativeRoleError(location=location, issue=NativeRoleIssue.CLAUDE_MODEL)
    return raw


def _model_settings(
    value: object, location: str
) -> tuple[tuple[str, ...] | None, str | None]:
    """Validate only the explicitly supported native model declarations.

    Raises:
        InputTypeError: The models value is not an object.
        UnknownNativeFieldError: A provider is not supported.
        NativeRoleError: No provider is declared.
    """
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
    copilot_models = (
        _copilot_models(value["copilot"], location) if "copilot" in value else None
    )
    claude_model = (
        _claude_model(value["claude"], location) if "claude" in value else None
    )
    return copilot_models, claude_model


def _role_identifier(value: object, location: str) -> str:
    """Require a ``kit-`` role identifier.

    Raises:
        InputTypeError: The identifier is not a string.
        NativeRoleError: The identifier lacks the ``kit-`` form.
    """
    if not isinstance(value, str):
        raise InputTypeError(location=f"{location}.id", expected="a string")
    if not _ROLE_ID.fullmatch(value):
        raise NativeRoleError(location=location, issue=NativeRoleIssue.IDENTIFIER)
    return value


def _closed_choice(
    value: object,
    allowed: frozenset[str],
    field: str,
    location: str,
    issue: NativeRoleIssue,
) -> str:
    """Require a string drawn from a closed vocabulary.

    Raises:
        InputTypeError: The value is not a string.
        NativeRoleError: The value is outside ``allowed``.
    """
    if not isinstance(value, str):
        raise InputTypeError(location=f"{location}.{field}", expected="a string")
    if value not in allowed:
        raise NativeRoleError(location=location, issue=issue)
    return value


def _role_description(value: object, location: str) -> str:
    """Require a bounded, single-line role description.

    Raises:
        NativeRoleError: The description spans several lines.
    """
    field = f"{location}.description"
    description = _check_text(value, field, maximum=_MAX_ROLE_DESCRIPTION_CHARS)
    if "\n" in description or "\r" in description:
        raise NativeRoleError(location=field, issue=NativeRoleIssue.MULTILINE)
    return description


def _role_body(value: object, location: str) -> str:
    """Require a role body within the shared line budget.

    Raises:
        NativeTextLimitError: The body exceeds the line budget.
    """
    field = f"{location}.body"
    body = _check_text(value, field, maximum=None)
    if len(body.splitlines()) > _MAX_ROLE_BODY_LINES:
        raise NativeTextLimitError(
            location=field, maximum=_MAX_ROLE_BODY_LINES, unit="lines"
        )
    return body


def _role_workers(value: object, location: str) -> tuple[str, ...]:
    """Require a unique list of valid worker identifiers.

    Raises:
        InputTypeError: The workers are not a list of strings.
        NativeRoleError: A worker identifier is invalid or repeated.
    """
    if not isinstance(value, list):
        raise InputTypeError(location=f"{location}.workers", expected="a list")
    workers: list[str] = []
    for worker in value:
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
    return tuple(workers)


def _check_coordination(
    kind: str, tier: str, workers: tuple[str, ...], location: str
) -> None:
    """Allow workers only on primary coordinators, which must name some.

    Raises:
        NativeRoleError: Workers appear outside a primary coordinator, or a
            coordinator names none.
    """
    if tier != "coordinator":
        if workers:
            raise NativeRoleError(
                location=f"{location}.workers",
                issue=NativeRoleIssue.UNEXPECTED_WORKERS,
            )
        return
    if kind != "primary":
        raise NativeRoleError(
            location=location, issue=NativeRoleIssue.WORKER_COORDINATION
        )
    if not workers:
        raise NativeRoleError(location=location, issue=NativeRoleIssue.MISSING_WORKERS)


def _parse_role(value: object, asset_path: str, index: int) -> _NativeRole:
    """Validate one role against the closed role schema."""
    location = f"{asset_path}:roles[{index}]"
    role = _require_fields(
        value,
        {"id", "kind", "tier", "description", "body", "workers"},
        {"models"},
        location,
    )
    identifier = _role_identifier(role["id"], location)
    kind = _closed_choice(
        role["kind"], _ROLE_KINDS, "kind", location, NativeRoleIssue.KIND
    )
    tier = _closed_choice(
        role["tier"], _ROLE_TIERS, "tier", location, NativeRoleIssue.TIER
    )
    description = _role_description(role["description"], location)
    body = _role_body(role["body"], location)
    workers = _role_workers(role["workers"], location)
    _check_coordination(kind, tier, workers, location)
    copilot_models, claude_model = (
        _model_settings(role["models"], location) if "models" in role else (None, None)
    )
    return _NativeRole(
        body=body,
        claude_model=claude_model,
        copilot_models=copilot_models,
        description=description,
        identifier=identifier,
        kind=kind,
        tier=tier,
        workers=workers,
    )


def _asset_roles(path: str, content: bytes) -> list[object]:
    """Decode one native asset and return its raw role list.

    Raises:
        InvalidNativeJsonError: The asset cannot be read or decoded.
        InputTypeError: The asset or its roles have the wrong type.
        NativeRoleError: The asset has unexpected fields.
    """
    try:
        decoded: object = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object_pairs
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
        raise InputTypeError(location=f"native asset '{path}'.roles", expected="a list")
    return raw_roles


def _check_worker_links(roles: dict[str, _NativeRole]) -> None:
    """Require every coordinator target to be an available worker role.

    Raises:
        UnavailableWorkerError: A target names no available role.
        InvalidWorkerTargetError: A target is not a worker role.
    """
    for role in roles.values():
        for worker_id in role.workers:
            worker = roles.get(worker_id)
            if worker is None:
                raise UnavailableWorkerError(worker_id)
            if worker.kind != "worker":
                raise InvalidWorkerTargetError(worker_id)


def _load_roles(files: dict[str, bytes]) -> tuple[_NativeRole, ...]:
    """Decode every matching authored asset and resolve explicit worker links.

    Raises:
        DuplicateRoleError: Two assets declare the same role.
    """
    roles: dict[str, _NativeRole] = {}
    for path in sorted(path for path in files if _ASSET_PATH.fullmatch(path)):
        for index, raw_role in enumerate(_asset_roles(path, files[path])):
            role = _parse_role(raw_role, path, index)
            if role.identifier in roles:
                raise DuplicateRoleError(role.identifier)
            roles[role.identifier] = role
    _check_worker_links(roles)
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
