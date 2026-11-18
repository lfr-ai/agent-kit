"""Own catalog schema parsing, profile references, and profile resolution.

Works on decoded ``catalog.json`` values only; reading files belongs to the
infrastructure adapter.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from posixpath import curdir, pardir
import re
from typing import TYPE_CHECKING, TypeGuard

from agent_kit.application.catalog.errors import UnknownProfileError
from agent_kit.application.findings import add_finding
from agent_kit.core.guards import is_int, is_json_object, is_semantic_version
from agent_kit.core.models import Bundle, BundleKind, Catalog, Profile
from agent_kit.core.primitives import NativeRuntime

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import CatalogSnapshot, Finding

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
_CATALOG_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


def is_text(value: object) -> TypeGuard[str]:
    """Check for a non-empty string, whitespace included."""
    return isinstance(value, str) and bool(value)


def exact_mapping(
    value: object,
    expected: set[str],
    path: str,
    findings: list[Finding],
) -> JSONObject | None:
    """Return the mapping, reporting missing or unknown keys; ``None`` if not one."""
    if not is_json_object(value):
        add_finding(findings, "schema.mapping", "expected an object", path)
        return None
    actual = set(value)
    for name in sorted(expected - actual):
        add_finding(findings, "schema.missing", f"missing field '{name}'", path)
    for name in sorted(actual - expected):
        add_finding(findings, "schema.unknown", f"unknown field '{name}'", path)
    return value


def string_list(
    value: object, path: str, findings: list[Finding]
) -> tuple[str, ...] | None:
    """Return the strings, reporting duplicates; ``None`` for a non-list or bad item."""
    if not isinstance(value, list):
        add_finding(findings, "schema.list", "expected a list of strings", path)
        return None
    strings: list[str] = []
    for index, item in enumerate(value):
        if not is_text(item):
            add_finding(
                findings,
                "schema.string",
                "expected a non-empty string",
                f"{path}[{index}]",
            )
            return None
        strings.append(item)
    if len(set(strings)) != len(strings):
        add_finding(findings, "schema.duplicate", "duplicate list entry", path)
    return tuple(strings)


def is_absolute(value: str) -> bool:
    """Detect POSIX, Windows, and drive-qualified absolute paths."""
    windows = PureWindowsPath(value)
    return (
        PurePosixPath(value).is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
    )


def contained_catalog_path(value: object) -> str | None:
    """Validate a normalized, relative source bundle path."""
    if not is_text(value) or "\\" in value:
        return None
    posix = PurePosixPath(value)
    if is_absolute(value) or pardir in posix.parts:
        return None
    normalized = posix.as_posix()
    if normalized == curdir:
        return curdir
    if normalized.startswith("./") or normalized.endswith("/"):
        return None
    return normalized


def _catalog_schema_version(raw: JSONObject, findings: list[Finding]) -> int | None:
    """Return the supported catalog schema version or report it."""
    value = raw.get("schema_version")
    if is_int(value) and value == 1:
        return value
    add_finding(findings, "catalog.version", "schema_version must be 1", "catalog.json")
    return None


def _catalog_version(raw: JSONObject, findings: list[Finding]) -> str | None:
    """Return the semantic catalog version or report it."""
    value = raw.get("version")
    if is_semantic_version(value):
        return value
    add_finding(
        findings,
        "catalog.version",
        "version must be a semantic version",
        "catalog.json",
    )
    return None


def _catalog_runtimes(
    raw: JSONObject, findings: list[Finding]
) -> tuple[str, ...] | None:
    """Accept only ``tuple(NativeRuntime)``; otherwise report it and return ``None``."""
    location = "catalog.json:supported_runtimes"
    runtimes = string_list(raw.get("supported_runtimes"), location, findings)
    if runtimes is None or runtimes == tuple(NativeRuntime):
        return runtimes
    add_finding(
        findings,
        "catalog.runtime",
        f"supported runtimes must be exactly {' and '.join(NativeRuntime)}",
        location,
    )
    return None


def _catalog_budgets(
    raw: JSONObject, findings: list[Finding]
) -> tuple[tuple[str, int], ...]:
    """Return positive ``(field, limit)`` budgets sorted by field; report the rest."""
    budgets_raw = exact_mapping(
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
            add_finding(
                findings,
                "catalog.budget",
                f"'{key}' must be a positive integer",
                "catalog.json:budgets",
            )
    return tuple(budgets)


def parse_catalog(snapshot: CatalogSnapshot, findings: list[Finding]) -> Catalog | None:
    """Validate exact catalog fields into a typed ``Catalog``; ``None`` if unusable."""
    if snapshot.catalog_error or snapshot.catalog is None:
        add_finding(
            findings,
            "catalog.read",
            "catalog.json is missing or invalid",
            "catalog.json",
        )
        return None
    raw = exact_mapping(snapshot.catalog, _CATALOG_FIELDS, "catalog.json", findings)
    if raw is None:
        return None
    schema_version = _catalog_schema_version(raw, findings)
    version = _catalog_version(raw, findings)
    runtimes = _catalog_runtimes(raw, findings)
    budgets = _catalog_budgets(raw, findings)
    bundles = parse_bundles(raw.get("bundles"), findings)
    profiles = parse_profiles(raw.get("profiles"), findings)
    if bundles is not None and profiles is not None:
        check_references(bundles, profiles, findings)
        check_profile_cycles(profiles, findings)

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
        add_finding(findings, "catalog.name", "bundle name is not legal", location)
    item = exact_mapping(raw_bundle, {"path", "kind"}, location, findings)
    if item is None:
        return None
    path = contained_catalog_path(item.get("path"))
    if path is None:
        add_finding(
            findings,
            "catalog.path",
            "bundle path must be relative and contained in the source root",
            location,
        )
        return None
    try:
        kind = BundleKind(item.get("kind"))
    except ValueError:
        add_finding(findings, "catalog.kind", "bundle kind is invalid", location)
        return None
    return Bundle(kind=kind, name=name, path=path)


def _parse_section[T](
    value: object,
    section: str,
    parse: Callable[[str, object, list[Finding]], T | None],
    findings: list[Finding],
) -> tuple[T, ...] | None:
    """Parse a section's named entries in order; ``None`` if it is not an object."""
    if not is_json_object(value):
        add_finding(
            findings,
            f"catalog.{section}",
            f"{section} must be an object",
            "catalog.json",
        )
        return None
    parsed = (parse(name, item, findings) for name, item in value.items())
    entries = tuple(entry for entry in parsed if entry is not None)
    if not entries:
        add_finding(
            findings,
            f"catalog.{section}",
            f"at least one {section.removesuffix('s')} is required",
            "catalog.json",
        )
    return entries


def parse_bundles(value: object, findings: list[Finding]) -> tuple[Bundle, ...] | None:
    """Validate every named source bundle; ``None`` if ``bundles`` is not an object."""
    return _parse_section(value, "bundles", _parse_bundle, findings)


def _parse_profile(
    name: str, raw_profile: object, findings: list[Finding]
) -> Profile | None:
    """Validate one profile's inheritance and direct bundle references."""
    location = f"catalog.json:profiles:{name}"
    if _CATALOG_NAME.fullmatch(name) is None:
        add_finding(findings, "catalog.name", "profile name is not legal", location)
    item = exact_mapping(raw_profile, {"extends", "bundles"}, location, findings)
    if item is None:
        return None
    extends = string_list(item.get("extends"), f"{location}:extends", findings)
    bundles = string_list(item.get("bundles"), f"{location}:bundles", findings)
    if extends is None or bundles is None:
        return None
    return Profile(bundles=bundles, extends=extends, name=name)


def parse_profiles(
    value: object, findings: list[Finding]
) -> tuple[Profile, ...] | None:
    """Validate every profile; ``None`` if ``profiles`` is not an object."""
    return _parse_section(value, "profiles", _parse_profile, findings)


def check_references(
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
                add_finding(
                    findings,
                    "profile.reference",
                    f"profile extends unknown profile '{name}'",
                    f"catalog.json:profiles:{profile.name}",
                )
        for name in profile.bundles:
            if name not in bundle_names:
                add_finding(
                    findings,
                    "profile.reference",
                    f"profile selects unknown bundle '{name}'",
                    f"catalog.json:profiles:{profile.name}",
                )


def check_profile_cycles(
    profiles: tuple[Profile, ...], findings: list[Finding]
) -> None:
    """Report all profiles participating in inheritance cycles."""
    profile_map = {item.name: item for item in profiles}
    active: set[str] = set()
    complete: set[str] = set()

    def visit(name: str) -> None:
        if name in active:
            add_finding(
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


def effective_bundles(
    catalog: Catalog, profile_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve inheritance into ordered unique bundles; unknown profiles raise."""
    profiles = {item.name: item for item in catalog.profiles}
    selected: list[str] = []
    visited: set[str] = set()
    for name in profile_names:
        _include_profile(name, profiles, selected, visited)
    return tuple(selected)


def resolved_profiles(
    catalog: Catalog,
) -> Iterator[tuple[Profile, tuple[str, ...]]]:
    """Yield each profile with its effective bundle names in first-seen order.

    Profiles that reference unknown parents are skipped because validation reports
    them.
    """
    for profile in catalog.profiles:
        try:
            selected = effective_bundles(catalog, (profile.name,))
        except ValueError:
            continue
        yield profile, selected
