"""Verify or refresh catalog-generated APM profile manifests."""

from __future__ import annotations

import argparse
from enum import StrEnum, unique
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.core.errors import InputTypeError
from agent_kit.core.guards import JsonObject, is_json_object
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

if TYPE_CHECKING:
    from agent_kit.core.models import BundleSource

_ROOT = Path(__file__).resolve().parents[1]
_LOCK_PATH = ".agents/agentic-setup/profile-lock.json"
_PROFILE_ROOT = "profiles"
_PACKAGE_SOURCE_ROOT = "lfr-ai/agent-kit"
_SCHEMA_VERSION = 1
_JSON_INDENT = 2
_RUNTIMES = ("copilot", "claude")
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


def _resolve_root(root: Path) -> Path:
    """Resolve a checkout root only after rejecting linked path components.

    Raises:
        ProfileBuildError: The root or an ancestor is a link or junction.
    """
    absolute = root.absolute()
    for path in (absolute, *absolute.parents):
        if path.is_symlink() or path.is_junction():
            raise ProfileBuildError(_ProfileIssue.LINKED_PATH, path=str(path))
    return absolute.resolve()


def _owned_path(root: Path, relative: str) -> Path:
    """Resolve a generated path without crossing links or leaving the checkout.

    Raises:
        ProfileBuildError: The generated path is linked, unsafe, or escapes ``root``.
    """
    parts = PurePosixPath(relative)
    if (
        root.is_symlink()
        or root.is_junction()
        or parts.is_absolute()
        or PureWindowsPath(relative).drive
        or "\\" in relative
        or ".." in parts.parts
    ):
        raise ProfileBuildError(_ProfileIssue.UNSAFE_PATH, path=relative)
    current = root
    for part in parts.parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ProfileBuildError(_ProfileIssue.LINKED_PATH, path=relative)
    if not current.resolve(strict=False).is_relative_to(root.resolve()):
        raise ProfileBuildError(_ProfileIssue.ESCAPING_PATH, path=relative)
    return current


def _planned_profiles(root: Path) -> dict[str, bytes]:
    """Create one small meta-package manifest for each portable catalog profile.

    Returns:
        dict[str, bytes]: Sorted output paths mapped to UTF-8 manifest bytes;
            an empty plan is rejected.

    Raises:
        ProfileBuildError: The catalog is invalid or has no portable profiles.
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
    return dict(sorted(planned.items()))


def _is_portable(bundle_names: tuple[str, ...], kinds: dict[str, str]) -> bool:
    """Require every catalog bundle in a profile closure to be portable."""
    return all(kinds[name] == "portable" for name in bundle_names)


def _profile_file(
    profile: str,
    version: str,
    bundle_names: tuple[str, ...],
    bundles: dict[str, BundleSource],
) -> dict[str, bytes]:
    """Build a compact profile manifest from its catalog bundle closure.

    Returns:
        dict[str, bytes]: One profile-relative output path mapped to its UTF-8
            manifest bytes.

    Raises:
        ProfileBuildError: A selected bundle has invalid or conflicting MCP data.
    """
    references = [
        f"{_PACKAGE_SOURCE_ROOT}/{bundles[name].path}#{_VERSION_PREFIX}{version}"
        for name in bundle_names
    ]
    manifest = {
        "name": f"agent-kit-profile-{profile}",
        "version": version,
        "license": "MIT",
        "description": f"Agent Kit {profile} profile.",
        "targets": list(_RUNTIMES),
        "includes": [],
        "dependencies": {
            "apm": references,
            "mcp": _profile_mcp(profile, bundle_names, bundles),
        },
        "executables": {},
    }
    content = (json.dumps(manifest, indent=_JSON_INDENT, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return {f"{_PROFILE_ROOT}/{profile}/apm.yml": content}


def _profile_mcp(
    profile: str,
    bundle_names: tuple[str, ...],
    bundles: dict[str, BundleSource],
) -> list[JsonObject]:
    """Merge each selected bundle's validated, direct MCP declarations.

    Raises:
        ProfileBuildError: A bundle has invalid MCP data or conflicting declarations.
    """
    servers: dict[str, JsonObject] = {}
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


def _bundle_mcp(bundle: BundleSource) -> list[JsonObject]:
    """Extract direct MCP declarations from one source package manifest.

    Raises:
        ProfileBuildError: The bundle manifest does not contain validated MCP data.
    """
    if not is_json_object(bundle.manifest):
        raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
    dependencies = bundle.manifest.get("dependencies")
    if not is_json_object(dependencies):
        raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
    mcp = dependencies.get("mcp", [])
    if not isinstance(mcp, list):
        raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
    servers: list[JsonObject] = []
    for server in mcp:
        if not is_json_object(server) or not isinstance(server.get("name"), str):
            raise ProfileBuildError(_ProfileIssue.INVALID_SOURCE, path=bundle.path)
        servers.append(server)
    return servers


def _files_under_profiles(root: Path) -> set[str]:
    """Inventory generated profile files without following links.

    Raises:
        ProfileBuildError: The package tree contains a linked or unsupported path.
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
    """Load the generated-file ledger and reject malformed or unowned entries.

    Returns:
        dict[str, str]: Owned output paths mapped to SHA-256 digests, or an empty
            mapping when the ledger does not exist.

    Raises:
        ProfileBuildError: The ledger cannot be read or contains invalid entries.
    """
    path = _owned_path(root, _LOCK_PATH)
    if not path.exists():
        return {}
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfileBuildError(_ProfileIssue.UNREADABLE_LEDGER) from error
    if (
        not isinstance(ledger, dict)
        or set(ledger) != {"schema_version", "files"}
        or ledger.get("schema_version") != _SCHEMA_VERSION
        or not isinstance(ledger.get("files"), dict)
    ):
        raise ProfileBuildError(_ProfileIssue.INVALID_LEDGER)
    files = ledger["files"]
    if not all(
        isinstance(name, str)
        and name.startswith(f"{_PROFILE_ROOT}/")
        and isinstance(digest, str)
        and _DIGEST.fullmatch(digest) is not None
        for name, digest in files.items()
    ):
        raise ProfileBuildError(_ProfileIssue.INVALID_LEDGER_ENTRY)
    return files


def _check_previous(root: Path, previous: dict[str, str]) -> None:
    for name, digest in previous.items():
        path = _owned_path(root, name)
        if path.exists() and (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ProfileBuildError(_ProfileIssue.EDITED_OUTPUT, path=name)


def _ledger_bytes(planned: dict[str, bytes]) -> bytes:
    hashes = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(planned.items())
    }
    return (
        json.dumps(
            {"schema_version": _SCHEMA_VERSION, "files": hashes},
            indent=_JSON_INDENT,
        )
        + "\n"
    ).encode("utf-8")


def _replace(path: Path, content: bytes) -> None:
    """Atomically replace one generated file after its parents are validated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=".profile-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _restore(root: Path, before: dict[str, bytes | None]) -> None:
    for name, content in before.items():
        path = _owned_path(root, name)
        if content is None:
            path.unlink(missing_ok=True)
        else:
            _replace(path, content)


def _apply(
    root: Path,
    planned: dict[str, bytes],
    removed: set[str],
    before: dict[str, bytes | None],
) -> None:
    complete = False
    try:
        for name, content in planned.items():
            _replace(_owned_path(root, name), content)
        for name in removed:
            _owned_path(root, name).unlink(missing_ok=True)
        complete = True
    finally:
        if not complete:
            _restore(root, before)


def write(root: Path) -> None:
    """Refresh only profile outputs still matching their prior ownership hashes.

    Raises:
        ProfileBuildError: An output is unowned, linked, or independently edited.
    """
    root = _resolve_root(root)
    output = _planned_profiles(root)
    previous = _load_ledger(root)
    _check_previous(root, previous)
    actual = _files_under_profiles(root)
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
    planned = {
        **output,
        _LOCK_PATH: _ledger_bytes(output),
    }
    touched = set(planned) | previous.keys()
    before = {
        name: _owned_path(root, name).read_bytes()
        if _owned_path(root, name).is_file()
        else None
        for name in touched
    }
    changed = {
        name: content for name, content in planned.items() if before[name] != content
    }
    removed = previous.keys() - output.keys()
    _apply(
        root,
        changed,
        removed,
        {name: before[name] for name in changed.keys() | removed},
    )


def check(root: Path) -> list[str]:
    """Report profile manifest, ownership-ledger, and catalog drift."""
    root = _resolve_root(root)
    output = _planned_profiles(root)
    previous = _load_ledger(root)
    expected_hashes = json.loads(_ledger_bytes(output))["files"]
    failures: list[str] = []
    if previous != expected_hashes:
        failures.append("profile ownership ledger differs from catalog output")
    actual = _files_under_profiles(root)
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
