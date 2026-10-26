"""Check capability completeness, resource syntax, and editor task ownership."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path, PureWindowsPath
import sys

import yaml

from scripts.check_resources import check as check_resources

_ROOT = Path(__file__).resolve().parents[1]
_FRONTMATTER_FENCES = 2  # split into empty prefix, metadata, and body
_FIELDS = {
    "schema_version",
    "baseline",
    "skills",
    "exclusions",
    "instructions",
    "agents",
    "mcp",
    "hooks",
    "assets",
    "guard_migration",
    "prompts",
    "prompt_files",
    "scripts",
}
_BASELINE_COUNTS = {
    "skills": 74,
    "instructions": 31,
    "agents": 24,
    "prompts": 24,
    "mcp": 11,
    "hooks": 3,
    "assets": 5,
    "scripts": 22,
}
_BASELINE_KEYS_SHA256 = "0432d97293e5305af867e9751112b432f14766d79b35b3854ce0449959af4719"  # pragma: allowlist secret
_SCRIPT_DISPOSITIONS = {
    "superseded-by-apm-owned-drift",
    "consumer-owned",
    "operator-owned",
    "excluded-copier",
}
_ACTIVE_MCP_SERVERS = {
    "context7": {
        "type": "http",
        "url": "https://mcp.context7.com/mcp/oauth",
    },
    "github": {
        "type": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": {
            "X-MCP-Toolsets": "repos,issues,pull_requests,actions",
            "X-MCP-Readonly": "true",
            "X-MCP-Lockdown": "true",
        },
    },
    "microsoft-learn": {
        "type": "http",
        "url": "https://learn.microsoft.com/api/mcp",
    },
}


class _CoverageIssue(Enum):
    """Stable diagnostics for invalid inventory structure."""

    DUPLICATE_KEY = "duplicate coverage or asset key"


class _CoverageInputError(ValueError):
    """Report a known duplicate-key error from coverage JSON."""

    def __init__(self, issue: _CoverageIssue) -> None:
        self.issue = issue
        super().__init__(issue.value)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Prevent a later duplicate inventory entry hiding an earlier one.

    Raises:
        _CoverageInputError: An inventory key is repeated.
    """
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _CoverageInputError(_CoverageIssue.DUPLICATE_KEY)
        result[key] = value
    return result


def _json(path: Path) -> object:
    """Read exact JSON without silently accepting duplicate properties."""
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)


def _unsafe_asset(root: Path, relative: object) -> bool:
    """Reject non-string, absolute, drive, backslash, parent, missing, or escaping paths."""
    return (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or bool(PureWindowsPath(relative).drive)
        or "\\" in relative
        or ".." in Path(relative).parts
        or not (root / relative).is_file()
        or not (root / relative).resolve().is_relative_to(root.resolve())
    )


def _valid_mcp_template_server(name: str, server: dict[str, object]) -> bool:
    """Validate one inactive example or reviewed server definition."""
    if name in _ACTIVE_MCP_SERVERS:
        return server == _ACTIVE_MCP_SERVERS[name]
    if server.get("type") == "http":
        url = server.get("url")
        return (
            set(server) == {"type", "url"}
            and isinstance(url, str)
            and url.startswith("https://")
        )
    if server.get("type") != "stdio":
        return False
    command = server.get("command")
    args = server.get("args")
    return (
        set(server) == {"type", "command", "args"}
        and isinstance(command, str)
        and command in {"npx", "docker"}
        and isinstance(args, list)
        and bool(args)
        and all(isinstance(item, str) for item in args)
        and "REVIEWED_" in " ".join(args)
        and not any("latest" in item for item in args)
    )


def _mcp_template_servers(
    filename: str, raw: object, *, wrapper: str, names: set[str]
) -> tuple[dict[str, object] | None, list[str]]:
    """Validate one native template; return its servers and failures."""
    if (
        not isinstance(raw, dict)
        or set(raw) != {wrapper}
        or not isinstance(raw[wrapper], dict)
        or set(raw[wrapper]) != names
    ):
        return None, [f"{filename}: MCP template wrapper or inventory is invalid"]
    servers: dict[str, object] = raw[wrapper]
    failures: list[str] = []
    for name, server in servers.items():
        if not isinstance(server, dict):
            failures.append(f"{filename}: invalid MCP template server {name}")
        elif not _valid_mcp_template_server(name, server):
            failures.append(f"{filename}: invalid MCP template transport for {name}")
    return servers, failures


def _mcp_templates(root: Path, names: set[str]) -> list[str]:
    """Compare complete inactive native inventories without claiming tool safety."""
    failures: list[str] = []
    home = root / "packages/shared/.apm/skills/kit-editor/assets"
    definitions: list[dict[str, object]] = []
    for filename, wrapper in (
        ("mcp-vscode.json.template", "servers"),
        ("mcp-claude.json.template", "mcpServers"),
    ):
        servers, template_failures = _mcp_template_servers(
            filename, _json(home / filename), wrapper=wrapper, names=names
        )
        failures.extend(template_failures)
        if servers is not None:
            definitions.append(servers)
    if any(item != definitions[0] for item in definitions):
        failures.append("native MCP template server definitions disagree")
    optional = _json(home / "mcp-optional.json.template")
    optional_servers = {
        name: _ACTIVE_MCP_SERVERS[name] for name in ("context7", "microsoft-learn")
    }
    if optional != {"mcpServers": optional_servers}:
        failures.append("optional MCP template definitions are invalid")
    return failures


def _active_mcp_manifests(root: Path) -> list[str]:
    """Require matching host manifests with only the reviewed server set."""
    failures: list[str] = []
    for relative, wrapper in (
        (".mcp.json", "mcpServers"),
        (".vscode/mcp.json", "servers"),
    ):
        if _json(root / relative) != {wrapper: _ACTIVE_MCP_SERVERS}:
            failures.append(
                f"{relative}: active MCP servers must match the reviewed read-only set"
            )
    return failures


@dataclass(frozen=True, kw_only=True, slots=True)
class _Bundles:
    """Capability identities discovered in every authored bundle."""

    skills: dict[str, Path]
    instructions: set[str]
    roles: set[str]
    prompts: set[str]


def _baseline_sections(
    raw: dict[str, object],
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Return baseline sections, or failures when any count is wrong."""
    sections: dict[str, dict[str, object]] = {}
    failures: list[str] = []
    for name, count in _BASELINE_COUNTS.items():
        section = raw.get(name)
        if isinstance(section, dict) and len(section) == count:
            sections[name] = section
        else:
            failures.append(
                f"coverage baseline {name} must contain {count} unique entries"
            )
    return sections, failures


def _identity_failures(
    sections: dict[str, dict[str, object]], exclusions: object
) -> list[str]:
    """Pin baseline identities and require exclusions for unmigrated skills."""
    baseline = {name: sorted(section) for name, section in sections.items()}
    digest = hashlib.sha256(
        json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if digest != _BASELINE_KEYS_SHA256:
        return [
            "coverage baseline identities differ from the source-verified inventory"
        ]
    unmigrated = {name for name, value in sections["skills"].items() if value is None}
    if not isinstance(exclusions, dict) or set(exclusions) != unmigrated:
        return [
            "coverage exclusions must match exactly the deliberately unmigrated skills"
        ]
    return []


def _asset_index(root: Path) -> dict[str, object] | None:
    """Return the asset categories, or None when the index is malformed."""
    asset_index = _json(root / ".agents/agentic-setup/assets.json")
    if (
        not isinstance(asset_index, dict)
        or set(asset_index) != {"schema_version", "assets"}
        or not isinstance(asset_index["assets"], dict)
    ):
        return None
    return asset_index["assets"]


def _asset_failures(
    root: Path, assets: dict[str, object], baseline: dict[str, object]
) -> list[str]:
    """Require matching categories and safe, present asset references."""
    failures: list[str] = []
    if set(assets) != set(baseline):
        failures.append("asset index and baseline asset categories differ")
    for category, paths in assets.items():
        if not isinstance(paths, list) or not paths:
            failures.append(f"{category}: asset references must be nonempty")
            continue
        failures.extend(
            f"{category}: missing or unsafe asset reference"
            for relative in paths
            if _unsafe_asset(root, relative)
        )
    return failures


def _collect_skills(root: Path, bundle: Path, skills: dict[str, Path]) -> list[str]:
    """Record each bundle skill identity and report unreadable metadata."""
    failures: list[str] = []
    for path in bundle.rglob("SKILL.md"):
        parts = path.read_text(encoding="utf-8").split("---", _FRONTMATTER_FENCES)
        if len(parts) != _FRONTMATTER_FENCES + 1:
            failures.append(f"{path.relative_to(root)}: invalid skill metadata")
            continue
        metadata = yaml.safe_load(parts[1])
        if not isinstance(metadata, dict) or not isinstance(metadata.get("name"), str):
            failures.append(f"{path.relative_to(root)}: missing skill identity")
            continue
        skills[metadata["name"]] = path
    return failures


def _collect_roles(root: Path, bundle: Path, roles: set[str]) -> list[str]:
    """Record native role identities and report invalid or duplicate roles."""
    failures: list[str] = []
    for path in bundle.rglob("agents.json"):
        asset = _json(path)
        if not isinstance(asset, dict) or not isinstance(asset.get("roles"), list):
            failures.append(f"{path.relative_to(root)}: invalid native role asset")
            continue
        for role in asset["roles"]:
            if not isinstance(role, dict) or not isinstance(role.get("id"), str):
                continue
            if role["id"] in roles:
                failures.append(f"duplicate role {role['id']}")
            roles.add(role["id"])
    return failures


def _parse_template(path: Path) -> None:
    """Parse a source template with the parser for its rendered suffix."""
    name = path.name.removesuffix(".template")
    if name.endswith(".json"):
        _json(path)
    elif name.endswith((".yaml", ".yml")):
        yaml.safe_load(path.read_text(encoding="utf-8"))
    elif name.endswith(".py"):
        ast.parse(path.read_text(encoding="utf-8"))


def _template_failures(root: Path, bundle: Path) -> list[str]:
    """Report source templates whose rendered syntax cannot be parsed."""
    failures: list[str] = []
    for path in bundle.rglob("*.template"):
        try:
            _parse_template(path)
        except (ValueError, SyntaxError, yaml.YAMLError):
            failures.append(f"{path.relative_to(root)}: invalid source template syntax")
    return failures


def _scan_bundles(root: Path) -> tuple[_Bundles, list[str]]:
    """Collect capability identities from the root and every package bundle."""
    bundles = _Bundles(skills={}, instructions=set(), roles=set(), prompts=set())
    failures: list[str] = []
    for bundle in [root / ".apm", *sorted((root / "packages").glob("*/.apm"))]:
        failures.extend(_collect_skills(root, bundle, bundles.skills))
        bundles.instructions.update(
            path.name.removesuffix(".instructions.md")
            for path in bundle.rglob("*.instructions.md")
        )
        bundles.prompts.update(
            path.name.removesuffix(".prompt.md")
            for path in bundle.glob("prompts/*.prompt.md")
        )
        failures.extend(_collect_roles(root, bundle, bundles.roles))
        failures.extend(_template_failures(root, bundle))
    return bundles, failures


def _skill_replacement_failures(
    skills: dict[str, object], exclusions: dict[str, object], available: set[str]
) -> list[str]:
    """Require a replacement or an exclusion rationale for every skill."""
    failures: list[str] = []
    for name, target in skills.items():
        if target is None:
            if not exclusions.get(name):
                failures.append(f"missing rationale for excluded {name}")
        elif not isinstance(target, str) or target not in available:
            failures.append(f"missing skill replacement {name}: {target}")
    return failures


def _prompt_file_failures(
    prompt_files: object, commands: dict[str, object], prompts: set[str]
) -> list[str]:
    """Require native prompt replacements for recorded original commands."""
    if not isinstance(prompt_files, dict):
        return ["prompt_files must map original commands to prompts"]
    failures: list[str] = []
    for name, target in prompt_files.items():
        if name not in commands:
            failures.append(f"prompt file mapping names no original command: {name}")
        elif not isinstance(target, str) or target not in prompts:
            failures.append(f"missing native prompt replacement {name}: {target}")
    return failures


def _script_failures(root: Path, scripts: dict[str, object]) -> list[str]:
    """Require a known disposition or a safe Python replacement per script."""
    return [
        f"missing or unsafe script disposition {name}: {target}"
        for name, target in scripts.items()
        if not (isinstance(target, str) and target in _SCRIPT_DISPOSITIONS)
        and (
            _unsafe_asset(root, target)
            or not isinstance(target, str)
            or not target.endswith(".py")
        )
    ]


def _replacement_failures(
    root: Path,
    sections: dict[str, dict[str, object]],
    *,
    exclusions: dict[str, object],
    prompt_files: object,
    bundles: _Bundles,
) -> list[str]:
    """Check every recorded replacement against the discovered bundles."""
    failures = _skill_replacement_failures(
        sections["skills"], exclusions, set(bundles.skills)
    )
    failures.extend(
        f"missing instruction replacement {name}: {target}"
        for name, target in sections["instructions"].items()
        if not isinstance(target, str) or target not in bundles.instructions
    )
    failures.extend(
        f"missing command procedure replacement {name}: {target}"
        for name, target in sections["prompts"].items()
        if not isinstance(target, str) or target not in bundles.skills
    )
    failures.extend(
        _prompt_file_failures(prompt_files, sections["prompts"], bundles.prompts)
    )
    failures.extend(
        f"missing native role replacement {name}: {target}"
        for name, target in sections["agents"].items()
        if not isinstance(target, str) or target not in bundles.roles
    )
    failures.extend(_script_failures(root, sections["scripts"]))
    return failures


def _integration_failures(
    root: Path, sections: dict[str, dict[str, object]]
) -> list[str]:
    """Check integration, MCP template, and hook migration inventories."""
    failures: list[str] = []
    integration = _json(
        root / "packages/shared/.apm/skills/kit-editor/assets/integration-catalog.json"
    )
    if (
        not isinstance(integration, dict)
        or integration.get("default_active") != []
        or not isinstance(integration.get("integrations"), dict)
        or set(integration["integrations"]) != set(sections["mcp"])
    ):
        failures.append(
            "integration source inventory must match the baseline with no implicit active servers"
        )
    failures.extend(_mcp_templates(root, set(sections["mcp"])))
    if set(sections["hooks"]) != {
        "session-context",
        "tool-guardian",
        "license-guardian",
    }:
        failures.append("hook migration inventory is incomplete")
    return failures


def _live_inventory(source_root: Path) -> dict[str, set[str]]:
    """Collect capability identities from the original source checkout."""
    skills_root = source_root / ".agents/skills"
    prompts_root = source_root / ".github/prompts"
    return {
        "skills": {
            path.parent.relative_to(skills_root).as_posix()
            for path in skills_root.rglob("SKILL.md")
        },
        "instructions": {
            path.name.removesuffix(".instructions.md")
            for path in (source_root / ".github/instructions").glob("*.instructions.md")
        },
        "agents": {
            path.name.removesuffix(".agent.md")
            for path in (source_root / ".github/agents").rglob("*.agent.md")
        },
        "prompts": {
            path.relative_to(prompts_root).as_posix().removesuffix(".prompt.md")
            for path in prompts_root.rglob("*.prompt.md")
        },
        "scripts": {
            path.relative_to(skills_root).as_posix()
            for path in skills_root.rglob("scripts/*.py")
        },
    }


def _live_source_failures(
    source_root: Path | None, sections: dict[str, dict[str, object]]
) -> list[str]:
    """Compare an optional original checkout with the recorded inventory."""
    if source_root is None:
        return []
    failures: list[str] = []
    for name, actual in _live_inventory(source_root).items():
        recorded = set(sections[name])
        if actual == recorded:
            continue
        failures.append(
            f"live source {name} differs from the recorded coverage inventory"
        )
        if missing := actual - recorded:
            failures.append(f"unrecorded {name}: {', '.join(sorted(missing))}")
        if stale := recorded - actual:
            failures.append(f"stale {name}: {', '.join(sorted(stale))}")
    return failures


def _editor_task_entry_failures(
    task: object, definitions: dict[str, object]
) -> list[str]:
    """Require one editor task to be a thin wrapper over a Taskfile target."""
    if (
        not isinstance(task, dict)
        or task.get("type") != "process"
        or task.get("command") != "task"
    ):
        return ["editor task is not a thin canonical Task wrapper"]
    failures: list[str] = []
    args = task.get("args")
    if (
        not isinstance(args, list)
        or len(args) != 1
        or not isinstance(args[0], str)
        or args[0] not in definitions
    ):
        failures.append("editor task references an unavailable Taskfile target")
    if task.get("options") != {"cwd": "${workspaceFolder}"}:
        failures.append("editor task must target the active workspace directory")
    return failures


def _editor_task_failures(root: Path) -> list[str]:
    """Require editor tasks to delegate to canonical Taskfile targets."""
    tasks: object = _json(root / ".vscode/tasks.json")
    taskfile = yaml.safe_load((root / "Taskfile.yml").read_text(encoding="utf-8"))
    if not isinstance(tasks, dict) or not isinstance(taskfile, dict):
        return ["editor/task definitions cannot be parsed"]
    definitions = taskfile.get("tasks", {})
    if not isinstance(definitions, dict):
        definitions = {}
    task_entries = tasks.get("tasks", [])
    failures: list[str] = []
    if not isinstance(task_entries, list):
        failures.append("editor/task definitions cannot be parsed")
        task_entries = []
    for task in task_entries:
        failures.extend(_editor_task_entry_failures(task, definitions))
    return failures


def _policy_failures(root: Path) -> list[str]:
    """Require the consumer APM policy template to deny MCP by default."""
    policy_path = root / ".apm/skills/kit-apm-adopt/assets/apm-policy.yml.template"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    mcp_policy = policy.get("mcp") if isinstance(policy, dict) else None
    if (
        not isinstance(mcp_policy, dict)
        or mcp_policy.get("allow") != []
        or mcp_policy.get("self_defined") != "deny"
        or mcp_policy.get("trust_transitive") is not False
    ):
        return ["consumer APM policy template must deny MCP by default"]
    return []


def check(root: Path, *, source_root: Path | None = None) -> list[str]:
    """Verify every promised replacement exists and inactive sources remain valid."""
    raw = _json(root / ".agents/agentic-setup/coverage.json")
    if (
        not isinstance(raw, dict)
        or set(raw) != _FIELDS
        or type(raw.get("schema_version")) is not int
        or raw.get("schema_version") != 1
    ):
        return ["coverage schema is invalid"]
    sections, failures = _baseline_sections(raw)
    if failures:
        return failures
    exclusions = raw["exclusions"]
    identity_failures = _identity_failures(sections, exclusions)
    if identity_failures:
        return identity_failures
    assets = _asset_index(root)
    if assets is None:
        return ["asset index is invalid"]
    failures = _asset_failures(root, assets, sections["assets"])
    bundles, bundle_failures = _scan_bundles(root)
    failures.extend(bundle_failures)
    failures.extend(
        _replacement_failures(
            root,
            sections,
            exclusions=exclusions,
            prompt_files=raw["prompt_files"],
            bundles=bundles,
        )
    )
    failures.extend(_integration_failures(root, sections))
    failures.extend(_live_source_failures(source_root, sections))
    failures.extend(_editor_task_failures(root))
    failures.extend(_active_mcp_manifests(root))
    failures.extend(_policy_failures(root))
    failures.extend(check_resources(root))
    return failures


def main() -> int:
    """Print coverage failures without modifying runtime projections."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        failures = check(_ROOT, source_root=args.source_root)
    except (OSError, ValueError, yaml.YAMLError):
        print("Capability coverage inputs cannot be parsed.", file=sys.stderr)
        return 1
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print(
        "Original capability inventory, replacements, templates, and editor contracts passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
