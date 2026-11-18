"""Bind installed hook scripts and registrations to authored hook sources."""

from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING, Final

from agent_kit.application.findings import add_finding
from agent_kit.application.provenance.workspace import json_value, selected_targets
from agent_kit.core.executables import hook_issues
from agent_kit.core.guards import is_json_object
from agent_kit.core.primitives import NativeRuntime

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import ComposedSnapshot, Finding, SourceDocument

HOOK_SCRIPT: Final[re.Pattern[str]] = re.compile(
    r"(?:\.github/hooks/scripts|\.claude/hooks)/[^/]+/scripts/([^/]+)"
)
HOOK_REGISTRATION: Final[re.Pattern[str]] = re.compile(r"\.github/hooks/[^/]+\.json")


def check_hook_source(native_actual: dict[str, str], findings: list[Finding]) -> None:
    """Bind installed hook scripts to source, even if a ledger hash is rewritten.

    Args:
        native_actual (dict[str, str]): Observed native digest keyed by relative path.
        findings (list[Finding]): Collector extended in place.
    """
    for relative, digest in native_actual.items():
        match = HOOK_SCRIPT.fullmatch(relative)
        if match is not None and digest != native_actual.get(
            f".apm/hooks/scripts/{match.group(1)}"
        ):
            add_finding(
                findings,
                "provenance.hook-source",
                "installed hook script differs from its authored source",
                relative,
            )


def hook_authored(relative: str, authored: dict[str, str]) -> bool:
    """Tie a delivered hook script or registration to authored hook source.

    Args:
        relative (str): Delivered relative path.
        authored (dict[str, str]): Recorded digest keyed by authored relative path.

    Returns:
        bool: Whether the path is a hook script or registration with a source.
    """
    script = HOOK_SCRIPT.fullmatch(relative)
    if script is not None:
        return f".apm/hooks/scripts/{script.group(1)}" in authored
    if HOOK_REGISTRATION.fullmatch(relative) is None:
        return False
    return any(
        path.startswith(".apm/hooks/")
        and path.endswith(".json")
        and PurePosixPath(path).parent == PurePosixPath(".apm/hooks")
        and relative.endswith(f"-{PurePosixPath(path).name}")
        for path in authored
    )


def _hook_projections(
    document: SourceDocument, package: str
) -> tuple[JSONObject, list[JSONObject]]:
    """Project the closed hook schema into the two pinned APM native formats.

    Args:
        document (SourceDocument): Authored, already validated hook registration.
        package (str): Package name embedded in native script paths.

    Returns:
        tuple[JSONObject, list[JSONObject]]: The Copilot registration document,
        then the Claude ``PreToolUse`` handler entries, both in source order.
    """
    data = json_value(document)
    hooks = data.get("hooks") if is_json_object(data) else None
    entries = hooks.get("preToolUse") if is_json_object(hooks) else None
    copilot: list[JSONObject] = []
    claude: list[JSONObject] = []
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
    documents: dict[str, SourceDocument],
    package: str | None,
    findings: list[Finding],
) -> tuple[JSONObject, list[JSONObject]]:
    """Build expected registrations only from validated, authored hook sources.

    Args:
        documents (dict[str, SourceDocument]): Captured files keyed by relative path.
        package (str | None): Package name embedded in native script paths, or
            ``None`` when ``apm.yml`` names no package; each hook is then a finding.
        findings (list[Finding]): Collector extended in place.

    Returns:
        tuple[JSONObject, list[JSONObject]]: Expected Copilot registration documents
        keyed by relative path, then the Claude handler entries in source order.
    """
    copilot: JSONObject = {}
    claude: list[JSONObject] = []
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
            add_finding(findings, "provenance.hooks", "authored hook is invalid", path)
            continue
        if package is None:
            add_finding(
                findings, "provenance.hooks", "hook needs a named apm.yml package", path
            )
            continue
        native, handlers = _hook_projections(document, package)
        copilot[f".github/hooks/{package}-{PurePosixPath(path).name}"] = native
        claude.extend(handlers)
    return copilot, claude


def check_hook_configuration(
    snapshot: ComposedSnapshot, findings: list[Finding]
) -> None:
    """Bind effective hook events, commands and disabling settings to source."""
    documents = {item.relative_path: item for item in snapshot.files}
    if "apm.lock.yaml" not in documents:
        return
    manifest = documents.get("apm.yml")
    value = manifest.yaml_value if manifest is not None else None
    name = value.get("name") if is_json_object(value) else None
    package = name if isinstance(name, str) and name else None
    selected = selected_targets(value)
    copilot, claude = _expected_hooks(documents, package, findings)
    for relative, expected in copilot.items():
        if (NativeRuntime.COPILOT in selected or relative in documents) and json_value(
            documents.get(relative)
        ) != expected:
            add_finding(
                findings,
                "provenance.hooks",
                "hook registration differs from source",
                relative,
            )
    _check_claude_hooks(documents, claude, package, selected, findings)


def _check_claude_hooks(
    documents: dict[str, SourceDocument],
    handlers: list[JSONObject],
    package: str | None,
    targets: list[object],
    findings: list[Finding],
) -> None:
    """Check both effective Claude settings and APM's hook ownership receipt.

    Args:
        documents (dict[str, SourceDocument]): Captured files keyed by relative path.
        handlers (list[JSONObject]): Expected Claude ``PreToolUse`` handler entries;
            empty whenever ``package`` is ``None``.
        package (str | None): Package name recorded as the local ownership source.
        targets (list[object]): Runtime targets selected by the manifest.
        findings (list[Finding]): Collector extended in place.
    """
    relative = ".claude/settings.json"
    settings = json_value(documents.get(relative))
    expected: JSONObject = {"PreToolUse": handlers} if handlers else {}
    required = NativeRuntime.CLAUDE in targets and bool(handlers)
    if required or relative in documents:
        actual = settings.get("hooks", {}) if is_json_object(settings) else None
        disabled = is_json_object(settings) and (
            settings.get("disableAllHooks") is True
            or settings.get("allowManagedHooksOnly") is True
        )
        if actual != expected or disabled:
            add_finding(
                findings,
                "provenance.hooks",
                "effective Claude hooks differ from source",
                relative,
            )
    receipt = ".claude/apm-hooks.json"
    if receipt in documents:
        owned = [{**entry, "_apm_source": f"_local/{package}"} for entry in handlers]
        if json_value(documents[receipt]) != ({"PreToolUse": owned} if owned else {}):
            add_finding(
                findings,
                "provenance.hooks",
                "Claude hook ownership receipt differs from source",
                receipt,
            )
