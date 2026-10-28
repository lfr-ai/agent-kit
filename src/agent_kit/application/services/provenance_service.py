"""Verify composed output hashes without relying on source checkout state."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import TypeGuard

from agent_kit.core.models import CheckReport, ComposedSnapshot, Finding, SourceDocument

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")
_NATIVE_PROMPT_DEPTH = 3  # native root/provider/file
_PROVENANCE_FIELDS = frozenset({"schema_version", "source", "files"})
_SOURCE_FIELDS = frozenset({"catalog_version", "profile", "bundles"})
_REQUIRED_FILES = frozenset({"apm.yml", "apm-policy.yml", "LICENSE"})
_DELIVERY_ROOTS = (
    ".agents/skills/",
    ".claude/skills/",
    ".claude/rules/",
    ".github/instructions/",
)
_POST_INSTALL_METADATA = frozenset(
    {"apm.lock.yaml", ".gitignore", "AGENTS.md", "CLAUDE.md"}
)


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow decoded provenance objects to string-keyed mappings."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _path_is_relative(value: str) -> bool:
    """Check that provenance paths cannot name outside files."""
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        bool(value)
        and "\\" not in value
        # PurePosixPath drops "." and empty segments; require the canonical spelling.
        and posix.as_posix() == value
        and not posix.is_absolute()
        and not windows.is_absolute()
        and not windows.drive
        and all(part not in {"", ".", ".."} for part in posix.parts)
    )


def _prompt_source(relative: str) -> str | None:
    """Map flat native prompt projections back to their authored facade."""
    parts = PurePosixPath(relative).parts
    if len(parts) != _NATIVE_PROMPT_DEPTH:
        return None
    name = parts[-1]
    if parts[:-1] == (".github", "prompts") and name.endswith(".prompt.md"):
        return f".apm/prompts/{name}"
    if parts[:-1] == (".claude", "commands") and name.endswith(".md"):
        return f".apm/prompts/{name.removesuffix('.md')}.prompt.md"
    return None


def _finding(findings: list[Finding], code: str, message: str, path: str) -> None:
    """Append one safe provenance diagnostic."""
    findings.append(Finding(code=code, message=message, path=path))


def _check_composed_links(snapshot: ComposedSnapshot, findings: list[Finding]) -> None:
    """Report a symlinked composed root or provenance file."""
    if snapshot.root_is_symlink:
        _finding(findings, "provenance.symlink", "composed root is a symlink", ".")
    if snapshot.provenance_is_symlink:
        _finding(
            findings,
            "provenance.symlink",
            "provenance file is a symlink",
            "provenance.json",
        )


def _provenance_mapping(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> dict[str, object] | None:
    """Return a readable provenance object with exactly the expected fields."""
    if snapshot.provenance_error or snapshot.provenance is None:
        _finding(
            findings,
            "provenance.read",
            "provenance.json is missing or invalid",
            "provenance.json",
        )
        return None
    provenance = snapshot.provenance
    if not _mapping(provenance) or set(provenance) != _PROVENANCE_FIELDS:
        _finding(
            findings,
            "provenance.schema",
            "provenance schema has missing or unknown fields",
            "provenance.json",
        )
        return None
    return provenance


def _check_schema_version(
    provenance: dict[str, object], findings: list[Finding]
) -> None:
    """Require the integer provenance schema version 1."""
    schema_version = provenance.get("schema_version")
    if schema_version != 1 or type(schema_version) is not int:
        _finding(
            findings,
            "provenance.schema",
            "provenance schema_version must be 1",
            "provenance.json",
        )


def _valid_file_hash(digest: object, relative: str) -> TypeGuard[str]:
    """Accept a contained, non-ledger path with a lowercase SHA-256 digest."""
    return (
        _path_is_relative(relative)
        and relative != "provenance.json"
        and isinstance(digest, str)
        and _HASH.fullmatch(digest) is not None
    )


def _expected_hashes(
    expected: dict[str, object], findings: list[Finding]
) -> dict[str, str]:
    """Return valid recorded hashes and report invalid or missing entries."""
    hashes: dict[str, str] = {}
    for relative, digest in expected.items():
        if _valid_file_hash(digest, relative):
            hashes[relative] = digest
        else:
            _finding(
                findings,
                "provenance.path",
                "provenance contains an invalid relative file hash",
                "provenance.json",
            )
    for relative in sorted(_REQUIRED_FILES - set(hashes)):
        _finding(
            findings,
            "provenance.required",
            f"provenance does not hash required file '{relative}'",
            "provenance.json",
        )
    return hashes


def _native_digest(document: SourceDocument) -> str:
    """Hash text with normalized line endings, as native delivery records it."""
    content = document.content
    if document.text is not None and b"\x00" not in content:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _actual_hashes(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> tuple[dict[str, str], dict[str, str]]:
    """Hash captured bytes, not unreadable placeholders or parsed YAML values."""
    actual: dict[str, str] = {}
    native_actual: dict[str, str] = {}
    for document in snapshot.files:
        if document.is_symlink:
            _finding(
                findings,
                "provenance.symlink",
                "composed output contains a symlink",
                document.relative_path,
            )
        elif document.parse_error and document.text is None:
            # Readable malformed YAML has text; failed captures have neither.
            _finding(
                findings,
                "provenance.read",
                "composed file could not be read; check permissions and retry",
                document.relative_path,
            )
        elif not document.is_directory:
            actual[document.relative_path] = hashlib.sha256(
                document.content
            ).hexdigest()
            native_actual[document.relative_path] = _native_digest(document)
    return actual, native_actual


def _check_delivery_drift(
    delivery: dict[str, str], native_actual: dict[str, str], findings: list[Finding]
) -> None:
    """Report native files whose bytes differ from the APM ledger."""
    for relative, digest in delivery.items():
        if native_actual.get(relative) != digest:
            _finding(
                findings,
                "provenance.delivery-drift",
                f"native file does not match its APM ledger: {relative}",
                relative,
            )


def _check_recorded_files(
    expected: dict[str, str],
    actual: dict[str, str],
    permitted: set[str],
    findings: list[Finding],
) -> None:
    """Report missing, unrecorded, and drifted composed files."""
    for relative in sorted(expected.keys() - actual.keys()):
        _finding(
            findings,
            "provenance.missing",
            f"recorded file is missing: {relative}",
            relative,
        )
    for relative in sorted(actual.keys() - permitted):
        _finding(
            findings,
            "provenance.extra",
            f"unrecorded file exists: {relative}",
            relative,
        )
    for relative in sorted(actual.keys() & expected.keys()):
        if actual[relative] != expected[relative]:
            _finding(
                findings,
                "provenance.drift",
                f"file hash does not match provenance: {relative}",
                relative,
            )


def _source_version(source: object, *, source_valid: bool) -> str | None:
    """Return the recorded catalog version of valid source metadata."""
    if not source_valid or not _mapping(source):
        return None
    candidate = source.get("catalog_version")
    return candidate if isinstance(candidate, str) else None


def _ledger_deployments(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> list[object] | None:
    """Return APM ledger deployments, or ``None`` when absent or invalid."""
    lock = next(
        (item for item in snapshot.files if item.relative_path == "apm.lock.yaml"),
        None,
    )
    if lock is None:
        return None
    value = lock.yaml_value
    if not _mapping(value) or value.get("lockfile_version") != "1":
        _finding(
            findings, "provenance.delivery", "APM ledger is invalid", "apm.lock.yaml"
        )
        return None
    deployments = value.get("deployments")
    if not isinstance(deployments, list):
        _finding(
            findings,
            "provenance.delivery",
            "APM deployments must be a list",
            "apm.lock.yaml",
        )
        return None
    return deployments


def _approved_delivery(
    item: dict[str, object], relative: str, digest: str, authored: dict[str, str]
) -> bool:
    """Accept only project-owned first-party deliveries with SHA-256 digests."""
    prompt_source = _prompt_source(relative)
    return (
        item.get("kind") == "project-relative"
        and item.get("scope") == "project"
        and item.get("owners") == ["."]
        and item.get("active_owner") == "."
        and _path_is_relative(relative)
        and (
            relative.startswith(_DELIVERY_ROOTS)
            or (prompt_source is not None and prompt_source in authored)
        )
        and digest.startswith("sha256:")
        and _HASH.fullmatch(digest.removeprefix("sha256:")) is not None
    )


def _delivery_entry(
    item: object, authored: dict[str, str], findings: list[Finding]
) -> tuple[str, str] | None:
    """Return one approved ledger path and digest, reporting rejected entries."""
    if not _mapping(item):
        _finding(
            findings, "provenance.delivery", "APM entry is invalid", "apm.lock.yaml"
        )
        return None
    relative = item.get("value")
    digest = item.get("content_hash")
    if digest is None:
        return None
    if (
        not isinstance(relative, str)
        or not isinstance(digest, str)
        or not _approved_delivery(item, relative, digest, authored)
    ):
        _finding(
            findings,
            "provenance.delivery",
            "APM entry is not an approved first-party delivery",
            "apm.lock.yaml",
        )
        return None
    return relative, digest.removeprefix("sha256:")


def _bundle_name(item: object) -> str | None:
    """Return the name of a well-formed, contained source bundle identity."""
    if not _mapping(item) or set(item) != {"name", "path"}:
        return None
    name = item.get("name")
    path = item.get("path")
    if (
        not isinstance(name, str)
        or not isinstance(path, str)
        or not _path_is_relative(path)
    ):
        return None
    return name


def _source_identity_valid(source: dict[str, object], findings: list[Finding]) -> bool:
    """Require a semantic catalog version and a non-empty profile name."""
    version = source.get("catalog_version")
    profile = source.get("profile")
    valid = (
        isinstance(version, str)
        and _VERSION.fullmatch(version) is not None
        and isinstance(profile, str)
        and bool(profile)
    )
    if not valid:
        _finding(
            findings,
            "provenance.source",
            "provenance source identity is invalid",
            "provenance.json",
        )
    return valid


def _source_bundles_valid(bundles: list[object], findings: list[Finding]) -> bool:
    """Require well-formed, uniquely named source bundle identities."""
    valid = True
    names: set[str] = set()
    for item in bundles:
        name = _bundle_name(item)
        if name is None:
            _finding(
                findings,
                "provenance.source",
                "provenance bundle identity is invalid",
                "provenance.json",
            )
            valid = False
            continue
        if name in names:
            _finding(
                findings,
                "provenance.source",
                "provenance contains a duplicate source bundle",
                "provenance.json",
            )
            valid = False
        names.add(name)
    return valid


class ProvenanceService:
    """Own the pure, read-only composed-workspace integrity check."""

    def __init__(self) -> None:
        """Create the stateless provenance verifier."""

    def verify(self, snapshot: ComposedSnapshot) -> CheckReport:
        """Compare all recorded hashes with the captured composed workspace."""
        findings: list[Finding] = []
        _check_composed_links(snapshot, findings)
        provenance = _provenance_mapping(snapshot, findings)
        if provenance is None:
            return CheckReport(findings=tuple(findings), profiles=(), version=None)
        _check_schema_version(provenance, findings)
        source = provenance.get("source")
        source_valid = self._validate_source(source, findings)
        expected = provenance.get("files")
        if not _mapping(expected):
            self._add(
                findings,
                "provenance.schema",
                "provenance files must be an object",
                "provenance.json",
            )
            return CheckReport(findings=tuple(findings), profiles=(), version=None)

        expected_hashes = _expected_hashes(expected, findings)
        actual, native_actual = _actual_hashes(snapshot, findings)
        delivery, metadata_paths = self._delivery_hashes(
            snapshot, findings, authored=expected_hashes
        )
        _check_delivery_drift(delivery, native_actual, findings)
        permitted = expected_hashes.keys() | delivery.keys() | metadata_paths
        _check_recorded_files(expected_hashes, actual, permitted, findings)
        return CheckReport(
            findings=tuple(
                sorted(findings, key=lambda item: (item.path, item.code, item.message))
            ),
            profiles=(),
            version=_source_version(source, source_valid=source_valid),
        )

    def _delivery_hashes(
        self,
        snapshot: ComposedSnapshot,
        findings: list[Finding],
        *,
        authored: dict[str, str],
    ) -> tuple[dict[str, str], set[str]]:
        """Permit exact first-party native entries, not arbitrary runtime trees."""
        deployments = _ledger_deployments(snapshot, findings)
        if deployments is None:
            return {}, set()
        hashes: dict[str, str] = {}
        for item in deployments:
            entry = _delivery_entry(item, authored, findings)
            if entry is not None:
                relative, digest = entry
                hashes[relative] = digest
        # These are post-installation metadata, not authored source bytes.
        # Review compiled context separately; APM audits its owned delivery.
        return hashes, set(_POST_INSTALL_METADATA)

    def _validate_source(self, value: object, findings: list[Finding]) -> bool:
        """Require relative source provenance with explicit bundle ownership."""
        if not _mapping(value) or set(value) != _SOURCE_FIELDS:
            self._add(
                findings,
                "provenance.source",
                "provenance source metadata has missing or unknown fields",
                "provenance.json",
            )
            return False
        identity_valid = _source_identity_valid(value, findings)
        bundles = value.get("bundles")
        if not isinstance(bundles, list) or not bundles:
            self._add(
                findings,
                "provenance.source",
                "provenance must list selected source bundles",
                "provenance.json",
            )
            return False
        return _source_bundles_valid(bundles, findings) and identity_valid

    def _add(self, findings: list[Finding], code: str, message: str, path: str) -> None:
        """Append one safe provenance diagnostic."""
        _finding(findings, code, message, path)
