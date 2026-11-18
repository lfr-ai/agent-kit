"""Own the ``provenance.json`` schema shared by the composer and the verifier.

The composer builds the record with ``provenance_record``; the verifier checks a
captured record against the same file name, version, and field names.
"""

from __future__ import annotations

import hashlib
from posixpath import curdir
from typing import TYPE_CHECKING, Final

from agent_kit.application.findings import add_finding
from agent_kit.core.guards import is_int, is_json_object, is_semantic_version
from agent_kit.core.paths import is_relative_file_path

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import Catalog, ComposedSnapshot, Finding

PROVENANCE_FILE: Final[str] = "provenance.json"
PROVENANCE_SCHEMA_VERSION: Final[int] = 1
PROVENANCE_FIELDS: Final[frozenset[str]] = frozenset(
    {"schema_version", "source", "files"}
)
SOURCE_FIELDS: Final[frozenset[str]] = frozenset(
    {"catalog_version", "profile", "bundles"}
)
_BUNDLE_FIELDS = frozenset({"name", "path"})


def provenance_record(
    catalog: Catalog,
    profile: str,
    selected: tuple[str, ...],
    files: dict[str, bytes],
) -> JSONObject:
    """Record source bundles and content hashes for every planned file.

    Returns:
        JSONObject: ``schema_version``, a ``source`` object (catalog version,
        profile, and bundle names with paths), and ``files`` mapping each output
        path to its hex SHA-256 digest in sorted order.
    """
    bundle_paths = {item.name: item.path for item in catalog.bundles}
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
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


def provenance_mapping(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> JSONObject | None:
    """Return a readable provenance object with exactly the expected fields.

    Returns:
        JSONObject | None: The decoded provenance document, or ``None`` after a
        finding when it is unreadable or has missing or unknown fields.
    """
    if snapshot.provenance_error or snapshot.provenance is None:
        add_finding(
            findings,
            "provenance.read",
            f"{PROVENANCE_FILE} is missing or invalid",
            PROVENANCE_FILE,
        )
        return None
    provenance = snapshot.provenance
    if not is_json_object(provenance) or set(provenance) != PROVENANCE_FIELDS:
        add_finding(
            findings,
            "provenance.schema",
            "provenance schema has missing or unknown fields",
            PROVENANCE_FILE,
        )
        return None
    return provenance


def check_schema_version(provenance: JSONObject, findings: list[Finding]) -> None:
    """Require the integer provenance schema version."""
    schema_version = provenance.get("schema_version")
    if not is_int(schema_version) or schema_version != PROVENANCE_SCHEMA_VERSION:
        add_finding(
            findings,
            "provenance.schema",
            f"provenance schema_version must be {PROVENANCE_SCHEMA_VERSION}",
            PROVENANCE_FILE,
        )


def source_version(source: object, *, source_valid: bool) -> str | None:
    """Return the recorded catalog version of valid source metadata.

    Args:
        source (object): Decoded ``source`` value.
        source_valid (bool): Whether the source metadata passed validation.

    Returns:
        str | None: The ``catalog_version`` string, or ``None`` when the source is
        invalid or lacks a string version.
    """
    if not source_valid or not is_json_object(source):
        return None
    candidate = source.get("catalog_version")
    return candidate if isinstance(candidate, str) else None


def _bundle_name(item: object) -> str | None:
    """Return the name of a well-formed, contained source bundle identity."""
    if not is_json_object(item) or set(item) != _BUNDLE_FIELDS:
        return None
    name = item.get("name")
    path = item.get("path")
    if (
        not isinstance(name, str)
        or not isinstance(path, str)
        or not (path == curdir or is_relative_file_path(path))
    ):
        return None
    return name


def _source_identity_valid(source: JSONObject, findings: list[Finding]) -> bool:
    """Require a semantic catalog version and a non-empty profile name.

    Args:
        source (JSONObject): Decoded ``source`` object.
        findings (list[Finding]): Collector extended in place.

    Returns:
        bool: Whether the identity is valid.
    """
    version = source.get("catalog_version")
    profile = source.get("profile")
    named_profile = isinstance(profile, str) and bool(profile)
    valid = is_semantic_version(version) and named_profile
    if not valid:
        add_finding(
            findings,
            "provenance.source",
            "provenance source identity is invalid",
            PROVENANCE_FILE,
        )
    return valid


def _source_bundles_valid(bundles: list[object], findings: list[Finding]) -> bool:
    """Require well-formed, uniquely named source bundle identities.

    Args:
        bundles (list[object]): Decoded bundle identity entries.
        findings (list[Finding]): Collector extended in place.

    Returns:
        bool: Whether every identity is well formed and no name repeats.
    """
    valid = True
    names: set[str] = set()
    for item in bundles:
        name = _bundle_name(item)
        if name is None:
            add_finding(
                findings,
                "provenance.source",
                "provenance bundle identity is invalid",
                PROVENANCE_FILE,
            )
            valid = False
            continue
        if name in names:
            add_finding(
                findings,
                "provenance.source",
                "provenance contains a duplicate source bundle",
                PROVENANCE_FILE,
            )
            valid = False
        names.add(name)
    return valid


def validate_source(value: object, findings: list[Finding]) -> bool:
    """Require relative source provenance with explicit bundle ownership.

    Args:
        value (object): Decoded ``source`` value.
        findings (list[Finding]): Collector extended in place.

    Returns:
        bool: Whether the identity and every bundle are valid.
    """
    if not is_json_object(value) or set(value) != SOURCE_FIELDS:
        add_finding(
            findings,
            "provenance.source",
            "provenance source metadata has missing or unknown fields",
            PROVENANCE_FILE,
        )
        return False
    identity_valid = _source_identity_valid(value, findings)
    bundles = value.get("bundles")
    if not isinstance(bundles, list) or not bundles:
        add_finding(
            findings,
            "provenance.source",
            "provenance must list selected source bundles",
            PROVENANCE_FILE,
        )
        return False
    return _source_bundles_valid(bundles, findings) and identity_valid
