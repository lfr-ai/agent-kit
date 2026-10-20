"""Validate source catalogs and build deterministic profile compositions."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum, unique
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal, TypeGuard
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
_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))")
_POLICY = {
    "name": "Agent Kit source and dependency policy",
    "version": "1.0.0",
    "enforcement": "block",
    "fetch_failure": "block",
    "dependencies": {"allow": []},
    "mcp": {
        "allow": [],
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


def _contained_catalog_path(value: object) -> str | None:
    """Validate a normalized, relative source bundle path."""
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return None
    if any(part == ".." for part in posix.parts):
        return None
    normalized = posix.as_posix()
    if normalized == ".":
        return "."
    if normalized.startswith("./") or normalized.endswith("/"):
        return None
    return normalized


def _contains_hidden_unicode(value: object) -> bool:
    """Find unsupported format and control characters in decoded content."""
    pending = [value]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str) and not visible_text(current):
            return True
        if isinstance(current, dict):
            identity = id(current)
            if identity not in visited:
                visited.add(identity)
                for key, item in current.items():
                    pending.extend((key, item))
        elif isinstance(current, list):
            identity = id(current)
            if identity not in visited:
                visited.add(identity)
                pending.extend(current)
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


def _link_target(  # noqa: C901, PLR0911, PLR0912
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
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            return
        project_contact = (
            not base_is_bundle
            and parsed.scheme.lower() == "mailto"
            and not parsed.netloc
            and not parsed.query
            and not parsed.fragment
            and parsed.path == unquote(parsed.path)
            and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", unquote(parsed.path))
            is not None
        )
        if project_contact:
            return
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
    if "\\" in raw_path:
        _finding(
            findings,
            "links.path",
            "resource link is not a portable path",
            document_path,
        )
        return
    posix = PurePosixPath(raw_path)
    windows = PureWindowsPath(raw_path)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        _finding(
            findings,
            "links.escape",
            "resource link escapes its source root",
            document_path,
        )
        return
    parent = PurePosixPath(document_path).parent
    stack = [] if not base_is_bundle else list(parent.parts)
    if not base_is_bundle:
        stack = list(parent.parts)
    for part in posix.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not stack:
                _finding(
                    findings,
                    "links.escape",
                    "resource link escapes its source root",
                    document_path,
                )
                return
            stack.pop()
        else:
            stack.append(part)
    target = "/".join(stack)
    candidates = {item.casefold() for item in available_paths}
    if target.casefold() in candidates:
        return
    if target and any(item.startswith(f"{target.casefold()}/") for item in candidates):
        return
    _finding(
        findings,
        "links.missing",
        f"resource link target does not exist: {raw_path}",
        document_path,
    )


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
        link = match.group(1) or match.group(2)
        if link is not None:
            _link_target(
                link,
                document.relative_path,
                available_paths,
                findings,
                base_is_bundle=base_is_bundle,
            )


def _policy_mapping(value: object, path: str, findings: list[Finding]) -> bool:  # noqa: C901
    """Require the exact released strict policy contract."""
    top = _exact_mapping(value, _POLICY_FIELDS, path, findings)
    if top is None:
        return False
    valid = True
    for key in ("name", "version", "enforcement", "fetch_failure"):
        if top.get(key) != _POLICY[key]:
            _finding(
                findings, "policy.value", f"unsupported policy value for '{key}'", path
            )
            valid = False
    nested_shapes = {
        "dependencies": {"allow"},
        "mcp": {"allow", "self_defined", "trust_transitive"},
        "manifest": {"required_fields", "require_explicit_includes", "scripts"},
        "executables": {"deny_all"},
        "security": {"integrity", "audit"},
    }
    for key, fields in nested_shapes.items():
        nested = _exact_mapping(top.get(key), fields, f"{path}:{key}", findings)
        if nested is None:
            valid = False
            continue
        if key == "security":
            for child, child_fields in (
                ("integrity", {"require_hashes"}),
                ("audit", {"fail_on_drift"}),
            ):
                nested_child = _exact_mapping(
                    nested.get(child), child_fields, f"{path}:{key}:{child}", findings
                )
                if nested_child is None:
                    valid = False
                    continue
                expected_security = _POLICY.get("security")
                expected_security_mapping = (
                    expected_security if _mapping(expected_security) else {}
                )
                expected_child = expected_security_mapping.get(child)
                if not _same_value(nested_child, expected_child):
                    _finding(
                        findings,
                        "policy.value",
                        f"unsupported policy value for '{child}'",
                        path,
                    )
                    valid = False
        elif not _same_value(nested, _POLICY.get(key)):
            _finding(
                findings,
                "policy.value",
                f"unsupported policy value for '{key}'",
                path,
            )
            valid = False
    if not _same_value(top, _POLICY):
        valid = False
    return valid


def _parse_catalog(  # noqa: C901
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

    schema_version = raw.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        _finding(
            findings, "catalog.version", "schema_version must be 1", "catalog.json"
        )
        schema_version = None

    version = raw.get("version")
    if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        _finding(
            findings,
            "catalog.version",
            "version must be a semantic version",
            "catalog.json",
        )
        version = None

    runtimes = _string_list(
        raw.get("supported_runtimes"), "catalog.json:supported_runtimes", findings
    )
    if runtimes is not None and (runtimes != ("copilot", "claude")):
        _finding(
            findings,
            "catalog.runtime",
            "supported runtimes must be exactly copilot and claude",
            "catalog.json:supported_runtimes",
        )
        runtimes = None

    budgets_raw = _exact_mapping(
        raw.get("budgets"), _BUDGET_FIELDS, "catalog.json:budgets", findings
    )
    budgets: list[tuple[str, int]] = []
    if budgets_raw is not None:
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
        budgets=tuple(budgets),
        bundles=bundles,
        profiles=profiles,
        schema_version=schema_version,
        supported_runtimes=runtimes,
        version=version,
    )


def _parse_bundles(value: object, findings: list[Finding]) -> tuple[Bundle, ...] | None:
    """Validate every named source bundle."""
    if not _mapping(value):
        _finding(
            findings, "catalog.bundles", "bundles must be an object", "catalog.json"
        )
        return None
    bundles: list[Bundle] = []
    for name, raw_bundle in value.items():
        location = f"catalog.json:bundles:{name}"
        if _CATALOG_NAME.fullmatch(name) is None:
            _finding(findings, "catalog.name", "bundle name is not legal", location)
        item = _exact_mapping(raw_bundle, {"path", "kind"}, location, findings)
        if item is None:
            continue
        path = _contained_catalog_path(item.get("path"))
        kind = item.get("kind")
        if path is None:
            _finding(
                findings,
                "catalog.path",
                "bundle path must be relative and contained in the source root",
                location,
            )
            continue
        if not isinstance(kind, str) or kind not in {"project", "portable"}:
            _finding(findings, "catalog.kind", "bundle kind is invalid", location)
            continue
        bundles.append(Bundle(kind=kind, name=name, path=path))
    if not bundles:
        _finding(
            findings,
            "catalog.bundles",
            "at least one bundle is required",
            "catalog.json",
        )
    return tuple(bundles)


def _parse_profiles(
    value: object, findings: list[Finding]
) -> tuple[Profile, ...] | None:
    """Validate profile inheritance and direct bundle references."""
    if not _mapping(value):
        _finding(
            findings, "catalog.profiles", "profiles must be an object", "catalog.json"
        )
        return None
    profiles: list[Profile] = []
    for name, raw_profile in value.items():
        location = f"catalog.json:profiles:{name}"
        if _CATALOG_NAME.fullmatch(name) is None:
            _finding(findings, "catalog.name", "profile name is not legal", location)
        item = _exact_mapping(raw_profile, {"extends", "bundles"}, location, findings)
        if item is None:
            continue
        extends = _string_list(item.get("extends"), f"{location}:extends", findings)
        bundles = _string_list(item.get("bundles"), f"{location}:bundles", findings)
        if extends is None or bundles is None:
            continue
        profiles.append(Profile(bundles=bundles, extends=extends, name=name))
    if not profiles:
        _finding(
            findings,
            "catalog.profiles",
            "at least one profile is required",
            "catalog.json",
        )
    return tuple(profiles)


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


def _effective_bundles(
    catalog: Catalog, profile_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve profile inheritance into an ordered unique bundle union."""
    profiles = {item.name: item for item in catalog.profiles}
    selected: list[str] = []
    visited: set[str] = set()

    def include(name: str) -> None:
        profile = profiles.get(name)
        if profile is None:
            raise UnknownProfileError(name)
        if name in visited:
            return
        visited.add(name)
        for parent in profile.extends:
            include(parent)
        for bundle in profile.bundles:
            if bundle not in selected:
                selected.append(bundle)

    for name in profile_names:
        include(name)
    return tuple(selected)


def _included_paths(  # noqa: C901, PLR0912
    bundle: BundleSource,
    findings: list[Finding],
    version: str,
    supported_runtimes: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate source APM metadata and return explicit .apm include roots."""
    location = f"{bundle.path}/apm.yml"
    if bundle.manifest_error or bundle.manifest is None:
        _finding(findings, "manifest.read", "apm.yml is missing or invalid", location)
        return ()
    manifest = bundle.manifest
    if not _mapping(manifest):
        _finding(findings, "manifest.schema", "manifest must be an object", location)
        return ()
    required = {
        "name",
        "version",
        "targets",
        "includes",
        "dependencies",
        "executables",
        "license",
    }
    allowed = required | {"description"}
    for field in sorted(required - set(manifest)):
        _finding(findings, "manifest.missing", f"missing field '{field}'", location)
    for field in sorted(set(manifest) - allowed):
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
    targets = _string_list(manifest.get("targets"), f"{location}:targets", findings)
    includes = _string_list(manifest.get("includes"), f"{location}:includes", findings)
    if targets is not None and (
        not targets or any(runtime not in supported_runtimes for runtime in targets)
    ):
        _finding(findings, "manifest.targets", "manifest targets are invalid", location)
    if not _mapping(manifest.get("dependencies")) or manifest.get("dependencies") != {}:
        _finding(
            findings, "manifest.dependencies", "dependencies must be empty", location
        )
    if not _mapping(manifest.get("executables")) or manifest.get("executables") != {}:
        _finding(
            findings, "manifest.executables", "executables must be empty", location
        )

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
    normalized: list[str] = []
    for include in includes:
        if not include.startswith(".apm/") or "\\" in include:
            _finding(
                findings,
                "manifest.includes",
                "includes must name paths beneath .apm",
                location,
            )
            continue
        path = PurePosixPath(include.rstrip("/"))
        if path.is_absolute() or any(part in {"..", "."} for part in path.parts[1:]):
            _finding(
                findings,
                "manifest.includes",
                "include path escapes .apm",
                location,
            )
            continue
        normalized.append(path.relative_to(".apm").as_posix())
    available = {item.relative_path for item in bundle.files}
    for include in normalized:
        if not any(
            item == include or item.startswith(f"{include}/") for item in available
        ):
            _finding(
                findings,
                "manifest.includes",
                f"include path has no resources: .apm/{include}",
                location,
            )
    for source in bundle.files:
        if source.relative_path not in available:
            continue
        if not any(
            source.relative_path == include
            or source.relative_path.startswith(f"{include}/")
            for include in normalized
        ):
            _finding(
                findings,
                "manifest.includes",
                f"resource is not covered by an include: {source.relative_path}",
                location,
            )
    return tuple(normalized)


def _skill_records(
    bundles: tuple[BundleSource, ...],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> dict[str, tuple[str, int, str]]:
    """Validate skill metadata and return each skill's description and body."""
    records: dict[str, tuple[str, int, str]] = {}
    prompts: set[str] = set()
    for bundle in bundles:
        paths = {item.relative_path for item in bundle.files if not item.is_directory}
        for document in bundle.files:
            if document.is_symlink:
                _finding(
                    findings,
                    "source.symlink",
                    "source bundle contains a symlink",
                    f"{bundle.path}/.apm/{document.relative_path}",
                )
                continue
            if document.parse_error:
                _finding(
                    findings,
                    "source.parse",
                    "source metadata is malformed or unreadable",
                    f"{bundle.path}/.apm/{document.relative_path}",
                )
            if document.frontmatter_error:
                _finding(
                    findings,
                    "frontmatter.parse",
                    "Markdown frontmatter is malformed",
                    f"{bundle.path}/.apm/{document.relative_path}",
                )
            if document.relative_path.endswith(".instructions.md"):
                _validate_instruction(document, bundle, findings)
            if document.relative_path.startswith("prompts/"):
                _validate_prompt(document, bundle, prompts, findings, description_limit)
            if document.relative_path.endswith("/SKILL.md") or (
                document.relative_path == "SKILL.md"
            ):
                _validate_skill(
                    document,
                    bundle,
                    records,
                    findings,
                    description_limit,
                    body_limit,
                )
            source_name = PurePosixPath(document.relative_path).name.casefold()
            if (
                PurePosixPath(document.relative_path).suffix.lower()
                in {".md", ".markdown"}
                and ".template." not in source_name
            ):
                _check_links(
                    document,
                    paths,
                    findings,
                    base_is_bundle=True,
                )
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
    parts = PurePosixPath(document.relative_path).parts
    name = parts[-1].removesuffix(".prompt.md")
    if (
        len(parts) != _PROMPT_PATH_DEPTH
        or not parts[-1].endswith(".prompt.md")
        or _SKILL_NAME.fullmatch(name) is None
    ):
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
    for field in sorted(set(metadata) - _PROMPT_FIELDS):
        _finding(
            findings,
            "prompt.metadata",
            f"prompt metadata '{field}' is not allowed; tools and models stay native",
            location,
        )
    description = metadata.get("description")
    if (
        not isinstance(description, str)
        or not description.strip()
        or "\n" in description
        or len(description) > description_limit
    ):
        _finding(
            findings,
            "prompt.description",
            f"prompt description must be one line of at most {description_limit} characters",
            location,
        )


def _validate_skill(  # noqa: C901
    document: SourceDocument,
    bundle: BundleSource,
    records: dict[str, tuple[str, int, str]],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> None:
    """Validate a skill name, description, body, and portable metadata."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    if not _mapping(document.frontmatter):
        _finding(findings, "skill.frontmatter", "skill metadata is required", location)
        return
    metadata = document.frontmatter
    name = metadata.get("name")
    description = metadata.get("description")
    parts = PurePosixPath(document.relative_path).parts
    if (
        not isinstance(name, str)
        or len(name) > _MAX_SKILL_NAME_CHARS
        or _SKILL_NAME.fullmatch(name) is None
    ):
        _finding(findings, "skill.name", "skill name is not legal", location)
        return
    if (
        len(parts) != _SKILL_PATH_DEPTH
        or parts[0] != "skills"
        or parts[2] != "SKILL.md"
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
    if any(
        key.casefold() in {"applyto", "apply_to", "scope", "paths"} for key in metadata
    ):
        _finding(
            findings,
            "skill.scope",
            "native scope metadata is not allowed in skill frontmatter",
            location,
        )
    if not isinstance(description, str) or not description:
        _finding(
            findings, "skill.description", "skill description is required", location
        )
        return
    if len(description) > description_limit:
        _finding(
            findings,
            "budget.description",
            f"skill description exceeds {description_limit} characters",
            location,
        )
    text = _document_text(document)
    body = _body_text(text)
    if body is None:
        _finding(
            findings, "skill.body", "skill frontmatter delimiters are invalid", location
        )
        return
    lines = len(body.splitlines())
    if lines > body_limit:
        _finding(
            findings,
            "budget.skill_body",
            f"skill body exceeds {body_limit} lines",
            location,
        )
    records[name] = (description, lines, bundle.name)


class CatalogService:
    """Own pure schema validation, profile selection, and output planning."""

    def __init__(self) -> None:
        """Create the stateless catalog application service."""

    def validate(self, snapshot: CatalogSnapshot) -> CheckReport:  # noqa: C901, PLR0912, PLR0915
        """Validate every source bundle, catalog profile, and strict policy."""
        findings: list[Finding] = []
        catalog = _parse_catalog(snapshot, findings)
        if snapshot.root_is_symlink:
            _finding(findings, "source.symlink", "source root is a symlink", ".")
        for relative in snapshot.root_symlinks:
            _finding(
                findings,
                "source.symlink",
                "source root contains a symlink or junction",
                relative,
            )
        if snapshot.catalog_document is not None:
            _check_hidden_unicode(
                snapshot.catalog_document.text or "",
                "catalog.json",
                findings,
            )
        _check_hidden_unicode(snapshot.catalog, "catalog.json", findings)
        if snapshot.policy_error or snapshot.policy_document is None:
            _finding(
                findings,
                "policy.read",
                "apm-policy.yml is missing or invalid",
                "apm-policy.yml",
            )
        else:
            _policy_mapping(snapshot.policy, "apm-policy.yml", findings)
        if snapshot.policy_document is not None:
            _check_hidden_unicode(
                snapshot.policy_document.text or "",
                "apm-policy.yml",
                findings,
            )
        _check_hidden_unicode(snapshot.policy, "apm-policy.yml", findings)

        for bundle in snapshot.bundles:
            manifest_path = f"{bundle.path}/apm.yml"
            _check_hidden_unicode(
                bundle.manifest_document.text or "",
                manifest_path,
                findings,
            )
            _check_hidden_unicode(bundle.manifest, manifest_path, findings)
            for document in bundle.files:
                path = f"{bundle.path}/.apm/{document.relative_path}"
                _check_hidden_unicode(document.relative_path, path, findings)
                _check_hidden_unicode(document.text or "", path, findings)
                _check_hidden_unicode(document.frontmatter, path, findings)
                _check_hidden_unicode(document.yaml_value, path, findings)

        limits = dict(catalog.budgets) if catalog is not None else {}
        policy_limit = limits.get("policy_lines", 120)
        policy_lines = (
            len(snapshot.policy_document.text.splitlines())
            if snapshot.policy_document is not None
            and snapshot.policy_document.text is not None
            else 0
        )
        if policy_lines > policy_limit:
            _finding(
                findings,
                "budget.policy",
                f"policy exceeds {policy_limit} lines",
                "apm-policy.yml",
            )

        root_documents = {item.relative_path: item for item in snapshot.root_documents}
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
        for required in ("llms.txt",):
            if required not in root_documents:
                _finding(
                    findings, "docs.index", "root llms.txt index is missing", required
                )
        agents = root_documents.get("AGENTS.md")
        if agents is not None and agents.text is not None:
            agent_lines = len(agents.text.splitlines())
            if agent_lines > policy_limit:
                _finding(
                    findings,
                    "budget.agents",
                    f"AGENTS.md exceeds {policy_limit} lines",
                    "AGENTS.md",
                )

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
            _check_hidden_unicode(
                document.text or "",
                document.relative_path,
                findings,
            )
            _check_links(
                document,
                root_available,
                findings,
                base_is_bundle=False,
            )

        skill_records: dict[str, tuple[str, int, str]] = {}
        if catalog is not None:
            skill_records = self._validate_bundles(snapshot, catalog, findings)
            self._validate_profile_budgets(catalog, skill_records, findings)
            native_assets: dict[str, bytes] = {}
            for bundle in snapshot.bundles:
                prefix = "" if bundle.path == "." else f"{bundle.path}/"
                for document in bundle.files:
                    if not document.is_directory:
                        native_assets[f"{prefix}.apm/{document.relative_path}"] = (
                            document.content
                        )
            try:
                validate_native_assets(native_assets, catalog.supported_runtimes)
            except (ValueError, InputTypeError) as error:
                _finding(
                    findings,
                    "native.assets",
                    f"native role assets are invalid: {error}",
                    "catalog.json",
                )
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

    def compose(  # noqa: C901, PLR0912, PLR0915
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
        profile_names = (profile, *features)
        if profile not in {item.name for item in catalog.profiles}:
            raise UnknownProfileError(profile)
        if any(
            name not in {item.name for item in catalog.profiles} for name in features
        ):
            unknown = next(
                name
                for name in features
                if name not in {item.name for item in catalog.profiles}
            )
            raise UnknownProfileError(unknown, kind="feature profile")
        selected_runtimes = runtimes or catalog.supported_runtimes
        if not selected_runtimes or len(set(selected_runtimes)) != len(
            selected_runtimes
        ):
            raise CompositionError(CompositionIssue.RUNTIME_SELECTION)
        if any(
            runtime not in catalog.supported_runtimes for runtime in selected_runtimes
        ):
            raise CompositionError(CompositionIssue.UNSUPPORTED_RUNTIME)

        selected = _effective_bundles(catalog, profile_names)
        limits = dict(catalog.budgets)
        selected_skills = _skill_records(
            snapshot.bundles,
            [],
            limits["description_chars"],
            limits["skill_body_lines"],
        )
        available_skills = {
            name: record
            for name, record in selected_skills.items()
            if record[2] in selected
        }
        if len(skills) != len(set(skills)):
            raise CompositionError(CompositionIssue.DUPLICATE_SKILLS)
        if unavailable := set(skills) - available_skills.keys():
            raise UnavailableSkillsError(unavailable)
        active_skills = set(skills) if skills else set(available_skills)
        selected_descriptions = sum(
            len(available_skills[name][0]) for name in active_skills
        )
        if selected_descriptions > limits["profile_description_chars"]:
            raise CompositionError(CompositionIssue.DESCRIPTION_BUDGET)

        bundle_definitions = {item.name: item for item in catalog.bundles}
        source_bundles = {item.name: item for item in snapshot.bundles}
        output_files: dict[str, bytes] = {}
        folded_destinations: dict[str, str] = {}
        include_paths: set[str] = set()
        selected_documents: list[SourceDocument] = []
        selected_instructions: set[str] = set()
        for name in selected:
            source = source_bundles.get(name)
            if source is None:
                raise UnavailableBundleError(name)
            included = _included_paths(
                source, [], catalog.version, catalog.supported_runtimes
            )
            include_paths.update(f".apm/{item}/" for item in included)
            for document in source.files:
                if document.is_symlink or document.is_directory:
                    continue
                parts = PurePosixPath(document.relative_path).parts
                if parts[0] == "skills" and parts[1] not in active_skills:
                    continue
                # Prompts are project workflows that may link any selected skill.
                if skills and parts[0] == "prompts":
                    continue
                if parts[0] == "instructions":
                    instruction_name = PurePosixPath(
                        document.relative_path
                    ).name.removesuffix(".instructions.md")
                    if (
                        skills
                        and instruction_name in available_skills
                        and instruction_name not in active_skills
                    ):
                        continue
                    selected_instructions.add(instruction_name)
                relative = f".apm/{document.relative_path}"
                folded = relative.casefold()
                if folded in folded_destinations:
                    previous = folded_destinations[folded]
                    raise CompositionCollisionError(
                        previous=previous, relative=relative
                    )
                folded_destinations[folded] = relative
                output_files[relative] = document.content
                selected_documents.append(document)

        if skills:
            available_paths = {name.removeprefix(".apm/") for name in output_files}
            missing_links: list[Finding] = []
            for document in selected_documents:
                _check_links(
                    document, available_paths, missing_links, base_is_bundle=True
                )
            if missing_links:
                first = missing_links[0]
                raise OmittedResourceError(first)
        native_agents = (
            {} if skills else render_native_agents(output_files, selected_runtimes)
        )
        for relative, content in native_agents.items():
            folded = relative.casefold()
            if folded in folded_destinations:
                previous = folded_destinations[folded]
                raise CompositionCollisionError(previous=previous, relative=relative)
            folded_destinations[folded] = relative
            output_files[relative] = content

        selection = {
            "mode": "session" if skills else "project",
            "skills": sorted(active_skills),
            "instructions": sorted(selected_instructions),
            "description_chars": selected_descriptions,
            "instruction_chars": sum(
                len(item.text or "")
                for item in selected_documents
                if item.relative_path.startswith("instructions/")
            ),
            "native_role_files": len(native_agents),
        }
        output_files[".apm/selection.json"] = (
            json.dumps(selection, indent=2) + "\n"
        ).encode("utf-8")
        manifest = {
            "name": f"agent-kit-{profile}",
            "version": catalog.version,
            "targets": list(selected_runtimes),
            "includes": sorted(include_paths),
            "dependencies": {},
            "executables": {},
            "license": "MIT",
            "compilation": {
                "exclude": [".apm/skills", ".agents/skills", ".claude/skills"]
            },
        }
        output_files["apm.yml"] = (
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        policy_document = snapshot.policy_document
        if policy_document is None or policy_document.text is None:
            raise CompositionError(CompositionIssue.POLICY_UNAVAILABLE)
        output_files["apm-policy.yml"] = policy_document.content
        license_document = next(
            (
                item
                for item in snapshot.root_documents
                if item.relative_path == "LICENSE"
            ),
            None,
        )
        if license_document is None:
            raise CompositionError(CompositionIssue.LICENSE_UNAVAILABLE)
        output_files["LICENSE"] = license_document.content

        provenance = {
            "schema_version": 1,
            "source": {
                "catalog_version": catalog.version,
                "profile": profile,
                "bundles": [
                    {
                        "name": name,
                        "path": bundle_definitions[name].path,
                    }
                    for name in selected
                ],
            },
            "files": {
                name: hashlib.sha256(content).hexdigest()
                for name, content in sorted(output_files.items())
            },
        }
        output_files["provenance.json"] = (
            json.dumps(provenance, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
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
    ) -> dict[str, tuple[str, int, str]]:
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
            _included_paths(
                source, findings, catalog.version, catalog.supported_runtimes
            )
        limits = dict(catalog.budgets)
        skill_records = _skill_records(
            snapshot.bundles,
            findings,
            limits["description_chars"],
            limits["skill_body_lines"],
        )
        duplicate_names: set[str] = set()
        seen: set[str] = set()
        for name in skill_records:
            if name in seen:
                duplicate_names.add(name)
            seen.add(name)
        for name in sorted(duplicate_names):
            _finding(
                findings,
                "skill.duplicate",
                f"duplicate skill name '{name}'",
                "catalog.json",
            )
        return skill_records

    def _validate_profile_budgets(
        self,
        catalog: Catalog,
        skills: dict[str, tuple[str, int, str]],
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
        skills: dict[str, tuple[str, int, str]],
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
            effective = [value for value in skills.values() if value[2] in selected]
            summaries.append(
                ProfileSummary(
                    body_lines=sum(item[1] for item in effective),
                    description_chars=sum(len(item[0]) for item in effective),
                    limits=limits,
                    policy_lines=policy_lines,
                    profile=profile.name,
                    skill_count=len(effective),
                )
            )
        return tuple(summaries)
