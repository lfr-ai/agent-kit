"""Check authored skill resource depth without executing consumer resources."""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

_ROOT = Path(__file__).resolve().parents[1]
_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _skills(root: Path) -> list[Path]:
    """Find canonical skills, never generated runtime copies."""
    return sorted(
        [
            *(root / ".apm/skills").glob("*/SKILL.md"),
            *(root / "packages").glob("*/.apm/skills/*/SKILL.md"),
        ]
    )


def _files(directory: Path) -> list[Path]:
    """List authored resources without counting bytecode as capability content."""
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def inventory(root: Path) -> list[dict[str, str | list[str]]]:
    """Report real resource paths for each skill, not baseline mapping ratios."""
    records: list[dict[str, str | list[str]]] = []
    for skill in _skills(root):
        home = skill.parent
        resources = _files(home)
        records.append(
            {
                "skill": home.name,
                "path": skill.relative_to(root).as_posix(),
                "references": [
                    path.relative_to(home).as_posix()
                    for path in resources
                    if path.is_relative_to(home / "references")
                ],
                "assets": [
                    path.relative_to(home).as_posix()
                    for path in resources
                    if path.is_relative_to(home / "assets")
                ],
                "scripts": [
                    path.relative_to(home).as_posix()
                    for path in resources
                    if path.suffix == ".py"
                ],
            }
        )
    return records


def _reachable(skill: Path) -> set[Path]:
    """Follow local resource links transitively inside this skill's boundary."""
    home = skill.parent.resolve()
    pending = [skill.resolve()]
    visited: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        if path.suffix != ".md":
            continue
        for match in _LINK.findall(path.read_text(encoding="utf-8")):
            target = match.strip().strip("<>").split(" ", 1)[0]
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            resolved = (path.parent / unquote(target.partition("#")[0])).resolve()
            if resolved.is_relative_to(home) and resolved.is_file():
                pending.append(resolved)
    return visited


def _python_failures(resources: list[Path], root: Path) -> list[str]:
    """Parse executable resources without importing or running them."""
    failures: list[str] = []
    for path in resources:
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError:
                failures.append(f"{path.relative_to(root)}: invalid Python syntax")
    return failures


def check(root: Path) -> list[str]:
    """Reject checklist-only, undiscoverable, escaping or invalid Python resources."""
    failures: list[str] = []
    skills = _skills(root)
    if not skills:
        return ["no canonical skills found"]
    for skill in skills:
        home = skill.parent
        if not home.resolve().is_relative_to(root.resolve()):
            failures.append(f"{home.name}: unsafe resource path")
            continue
        resources = _files(home)
        if any(
            path.is_symlink()
            or path.is_junction()
            or not path.resolve().is_relative_to(home.resolve())
            for path in [home, *home.rglob("*")]
        ):
            failures.append(f"{home.name}: unsafe resource path")
            continue
        reached = _reachable(skill)
        for category, label in (("references", "reference"), ("assets", "asset")):
            candidates = [
                path
                for path in resources
                if path.is_relative_to(home / category)
                and path.stat().st_size
                and (category != "references" or path.suffix == ".md")
            ]
            if not candidates:
                failures.append(f"{home.name}: missing nonempty {label}")
            elif not any(path.resolve() in reached for path in candidates):
                failures.append(f"{home.name}: no reachable {label} from SKILL.md")
        failures.extend(_python_failures(resources, root))
    return failures


def main() -> int:
    """Print resource inventory and explicit failures without changing source."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        failures = check(args.root)
        records = inventory(args.root)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Resource inputs cannot be read: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps({"valid": not failures, "failures": failures, "skills": records})
        )
    else:
        for failure in failures:
            print(failure, file=sys.stderr)
        if not failures:
            print(
                f"Linked references, assets and Python syntax passed for {len(records)} skills."
            )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
