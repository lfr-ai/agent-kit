"""Runtime-specific agent adapters are rendered from portable assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.native_delivery import (
    render_native_agents,
    validate_native_assets,
)
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_ASSETS = {
    path.relative_to(_ROOT).as_posix(): path.read_bytes()
    for path in sorted((_ROOT / "packages").glob("*/.apm/skills/*/assets/agents.json"))
}
_CANONICAL_ROLES = [
    role
    for content in _CANONICAL_ASSETS.values()
    for role in json.loads(content)["roles"]
]
_MAIN_ROLES = {"kit-debug", "kit-orchestrator"}
_RETIRED_ROLES = {
    "kit-ai-engineer",
    "kit-devops",
    "kit-frontend",
    "kit-fullstack",
    "kit-modernization",
    "kit-plan-architect",
    "kit-reviewer",
    "kit-solid-review",
    "kit-tdd",
}
_ADVISERS = {"kit-ddd", "kit-sdd", "kit-deep-thinking"}
_VERIFIERS = {
    "kit-code-reviewer",
    "kit-codebase-researcher",
    "kit-contract-iac-lint",
    "kit-ddd",
    "kit-deep-thinking",
    "kit-eval-reviewer",
    "kit-infra-reviewer",
    "kit-planner",
    "kit-sdd",
    "kit-security-reviewer",
}
_COPILOT_TIER_TOOLS = {
    "verifier": ["read", "search", "execute", "todo"],
    "implementer": ["read", "search", "edit", "execute", "todo"],
    "coordinator": ["read", "search", "edit", "execute", "agent", "todo"],
}
_CLAUDE_TIER_TOOLS = {
    "verifier": "Read, Grep, Glob, Bash",
    "implementer": "Read, Grep, Glob, Edit, Write, Bash",
}


def test_canonical_picker_roster_and_worker_links_are_deliberate() -> None:
    """Specialists stay callable, not picker entries or unrestricted delegates."""
    roles = {role["id"]: role for role in _CANONICAL_ROLES}
    assert {name for name, role in roles.items() if role["kind"] == "primary"} == (
        _MAIN_ROLES
    )
    assert "kit-testing" not in roles
    assert not roles.keys() & _RETIRED_ROLES
    assert roles["kit-refactor"]["kind"] == "worker"
    assert roles["kit-refactor"]["tier"] == "implementer"
    assert "kit-refactor" in roles["kit-orchestrator"]["workers"]
    assert "kit-infra-reviewer" in roles["kit-orchestrator"]["optional_workers"]
    assert {
        "kit-devops-implementer",
        "kit-test-author",
        "kit-refactor",
    } <= set(roles["kit-orchestrator"]["workers"])
    assert all(roles[name]["kind"] == "worker" for name in _ADVISERS)
    assert all(roles[name]["tier"] == "verifier" for name in _ADVISERS)
    referenced = set()
    for role in roles.values():
        workers = [*role["workers"], *role.get("optional_workers", [])]
        assert "*" not in workers
        for worker in workers:
            assert roles[worker]["kind"] == "worker"
        referenced.update(workers)
        if role["kind"] == "worker":
            assert role["tier"] != "coordinator", role["id"]
    assert (
        set(roles["kit-orchestrator"]["workers"])
        | set(roles["kit-orchestrator"]["optional_workers"])
        >= _ADVISERS
    )
    assert referenced == {
        name for name, role in roles.items() if role["kind"] == "worker"
    }


def test_canonical_frontmatter_matches_tier_and_kind() -> None:
    """Every role renders the documented tools, visibility and worker allowlist."""
    rendered = render_native_agents(_CANONICAL_ASSETS, ("copilot", "claude"))
    assert len(rendered) == 2 * len(_CANONICAL_ROLES)
    names = {role["id"] for role in _CANONICAL_ROLES}
    worker_names = {role["id"] for role in _CANONICAL_ROLES if role["kind"] == "worker"}
    for role in _CANONICAL_ROLES:
        name = role["id"]
        copilot, copilot_body = _metadata(rendered[f".github/agents/{name}.agent.md"])
        claude, claude_body = _metadata(rendered[f".claude/agents/{name}.md"])
        assert copilot_body == claude_body, name
        assert copilot["name"] == claude["name"] == name
        copilot_tools = copilot["tools"]
        claude_tools = claude["tools"]
        assert isinstance(copilot_tools, list), name
        assert isinstance(claude_tools, str), name
        assert {"read", "search"} <= set(copilot_tools), name
        assert {"Read", "Grep", "Glob"} <= set(claude_tools.split(", ")), name
        assert copilot_tools == _COPILOT_TIER_TOOLS[role["tier"]], name
        is_primary = role["kind"] == "primary"
        assert copilot["user-invocable"] is is_primary, name
        assert copilot["disable-model-invocation"] is is_primary, name
        if role["tier"] == "coordinator":
            workers = copilot["agents"]
            assert isinstance(workers, list), name
            assert workers == [*role["workers"], *role.get("optional_workers", [])]
            assert workers, name
            assert set(workers) <= worker_names, name
            assert set(workers) <= names, name
            assert claude_tools == (
                f"Agent({', '.join(workers)}), Read, Grep, Glob, Edit, Write, Bash"
            ), name
        else:
            assert "agents" not in copilot, name
            assert claude_tools == _CLAUDE_TIER_TOOLS[role["tier"]], name


def test_verifier_roster_is_exact() -> None:
    """Analysis, review and verification roles share the non-editing shell tier."""
    assert {
        role["id"] for role in _CANONICAL_ROLES if role["tier"] == "verifier"
    } == _VERIFIERS


def test_every_canonical_role_can_inspect_history_with_a_shell() -> None:
    """No role is rendered without the shell needed for diffs, history and checks."""
    assert all(role["tier"] != "readonly" for role in _CANONICAL_ROLES)
    rendered = render_native_agents(_CANONICAL_ASSETS, ("copilot", "claude"))
    for role in _CANONICAL_ROLES:
        name = role["id"]
        copilot, _ = _metadata(rendered[f".github/agents/{name}.agent.md"])
        claude, _ = _metadata(rendered[f".claude/agents/{name}.md"])
        copilot_tools = copilot["tools"]
        claude_tools = claude["tools"]
        assert isinstance(copilot_tools, list), name
        assert isinstance(claude_tools, str), name
        assert "execute" in copilot_tools, name
        assert "Bash" in claude_tools.split(", "), name


def test_every_coordinator_worker_resolves_to_a_rendered_name() -> None:
    """Each ``agents:`` entry must match the ``name:`` of an existing agent file."""
    rendered = render_native_agents(_CANONICAL_ASSETS, ("copilot",))
    discovered = {_metadata(content)[0]["name"] for content in rendered.values()}
    for path, content in rendered.items():
        metadata, _ = _metadata(content)
        workers = metadata.get("agents", [])
        assert isinstance(workers, list), path
        for worker in workers:
            assert worker in discovered, (path, worker)
    assert all(path.count("/") == 2 for path in rendered)


def _role(
    identifier: str,
    *,
    kind: str = "worker",
    tier: str = "verifier",
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


@pytest.mark.parametrize(
    ("coordinator", "worker"),
    [
        ("kit-orchestrator", "kit-planner"),
        ("kit-orchestrator", "kit-devops-implementer"),
    ],
)
def test_workers_resolve_from_flat_discovery_without_picker_visibility(
    coordinator: str, worker: str
) -> None:
    """Hidden helpers must still resolve by exact name from the standard folder."""
    rendered = render_native_agents(
        _assets(
            _role(
                coordinator,
                kind="primary",
                tier="coordinator",
                workers=[worker],
            ),
            _role(worker),
        ),
        ("copilot", "claude"),
    )
    discovered = {
        _metadata(content)[0]["name"]: _metadata(content)[0]
        for path, content in rendered.items()
        if path.startswith(".github/agents/") and path.count("/") == 2
    }

    assert set(discovered) == {coordinator, worker}
    assert discovered[coordinator]["agents"] == [worker]
    assert discovered[worker]["user-invocable"] is False
    assert discovered[worker]["disable-model-invocation"] is False
    assert f".claude/agents/{worker}.md" in rendered


def test_verifier_tier_gets_a_shell_but_no_editing_or_delegation_tools() -> None:
    """Verifiers get execution for offline inspection, not implementation."""
    rendered = render_native_agents(
        _assets(_role("kit-verifier")), ("copilot", "claude")
    )

    verifier, _ = _metadata(rendered[".github/agents/kit-verifier.agent.md"])
    claude_verifier, _ = _metadata(rendered[".claude/agents/kit-verifier.md"])
    assert verifier["tools"] == ["read", "search", "execute", "todo"]
    assert "agents" not in verifier
    assert claude_verifier["tools"] == "Read, Grep, Glob, Bash"


def test_removed_shell_less_tier_fails_closed() -> None:
    """The retired ``readonly`` tier is rejected instead of rendered without a shell."""
    with pytest.raises(ValueError, match="invalid tier"):
        render_native_agents(
            _assets(_role("kit-reader", tier="readonly")), ("copilot",)
        )


def test_render_emits_provider_metadata_with_identical_source_bodies() -> None:
    body = "Line one.\nKeep this exact body.\n"
    rendered = render_native_agents(
        _assets(
            _role(
                "kit-analyzer",
                kind="primary",
                body="Read and report. Do not edit or delegate.",
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
        ".github/agents/kit-builder.agent.md",
        ".claude/agents/kit-analyzer.md",
        ".claude/agents/kit-coordinator.md",
        ".claude/agents/kit-builder.md",
    }
    copilot_metadata, copilot_body = _metadata(
        rendered[".github/agents/kit-builder.agent.md"]
    )
    claude_metadata, claude_body = _metadata(rendered[".claude/agents/kit-builder.md"])
    assert copilot_body == claude_body == body.encode()
    assert copilot_metadata["model"] == ["GPT-5 mini", "Claude Haiku 4.5"]
    assert claude_metadata["model"] == "haiku"
    assert "agents" not in copilot_metadata
    assert copilot_metadata["user-invocable"] is False
    assert copilot_metadata["disable-model-invocation"] is False
    assert "model" not in _metadata(rendered[".claude/agents/kit-analyzer.md"])[0]
    assert copilot_metadata["tools"] == ["read", "search", "edit", "execute", "todo"]
    assert (
        _metadata(rendered[".claude/agents/kit-builder.md"])[0]["tools"]
        == "Read, Grep, Glob, Edit, Write, Bash"
    )
    assert _metadata(rendered[".claude/agents/kit-analyzer.md"])[0]["tools"] == (
        "Read, Grep, Glob, Bash"
    )
    assert _metadata(rendered[".github/agents/kit-analyzer.agent.md"])[0] == {
        "name": "kit-analyzer",
        "description": "A concise role description.",
        "tools": ["read", "search", "execute", "todo"],
        "user-invocable": True,
        "disable-model-invocation": True,
    }
    for identifier in ("kit-analyzer", "kit-coordinator", "kit-builder"):
        assert (
            _metadata(rendered[f".github/agents/{identifier}.agent.md"])[1]
            == _metadata(rendered[f".claude/agents/{identifier}.md"])[1]
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
    assert copilot["tools"] == ["read", "search", "edit", "execute", "agent", "todo"]
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
                    tier="verifier",
                    body="secret: synthetic-placeholder",
                )
            ],
            "secret-like",
        ),
        (
            [_role("kit-worker", tier="verifier", workers=["kit-*"])],
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


@pytest.mark.parametrize(
    ("coordinator_bundle", "worker_bundle"),
    [("shared", "shared"), ("shared", "frontend"), ("backend", "shared")],
)
def test_native_dependencies_must_close_within_each_effective_profile(
    source_root: Path, coordinator_bundle: str, worker_bundle: str
) -> None:
    coordinator = _role(
        "kit-coordinator",
        kind="primary",
        tier="coordinator",
        workers=["kit-builder"],
    )
    worker = _role("kit-builder", tier="implementer")
    by_bundle = {coordinator_bundle: [coordinator]}
    by_bundle.setdefault(worker_bundle, []).append(worker)
    for bundle, roles in by_bundle.items():
        asset = (
            source_root
            / f"packages/{bundle}/.apm/skills/kit-{bundle}/assets/agents.json"
        )
        asset.parent.mkdir()
        asset.write_bytes(json.dumps({"schema_version": 1, "roles": roles}).encode())
    snapshot = FileCatalogAdapter().load(source_root)
    service = CatalogService()

    report = service.validate(snapshot)

    if worker_bundle == "frontend":
        assert {
            item.path for item in report.findings if item.code == "native.assets"
        } == {
            f"catalog.json:profiles:{name}"
            for name in ("toolkit", "shared", "backend", "iac")
        }
        assert all(
            "required worker 'kit-builder' is unavailable" in item.message
            for item in report.findings
        )
        with pytest.raises(ValueError, match="source validation failed"):
            service.compose(snapshot, "shared", (), ())
    else:
        assert report.valid, report.findings
        for profile in ("shared", "backend", "fullstack"):
            plan = service.compose(snapshot, profile, (), ())
            assert ".github/agents/kit-builder.agent.md" in {
                item.relative_path for item in plan.files
            }
            if coordinator_bundle == "shared" or profile != "shared":
                assert ".github/agents/kit-coordinator.agent.md" in {
                    item.relative_path for item in plan.files
                }


@pytest.mark.parametrize("discoverable", [False, True])
def test_profile_native_closure_uses_discoverable_skill_assets(
    source_root: Path, discoverable: bool
) -> None:
    shared = source_root / "packages/shared/.apm/skills"
    coordinator = shared / "kit-shared/assets/agents.json"
    coordinator.parent.mkdir()
    coordinator.write_bytes(
        json.dumps(
            {
                "schema_version": 1,
                "roles": [
                    _role(
                        "kit-coordinator",
                        kind="primary",
                        tier="coordinator",
                        workers=["kit-builder"],
                    )
                ],
            }
        ).encode()
    )
    worker = shared / "kit-worker/assets/agents.json"
    worker.parent.mkdir(parents=True)
    worker.write_bytes(
        json.dumps(
            {
                "schema_version": 1,
                "roles": [_role("kit-builder", tier="implementer")],
            }
        ).encode()
    )
    if discoverable:
        (shared / "kit-worker/SKILL.md").write_text(
            "---\nname: kit-worker\ndescription: Build the assigned change.\n"
            "---\n\nInspect and implement the assigned scope.\n",
            encoding="utf-8",
        )
    snapshot = FileCatalogAdapter().load(source_root)
    service = CatalogService()

    report = service.validate(snapshot)

    if not discoverable:
        assert not report.valid
        assert {item.path for item in report.findings} == {
            f"catalog.json:profiles:{name}"
            for name in ("toolkit", "shared", "backend", "frontend", "fullstack", "iac")
        }
        assert all(
            item.code == "native.assets"
            and "required worker 'kit-builder' is unavailable" in item.message
            for item in report.findings
        )
        with pytest.raises(ValueError, match="source validation failed"):
            service.compose(snapshot, "shared", (), ())
    else:
        assert report.valid, report.findings
        plan = service.compose(snapshot, "shared", (), ())
        assert plan.bundles == ("shared",)
        paths = {item.relative_path for item in plan.files}
        assert {
            ".apm/skills/kit-worker/SKILL.md",
            ".apm/skills/kit-worker/assets/agents.json",
            ".github/agents/kit-coordinator.agent.md",
            ".github/agents/kit-builder.agent.md",
            ".claude/agents/kit-coordinator.md",
            ".claude/agents/kit-builder.md",
        } <= paths


def test_catalog_validation_still_checks_omitted_native_assets(
    source_root: Path,
) -> None:
    asset = source_root / "packages/shared/.apm/skills/kit-worker/assets/agents.json"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(json.dumps({"schema_version": 1, "roles": "not-a-list"}).encode())

    report = CatalogService().validate(FileCatalogAdapter().load(source_root))

    assert not report.valid
    assert any(
        item.code == "native.assets"
        and item.path == "catalog.json"
        and "roles must be a list" in item.message
        for item in report.findings
    )


def _coordinator(optional: list[str]) -> dict[str, object]:
    return _role(
        "kit-lead",
        kind="primary",
        tier="coordinator",
        workers=["kit-reader"],
    ) | {"optional_workers": optional}


def test_optional_workers_link_only_when_their_role_is_selected() -> None:
    """A shared coordinator gains a bundle's worker only when it is composed."""
    lead = _coordinator(["kit-builder"])
    reader = _role("kit-reader")
    builder = _role("kit-builder", tier="implementer")

    without = render_native_agents(_assets(lead, reader), ("copilot", "claude"))
    with_builder = render_native_agents(
        _assets(lead, reader, builder), ("copilot", "claude")
    )

    copilot, _ = _metadata(without[".github/agents/kit-lead.agent.md"])
    assert copilot["agents"] == ["kit-reader"]
    copilot, _ = _metadata(with_builder[".github/agents/kit-lead.agent.md"])
    assert copilot["agents"] == ["kit-reader", "kit-builder"]
    claude, _ = _metadata(with_builder[".claude/agents/kit-lead.md"])
    assert str(claude["tools"]).startswith("Agent(kit-reader, kit-builder)")


def test_catalog_validation_requires_every_optional_worker_to_exist() -> None:
    """A misspelled optional worker fails the whole-catalog check, not composition."""
    # Deliberate misspelling of a worker id; cspell:ignore bilder
    files = _assets(_coordinator(["kit-bilder"]), _role("kit-reader"))

    validate_native_assets(files, ("copilot",))
    with pytest.raises(ValueError, match="'kit-bilder' is unavailable"):
        validate_native_assets(files, ("copilot",), require_optional=True)


@pytest.mark.parametrize(
    ("roles", "message"),
    [
        (
            [_coordinator(["kit-reader"]), _role("kit-reader")],
            "repeat a required worker",
        ),
        (
            [
                _role("kit-solo", kind="primary", tier="implementer")
                | {"optional_workers": ["kit-reader"]},
                _role("kit-reader"),
            ],
            "only allowed for coordinators",
        ),
        (
            [
                _coordinator(["kit-other"]),
                _role("kit-reader"),
                _role("kit-other", kind="primary"),
            ],
            "is not a worker",
        ),
        (
            [_coordinator(["kit-*"]), _role("kit-reader")],
            "invalid worker identifier",
        ),
    ],
)
def test_invalid_optional_workers_fail_closed(
    roles: list[dict[str, object]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        render_native_agents(_assets(*roles), ("copilot",))


def test_repository_coordinators_reach_selected_bundle_implementers() -> None:
    """The shared orchestrator delegates to implementers of selected bundles only."""
    root = Path(__file__).resolve().parents[3]
    snapshot = FileCatalogAdapter().load(root)

    def agents(profile: str) -> list[object]:
        plan = CatalogService().compose(snapshot, profile, (), ("copilot",))
        files = {item.relative_path: item.content for item in plan.files}
        metadata, _ = _metadata(files[".github/agents/kit-orchestrator.agent.md"])
        workers = metadata["agents"]
        assert isinstance(workers, list)
        return workers

    shared = agents("shared")
    assert "kit-backend-implementer" not in shared
    assert {"kit-planner", "kit-deep-thinking"} <= set(shared)
    assert not {"kit-ddd", "kit-sdd"} & set(shared)
    assert {
        "kit-backend-implementer",
        "kit-contract-iac-lint",
        "kit-ddd",
        "kit-sdd",
    } <= set(agents("backend"))
    assert "kit-frontend-implementer" in agents("frontend")
    assert "kit-infra-reviewer" in agents("iac")
