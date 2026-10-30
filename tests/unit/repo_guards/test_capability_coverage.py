"""Completeness and configuration-facade regressions for the expanded toolkit."""

import json
from pathlib import Path
import shutil

import pytest
import scripts.check_coverage as coverage_module
from scripts.check_coverage import check
import yaml

_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def coverage_inputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Read source once; per-case mutations still use isolated temporary copies."""
    root = tmp_path_factory.mktemp("coverage-inputs")
    for directory in (".apm", "packages", ".agents/agentic-setup", ".vscode"):
        shutil.copytree(
            _ROOT / directory,
            root / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for name in (
        "Taskfile.yml",
        ".mcp.json",
        "scripts/verify.py",
        "scripts/check_docs.py",
        "scripts/check_coverage.py",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_ROOT / name, target)
    return root


@pytest.fixture
def covered_root(tmp_path: Path, coverage_inputs: Path) -> Path:
    """Never mutate either the source tree or another case's fixture."""
    shutil.copytree(coverage_inputs, tmp_path, dirs_exist_ok=True)
    return tmp_path


def test_all_original_capabilities_have_a_disposition(covered_root: Path) -> None:
    """Missing capabilities are a failing manifest contract, not an unstated reduction."""
    assert check(covered_root) == []


def test_duplicate_inventory_json_key_has_a_stable_input_diagnostic(
    tmp_path: Path,
) -> None:
    """Duplicate source entries remain rejected with their domain diagnostic."""
    path = tmp_path / "coverage.json"
    path.write_text('{"skills": {}, "skills": {}}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate coverage or asset key"):
        coverage_module._json(path)


def test_deleted_skill_replacement_fails_coverage(covered_root: Path) -> None:
    """Removing an actual replacement cannot leave the coverage promise green."""
    path = (
        covered_root / "packages/shared/.apm/skills/kit-hexagonal-architecture/SKILL.md"
    )
    path.unlink()

    assert any("hexagonal-architecture" in item for item in check(covered_root))


def test_unknown_original_inventory_entry_fails_coverage(covered_root: Path) -> None:
    """The fixed baseline cannot change without a deliberate reviewed inventory update."""
    path = covered_root / ".agents/agentic-setup/coverage.json"
    coverage = json.loads(path.read_text())
    coverage["skills"]["new-unreviewed"] = "kit-test-first"
    path.write_text(json.dumps(coverage), encoding="utf-8")

    assert any("74" in item for item in check(covered_root))


def test_original_inventory_cannot_change_while_preserving_count(
    covered_root: Path,
) -> None:
    """An equal-size replacement is not the same original capability inventory."""
    path = covered_root / ".agents/agentic-setup/coverage.json"
    coverage = json.loads(path.read_text())
    target = coverage["skills"].pop("hexagonal-architecture")
    coverage["skills"]["invented-baseline-entry"] = target
    path.write_text(json.dumps(coverage), encoding="utf-8")

    assert any("baseline" in item for item in check(covered_root))


def test_editor_wrapper_cannot_call_an_unknown_task(covered_root: Path) -> None:
    """Workspace commands remain thin wrappers around the canonical task runner."""
    path = covered_root / ".vscode/tasks.json"
    tasks = json.loads(path.read_text())
    tasks["tasks"][0]["args"] = ["unknown-command"]
    path.write_text(json.dumps(tasks), encoding="utf-8")

    assert any("Taskfile" in item for item in check(covered_root))


def test_unreviewed_active_mcp_server_is_rejected(covered_root: Path) -> None:
    """An unreviewed server cannot be added to the active host manifests."""
    path = covered_root / ".mcp.json"
    config = json.loads(path.read_text())
    config["mcpServers"]["unapproved"] = {"type": "http", "url": "https://example.org"}
    path.write_text(json.dumps(config), encoding="utf-8")

    assert any("reviewed read-only set" in item for item in check(covered_root))


def test_active_github_server_cannot_be_widened(covered_root: Path) -> None:
    """The GitHub server stays limited to the reviewed read-only tools."""
    path = covered_root / ".vscode/mcp.json"
    config = json.loads(path.read_text())
    config["servers"]["github"]["headers"]["X-MCP-Readonly"] = "false"
    path.write_text(json.dumps(config), encoding="utf-8")

    assert any("reviewed read-only set" in item for item in check(covered_root))


def test_active_mcp_host_manifests_must_match(covered_root: Path) -> None:
    """Claude and VS Code expose the same reviewed server definitions."""
    path = covered_root / ".vscode/mcp.json"
    config = json.loads(path.read_text())
    config["servers"]["context7"]["url"] = "https://unreviewed.example/mcp"
    path.write_text(json.dumps(config), encoding="utf-8")

    assert any("reviewed read-only set" in item for item in check(covered_root))


def test_consumer_apm_policy_remains_deny_by_default(covered_root: Path) -> None:
    """Portable APM examples never authorize MCP without consumer review."""
    path = covered_root / ".apm/skills/kit-apm-adopt/assets/apm-policy.yml.template"
    policy = yaml.safe_load(path.read_text())
    policy["mcp"]["allow"] = ["github"]
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")

    assert any("deny MCP by default" in item for item in check(covered_root))


def test_broken_template_is_detected_without_rendering_it(covered_root: Path) -> None:
    """Resource files receive syntax validation even when their feature is inactive."""
    path = (
        covered_root
        / "packages/shared/.apm/skills/kit-editor/assets/settings.json.template"
    )
    path.write_text("{broken", encoding="utf-8")

    assert any("template" in item for item in check(covered_root))


def test_asset_index_cannot_escape_the_repository(covered_root: Path) -> None:
    """A copied resource reference must not reach outside the declared toolkit."""
    path = covered_root / ".agents/agentic-setup/assets.json"
    index = json.loads(path.read_text())
    index["assets"]["backend-blueprint"] = ["../outside.py"]
    path.write_text(json.dumps(index), encoding="utf-8")

    assert any("unsafe asset" in item for item in check(covered_root))


def test_no_mcp_can_be_declared_active_in_the_resource_inventory(
    covered_root: Path,
) -> None:
    """A template catalog cannot be used as silent permission to start a service."""
    path = (
        covered_root
        / "packages/shared/.apm/skills/kit-editor/assets/integration-catalog.json"
    )
    catalog = json.loads(path.read_text())
    catalog["default_active"] = ["github"]
    path.write_text(json.dumps(catalog), encoding="utf-8")

    assert any("implicit active" in item for item in check(covered_root))


def test_skill_identity_is_not_sufficient_resource_coverage(covered_root: Path) -> None:
    """A retained skill ID must not hide the loss of its usable resource depth."""
    path = covered_root / "packages/shared/.apm/skills/kit-change-plan/references"
    shutil.rmtree(path)

    assert any("reference" in item for item in check(covered_root))


def test_native_mcp_template_wrapper_is_not_interchangeable(
    covered_root: Path,
) -> None:
    path = (
        covered_root
        / "packages/shared/.apm/skills/kit-editor/assets/mcp-vscode.json.template"
    )
    content = json.loads(path.read_text())
    path.write_text(json.dumps({"mcpServers": content["servers"]}), encoding="utf-8")
    assert any("MCP template" in item for item in check(covered_root))


def test_native_mcp_templates_cannot_silently_disagree(covered_root: Path) -> None:
    path = (
        covered_root
        / "packages/shared/.apm/skills/kit-editor/assets/mcp-claude.json.template"
    )
    content = json.loads(path.read_text())
    content["mcpServers"]["github"]["url"] = "https://unreviewed.example/mcp"
    path.write_text(json.dumps(content), encoding="utf-8")
    assert any("MCP template" in item for item in check(covered_root))


def test_optional_mcp_template_matches_reviewed_public_endpoints(
    covered_root: Path,
) -> None:
    path = (
        covered_root
        / "packages/shared/.apm/skills/kit-editor/assets/mcp-optional.json.template"
    )
    config = json.loads(path.read_text())
    config["mcpServers"]["context7"]["url"] = "https://unreviewed.example/mcp"
    path.write_text(json.dumps(config), encoding="utf-8")

    assert any("optional MCP template" in item for item in check(covered_root))


def test_mcp_catalog_entry_cannot_lose_native_setup(covered_root: Path) -> None:
    path = (
        covered_root
        / "packages/shared/.apm/skills/kit-editor/assets/mcp-vscode.json.template"
    )
    content = json.loads(path.read_text())
    del content["servers"]["terraform"]
    path.write_text(json.dumps(content), encoding="utf-8")
    assert any("MCP template" in item for item in check(covered_root))


@pytest.mark.parametrize(
    ("template", "wrapper"),
    [
        ("mcp-vscode.json.template", "servers"),
        ("mcp-claude.json.template", "mcpServers"),
    ],
)
@pytest.mark.parametrize(
    ("server", "flag"),
    [
        ("azure", "--read-only"),
        ("terraform", "--toolsets=registry"),
        ("playwright", "--isolated"),
        ("playwright", "--headless"),
        ("chrome-devtools", "--isolated"),
        ("chrome-devtools", "--headless"),
        ("chrome-devtools", "--no-usage-statistics"),
        ("chrome-devtools", "--no-performance-crux"),
    ],
)
def test_mcp_templates_keep_their_hardening_flags(
    covered_root: Path, template: str, wrapper: str, server: str, flag: str
) -> None:
    """Read-only, isolation and telemetry opt-outs cannot be dropped from a template."""
    path = covered_root / "packages/shared/.apm/skills/kit-editor/assets" / template
    content = json.loads(path.read_text())
    content[wrapper][server]["args"].remove(flag)
    path.write_text(json.dumps(content), encoding="utf-8")

    assert any("invalid MCP template transport" in item for item in check(covered_root))


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("npx", ["--yes", "shadcn@REVIEWED_VERSION", "mcp"]),
        ("node", ["shadcn@REVIEWED_VERSION", "mcp"]),
        ("bunx", ["shadcn@REVIEWED_VERSION", "mcp"]),
        ("bunx", ["shadcn@REVIEWED_VERSION", "--bun", "mcp"]),
    ],
)
def test_native_mcp_templates_require_bun_runtime(
    covered_root: Path, command: str, args: list[str]
) -> None:
    for template, wrapper in (
        ("mcp-vscode.json.template", "servers"),
        ("mcp-claude.json.template", "mcpServers"),
    ):
        path = covered_root / "packages/shared/.apm/skills/kit-editor/assets" / template
        content = json.loads(path.read_text())
        content[wrapper]["shadcn"].update(command=command, args=args)
        path.write_text(json.dumps(content), encoding="utf-8")

    assert any("invalid MCP template transport" in item for item in check(covered_root))


def test_script_disposition_cannot_claim_nonexistent_implementation(
    covered_root: Path,
) -> None:
    path = covered_root / ".agents/agentic-setup/coverage.json"
    content = json.loads(path.read_text())
    content["scripts"]["quality-gate/scripts/run_gate.py"] = "invented-green-gate"
    path.write_text(json.dumps(content), encoding="utf-8")
    assert any("script disposition" in item for item in check(covered_root))


@pytest.mark.parametrize(
    ("command", "prompt", "expected"),
    [
        ("opsx/apply", "kit-not-a-prompt", "missing native prompt replacement"),
        ("invented/command", "kit-spec-apply", "names no original command"),
    ],
)
def test_prompt_file_mapping_must_name_real_commands_and_prompts(
    covered_root: Path, command: str, prompt: str, expected: str
) -> None:
    """A recorded native command replacement must exist and trace to an original."""
    path = covered_root / ".agents/agentic-setup/coverage.json"
    coverage = json.loads(path.read_text())
    coverage["prompt_files"][command] = prompt
    path.write_text(json.dumps(coverage), encoding="utf-8")

    assert any(expected in item for item in check(covered_root))


def test_deleted_prompt_breaks_its_recorded_replacement(covered_root: Path) -> None:
    """Removing a delivered prompt cannot leave its coverage promise green."""
    (covered_root / "packages/workflows/.apm/prompts/kit-spec-apply.prompt.md").unlink()

    assert any("kit-spec-apply" in item for item in check(covered_root))
