"""Check source documentation links without fetching external resources."""

from collections.abc import Iterator
import os
from pathlib import Path
import sys
from urllib.parse import unquote

from agent_kit.core.text import markdown_link_targets

_ROOT = Path(__file__).resolve().parents[1]
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
_REQUIRED = (
    "AGENTS.md",
    "CLAUDE.md",
    "PROJECT.md",
    "projects.md",
    "llms.txt",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
)
_ROOT_DOCUMENTS = frozenset(
    {
        *_REQUIRED,
        "CHANGELOG.md",
        "CODE_OF_CONDUCT.md",
        "GOVERNANCE.md",
        "SUPPORT.md",
    }
)


def _documentation_paths(root: Path) -> Iterator[Path]:
    """Find actual source documents without traversing generated directories."""
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if name not in _EXCLUDED_PARTS and not (Path(current) / name).is_symlink()
        ]
        for name in files:
            if (name.endswith(".md") or name == "llms.txt") and (
                Path(current) != root or name in _ROOT_DOCUMENTS or name == "llms.txt"
            ):
                yield Path(current) / name


def check(root: Path) -> list[str]:
    """Find missing entry files or unresolved local links."""
    failures = [
        f"missing entry: {name}" for name in _REQUIRED if not (root / name).is_file()
    ]
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
