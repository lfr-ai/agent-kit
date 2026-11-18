"""Compare recorded, observed, and ledger SHA-256 digests of composed files."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Final, TypeGuard

from agent_kit.application.findings import add_finding
from agent_kit.application.provenance.record import PROVENANCE_FILE
from agent_kit.core.paths import is_relative_file_path
from agent_kit.core.primitives import PACKAGE_REQUIRED_FILES

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import ComposedSnapshot, Finding, SourceDocument

SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}\Z")
DIGEST_PREFIX: Final[str] = "sha256:"


def _valid_file_hash(digest: object, relative: str) -> TypeGuard[str]:
    """Accept a contained, non-ledger path with a lowercase SHA-256 digest.

    Args:
        digest (object): Recorded digest value.
        relative (str): Recorded relative path.

    Returns:
        Whether both are acceptable; narrows ``digest`` to ``str``.
    """
    return (
        is_relative_file_path(relative)
        and relative != PROVENANCE_FILE
        and isinstance(digest, str)
        and SHA256_HEX.fullmatch(digest) is not None
    )


def expected_hashes(expected: JSONObject, findings: list[Finding]) -> dict[str, str]:
    """Return valid recorded hashes and report invalid or missing entries.

    Args:
        expected (JSONObject): Decoded ``files`` object mapping path to digest.
        findings (list[Finding]): Collector extended in place.

    Returns:
        dict[str, str]: Lowercase SHA-256 hex digest keyed by relative path, for
        valid entries only.
    """
    hashes: dict[str, str] = {}
    for relative, digest in expected.items():
        if _valid_file_hash(digest, relative):
            hashes[relative] = digest
        else:
            add_finding(
                findings,
                "provenance.path",
                "provenance contains an invalid relative file hash",
                PROVENANCE_FILE,
            )
    for relative in sorted(PACKAGE_REQUIRED_FILES - set(hashes)):
        add_finding(
            findings,
            "provenance.required",
            f"provenance does not hash required file '{relative}'",
            PROVENANCE_FILE,
        )
    return hashes


def _native_digest(document: SourceDocument) -> str:
    """Hash text with normalized line endings, as native delivery records it."""
    content = document.content
    if document.text is not None and b"\x00" not in content:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def actual_hashes(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> tuple[dict[str, str], dict[str, str]]:
    """Hash captured bytes, not unreadable placeholders or parsed YAML values.

    Returns:
        tuple[dict[str, str], dict[str, str]]: Two SHA-256 hex digest maps keyed
        by relative path: exact byte digests, then native digests with normalized
        line endings. Links, directories, and unreadable files are excluded.
    """
    actual: dict[str, str] = {}
    native_actual: dict[str, str] = {}
    for document in snapshot.files:
        if document.is_symlink:
            add_finding(
                findings,
                "provenance.symlink",
                "composed output contains a symlink",
                document.relative_path,
            )
        elif document.parse_error and document.text is None:
            # Readable malformed YAML has text; failed captures have neither.
            add_finding(
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


def check_delivery_drift(
    delivery: dict[str, str], native_actual: dict[str, str], findings: list[Finding]
) -> None:
    """Report native files whose bytes differ from the APM ledger.

    Args:
        delivery (dict[str, str]): Ledger digest keyed by relative path.
        native_actual (dict[str, str]): Observed native digest keyed by relative path.
        findings (list[Finding]): Collector extended in place.
    """
    for relative, digest in delivery.items():
        if native_actual.get(relative) != digest:
            add_finding(
                findings,
                "provenance.delivery-drift",
                f"native file does not match its APM ledger: {relative}",
                relative,
            )


def check_recorded_files(
    expected: dict[str, str],
    actual: dict[str, str],
    permitted: set[str],
    findings: list[Finding],
) -> None:
    """Report missing, unrecorded, and drifted composed files.

    Args:
        expected (dict[str, str]): Recorded digest keyed by relative path.
        actual (dict[str, str]): Observed digest keyed by relative path.
        permitted (set[str]): Relative paths allowed to exist without a record.
        findings (list[Finding]): Collector extended in place.
    """
    for relative in sorted(expected.keys() - actual.keys()):
        add_finding(
            findings,
            "provenance.missing",
            f"recorded file is missing: {relative}",
            relative,
        )
    for relative in sorted(actual.keys() - permitted):
        add_finding(
            findings,
            "provenance.extra",
            f"unrecorded file exists: {relative}",
            relative,
        )
    for relative in sorted(actual.keys() & expected.keys()):
        if actual[relative] != expected[relative]:
            add_finding(
                findings,
                "provenance.drift",
                f"file hash does not match provenance: {relative}",
                relative,
            )
