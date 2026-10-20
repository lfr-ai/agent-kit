"""Verify composed output hashes without relying on source checkout state."""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import TypeGuard

from agent_kit.core.models import CheckReport, ComposedSnapshot, Finding

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")


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
    if len(parts) != 3:  # noqa: PLR2004 - native root/provider/file
        return None
    name = parts[-1]
    if parts[:2] == (".github", "prompts") and name.endswith(".prompt.md"):
        return f".apm/prompts/{name}"
    if parts[:2] == (".claude", "commands") and name.endswith(".md"):
        return f".apm/prompts/{name.removesuffix('.md')}.prompt.md"
    return None


class ProvenanceService:
    """Own the pure, read-only composed-workspace integrity check."""

    def __init__(self) -> None:
        """Create the stateless provenance verifier."""

    def verify(self, snapshot: ComposedSnapshot) -> CheckReport:  # noqa: C901, PLR0912
        """Compare all recorded hashes with the captured composed workspace."""
        findings: list[Finding] = []
        if snapshot.root_is_symlink:
            self._add(findings, "provenance.symlink", "composed root is a symlink", ".")
        if snapshot.provenance_is_symlink:
            self._add(
                findings,
                "provenance.symlink",
                "provenance file is a symlink",
                "provenance.json",
            )
        if snapshot.provenance_error or snapshot.provenance is None:
            self._add(
                findings,
                "provenance.read",
                "provenance.json is missing or invalid",
                "provenance.json",
            )
            return CheckReport(findings=tuple(findings), profiles=(), version=None)

        provenance = snapshot.provenance
        if not _mapping(provenance) or set(provenance) != {
            "schema_version",
            "source",
            "files",
        }:
            self._add(
                findings,
                "provenance.schema",
                "provenance schema has missing or unknown fields",
                "provenance.json",
            )
            return CheckReport(findings=tuple(findings), profiles=(), version=None)
        if (
            provenance.get("schema_version") != 1
            or type(provenance.get("schema_version")) is not int
        ):
            self._add(
                findings,
                "provenance.schema",
                "provenance schema_version must be 1",
                "provenance.json",
            )
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

        expected_hashes: dict[str, str] = {}
        for relative, digest in expected.items():
            if (
                not _path_is_relative(relative)
                or relative == "provenance.json"
                or not isinstance(digest, str)
                or _HASH.fullmatch(digest) is None
            ):
                self._add(
                    findings,
                    "provenance.path",
                    "provenance contains an invalid relative file hash",
                    "provenance.json",
                )
                continue
            expected_hashes[relative] = digest
        required = {"apm.yml", "apm-policy.yml", "LICENSE"}
        if not required.issubset(expected_hashes):
            for relative in sorted(required - set(expected_hashes)):
                self._add(
                    findings,
                    "provenance.required",
                    f"provenance does not hash required file '{relative}'",
                    "provenance.json",
                )

        actual: dict[str, str] = {}
        native_actual: dict[str, str] = {}
        for document in snapshot.files:
            if document.is_symlink:
                self._add(
                    findings,
                    "provenance.symlink",
                    "composed output contains a symlink",
                    document.relative_path,
                )
                continue
            if document.is_directory:
                continue
            actual[document.relative_path] = hashlib.sha256(
                document.content
            ).hexdigest()
            native_bytes = document.content
            if document.text is not None and b"\x00" not in native_bytes:
                native_bytes = native_bytes.replace(b"\r\n", b"\n")
            native_actual[document.relative_path] = hashlib.sha256(
                native_bytes
            ).hexdigest()
        delivery, metadata_paths = self._delivery_hashes(
            snapshot, findings, authored=expected_hashes
        )
        for relative, digest in delivery.items():
            if native_actual.get(relative) != digest:
                self._add(
                    findings,
                    "provenance.delivery-drift",
                    f"native file does not match its APM ledger: {relative}",
                    relative,
                )
        for relative in sorted(expected_hashes.keys() - actual.keys()):
            self._add(
                findings,
                "provenance.missing",
                f"recorded file is missing: {relative}",
                relative,
            )
        permitted = expected_hashes.keys() | delivery.keys() | metadata_paths
        for relative in sorted(actual.keys() - permitted):
            self._add(
                findings,
                "provenance.extra",
                f"unrecorded file exists: {relative}",
                relative,
            )
        for relative in sorted(actual.keys() & expected_hashes.keys()):
            if actual[relative] != expected_hashes[relative]:
                self._add(
                    findings,
                    "provenance.drift",
                    f"file hash does not match provenance: {relative}",
                    relative,
                )

        version: str | None = None
        if source_valid and _mapping(source):
            candidate = source.get("catalog_version")
            version = candidate if isinstance(candidate, str) else None
        return CheckReport(
            findings=tuple(
                sorted(findings, key=lambda item: (item.path, item.code, item.message))
            ),
            profiles=(),
            version=version,
        )

    def _delivery_hashes(
        self,
        snapshot: ComposedSnapshot,
        findings: list[Finding],
        *,
        authored: dict[str, str],
    ) -> tuple[dict[str, str], set[str]]:
        """Permit exact first-party native entries, not arbitrary runtime trees."""
        lock = next(
            (item for item in snapshot.files if item.relative_path == "apm.lock.yaml"),
            None,
        )
        if lock is None:
            return {}, set()
        value = lock.yaml_value
        if not _mapping(value) or value.get("lockfile_version") != "1":
            self._add(
                findings,
                "provenance.delivery",
                "APM ledger is invalid",
                "apm.lock.yaml",
            )
            return {}, set()
        deployments = value.get("deployments")
        if not isinstance(deployments, list):
            self._add(
                findings,
                "provenance.delivery",
                "APM deployments must be a list",
                "apm.lock.yaml",
            )
            return {}, set()
        hashes: dict[str, str] = {}
        roots = (
            ".agents/skills/",
            ".claude/skills/",
            ".claude/rules/",
            ".github/instructions/",
        )
        for item in deployments:
            if not _mapping(item):
                self._add(
                    findings,
                    "provenance.delivery",
                    "APM entry is invalid",
                    "apm.lock.yaml",
                )
                continue
            relative = item.get("value")
            digest = item.get("content_hash")
            if digest is None:
                continue
            prompt_source = (
                _prompt_source(relative) if isinstance(relative, str) else None
            )
            if (
                item.get("kind") != "project-relative"
                or item.get("scope") != "project"
                or item.get("owners") != ["."]
                or item.get("active_owner") != "."
                or not isinstance(relative, str)
                or not _path_is_relative(relative)
                or not (
                    relative.startswith(roots)
                    or (prompt_source is not None and prompt_source in authored)
                )
                or not isinstance(digest, str)
                or not digest.startswith("sha256:")
                or _HASH.fullmatch(digest.removeprefix("sha256:")) is None
            ):
                self._add(
                    findings,
                    "provenance.delivery",
                    "APM entry is not an approved first-party delivery",
                    "apm.lock.yaml",
                )
                continue
            hashes[relative] = digest.removeprefix("sha256:")
        # These are post-installation metadata, not authored source bytes.
        # Review compiled context separately; APM audits its owned delivery.
        return hashes, {"apm.lock.yaml", ".gitignore", "AGENTS.md", "CLAUDE.md"}

    def _validate_source(self, value: object, findings: list[Finding]) -> bool:
        """Require relative source provenance with explicit bundle ownership."""
        if not _mapping(value) or set(value) != {
            "catalog_version",
            "profile",
            "bundles",
        }:
            self._add(
                findings,
                "provenance.source",
                "provenance source metadata has missing or unknown fields",
                "provenance.json",
            )
            return False
        version = value.get("catalog_version")
        profile = value.get("profile")
        bundles = value.get("bundles")
        valid = (
            isinstance(version, str)
            and _VERSION.fullmatch(version) is not None
            and isinstance(profile, str)
            and bool(profile)
        )
        if not valid:
            self._add(
                findings,
                "provenance.source",
                "provenance source identity is invalid",
                "provenance.json",
            )
        if not isinstance(bundles, list) or not bundles:
            self._add(
                findings,
                "provenance.source",
                "provenance must list selected source bundles",
                "provenance.json",
            )
            return False
        names: set[str] = set()
        for item in bundles:
            if not _mapping(item) or set(item) != {"name", "path"}:
                self._add(
                    findings,
                    "provenance.source",
                    "provenance bundle identity is invalid",
                    "provenance.json",
                )
                valid = False
                continue
            name = item.get("name")
            path = item.get("path")
            if (
                not isinstance(name, str)
                or not isinstance(path, str)
                or not _path_is_relative(path)
            ):
                self._add(
                    findings,
                    "provenance.source",
                    "provenance bundle identity is invalid",
                    "provenance.json",
                )
                valid = False
                continue
            if name in names:
                self._add(
                    findings,
                    "provenance.source",
                    "provenance contains a duplicate source bundle",
                    "provenance.json",
                )
                valid = False
            names.add(name)
        return valid

    def _add(self, findings: list[Finding], code: str, message: str, path: str) -> None:
        """Append one safe provenance diagnostic."""
        findings.append(Finding(code=code, message=message, path=path))
