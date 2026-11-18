"""Validate strict portable agent role assets and their worker links."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum, auto, unique
import json
import re

from agent_kit.application.native_delivery.errors import (
    DuplicateRoleError,
    InvalidNativeJSONError,
    InvalidWorkerTargetError,
    MissingNativeFieldError,
    NativeRoleError,
    NativeRoleIssue,
    NativeRuntimeError,
    NativeTextLimitError,
    UnavailableWorkerError,
    UnknownNativeFieldError,
)
from agent_kit.core.errors import InputTypeError
from agent_kit.core.guards import (
    require_int,
    require_list,
    require_object,
    require_text,
    unique_json_object,
)
from agent_kit.core.primitives import KIT_NAME_PATTERN, NativeRuntime
from agent_kit.core.text import visible_text


@unique
class RoleKind(StrEnum):
    """Whether a native role is user-invocable or only delegated to."""

    PRIMARY = auto()
    WORKER = auto()


@unique
class RoleTier(StrEnum):
    """Tool grant level of one native role."""

    VERIFIER = auto()
    IMPLEMENTER = auto()
    COORDINATOR = auto()


_ASSET_PATH = re.compile(r"(?:[^/]+/)*\.apm/skills/[^/\\]+/assets/agents\.json\Z")
_ROLE_ID = re.compile(rf"{KIT_NAME_PATTERN}\Z")
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


@dataclass(frozen=True, kw_only=True, slots=True)
class NativeRole:
    """Validated role data shared by provider-specific adapters.

    Attributes:
        body (str): Shared role instructions rendered after the frontmatter.
        claude_model (str | None): Claude model alias, if declared.
        copilot_models (tuple[str, ...] | None): Copilot models in preference
            order, if declared.
        description (str): Single-line role description.
        identifier (str): ``kit-`` role identifier.
        kind (RoleKind): Whether the role is primary or a worker.
        tier (RoleTier): Tool grant level.
        workers (tuple[str, ...]): Linked worker identifiers in authored order.
        optional_workers (tuple[str, ...]): Workers linked only when selected.
    """

    body: str
    claude_model: str | None
    copilot_models: tuple[str, ...] | None
    description: str
    identifier: str
    kind: RoleKind
    tier: RoleTier
    workers: tuple[str, ...]
    optional_workers: tuple[str, ...]


def checked_runtimes(runtimes: tuple[str, ...]) -> tuple[NativeRuntime, ...]:
    """Return one or more unique supported runtimes or raise ``NativeRuntimeError``."""
    if not runtimes:
        raise NativeRuntimeError
    targets: list[NativeRuntime] = []
    for runtime in runtimes:
        name = require_text(runtime, location="runtime target")
        try:
            target = NativeRuntime(name)
        except ValueError as error:
            raise NativeRuntimeError from error
        if target in targets:
            raise NativeRuntimeError
        targets.append(target)
    return tuple(targets)


def _require_fields(
    value: object,
    required: set[str],
    optional: set[str],
    location: str,
) -> dict[str, object]:
    """Validate an object's exact required and optional field set.

    A value that is not an object raises ``InputTypeError``.

    Args:
        value (object): Decoded JSON value to validate as a string-keyed object.
        required (set[str]): Field names that must be present.
        optional (set[str]): Additional permitted field names.
        location (str): Object location used in validation diagnostics.

    Returns:
        dict[str, object]: The original object with all required fields and no keys
        outside the required and optional sets; field values remain unvalidated.

    Raises:
        MissingNativeFieldError: A required field is absent.
        UnknownNativeFieldError: A field is neither required nor optional.
    """
    fields = require_object(value, location=location)
    missing = sorted(required - fields.keys())
    unknown = sorted(fields.keys() - required - optional)
    if missing:
        raise MissingNativeFieldError(location=location, field=missing[0])
    if unknown:
        raise UnknownNativeFieldError(location=location, field=unknown[0])
    return fields


def _check_text(value: object, location: str, *, maximum: int | None) -> str:
    """Require bounded visible text without secret-like credential material.

    A value that is not a string raises ``InputTypeError``.

    Args:
        value (object): Decoded text to validate without trimming or normalization.
        location (str): Full field location used in validation diagnostics.
        maximum (int | None): Character limit, or ``None`` to skip the length check.

    Raises:
        NativeRoleError: The text is blank, has control characters, or looks
            like a credential.
        NativeTextLimitError: The text exceeds ``maximum`` characters.
    """
    text = require_text(value, location=location)
    if not text.strip():
        raise NativeRoleError(location=location, issue=NativeRoleIssue.EMPTY_TEXT)
    if not visible_text(text):
        raise NativeRoleError(
            location=location, issue=NativeRoleIssue.CONTROL_CHARACTERS
        )
    if maximum is not None and len(text) > maximum:
        raise NativeTextLimitError(
            location=location, maximum=maximum, unit="characters"
        )
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        raise NativeRoleError(location=location, issue=NativeRoleIssue.CREDENTIAL)
    return text


def _copilot_models(raw: object, location: str) -> tuple[str, ...]:
    """Validate a non-empty, unique list of supported Copilot models.

    Args:
        raw (object): Decoded Copilot model list in authored preference order.
        location (str): Role location to which the model field path is appended.

    Raises:
        InputTypeError: The models are not a list of strings.
        NativeRoleError: The list is empty, repeats, or names an unsupported model.
    """
    field = f"{location}.models.copilot"
    entries = require_list(raw, location=field)
    if not entries:
        raise NativeRoleError(location=field, issue=NativeRoleIssue.EMPTY_MODEL_LIST)
    models = tuple(model for model in entries if isinstance(model, str))
    if len(models) != len(entries):
        raise InputTypeError(location=f"{field} entries", expected="strings")
    if len(set(models)) != len(models):
        raise NativeRoleError(location=field, issue=NativeRoleIssue.DUPLICATE_MODELS)
    if any(model not in _COPILOT_MODELS for model in models):
        raise NativeRoleError(location=location, issue=NativeRoleIssue.COPILOT_MODEL)
    return models


def _claude_model(raw: object, location: str) -> str:
    """Validate one supported Claude model alias.

    A model that is not a string raises ``InputTypeError``.

    Args:
        raw (object): Decoded Claude model alias.
        location (str): Role location to which the model field path is appended.

    Raises:
        NativeRoleError: The model alias is unsupported.
    """
    model = require_text(raw, location=f"{location}.models.claude")
    if model not in _CLAUDE_MODELS:
        raise NativeRoleError(location=location, issue=NativeRoleIssue.CLAUDE_MODEL)
    return model


def model_settings(
    value: object, location: str
) -> tuple[tuple[str, ...] | None, str | None]:
    """Validate only the explicitly supported native model declarations.

    A models value that is not an object raises ``InputTypeError``.

    Args:
        value (object): Decoded provider-to-model declarations.
        location (str): Role location used to identify model validation failures.

    Returns:
        tuple[tuple[str, ...] | None, str | None]: Copilot model names in authored
        order, then the Claude model alias; each is ``None`` if its provider is absent.

    Raises:
        UnknownNativeFieldError: A provider is not supported.
        NativeRoleError: No provider is declared.
    """
    models = require_object(value, location=f"{location}.models")
    unknown = sorted(models.keys() - set(NativeRuntime))
    if unknown:
        raise UnknownNativeFieldError(
            location=f"{location}.models", field=unknown[0], kind="provider"
        )
    if not models:
        raise NativeRoleError(
            location=f"{location}.models", issue=NativeRoleIssue.EMPTY_MODELS
        )
    copilot_models = (
        _copilot_models(models[NativeRuntime.COPILOT], location)
        if NativeRuntime.COPILOT in models
        else None
    )
    claude_model = (
        _claude_model(models[NativeRuntime.CLAUDE], location)
        if NativeRuntime.CLAUDE in models
        else None
    )
    return copilot_models, claude_model


def _role_identifier(value: object, location: str) -> str:
    """Require a ``kit-`` role identifier.

    An identifier that is not a string raises ``InputTypeError``.

    Args:
        value (object): Decoded role identifier.
        location (str): Role location to which the identifier field path is appended.

    Raises:
        NativeRoleError: The identifier lacks the ``kit-`` form.
    """
    identifier = require_text(value, location=f"{location}.id")
    if not _ROLE_ID.fullmatch(identifier):
        raise NativeRoleError(location=location, issue=NativeRoleIssue.IDENTIFIER)
    return identifier


def _closed_choice[T: StrEnum](
    value: object,
    choices: type[T],
    field: str,
    location: str,
    issue: NativeRoleIssue,
) -> T:
    """Require a string drawn from a closed vocabulary.

    A value that is not a string raises ``InputTypeError``.

    Args:
        value (object): Decoded field value to check against the vocabulary.
        choices (type[T]): Closed enumeration of accepted values.
        field (str): Field name appended to the role location for type errors.
        location (str): Role location used in diagnostics.
        issue (NativeRoleIssue): Violation reported for a string outside the vocabulary.

    Raises:
        NativeRoleError: The value is outside ``choices``.
    """
    choice = require_text(value, location=f"{location}.{field}")
    if choice not in choices:
        raise NativeRoleError(location=location, issue=issue)
    return choices(choice)


def _role_description(value: object, location: str) -> str:
    """Require a bounded, single-line role description.

    Args:
        value (object): Decoded description checked for safe text and length.
        location (str): Role location to which the description field path is appended.

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

    Args:
        value (object): Decoded body checked for safe text and line count.
        location (str): Role location to which the body field path is appended.

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


def _role_workers(
    value: object, location: str, field: str = "workers"
) -> tuple[str, ...]:
    """Require a unique list of valid worker identifiers.

    Workers that are not a list of strings raise ``InputTypeError``.

    Args:
        value (object): Decoded worker list.
        location (str): Role location used in diagnostics.
        field (str): Role field that holds the list.

    Returns:
        tuple[str, ...]: Worker identifiers in authored order.

    Raises:
        NativeRoleError: A worker identifier is invalid or repeated.
    """
    workers: list[str] = []
    for entry in require_list(value, location=f"{location}.{field}"):
        worker = require_text(entry, location=f"{location}.{field} entry")
        if not _ROLE_ID.fullmatch(worker):
            raise NativeRoleError(
                location=location, issue=NativeRoleIssue.WORKER_IDENTIFIER
            )
        workers.append(worker)
    if len(set(workers)) != len(workers):
        raise NativeRoleError(
            location=f"{location}.{field}", issue=NativeRoleIssue.DUPLICATE_WORKERS
        )
    return tuple(workers)


def _optional_workers(
    role: dict[str, object], tier: RoleTier, workers: tuple[str, ...], location: str
) -> tuple[str, ...]:
    """Read workers linked only when their bundle is selected.

    Args:
        role (dict[str, object]): Role fields, optionally including ``optional_workers``.
        tier (RoleTier): Validated tier; only coordinators may declare optional workers.
        workers (tuple[str, ...]): Required worker identifiers that must not be repeated.
        location (str): Role location used in worker validation diagnostics.

    Raises:
        NativeRoleError: A non-coordinator declares them, or one repeats a
            required worker.
    """
    if "optional_workers" not in role:
        return ()
    optional = _role_workers(role["optional_workers"], location, "optional_workers")
    if tier is not RoleTier.COORDINATOR:
        raise NativeRoleError(
            location=f"{location}.optional_workers",
            issue=NativeRoleIssue.UNEXPECTED_WORKERS,
        )
    if set(optional) & set(workers):
        raise NativeRoleError(
            location=f"{location}.optional_workers",
            issue=NativeRoleIssue.OVERLAPPING_WORKERS,
        )
    return optional


def _check_coordination(
    kind: RoleKind, tier: RoleTier, workers: tuple[str, ...], location: str
) -> None:
    """Allow workers only on primary coordinators, which must name some.

    Args:
        kind (RoleKind): Validated role kind; coordinators must be primary roles.
        tier (RoleTier): Validated role tier controlling whether workers are required.
        workers (tuple[str, ...]): Required worker identifiers declared by the role.
        location (str): Role location used in coordination diagnostics.

    Raises:
        NativeRoleError: Workers appear outside a primary coordinator, or a
            coordinator names none.
    """
    if tier is not RoleTier.COORDINATOR:
        if workers:
            raise NativeRoleError(
                location=f"{location}.workers",
                issue=NativeRoleIssue.UNEXPECTED_WORKERS,
            )
        return
    if kind is not RoleKind.PRIMARY:
        raise NativeRoleError(
            location=location, issue=NativeRoleIssue.WORKER_COORDINATION
        )
    if not workers:
        raise NativeRoleError(location=location, issue=NativeRoleIssue.MISSING_WORKERS)


def _parse_role(value: object, asset_path: str, index: int) -> NativeRole:
    """Validate one role against the closed role schema."""
    location = f"{asset_path}:roles[{index}]"
    role = _require_fields(
        value,
        {"id", "kind", "tier", "description", "body", "workers"},
        {"models", "optional_workers"},
        location,
    )
    identifier = _role_identifier(role["id"], location)
    kind = _closed_choice(
        role["kind"], RoleKind, "kind", location, NativeRoleIssue.KIND
    )
    tier = _closed_choice(
        role["tier"], RoleTier, "tier", location, NativeRoleIssue.TIER
    )
    description = _role_description(role["description"], location)
    body = _role_body(role["body"], location)
    workers = _role_workers(role["workers"], location)
    _check_coordination(kind, tier, workers, location)
    optional_workers = _optional_workers(role, tier, workers, location)
    copilot_models, claude_model = (
        model_settings(role["models"], location) if "models" in role else (None, None)
    )
    return NativeRole(
        body=body,
        claude_model=claude_model,
        copilot_models=copilot_models,
        description=description,
        identifier=identifier,
        kind=kind,
        tier=tier,
        workers=workers,
        optional_workers=optional_workers,
    )


def _asset_roles(path: str, content: bytes) -> list[object]:
    """Decode one native asset and return its raw role list.

    An asset or role list of the wrong type raises ``InputTypeError``.

    Args:
        path (str): Source-relative asset path used in decoding diagnostics.
        content (bytes): UTF-8 JSON asset with schema version and role declarations.

    Raises:
        InvalidNativeJSONError: The asset cannot be read or decoded.
        NativeRoleError: The asset has an unsupported schema version.
    """
    try:
        decoded: object = json.loads(
            content.decode("utf-8"), object_pairs_hook=unique_json_object
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise InvalidNativeJSONError(path=path, cause=error) from error
    asset = _require_fields(decoded, {"schema_version", "roles"}, set(), path)
    schema_version = require_int(
        asset["schema_version"], location=f"native asset '{path}'.schema_version"
    )
    if schema_version != 1:
        raise NativeRoleError(
            location=f"native asset '{path}'", issue=NativeRoleIssue.SCHEMA_VERSION
        )
    return require_list(asset["roles"], location=f"native asset '{path}'.roles")


def _check_worker_links(
    roles: dict[str, NativeRole], *, require_optional: bool
) -> dict[str, NativeRole]:
    """Require worker targets and link the optional workers that are present.

    Args:
        roles (dict[str, NativeRole]): Roles keyed by identifier.
        require_optional (bool): Whether every optional worker must exist, as
            when validating the whole catalog rather than one composition.

    Returns:
        dict[str, NativeRole]: Roles whose ``workers`` include each present
        optional worker, in authored order.

    Raises:
        UnavailableWorkerError: A required target, or an optional target when
            required, names no available role.
        InvalidWorkerTargetError: A target is not a worker role.
    """
    linked: dict[str, NativeRole] = {}
    for identifier, role in roles.items():
        present: list[str] = []
        for worker_id in (*role.workers, *role.optional_workers):
            worker = roles.get(worker_id)
            if worker is None:
                if worker_id in role.workers or require_optional:
                    raise UnavailableWorkerError(worker_id)
                continue
            if worker.kind is not RoleKind.WORKER:
                raise InvalidWorkerTargetError(worker_id)
            present.append(worker_id)
        linked[identifier] = replace(role, workers=tuple(present))
    return linked


def load_roles(
    files: dict[str, bytes], *, require_optional: bool = False
) -> tuple[NativeRole, ...]:
    """Decode every matching authored asset and resolve explicit worker links.

    Args:
        files (dict[str, bytes]): Candidate source files keyed by path.
        require_optional (bool): Whether optional workers must all be present.

    Raises:
        DuplicateRoleError: Two assets declare the same role.
    """
    roles: dict[str, NativeRole] = {}
    for path in sorted(path for path in files if _ASSET_PATH.fullmatch(path)):
        for index, raw_role in enumerate(_asset_roles(path, files[path])):
            role = _parse_role(raw_role, path, index)
            if role.identifier in roles:
                raise DuplicateRoleError(role.identifier)
            roles[role.identifier] = role
    linked = _check_worker_links(roles, require_optional=require_optional)
    return tuple(linked[key] for key in sorted(linked))


def validate_native_assets(
    files: dict[str, bytes],
    runtimes: tuple[str, ...],
    *,
    require_optional: bool = False,
) -> None:
    """Validate role assets and their worker links for the given targets.

    Empty, repeated or unsupported targets raise ``NativeRuntimeError``; assets
    with a mistyped field raise ``InputTypeError``, and malformed assets or
    broken role and worker-link rules raise ``ValueError``.

    Args:
        files (dict[str, bytes]): Candidate source files keyed by path.
        runtimes (tuple[str, ...]): Native runtime targets.
        require_optional (bool): Whether every optional worker must exist; true
            for the whole catalog, false for one profile's selection.
    """
    checked_runtimes(runtimes)
    load_roles(files, require_optional=require_optional)
