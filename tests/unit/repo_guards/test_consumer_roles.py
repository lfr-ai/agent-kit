"""Portable profiles deliver canonical roles as target-scoped APM primitives."""

import json
from pathlib import Path

import pytest
import yaml

from agent_kit.application.native_delivery import render_native_agents
from agent_kit.infrastructure import owned_output
from scripts import build_profiles, render_native

_ROOT = Path(__file__).resolve().parents[3]
# Each case builds and renders complete role packages; `task check` skips them.
pytestmark = pytest.mark.slow
_CATALOG = json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))
_ASSETS = {
    path.relative_to(_ROOT).as_posix(): path.read_bytes()
    for path in sorted((_ROOT / "packages").glob("*/.apm/skills/*/assets/agents.json"))
}
_PROFILES = tuple(name for name in _CATALOG["profiles"] if name != "toolkit")
_PRIMARY = {"kit-orchestrator", "kit-debug"}
_WORKERS = {
    "kit-backend-implementer",
    "kit-code-reviewer",
    "kit-codebase-researcher",
    "kit-contract-iac-lint",
    "kit-ddd",
    "kit-deep-thinking",
    "kit-devops-implementer",
    "kit-docs-writer",
    "kit-eval-reviewer",
    "kit-frontend-implementer",
    "kit-infra-reviewer",
    "kit-planner",
    "kit-refactor",
    "kit-sdd",
    "kit-security-reviewer",
    "kit-test-author",
}
_TARGETS = {
    "copilot": (".github/agents/", ".agent.md"),
    "claude": (".claude/agents/", ".md"),
}


@pytest.fixture
def consumer_source(source_root: Path) -> Path:
    """Keep the real catalog and role assets, with inexpensive synthetic skills."""
    template = json.loads(
        (source_root / "packages/shared/apm.yml").read_text(encoding="utf-8")
    )
    for name, bundle in _CATALOG["bundles"].items():
        package = source_root / bundle["path"]
        instructions = package / ".apm/instructions"
        instructions.mkdir(parents=True, exist_ok=True)
        (instructions / f"kit-{name}.instructions.md").write_text(
            f'---\ndescription: Check {name} changes.\napplyTo: "**/*"\n---\n'
            "Inspect the assigned scope.\n",
            encoding="utf-8",
        )
        _skill(package / f".apm/skills/kit-{name}")
        (package / "apm.yml").write_text(
            json.dumps(
                template | {"name": f"agent-kit-{name}", "version": _CATALOG["version"]}
            ),
            encoding="utf-8",
        )
    for relative, content in _ASSETS.items():
        asset = source_root / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(content)
        _skill(asset.parent.parent)
    (source_root / "catalog.json").write_text(json.dumps(_CATALOG), encoding="utf-8")
    selection = source_root / ".agents/agentic-setup/self.json"
    selection.parent.mkdir(parents=True)
    selection.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "shared",
                "features": [name for name in _PROFILES if name != "shared"],
                "runtimes": list(_TARGETS),
            }
        ),
        encoding="utf-8",
    )
    return source_root


def _skill(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {directory.name}\ndescription: Inspect the assigned scope.\n"
        "---\n\nUse the canonical role guidance.\n",
        encoding="utf-8",
    )


def _manifest(path: Path) -> dict[str, object]:
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict), f"{path}: expected an APM manifest mapping"
    return manifest


def _metadata(content: bytes) -> tuple[dict[str, object], str]:
    _, header, body = content.decode("utf-8").split("---\n", 2)
    metadata = yaml.safe_load(header)
    assert isinstance(metadata, dict), "native agent frontmatter must be a mapping"
    return metadata, body


def _role_packages(root: Path) -> dict[Path, dict[str, object]]:
    """Discover packages by their APM primitive, not a proposed output directory."""
    packages = {}
    for path in sorted(root.rglob("apm.yml")):
        manifest = _manifest(path)
        includes = manifest.get("includes")
        assert isinstance(includes, list), f"{path}: includes must be explicit"
        if ".apm/agents/" in includes or ".apm/agents" in includes:
            packages[path.parent] = manifest
    assert packages, (
        "profile generation emitted no APM-native role package with explicit "
        ".apm/agents/ includes; checkout-only projections are not consumer delivery"
    )
    return packages


def _delivered_agents(root: Path, runtime: str) -> dict[str, bytes]:
    agents: dict[str, bytes] = {}
    for package, manifest in _role_packages(root).items():
        targets = manifest["targets"]
        assert targets in (["copilot"], ["claude"]), (
            f"{package}: provider-specific role packages need exactly one target"
        )
        if targets != [runtime]:
            continue
        for path in sorted((package / ".apm/agents").rglob("*.md")):
            content = path.read_bytes()
            name = _metadata(content)[0]["name"]
            assert isinstance(name, str), f"{path}: role name must be text"
            assert path.name in (f"{name}.agent.md", f"{name}.md"), (
                f"{path}: APM's filename-derived role must match the worker allowlist"
            )
            assert name not in agents, f"{runtime}: duplicate delivered role {name}"
            agents[name] = content
    assert set(agents) == _PRIMARY | _WORKERS, (
        f"{runtime}: every profile needs both primary roles and all 16 workers; "
        f"missing={sorted((_PRIMARY | _WORKERS) - agents.keys())}, "
        f"unexpected={sorted(agents.keys() - (_PRIMARY | _WORKERS))}"
    )
    return agents


def _change_role(root: Path, identifier: str, **changes: object) -> Path:
    for relative in _ASSETS:
        path = root / relative
        asset = json.loads(path.read_text(encoding="utf-8"))
        for role in asset["roles"]:
            if role["id"] == identifier:
                role.update(changes)
                path.write_text(json.dumps(asset), encoding="utf-8")
                return path
    pytest.fail(f"canonical fixture is missing role {identifier}")


def test_full_consumer_roster_reuses_the_existing_native_renderers(
    consumer_source: Path,
) -> None:
    roles = [
        role for content in _ASSETS.values() for role in json.loads(content)["roles"]
    ]
    assert {role["id"] for role in roles if role["kind"] == "primary"} == _PRIMARY
    assert {role["id"] for role in roles if role["kind"] == "worker"} == _WORKERS
    assert len(roles) == 18, "canonical roles must be unique, not independently copied"
    assert render_native.expected(consumer_source) == render_native_agents(
        _ASSETS, tuple(_TARGETS)
    )


def test_every_portable_profile_pins_the_generated_role_packages(
    consumer_source: Path,
) -> None:
    """Generate once, then check every published profile's dependency references."""
    build_profiles.write(consumer_source)

    packages = _role_packages(consumer_source)
    expected = [
        {
            "git": "https://github.com/lfr-ai/agent-kit.git",
            "path": package.relative_to(consumer_source).as_posix(),
            "ref": f"v{_CATALOG['version']}",
            "targets": manifest["targets"],
        }
        for package, manifest in packages.items()
    ]
    for profile in _PROFILES:
        relative = (
            f"profiles/starters/{profile.removeprefix('starter-')}"
            if profile.startswith("starter-")
            else f"profiles/{profile}"
        )
        manifest = _manifest(consumer_source / f"{relative}/apm.yml")
        dependencies = manifest["dependencies"]
        assert isinstance(dependencies, dict)
        references = dependencies["apm"]
        assert isinstance(references, list)
        assert all(reference in references for reference in expected), (
            f"{profile}: APM must resolve all role packages without consumer copying; "
            f"missing={[item for item in expected if item not in references]}"
        )
        assert len(references) == len(
            {json.dumps(item, sort_keys=True) for item in references}
        ), f"{profile}: repeated dependencies"
        assert manifest["includes"] == [], f"{profile}: keep profiles as meta-packages"
        assert not (consumer_source / f"{relative}/.apm").exists(), (
            f"{profile}: do not duplicate role sources into each profile"
        )
    assert not (consumer_source / "profiles/toolkit").exists()


@pytest.mark.parametrize("runtime", _TARGETS)
def test_apm_role_packages_preserve_roster_and_provider_metadata(
    consumer_source: Path, runtime: str
) -> None:
    expected = render_native_agents(_ASSETS, (runtime,))
    build_profiles.write(consumer_source)

    agents = _delivered_agents(consumer_source, runtime)
    prefix, suffix = _TARGETS[runtime]
    for name, content in agents.items():
        metadata, body = _metadata(content)
        expected_metadata, expected_body = _metadata(
            expected[f"{prefix}{name}{suffix}"]
        )
        assert metadata == expected_metadata, (
            f"{runtime}/{name}: native metadata changed"
        )
        assert body == expected_body, f"{runtime}/{name}: canonical procedure changed"
        assert "model" not in metadata, f"{runtime}/{name}: no new model preference"
    for package, manifest in _role_packages(consumer_source).items():
        assert manifest["version"] == _CATALOG["version"], package
        assert manifest["license"] == "MIT", package
        assert not manifest.get("scripts"), (
            f"{package}: consumers must not run a copier"
        )
        assert not manifest.get("executables"), f"{package}: roles need no executables"
        assert not list(package.rglob("agents.json")), (
            f"{package}: generated adapters must not become independent role sources"
        )
    assert build_profiles.check(consumer_source) == []


@pytest.mark.parametrize("runtime", _TARGETS)
def test_role_package_refresh_follows_canonical_body_and_narrow_model_preferences(
    consumer_source: Path, runtime: str
) -> None:
    build_profiles.write(consumer_source)
    before = _delivered_agents(consumer_source, runtime)
    asset = _change_role(
        consumer_source,
        "kit-backend-implementer",
        body="Inspect the synthetic change and report evidence.\n",
        models={"copilot": ["GPT-5 mini"], "claude": "haiku"},
    )
    authored = asset.read_bytes()

    build_profiles.write(consumer_source)

    after = _delivered_agents(consumer_source, runtime)
    metadata, body = _metadata(after["kit-backend-implementer"])
    assert metadata["model"] == (["GPT-5 mini"] if runtime == "copilot" else "haiku"), (
        f"{runtime}: preserve the exact authored model preference, never widen it"
    )
    assert body == "Inspect the synthetic change and report evidence.\n"
    assert {name for name, content in after.items() if content != before[name]} == {
        "kit-backend-implementer"
    }, "unrelated roles must not change"
    assert asset.read_bytes() == authored, (
        "generation must not rewrite canonical source"
    )
    assert build_profiles.check(consumer_source) == []


def test_role_package_refresh_refuses_independently_edited_generated_agents(
    consumer_source: Path,
) -> None:
    build_profiles.write(consumer_source)
    package = next(iter(_role_packages(consumer_source)))
    agent = next((package / ".apm/agents").rglob("*.md"))
    independent = agent.read_bytes() + b"\nIndependent edit.\n"
    agent.write_bytes(independent)

    assert build_profiles.check(consumer_source), (
        "generated role drift must be reported"
    )
    with pytest.raises(build_profiles.ProfileBuildError, match="edited independently"):
        build_profiles.write(consumer_source)

    assert agent.read_bytes() == independent, (
        "an independent edit must not be overwritten"
    )


@pytest.mark.parametrize(
    ("identifier", "changes"),
    [
        ("kit-backend-implementer", {"id": "kit-unreferenced"}),
        ("kit-backend-implementer", {"models": {"copilot": ["GPT-5"]}}),
        ("kit-backend-implementer", {"models": {"claude": "opus"}}),
    ],
    ids=["missing-worker", "unsupported-copilot-model", "unsupported-claude-model"],
)
def test_invalid_role_source_prevents_partial_profile_publication(
    consumer_source: Path, identifier: str, changes: dict[str, object]
) -> None:
    _change_role(consumer_source, identifier, **changes)
    before = {
        path.relative_to(consumer_source): path.read_bytes()
        for path in consumer_source.rglob("*")
        if path.is_file()
    }

    with pytest.raises(
        build_profiles.ProfileBuildError, match="source validation failed"
    ):
        build_profiles.write(consumer_source)

    after = {
        path.relative_to(consumer_source): path.read_bytes()
        for path in consumer_source.rglob("*")
        if path.is_file()
    }
    assert after == before, "invalid roles must not publish partial files or ledgers"


def _generated_files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for directory in ("profiles", ".agents/agentic-setup")
        for path in (root / directory).rglob("*")
        if path.is_file()
    }


def test_native_package_failure_rolls_back_profiles_roles_and_ledger(
    consumer_source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_profiles.write(consumer_source)
    before = _generated_files(consumer_source)
    _change_role(
        consumer_source, "kit-backend-implementer", body="Review the changed scope.\n"
    )
    replace = owned_output.replace_file
    failed = False
    failure = OSError("synthetic write failure")

    def fail_once(path: Path, content: bytes) -> None:
        nonlocal failed
        if "/native/copilot/.apm/agents/" in path.as_posix() and not failed:
            failed = True
            raise failure
        replace(path, content)

    monkeypatch.setattr(owned_output, "replace_file", fail_once)
    with pytest.raises(OSError, match="synthetic write failure"):
        build_profiles.write(consumer_source)
    assert failed
    assert _generated_files(consumer_source) == before


@pytest.mark.parametrize("linked", [False, True])
def test_native_package_rejects_unowned_files_and_linked_parents(
    consumer_source: Path, monkeypatch: pytest.MonkeyPatch, linked: bool
) -> None:
    build_profiles.write(consumer_source)
    package = next(iter(_role_packages(consumer_source)))
    marker = package / ".apm/agents/operator.md"
    marker.write_bytes(b"operator-owned")
    if linked:
        original = Path.is_symlink
        monkeypatch.setattr(
            Path, "is_symlink", lambda path: path == marker.parent or original(path)
        )
        with pytest.raises(build_profiles.ProfileBuildError, match="contains a link"):
            build_profiles.check(consumer_source)
    before = _generated_files(consumer_source)
    with pytest.raises(
        build_profiles.ProfileBuildError,
        match="contains a link" if linked else "unowned files",
    ):
        build_profiles.write(consumer_source)
    assert _generated_files(consumer_source) == before


def test_native_package_ledger_cannot_claim_files_outside_profiles(
    consumer_source: Path,
) -> None:
    build_profiles.write(consumer_source)
    ledger_path = consumer_source / ".agents/agentic-setup/profile-lock.json"
    ledger = json.loads(ledger_path.read_bytes())
    ledger["files"]["profiles/../operator.md"] = "0" * 64
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    marker = consumer_source / "operator.md"
    marker.write_bytes(b"operator-owned")
    with pytest.raises(build_profiles.ProfileBuildError, match="unsafe"):
        build_profiles.write(consumer_source)
    assert marker.read_bytes() == b"operator-owned"
