"""Hook and MCP delivery through source validation and composition."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from agent_kit.application.services.catalog_service import (
    CatalogService,
    CompositionError,
    CompositionIssue,
)
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_DOCS = {
    "name": "context7",
    "registry": False,
    "transport": "http",
    "url": "https://mcp.context7.com/mcp",
}
_BROWSER = {
    "name": "playwright",
    "registry": False,
    "transport": "stdio",
    "command": "bunx",
    "args": ["--bun", "@playwright/mcp@0.0.80", "--isolated"],
}
_HOOK_ENTRY = {
    "type": "command",
    "bash": "python3 ./scripts/guard.py",
    "powershell": "python ./scripts/guard.py",
    "timeoutSec": 10,
}


def _hook(**entry_changes: object) -> dict[str, object]:
    entry = {**_HOOK_ENTRY, **entry_changes}
    return {"version": 1, "hooks": {"preToolUse": [entry]}}


def _declare(root: Path, bundle: str, *servers: Mapping[str, object]) -> None:
    path = root / f"packages/{bundle}/apm.yml"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["dependencies"] = {"mcp": list(servers)}
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _ship_hook(root: Path, registration: Mapping[str, object] | None = None) -> Path:
    bundle = root / "packages/shared"
    hooks = bundle / ".apm/hooks"
    (hooks / "scripts").mkdir(parents=True)
    content = _hook() if registration is None else registration
    (hooks / "guard.json").write_text(json.dumps(content), encoding="utf-8")
    (hooks / "scripts/guard.py").write_text("print('guard')\n", encoding="utf-8")
    manifest = json.loads((bundle / "apm.yml").read_text(encoding="utf-8"))
    manifest["includes"] = [*manifest["includes"], ".apm/hooks/"]
    (bundle / "apm.yml").write_text(json.dumps(manifest), encoding="utf-8")
    return hooks


def _codes(root: Path) -> set[str]:
    report = CatalogService().validate(FileCatalogAdapter().load(root))
    return {item.code for item in report.findings}


def _compose(root: Path, profile: str, **kwargs: tuple[str, ...]) -> dict[str, object]:
    snapshot = FileCatalogAdapter().load(root)
    plan = CatalogService().compose(snapshot, profile, (), (), **kwargs)
    files = {item.relative_path: item.content for item in plan.files}
    return json.loads(files["apm.yml"])


def _includes(manifest: Mapping[str, object]) -> list[object]:
    includes = manifest["includes"]
    assert isinstance(includes, list)
    return includes


def test_declared_servers_and_hook_validate(source_root: Path) -> None:
    _declare(source_root, "backend", _DOCS)
    _ship_hook(source_root)

    assert _codes(source_root) == set()


@pytest.mark.parametrize(
    "server",
    [
        {**_BROWSER, "args": ["--bun", "@playwright/mcp@latest"]},
        {**_BROWSER, "command": "npx"},
        {**_DOCS, "url": "http://example.com/mcp"},
        {**_DOCS, "name": "unreviewed"},
        {**_DOCS, "registry": True},
    ],
)
def test_unsafe_server_declarations_are_findings(
    source_root: Path, server: dict[str, object]
) -> None:
    _declare(source_root, "backend", server)

    assert "manifest.mcp" in _codes(source_root)


def test_executables_stay_empty(source_root: Path) -> None:
    path = source_root / "packages/backend/apm.yml"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["executables"] = {"allow": {}}
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert "manifest.executables" in _codes(source_root)


def test_hook_may_only_run_a_bundled_script(source_root: Path) -> None:
    _ship_hook(source_root, _hook(bash="python3 ./scripts/missing.py"))

    assert "hooks.registration" in _codes(source_root)


def test_hook_scripts_must_be_python_or_policy(source_root: Path) -> None:
    hooks = _ship_hook(source_root)
    (hooks / "scripts/run.sh").write_text("id\n", encoding="utf-8")

    assert "hooks.script" in _codes(source_root)


def test_hooks_hold_only_registrations_and_scripts(source_root: Path) -> None:
    hooks = _ship_hook(source_root)
    (hooks / "notes.md").write_text("notes\n", encoding="utf-8")

    assert "hooks.layout" in _codes(source_root)


def test_composition_carries_the_hook_and_merges_servers(
    source_root: Path, tmp_path: Path
) -> None:
    _declare(source_root, "backend", _DOCS)
    _declare(source_root, "frontend", _BROWSER, _DOCS)
    _ship_hook(source_root)

    manifest = _compose(source_root, "fullstack")

    assert manifest["dependencies"] == {"mcp": [_DOCS, _BROWSER]}
    assert ".apm/hooks/" in _includes(manifest)


def test_composition_without_servers_stays_empty(source_root: Path) -> None:
    assert _compose(source_root, "backend")["dependencies"] == {}


def test_conflicting_server_definitions_are_rejected(source_root: Path) -> None:
    _declare(source_root, "backend", _DOCS)
    _declare(source_root, "frontend", {**_DOCS, "url": "https://example.com/mcp"})

    with pytest.raises(CompositionError) as raised:
        _compose(source_root, "fullstack")

    assert CompositionIssue.MCP_CONFLICT in raised.value.args


def test_session_composition_keeps_the_hook_and_drops_servers(
    source_root: Path,
) -> None:
    _declare(source_root, "backend", _DOCS)
    _ship_hook(source_root)

    manifest = _compose(source_root, "backend", skills=("kit-backend",))

    assert manifest["dependencies"] == {}
    assert ".apm/hooks/" in _includes(manifest)
