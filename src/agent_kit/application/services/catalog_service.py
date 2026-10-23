"""Validate source catalogs and build deterministic profile compositions."""

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
from agent_kit.core.text import visible_text

if TYPE_CHECKING:
    from urllib.parse import SplitResult

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
_POLICY_FIELDS = {
    "name",
    "version",
    "enforcement",
    "fetch_failure",
    "dependencies",
    "mcp",
    "manifest",
    "executables",
    "security",
}
_SKILL_NAME = re.compile(r"kit-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_MAX_SKILL_NAME_CHARS = 64
_SKILL_PATH_DEPTH = 3  # skills/<name>/SKILL.md
_PROMPT_PATH_DEPTH = 2  # prompts/<name>.prompt.md
_PROMPT_FIELDS = frozenset({"description", "argument-hint", "agent"})
_CATALOG_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")
_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(?:<(?P<angled>[^>]+)>|(?P<bare>[^\s)]+))")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_JSON_INDENT = 2
_DEFAULT_POLICY_LINES = 120
_POLICY = {
    "name": "Agent Kit source and dependency policy",
    "version": "1.0.0",
    "enforcement": "block",
    "fetch_failure": "block",
    "dependencies": {"allow": []},
    "mcp": {
        "allow": ["context7", "github", "microsoft-learn"],
        "self_defined": "deny",
        "trust_transitive": False,
    },
    "manifest": {
        "required_fields": ["name", "version", "includes", "license"],
        "require_explicit_includes": True,
        "scripts": "deny",
    },
    "executables": {"deny_all": True},
    "security": {
        "integrity": {"require_hashes": True},
        "audit": {"fail_on_drift": True},
    },
}
_POLICY_SCALARS = ("name", "version", "enforcement", "fetch_failure")
_POLICY_SECTIONS = {
    "dependencies": {"allow"},
    "mcp": {"allow", "self_defined", "trust_transitive"},
    "manifest": {"required_fields", "require_explicit_includes", "scripts"},
    "executables": {"deny_all"},
    "security": {"integrity", "audit"},
}
_SECURITY_SECTIONS = (("integrity", {"require_hashes"}), ("audit", {"fail_on_drift"}))
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
_MANIFEST_EMPTY_FIELDS = ("dependencies", "executables")
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


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow decoded objects to string-keyed mappings."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _sequence(value: object) -> TypeGuard[list[object]]:
    """Narrow decoded objects to lists without introducing Any."""
    return isinstance(value, list)


def _finding(findings: list[Finding], code: str, message: str, path: str) -> None:
    """Append one source-relative diagnostic."""
    findings.append(Finding(code=code, message=message, path=path))


def _exact_mapping(
    value: object,
    expected: set[str],
    path: str,
    findings: list[Finding],
) -> dict[str, object] | None:
    """Require a mapping with exactly the declared keys."""
    if not _mapping(value):
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
    """Validate a list of unique, non-empty strings."""
    if not _sequence(value):
        _finding(findings, "schema.list", "expected a list of strings", path)
        return None
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
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


def _positive_integer(value: object) -> bool:
    """Check an integer without accepting bool values."""
    return type(value) is int and value > 0


def _same_value(actual: object, expected: object) -> bool:
    """Compare nested policy values without Python bool/integer equivalence."""
    if type(actual) is not type(expected):
        return False
    if _mapping(actual) and _mapping(expected):
        return actual.keys() == expected.keys() and all(
            _same_value(actual[key], expected[key]) for key in actual
        )
    if _sequence(actual) and _sequence(expected):
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
    if not isinstance(value, str) or not value or "\\" in value:
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
    """Return the keys, values, or items of a container not yet traversed."""
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
    """Record a safe diagnostic without including the offending text."""
    if _contains_hidden_unicode(value):
        _finding(
            findings,
            "unicode.hidden",
            "source content contains unsupported hidden Unicode controls",
            path,
        )


def _document_text(document: SourceDocument) -> str:
    """Return a safe, empty string for a non-text document."""
    return document.text if document.text is not None else ""


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
    """Allow web links everywhere and project contacts outside bundles."""
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return True
    return not base_is_bundle and _is_project_contact(parsed)


def _resolved_link(raw_path: str, document_path: str) -> str | None:
    """Resolve a relative link beside its document; ``None`` when it escapes."""
    stack = list(PurePosixPath(document_path).parent.parts)
    for part in PurePosixPath(raw_path).parts:
        if part == "..":
            if not stack:
                return None
            stack.pop()
        elif part not in {"", "."}:
            stack.append(part)
    return "/".join(stack)


def _link_exists(target: str, available_paths: set[str]) -> bool:
    """Match a resolved target to a file or directory case-insensitively."""
    folded = target.casefold()
    candidates = {item.casefold() for item in available_paths}
    return folded in candidates or (
        bool(target) and any(item.startswith(f"{folded}/") for item in candidates)
    )


def _local_link_issue(
    raw_path: str, document_path: str, available_paths: set[str]
) -> tuple[str, str] | None:
    """Return the finding code and message for an invalid local link."""
    if "\\" in raw_path:
        return "links.path", "resource link is not a portable path"
    target = None if _is_absolute(raw_path) else _resolved_link(raw_path, document_path)
    if target is None:
        return "links.escape", "resource link escapes its source root"
    if _link_exists(target, available_paths):
        return None
    return "links.missing", f"resource link target does not exist: {raw_path}"


def _link_target(
    link: str,
    document_path: str,
    available_paths: set[str],
    findings: list[Finding],
    *,
    base_is_bundle: bool,
) -> None:
    """Verify a Markdown resource target stays in its owning source root."""
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
    issue = _local_link_issue(raw_path, document_path, available_paths)
    if issue is not None:
        code, message = issue
        _finding(findings, code, message, document_path)


def _check_links(
    document: SourceDocument,
    available_paths: set[str],
    findings: list[Finding],
    *,
    base_is_bundle: bool,
) -> None:
    """Validate Markdown documents, not Python expressions or template data."""
    text = document.text
    name = PurePosixPath(document.relative_path).name.casefold()
    markdown = PurePosixPath(name).suffix in {".md", ".markdown"} or name == "llms.txt"
    if text is None or not markdown or ".template." in name:
        return
    for match in _LINK.finditer(text):
        link = match.group("angled") or match.group("bare")
        if link is not None:
            _link_target(
                link,
                document.relative_path,
                available_paths,
                findings,
                base_is_bundle=base_is_bundle,
            )


def _policy_value_finding(findings: list[Finding], key: str, path: str) -> None:
    """Report one policy value that differs from the released contract."""
    _finding(findings, "policy.value", f"unsupported policy value for '{key}'", path)


def _policy_scalars_valid(
    top: dict[str, object], path: str, findings: list[Finding]
) -> bool:
    """Compare top-level scalar policy values with the released contract."""
    valid = True
    for key in _POLICY_SCALARS:
        if top.get(key) != _POLICY[key]:
            _policy_value_finding(findings, key, path)
            valid = False
    return valid


def _security_policy_valid(
    security: dict[str, object], path: str, findings: list[Finding]
) -> bool:
    """Require the exact nested integrity and audit security settings."""
    expected_security = _POLICY.get("security")
    expected = expected_security if _mapping(expected_security) else {}
    valid = True
    for child, child_fields in _SECURITY_SECTIONS:
        nested = _exact_mapping(
            security.get(child), child_fields, f"{path}:security:{child}", findings
        )
        if nested is None:
            valid = False
        elif not _same_value(nested, expected.get(child)):
            _policy_value_finding(findings, child, path)
            valid = False
    return valid


def _policy_section_valid(
    top: dict[str, object], key: str, path: str, findings: list[Finding]
) -> bool:
    """Require one nested policy section to match its released shape and values."""
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
    """Require the exact released strict policy contract."""
    top = _exact_mapping(value, _POLICY_FIELDS, path, findings)
    if top is None:
        return False
    results = [_policy_scalars_valid(top, path, findings)]
    results.extend(
        _policy_section_valid(top, key, path, findings) for key in _POLICY_SECTIONS
    )
    return all(results) and _same_value(top, _POLICY)


def _catalog_schema_version(
    raw: dict[str, object], findings: list[Finding]
) -> int | None:
    """Return the supported catalog schema version or report it."""
    value = raw.get("schema_version")
    if type(value) is int and value == 1:
        return value
    _finding(findings, "catalog.version", "schema_version must be 1", "catalog.json")
    return None


def _catalog_version(raw: dict[str, object], findings: list[Finding]) -> str | None:
    """Return the semantic catalog version or report it."""
    value = raw.get("version")
    if isinstance(value, str) and _VERSION.fullmatch(value) is not None:
        return value
    _finding(
        findings,
        "catalog.version",
        "version must be a semantic version",
        "catalog.json",
    )
    return None


def _catalog_runtimes(
    raw: dict[str, object], findings: list[Finding]
) -> tuple[str, ...] | None:
    """Return the exact supported runtime list or report it."""
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
    raw: dict[str, object], findings: list[Finding]
) -> tuple[tuple[str, int], ...]:
    """Return every valid positive budget in sorted field order."""
    budgets_raw = _exact_mapping(
        raw.get("budgets"), _BUDGET_FIELDS, "catalog.json:budgets", findings
    )
    if budgets_raw is None:
        return ()
    budgets: list[tuple[str, int]] = []
    for key in sorted(_BUDGET_FIELDS):
        value = budgets_raw.get(key)
        if not _positive_integer(value):
            _finding(
                findings,
                "catalog.budget",
                f"'{key}' must be a positive integer",
                "catalog.json:budgets",
            )
        elif isinstance(value, int):
            budgets.append((key, value))
    return tuple(budgets)


def _parse_catalog(
    snapshot: CatalogSnapshot, findings: list[Finding]
) -> Catalog | None:
    """Validate exact catalog fields and build typed selection values."""
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
    """Validate one named source bundle declaration."""
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
    kind = item.get("kind")
    if not isinstance(kind, str) or kind not in {"project", "portable"}:
        _finding(findings, "catalog.kind", "bundle kind is invalid", location)
        return None
    return Bundle(kind=kind, name=name, path=path)


def _parse_bundles(value: object, findings: list[Finding]) -> tuple[Bundle, ...] | None:
    """Validate every named source bundle."""
    if not _mapping(value):
        _finding(
            findings, "catalog.bundles", "bundles must be an object", "catalog.json"
        )
        return None
    parsed = (_parse_bundle(name, item, findings) for name, item in value.items())
    bundles = tuple(bundle for bundle in parsed if bundle is not None)
    if not bundles:
        _finding(
            findings,
            "catalog.bundles",
            "at least one bundle is required",
            "catalog.json",
        )
    return bundles


def _parse_profile(
    name: str, raw_profile: object, findings: list[Finding]
) -> Profile | None:
    """Validate one profile's inheritance and direct bundle references."""
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
    """Validate profile inheritance and direct bundle references."""
    if not _mapping(value):
        _finding(
            findings, "catalog.profiles", "profiles must be an object", "catalog.json"
        )
        return None
    parsed = (_parse_profile(name, item, findings) for name, item in value.items())
    profiles = tuple(profile for profile in parsed if profile is not None)
    if not profiles:
        _finding(
            findings,
            "catalog.profiles",
            "at least one profile is required",
            "catalog.json",
        )
    return profiles


def _check_references(
    bundles: tuple[Bundle, ...],
    profiles: tuple[Profile, ...],
    findings: list[Finding],
) -> None:
    """Report missing bundle or profile references."""
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
    """Report all profiles participating in inheritance cycles."""
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
    """Append a profile's inherited and direct bundles in first-seen order."""
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
    """Resolve profile inheritance into an ordered unique bundle union."""
    profiles = {item.name: item for item in catalog.profiles}
    selected: list[str] = []
    visited: set[str] = set()
    for name in profile_names:
        _include_profile(name, profiles, selected, visited)
    return tuple(selected)


def _covers(prefix: str, path: str) -> bool:
    """Check whether ``path`` equals ``prefix`` or lies beneath it."""
    return path == prefix or path.startswith(f"{prefix}/")


def _manifest_mapping(
    bundle: BundleSource, location: str, findings: list[Finding]
) -> dict[str, object] | None:
    """Return a readable manifest object or report why it is unusable."""
    if bundle.manifest_error or bundle.manifest is None:
        _finding(findings, "manifest.read", "apm.yml is missing or invalid", location)
        return None
    manifest = bundle.manifest
    if not _mapping(manifest):
        _finding(findings, "manifest.schema", "manifest must be an object", location)
        return None
    return manifest


def _check_manifest_fields(
    manifest: dict[str, object], location: str, findings: list[Finding]
) -> None:
    """Report missing, unknown, prohibited, and unlicensed manifest fields."""
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
    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        _finding(findings, "manifest.name", "manifest name is required", location)


def _check_manifest_version(
    manifest: dict[str, object], version: str, location: str, findings: list[Finding]
) -> None:
    """Require a semantic manifest version equal to the catalog version."""
    manifest_version = manifest.get("version")
    if (
        not isinstance(manifest_version, str)
        or _VERSION.fullmatch(manifest_version) is None
    ):
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
    """Require non-empty manifest targets drawn from supported runtimes."""
    if targets is not None and (
        not targets or any(runtime not in supported_runtimes for runtime in targets)
    ):
        _finding(findings, "manifest.targets", "manifest targets are invalid", location)


def _check_manifest_empty_fields(
    manifest: dict[str, object], location: str, findings: list[Finding]
) -> None:
    """Require empty dependency and executable declarations."""
    for field in _MANIFEST_EMPTY_FIELDS:
        value = manifest.get(field)
        if not _mapping(value) or value != {}:
            _finding(findings, f"manifest.{field}", f"{field} must be empty", location)


def _include_issue(include: str, path: PurePosixPath) -> str | None:
    """Return why an include is not a contained ``.apm`` path, if it is not."""
    if not include.startswith(".apm/") or "\\" in include:
        return "includes must name paths beneath .apm"
    if path.is_absolute() or any(part in {"..", "."} for part in path.parts[1:]):
        return "include path escapes .apm"
    return None


def _normalized_includes(
    includes: tuple[str, ...], location: str, findings: list[Finding]
) -> tuple[str, ...]:
    """Return valid includes relative to ``.apm`` and report the others."""
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
    """Require every include to match resources and every resource to be included."""
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
    """Validate source APM metadata and return explicit .apm include roots."""
    location = f"{bundle.path}/apm.yml"
    manifest = _manifest_mapping(bundle, location, findings)
    if manifest is None:
        return ()
    _check_manifest_fields(manifest, location, findings)
    _check_manifest_version(manifest, version, location, findings)
    targets = _string_list(manifest.get("targets"), f"{location}:targets", findings)
    includes = _string_list(manifest.get("includes"), f"{location}:includes", findings)
    _check_manifest_targets(targets, supported_runtimes, location, findings)
    _check_manifest_empty_fields(manifest, location, findings)
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
    """Report unsafe or malformed documents; reject symlinks from validation."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    if document.is_symlink:
        _finding(
            findings, "source.symlink", "source bundle contains a symlink", location
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


def _validate_metadata(
    document: SourceDocument,
    bundle: BundleSource,
    records: dict[str, _SkillRecord],
    prompts: set[str],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> None:
    """Dispatch a document to its instruction, prompt, or skill validator."""
    relative = document.relative_path
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
    """Validate skill metadata and return each skill's description and body."""
    records: dict[str, _SkillRecord] = {}
    prompts: set[str] = set()
    for bundle in bundles:
        paths = {item.relative_path for item in bundle.files if not item.is_directory}
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
                _check_links(document, paths, findings, base_is_bundle=True)
    return records


def _validate_instruction(
    document: SourceDocument,
    bundle: BundleSource,
    findings: list[Finding],
) -> None:
    """Require portable instruction discovery metadata."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    if not _mapping(document.frontmatter):
        _finding(
            findings,
            "instruction.frontmatter",
            "instruction metadata is required",
            location,
        )
        return
    for key in ("description", "applyTo"):
        if not isinstance(
            document.frontmatter.get(key), str
        ) or not document.frontmatter.get(key):
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
    """Check for a non-blank, single-line string within ``limit`` characters."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and "\n" not in value
        and len(value) <= limit
    )


def _check_prompt_metadata(
    metadata: dict[str, object],
    location: str,
    findings: list[Finding],
    description_limit: int,
) -> None:
    """Allow only discovery metadata and a bounded one-line description."""
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
    """Require a flat, uniquely named prompt with discovery-only metadata."""
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
    if not _mapping(metadata):
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
    metadata: dict[str, object],
    relative_path: str,
    records: dict[str, _SkillRecord],
    location: str,
    findings: list[Finding],
) -> None:
    """Check skill placement, uniqueness, and absence of native scope metadata."""
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
    metadata: dict[str, object],
    description_limit: int,
    location: str,
    findings: list[Finding],
) -> str | None:
    """Return a required skill description, reporting budget overruns."""
    description = metadata.get("description")
    if not isinstance(description, str) or not description:
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
    """Return the skill body line count, reporting delimiters and budget."""
    body = _body_text(_document_text(document))
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
    """Validate a skill name, description, body, and portable metadata."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    metadata = document.frontmatter
    if not _mapping(metadata):
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
    """Report a symlinked source root and any captured root links."""
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
    """Require a readable policy document with the strict released contract."""
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
    """Reject hidden Unicode in catalog, policy, manifest, and bundle content."""
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
    """Require the MIT license and docs index and bound ``AGENTS.md``."""
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
    """Require readable, link-safe, non-symlink root documentation."""
    root_available = set(snapshot.root_paths) | set(root_documents)
    root_available.update(
        f"{bundle.path}/.apm/{source.relative_path}"
        for bundle in snapshot.bundles
        for source in bundle.files
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


def _native_assets(snapshot: CatalogSnapshot) -> dict[str, bytes]:
    """Map every bundle file to its source-root-relative ``.apm`` path."""
    assets: dict[str, bytes] = {}
    for bundle in snapshot.bundles:
        prefix = "" if bundle.path == "." else f"{bundle.path}/"
        for document in bundle.files:
            if not document.is_directory:
                assets[f"{prefix}.apm/{document.relative_path}"] = document.content
    return assets


def _check_native_assets(
    snapshot: CatalogSnapshot, catalog: Catalog, findings: list[Finding]
) -> None:
    """Report native role assets that cannot be rendered for supported runtimes."""
    try:
        validate_native_assets(_native_assets(snapshot), catalog.supported_runtimes)
    except (ValueError, InputTypeError) as error:
        _finding(
            findings,
            "native.assets",
            f"native role assets are invalid: {error}",
            "catalog.json",
        )


def _check_bundle_source(
    definition: Bundle,
    source: BundleSource,
    source_paths: dict[str, BundleSource],
    findings: list[Finding],
) -> None:
    """Require a captured bundle to match its declaration and safe ``.apm`` root."""
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
    """Reject an unknown base profile or feature profile."""
    profile_names = {item.name for item in catalog.profiles}
    if profile not in profile_names:
        raise UnknownProfileError(profile)
    unknown = next((name for name in features if name not in profile_names), None)
    if unknown is not None:
        raise UnknownProfileError(unknown, kind="feature profile")


def _selected_runtimes(catalog: Catalog, runtimes: tuple[str, ...]) -> tuple[str, ...]:
    """Default to every supported runtime and reject invalid selections."""
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
    """Resolve requested session skills within the selected bundles' budget."""
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
    return PurePosixPath(document.relative_path).parts[0] == "instructions"


def _document_selected(document: SourceDocument, selection: _SkillSelection) -> bool:
    """Select a source file for the composition's project or session mode."""
    if document.is_symlink or document.is_directory:
        return False
    parts = PurePosixPath(document.relative_path).parts
    if parts[0] == "skills" and parts[1] not in selection.active:
        return False
    # Prompts are project workflows that may link any selected skill.
    if selection.requested and parts[0] == "prompts":
        return False
    if not selection.requested or not _is_instruction(document):
        return True
    name = _instruction_name(document)
    return name not in selection.available or name in selection.active


def _add_output(outputs: _Outputs, relative: str, content: bytes) -> None:
    """Plan one output file, rejecting case-insensitive destination collisions."""
    folded = relative.casefold()
    previous = outputs.folded.get(folded)
    if previous is not None:
        raise CompositionCollisionError(previous=previous, relative=relative)
    outputs.folded[folded] = relative
    outputs.files[relative] = content


def _collect_sources(
    snapshot: CatalogSnapshot,
    catalog: Catalog,
    selected: tuple[str, ...],
    selection: _SkillSelection,
) -> _Outputs:
    """Plan every selected bundle file and its manifest include roots."""
    source_bundles = {item.name: item for item in snapshot.bundles}
    outputs = _Outputs(files={}, folded={}, include_paths=set(), documents=[])
    for name in selected:
        source = source_bundles.get(name)
        if source is None:
            raise UnavailableBundleError(name)
        included = _included_paths(
            source, [], catalog.version, catalog.supported_runtimes
        )
        outputs.include_paths.update(f".apm/{item}/" for item in included)
        for document in source.files:
            if _document_selected(document, selection):
                _add_output(outputs, f".apm/{document.relative_path}", document.content)
                outputs.documents.append(document)
    return outputs


def _require_session_resources(outputs: _Outputs) -> None:
    """Reject a session selection whose links reference omitted resources."""
    available_paths = {name.removeprefix(".apm/") for name in outputs.files}
    missing_links: list[Finding] = []
    for document in outputs.documents:
        _check_links(document, available_paths, missing_links, base_is_bundle=True)
    if missing_links:
        raise OmittedResourceError(missing_links[0])


def _json_bytes(value: object, *, ensure_ascii: bool) -> bytes:
    """Serialize deterministic, newline-terminated, indented JSON."""
    text = json.dumps(value, indent=_JSON_INDENT, ensure_ascii=ensure_ascii)
    return f"{text}\n".encode()


def _selection_record(
    selection: _SkillSelection, outputs: _Outputs, native_role_files: int
) -> dict[str, object]:
    """Describe the composition mode, active skills, and instruction budget."""
    instructions = {
        _instruction_name(item) for item in outputs.documents if _is_instruction(item)
    }
    return {
        "mode": "session" if selection.requested else "project",
        "skills": sorted(selection.active),
        "instructions": sorted(instructions),
        "description_chars": selection.description_chars,
        "instruction_chars": sum(
            len(item.text or "")
            for item in outputs.documents
            if item.relative_path.startswith("instructions/")
        ),
        "native_role_files": native_role_files,
    }


def _manifest_record(
    profile: str,
    catalog: Catalog,
    runtimes: tuple[str, ...],
    include_paths: set[str],
) -> dict[str, object]:
    """Build the composed APM manifest for the selected runtimes."""
    return {
        "name": f"agent-kit-{profile}",
        "version": catalog.version,
        "targets": list(runtimes),
        "includes": sorted(include_paths),
        "dependencies": {},
        "executables": {},
        "license": "MIT",
        "compilation": {"exclude": [".apm/skills", ".agents/skills", ".claude/skills"]},
    }


def _policy_content(snapshot: CatalogSnapshot) -> bytes:
    """Return the readable source policy bytes."""
    policy_document = snapshot.policy_document
    if policy_document is None or policy_document.text is None:
        raise CompositionError(CompositionIssue.POLICY_UNAVAILABLE)
    return policy_document.content


def _license_content(snapshot: CatalogSnapshot) -> bytes:
    """Return the root license bytes."""
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
) -> dict[str, object]:
    """Record source bundles and content hashes for every planned file."""
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
        """Validate every source bundle, catalog profile, and strict policy."""
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
            _check_native_assets(snapshot, catalog, findings)
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
        """Build a pure, deterministic plan after source validation."""
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

        output_files = outputs.files
        output_files[".apm/selection.json"] = _json_bytes(
            _selection_record(selection, outputs, len(native_agents)),
            ensure_ascii=True,
        )
        output_files["apm.yml"] = _json_bytes(
            _manifest_record(
                profile, catalog, selected_runtimes, outputs.include_paths
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
        """Validate source roots, manifests, metadata, and every inactive bundle."""
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
        """Enforce the aggregate description budget for every declared profile."""
        limit = dict(catalog.budgets)["profile_description_chars"]
        for profile in catalog.profiles:
            try:
                selected = _effective_bundles(catalog, (profile.name,))
            except ValueError:
                continue
            description_chars = sum(
                len(description)
                for description, _lines, bundle in skills.values()
                if bundle in selected
            )
            if description_chars > limit:
                _finding(
                    findings,
                    "budget.profile_description",
                    f"profile descriptions exceed {limit} characters",
                    f"catalog.json:profiles:{profile.name}",
                )

    def _summaries(
        self,
        catalog: Catalog | None,
        skills: dict[str, _SkillRecord],
        policy_lines: int,
    ) -> tuple[ProfileSummary, ...]:
        """Build effective profile counts without mutating source data."""
        if catalog is None:
            return ()
        limits = tuple(sorted(catalog.budgets))
        summaries: list[ProfileSummary] = []
        for profile in catalog.profiles:
            try:
                selected = _effective_bundles(catalog, (profile.name,))
            except ValueError:
                continue
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
