"""Runtime-specific agent adapters are rendered from portable assets."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest
import yaml

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.native_delivery import (
    render_native_agents,
    validate_native_assets,
)
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

if TYPE_CHECKING:
    from pathlib import Path


def _role(
    identifier: str,
    *,
    kind: str = "worker",
    tier: str = "readonly",
    workers: list[str] | None = None,
    models: dict[str, object] | None = None,
    description: str = "A concise role description.",
    body: str = "Inspect the assigned scope and report evidence.",
) -> dict[str, object]:
    role: dict[str, object] = {
        "id": identifier,
        "kind": kind,
        "tier": tier,
        "description": description,
        "body": body,
        "workers": workers or [],
    }
    if models is not None:
        role["models"] = models
    return role


def _assets(*roles: dict[str, object]) -> dict[str, bytes]:
    content = json.dumps({"schema_version": 1, "roles": list(roles)}).encode()
    return {".apm/skills/kit-runtime/assets/agents.json": content}


def _metadata(content: bytes) -> tuple[dict[str, object], bytes]:
    text = content.decode("utf-8")
    _, frontmatter, body = text.split("---\n", 2)
    metadata = yaml.safe_load(frontmatter)
    assert isinstance(metadata, dict)
    return metadata, body.encode("utf-8")


def test_render_emits_provider_metadata_with_identical_source_bodies() -> None:
    body = "Line one.\nKeep this exact body.\n"
    rendered = render_native_agents(
        _assets(
            _role(
                "kit-analyzer",
                kind="primary",
                body="Read and report. Do not edit, execute, or delegate.",
            ),
            _role(
                "kit-coordinator",
                kind="primary",
                tier="coordinator",
                workers=["kit-builder"],
            ),
            _role(
                "kit-builder",
                tier="implementer",
                body=body,
                models={
                    "copilot": ["GPT-5 mini", "Claude Haiku 4.5"],
                    "claude": "haiku",
                },
            ),
        ),
        ("copilot", "claude"),
    )

    assert set(rendered) == {
        ".github/agents/kit-analyzer.agent.md",
        ".github/agents/kit-coordinator.agent.md",
        ".github/agents/subagents/kit-builder.agent.md",
        ".claude/agents/kit-analyzer.md",
        ".claude/agents/kit-coordinator.md",
        ".claude/agents/subagents/kit-builder.md",
    }
    copilot_metadata, copilot_body = _metadata(
        rendered[".github/agents/subagents/kit-builder.agent.md"]
    )
    claude_metadata, claude_body = _metadata(
        rendered[".claude/agents/subagents/kit-builder.md"]
    )
    assert copilot_body == claude_body == body.encode()
    assert copilot_metadata["model"] == ["GPT-5 mini", "Claude Haiku 4.5"]
    assert claude_metadata["model"] == "haiku"
    assert copilot_metadata["agents"] == []
    assert copilot_metadata["user-invocable"] is False
    assert copilot_metadata["disable-model-invocation"] is False
    assert "model" not in _metadata(rendered[".claude/agents/kit-analyzer.md"])[0]
    assert copilot_metadata["tools"] == ["read", "search", "edit", "execute"]
    assert (
        _metadata(rendered[".claude/agents/subagents/kit-builder.md"])[0]["tools"]
        == "Read, Grep, Glob, Edit, Write, Bash"
    )
    assert _metadata(rendered[".claude/agents/kit-analyzer.md"])[0]["tools"] == (
        "Read, Grep, Glob"
    )
    assert _metadata(rendered[".github/agents/kit-analyzer.agent.md"])[0] == {
        "name": "kit-analyzer",
        "description": "A concise role description.",
        "tools": ["read", "search"],
        "agents": [],
        "user-invocable": True,
        "disable-model-invocation": True,
    }
    for identifier in ("kit-analyzer", "kit-coordinator", "kit-builder"):
        directory = "/subagents" if identifier == "kit-builder" else ""
        assert (
            _metadata(rendered[f".github/agents{directory}/{identifier}.agent.md"])[1]
            == _metadata(rendered[f".claude/agents{directory}/{identifier}.md"])[1]
        )


@pytest.mark.parametrize(
    ("runtime", "expected_prefix", "excluded_prefix"),
    [
        ("copilot", ".github/agents/", ".claude/agents/"),
        ("claude", ".claude/agents/", ".github/agents/"),
    ],
)
def test_runtime_selection_filters_only_generated_adapter_files(
    runtime: str, expected_prefix: str, excluded_prefix: str
) -> None:
    source = _assets(_role("kit-reader", kind="primary"))
    rendered = render_native_agents(source, (runtime,))

    assert rendered
    assert all(path.startswith(expected_prefix) for path in rendered)
    assert not any(path.startswith(excluded_prefix) for path in rendered)


def test_renderer_processes_every_matching_skill_asset_path() -> None:
    asset = _assets(_role("kit-reader", kind="primary")).popitem()[1]

    rendered = render_native_agents(
        {".apm/skills/custom-name/assets/agents.json": asset},
        ("claude",),
    )

    assert ".claude/agents/kit-reader.md" in rendered


def test_coordinator_worker_permissions_are_explicit_per_runtime() -> None:
    rendered = render_native_agents(
        _assets(
            _role(
                "kit-coordinator",
                kind="primary",
                tier="coordinator",
                workers=["kit-builder"],
            ),
            _role("kit-builder", tier="implementer"),
        ),
        ("copilot", "claude"),
    )

    copilot, _ = _metadata(rendered[".github/agents/kit-coordinator.agent.md"])
    claude, _ = _metadata(rendered[".claude/agents/kit-coordinator.md"])
    assert copilot["tools"] == ["read", "search", "edit", "execute", "agent"]
    assert copilot["agents"] == ["kit-builder"]
    assert copilot["user-invocable"] is True
    assert copilot["disable-model-invocation"] is True
    assert claude["tools"] == (
        "Agent(kit-builder), Read, Grep, Glob, Edit, Write, Bash"
    )
    assert set(claude) == {"name", "description", "tools"}


@pytest.mark.parametrize(
    ("roles", "message"),
    [
        (
            [
                _role(
                    "kit-coordinator",
                    kind="primary",
                    tier="coordinator",
                    workers=["kit-absent"],
                )
            ],
            "worker 'kit-absent' is unavailable",
        ),
        (
            [_role("kit-worker", tier="implementer", models={"claude": "unknown"})],
            "unsupported Claude model",
        ),
        (
            [
                _role(
                    "kit-worker",
                    tier="implementer",
                    models={"copilot": ["GPT-5 mini", "*"]},
                )
            ],
            "unsupported Copilot model",
        ),
        (
            [_role("kit-worker", tier="implementer", description="x" * 181)],
            "description exceeds 180 characters",
        ),
        (
            [_role("kit-worker", tier="implementer", body="\n".join(["step"] * 126))],
            "body exceeds 125 lines",
        ),
        (
            [
                _role(
                    "kit-worker",
                    tier="readonly",
                    body="secret: synthetic-placeholder",
                )
            ],
            "secret-like",
        ),
        (
            [_role("kit-worker", tier="readonly", workers=["kit-*"])],
            "invalid worker identifier",
        ),
    ],
)
def test_invalid_or_unsafe_role_definitions_fail_closed(
    roles: list[dict[str, object]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        render_native_agents(_assets(*roles), ("copilot",))


def test_duplicate_role_ids_across_assets_fail_closed() -> None:
    role = _role("kit-reader", kind="primary")
    files = _assets(role)
    files[".apm/skills/kit-another/assets/agents.json"] = json.dumps(
        {"schema_version": 1, "roles": [role]}
    ).encode()

    with pytest.raises(ValueError, match="duplicate role id 'kit-reader'"):
        render_native_agents(files, ("claude",))


def test_duplicate_json_keys_unknown_fields_and_invalid_tiers_fail_closed() -> None:
    path = ".apm/skills/kit-runtime/assets/agents.json"
    with pytest.raises(ValueError, match="duplicate JSON field"):
        render_native_agents(
            {path: b'{"schema_version":1,"schema_version":1,"roles":[]}'},
            ("claude",),
        )
    with pytest.raises(ValueError, match="unknown field 'extra'"):
        render_native_agents(
            _assets(_role("kit-reader", kind="primary") | {"extra": True}),
            ("claude",),
        )
    with pytest.raises(ValueError, match="invalid tier"):
        render_native_agents(
            _assets(_role("kit-reader", kind="primary", tier="admin")),
            ("claude",),
        )
    invalid_kind = _role("kit-reader", kind="primary")
    invalid_kind["kind"] = ["primary"]
    with pytest.raises(TypeError, match="kind must be a string"):
        render_native_agents(_assets(invalid_kind), ("claude",))


def test_validator_reuses_render_validation_and_rejects_unknown_runtimes() -> None:
    invalid = _assets(
        _role("kit-worker", tier="implementer", models={"claude": "unknown"})
    )
    with pytest.raises(ValueError, match="unsupported Claude model"):
        validate_native_assets(invalid, ("claude",))
    with pytest.raises(ValueError, match="unsupported Claude model"):
        render_native_agents(invalid, ("claude",))
    with pytest.raises(ValueError, match="runtime targets"):
        validate_native_assets(_assets(), ("other",))


@pytest.mark.parametrize(
    ("roles", "message"),
    [
        ([_role("kit-inactive", tier="admin")], "invalid tier"),
        ("not-a-list", "roles must be a list"),
    ],
)
def test_catalog_validation_checks_native_assets_in_inactive_bundles(
    source_root: Path, roles: object, message: str
) -> None:
    asset = (
        source_root / "packages/frontend/.apm/skills/kit-frontend/assets/agents.json"
    )
    asset.parent.mkdir()
    asset.write_bytes(json.dumps({"schema_version": 1, "roles": roles}).encode())

    report = CatalogService().validate(FileCatalogAdapter().load(source_root))

    assert any(
        item.code == "native.assets" and message in item.message
        for item in report.findings
    )


def test_compose_keeps_source_assets_and_hashes_generated_adapters(
    source_root: Path,
) -> None:
    asset = source_root / "packages/shared/.apm/skills/kit-shared/assets/agents.json"
    asset.parent.mkdir()
    asset.write_bytes(
        json.dumps(
            {
                "schema_version": 1,
                "roles": [_role("kit-shared-reviewer", kind="primary")],
            }
        ).encode()
    )
    snapshot = FileCatalogAdapter().load(source_root)

    plan = CatalogService().compose(snapshot, "backend", (), ("claude",))

    files = {item.relative_path: item.content for item in plan.files}
    adapter = files[".claude/agents/kit-shared-reviewer.md"]
    provenance = json.loads(files["provenance.json"])
    assert ".apm/skills/kit-shared/assets/agents.json" in files
    assert ".github/agents/kit-shared-reviewer.agent.md" not in files
    assert provenance["files"][".claude/agents/kit-shared-reviewer.md"] == (
        hashlib.sha256(adapter).hexdigest()
    )
