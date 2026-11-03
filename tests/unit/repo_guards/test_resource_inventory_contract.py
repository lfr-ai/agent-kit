"""Characterize the resource census independently of the live catalog."""

from pathlib import Path

from scripts.check_resources import inventory


def _write(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("resource", encoding="utf-8")


def test_inventory_returns_empty_without_canonical_skills(tmp_path: Path) -> None:
    _write(tmp_path, ".agents/skills/generated/SKILL.md")

    assert inventory(tmp_path) == []


def test_inventory_has_exact_keys_and_sorted_relative_paths(tmp_path: Path) -> None:
    home = ".apm/skills/zeta"
    for relative in (
        "SKILL.md",
        "references/z.md",
        "references/a.md",
        "assets/z.py",
        "assets/a.py.template",
        "tools/a.py",
        "assets/__pycache__/cached.py",
    ):
        _write(tmp_path, f"{home}/{relative}")
    _write(tmp_path, "packages/backend/.apm/skills/alpha/SKILL.md")
    _write(tmp_path, ".claude/skills/generated/SKILL.md")

    assert inventory(tmp_path) == [
        {
            "skill": "zeta",
            "path": f"{home}/SKILL.md",
            "references": ["references/a.md", "references/z.md"],
            "assets": ["assets/a.py.template", "assets/z.py"],
            "scripts": ["assets/z.py", "tools/a.py"],
        },
        {
            "skill": "alpha",
            "path": "packages/backend/.apm/skills/alpha/SKILL.md",
            "references": [],
            "assets": [],
            "scripts": [],
        },
    ]
