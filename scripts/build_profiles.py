"""Verify or refresh ledger-owned APM profiles and native role packages."""

from __future__ import annotations

import argparse
from enum import StrEnum, unique
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import TYPE_CHECKING, Final

from agent_kit.application.catalog import CatalogService
from agent_kit.application.native_delivery import render_native_agents
from agent_kit.core.errors import InputTypeError
from agent_kit.core.guards import JSONObject, is_json_object
from agent_kit.core.models import BundleKind
from agent_kit.core.primitives import JSON_INDENT, NativeRuntime
from agent_kit.infrastructure.catalog import FileCatalogAdapter
from agent_kit.infrastructure.owned_output import (
    OwnedPathError,
    OwnedPathIssue,
    ledger_entries,
    ledger_hashes,
    owned_path,
    publish_owned,
)

if TYPE_CHECKING:
    from agent_kit.core.models import BundleSource

PACKAGE_SOURCE: Final[str] = "lfr-ai/agent-kit"
PACKAGE_GIT: Final[str] = f"https://github.com/{PACKAGE_SOURCE}.git"
LICENSE: Final[str] = "MIT"  # SPDX expression of every generated or released package
_ROOT = Path(__file__).resolve().parents[1]
_LOCK_PATH = ".agents/agentic-setup/profile-lock.json"
_PROFILE_ROOT = "profiles"
_RUNTIMES = tuple(NativeRuntime)
_NATIVE_ROOT = f"{_PROFILE_ROOT}/native"
_VERSION_PREFIX = "v"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@unique
class _ProfileIssue(StrEnum):
    """Closed set of profile generation and ownership violations."""

    UNSAFE_PATH = "generated path is unsafe"
    LINKED_PATH = "generated path contains a link"
    ESCAPING_PATH = "generated path escapes the checkout"
    NON_REGULAR_FILE = "generated path is not a regular file"
    UNREADABLE_LEDGER = "profile ownership ledger is unreadable"
    INVALID_LEDGER = "profile ownership ledger is invalid"
    INVALID_LEDGER_ENTRY = "profile ownership ledger contains an invalid path or hash"
    EDITED_OUTPUT = "generated profile was edited independently"
    INVALID_SOURCE = "catalog source validation failed"
    NO_PORTABLE_PROFILES = "catalog has no portable profiles to publish"
    CONFLICTING_MCP = "profile bundles declare conflicting MCP servers"
    UNOWNED_FILES = "unowned files exist under profiles/"
    EXISTING_UNOWNED_OUTPUT = "unowned profile output already exists"


class ProfileBuildError(ValueError):
    """Report a profile generation or ownership contract failure."""

    def __init__(self, issue: _ProfileIssue, *, path: str | None = None) -> None:
        """Retain the fixed issue and optional source-relative path.

        Args:
            issue (_ProfileIssue): Failed profile generation invariant.
            path (str | None): Generated path associated with the failure.
        """
        self.issue = issue
        self.path = path
        message = f"{issue.value}: {path}" if path is not None else issue.value
        super().__init__(message)


_PATH_ISSUES = {
    OwnedPathIssue.UNSAFE: _ProfileIssue.UNSAFE_PATH,
    OwnedPathIssue.LINKED: _ProfileIssue.LINKED_PATH,
    OwnedPathIssue.ESCAPING: _ProfileIssue.ESCAPING_PATH,
}


def _resolve_root(root: Path) -> Path:
    """Resolve ``root``; a linked root or ancestor raises ``ProfileBuildError``."""
    absolute = root.absolute()
    for path in (absolute, *absolute.parents):
        if path.is_symlink() or path.is_junction():
            raise ProfileBuildError(_ProfileIssue.LINKED_PATH, path=str(path))
    return absolute.resolve()


def _owned_path(root: Path, relative: str) -> Path:
    """Resolve a generated path beneath ``root``; violations raise ``ProfileBuildError``."""
    try:
        return owned_path(root, relative)
    except OwnedPathError as error:
        raise ProfileBuildError(_PATH_ISSUES[error.issue], path=relative) from error


def _planned_profiles(root: Path) -> dict[str, bytes]:
    """Plan one small meta-package manifest for each portable catalog profile.

    Sorted output paths map to UTF-8 file bytes. An invalid catalog or one without
    portable profiles raises ``ProfileBuildError``.
    """
    snapshot = FileCatalogAdapter().load(root)
    service = CatalogService()
    report = service.validate(snapshot)
    if not report.valid or report.version is None:
        raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE)
    bundle_kinds = {bundle.name: bundle.kind for bundle in snapshot.bundles}
    bundles = {bundle.name: bundle for bundle in snapshot.bundles}
    planned: dict[str, bytes] = {}
    for summary in report.profiles:
        plan = service.compose(snapshot, summary.profile, (), _RUNTIMES)
        if not _is_portable(plan.bundles, bundle_kinds):
            continue
        planned.update(
            _profile_file(
                summary.profile,
                report.version,
                plan.bundles,
                bundles,
            )
        )
    if not planned:
        raise ProfileBuildError(_ProfileIssue.NO_PORTABLE_PROFILES)
    planned.update(_native_packages(snapshot.bundles, version=report.version))
    return dict(sorted(planned.items()))


def _native_packages(
    bundles: tuple[BundleSource, ...], *, version: str
) -> dict[str, bytes]:
    """Package the shared renderer's bytes without translating native metadata."""
    assets = {
        f"{bundle.path}/.apm/{document.relative_path}": document.content
        for bundle in bundles
        for document in bundle.files
        if not document.is_directory
    }
    files: dict[str, bytes] = {}
    for runtime in _RUNTIMES:
        package = f"{_NATIVE_ROOT}/{runtime}"
        manifest: JSONObject = {
            "name": f"agent-kit-native-{runtime}",
            "version": version,
            "license": LICENSE,
            "description": f"Agent Kit native {runtime} roles.",
            "targets": [runtime],
            "includes": [".apm/agents/"],
            "dependencies": {},
            "executables": {},
        }
        files[f"{package}/apm.yml"] = _manifest_bytes(manifest)
        for path, content in render_native_agents(assets, (runtime,)).items():
            files[f"{package}/.apm/agents/{PurePosixPath(path).name}"] = content
    return files


def _manifest_bytes(manifest: JSONObject) -> bytes:
    """Encode deterministic JSON, an APM-compatible YAML subset."""
    return (json.dumps(manifest, indent=JSON_INDENT, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _is_portable(bundle_names: tuple[str, ...], kinds: dict[str, str | None]) -> bool:
    """Require every catalog bundle in a profile closure to be portable."""
    return all(kinds[name] == BundleKind.PORTABLE for name in bundle_names)


def _profile_file(
    profile: str,
    version: str,
    bundle_names: tuple[str, ...],
    bundles: dict[str, BundleSource],
) -> dict[str, bytes]:
    """Build a compact profile manifest from its catalog bundle closure.

    Invalid or conflicting MCP data in a selected bundle raises
    ``ProfileBuildError``.

    Returns:
        dict[str, bytes]: One profile-relative output path mapped to its UTF-8
            manifest bytes.
    """
    references: list[object] = [
        f"{PACKAGE_SOURCE}/{bundles[name].path}#{_VERSION_PREFIX}{version}"
        for name in bundle_names
    ]
    references.extend(
        {
            "git": PACKAGE_GIT,
            "path": f"{_NATIVE_ROOT}/{runtime}",
            "ref": f"{_VERSION_PREFIX}{version}",
            "targets": [runtime],
        }
        for runtime in _RUNTIMES
    )
    manifest = {
        "name": f"agent-kit-profile-{profile}",
        "version": version,
        "license": LICENSE,
        "description": f"Agent Kit {profile} profile.",
        "targets": list(_RUNTIMES),
        "includes": [],
        "dependencies": {
            "apm": references,
            "mcp": _profile_mcp(profile, bundle_names, bundles),
        },
        "executables": {},
    }
    relative = (
        f"{_PROFILE_ROOT}/starters/{profile.removeprefix('starter-')}"
        if profile.startswith("starter-")
        else f"{_PROFILE_ROOT}/{profile}"
    )
    return {f"{relative}/apm.yml": _manifest_bytes(manifest)}


def _profile_mcp(
    profile: str,
    bundle_names: tuple[str, ...],
    bundles: dict[str, BundleSource],
) -> list[JSONObject]:
    """Merge each selected bundle's validated, direct MCP declarations.

    Raises:
        ProfileBuildError: A bundle has invalid MCP data or conflicting declarations.
    """
    servers: dict[str, JSONObject] = {}
    for name in bundle_names:
        bundle = bundles[name]
        for server in _bundle_mcp(bundle):
            server_name = server.get("name")
            if not isinstance(server_name, str):
                raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
            previous = servers.get(server_name)
            if previous is not None and previous != server:
                raise ProfileBuildError(
                    _ProfileIssue.CONFLICTING_MCP,
                    path=f"{profile}: {server_name}",
                )
            servers[server_name] = server
    return list(servers.values())


def _bundle_mcp(bundle: BundleSource) -> list[JSONObject]:
    """Extract direct MCP declarations from one source package manifest.

    A manifest without validated MCP data raises ``ProfileBuildError``.
    """
    if not is_json_object(bundle.manifest):
        raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
    dependencies = bundle.manifest.get("dependencies")
    if not is_json_object(dependencies):
        raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
    mcp = dependencies.get("mcp", [])
    if not isinstance(mcp, list):
        raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
    servers: list[JSONObject] = []
    for server in mcp:
        if not is_json_object(server) or not isinstance(server.get("name"), str):
            raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
        servers.append(server)
    return servers


def _files_under_profiles(root: Path) -> set[str]:
    """Inventory generated profile files without following links.

    The set is empty when the profile root is absent; an entry that is neither a
    directory nor a regular file raises ``ProfileBuildError``.
    """
    base = _owned_path(root, _PROFILE_ROOT)
    if not base.exists():
        return set()
    found: set[str] = set()
    pending = [base]
    while pending:
        directory = pending.pop()
        for entry in directory.iterdir():
            relative = entry.relative_to(root).as_posix()
            path = _owned_path(root, relative)
            if path.is_dir():
                pending.append(path)
            elif path.is_file():
                found.add(relative)
            else:
                raise ProfileBuildError(_ProfileIssue.NON_REGULAR_FILE, path=relative)
    return found


def _load_ledger(root: Path) -> dict[str, str]:
    """Return the ledger's owned output paths mapped to SHA-256 digests.

    A missing ledger gives an empty mapping; an unreadable or malformed ledger,
    or an unowned entry, raises ``ProfileBuildError``.
    """
    path = _owned_path(root, _LOCK_PATH)
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfileBuildError(_ProfileIssue.UNREADABLE_LEDGER) from error
    files = ledger_entries(document)
    if files is None:
        raise ProfileBuildError(_ProfileIssue.INVALID_LEDGER)
    hashes = {
        name: digest
        for name, digest in files.items()
        if name.startswith(f"{_PROFILE_ROOT}/")
        and isinstance(digest, str)
        and _DIGEST.fullmatch(digest) is not None
    }
    if len(hashes) != len(files):
        raise ProfileBuildError(_ProfileIssue.INVALID_LEDGER_ENTRY)
    return hashes


def _check_previous(
    root: Path, previous: dict[str, str], planned: dict[str, bytes]
) -> None:
    for name, digest in previous.items():
        path = _owned_path(root, name)
        if not path.exists():
            continue
        if not path.is_file():
            raise ProfileBuildError(_ProfileIssue.EDITED_OUTPUT, path=name)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest and content != planned.get(
            name
        ):
            # A failed prior publication may leave canonical bytes before the ledger.
            raise ProfileBuildError(_ProfileIssue.EDITED_OUTPUT, path=name)


def write(root: Path) -> None:
    """Refresh profiles and native packages only after auditing prior ownership.

    Unowned generated output raises ``ProfileBuildError``; a failed publication
    rolls back the files already written.
    """
    root = _resolve_root(root)
    previous = _load_ledger(root)
    # Audit generated links first; the source scan would report them as invalid.
    actual = _files_under_profiles(root)
    output = _planned_profiles(root)
    _check_previous(root, previous, output)
    unowned = actual - previous.keys()
    if unowned:
        raise ProfileBuildError(
            _ProfileIssue.UNOWNED_FILES,
            path=", ".join(sorted(unowned)),
        )
    for name in output:
        path = _owned_path(root, name)
        if path.exists() and name not in previous:
            raise ProfileBuildError(_ProfileIssue.EXISTING_UNOWNED_OUTPUT, path=name)
    publish_owned(
        output,
        previous,
        ledger=_LOCK_PATH,
        resolve=lambda name: _owned_path(root, name),
    )


def check(root: Path) -> list[str]:
    """Report profile manifest, ownership-ledger, and catalog drift."""
    root = _resolve_root(root)
    actual = _files_under_profiles(root)
    output = _planned_profiles(root)
    previous = _load_ledger(root)
    failures: list[str] = []
    if previous != ledger_hashes(output):
        failures.append("profile ownership ledger differs from catalog output")
    failures.extend(
        f"missing profile output: {name}" for name in sorted(output.keys() - actual)
    )
    failures.extend(
        f"unexpected profile output: {name}" for name in sorted(actual - output.keys())
    )
    for name, content in output.items():
        path = _owned_path(root, name)
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            failures.append(f"profile output differs from catalog: {name}")
    return failures


def main() -> int:
    """Check generated profiles by default; ``--write`` refreshes attested files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.write:
            write(arguments.root)
            failures: list[str] = []
        else:
            failures = check(arguments.root)
    except (OSError, ValueError, InputTypeError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write(
        "Catalog-generated APM profile manifests and ownership hashes passed.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
