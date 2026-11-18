"""Own bundle manifest validation, include coverage, and the composed manifest.

Manifests must declare explicit ``.apm`` includes, MIT licensing, no scripts or
executables, and only allow-listed MCP servers.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from posixpath import pardir
from typing import TYPE_CHECKING

from agent_kit.application.catalog.errors import CompositionError, CompositionIssue
from agent_kit.application.catalog.policy import MCP_ALLOWED
from agent_kit.application.catalog.schema import is_text, string_list
from agent_kit.application.findings import add_finding
from agent_kit.core.executables import mcp_issues
from agent_kit.core.guards import is_json_object, is_semantic_version

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import BundleSource, Catalog, CatalogSnapshot, Finding

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


def _covers(prefix: str, path: str) -> bool:
    """Check whether ``path`` equals ``prefix`` or lies beneath it."""
    return path == prefix or path.startswith(f"{prefix}/")


def _manifest_mapping(
    bundle: BundleSource, location: str, findings: list[Finding]
) -> JSONObject | None:
    """Return a readable manifest object or report why it is unusable."""
    if bundle.manifest_error or bundle.manifest is None:
        add_finding(
            findings, "manifest.read", "apm.yml is missing or invalid", location
        )
        return None
    manifest = bundle.manifest
    if not is_json_object(manifest):
        add_finding(findings, "manifest.schema", "manifest must be an object", location)
        return None
    return manifest


def _check_manifest_fields(
    manifest: JSONObject, location: str, findings: list[Finding]
) -> None:
    """Report missing, unknown, prohibited, and unlicensed manifest fields."""
    for field in sorted(_MANIFEST_REQUIRED - set(manifest)):
        add_finding(findings, "manifest.missing", f"missing field '{field}'", location)
    for field in sorted(set(manifest) - _MANIFEST_ALLOWED):
        add_finding(findings, "manifest.unknown", f"unknown field '{field}'", location)
    if "scripts" in manifest:
        add_finding(
            findings, "manifest.scripts", "manifest scripts are prohibited", location
        )
    if manifest.get("license") != "MIT":
        add_finding(
            findings, "manifest.license", "toolkit bundles must declare MIT", location
        )
    if not is_text(manifest.get("name")):
        add_finding(findings, "manifest.name", "manifest name is required", location)


def _check_manifest_version(
    manifest: JSONObject, version: str, location: str, findings: list[Finding]
) -> None:
    """Require a semantic manifest version equal to the catalog version."""
    manifest_version = manifest.get("version")
    if not is_semantic_version(manifest_version):
        add_finding(
            findings, "manifest.version", "manifest version is invalid", location
        )
    elif manifest_version != version:
        add_finding(
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
    """Require non-empty supported targets; ``None`` means already reported."""
    if targets is not None and (
        not targets or any(runtime not in supported_runtimes for runtime in targets)
    ):
        add_finding(
            findings, "manifest.targets", "manifest targets are invalid", location
        )


def _check_manifest_executables(
    manifest: JSONObject, location: str, findings: list[Finding]
) -> None:
    """Require empty ``executables`` and only validated MCP dependencies."""
    if manifest.get("executables") != {}:
        add_finding(
            findings, "manifest.executables", "executables must be empty", location
        )
    dependencies = manifest.get("dependencies")
    if not is_json_object(dependencies) or set(dependencies) - {"mcp"}:
        add_finding(
            findings,
            "manifest.dependencies",
            "dependencies may only declare mcp servers",
            location,
        )
    elif "mcp" in dependencies:
        for issue in mcp_issues(dependencies["mcp"], allowed=MCP_ALLOWED):
            add_finding(findings, "manifest.mcp", issue, location)


def _include_issue(include: str, path: PurePosixPath) -> str | None:
    """Return why an include is not a contained ``.apm`` path, if it is not."""
    if not include.startswith(".apm/") or "\\" in include:
        return "includes must name paths beneath .apm"
    if pardir in path.parts:
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
            add_finding(findings, "manifest.includes", issue, location)
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
            add_finding(
                findings,
                "manifest.includes",
                f"include path has no resources: .apm/{include}",
                location,
            )
    for source in bundle.files:
        if not any(_covers(include, source.relative_path) for include in normalized):
            add_finding(
                findings,
                "manifest.includes",
                f"resource is not covered by an include: {source.relative_path}",
                location,
            )


def included_paths(
    bundle: BundleSource,
    findings: list[Finding],
    version: str,
    supported_runtimes: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate the manifest; return ``.apm``-relative includes, ``()`` if unusable."""
    location = f"{bundle.path}/apm.yml"
    manifest = _manifest_mapping(bundle, location, findings)
    if manifest is None:
        return ()
    _check_manifest_fields(manifest, location, findings)
    _check_manifest_version(manifest, version, location, findings)
    targets = string_list(manifest.get("targets"), f"{location}:targets", findings)
    includes = string_list(manifest.get("includes"), f"{location}:includes", findings)
    _check_manifest_targets(targets, supported_runtimes, location, findings)
    _check_manifest_executables(manifest, location, findings)
    if includes is None:
        return ()
    if not includes:
        add_finding(
            findings,
            "manifest.includes",
            "manifest must declare explicit includes",
            location,
        )
        return ()
    normalized = _normalized_includes(includes, location, findings)
    _check_include_coverage(bundle, normalized, location, findings)
    return normalized


def _bundle_mcp(bundle: BundleSource) -> list[JSONObject]:
    """Return the validated MCP declarations of one source bundle's manifest."""
    match bundle.manifest:
        case {"dependencies": {"mcp": list() as entries}}:
            return [entry for entry in entries if is_json_object(entry)]
        case _:
            return []


def selected_mcp(
    snapshot: CatalogSnapshot, selected: tuple[str, ...]
) -> list[JSONObject]:
    """Merge the selected bundles' MCP declarations in a stable order.

    Returns:
        list[JSONObject]: One declaration per server, sorted by server name.

    Raises:
        CompositionError: Two bundles declare one server name differently.
    """
    merged: dict[str, JSONObject] = {}
    chosen = set(selected)
    for bundle in snapshot.bundles:
        if bundle.name not in chosen:
            continue
        for entry in _bundle_mcp(bundle):
            name = str(entry.get("name"))
            if merged.setdefault(name, entry) != entry:
                raise CompositionError(CompositionIssue.MCP_CONFLICT)
    return [merged[name] for name in sorted(merged)]


def manifest_record(
    profile: str,
    catalog: Catalog,
    runtimes: tuple[str, ...],
    include_paths: set[str],
    mcp: list[JSONObject],
) -> JSONObject:
    """Build the composed APM manifest for the selected runtimes.

    Returns:
        JSONObject: Manifest with ``name``, ``version``, ``targets``, sorted
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
