"""Reject stray root artifacts and broken local documentation links."""

from collections.abc import Iterator
import os
from pathlib import Path
import sys
from urllib.parse import unquote

from agent_kit.core.text import markdown_link_targets
from agent_kit.infrastructure.catalog import ROOT_DOCUMENTS

_ROOT = Path(__file__).resolve().parent.parent.parent
_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".tox",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    "node_modules",
    "htmlcov",
    "build",
    "dist",
    "apm_modules",
    "__pycache__",
}
_LLMS_INDEX = "llms.txt"
_REQUIRED = (
    "AGENTS.md",
    "CLAUDE.md",
    "PROJECT.md",
    "OWNERSHIP.md",
    _LLMS_INDEX,
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
)
_ROOT_CONFIGURATION_FILES = frozenset(
    {
        ".cz.toml",
        ".jscpd.json",
        ".mcp.json",
        "bunfig.toml",
        "catalog.json",
        "cspell.json",
        "license-allowlist.json",
        "lychee.toml",
        "package.json",
        "pyproject.toml",
        "ruff.toml",
        "ty.toml",
    }
)
_ROOT_ARTIFACT_SUFFIXES = frozenset(
    {".html", ".htm", ".rst", ".txt", ".md", ".mdx", ".json", ".xml", ".toml"}
)


def _documentation_paths(root: Path) -> Iterator[Path]:
    """Find source documents without traversing excluded or linked directories.

    Markdown and ``llms.txt`` paths come in filesystem traversal order, with
    Markdown directly under ``root`` restricted to approved filenames. Paths keep
    the relative or absolute form of ``root``; linked files are included so the
    caller can report them.
    """
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if name not in _EXCLUDED_PARTS and not (Path(current) / name).is_symlink()
        ]
        for name in files:
            in_scope = Path(current) != root or name in ROOT_DOCUMENTS
            if name == _LLMS_INDEX or (name.endswith(".md") and in_scope):
                yield Path(current) / name


def check(root: Path) -> list[str]:
    """Report stray root artifacts, missing entries and unresolved local links."""
    failures = [
        f"missing entry: {name}" for name in _REQUIRED if not (root / name).is_file()
    ]
    failures.extend(
        f"unexpected root artifact: {path.name}; keep research in temporary storage "
        "and durable documentation under docs/"
        for path in sorted(root.iterdir())
        if path.suffix.lower() in _ROOT_ARTIFACT_SUFFIXES
        and path.name not in ROOT_DOCUMENTS | _ROOT_CONFIGURATION_FILES
        and (not path.is_dir() or path.is_symlink())
    )
    for path in _documentation_paths(root):
        if path.is_symlink():
            failures.append(f"{path.relative_to(root)}: symbolic-link document")
        elif ".template." not in path.name:
            failures.extend(
                f"{path.relative_to(root)}: missing link {target}"
                for target in _local_targets(path.read_text(encoding="utf-8"))
                if not (path.parent / target).exists()
            )
    return failures


def _local_targets(text: str) -> Iterator[str]:
    """Yield decoded local link targets, skipping web, mail and anchor links."""
    for target in markdown_link_targets(text):
        if not target.startswith(("https://", "http://", "mailto:", "#")):
            yield unquote(target.partition("#")[0])


def main() -> int:
    """Print actionable link failures and an exit status."""
    failures = check(_ROOT)
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write("Documentation entries and local links passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
