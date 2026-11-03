"""Verify composed output hashes without relying on source checkout state."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import TypeGuard

from agent_kit.core.executables import hook_issues
from agent_kit.core.guards import JsonObject, is_int, is_json_object
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
_HOOK_SCRIPT = re.compile(
    r"(?:\.github/hooks/scripts|\.claude/hooks)/[^/]+/scripts/([^/]+)"
)
_HOOK_REGISTRATION = re.compile(r"\.github/hooks/[^/]+\.json")


def _selected_targets(manifest: object) -> list[object]:
    """Return the ``targets`` list of a decoded manifest, or empty when absent."""
    targets = manifest.get("targets") if is_json_object(manifest) else None
    return targets if isinstance(targets, list) else []


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
    """Append one safe provenance diagnostic.

    Args:
        findings (list[Finding]): Collector extended in place.
        code (str): Stable finding code.
        message (str): Safe, value-free description.
        path (str): Source- or output-relative location.
    """
    findings.append(Finding(code=code, message=message, path=path))


def _check_composed_links(snapshot: ComposedSnapshot, findings: list[Finding]) -> None:
    """Report a symlinked composed root or provenance file.

    Args:
        snapshot (ComposedSnapshot): Captured composed workspace.
        findings (list[Finding]): Collector extended in place.
    """
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
) -> JsonObject | None:
    """Return a readable provenance object with exactly the expected fields.

    Args:
        snapshot (ComposedSnapshot): Captured composed workspace.
        findings (list[Finding]): Collector extended in place.

    Returns:
        JsonObject | None: The decoded provenance document, or ``None`` after a
        finding when it is unreadable or has missing or unknown fields.
    """
    if snapshot.provenance_error or snapshot.provenance is None:
        _finding(
            findings,
            "provenance.read",
            "provenance.json is missing or invalid",
            "provenance.json",
        )
        return None
    provenance = snapshot.provenance
    if not is_json_object(provenance) or set(provenance) != _PROVENANCE_FIELDS:
        _finding(
            findings,
            "provenance.schema",
            "provenance schema has missing or unknown fields",
            "provenance.json",
        )
        return None
    return provenance


def _check_schema_version(provenance: JsonObject, findings: list[Finding]) -> None:
    """Require the integer provenance schema version 1.

    Args:
        provenance (JsonObject): Decoded provenance document.
        findings (list[Finding]): Collector extended in place.
    """
    schema_version = provenance.get("schema_version")
    if not is_int(schema_version) or schema_version != 1:
        _finding(
            findings,
            "provenance.schema",
            "provenance schema_version must be 1",
            "provenance.json",
        )


def _valid_file_hash(digest: object, relative: str) -> TypeGuard[str]:
    """Accept a contained, non-ledger path with a lowercase SHA-256 digest.

    Args:
        digest (object): Recorded digest value.
        relative (str): Recorded relative path.

    Returns:
        bool: Whether both are acceptable; narrows ``digest`` to ``str``.
    """
    return (
        _path_is_relative(relative)
        and relative != "provenance.json"
        and isinstance(digest, str)
        and _HASH.fullmatch(digest) is not None
    )


def _expected_hashes(expected: JsonObject, findings: list[Finding]) -> dict[str, str]:
    """Return valid recorded hashes and report invalid or missing entries.

    Args:
        expected (JsonObject): Decoded ``files`` object mapping path to digest.
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
    """Hash captured bytes, not unreadable placeholders or parsed YAML values.

    Args:
        snapshot (ComposedSnapshot): Captured composed workspace.
        findings (list[Finding]): Collector extended in place.

    Returns:
        tuple[dict[str, str], dict[str, str]]: Two SHA-256 hex digest maps keyed
        by relative path: exact byte digests, then native digests with normalized
        line endings. Links, directories, and unreadable files are excluded.
    """
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
    """Report native files whose bytes differ from the APM ledger.

    Args:
        delivery (dict[str, str]): Ledger digest keyed by relative path.
        native_actual (dict[str, str]): Observed native digest keyed by relative path.
        findings (list[Finding]): Collector extended in place.
    """
    for relative, digest in delivery.items():
        if native_actual.get(relative) != digest:
            _finding(
                findings,
                "provenance.delivery-drift",
                f"native file does not match its APM ledger: {relative}",
                relative,
            )


def _check_hook_source(native_actual: dict[str, str], findings: list[Finding]) -> None:
    """Bind installed hook scripts to source, even if a ledger hash is rewritten.

    Args:
        native_actual (dict[str, str]): Observed native digest keyed by relative path.
        findings (list[Finding]): Collector extended in place.
    """
    for relative, digest in native_actual.items():
        match = _HOOK_SCRIPT.fullmatch(relative)
        if match is not None and digest != native_actual.get(
            f".apm/hooks/scripts/{match.group(1)}"
        ):
            _finding(
                findings,
                "provenance.hook-source",
                "installed hook script differs from its authored source",
                relative,
            )


def _json_value(document: SourceDocument | None) -> object:
    """Decode captured JSON; return ``None`` for absent or invalid configuration."""
    try:
        return json.loads(document.text or "") if document is not None else None
    except ValueError:
        return None


def _hook_projections(
    document: SourceDocument, package: str
) -> tuple[JsonObject, list[JsonObject]]:
    """Project the closed hook schema into the two pinned APM native formats.

    Args:
        document (SourceDocument): Authored, already validated hook registration.
        package (str): Package name embedded in native script paths.

    Returns:
        tuple[JsonObject, list[JsonObject]]: The Copilot registration document,
        then the Claude ``PreToolUse`` handler entries, both in source order.
    """
    data = _json_value(document)
    hooks = data.get("hooks") if is_json_object(data) else None
    entries = hooks.get("preToolUse") if is_json_object(hooks) else None
    copilot: list[JsonObject] = []
    claude: list[JsonObject] = []
    for entry in entries if isinstance(entries, list) else []:
        if not is_json_object(entry):
            continue
        script = str(entry["bash"]).removeprefix("python3 ./")
        base = f".claude/hooks/{package}/{script}"
        copilot.append(
            {
                **entry,
                "bash": f"python3 .github/hooks/scripts/{package}/{script}",
                "powershell": f"python .github/hooks/scripts/{package}/{script}",
            }
        )
        claude.append(
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": f'python3 "${{CLAUDE_PROJECT_DIR}}/{base}"',
                        "powershell": f"python $env:CLAUDE_PROJECT_DIR/{base}",
                        "timeout": entry["timeoutSec"],
                    }
                ],
            }
        )
    return {"version": 1, "hooks": {"preToolUse": copilot}}, claude


def _expected_hooks(
    documents: dict[str, SourceDocument], package: str, findings: list[Finding]
) -> tuple[JsonObject, list[JsonObject]]:
    """Build expected registrations only from validated, authored hook sources.

    Args:
        documents (dict[str, SourceDocument]): Captured files keyed by relative path.
        package (str): Package name embedded in native script paths.
        findings (list[Finding]): Collector extended in place.

    Returns:
        tuple[JsonObject, list[JsonObject]]: Expected Copilot registration documents
        keyed by relative path, then the Claude handler entries in source order.
    """
    copilot: JsonObject = {}
    claude: list[JsonObject] = []
    scripts = {
        PurePosixPath(path).name
        for path in documents
        if path.startswith(".apm/hooks/scripts/")
    }
    for path, document in sorted(documents.items()):
        if (
            document.is_directory
            or PurePosixPath(path).suffix != ".json"
            or PurePosixPath(path).parent != PurePosixPath(".apm/hooks")
        ):
            continue
        if hook_issues(document.text or "", scripts):
            _finding(findings, "provenance.hooks", "authored hook is invalid", path)
            continue
        native, handlers = _hook_projections(document, package)
        copilot[f".github/hooks/{package}-{PurePosixPath(path).name}"] = native
        claude.extend(handlers)
    return copilot, claude


def _check_hook_configuration(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> None:
    """Bind effective hook events, commands and disabling settings to source.

    Args:
        snapshot (ComposedSnapshot): Captured composed workspace.
        findings (list[Finding]): Collector extended in place.
    """
    documents = {item.relative_path: item for item in snapshot.files}
    if "apm.lock.yaml" not in documents:
        return
    manifest = documents.get("apm.yml")
    value = manifest.yaml_value if manifest is not None else None
    package = str(value.get("name", "")) if is_json_object(value) else ""
    selected = _selected_targets(value)
    copilot, claude = _expected_hooks(documents, package, findings)
    for relative, expected in copilot.items():
        if ("copilot" in selected or relative in documents) and _json_value(
            documents.get(relative)
        ) != expected:
            _finding(
                findings,
                "provenance.hooks",
                "hook registration differs from source",
                relative,
            )
    _check_claude_hooks(documents, claude, package, selected, findings)


def _check_claude_hooks(
    documents: dict[str, SourceDocument],
    handlers: list[JsonObject],
    package: str,
    targets: list[object],
    findings: list[Finding],
) -> None:
    """Check both effective Claude settings and APM's hook ownership receipt.

    Args:
        documents (dict[str, SourceDocument]): Captured files keyed by relative path.
        handlers (list[JsonObject]): Expected Claude ``PreToolUse`` handler entries.
        package (str): Package name recorded as the local ownership source.
        targets (list[object]): Runtime targets selected by the manifest.
        findings (list[Finding]): Collector extended in place.
    """
    relative = ".claude/settings.json"
    settings = _json_value(documents.get(relative))
    expected: JsonObject = {"PreToolUse": handlers} if handlers else {}
    required = "claude" in targets and bool(handlers)
    if required or relative in documents:
        actual = settings.get("hooks", {}) if is_json_object(settings) else None
        disabled = is_json_object(settings) and (
            settings.get("disableAllHooks") is True
            or settings.get("allowManagedHooksOnly") is True
        )
        if actual != expected or disabled:
            _finding(
                findings,
                "provenance.hooks",
                "effective Claude hooks differ from source",
                relative,
            )
    receipt = ".claude/apm-hooks.json"
    if receipt in documents:
        owned = [{**entry, "_apm_source": f"_local/{package}"} for entry in handlers]
        if _json_value(documents[receipt]) != ({"PreToolUse": owned} if owned else {}):
            _finding(
                findings,
                "provenance.hooks",
                "Claude hook ownership receipt differs from source",
                receipt,
            )


def _mcp_projection(entries: object, *, copilot: bool) -> JsonObject:
    """Project validated server declarations into APM's native configuration shape.

    Args:
        entries (object): Decoded ``dependencies.mcp`` value.
        copilot (bool): Whether to emit the Copilot shape, with local type and tools.

    Returns:
        JsonObject: Native server definition keyed by server name; empty when
        ``entries`` is not a list. Entries without a string name are skipped.
    """
    result: JsonObject = {}
    if not isinstance(entries, list):
        return result
    for entry in entries:
        if not is_json_object(entry) or not isinstance(entry.get("name"), str):
            continue
        server = {
            key: value
            for key, value in entry.items()
            if key not in {"name", "registry", "transport"}
        }
        transport = entry.get("transport")
        server["type"] = "local" if copilot and transport == "stdio" else transport
        if copilot:
            server.update({"tools": ["*"], "id": ""})
        result[str(entry["name"])] = server
    return result


def _check_mcp_configuration(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> None:
    """Require installed MCP definitions to match the authored package manifest.

    Args:
        snapshot (ComposedSnapshot): Captured composed workspace.
        findings (list[Finding]): Collector extended in place.
    """
    documents = {item.relative_path: item for item in snapshot.files}
    if "apm.lock.yaml" not in documents:
        return
    manifest = documents.get("apm.yml")
    value = manifest.yaml_value if manifest is not None else None
    dependencies = value.get("dependencies") if is_json_object(value) else None
    entries = dependencies.get("mcp") if is_json_object(dependencies) else None
    selected = _selected_targets(value)
    for relative, target in ((".mcp.json", "claude"), (".github/mcp.json", "copilot")):
        expected = _mcp_projection(entries, copilot=relative.startswith(".github/"))
        document = documents.get(relative)
        if document is None and (not expected or target not in selected):
            continue
        actual = _json_value(document)
        servers = actual.get("mcpServers", {}) if is_json_object(actual) else None
        if servers != expected or (
            is_json_object(actual) and set(actual) - {"mcpServers"}
        ):
            _finding(
                findings,
                "provenance.mcp",
                "installed MCP configuration differs from the authored manifest",
                relative,
            )


def _check_recorded_files(
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


def _ledger_deployments(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> list[object] | None:
    """Return APM ledger deployments, or ``None`` when absent or invalid.

    Args:
        snapshot (ComposedSnapshot): Captured composed workspace.
        findings (list[Finding]): Collector extended in place.

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


def _hook_authored(relative: str, authored: dict[str, str]) -> bool:
    """Tie a delivered hook script or registration to authored hook source.

    Args:
        relative (str): Delivered relative path.
        authored (dict[str, str]): Recorded digest keyed by authored relative path.

    Returns:
        bool: Whether the path is a hook script or registration with a source.
    """
    script = _HOOK_SCRIPT.fullmatch(relative)
    if script is not None:
        return f".apm/hooks/scripts/{script.group(1)}" in authored
    if _HOOK_REGISTRATION.fullmatch(relative) is None:
        return False
    return any(
        path.startswith(".apm/hooks/")
        and path.endswith(".json")
        and PurePosixPath(path).parent == PurePosixPath(".apm/hooks")
        and relative.endswith(f"-{PurePosixPath(path).name}")
        for path in authored
    )


def _approved_delivery(
    item: JsonObject, relative: str, digest: str, authored: dict[str, str]
) -> bool:
    """Accept only project-owned first-party deliveries with SHA-256 digests.

    Args:
        item (JsonObject): Decoded ledger deployment entry.
        relative (str): Delivered relative path.
        digest (str): Ledger digest, expected as ``sha256:`` plus 64 hex digits.
        authored (dict[str, str]): Recorded digest keyed by authored relative path.

    Returns:
        bool: Whether the entry is an approved delivery.
    """
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
            or _hook_authored(relative, authored)
        )
        and digest.startswith("sha256:")
        and _HASH.fullmatch(digest.removeprefix("sha256:")) is not None
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
    if not is_json_object(item) or set(item) != {"name", "path"}:
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


def _source_identity_valid(source: JsonObject, findings: list[Finding]) -> bool:
    """Require a semantic catalog version and a non-empty profile name.

    Args:
        source (JsonObject): Decoded ``source`` object.
        findings (list[Finding]): Collector extended in place.

    Returns:
        bool: Whether the identity is valid.
    """
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
        if not is_json_object(expected):
            _finding(
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
        _check_hook_source(native_actual, findings)
        _check_hook_configuration(snapshot, findings)
        _check_mcp_configuration(snapshot, findings)
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
        for item in deployments:
            entry = _delivery_entry(item, authored, findings)
            if entry is not None:
                relative, digest = entry
                hashes[relative] = digest
        # These are post-installation metadata, not authored source bytes.
        # Review compiled context separately; APM audits its owned delivery.
        return hashes, set(_POST_INSTALL_METADATA)

    def _validate_source(self, value: object, findings: list[Finding]) -> bool:
        """Require relative source provenance with explicit bundle ownership.

        Args:
            value (object): Decoded ``source`` value.
            findings (list[Finding]): Collector extended in place.

        Returns:
            bool: Whether the identity and every bundle are valid.
        """
        if not is_json_object(value) or set(value) != _SOURCE_FIELDS:
            _finding(
                findings,
                "provenance.source",
                "provenance source metadata has missing or unknown fields",
                "provenance.json",
            )
            return False
        identity_valid = _source_identity_valid(value, findings)
        bundles = value.get("bundles")
        if not isinstance(bundles, list) or not bundles:
            _finding(
                findings,
                "provenance.source",
                "provenance must list selected source bundles",
                "provenance.json",
            )
            return False
        return _source_bundles_valid(bundles, findings) and identity_valid
