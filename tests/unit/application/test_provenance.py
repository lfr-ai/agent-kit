"""Composed-workspace integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.provenance_service import ProvenanceService
from agent_kit.core.errors import UnreadableDocumentError
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from agent_kit.infrastructure.output_adapter import OutputAdapter

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager

    from agent_kit.core.models import CheckReport


def _compose(source_root: Path, output: Path) -> Path:
    snapshot = FileCatalogAdapter().load(source_root)
    plan = CatalogService().compose(snapshot, "backend", (), ())
    return OutputAdapter().write(plan, output)


def _verify(root: Path) -> CheckReport:
    snapshot = FileCatalogAdapter().load_composed(root)
    return ProvenanceService().verify(snapshot)


def test_new_composition_passes_provenance(source_root: Path, tmp_path: Path) -> None:
    output = _compose(source_root, tmp_path / "backend")

    report = _verify(output)

    assert report.valid
    assert report.version == "0.1.0"


def test_provenance_hashes_manifest_and_native_policy(
    source_root: Path, tmp_path: Path
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    assert {"apm.yml", "apm-policy.yml"}.issubset(provenance["files"])
    assert str(source_root) not in (output / "provenance.json").read_text(
        encoding="utf-8"
    )

    for relative in ("apm.yml", "apm-policy.yml"):
        target = output / relative
        target.write_bytes(target.read_bytes() + b"\n")
        report = _verify(output)
        assert not report.valid
        assert any(relative in item.message for item in report.findings)
        target.write_bytes(target.read_bytes()[:-1])
        assert _verify(output).valid


def test_modified_and_extra_apm_files_fail_provenance(
    source_root: Path, tmp_path: Path
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    skill = output / ".apm/skills/kit-backend/SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8"
    )
    (output / ".apm/extra.md").write_text("extra\n", encoding="utf-8")

    report = _verify(output)

    assert not report.valid
    assert any(item.code == "provenance.drift" for item in report.findings)
    assert any(item.code == "provenance.extra" for item in report.findings)


def test_missing_recorded_file_fails_provenance(
    source_root: Path, tmp_path: Path
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    (output / ".apm/instructions/kit-backend.instructions.md").unlink()

    report = _verify(output)

    assert not report.valid
    assert any(item.code == "provenance.missing" for item in report.findings)


def test_malformed_provenance_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / "invalid"
    output.mkdir()
    (output / "provenance.json").write_text("{broken", encoding="utf-8")

    report = _verify(output)

    assert not report.valid
    assert any(item.code == "provenance.read" for item in report.findings)


def test_recorded_native_delivery_is_accepted_after_installation(
    source_root: Path, tmp_path: Path
) -> None:
    """Source provenance remains valid after APM creates attested native output."""
    output = _compose(source_root, tmp_path / "backend")
    relative = ".agents/skills/kit-backend/SKILL.md"
    native = output / relative
    native.parent.mkdir(parents=True)
    native.write_bytes((output / ".apm/skills/kit-backend/SKILL.md").read_bytes())
    digest = hashlib.sha256(native.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    lock = {
        "lockfile_version": "1",
        "dependencies": [],
        "deployments": [
            {
                "kind": "project-relative",
                "target": "legacy",
                "value": relative,
                "scope": "project",
                "owners": ["."],
                "active_owner": ".",
                "content_hash": f"sha256:{digest}",
            }
        ],
    }
    (output / "apm.lock.yaml").write_text(yaml.safe_dump(lock), encoding="utf-8")

    assert _verify(output).valid

    native.write_text("changed delivery", encoding="utf-8")
    report = _verify(output)
    assert not report.valid
    assert any(item.code == "provenance.delivery-drift" for item in report.findings)


def _with_hook(source_root: Path) -> None:
    bundle = source_root / "packages/shared"
    scripts = bundle / ".apm/hooks/scripts"
    scripts.mkdir(parents=True)
    (bundle / ".apm/hooks/guard.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "preToolUse": [
                        {
                            "type": "command",
                            "bash": "python3 ./scripts/guard.py",
                            "powershell": "python ./scripts/guard.py",
                            "timeoutSec": 10,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (scripts / "guard.py").write_text("print('guard')\n", encoding="utf-8")
    manifest = json.loads((bundle / "apm.yml").read_text(encoding="utf-8"))
    manifest["includes"] = [*manifest["includes"], ".apm/hooks/"]
    (bundle / "apm.yml").write_text(json.dumps(manifest), encoding="utf-8")


def _install_hook(output: Path, deliveries: dict[str, bytes]) -> None:
    entries = []
    for relative, content in deliveries.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        entries.append(
            {
                "kind": "project-relative",
                "target": "copilot",
                "value": relative,
                "scope": "project",
                "owners": ["."],
                "active_owner": ".",
                "content_hash": f"sha256:{hashlib.sha256(content).hexdigest()}",
            }
        )
    lock = {"lockfile_version": "1", "dependencies": [], "deployments": entries}
    (output / "apm.lock.yaml").write_text(yaml.safe_dump(lock), encoding="utf-8")


_HOOK_DELIVERY = {
    ".github/hooks/agent-kit-backend-guard.json": json.dumps(
        {
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {
                        "type": "command",
                        "bash": "python3 .github/hooks/scripts/agent-kit-backend/scripts/guard.py",
                        "powershell": "python .github/hooks/scripts/agent-kit-backend/scripts/guard.py",
                        "timeoutSec": 10,
                    }
                ]
            },
        }
    ).encode(),
    ".github/hooks/scripts/agent-kit-backend/scripts/guard.py": b"print('guard')\n",
    ".claude/hooks/agent-kit-backend/scripts/guard.py": b"print('guard')\n",
}
_CLAUDE_HOOKS = {
    "PreToolUse": [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": 'python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/agent-kit-backend/scripts/guard.py"',
                    "powershell": "python $env:CLAUDE_PROJECT_DIR/.claude/hooks/agent-kit-backend/scripts/guard.py",
                    "timeout": 10,
                }
            ],
        }
    ]
}


def test_delivered_hooks_and_merged_configuration_are_accepted(
    source_root: Path, tmp_path: Path
) -> None:
    """APM's hook files and merged MCP and settings files are post-install output."""
    _with_hook(source_root)
    output = _compose(source_root, tmp_path / "backend")
    _install_hook(output, _HOOK_DELIVERY)
    for relative in (".mcp.json", ".github/mcp.json"):
        (output / relative).parent.mkdir(parents=True, exist_ok=True)
        (output / relative).write_text("{}", encoding="utf-8")
    (output / ".claude/settings.json").write_text(
        json.dumps({"hooks": _CLAUDE_HOOKS}), encoding="utf-8"
    )

    assert _verify(output).valid

    (output / ".claude/hooks/agent-kit-backend/scripts/guard.py").write_text(
        "print('changed')\n", encoding="utf-8"
    )
    report = _verify(output)
    assert any(item.code == "provenance.delivery-drift" for item in report.findings)


@pytest.mark.parametrize(
    "relative",
    [
        ".github/hooks/scripts/agent-kit-backend/scripts/other.py",
        ".claude/hooks/agent-kit-backend/scripts/other.py",
        ".github/hooks/agent-kit-backend-other.json",
        ".github/hooks/scripts/agent-kit-backend/guard.py",
        ".github/hooks/guard.json",
    ],
)
def test_hook_delivery_must_match_an_authored_hook(
    relative: str, source_root: Path, tmp_path: Path
) -> None:
    _with_hook(source_root)
    output = _compose(source_root, tmp_path / "backend")
    _install_hook(output, {relative: b"x"})

    report = _verify(output)

    assert any(item.code == "provenance.delivery" for item in report.findings)


def test_rewritten_ledger_cannot_authorize_changed_hook_source(
    source_root: Path, tmp_path: Path
) -> None:
    _with_hook(source_root)
    output = _compose(source_root, tmp_path / "backend")
    _install_hook(
        output, {".claude/hooks/agent-kit-backend/scripts/guard.py": b"changed"}
    )

    assert any(
        item.code == "provenance.hook-source" for item in _verify(output).findings
    )


@pytest.mark.parametrize("relative", [".mcp.json", ".github/mcp.json"])
def test_unrecorded_mcp_server_is_not_accepted_as_metadata(
    source_root: Path, tmp_path: Path, relative: str
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    _install_hook(output, {})
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"mcpServers": {"injected": {"url": "https://example.com"}}}),
        encoding="utf-8",
    )

    assert any(item.code == "provenance.mcp" for item in _verify(output).findings)


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"hooks": {}},
        {"hooks": _CLAUDE_HOOKS, "disableAllHooks": True},
        {"hooks": _CLAUDE_HOOKS, "allowManagedHooksOnly": True},
        {
            "hooks": {
                "PreToolUse": [{"hooks": [{"type": "command", "command": "evil"}]}]
            }
        },
    ],
)
def test_effective_claude_hooks_cannot_be_removed_disabled_or_replaced(
    source_root: Path, tmp_path: Path, settings: dict[str, object]
) -> None:
    _with_hook(source_root)
    output = _compose(source_root, tmp_path / "backend")
    _install_hook(output, _HOOK_DELIVERY)
    (output / ".claude/settings.json").write_text(
        json.dumps(settings), encoding="utf-8"
    )

    assert any(item.code == "provenance.hooks" for item in _verify(output).findings)


def test_rewritten_ledger_cannot_authorize_changed_hook_registration(
    source_root: Path, tmp_path: Path
) -> None:
    _with_hook(source_root)
    output = _compose(source_root, tmp_path / "backend")
    _install_hook(output, {".github/hooks/agent-kit-backend-guard.json": b"{}"})

    assert any(item.code == "provenance.hooks" for item in _verify(output).findings)


@pytest.mark.parametrize("runtime", ["claude", "copilot"])
@pytest.mark.parametrize("transport", ["http", "stdio"])
def test_native_mcp_projection_matches_only_selected_runtime(
    source_root: Path, tmp_path: Path, runtime: str, transport: str
) -> None:
    path = source_root / "packages/backend/apm.yml"
    manifest = json.loads(path.read_text())
    connection = (
        {"url": "https://example.com/mcp"}
        if transport == "http"
        else {"command": "bunx", "args": ["--bun", "@scope/example@1.2.3"]}
    )
    manifest["dependencies"] = {
        "mcp": [
            {
                "name": "context7",
                "registry": False,
                "transport": transport,
                **connection,
            }
        ]
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    snapshot = FileCatalogAdapter().load(source_root)
    plan = CatalogService().compose(snapshot, "backend", (), (runtime,))
    output = OutputAdapter().write(plan, tmp_path / "backend")
    _install_hook(output, {})
    server: dict[str, object] = {
        "type": "local" if runtime == "copilot" and transport == "stdio" else transport,
        **connection,
    }
    if runtime == "copilot":
        server.update({"tools": ["*"], "id": ""})
    relative = ".mcp.json" if runtime == "claude" else ".github/mcp.json"
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"mcpServers": {"context7": server}}), encoding="utf-8"
    )

    assert _verify(output).valid

    server["url" if transport == "http" else "command"] = "changed"
    target.write_text(
        json.dumps({"mcpServers": {"context7": server}}), encoding="utf-8"
    )
    assert any(item.code == "provenance.mcp" for item in _verify(output).findings)


def test_denied_extra_subtree_enumeration_aborts_provenance_capture(
    source_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    denied = output / ".apm/unrecorded/assets"
    denied.mkdir(parents=True)
    (denied / "extra.bin").write_bytes(b"unrecorded")
    assert any(item.code == "provenance.extra" for item in _verify(output).findings)
    failure = PermissionError(13, "controlled enumeration denial", str(denied))
    scandir = os.scandir

    def denied_scandir(
        path: str | Path,
    ) -> AbstractContextManager[Iterator[os.DirEntry[str]]]:
        if str(path) == str(denied):
            raise failure
        return scandir(path)

    monkeypatch.setattr(os, "scandir", denied_scandir)
    with pytest.raises(UnreadableDocumentError, match="cannot be enumerated") as raised:
        _verify(output)

    assert raised.value.__cause__ is failure
    assert ".apm/unrecorded/assets" in str(raised.value)
    assert str(output) not in str(raised.value)


@pytest.mark.parametrize("original", [b"", b"approved"])
def test_denied_composed_asset_read_never_hashes_placeholder(
    source_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    original: bytes,
) -> None:
    relative = ".apm/skills/kit-backend/asset.bin"
    (source_root / "packages/backend" / relative).write_bytes(original)
    output = _compose(source_root, tmp_path / "backend")
    assert _verify(output).valid
    denied = output / relative
    denied.write_bytes(b"tampered")
    assert any(item.code == "provenance.drift" for item in _verify(output).findings)
    read_bytes = Path.read_bytes
    failure = PermissionError(13, "controlled read denial", str(denied))

    def denied_read(path: Path) -> bytes:
        if path == denied:
            raise failure
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", denied_read)
    report = _verify(output)

    assert not report.valid
    assert any(
        item.code == "provenance.read" and item.path == relative
        for item in report.findings
    )
    assert any(
        item.code == "provenance.missing" and item.path == relative
        for item in report.findings
    )
    assert not any(item.code == "provenance.drift" for item in report.findings)


@pytest.mark.parametrize("content", [b"", b"field: [", b"\xff"])
def test_readable_assets_are_hashed_as_raw_bytes(
    source_root: Path, tmp_path: Path, content: bytes
) -> None:
    """Real empty/binary assets and readable malformed YAML remain hashable."""
    relative = ".apm/skills/kit-backend/asset.yaml"
    (source_root / "packages/backend" / relative).write_bytes(b"")
    output = _compose(source_root, tmp_path / "backend")
    (output / relative).write_bytes(content)
    provenance_path = output / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["files"][relative] = hashlib.sha256(content).hexdigest()
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    snapshot = FileCatalogAdapter().load_composed(output)
    document = next(item for item in snapshot.files if item.relative_path == relative)

    assert document.content == content
    assert document.parse_error is (content == b"field: [")
    assert ProvenanceService().verify(snapshot).valid
