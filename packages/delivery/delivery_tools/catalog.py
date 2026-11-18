"""Generate the package contract from actual templates, adapted from Delivery Kit."""

from __future__ import annotations

from enum import StrEnum, auto, unique
import json
import math
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final, NotRequired, TypedDict

from delivery_tools.documents import (
    DocumentError,
    mapping,
    read_catalog_yaml,
    read_yaml,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
VERSION: Final[str] = "0.1.0"
KINDS: Final[tuple[str, ...]] = ("extends", "jobs", "steps")
CAPABILITIES: Final[tuple[str, ...]] = (
    "python-ci",
    "bun-ci",
    "bicep-check",
    "terraform-check",
    "azure-deploy",
)
WORKFLOW_FILES: Final[tuple[str, ...]] = tuple(
    f"delivery-{name}.yml" for name in CAPABILITIES
)
PYTHON_CHECK_ACTION: Final[str] = "actions/python-check/action.yml"
PYTHON_CHECK_REFERENCE: Final[str] = "$/packages/delivery/actions/python-check"
COMPOSITIONS: Final[tuple[str, ...]] = tuple(
    f"infra/{name}"
    for name in (
        "ai-foundry",
        "ai-search",
        "api-management",
        "application-insights",
        "audit-logs",
        "container-apps",
        "container-apps-alerts",
        "container-registry",
        "cosmos-db",
        "document-intelligence",
        "key-vault",
        "managed-redis",
        "network",
        "postgresql",
        "storage-account",
        "terraform-state",
    )
)
_SCHEMA_VERSION = 4
_JSON_INDENT = 2
_MAX_VALUE_DEPTH = 100
_ACCESS_LEVELS = ("none", "read", "write")


@unique
class _ValueType(StrEnum):
    STRING = auto()
    BOOLEAN = auto()
    NUMBER = auto()
    OBJECT = auto()
    STEP = auto()
    STEP_LIST = "stepList"
    JOB = auto()
    JOB_LIST = "jobList"
    DEPLOYMENT = auto()
    DEPLOYMENT_LIST = "deploymentList"
    STAGE = auto()
    STAGE_LIST = "stageList"


_SCALAR_TYPES = (_ValueType.STRING, _ValueType.BOOLEAN, _ValueType.NUMBER)
_MAPPING_TYPES = (
    _ValueType.STEP,
    _ValueType.JOB,
    _ValueType.DEPLOYMENT,
    _ValueType.STAGE,
)
type _Scalar = str | bool | int | float


class _SecretContract(TypedDict):
    required: bool
    description: str


class _InputContract(_SecretContract):
    type: str
    default: NotRequired[_Scalar]


def _invalid(field: str, expected: str) -> DocumentError:
    return DocumentError(f"{field}: expected {expected}")


def _mapping(value: object, *, field: str) -> dict[str, object]:
    try:
        return mapping(value)
    except DocumentError as exc:
        raise _invalid(field, "a string-keyed mapping") from exc


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise _invalid(field, "a string")
    return value


def _name(value: object, *, field: str) -> str:
    name = _text(value, field=field)
    if not name.strip():
        raise _invalid(field, "a non-empty name")
    return name


def _boolean(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid(field, "a boolean")
    return value


def _kind(value: object, *, field: str) -> _ValueType:
    """Decode a supported parameter type with a field-specific error."""
    text = _text(value, field=field)
    try:
        return _ValueType(text)
    except ValueError as exc:
        raise _invalid(field, "a supported parameter type") from exc


def _scalar(value: object, *, kind: _ValueType, field: str) -> _Scalar:
    """Validate without coercion; booleans are not numbers and numbers must be finite."""
    if kind is _ValueType.STRING:
        return _text(value, field=field)
    if kind is _ValueType.BOOLEAN:
        return _boolean(value, field=field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(field, "a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise _invalid(field, "a finite number")
    return value


def _document_scalar(value: object, *, field: str) -> None:
    if value is not None and not isinstance(value, (str, bool, int, float)):
        raise _invalid(field, "a JSON-compatible value")
    if isinstance(value, float) and not math.isfinite(value):
        raise _invalid(field, "a finite number")


def _document_value(value: object, *, field: str, depth: int = 0) -> None:
    """Reject non-JSON, non-finite and cyclic/deep values before serialization."""
    if depth >= _MAX_VALUE_DEPTH:
        raise _invalid(field, "a value nested less than 100 levels")
    if isinstance(value, dict):
        children = _mapping(value, field=field).values()
    elif isinstance(value, list):
        children = value
    else:
        _document_scalar(value, field=field)
        return
    for child in children:
        _document_value(child, field=field, depth=depth + 1)


def _default(value: object, *, kind: _ValueType, field: str) -> None:
    """Check Azure scalar/structured defaults and their nested JSON compatibility."""
    if kind in _SCALAR_TYPES:
        _scalar(value, kind=kind, field=field)
    elif kind in _MAPPING_TYPES:
        _mapping(value, field=field)
    elif kind is not _ValueType.OBJECT:
        if not isinstance(value, list):
            raise _invalid(field, "a list of mappings")
        for child in value:
            _mapping(child, field=field)
    _document_value(value, field=field)


def is_source_file(path: Path, root: Path) -> bool:
    """Return whether ``path`` is authored source, not local Terraform working output.

    A local ``terraform init`` or ``test`` inside a module writes ``.terraform/``
    and a lock file that Terraform ignores for child modules; neither may change
    the inventory, or a clean checkout would see a stale catalog.

    Args:
        path (Path): Candidate file under ``root``.
        root (Path): Package root that inventory paths are relative to.

    Returns:
        bool: ``True`` for a regular file that belongs in the inventory.
    """
    relative = path.relative_to(root)
    return (
        path.is_file()
        and ".terraform" not in relative.parts
        and relative.name != ".terraform.lock.hcl"
    )


def _composition_files(root: Path, composition: str) -> tuple[str, ...]:
    """Inventory one Azure composition, rejecting incomplete or escaping sources."""
    directory = root / composition
    files = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in directory.rglob("*")
            if is_source_file(path, root)
        )
    )
    required = {
        f"{composition}/{name}"
        for name in (
            "README.md",
            "REFERENCE.md",
            "bicep/main.bicep",
            "terraform/main.tf",
        )
    }
    resolved_root = root.resolve()
    escapes = any(
        not (root / name).resolve().is_relative_to(resolved_root) for name in files
    )
    complete = directory.is_dir() and required.issubset(files)
    if not complete or escapes:
        message = (
            f"{composition} infrastructure source is incomplete or escapes the package"
        )
        raise DocumentError(message)
    return files


def infrastructure_files(root: Path) -> tuple[str, ...]:
    """Inventory every Azure composition's sources for validation."""
    return tuple(
        name
        for composition in COMPOSITIONS
        for name in _composition_files(root, composition)
    )


def _composition(root: Path, composition: str) -> dict[str, object]:
    return {
        "path": composition,
        "files": list(_composition_files(root, composition)),
        "bicep": f"{composition}/bicep/main.bicep",
        "terraform": f"{composition}/terraform/main.tf",
    }


def nodes(value: object) -> Iterator[dict[str, object]]:
    """Yield each string-keyed mapping depth-first without interpreting expressions.

    A nested dictionary with non-string keys propagates ``DocumentError``.
    """
    if isinstance(value, dict):
        item = mapping(value)
        yield item
        for child in item.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def _input(value: object, *, field: str, action: bool = False) -> _InputContract:
    """Validate inputs; only actions imply string types and require descriptions."""
    definition = _mapping(value, field=field)
    type_field = f"{field}.type"
    kind = (
        _ValueType.STRING if action else _kind(definition.get("type"), field=type_field)
    )
    if kind not in _SCALAR_TYPES:
        raise _invalid(type_field, "string, boolean or number")
    description = (
        definition.get("description") if action else definition.get("description", "")
    )
    result: _InputContract = {
        "type": kind.value,
        "required": _boolean(
            definition.get("required", False), field=f"{field}.required"
        ),
        "description": _text(description, field=f"{field}.description"),
    }
    if "default" in definition:
        result["default"] = _scalar(
            definition["default"], kind=kind, field=f"{field}.default"
        )
    return result


def _inputs(value: object, *, action: bool = False) -> dict[str, _InputContract]:
    return {
        _name(name, field="inputs.name"): _input(
            item, field=f"inputs.{name}", action=action
        )
        for name, item in _mapping(value, field="inputs").items()
    }


def _secret(value: object, *, field: str) -> _SecretContract:
    """Validate declarations without reading or returning secret values."""
    definition = _mapping(value, field=field)
    return {
        "required": _boolean(
            definition.get("required", False), field=f"{field}.required"
        ),
        "description": _text(
            definition.get("description", ""), field=f"{field}.description"
        ),
    }


def workflow_paths(workflow_root: Path) -> tuple[Path, ...]:
    """Return the exact, flat delivery workflow paths in stable order.

    Unrelated workflows are not selected; a missing, unexpected, nested or
    escaping delivery workflow raises ``DocumentError``.
    """
    workflow_root = workflow_root.resolve()
    actual = {
        path.relative_to(workflow_root).as_posix()
        for path in workflow_root.rglob("delivery-*")
        if path.is_file()
    }
    expected = set(WORKFLOW_FILES)
    if actual != expected:
        message = f"Workflow inventory differs: {sorted(actual ^ expected)}"
        raise DocumentError(message)
    paths = tuple(workflow_root / name for name in sorted(WORKFLOW_FILES))
    if any(path.resolve().parent != workflow_root for path in paths):
        message = "Workflow escapes the supplied workflow root"
        raise DocumentError(message)
    return paths


def _access(value: object, *, field: str) -> str:
    level = _text(value, field=field)
    if level not in _ACCESS_LEVELS:
        raise _invalid(field, "none, read or write")
    return level


def _permissions(document: dict[str, object]) -> dict[str, str]:
    """Project the token grant a caller job must allow: the broadest root or job level.

    A called workflow can only keep or reduce its caller's ``GITHUB_TOKEN``
    permissions, so job-level grants such as ``id-token: write`` must be granted
    by the calling job.
    """
    grants = [_mapping(document.get("permissions"), field="permissions")]
    for name, job in _mapping(document.get("jobs", {}), field="jobs").items():
        definition = _mapping(job, field=f"jobs.{name}")
        if "permissions" in definition:
            grants.append(
                _mapping(definition["permissions"], field=f"jobs.{name}.permissions")
            )
    result: dict[str, str] = {}
    for grant in grants:
        for scope, value in grant.items():
            level = _access(value, field=f"permissions.{scope}")
            current = result.get(scope, "none")
            if _ACCESS_LEVELS.index(level) >= _ACCESS_LEVELS.index(current):
                result[scope] = level
    return result


def _workflow(path: Path) -> dict[str, object]:
    """Project typed workflow metadata, accepting native empty workflow-call blocks."""
    document = read_catalog_yaml(path)
    triggers = _mapping(document.get("on"), field="on")
    call_value = triggers.get("workflow_call")
    call = (
        {}
        if "workflow_call" in triggers and call_value is None
        else _mapping(call_value, field="on.workflow_call")
    )
    return {
        "path": f".github/workflows/{path.name}",
        "sourceRoot": "repository",
        "inputs": _inputs(call.get("inputs", {})),
        "secrets": {
            _name(name, field="secrets.name"): _secret(item, field=f"secrets.{name}")
            for name, item in _mapping(call.get("secrets", {}), field="secrets").items()
        },
        "permissions": _permissions(document),
    }


def python_action_path(root: Path) -> Path:
    """Return the canonical composite action, or raise ``DocumentError`` if absent or escaping."""
    path = root / PYTHON_CHECK_ACTION
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        message = "Python check action is missing or escapes its package"
        raise DocumentError(message)
    return path


def _python_action(root: Path) -> dict[str, object]:
    """Read action inputs as strings without overwriting supplied scalar values."""
    document = read_catalog_yaml(python_action_path(root))
    return {
        "path": PYTHON_CHECK_ACTION,
        "sourceRoot": "package",
        "reference": PYTHON_CHECK_REFERENCE,
        "inputs": _inputs(document.get("inputs", {}), action=True),
    }


def parameters(document: dict[str, object]) -> dict[str, dict[str, object]]:
    """Describe unique, typed Azure template parameters.

    The optional ``parameters`` list is validated without mutating the source.
    Omitted defaults stay omitted; their absence alone determines ``required``.
    A non-list, a non-mapping definition, an invalid name, type, default or
    values, or a duplicate name raises ``DocumentError`` naming the field.
    Values must be finite, JSON-compatible and nested less than 100 levels.
    """
    raw = document.get("parameters", [])
    if not isinstance(raw, list):
        message = "Template parameters must be a list"
        raise DocumentError(message)
    result: dict[str, dict[str, object]] = {}
    for index, value in enumerate(raw):
        field = f"parameters[{index}]"
        item = _mapping(value, field=field)
        name = _name(item.get("name"), field=f"{field}.name")
        if name in result:
            message = f"Duplicate template parameter: {name}"
            raise DocumentError(message)
        kind = _kind(item.get("type"), field=f"{field}.type")
        _parameter_values(item, kind=kind, field=field)
        result[name] = {
            "type": kind.value,
            "required": "default" not in item,
            **{key: item[key] for key in ("default", "values") if key in item},
        }
    return result


def _parameter_values(item: dict[str, object], *, kind: _ValueType, field: str) -> None:
    """Validate defaults and allowed-value entries against the declared Azure type."""
    if "default" in item:
        _default(item["default"], kind=kind, field=f"{field}.default")
    if "values" in item:
        values = item["values"]
        values_field = f"{field}.values"
        if not isinstance(values, list):
            raise _invalid(values_field, "a list")
        for value in values:
            _default(value, kind=kind, field=values_field)


def build(root: Path = ROOT, *, workflow_root: Path) -> dict[str, object]:
    """Build package contracts and repository-owned workflows from explicit roots.

    Invalid or ambiguous source inventory or metadata propagates
    ``DocumentError``; field diagnostics identify malformed input, secret or
    parameter definitions, and no partial catalog is returned. An unreadable
    source propagates ``OSError`` and a non-UTF-8 source ``UnicodeError``.

    Args:
        root: Installed or exported delivery package; defaults to this package.
        workflow_root: Explicit directory of all five workflows; no fallback lookup.

    Returns:
        A complete schema-v4 catalog with typed defaults and stable source paths.
    """
    return {
        "schemaVersion": _SCHEMA_VERSION,
        "version": VERSION,
        "github": {
            path.stem: _workflow(path) for path in workflow_paths(workflow_root)
        },
        "githubActions": {"python-check": _python_action(root)},
        "azureInfrastructure": {
            PurePosixPath(composition).name: _composition(root, composition)
            for composition in COMPOSITIONS
        },
        "azureDevOps": {
            kind: {
                path.stem: {
                    "path": path.relative_to(root).as_posix(),
                    "parameters": parameters(read_yaml(path)),
                }
                for path in sorted((root / "azure-devops" / kind).glob("*.yml"))
            }
            for kind in KINDS
        },
        "renovate": [
            path.relative_to(root).as_posix()
            for path in sorted((root / "renovate").glob("*.json"))
        ],
    }


def render(root: Path = ROOT, *, workflow_root: Path) -> str:
    """Render a complete schema-v4 catalog with stable ordering and a trailing newline.

    Roots and propagated failures follow ``build``; no partial JSON is returned.
    Rendering never writes the generated JSON.
    """
    return (
        json.dumps(
            build(root, workflow_root=workflow_root),
            indent=_JSON_INDENT,
            sort_keys=True,
        )
        + "\n"
    )
