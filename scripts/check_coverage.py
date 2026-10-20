"""Check capability completeness, resource syntax, and editor task ownership."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from enum import Enum
from pathlib import Path, PureWindowsPath

import yaml

from scripts.check_resources import check as check_resources

_ROOT = Path(__file__).resolve().parents[1]
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


class _CoverageIssue(Enum):
    """Stable diagnostics for invalid inventory structure."""

    DUPLICATE_KEY = "duplicate coverage or asset key"


class _CoverageInputError(ValueError):
    """Report a known duplicate-key error from coverage JSON."""

    def __init__(self, issue: _CoverageIssue) -> None:
        self.issue = issue
        super().__init__(issue.value)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Prevent a later duplicate inventory entry hiding an earlier one."""
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


def _mcp_templates(root: Path, names: set[str]) -> list[str]:
    """Compare complete inactive native inventories without claiming tool safety."""
    failures: list[str] = []
    home = root / "packages/shared/.apm/skills/kit-editor/assets"
    definitions: list[dict[str, object]] = []
    for filename, wrapper in (
        ("mcp-vscode.json.template", "servers"),
        ("mcp-claude.json.template", "mcpServers"),
    ):
        raw = _json(home / filename)
        if (
            not isinstance(raw, dict)
            or set(raw) != {wrapper}
            or not isinstance(raw[wrapper], dict)
            or set(raw[wrapper]) != names
        ):
            failures.append(f"{filename}: MCP template wrapper or inventory is invalid")
            continue
        definitions.append(raw[wrapper])
        for name, server in raw[wrapper].items():
            if not isinstance(server, dict):
                failures.append(f"{filename}: invalid MCP template server {name}")
                continue
            if server.get("type") == "http":
                valid = (
                    set(server) == {"type", "url"}
                    and isinstance(server["url"], str)
                    and server["url"].startswith("https://")
                )
            elif server.get("type") == "stdio":
                valid = (
                    set(server) == {"type", "command", "args"}
                    and server.get("command") in {"npx", "docker"}
                    and isinstance(server.get("args"), list)
                    and bool(server["args"])
                    and all(isinstance(item, str) for item in server["args"])
                    and "REVIEWED_" in " ".join(server["args"])
                    and not any("latest" in item for item in server["args"])
                )
            else:
                valid = False
            if not valid:
                failures.append(
                    f"{filename}: invalid MCP template transport for {name}"
                )
    if len(definitions) == 2 and definitions[0] != definitions[1]:  # noqa: PLR2004 - two supported native wrappers
        failures.append("native MCP template server definitions disagree")
    return failures


def check(root: Path, *, source_root: Path | None = None) -> list[str]:  # noqa: C901, PLR0912, PLR0915 - pre-existing; split per inventory section
    """Verify every promised replacement exists and inactive sources remain valid."""
    failures: list[str] = []
    raw = _json(root / ".agents/agentic-setup/coverage.json")
    if (
        not isinstance(raw, dict)
        or set(raw) != _FIELDS
        or type(raw.get("schema_version")) is not int
        or raw.get("schema_version") != 1
    ):
        return ["coverage schema is invalid"]
    for name, count in _BASELINE_COUNTS.items():
        if not isinstance(raw.get(name), dict) or len(raw[name]) != count:
            failures.append(
                f"coverage baseline {name} must contain {count} unique entries"
            )
    if failures:
        return failures
    baseline = {name: sorted(raw[name]) for name in _BASELINE_COUNTS}
    digest = hashlib.sha256(
        json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if digest != _BASELINE_KEYS_SHA256:
        return [
            "coverage baseline identities differ from the source-verified inventory"
        ]
    if not isinstance(raw["exclusions"], dict) or set(raw["exclusions"]) != {
        name for name, value in raw["skills"].items() if value is None
    }:
        return [
            "coverage exclusions must match exactly the deliberately unmigrated skills"
        ]
    asset_index = _json(root / ".agents/agentic-setup/assets.json")
    if (
        not isinstance(asset_index, dict)
        or set(asset_index) != {"schema_version", "assets"}
        or not isinstance(asset_index["assets"], dict)
    ):
        return ["asset index is invalid"]
    if set(asset_index["assets"]) != set(raw["assets"]):
        failures.append("asset index and baseline asset categories differ")
    for category, paths in asset_index["assets"].items():
        if not isinstance(paths, list) or not paths:
            failures.append(f"{category}: asset references must be nonempty")
            continue
        failures.extend(
            f"{category}: missing or unsafe asset reference"
            for relative in paths
            if _unsafe_asset(root, relative)
        )
    skills: dict[str, Path] = {}
    instructions: set[str] = set()
    roles: set[str] = set()
    prompts: set[str] = set()
    bundle_roots = [root / ".apm", *sorted((root / "packages").glob("*/.apm"))]
    for bundle in bundle_roots:
        for path in bundle.rglob("SKILL.md"):
            parts = path.read_text(encoding="utf-8").split("---", 2)
            if len(parts) != 3:  # noqa: PLR2004 - empty prefix, frontmatter, body
                failures.append(f"{path.relative_to(root)}: invalid skill metadata")
                continue
            metadata = yaml.safe_load(parts[1])
            if not isinstance(metadata, dict) or not isinstance(
                metadata.get("name"), str
            ):
                failures.append(f"{path.relative_to(root)}: missing skill identity")
                continue
            skills[metadata["name"]] = path
        instructions.update(
            path.name.removesuffix(".instructions.md")
            for path in bundle.rglob("*.instructions.md")
        )
        prompts.update(
            path.name.removesuffix(".prompt.md")
            for path in bundle.glob("prompts/*.prompt.md")
        )
        for path in bundle.rglob("agents.json"):
            asset = _json(path)
            if not isinstance(asset, dict) or not isinstance(asset.get("roles"), list):
                failures.append(f"{path.relative_to(root)}: invalid native role asset")
                continue
            for role in asset["roles"]:
                if isinstance(role, dict) and isinstance(role.get("id"), str):
                    if role["id"] in roles:
                        failures.append(f"duplicate role {role['id']}")
                    roles.add(role["id"])
        for path in bundle.rglob("*.template"):
            name = path.name.removesuffix(".template")
            try:
                if name.endswith(".json"):
                    _json(path)
                elif name.endswith((".yaml", ".yml")):
                    yaml.safe_load(path.read_text(encoding="utf-8"))
                elif name.endswith(".py"):
                    ast.parse(path.read_text(encoding="utf-8"))
            except (ValueError, SyntaxError, yaml.YAMLError):
                failures.append(
                    f"{path.relative_to(root)}: invalid source template syntax"
                )
    for name, target in raw.get("skills", {}).items():
        if target is None:
            if not raw.get("exclusions", {}).get(name):
                failures.append(f"missing rationale for excluded {name}")
        elif not isinstance(target, str) or target not in skills:
            failures.append(f"missing skill replacement {name}: {target}")
    for name, target in raw.get("instructions", {}).items():
        if not isinstance(target, str) or target not in instructions:
            failures.append(f"missing instruction replacement {name}: {target}")
    for name, target in raw["prompts"].items():
        if not isinstance(target, str) or target not in skills:
            failures.append(f"missing command procedure replacement {name}: {target}")
    prompt_files = raw["prompt_files"]
    if not isinstance(prompt_files, dict):
        failures.append("prompt_files must map original commands to prompts")
        prompt_files = {}
    for name, target in prompt_files.items():
        if name not in raw["prompts"]:
            failures.append(f"prompt file mapping names no original command: {name}")
        elif not isinstance(target, str) or target not in prompts:
            failures.append(f"missing native prompt replacement {name}: {target}")
    for name, target in raw.get("agents", {}).items():
        if not isinstance(target, str) or target not in roles:
            failures.append(f"missing native role replacement {name}: {target}")
    for name, target in raw["scripts"].items():
        if isinstance(target, str) and target in _SCRIPT_DISPOSITIONS:
            continue
        if (
            _unsafe_asset(root, target)
            or not isinstance(target, str)
            or not target.endswith(".py")
        ):
            failures.append(f"missing or unsafe script disposition {name}: {target}")
    integration = _json(
        root / "packages/shared/.apm/skills/kit-editor/assets/integration-catalog.json"
    )
    if (
        not isinstance(integration, dict)
        or integration.get("default_active") != []
        or not isinstance(integration.get("integrations"), dict)
        or set(integration["integrations"]) != set(raw["mcp"])
    ):
        failures.append(
            "integration source inventory must match the baseline with no implicit active servers"
        )
    failures.extend(_mcp_templates(root, set(raw["mcp"])))
    if not isinstance(raw["hooks"], dict) or set(raw["hooks"]) != {
        "session-context",
        "tool-guardian",
        "license-guardian",
    }:
        failures.append("hook migration inventory is incomplete")
    if source_root is not None:
        original_skills = {
            path.parent.relative_to(source_root / ".agents/skills").as_posix()
            for path in (source_root / ".agents/skills").rglob("SKILL.md")
        }
        original_instructions = {
            path.name.removesuffix(".instructions.md")
            for path in (source_root / ".github/instructions").glob("*.instructions.md")
        }
        original_agents = {
            path.name.removesuffix(".agent.md")
            for path in (source_root / ".github/agents").rglob("*.agent.md")
        }
        original_prompts = {
            path.relative_to(source_root / ".github/prompts")
            .as_posix()
            .removesuffix(".prompt.md")
            for path in (source_root / ".github/prompts").rglob("*.prompt.md")
        }
        original_scripts = {
            path.relative_to(source_root / ".agents/skills").as_posix()
            for path in (source_root / ".agents/skills").rglob("scripts/*.py")
        }
        for name, actual in (
            ("skills", original_skills),
            ("instructions", original_instructions),
            ("agents", original_agents),
            ("prompts", original_prompts),
            ("scripts", original_scripts),
        ):
            if actual != set(raw.get(name, {})):
                failures.append(
                    f"live source {name} differs from the recorded coverage inventory"
                )
                missing = actual - set(raw.get(name, {}))
                stale = set(raw.get(name, {})) - actual
                if missing:
                    failures.append(f"unrecorded {name}: {', '.join(sorted(missing))}")
                if stale:
                    failures.append(f"stale {name}: {', '.join(sorted(stale))}")
    tasks: object = _json(root / ".vscode/tasks.json")
    taskfile = yaml.safe_load((root / "Taskfile.yml").read_text(encoding="utf-8"))
    if isinstance(tasks, dict) and isinstance(taskfile, dict):
        definitions = taskfile.get("tasks", {})
        if not isinstance(definitions, dict):
            definitions = {}
        task_entries = tasks.get("tasks", [])
        if not isinstance(task_entries, list):
            failures.append("editor/task definitions cannot be parsed")
            task_entries = []
        for task in task_entries:
            if (
                not isinstance(task, dict)
                or task.get("type") != "process"
                or task.get("command") != "task"
            ):
                failures.append("editor task is not a thin canonical Task wrapper")
                continue
            args = task.get("args")
            if (
                not isinstance(args, list)
                or len(args) != 1
                or not isinstance(args[0], str)
                or args[0] not in definitions
            ):
                failures.append("editor task references an unavailable Taskfile target")
            if task.get("options") != {"cwd": "${workspaceFolder}"}:
                failures.append(
                    "editor task must target the active workspace directory"
                )
    else:
        failures.append("editor/task definitions cannot be parsed")
    mcp: object = _json(root / ".mcp.json")
    if mcp != {"mcpServers": {}}:
        failures.append(
            "active MCP integrations require an explicit adoption/policy review"
        )
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
