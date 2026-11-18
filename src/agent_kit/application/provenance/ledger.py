"""Approve first-party native deliveries recorded in the APM ledger."""

from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING

from agent_kit.application.findings import add_finding
from agent_kit.application.provenance.hashes import DIGEST_PREFIX, SHA256_HEX
from agent_kit.application.provenance.hooks import hook_authored
from agent_kit.application.provenance.mcp import mcp_fingerprints
from agent_kit.core.guards import is_json_object
from agent_kit.core.paths import is_relative_file_path
from agent_kit.core.primitives import PROMPT_SUFFIX, NativeRuntime

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import ComposedSnapshot, Finding

# APM lock entries owned by the consumer project use this scope and owner path.
_PROJECT_SCOPE = "project"
_ROOT_OWNER = "."
_NATIVE_PROMPT_SUFFIXES = {
    PurePosixPath(runtime.prompt_directory): runtime.prompt_suffix
    for runtime in NativeRuntime
}
_DELIVERY_ROOTS = (
    ".agents/skills/",
    ".claude/skills/",
    ".claude/rules/",
    ".github/instructions/",
)
_POST_INSTALL_METADATA = frozenset(
    {
        "apm.lock.yaml",
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        ".mcp.json",
        ".github/mcp.json",
        ".claude/settings.json",
        ".claude/apm-hooks.json",
    }
)
_LOCAL_INSTALLATION = ".apm-local/installation"
_LOCAL_INSTALLATION_IGNORE = ".apm-local/.gitignore"
_LOCAL_INSTALLATION_ID = re.compile(rb"[0-9a-f]{32}\n\Z")


def _local_installation_metadata(snapshot: ComposedSnapshot) -> set[str]:
    """Permit only the pinned APM writer's paired local identity files.

    The marker is incidental metadata, never evidence of ownership. Invalid
    content remains unpermitted and is reported by the recorded-file check.
    """
    documents = {item.relative_path: item for item in snapshot.files}
    identity = documents.get(_LOCAL_INSTALLATION)
    ignore = documents.get(_LOCAL_INSTALLATION_IGNORE)
    if (
        identity is None
        or ignore is None
        or ignore.content != b"*\n"
        or not _LOCAL_INSTALLATION_ID.fullmatch(identity.content)
    ):
        return set()
    return {_LOCAL_INSTALLATION, _LOCAL_INSTALLATION_IGNORE}


def _prompt_source(relative: str) -> str | None:
    """Map flat native prompt projections back to their authored facade."""
    path = PurePosixPath(relative)
    suffix = _NATIVE_PROMPT_SUFFIXES.get(path.parent)
    if suffix is None or not path.name.endswith(suffix):
        return None
    return f".apm/prompts/{path.name.removesuffix(suffix)}{PROMPT_SUFFIX}"


def _project_owned(item: JSONObject) -> bool:
    """Recognize an APM lock entry owned and activated by the project root."""
    return (
        item.get("scope") == _PROJECT_SCOPE
        and item.get("owners") == [_ROOT_OWNER]
        and item.get("active_owner") == _ROOT_OWNER
    )


def _mcp_delivery_matches(
    item: object, fingerprints: dict[tuple[str, str], str]
) -> bool:
    """Recognize only source-bound, project-owned MCP configuration fingerprints."""
    if not is_json_object(item):
        return False
    runtime, name = item.get("runtime"), item.get("value")
    return (
        item.get("kind") == "uri"
        and item.get("target") == "mcp"
        and _project_owned(item)
        and isinstance(runtime, str)
        and isinstance(name, str)
        and (runtime, name) in fingerprints
        and item.get("content_hash") == fingerprints[runtime, name]
    )


def _ledger_deployments(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> list[object] | None:
    """Return APM ledger deployments, or ``None`` when absent or invalid.

    Returns:
        list[object] | None: Decoded ``deployments`` list in ledger order, or
        ``None`` without a finding when there is no ledger and with one when the
        ledger is malformed.
    """
    lock = next(
        (item for item in snapshot.files if item.relative_path == "apm.lock.yaml"),
        None,
    )
    if lock is None:
        return None
    value = lock.yaml_value
    if not is_json_object(value) or value.get("lockfile_version") != "1":
        add_finding(
            findings, "provenance.delivery", "APM ledger is invalid", "apm.lock.yaml"
        )
        return None
    deployments = value.get("deployments")
    if not isinstance(deployments, list):
        add_finding(
            findings,
            "provenance.delivery",
            "APM deployments must be a list",
            "apm.lock.yaml",
        )
        return None
    return deployments


def _approved_delivery(
    item: JSONObject, relative: str, digest: str, authored: dict[str, str]
) -> bool:
    """Accept only project-owned first-party deliveries with SHA-256 digests.

    Args:
        item (JSONObject): Decoded ledger deployment entry.
        relative (str): Delivered relative path.
        digest (str): Ledger digest, expected as ``sha256:`` plus 64 hex digits.
        authored (dict[str, str]): Recorded digest keyed by authored relative path.

    Returns:
        bool: Whether the entry is an approved delivery.
    """
    prompt_source = _prompt_source(relative)
    return (
        item.get("kind") == "project-relative"
        and _project_owned(item)
        and is_relative_file_path(relative)
        and (
            relative.startswith(_DELIVERY_ROOTS)
            or (prompt_source is not None and prompt_source in authored)
            or hook_authored(relative, authored)
        )
        and digest.startswith(DIGEST_PREFIX)
        and SHA256_HEX.fullmatch(digest.removeprefix(DIGEST_PREFIX)) is not None
    )


def _delivery_entry(
    item: object, authored: dict[str, str], findings: list[Finding]
) -> tuple[str, str] | None:
    """Return one approved ledger path and digest, reporting rejected entries.

    Args:
        item (object): Decoded ledger deployment entry.
        authored (dict[str, str]): Recorded digest keyed by authored relative path.
        findings (list[Finding]): Collector extended in place.

    Returns:
        tuple[str, str] | None: Relative path and bare hex digest, or ``None`` for
        an entry without a content hash or one that is rejected with a finding.
    """
    if not is_json_object(item):
        add_finding(
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
        add_finding(
            findings,
            "provenance.delivery",
            "APM entry is not an approved first-party delivery",
            "apm.lock.yaml",
        )
        return None
    return relative, digest.removeprefix(DIGEST_PREFIX)


def delivery_hashes(
    snapshot: ComposedSnapshot,
    findings: list[Finding],
    *,
    authored: dict[str, str],
) -> tuple[dict[str, str], set[str]]:
    """Permit exact first-party native entries, not arbitrary runtime trees.

    Args:
        snapshot (ComposedSnapshot): Captured composed workspace.
        findings (list[Finding]): Collector extended in place.
        authored (dict[str, str]): Recorded digest keyed by authored relative path.

    Returns:
        tuple[dict[str, str], set[str]]: Approved ledger digests keyed by
        relative path, then the post-installation metadata paths permitted
        without a record. Both are empty when no ledger exists or it is invalid
        (the metadata set is empty only in that case).
    """
    deployments = _ledger_deployments(snapshot, findings)
    if deployments is None:
        return {}, set()
    hashes: dict[str, str] = {}
    fingerprints = mcp_fingerprints(snapshot, findings)
    for item in deployments:
        # URI rows fingerprint configuration entries, not filesystem paths.
        if _mcp_delivery_matches(item, fingerprints):
            continue
        entry = _delivery_entry(item, authored, findings)
        if entry is not None:
            relative, digest = entry
            hashes[relative] = digest
    # These are post-installation metadata, not authored source bytes.
    # Review compiled context separately; APM audits its owned delivery.
    return hashes, set(_POST_INSTALL_METADATA) | _local_installation_metadata(snapshot)
