"""Project authored MCP declarations and compare installed MCP configuration."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from agent_kit.application.findings import add_finding
from agent_kit.application.provenance.hashes import DIGEST_PREFIX
from agent_kit.application.provenance.workspace import json_value, selected_targets
from agent_kit.core.guards import is_json_object
from agent_kit.core.primitives import NativeRuntime

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import ComposedSnapshot, Finding


def _mcp_projection(entries: object, *, copilot: bool) -> JSONObject:
    """Project validated server declarations into APM's native configuration shape.

    Args:
        entries (object): Decoded ``dependencies.mcp`` value.
        copilot (bool): Whether to emit the Copilot shape, with local type and tools.

    Returns:
        JSONObject: Native server definition keyed by server name; empty when
        ``entries`` is not a list. Entries without a string name are skipped.
    """
    result: JSONObject = {}
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


def mcp_configurations(snapshot: ComposedSnapshot) -> dict[str, JSONObject]:
    """Project authored MCP declarations only for explicitly selected runtimes."""
    manifest = next(
        (item for item in snapshot.files if item.relative_path == "apm.yml"), None
    )
    value = manifest.yaml_value if manifest is not None else None
    dependencies = value.get("dependencies") if is_json_object(value) else None
    entries = dependencies.get("mcp") if is_json_object(dependencies) else None
    selected = selected_targets(value)
    return {
        runtime: _mcp_projection(entries, copilot=runtime is NativeRuntime.COPILOT)
        for runtime in NativeRuntime
        if runtime in selected
    }


def mcp_fingerprints(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> dict[tuple[str, str], str]:
    """Bind MCP URI hashes to canonical JSON of the authored native projection."""
    fingerprints: dict[tuple[str, str], str] = {}
    for runtime, servers in mcp_configurations(snapshot).items():
        for name, server in servers.items():
            try:
                encoded = json.dumps(
                    server, sort_keys=True, separators=(",", ":"), allow_nan=False
                )
            except (TypeError, ValueError, RecursionError):
                add_finding(
                    findings,
                    "provenance.mcp",
                    f"authored MCP configuration for {runtime} is not valid JSON",
                    "apm.yml",
                )
                continue
            fingerprints[runtime, name] = (
                DIGEST_PREFIX + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            )
    return fingerprints


def check_mcp_configuration(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> None:
    """Require installed MCP definitions to match the authored package manifest."""
    documents = {item.relative_path: item for item in snapshot.files}
    if "apm.lock.yaml" not in documents:
        return
    configurations = mcp_configurations(snapshot)
    for relative, target in (
        (".mcp.json", NativeRuntime.CLAUDE),
        (".github/mcp.json", NativeRuntime.COPILOT),
    ):
        expected = configurations.get(target, {})
        document = documents.get(relative)
        if document is None and not expected:
            continue
        actual = json_value(document)
        servers = actual.get("mcpServers", {}) if is_json_object(actual) else None
        if servers != expected or (
            is_json_object(actual) and set(actual) - {"mcpServers"}
        ):
            add_finding(
                findings,
                "provenance.mcp",
                "installed MCP configuration differs from the authored manifest",
                relative,
            )
