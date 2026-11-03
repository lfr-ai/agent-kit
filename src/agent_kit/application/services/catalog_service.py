"""Own catalog schema validation, profile resolution, and composition planning.

This application service works on captured ``CatalogSnapshot`` values only; the
infrastructure adapter owns every file read and write.
"""

from __future__ import annotations

from enum import StrEnum, unique
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import TYPE_CHECKING, Literal, NamedTuple, TypeGuard
from urllib.parse import unquote, urlsplit

from agent_kit.application.services.native_delivery import (
    render_native_agents,
    validate_native_assets,
)
from agent_kit.core.errors import InputTypeError
from agent_kit.core.executables import hook_issues, mcp_issues, script_issue
from agent_kit.core.guards import is_int, is_json_object, is_nonempty_text
from agent_kit.core.models import (
    Bundle,
    BundleSource,
    Catalog,
    CatalogSnapshot,
    CheckReport,
    CompositionPlan,
    Finding,
    PlannedFile,
    Profile,
    ProfileSummary,
    SourceDocument,
)
from agent_kit.core.text import markdown_link_targets, visible_text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from collections.abc import Set as AbstractSet
    from urllib.parse import SplitResult

    from agent_kit.core.guards import JsonObject

_CATALOG_FIELDS = {
    "schema_version",
    "version",
    "supported_runtimes",
    "budgets",
    "bundles",
    "profiles",
}
_BUDGET_FIELDS = {
    "policy_lines",
    "skill_body_lines",
    "description_chars",
    "profile_description_chars",
}
_SKILL_NAME = re.compile(r"kit-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_MAX_SKILL_NAME_CHARS = 64
_SKILL_PATH_DEPTH = 3  # skills/<name>/SKILL.md
_SKILL_MEMBER_MIN_DEPTH = 2  # skills/<name>
_RESOURCE_ROOTS = frozenset({"skills", "instructions", "prompts", "hooks"})
_PROMPT_PATH_DEPTH = 2  # prompts/<name>.prompt.md
_HOOK_REGISTRATION_DEPTH = 2  # hooks/<name>.json
_PROMPT_FIELDS = frozenset({"description", "argument-hint", "agent"})
_CATALOG_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_JSON_INDENT = 2
_DEFAULT_POLICY_LINES = 120
_MCP_ALLOWED = (
    "azure",
    "chrome-devtools",
    "context7",
    "github",
    "langfuse-docs",
    "microsoft-learn",
    "playwright",
    "postman",
    "shadcn",
    "storybook",
    "temporal-docs",
    "terraform",
)
_SECURITY_POLICY = {
    "integrity": {"require_hashes": True},
    "audit": {"fail_on_drift": True},
}
_POLICY = {
    "name": "Agent Kit source and dependency policy",
    "version": "1.0.0",
    "enforcement": "block",
    "fetch_failure": "block",
    "dependencies": {"allow": []},
    "mcp": {
        "allow": list(_MCP_ALLOWED),
        "self_defined": "allow",
        "trust_transitive": False,
        "transport": {"allow": ["http", "stdio"]},
    },
    "manifest": {
        "required_fields": ["name", "version", "includes", "license"],
        "require_explicit_includes": True,
        "scripts": "deny",
    },
    "security": _SECURITY_POLICY,
}
_POLICY_SCALARS = ("name", "version", "enforcement", "fetch_failure")
_POLICY_SECTIONS = {
    "dependencies": {"allow"},
    "mcp": {"allow", "self_defined", "trust_transitive", "transport"},
    "manifest": {"required_fields", "require_explicit_includes", "scripts"},
    "security": {"integrity", "audit"},
}
_MANIFEST_REQUIRED = frozenset(
    {
        "name",
        "version",
        "targets",
        "includes",
        "dependencies",
        "executables",
        "license",
    }
)
_MANIFEST_ALLOWED = _MANIFEST_REQUIRED | {"description"}
_SKILL_SCOPE_KEYS = frozenset({"applyto", "apply_to", "scope", "paths"})


class _SkillRecord(NamedTuple):
    """Validated skill facts used by budget and profile summaries."""

    description: str
    body_lines: int
    bundle: str


@unique
class CompositionIssue(StrEnum):
    """Closed set of composition precondition failures."""

    SOURCE_INVALID = "source validation failed; composition was not planned"
    CATALOG_INVALID = "catalog is invalid"
    RUNTIME_SELECTION = "runtime targets must be non-empty and unique"
    UNSUPPORTED_RUNTIME = "runtime target is not supported by this catalog"
    DUPLICATE_SKILLS = "session skill identifiers must be unique"
    DESCRIPTION_BUDGET = "selected profile exceeds the description character budget"
    POLICY_UNAVAILABLE = "source policy cannot be copied"
    LICENSE_UNAVAILABLE = "root license cannot be copied"
    MCP_CONFLICT = "selected bundles declare one MCP server differently"


class CompositionError(ValueError):
    """A source or selection precondition prevents safe composition."""

    def __init__(self, issue: CompositionIssue) -> None:
        """Record the failed precondition with its stable diagnostic.

        Args:
            issue (CompositionIssue): Failed composition invariant.
        """
        self.issue = issue
        super().__init__(issue.value)


class UnknownProfileError(ValueError):
    """A selected profile does not exist in the validated catalog."""

    def __init__(
        self, name: str, *, kind: Literal["profile", "feature profile"] = "profile"
    ) -> None:
        """Identify the unknown selection.

        Args:
            name (str): Selected profile name.
            kind (Literal["profile", "feature profile"]): Profile selection category.
        """
        super().__init__(f"unknown {kind} '{name}'")


class UnavailableSkillsError(ValueError):
    """Requested session skills are absent from the selected profile."""

    def __init__(self, skills: set[str]) -> None:
        """List unavailable identifiers in deterministic order.

        Args:
            skills (set[str]): Unavailable skill identifiers.
        """
        super().__init__(
            f"skills unavailable in selected profile: {', '.join(sorted(skills))}"
        )


class UnavailableBundleError(ValueError):
    """The source snapshot is missing a selected bundle."""

    def __init__(self, name: str) -> None:
        """Identify the unavailable source.

        Args:
            name (str): Selected bundle name.
        """
        super().__init__(f"source bundle '{name}' is unavailable")


class CompositionCollisionError(ValueError):
    """Multiple sources would occupy the same case-insensitive output path."""

    def __init__(self, *, previous: str, relative: str) -> None:
        """Identify conflicting destinations.

        Args:
            previous (str): First source destination.
            relative (str): Colliding source destination.
        """
        super().__init__(
            f"case-insensitive composition collision: '{previous}' and '{relative}'"
        )


class OmittedResourceError(ValueError):
    """A session selection omits a resource needed by one of its skills."""

    def __init__(self, finding: Finding) -> None:
        """Retain the actionable resource finding.

        Args:
            finding (Finding): First missing resource dependency.
        """
        self.finding = finding
        super().__init__(
            f"session selection has an omitted resource: {finding.path}: "
            f"{finding.message}; add its owning skill explicitly"
        )


def _is_text(value: object) -> TypeGuard[str]:
    """Check for a non-empty string, whitespace included."""
    return isinstance(value, str) and bool(value)


def _is_semantic_version(value: object) -> TypeGuard[str]:
    """Check for a ``MAJOR.MINOR.PATCH`` version string with optional suffix."""
    return isinstance(value, str) and _VERSION.fullmatch(value) is not None


def _finding(findings: list[Finding], code: str, message: str, path: str) -> None:
    """Append one source-relative diagnostic.

    Args:
        findings (list[Finding]): Accumulator that receives the finding.
        code (str): Stable dotted diagnostic code.
        message (str): Safe human-readable explanation.
        path (str): Source-relative location of the problem.
    """
    findings.append(Finding(code=code, message=message, path=path))


def _exact_mapping(
    value: object,
    expected: set[str],
    path: str,
    findings: list[Finding],
) -> JsonObject | None:
    """Require a mapping with exactly the declared keys.

    Args:
        value (object): Decoded value to inspect.
        expected (set[str]): Exact field names the mapping must declare.
        path (str): Source-relative location used in findings.
        findings (list[Finding]): Accumulator for schema findings.

    Returns:
        JsonObject | None: ``value`` when it is a string-keyed mapping, even if
        fields are missing or unknown (each is reported); ``None`` otherwise.
    """
    if not is_json_object(value):
        _finding(findings, "schema.mapping", "expected an object", path)
        return None
    actual = set(value)
    for name in sorted(expected - actual):
        _finding(findings, "schema.missing", f"missing field '{name}'", path)
    for name in sorted(actual - expected):
        _finding(findings, "schema.unknown", f"unknown field '{name}'", path)
    return value


def _string_list(
    value: object, path: str, findings: list[Finding]
) -> tuple[str, ...] | None:
    """Validate a list of unique, non-empty strings.

    Args:
        value (object): Decoded value to inspect.
        path (str): Source-relative location used in findings.
        findings (list[Finding]): Accumulator for schema findings.

    Returns:
        tuple[str, ...] | None: Entries in source order, duplicates included
        after reporting them; ``None`` when ``value`` is not a list or holds an
        empty or non-string entry.
    """
    if not isinstance(value, list):
        _finding(findings, "schema.list", "expected a list of strings", path)
        return None
    strings: list[str] = []
    for index, item in enumerate(value):
        if not _is_text(item):
            _finding(
                findings,
                "schema.string",
                "expected a non-empty string",
                f"{path}[{index}]",
            )
            return None
        strings.append(item)
    if len(set(strings)) != len(strings):
        _finding(findings, "schema.duplicate", "duplicate list entry", path)
    return tuple(strings)


def _same_value(actual: object, expected: object) -> bool:
    """Compare nested policy values without Python bool/integer equivalence.

    Args:
        actual (object): Decoded value from the source policy.
        expected (object): Released contract value.
    """
    if type(actual) is not type(expected):
        return False
    if is_json_object(actual) and is_json_object(expected):
        return actual.keys() == expected.keys() and all(
            _same_value(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_value(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return actual == expected


def _is_absolute(value: str) -> bool:
    """Detect POSIX, Windows, and drive-qualified absolute paths."""
    windows = PureWindowsPath(value)
    return (
        PurePosixPath(value).is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
    )


def _contained_catalog_path(value: object) -> str | None:
    """Validate a normalized, relative source bundle path."""
    if not _is_text(value) or "\\" in value:
        return None
    posix = PurePosixPath(value)
    if _is_absolute(value) or any(part == ".." for part in posix.parts):
        return None
    normalized = posix.as_posix()
    if normalized == ".":
        return "."
    if normalized.startswith("./") or normalized.endswith("/"):
        return None
    return normalized


def _unvisited_members(current: object, visited: set[int]) -> tuple[object, ...]:
    """Return the keys, values, or items of a container not yet traversed.

    Args:
        current (object): Decoded value that may be a container.
        visited (set[int]): Identities of containers already traversed; updated.

    Returns:
        tuple[object, ...]: Dict keys and values, or list items, flattened; empty
        for scalars and containers seen before.
    """
    if not isinstance(current, dict | list) or id(current) in visited:
        return ()
    visited.add(id(current))
    if isinstance(current, dict):
        return tuple(part for pair in current.items() for part in pair)
    return tuple(current)


def _contains_hidden_unicode(value: object) -> bool:
    """Find unsupported format and control characters in decoded content."""
    pending: list[object] = [value]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str) and not visible_text(current):
            return True
        pending.extend(_unvisited_members(current, visited))
    return False


def _check_hidden_unicode(value: object, path: str, findings: list[Finding]) -> None:
    """Record a safe diagnostic without including the offending text.

    Args:
        value (object): Decoded content to scan.
        path (str): Source-relative location used in the finding.
        findings (list[Finding]): Accumulator for the finding.
    """
    if _contains_hidden_unicode(value):
        _finding(
            findings,
            "unicode.hidden",
            "source content contains unsupported hidden Unicode controls",
            path,
        )


def _body_text(text: str) -> str | None:
    """Extract skill body following its YAML frontmatter delimiters."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            return "\n".join(lines[index + 1 :])
    return None


def _is_project_contact(parsed: SplitResult) -> bool:
    """Accept a plain ``mailto:`` address without query, fragment, or escapes."""
    address = unquote(parsed.path)
    return (
        parsed.scheme.lower() == "mailto"
        and not parsed.netloc
        and not parsed.query
        and not parsed.fragment
        and parsed.path == address
        and _EMAIL.fullmatch(address) is not None
    )


def _external_link_allowed(parsed: SplitResult, *, base_is_bundle: bool) -> bool:
    """Allow web links everywhere and project contacts outside bundles.

    Args:
        parsed (SplitResult): Link with a scheme or network location.
        base_is_bundle (bool): Whether the owning document lives in a bundle,
            where project contacts are not allowed.
    """
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return True
    return not base_is_bundle and _is_project_contact(parsed)


def _resolved_link(raw_path: str, document_path: str) -> str | None:
    """Resolve a relative link beside its document.

    Args:
        raw_path (str): Decoded relative link path.
        document_path (str): Source-relative path of the linking document.

    Returns:
        str | None: Source-relative target path, or ``None`` when the link
        climbs above the source root.
    """
    stack = list(PurePosixPath(document_path).parent.parts)
    for part in PurePosixPath(raw_path).parts:
        if part == "..":
            if not stack:
                return None
            stack.pop()
        elif part not in {"", "."}:
            stack.append(part)
    return "/".join(stack)


def _link_index(available_paths: Iterable[str]) -> frozenset[str]:
    """Index every source path and ancestor directory once for link lookups."""
    index: set[str] = set()
    for path in available_paths:
        index.add(path)
        parent, separator, _ = path.rpartition("/")
        while separator and parent and parent not in index:
            index.add(parent)
            parent, separator, _ = parent.rpartition("/")
    return frozenset(index)


def _local_link_issue(
    raw_path: str, document_path: str, link_index: AbstractSet[str]
) -> tuple[str, str] | None:
    """Classify an invalid local link, matching exact case-sensitive spelling.

    Args:
        raw_path (str): Decoded relative link path.
        document_path (str): Source-relative path of the linking document.
        link_index (AbstractSet[str]): Every file and directory path available.

    Returns:
        tuple[str, str] | None: Finding ``(code, message)`` for an invalid link,
        or ``None`` when the target exists.
    """
    if "\\" in raw_path:
        return "links.path", "resource link is not a portable path"
    target = None if _is_absolute(raw_path) else _resolved_link(raw_path, document_path)
    if target is None:
        return "links.escape", "resource link escapes its source root"
    if target in link_index:
        return None
    return "links.missing", f"resource link target does not exist: {raw_path}"


def _link_target(
    link: str,
    document_path: str,
    link_index: AbstractSet[str],
    findings: list[Finding],
    *,
    base_is_bundle: bool,
) -> None:
    """Verify a Markdown resource target stays in its owning source root.

    Args:
        link (str): Raw Markdown link target.
        document_path (str): Source-relative path of the linking document.
        link_index (AbstractSet[str]): Every file and directory path available.
        findings (list[Finding]): Accumulator for link findings.
        base_is_bundle (bool): Whether the document lives in a bundle.
    """
    parsed = urlsplit(link)
    if parsed.scheme or parsed.netloc:
        if not _external_link_allowed(parsed, base_is_bundle=base_is_bundle):
            _finding(
                findings,
                "links.scheme",
                "unsupported external link or invalid project contact",
                document_path,
            )
        return
    raw_path = unquote(parsed.path)
    if not raw_path:
        return
    issue = _local_link_issue(raw_path, document_path, link_index)
    if issue is not None:
        code, message = issue
        _finding(findings, code, message, document_path)


def _check_links(
    document: SourceDocument,
    link_index: AbstractSet[str],
    findings: list[Finding],
    *,
    base_is_bundle: bool,
) -> None:
    """Validate Markdown documents, not Python expressions or template data.

    Args:
        document (SourceDocument): Captured document; non-Markdown, template, or
            non-text documents are skipped.
        link_index (AbstractSet[str]): Every file and directory path available.
        findings (list[Finding]): Accumulator for link findings.
        base_is_bundle (bool): Whether the document lives in a bundle.
    """
    text = document.text
    name = PurePosixPath(document.relative_path).name.casefold()
    markdown = PurePosixPath(name).suffix in {".md", ".markdown"} or name == "llms.txt"
    if text is None or not markdown or ".template." in name:
        return
    for link in markdown_link_targets(text):
        _link_target(
            link,
            document.relative_path,
            link_index,
            findings,
            base_is_bundle=base_is_bundle,
        )


def _policy_value_finding(findings: list[Finding], key: str, path: str) -> None:
    """Report one policy value that differs from the released contract.

    Args:
        findings (list[Finding]): Accumulator for the finding.
        key (str): Policy field whose value is unsupported.
        path (str): Source-relative policy location.
    """
    _finding(findings, "policy.value", f"unsupported policy value for '{key}'", path)


def _policy_scalars_valid(top: JsonObject, path: str, findings: list[Finding]) -> bool:
    """Compare top-level scalar policy values with the released contract.

    Args:
        top (JsonObject): Policy document with exactly the declared fields.
        path (str): Source-relative policy location.
        findings (list[Finding]): Accumulator for value findings.
    """
    valid = True
    for key in _POLICY_SCALARS:
        if top.get(key) != _POLICY[key]:
            _policy_value_finding(findings, key, path)
            valid = False
    return valid


def _security_policy_valid(
    security: JsonObject, path: str, findings: list[Finding]
) -> bool:
    """Require the exact nested integrity and audit security settings.

    Args:
        security (JsonObject): The policy's ``security`` section.
        path (str): Source-relative policy location.
        findings (list[Finding]): Accumulator for shape and value findings.
    """
    valid = True
    for child, expected in _SECURITY_POLICY.items():
        nested = _exact_mapping(
            security.get(child), set(expected), f"{path}:security:{child}", findings
        )
        if nested is None:
            valid = False
        elif not _same_value(nested, expected):
            _policy_value_finding(findings, child, path)
            valid = False
    return valid


def _policy_section_valid(
    top: JsonObject, key: str, path: str, findings: list[Finding]
) -> bool:
    """Require one nested policy section to match its released shape and values.

    Args:
        top (JsonObject): Policy document with exactly the declared fields.
        key (str): Name of the section to validate.
        path (str): Source-relative policy location.
        findings (list[Finding]): Accumulator for shape and value findings.
    """
    nested = _exact_mapping(
        top.get(key), _POLICY_SECTIONS[key], f"{path}:{key}", findings
    )
    if nested is None:
        return False
    if key == "security":
        return _security_policy_valid(nested, path, findings)
    if _same_value(nested, _POLICY.get(key)):
        return True
    _policy_value_finding(findings, key, path)
    return False


def _policy_mapping(value: object, path: str, findings: list[Finding]) -> bool:
    """Require the exact released strict policy contract.

    Args:
        value (object): Decoded policy document.
        path (str): Source-relative policy location.
        findings (list[Finding]): Accumulator for shape and value findings.
    """
    top = _exact_mapping(value, set(_POLICY), path, findings)
    if top is None:
        return False
    results = [_policy_scalars_valid(top, path, findings)]
    results.extend(
        _policy_section_valid(top, key, path, findings) for key in _POLICY_SECTIONS
    )
    return all(results) and _same_value(top, _POLICY)


def _catalog_schema_version(raw: JsonObject, findings: list[Finding]) -> int | None:
    """Return the supported catalog schema version or report it.

    Args:
        raw (JsonObject): Decoded catalog document.
        findings (list[Finding]): Accumulator for version findings.
    """
    value = raw.get("schema_version")
    if is_int(value) and value == 1:
        return value
    _finding(findings, "catalog.version", "schema_version must be 1", "catalog.json")
    return None


def _catalog_version(raw: JsonObject, findings: list[Finding]) -> str | None:
    """Return the semantic catalog version or report it.

    Args:
        raw (JsonObject): Decoded catalog document.
        findings (list[Finding]): Accumulator for version findings.
    """
    value = raw.get("version")
    if _is_semantic_version(value):
        return value
    _finding(
        findings,
        "catalog.version",
        "version must be a semantic version",
        "catalog.json",
    )
    return None


def _catalog_runtimes(
    raw: JsonObject, findings: list[Finding]
) -> tuple[str, ...] | None:
    """Return the exact supported runtime list or report it.

    Args:
        raw (JsonObject): Decoded catalog document.
        findings (list[Finding]): Accumulator for runtime findings.

    Returns:
        tuple[str, ...] | None: ``("copilot", "claude")`` in that order, or
        ``None`` when the list is malformed or differs.
    """
    location = "catalog.json:supported_runtimes"
    runtimes = _string_list(raw.get("supported_runtimes"), location, findings)
    if runtimes is None or runtimes == ("copilot", "claude"):
        return runtimes
    _finding(
        findings,
        "catalog.runtime",
        "supported runtimes must be exactly copilot and claude",
        location,
    )
    return None


def _catalog_budgets(
    raw: JsonObject, findings: list[Finding]
) -> tuple[tuple[str, int], ...]:
    """Return every valid positive budget in sorted field order.

    Args:
        raw (JsonObject): Decoded catalog document.
        findings (list[Finding]): Accumulator for budget findings.

    Returns:
        tuple[tuple[str, int], ...]: ``(field, limit)`` pairs sorted by field;
        fields with invalid values are reported and omitted.
    """
    budgets_raw = _exact_mapping(
        raw.get("budgets"), _BUDGET_FIELDS, "catalog.json:budgets", findings
    )
    if budgets_raw is None:
        return ()
    budgets: list[tuple[str, int]] = []
    for key in sorted(_BUDGET_FIELDS):
        value = budgets_raw.get(key)
        if is_int(value) and value > 0:
            budgets.append((key, value))
        else:
            _finding(
                findings,
                "catalog.budget",
                f"'{key}' must be a positive integer",
                "catalog.json:budgets",
            )
    return tuple(budgets)


def _parse_catalog(
    snapshot: CatalogSnapshot, findings: list[Finding]
) -> Catalog | None:
    """Validate exact catalog fields and build typed selection values.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        findings (list[Finding]): Accumulator for schema findings.

    Returns:
        Catalog | None: Typed catalog, or ``None`` when any part is unusable.
    """
    if snapshot.catalog_error or snapshot.catalog is None:
        _finding(
            findings,
            "catalog.read",
            "catalog.json is missing or invalid",
            "catalog.json",
        )
        return None
    raw = _exact_mapping(snapshot.catalog, _CATALOG_FIELDS, "catalog.json", findings)
    if raw is None:
        return None
    schema_version = _catalog_schema_version(raw, findings)
    version = _catalog_version(raw, findings)
    runtimes = _catalog_runtimes(raw, findings)
    budgets = _catalog_budgets(raw, findings)
    bundles = _parse_bundles(raw.get("bundles"), findings)
    profiles = _parse_profiles(raw.get("profiles"), findings)
    if bundles is not None and profiles is not None:
        _check_references(bundles, profiles, findings)
        _check_profile_cycles(profiles, findings)

    if (
        schema_version is None
        or version is None
        or runtimes is None
        or len(budgets) != len(_BUDGET_FIELDS)
        or bundles is None
        or profiles is None
    ):
        return None
    return Catalog(
        budgets=budgets,
        bundles=bundles,
        profiles=profiles,
        schema_version=schema_version,
        supported_runtimes=runtimes,
        version=version,
    )


def _parse_bundle(
    name: str, raw_bundle: object, findings: list[Finding]
) -> Bundle | None:
    """Validate one named source bundle declaration.

    Args:
        name (str): Bundle name from the catalog.
        raw_bundle (object): Decoded bundle declaration.
        findings (list[Finding]): Accumulator for schema findings.
    """
    location = f"catalog.json:bundles:{name}"
    if _CATALOG_NAME.fullmatch(name) is None:
        _finding(findings, "catalog.name", "bundle name is not legal", location)
    item = _exact_mapping(raw_bundle, {"path", "kind"}, location, findings)
    if item is None:
        return None
    path = _contained_catalog_path(item.get("path"))
    if path is None:
        _finding(
            findings,
            "catalog.path",
            "bundle path must be relative and contained in the source root",
            location,
        )
        return None
    match item.get("kind"):
        case "project":
            return Bundle(kind="project", name=name, path=path)
        case "portable":
            return Bundle(kind="portable", name=name, path=path)
        case _:
            _finding(findings, "catalog.kind", "bundle kind is invalid", location)
            return None


def _parse_section[T](
    value: object,
    section: str,
    parse: Callable[[str, object, list[Finding]], T | None],
    findings: list[Finding],
) -> tuple[T, ...] | None:
    """Validate every named entry of a catalog section such as ``bundles``.

    Args:
        value (object): Decoded section object.
        section (str): Plural section name, such as ``bundles``.
        parse (Callable[[str, object, list[Finding]], T | None]): Entry parser
            taking the entry name, its decoded value, and the findings list.
        findings (list[Finding]): Accumulator for schema findings.

    Returns:
        tuple[T, ...] | None: Entries that parsed, in source order (reported
        when empty); ``None`` when ``value`` is not an object.
    """
    if not is_json_object(value):
        _finding(
            findings,
            f"catalog.{section}",
            f"{section} must be an object",
            "catalog.json",
        )
        return None
    parsed = (parse(name, item, findings) for name, item in value.items())
    entries = tuple(entry for entry in parsed if entry is not None)
    if not entries:
        _finding(
            findings,
            f"catalog.{section}",
            f"at least one {section.removesuffix('s')} is required",
            "catalog.json",
        )
    return entries


def _parse_bundles(value: object, findings: list[Finding]) -> tuple[Bundle, ...] | None:
    """Validate every named source bundle.

    Args:
        value (object): Decoded ``bundles`` section.
        findings (list[Finding]): Accumulator for schema findings.

    Returns:
        tuple[Bundle, ...] | None: Valid bundles, or ``None`` for a non-object.
    """
    return _parse_section(value, "bundles", _parse_bundle, findings)


def _parse_profile(
    name: str, raw_profile: object, findings: list[Finding]
) -> Profile | None:
    """Validate one profile's inheritance and direct bundle references.

    Args:
        name (str): Profile name from the catalog.
        raw_profile (object): Decoded profile declaration.
        findings (list[Finding]): Accumulator for schema findings.
    """
    location = f"catalog.json:profiles:{name}"
    if _CATALOG_NAME.fullmatch(name) is None:
        _finding(findings, "catalog.name", "profile name is not legal", location)
    item = _exact_mapping(raw_profile, {"extends", "bundles"}, location, findings)
    if item is None:
        return None
    extends = _string_list(item.get("extends"), f"{location}:extends", findings)
    bundles = _string_list(item.get("bundles"), f"{location}:bundles", findings)
    if extends is None or bundles is None:
        return None
    return Profile(bundles=bundles, extends=extends, name=name)


def _parse_profiles(
    value: object, findings: list[Finding]
) -> tuple[Profile, ...] | None:
    """Validate profile inheritance and direct bundle references.

    Args:
        value (object): Decoded ``profiles`` section.
        findings (list[Finding]): Accumulator for schema findings.

    Returns:
        tuple[Profile, ...] | None: Valid profiles, or ``None`` for a non-object.
    """
    return _parse_section(value, "profiles", _parse_profile, findings)


def _check_references(
    bundles: tuple[Bundle, ...],
    profiles: tuple[Profile, ...],
    findings: list[Finding],
) -> None:
    """Report missing bundle or profile references.

    Args:
        bundles (tuple[Bundle, ...]): Declared bundles.
        profiles (tuple[Profile, ...]): Declared profiles.
        findings (list[Finding]): Accumulator for reference findings.
    """
    bundle_names = {item.name for item in bundles}
    profile_names = {item.name for item in profiles}
    for profile in profiles:
        for name in profile.extends:
            if name not in profile_names:
                _finding(
                    findings,
                    "profile.reference",
                    f"profile extends unknown profile '{name}'",
                    f"catalog.json:profiles:{profile.name}",
                )
        for name in profile.bundles:
            if name not in bundle_names:
                _finding(
                    findings,
                    "profile.reference",
                    f"profile selects unknown bundle '{name}'",
                    f"catalog.json:profiles:{profile.name}",
                )


def _check_profile_cycles(
    profiles: tuple[Profile, ...], findings: list[Finding]
) -> None:
    """Report all profiles participating in inheritance cycles.

    Args:
        profiles (tuple[Profile, ...]): Declared profiles.
        findings (list[Finding]): Accumulator for cycle findings.
    """
    profile_map = {item.name: item for item in profiles}
    active: set[str] = set()
    complete: set[str] = set()

    def visit(name: str) -> None:
        if name in active:
            _finding(
                findings,
                "profile.cycle",
                f"profile inheritance cycle includes '{name}'",
                f"catalog.json:profiles:{name}",
            )
            return
        if name in complete or name not in profile_map:
            return
        active.add(name)
        for parent in profile_map[name].extends:
            visit(parent)
        active.remove(name)
        complete.add(name)

    for profile in profiles:
        visit(profile.name)


def _include_profile(
    name: str,
    profiles: dict[str, Profile],
    selected: list[str],
    visited: set[str],
) -> None:
    """Append a profile's inherited and direct bundles in first-seen order.

    Args:
        name (str): Profile to include.
        profiles (dict[str, Profile]): Every declared profile by name.
        selected (list[str]): Ordered bundle names; extended in place.
        visited (set[str]): Profiles already included; extended in place.

    Raises:
        UnknownProfileError: The profile is not in the catalog.
    """
    profile = profiles.get(name)
    if profile is None:
        raise UnknownProfileError(name)
    if name in visited:
        return
    visited.add(name)
    for parent in profile.extends:
        _include_profile(parent, profiles, selected, visited)
    for bundle in profile.bundles:
        if bundle not in selected:
            selected.append(bundle)


def _effective_bundles(
    catalog: Catalog, profile_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve profile inheritance into an ordered unique bundle union.

    Args:
        catalog (Catalog): Validated catalog.
        profile_names (tuple[str, ...]): Profiles whose bundles are unioned; an
            unknown name propagates ``UnknownProfileError``.

    Returns:
        tuple[str, ...]: Bundle names, inherited ones before direct ones, in
        first-seen order without repeats.
    """
    profiles = {item.name: item for item in catalog.profiles}
    selected: list[str] = []
    visited: set[str] = set()
    for name in profile_names:
        _include_profile(name, profiles, selected, visited)
    return tuple(selected)


def _resolved_profiles(
    catalog: Catalog,
) -> Iterator[tuple[Profile, tuple[str, ...]]]:
    """Yield each profile with its effective bundles, skipping unresolvable ones.

    Args:
        catalog (Catalog): Catalog whose profiles are resolved; profiles that
            reference unknown parents are skipped because validation reports them.

    Yields:
        tuple[Profile, tuple[str, ...]]: The profile and its effective bundle
        names in first-seen order.
    """
    for profile in catalog.profiles:
        try:
            selected = _effective_bundles(catalog, (profile.name,))
        except ValueError:
            continue
        yield profile, selected


def _covers(prefix: str, path: str) -> bool:
    """Check whether ``path`` equals ``prefix`` or lies beneath it.

    Args:
        prefix (str): Include path, file or directory.
        path (str): Candidate resource path.
    """
    return path == prefix or path.startswith(f"{prefix}/")


def _manifest_mapping(
    bundle: BundleSource, location: str, findings: list[Finding]
) -> JsonObject | None:
    """Return a readable manifest object or report why it is unusable.

    Args:
        bundle (BundleSource): Captured bundle whose manifest is read.
        location (str): Source-relative manifest path used in findings.
        findings (list[Finding]): Accumulator for manifest findings.
    """
    if bundle.manifest_error or bundle.manifest is None:
        _finding(findings, "manifest.read", "apm.yml is missing or invalid", location)
        return None
    manifest = bundle.manifest
    if not is_json_object(manifest):
        _finding(findings, "manifest.schema", "manifest must be an object", location)
        return None
    return manifest


def _check_manifest_fields(
    manifest: JsonObject, location: str, findings: list[Finding]
) -> None:
    """Report missing, unknown, prohibited, and unlicensed manifest fields.

    Args:
        manifest (JsonObject): Decoded bundle manifest.
        location (str): Source-relative manifest path used in findings.
        findings (list[Finding]): Accumulator for manifest findings.
    """
    for field in sorted(_MANIFEST_REQUIRED - set(manifest)):
        _finding(findings, "manifest.missing", f"missing field '{field}'", location)
    for field in sorted(set(manifest) - _MANIFEST_ALLOWED):
        _finding(findings, "manifest.unknown", f"unknown field '{field}'", location)
    if "scripts" in manifest:
        _finding(
            findings, "manifest.scripts", "manifest scripts are prohibited", location
        )
    if manifest.get("license") != "MIT":
        _finding(
            findings, "manifest.license", "toolkit bundles must declare MIT", location
        )
    if not _is_text(manifest.get("name")):
        _finding(findings, "manifest.name", "manifest name is required", location)


def _check_manifest_version(
    manifest: JsonObject, version: str, location: str, findings: list[Finding]
) -> None:
    """Require a semantic manifest version equal to the catalog version.

    Args:
        manifest (JsonObject): Decoded bundle manifest.
        version (str): Catalog version the manifest must match.
        location (str): Source-relative manifest path used in findings.
        findings (list[Finding]): Accumulator for manifest findings.
    """
    manifest_version = manifest.get("version")
    if not _is_semantic_version(manifest_version):
        _finding(findings, "manifest.version", "manifest version is invalid", location)
    elif manifest_version != version:
        _finding(
            findings,
            "manifest.version",
            "manifest version must match catalog version",
            location,
        )


def _check_manifest_targets(
    targets: tuple[str, ...] | None,
    supported_runtimes: tuple[str, ...],
    location: str,
    findings: list[Finding],
) -> None:
    """Require non-empty manifest targets drawn from supported runtimes.

    Args:
        targets (tuple[str, ...] | None): Declared targets; ``None`` when the
            field was already reported as malformed.
        supported_runtimes (tuple[str, ...]): Runtimes the catalog supports.
        location (str): Source-relative manifest path used in findings.
        findings (list[Finding]): Accumulator for manifest findings.
    """
    if targets is not None and (
        not targets or any(runtime not in supported_runtimes for runtime in targets)
    ):
        _finding(findings, "manifest.targets", "manifest targets are invalid", location)


def _check_manifest_executables(
    manifest: JsonObject, location: str, findings: list[Finding]
) -> None:
    """Require empty ``executables`` and only validated MCP dependencies.

    Args:
        manifest (JsonObject): Decoded bundle manifest.
        location (str): Source-relative manifest path used in findings.
        findings (list[Finding]): Accumulator for manifest findings.
    """
    if manifest.get("executables") != {}:
        _finding(
            findings, "manifest.executables", "executables must be empty", location
        )
    dependencies = manifest.get("dependencies")
    if not is_json_object(dependencies) or set(dependencies) - {"mcp"}:
        _finding(
            findings,
            "manifest.dependencies",
            "dependencies may only declare mcp servers",
            location,
        )
    elif "mcp" in dependencies:
        for issue in mcp_issues(dependencies["mcp"], allowed=_MCP_ALLOWED):
            _finding(findings, "manifest.mcp", issue, location)


def _include_issue(include: str, path: PurePosixPath) -> str | None:
    """Return why an include is not a contained ``.apm`` path, if it is not.

    Args:
        include (str): Raw manifest include.
        path (PurePosixPath): ``include`` without trailing slashes.
    """
    if not include.startswith(".apm/") or "\\" in include:
        return "includes must name paths beneath .apm"
    if path.is_absolute() or any(part in {"..", "."} for part in path.parts[1:]):
        return "include path escapes .apm"
    return None


def _normalized_includes(
    includes: tuple[str, ...], location: str, findings: list[Finding]
) -> tuple[str, ...]:
    """Return valid includes relative to ``.apm`` and report the others.

    Args:
        includes (tuple[str, ...]): Declared manifest include paths.
        location (str): Source-relative manifest path used in findings.
        findings (list[Finding]): Accumulator for include findings.
    """
    normalized: list[str] = []
    for include in includes:
        path = PurePosixPath(include.rstrip("/"))
        issue = _include_issue(include, path)
        if issue is None:
            normalized.append(path.relative_to(".apm").as_posix())
        else:
            _finding(findings, "manifest.includes", issue, location)
    return tuple(normalized)


def _check_include_coverage(
    bundle: BundleSource,
    normalized: tuple[str, ...],
    location: str,
    findings: list[Finding],
) -> None:
    """Require every include to match resources and every resource to be included.

    Args:
        bundle (BundleSource): Captured bundle with its resource files.
        normalized (tuple[str, ...]): Includes relative to ``.apm``.
        location (str): Source-relative manifest path used in findings.
        findings (list[Finding]): Accumulator for include findings.
    """
    available = {item.relative_path for item in bundle.files}
    for include in normalized:
        if not any(_covers(include, item) for item in available):
            _finding(
                findings,
                "manifest.includes",
                f"include path has no resources: .apm/{include}",
                location,
            )
    for source in bundle.files:
        if not any(_covers(include, source.relative_path) for include in normalized):
            _finding(
                findings,
                "manifest.includes",
                f"resource is not covered by an include: {source.relative_path}",
                location,
            )


def _included_paths(
    bundle: BundleSource,
    findings: list[Finding],
    version: str,
    supported_runtimes: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate source APM metadata and return explicit ``.apm`` include roots.

    Args:
        bundle (BundleSource): Captured bundle whose manifest is validated.
        findings (list[Finding]): Accumulator for manifest findings.
        version (str): Catalog version the manifest must match.
        supported_runtimes (tuple[str, ...]): Runtimes the catalog supports.

    Returns:
        tuple[str, ...]: Valid include paths relative to ``.apm``; empty when the
        manifest or its ``includes`` field is unusable.
    """
    location = f"{bundle.path}/apm.yml"
    manifest = _manifest_mapping(bundle, location, findings)
    if manifest is None:
        return ()
    _check_manifest_fields(manifest, location, findings)
    _check_manifest_version(manifest, version, location, findings)
    targets = _string_list(manifest.get("targets"), f"{location}:targets", findings)
    includes = _string_list(manifest.get("includes"), f"{location}:includes", findings)
    _check_manifest_targets(targets, supported_runtimes, location, findings)
    _check_manifest_executables(manifest, location, findings)
    if includes is None:
        return ()
    if not includes:
        _finding(
            findings,
            "manifest.includes",
            "manifest must declare explicit includes",
            location,
        )
        return ()
    normalized = _normalized_includes(includes, location, findings)
    _check_include_coverage(bundle, normalized, location, findings)
    return normalized


def _usable_document(
    document: SourceDocument, bundle: BundleSource, findings: list[Finding]
) -> bool:
    """Report unsafe or malformed documents; reject symlinks from validation.

    Args:
        document (SourceDocument): Captured source document.
        bundle (BundleSource): Bundle that owns the document.
        findings (list[Finding]): Accumulator for source findings.

    Returns:
        bool: ``False`` for a symlink or a misplaced resource root, which
        callers skip; ``True`` otherwise, even after reporting parse errors.
    """
    location = f"{bundle.path}/.apm/{document.relative_path}"
    if document.is_symlink:
        _finding(
            findings, "source.symlink", "source bundle contains a symlink", location
        )
        return False
    if document.relative_path in _RESOURCE_ROOTS and not document.is_directory:
        _finding(
            findings,
            "source.root",
            "resource root must be a directory",
            location,
        )
        return False
    if document.parse_error:
        _finding(
            findings,
            "source.parse",
            "source metadata is malformed or unreadable",
            location,
        )
    if document.frontmatter_error:
        _finding(
            findings,
            "frontmatter.parse",
            "Markdown frontmatter is malformed",
            location,
        )
    return True


def _is_markdown_source(relative_path: str) -> bool:
    """Select Markdown sources whose links are validated, excluding templates."""
    path = PurePosixPath(relative_path)
    return (
        path.suffix.lower() in {".md", ".markdown"}
        and ".template." not in path.name.casefold()
    )


def _validate_hook_file(
    document: SourceDocument, bundle: BundleSource, findings: list[Finding]
) -> None:
    """Validate a hook registration or script beneath ``.apm/hooks``.

    Args:
        document (SourceDocument): Captured document under ``hooks/``.
        bundle (BundleSource): Bundle that owns the document.
        findings (list[Finding]): Accumulator for hook findings.
    """
    location = f"{bundle.path}/.apm/{document.relative_path}"
    parts = PurePosixPath(document.relative_path).parts
    if document.is_directory:
        return
    if len(parts) == _HOOK_REGISTRATION_DEPTH and parts[1].endswith(".json"):
        scripts = frozenset(
            PurePosixPath(item.relative_path).name
            for item in bundle.files
            if item.relative_path.startswith("hooks/scripts/") and not item.is_directory
        )
        for issue in hook_issues(document.text or "", scripts):
            _finding(findings, "hooks.registration", issue, location)
    elif len(parts) > _HOOK_REGISTRATION_DEPTH and parts[1] == "scripts":
        issue = script_issue("/".join(parts[_HOOK_REGISTRATION_DEPTH:]))
        if issue is not None:
            _finding(findings, "hooks.script", issue, location)
    else:
        _finding(
            findings,
            "hooks.layout",
            "hooks hold registration JSON files and a scripts directory",
            location,
        )


def _validate_metadata(
    document: SourceDocument,
    bundle: BundleSource,
    records: dict[str, _SkillRecord],
    prompts: set[str],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> None:
    """Dispatch a document to its instruction, prompt, or skill validator.

    Args:
        document (SourceDocument): Captured source document.
        bundle (BundleSource): Bundle that owns the document.
        records (dict[str, _SkillRecord]): Validated skills by name; extended.
        prompts (set[str]): Prompt names seen so far; extended.
        findings (list[Finding]): Accumulator for metadata findings.
        description_limit (int): Maximum description characters.
        body_limit (int): Maximum skill body lines.
    """
    relative = document.relative_path
    if relative.startswith("hooks/"):
        _validate_hook_file(document, bundle, findings)
    if relative.endswith(".instructions.md"):
        _validate_instruction(document, bundle, findings)
    if relative.startswith("prompts/"):
        _validate_prompt(document, bundle, prompts, findings, description_limit)
    if relative.endswith("/SKILL.md") or relative == "SKILL.md":
        _validate_skill(
            document, bundle, records, findings, description_limit, body_limit
        )


def _skill_records(
    bundles: tuple[BundleSource, ...],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> dict[str, _SkillRecord]:
    """Validate skill metadata and return each skill's description and body.

    Args:
        bundles (tuple[BundleSource, ...]): Captured bundles to validate.
        findings (list[Finding]): Accumulator for source and metadata findings.
        description_limit (int): Maximum description characters.
        body_limit (int): Maximum skill body lines.

    Returns:
        dict[str, _SkillRecord]: Valid skills keyed by skill name.
    """
    records: dict[str, _SkillRecord] = {}
    prompts: set[str] = set()
    for bundle in bundles:
        link_index = _link_index(
            item.relative_path for item in bundle.files if not item.is_directory
        )
        for document in bundle.files:
            if not _usable_document(document, bundle, findings):
                continue
            _validate_metadata(
                document,
                bundle,
                records,
                prompts,
                findings,
                description_limit,
                body_limit,
            )
            if _is_markdown_source(document.relative_path):
                _check_links(document, link_index, findings, base_is_bundle=True)
    return records


def _validate_instruction(
    document: SourceDocument,
    bundle: BundleSource,
    findings: list[Finding],
) -> None:
    """Require portable instruction discovery metadata.

    Args:
        document (SourceDocument): Captured instruction document.
        bundle (BundleSource): Bundle that owns the document.
        findings (list[Finding]): Accumulator for instruction findings.
    """
    location = f"{bundle.path}/.apm/{document.relative_path}"
    metadata = document.frontmatter
    if not is_json_object(metadata):
        _finding(
            findings,
            "instruction.frontmatter",
            "instruction metadata is required",
            location,
        )
        return
    for key in ("description", "applyTo"):
        if not _is_text(metadata.get(key)):
            _finding(
                findings,
                "instruction.metadata",
                f"instructions require non-empty '{key}' metadata",
                location,
            )


def _prompt_name(relative_path: str) -> str | None:
    """Return a legal flat ``prompts/kit-<name>.prompt.md`` name, if any."""
    parts = PurePosixPath(relative_path).parts
    name = parts[-1].removesuffix(".prompt.md")
    if (
        len(parts) != _PROMPT_PATH_DEPTH
        or not parts[-1].endswith(".prompt.md")
        or _SKILL_NAME.fullmatch(name) is None
    ):
        return None
    return name


def _one_line(value: object, limit: int) -> TypeGuard[str]:
    """Check for a non-blank, single-line string within ``limit`` characters.

    Args:
        value (object): Decoded candidate.
        limit (int): Maximum characters.
    """
    return is_nonempty_text(value) and "\n" not in value and len(value) <= limit


def _check_prompt_metadata(
    metadata: JsonObject,
    location: str,
    findings: list[Finding],
    description_limit: int,
) -> None:
    """Allow only discovery metadata and a bounded one-line description.

    Args:
        metadata (JsonObject): Decoded prompt frontmatter.
        location (str): Source-relative prompt path used in findings.
        findings (list[Finding]): Accumulator for prompt findings.
        description_limit (int): Maximum description characters.
    """
    for field in sorted(set(metadata) - _PROMPT_FIELDS):
        _finding(
            findings,
            "prompt.metadata",
            f"prompt metadata '{field}' is not allowed; tools and models stay native",
            location,
        )
    if not _one_line(metadata.get("description"), description_limit):
        _finding(
            findings,
            "prompt.description",
            f"prompt description must be one line of at most {description_limit} characters",
            location,
        )


def _validate_prompt(
    document: SourceDocument,
    bundle: BundleSource,
    names: set[str],
    findings: list[Finding],
    description_limit: int,
) -> None:
    """Require a flat, uniquely named prompt with discovery-only metadata.

    Args:
        document (SourceDocument): Captured prompt document.
        bundle (BundleSource): Bundle that owns the document.
        names (set[str]): Prompt names seen so far; extended.
        findings (list[Finding]): Accumulator for prompt findings.
        description_limit (int): Maximum description characters.
    """
    location = f"{bundle.path}/.apm/{document.relative_path}"
    if document.is_directory:
        return
    name = _prompt_name(document.relative_path)
    if name is None:
        _finding(
            findings,
            "prompt.name",
            "prompts must be prompts/kit-<name>.prompt.md",
            location,
        )
        return
    if name in names:
        _finding(findings, "prompt.duplicate", f"duplicate prompt '{name}'", location)
    names.add(name)
    metadata = document.frontmatter
    if not is_json_object(metadata):
        _finding(
            findings, "prompt.frontmatter", "prompt metadata is required", location
        )
        return
    _check_prompt_metadata(metadata, location, findings, description_limit)


def _legal_skill_name(name: object) -> TypeGuard[str]:
    """Check the bounded ``kit-`` skill identifier grammar."""
    return (
        isinstance(name, str)
        and len(name) <= _MAX_SKILL_NAME_CHARS
        and _SKILL_NAME.fullmatch(name) is not None
    )


def _check_skill_identity(
    name: str,
    metadata: JsonObject,
    relative_path: str,
    records: dict[str, _SkillRecord],
    location: str,
    findings: list[Finding],
) -> None:
    """Check skill placement, uniqueness, and absence of native scope metadata.

    Args:
        name (str): Legal skill name from frontmatter.
        metadata (JsonObject): Decoded skill frontmatter.
        relative_path (str): Path of the skill document beneath ``.apm``.
        records (dict[str, _SkillRecord]): Skills validated so far.
        location (str): Source-relative skill path used in findings.
        findings (list[Finding]): Accumulator for identity findings.
    """
    parts = PurePosixPath(relative_path).parts
    if (
        len(parts) != _SKILL_PATH_DEPTH
        or parts[0] != "skills"
        or parts[-1] != "SKILL.md"
    ):
        _finding(
            findings,
            "skill.parent",
            "SKILL.md must be directly beneath skills/<name>",
            location,
        )
    elif name != parts[1]:
        _finding(
            findings,
            "skill.parent",
            "skill name must match its parent directory",
            location,
        )
    if name in records:
        _finding(
            findings, "skill.duplicate", f"duplicate skill name '{name}'", location
        )
    if any(key.casefold() in _SKILL_SCOPE_KEYS for key in metadata):
        _finding(
            findings,
            "skill.scope",
            "native scope metadata is not allowed in skill frontmatter",
            location,
        )


def _skill_description(
    metadata: JsonObject,
    description_limit: int,
    location: str,
    findings: list[Finding],
) -> str | None:
    """Return a required skill description, reporting budget overruns.

    Args:
        metadata (JsonObject): Decoded skill frontmatter.
        description_limit (int): Maximum description characters.
        location (str): Source-relative skill path used in findings.
        findings (list[Finding]): Accumulator for description findings.
    """
    description = metadata.get("description")
    if not _is_text(description):
        _finding(
            findings, "skill.description", "skill description is required", location
        )
        return None
    if len(description) > description_limit:
        _finding(
            findings,
            "budget.description",
            f"skill description exceeds {description_limit} characters",
            location,
        )
    return description


def _skill_body_lines(
    document: SourceDocument, body_limit: int, location: str, findings: list[Finding]
) -> int | None:
    """Return the skill body line count, reporting delimiters and budget.

    Args:
        document (SourceDocument): Captured ``SKILL.md`` document.
        body_limit (int): Maximum skill body lines.
        location (str): Source-relative skill path used in findings.
        findings (list[Finding]): Accumulator for body findings.
    """
    body = _body_text(document.text or "")
    if body is None:
        _finding(
            findings, "skill.body", "skill frontmatter delimiters are invalid", location
        )
        return None
    lines = len(body.splitlines())
    if lines > body_limit:
        _finding(
            findings,
            "budget.skill_body",
            f"skill body exceeds {body_limit} lines",
            location,
        )
    return lines


def _validate_skill(
    document: SourceDocument,
    bundle: BundleSource,
    records: dict[str, _SkillRecord],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> None:
    """Validate a skill name, description, body, and portable metadata.

    Args:
        document (SourceDocument): Captured ``SKILL.md`` document.
        bundle (BundleSource): Bundle that owns the document.
        records (dict[str, _SkillRecord]): Validated skills by name; extended.
        findings (list[Finding]): Accumulator for skill findings.
        description_limit (int): Maximum description characters.
        body_limit (int): Maximum skill body lines.
    """
    location = f"{bundle.path}/.apm/{document.relative_path}"
    metadata = document.frontmatter
    if not is_json_object(metadata):
        _finding(findings, "skill.frontmatter", "skill metadata is required", location)
        return
    name = metadata.get("name")
    if not _legal_skill_name(name):
        _finding(findings, "skill.name", "skill name is not legal", location)
        return
    _check_skill_identity(
        name, metadata, document.relative_path, records, location, findings
    )
    description = _skill_description(metadata, description_limit, location, findings)
    if description is None:
        return
    lines = _skill_body_lines(document, body_limit, location, findings)
    if lines is not None:
        records[name] = _SkillRecord(
            description=description, body_lines=lines, bundle=bundle.name
        )


def _check_root_symlinks(snapshot: CatalogSnapshot, findings: list[Finding]) -> None:
    """Report a symlinked source root and any captured root links.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        findings (list[Finding]): Accumulator for symlink findings.
    """
    if snapshot.root_is_symlink:
        _finding(findings, "source.symlink", "source root is a symlink", ".")
    for relative in snapshot.root_symlinks:
        _finding(
            findings,
            "source.symlink",
            "source root contains a symlink or junction",
            relative,
        )


def _check_policy(snapshot: CatalogSnapshot, findings: list[Finding]) -> None:
    """Require a readable policy document with the strict released contract.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        findings (list[Finding]): Accumulator for policy findings.
    """
    if snapshot.policy_error or snapshot.policy_document is None:
        _finding(
            findings,
            "policy.read",
            "apm-policy.yml is missing or invalid",
            "apm-policy.yml",
        )
    else:
        _policy_mapping(snapshot.policy, "apm-policy.yml", findings)


def _check_source_unicode(snapshot: CatalogSnapshot, findings: list[Finding]) -> None:
    """Reject hidden Unicode in catalog, policy, manifest, and bundle content.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        findings (list[Finding]): Accumulator for Unicode findings.
    """
    if snapshot.catalog_document is not None:
        _check_hidden_unicode(
            snapshot.catalog_document.text or "", "catalog.json", findings
        )
    _check_hidden_unicode(snapshot.catalog, "catalog.json", findings)
    if snapshot.policy_document is not None:
        _check_hidden_unicode(
            snapshot.policy_document.text or "", "apm-policy.yml", findings
        )
    _check_hidden_unicode(snapshot.policy, "apm-policy.yml", findings)
    for bundle in snapshot.bundles:
        manifest_path = f"{bundle.path}/apm.yml"
        _check_hidden_unicode(
            bundle.manifest_document.text or "", manifest_path, findings
        )
        _check_hidden_unicode(bundle.manifest, manifest_path, findings)
        for document in bundle.files:
            path = f"{bundle.path}/.apm/{document.relative_path}"
            _check_hidden_unicode(document.relative_path, path, findings)
            _check_hidden_unicode(document.text or "", path, findings)
            _check_hidden_unicode(document.frontmatter, path, findings)
            _check_hidden_unicode(document.yaml_value, path, findings)


def _policy_line_count(snapshot: CatalogSnapshot) -> int:
    """Count readable policy lines, treating an unreadable policy as empty."""
    document = snapshot.policy_document
    if document is None or document.text is None:
        return 0
    return len(document.text.splitlines())


def _check_root_files(
    root_documents: dict[str, SourceDocument],
    policy_limit: int,
    findings: list[Finding],
) -> None:
    """Require the MIT license and docs index and bound ``AGENTS.md``.

    Args:
        root_documents (dict[str, SourceDocument]): Root documents by path.
        policy_limit (int): Maximum ``AGENTS.md`` lines.
        findings (list[Finding]): Accumulator for root file findings.
    """
    license_document = root_documents.get("LICENSE")
    if (
        license_document is None
        or license_document.text is None
        or not license_document.text.startswith("MIT License")
    ):
        _finding(
            findings,
            "license.read",
            "root MIT license text is missing or invalid",
            "LICENSE",
        )
    if "llms.txt" not in root_documents:
        _finding(findings, "docs.index", "root llms.txt index is missing", "llms.txt")
    agents = root_documents.get("AGENTS.md")
    if (
        agents is not None
        and agents.text is not None
        and len(agents.text.splitlines()) > policy_limit
    ):
        _finding(
            findings,
            "budget.agents",
            f"AGENTS.md exceeds {policy_limit} lines",
            "AGENTS.md",
        )


def _check_root_documentation(
    snapshot: CatalogSnapshot,
    root_documents: dict[str, SourceDocument],
    findings: list[Finding],
) -> None:
    """Require readable, link-safe, non-symlink root documentation.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        root_documents (dict[str, SourceDocument]): Root documents by path.
        findings (list[Finding]): Accumulator for documentation findings.
    """
    root_available = _link_index(
        (
            *snapshot.root_paths,
            *root_documents,
            *(
                f"{bundle.path}/.apm/{source.relative_path}"
                for bundle in snapshot.bundles
                for source in bundle.files
            ),
        )
    )
    for document in snapshot.root_documents:
        if document.is_symlink:
            _finding(
                findings,
                "docs.symlink",
                "root documentation must not be a symlink",
                document.relative_path,
            )
        if document.parse_error or document.text is None:
            _finding(
                findings,
                "docs.read",
                "root documentation is unreadable or not UTF-8 text",
                document.relative_path,
            )
        _check_hidden_unicode(document.text or "", document.relative_path, findings)
        _check_links(document, root_available, findings, base_is_bundle=False)


def _native_assets(
    bundles: tuple[BundleSource, ...], *, selection: _SkillSelection | None = None
) -> dict[str, bytes]:
    """Map authored files, optionally restricted to a composition's selection.

    Args:
        bundles (tuple[BundleSource, ...]): Captured bundles to read.
        selection (_SkillSelection | None): Composition selection that filters
            documents; ``None`` keeps every file.

    Returns:
        dict[str, bytes]: File content keyed by output path
        ``<bundle>/.apm/<relative path>``.
    """
    assets: dict[str, bytes] = {}
    for bundle in bundles:
        prefix = "" if bundle.path == "." else f"{bundle.path}/"
        for document in bundle.files:
            if not document.is_directory and (
                selection is None or _document_selected(document, selection)
            ):
                assets[f"{prefix}.apm/{document.relative_path}"] = document.content
    return assets


def _check_native_selection(
    assets: dict[str, bytes],
    runtimes: tuple[str, ...],
    location: str,
    findings: list[Finding],
    *,
    require_optional: bool = False,
) -> None:
    """Report native roles whose explicit dependencies cannot be rendered.

    Args:
        assets (dict[str, bytes]): Authored file content by output path.
        runtimes (tuple[str, ...]): Native runtimes to render for.
        location (str): Source-relative location used in the finding.
        findings (list[Finding]): Accumulator for native findings.
        require_optional (bool): Whether optional role dependencies must resolve.
    """
    try:
        validate_native_assets(assets, runtimes, require_optional=require_optional)
    except (ValueError, InputTypeError) as error:
        _finding(
            findings,
            "native.assets",
            f"native role assets are invalid: {error}",
            location,
        )


def _check_native_assets(
    snapshot: CatalogSnapshot,
    catalog: Catalog,
    skills: dict[str, _SkillRecord],
    findings: list[Finding],
) -> None:
    """Validate every authored asset and each effective profile's role closure.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        catalog (Catalog): Validated catalog.
        skills (dict[str, _SkillRecord]): Validated skills by name.
        findings (list[Finding]): Accumulator for native findings.
    """
    _check_native_selection(
        _native_assets(snapshot.bundles),
        catalog.supported_runtimes,
        "catalog.json",
        findings,
        require_optional=True,
    )
    for profile, selected in _resolved_profiles(catalog):
        bundles = tuple(item for item in snapshot.bundles if item.name in selected)
        available = {
            name: record for name, record in skills.items() if record.bundle in selected
        }
        selection = _SkillSelection(
            requested=(),
            available=available,
            active=set(available),
            description_chars=sum(len(item.description) for item in available.values()),
        )
        _check_native_selection(
            _native_assets(bundles, selection=selection),
            catalog.supported_runtimes,
            f"catalog.json:profiles:{profile.name}",
            findings,
        )


def _check_bundle_source(
    definition: Bundle,
    source: BundleSource,
    source_paths: dict[str, BundleSource],
    findings: list[Finding],
) -> None:
    """Require a captured bundle to match its declaration and safe ``.apm`` root.

    Args:
        definition (Bundle): Catalog declaration of the bundle.
        source (BundleSource): Captured bundle source.
        source_paths (dict[str, BundleSource]): Captured bundles by path.
        findings (list[Finding]): Accumulator for bundle findings.
    """
    if source.path != definition.path or source.kind != definition.kind:
        _finding(
            findings,
            "bundle.mapping",
            "captured bundle does not match its catalog declaration",
            definition.path,
        )
    if source.root_is_symlink or not source.apm_exists:
        _finding(
            findings,
            "bundle.root",
            "bundle .apm source root is missing or contains a symlink",
            f"{definition.path}/.apm",
        )
    if definition.path in source_paths and source.root_is_symlink:
        _finding(
            findings,
            "source.symlink",
            "bundle source path contains a symlink",
            definition.path,
        )


class _SkillSelection(NamedTuple):
    """Skills available to a composition and the subset made active."""

    requested: tuple[str, ...]
    available: dict[str, _SkillRecord]
    active: set[str]
    description_chars: int


class _Outputs(NamedTuple):
    """Planned output files with case-insensitive destination tracking."""

    files: dict[str, bytes]
    folded: dict[str, str]
    include_paths: set[str]
    documents: list[SourceDocument]


def _check_profile_selection(
    catalog: Catalog, profile: str, features: tuple[str, ...]
) -> None:
    """Reject an unknown base profile or feature profile.

    Args:
        catalog (Catalog): Validated catalog.
        profile (str): Selected base profile.
        features (tuple[str, ...]): Selected feature profiles.

    Raises:
        UnknownProfileError: The base or a feature profile is unknown.
    """
    profile_names = {item.name for item in catalog.profiles}
    if profile not in profile_names:
        raise UnknownProfileError(profile)
    unknown = next((name for name in features if name not in profile_names), None)
    if unknown is not None:
        raise UnknownProfileError(unknown, kind="feature profile")


def _selected_runtimes(catalog: Catalog, runtimes: tuple[str, ...]) -> tuple[str, ...]:
    """Default to every supported runtime and reject invalid selections.

    Args:
        catalog (Catalog): Validated catalog.
        runtimes (tuple[str, ...]): Requested runtimes; empty selects all.

    Returns:
        tuple[str, ...]: Unique runtimes in request order, or the catalog's
        supported runtimes when none were requested.

    Raises:
        CompositionError: The selection is empty, repeated, or unsupported.
    """
    selected = runtimes or catalog.supported_runtimes
    if not selected or len(set(selected)) != len(selected):
        raise CompositionError(CompositionIssue.RUNTIME_SELECTION)
    if any(runtime not in catalog.supported_runtimes for runtime in selected):
        raise CompositionError(CompositionIssue.UNSUPPORTED_RUNTIME)
    return selected


def _skill_selection(
    snapshot: CatalogSnapshot,
    catalog: Catalog,
    selected: tuple[str, ...],
    skills: tuple[str, ...],
) -> _SkillSelection:
    """Resolve requested session skills within the selected bundles' budget.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        catalog (Catalog): Validated catalog.
        selected (tuple[str, ...]): Effective bundle names.
        skills (tuple[str, ...]): Requested session skills; empty selects every
            skill in the selected bundles.

    Returns:
        _SkillSelection: Requested skills, skills available in the selected
        bundles, the active subset, and the active description character total.

    Raises:
        CompositionError: Skills repeat or exceed the description budget.
        UnavailableSkillsError: A skill is outside the selected bundles.
    """
    limits = dict(catalog.budgets)
    records = _skill_records(
        snapshot.bundles, [], limits["description_chars"], limits["skill_body_lines"]
    )
    available = {
        name: record for name, record in records.items() if record.bundle in selected
    }
    if len(skills) != len(set(skills)):
        raise CompositionError(CompositionIssue.DUPLICATE_SKILLS)
    if unavailable := set(skills) - available.keys():
        raise UnavailableSkillsError(unavailable)
    active = set(skills) if skills else set(available)
    description_chars = sum(len(available[name].description) for name in active)
    if description_chars > limits["profile_description_chars"]:
        raise CompositionError(CompositionIssue.DESCRIPTION_BUDGET)
    return _SkillSelection(
        requested=skills,
        available=available,
        active=active,
        description_chars=description_chars,
    )


def _instruction_name(document: SourceDocument) -> str:
    """Return the instruction identifier without its ``.instructions.md`` suffix."""
    return PurePosixPath(document.relative_path).name.removesuffix(".instructions.md")


def _is_instruction(document: SourceDocument) -> bool:
    """Check whether a document lives in the ``instructions`` directory."""
    return document.relative_path.startswith("instructions/")


def _document_selected(document: SourceDocument, selection: _SkillSelection) -> bool:
    """Select a source file for the composition's project or session mode.

    Args:
        document (SourceDocument): Captured source document.
        selection (_SkillSelection): Resolved skills for the composition.
    """
    if document.is_symlink or document.is_directory:
        return False
    parts = PurePosixPath(document.relative_path).parts
    if not parts:
        return False
    if parts[0] == "skills" and (
        len(parts) < _SKILL_MEMBER_MIN_DEPTH or parts[1] not in selection.active
    ):
        return False
    # Prompts are project workflows that may link any selected skill.
    if selection.requested and parts[0] == "prompts":
        return False
    if not selection.requested or not _is_instruction(document):
        return True
    name = _instruction_name(document)
    return name not in selection.available or name in selection.active


def _add_output(outputs: _Outputs, relative: str, content: bytes) -> None:
    """Plan one output file, rejecting case-insensitive destination collisions.

    Args:
        outputs (_Outputs): Planned outputs; extended in place.
        relative (str): Output path relative to the composition root.
        content (bytes): File content.

    Raises:
        CompositionCollisionError: Two outputs share a case-insensitive destination.
    """
    folded = relative.casefold()
    previous = outputs.folded.get(folded)
    if previous is not None:
        raise CompositionCollisionError(previous=previous, relative=relative)
    outputs.folded[folded] = relative
    outputs.files[relative] = content


def _retained_includes(
    included: tuple[str, ...], documents: tuple[SourceDocument, ...]
) -> set[str]:
    """Keep only includes backed by retained files, preserving path types.

    Args:
        included (tuple[str, ...]): Include paths relative to ``.apm``.
        documents (tuple[SourceDocument, ...]): Documents kept by the selection.

    Returns:
        set[str]: Include paths prefixed with ``.apm/``; directory includes end
        in a slash and file includes do not.
    """
    paths = {item.relative_path for item in documents}
    retained: set[str] = set()
    for prefix in included:
        if prefix in paths:
            retained.add(f".apm/{prefix}")
        elif any(path.startswith(f"{prefix}/") for path in paths):
            retained.add(f".apm/{prefix}/")
    return retained


def _collect_sources(
    snapshot: CatalogSnapshot,
    catalog: Catalog,
    selected: tuple[str, ...],
    selection: _SkillSelection,
) -> _Outputs:
    """Plan every selected bundle file and its manifest include roots.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        catalog (Catalog): Validated catalog.
        selected (tuple[str, ...]): Effective bundle names.
        selection (_SkillSelection): Resolved skills for the composition.

    Returns:
        _Outputs: Planned authored files, their documents, and include roots.

    Raises:
        UnavailableBundleError: A selected bundle is not available.
    """
    source_bundles = {item.name: item for item in snapshot.bundles}
    outputs = _Outputs(files={}, folded={}, include_paths=set(), documents=[])
    for name in selected:
        source = source_bundles.get(name)
        if source is None:
            raise UnavailableBundleError(name)
        included = _included_paths(
            source, [], catalog.version, catalog.supported_runtimes
        )
        retained = tuple(
            item for item in source.files if _document_selected(item, selection)
        )
        outputs.include_paths.update(_retained_includes(included, retained))
        for document in retained:
            _add_output(outputs, f".apm/{document.relative_path}", document.content)
            outputs.documents.append(document)
    return outputs


def _require_session_resources(outputs: _Outputs) -> None:
    """Reject a session selection whose links reference omitted resources.

    Raises:
        OmittedResourceError: A link references an omitted resource.
    """
    link_index = _link_index(name.removeprefix(".apm/") for name in outputs.files)
    missing_links: list[Finding] = []
    for document in outputs.documents:
        _check_links(document, link_index, missing_links, base_is_bundle=True)
    if missing_links:
        raise OmittedResourceError(missing_links[0])


def _json_bytes(value: object, *, ensure_ascii: bool) -> bytes:
    """Serialize deterministic, newline-terminated, indented JSON.

    Args:
        value (object): JSON-serializable document.
        ensure_ascii (bool): Whether to escape non-ASCII characters.
    """
    text = json.dumps(value, indent=_JSON_INDENT, ensure_ascii=ensure_ascii)
    return f"{text}\n".encode()


def _selection_record(
    selection: _SkillSelection, outputs: _Outputs, native_role_files: int
) -> JsonObject:
    """Describe the composition mode, active skills, and instruction budget.

    Args:
        selection (_SkillSelection): Resolved skills for the composition.
        outputs (_Outputs): Planned authored files and documents.
        native_role_files (int): Count of generated native role files.

    Returns:
        JsonObject: ``mode`` (``session`` or ``project``), sorted ``skills`` and
        ``instructions`` names, ``description_chars`` and ``instruction_chars``
        totals, and ``native_role_files``.
    """
    instructions = {
        _instruction_name(item) for item in outputs.documents if _is_instruction(item)
    }
    return {
        "mode": "session" if selection.requested else "project",
        "skills": sorted(selection.active),
        "instructions": sorted(instructions),
        "description_chars": selection.description_chars,
        "instruction_chars": sum(
            len(item.text or "") for item in outputs.documents if _is_instruction(item)
        ),
        "native_role_files": native_role_files,
    }


def _bundle_mcp(bundle: BundleSource) -> list[JsonObject]:
    """Return the validated MCP declarations of one source bundle's manifest."""
    match bundle.manifest:
        case {"dependencies": {"mcp": list() as entries}}:
            return [entry for entry in entries if is_json_object(entry)]
        case _:
            return []


def _selected_mcp(
    snapshot: CatalogSnapshot, selected: tuple[str, ...]
) -> list[JsonObject]:
    """Merge the selected bundles' MCP declarations in a stable order.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        selected (tuple[str, ...]): Effective bundle names.

    Returns:
        list[JsonObject]: One declaration per server, sorted by server name.

    Raises:
        CompositionError: Two bundles declare one server name differently.
    """
    merged: dict[str, JsonObject] = {}
    chosen = set(selected)
    for bundle in snapshot.bundles:
        if bundle.name not in chosen:
            continue
        for entry in _bundle_mcp(bundle):
            name = str(entry.get("name"))
            if merged.setdefault(name, entry) != entry:
                raise CompositionError(CompositionIssue.MCP_CONFLICT)
    return [merged[name] for name in sorted(merged)]


def _manifest_record(
    profile: str,
    catalog: Catalog,
    runtimes: tuple[str, ...],
    include_paths: set[str],
    mcp: list[JsonObject],
) -> JsonObject:
    """Build the composed APM manifest for the selected runtimes.

    Args:
        profile (str): Selected base profile.
        catalog (Catalog): Validated catalog.
        runtimes (tuple[str, ...]): Selected native runtimes.
        include_paths (set[str]): Include paths for retained resources.
        mcp (list[JsonObject]): Merged MCP declarations; omitted when empty.

    Returns:
        JsonObject: Manifest with ``name``, ``version``, ``targets``, sorted
        ``includes``, ``dependencies``, empty ``executables``, ``license``, and
        ``compilation`` exclusions.
    """
    return {
        "name": f"agent-kit-{profile}",
        "version": catalog.version,
        "targets": list(runtimes),
        "includes": sorted(include_paths),
        "dependencies": {"mcp": mcp} if mcp else {},
        "executables": {},
        "license": "MIT",
        "compilation": {"exclude": [".apm/skills", ".agents/skills", ".claude/skills"]},
    }


def _policy_content(snapshot: CatalogSnapshot) -> bytes:
    """Return the readable source policy bytes.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.

    Raises:
        CompositionError: The source policy is unavailable.
    """
    policy_document = snapshot.policy_document
    if policy_document is None or policy_document.text is None:
        raise CompositionError(CompositionIssue.POLICY_UNAVAILABLE)
    return policy_document.content


def _license_content(snapshot: CatalogSnapshot) -> bytes:
    """Return the root license bytes.

    Raises:
        CompositionError: The root license is missing.
    """
    license_document = next(
        (item for item in snapshot.root_documents if item.relative_path == "LICENSE"),
        None,
    )
    if license_document is None:
        raise CompositionError(CompositionIssue.LICENSE_UNAVAILABLE)
    return license_document.content


def _provenance_record(
    catalog: Catalog,
    profile: str,
    selected: tuple[str, ...],
    files: dict[str, bytes],
) -> JsonObject:
    """Record source bundles and content hashes for every planned file.

    Args:
        catalog (Catalog): Validated catalog.
        profile (str): Selected base profile.
        selected (tuple[str, ...]): Effective bundle names.
        files (dict[str, bytes]): Planned file content by output path.

    Returns:
        JsonObject: ``schema_version``, a ``source`` object (catalog version,
        profile, and bundle names with paths), and ``files`` mapping each output
        path to its hex SHA-256 digest in sorted order.
    """
    bundle_paths = {item.name: item.path for item in catalog.bundles}
    return {
        "schema_version": 1,
        "source": {
            "catalog_version": catalog.version,
            "profile": profile,
            "bundles": [
                {"name": name, "path": bundle_paths[name]} for name in selected
            ],
        },
        "files": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(files.items())
        },
    }


class CatalogService:
    """Own pure schema validation, profile selection, and output planning."""

    def __init__(self) -> None:
        """Create the stateless catalog application service."""

    def validate(self, snapshot: CatalogSnapshot) -> CheckReport:
        """Validate every source bundle, catalog profile, and strict policy.

        Returns:
            CheckReport: Unique findings ordered by path, code, and message,
            plus effective profile summaries. Findings are empty on success;
            profiles are empty and version is ``None`` if catalog parsing fails.
        """
        findings: list[Finding] = []
        catalog = _parse_catalog(snapshot, findings)
        _check_root_symlinks(snapshot, findings)
        _check_policy(snapshot, findings)
        _check_source_unicode(snapshot, findings)

        limits = dict(catalog.budgets) if catalog is not None else {}
        policy_limit = limits.get("policy_lines", _DEFAULT_POLICY_LINES)
        policy_lines = _policy_line_count(snapshot)
        if policy_lines > policy_limit:
            _finding(
                findings,
                "budget.policy",
                f"policy exceeds {policy_limit} lines",
                "apm-policy.yml",
            )
        root_documents = {item.relative_path: item for item in snapshot.root_documents}
        _check_root_files(root_documents, policy_limit, findings)
        _check_root_documentation(snapshot, root_documents, findings)

        skill_records: dict[str, _SkillRecord] = {}
        if catalog is not None:
            skill_records = self._validate_bundles(snapshot, catalog, findings)
            self._validate_profile_budgets(catalog, skill_records, findings)
            _check_native_assets(snapshot, catalog, skill_records, findings)
        deduplicated = tuple(
            sorted(
                set(findings),
                key=lambda item: (item.path, item.code, item.message),
            )
        )
        return CheckReport(
            findings=deduplicated,
            profiles=self._summaries(catalog, skill_records, policy_lines),
            version=catalog.version if catalog is not None else None,
        )

    def compose(
        self,
        snapshot: CatalogSnapshot,
        profile: str,
        features: tuple[str, ...],
        runtimes: tuple[str, ...],
        *,
        skills: tuple[str, ...] = (),
    ) -> CompositionPlan:
        """Build a pure, deterministic plan after source validation.

        Selection errors from the helpers propagate unchanged:
        ``CompositionCollisionError``, ``UnknownProfileError``,
        ``UnavailableSkillsError``, ``UnavailableBundleError``, and
        ``OmittedResourceError``.

        Args:
            snapshot (CatalogSnapshot): Captured source inputs; no files are read.
            profile (str): Base profile declared in the catalog.
            features (tuple[str, ...]): Additional catalog profiles to include.
            runtimes (tuple[str, ...]): Native targets; empty uses catalog defaults.
            skills (tuple[str, ...]): Opt-in session skills; empty selects the full
                profile rather than a bounded session.

        Returns:
            CompositionPlan: Selected bundles and generated files, with files
            ordered by relative output path. Includes selection and provenance
            records; session plans omit native role generation. Writes nothing.

        Raises:
            CompositionError: The source or catalog is invalid, or the runtime
                or skill selection, policy, or license cannot be composed.
        """
        report = self.validate(snapshot)
        if not report.valid:
            raise CompositionError(CompositionIssue.SOURCE_INVALID)
        catalog = _parse_catalog(snapshot, [])
        if catalog is None:
            raise CompositionError(CompositionIssue.CATALOG_INVALID)
        _check_profile_selection(catalog, profile, features)
        selected_runtimes = _selected_runtimes(catalog, runtimes)
        selected = _effective_bundles(catalog, (profile, *features))
        selection = _skill_selection(snapshot, catalog, selected, skills)
        outputs = _collect_sources(snapshot, catalog, selected, selection)
        if skills:
            _require_session_resources(outputs)
        native_agents = (
            {} if skills else render_native_agents(outputs.files, selected_runtimes)
        )
        for relative, content in native_agents.items():
            _add_output(outputs, relative, content)

        _add_output(
            outputs,
            ".apm/selection.json",
            _json_bytes(
                _selection_record(selection, outputs, len(native_agents)),
                ensure_ascii=True,
            ),
        )
        output_files = outputs.files
        mcp = [] if skills else _selected_mcp(snapshot, selected)
        output_files["apm.yml"] = _json_bytes(
            _manifest_record(
                profile, catalog, selected_runtimes, outputs.include_paths, mcp
            ),
            ensure_ascii=False,
        )
        output_files["apm-policy.yml"] = _policy_content(snapshot)
        output_files["LICENSE"] = _license_content(snapshot)
        output_files["provenance.json"] = _json_bytes(
            _provenance_record(catalog, profile, selected, output_files),
            ensure_ascii=False,
        )
        return CompositionPlan(
            bundles=selected,
            files=tuple(
                PlannedFile(content=content, relative_path=name)
                for name, content in sorted(output_files.items())
            ),
            profile=profile,
            root=snapshot.root,
            runtimes=selected_runtimes,
            source_paths=tuple((item.name, item.path) for item in catalog.bundles),
            version=catalog.version,
        )

    def _validate_bundles(
        self,
        snapshot: CatalogSnapshot,
        catalog: Catalog,
        findings: list[Finding],
    ) -> dict[str, _SkillRecord]:
        """Validate source roots, manifests, metadata, and every inactive bundle.

        Args:
            snapshot (CatalogSnapshot): Captured source inputs.
            catalog (Catalog): Validated catalog.
            findings (list[Finding]): Accumulator for bundle findings.

        Returns:
            dict[str, _SkillRecord]: Valid skills keyed by skill name.
        """
        sources = {item.name: item for item in snapshot.bundles}
        source_paths = {item.path: item for item in snapshot.bundles}
        for definition in catalog.bundles:
            source = sources.get(definition.name)
            if source is None:
                _finding(
                    findings,
                    "bundle.missing",
                    "catalog bundle source is missing or unsafe",
                    definition.path,
                )
                continue
            _check_bundle_source(definition, source, source_paths, findings)
            _included_paths(
                source, findings, catalog.version, catalog.supported_runtimes
            )
        limits = dict(catalog.budgets)
        return _skill_records(
            snapshot.bundles,
            findings,
            limits["description_chars"],
            limits["skill_body_lines"],
        )

    def _validate_profile_budgets(
        self,
        catalog: Catalog,
        skills: dict[str, _SkillRecord],
        findings: list[Finding],
    ) -> None:
        """Require non-empty effective profiles and bound their descriptions.

        Args:
            catalog (Catalog): Validated catalog.
            skills (dict[str, _SkillRecord]): Validated skills by name.
            findings (list[Finding]): Accumulator for budget findings.
        """
        limit = dict(catalog.budgets)["profile_description_chars"]
        for profile, selected in _resolved_profiles(catalog):
            location = f"catalog.json:profiles:{profile.name}"
            if not selected:
                _finding(
                    findings,
                    "profile.empty",
                    "effective profile must select at least one source bundle",
                    location,
                )
            description_chars = sum(
                len(record.description)
                for record in skills.values()
                if record.bundle in selected
            )
            if description_chars > limit:
                _finding(
                    findings,
                    "budget.profile_description",
                    f"profile descriptions exceed {limit} characters",
                    location,
                )

    def _summaries(
        self,
        catalog: Catalog | None,
        skills: dict[str, _SkillRecord],
        policy_lines: int,
    ) -> tuple[ProfileSummary, ...]:
        """Build effective profile counts without mutating source data.

        Args:
            catalog (Catalog | None): Validated catalog, or ``None`` when parsing
                failed.
            skills (dict[str, _SkillRecord]): Validated skills by name.
            policy_lines (int): Readable policy line count.

        Returns:
            tuple[ProfileSummary, ...]: One summary per resolvable profile, in
            catalog order; empty when ``catalog`` is ``None``.
        """
        if catalog is None:
            return ()
        limits = tuple(sorted(catalog.budgets))
        summaries: list[ProfileSummary] = []
        for profile, selected in _resolved_profiles(catalog):
            effective = [value for value in skills.values() if value.bundle in selected]
            summaries.append(
                ProfileSummary(
                    body_lines=sum(item.body_lines for item in effective),
                    description_chars=sum(len(item.description) for item in effective),
                    limits=limits,
                    policy_lines=policy_lines,
                    profile=profile.name,
                    skill_count=len(effective),
                )
            )
        return tuple(summaries)
