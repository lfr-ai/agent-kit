"""Check toolkit Python conventions and docstrings in capability sources."""

from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Final

_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER: Final[Path] = (
    _ROOT / "packages/backend/.apm/skills/kit-python-service/assets/check_python.py"
)
_TEMPLATES_FLAG = "--templates"
_TEMPLATE_SUFFIX = ".template"
_STRICT = ("--magic-numbers", "--docstrings")
_PORTABLE_ROOTS = (".apm", "packages")
# Tests keep literal expectations; every other root names its values and documents.
# Portable roots additionally check their ``.template`` sources with template rules.
_SCOPES = (
    (("src", "scripts", ".agents/guard"), _STRICT),
    (("tests",), ()),
    (_PORTABLE_ROOTS, _STRICT),
)


def file_options(relative: PurePosixPath) -> tuple[str, ...] | None:
    """Return the gate's checker flags for one repository file; ``None`` if unscoped."""
    for roots, options in _SCOPES:
        if any(relative.is_relative_to(root) for root in roots):
            portable_template = (
                roots == _PORTABLE_ROOTS and relative.suffix == _TEMPLATE_SUFFIX
            )
            return (_TEMPLATES_FLAG, *options) if portable_template else options
    return None


def _run_checker(paths: tuple[Path, ...], *, options: tuple[str, ...] = ()) -> int:
    """Run the shared checker on paths with its default rules plus options.

    Args:
        paths (tuple[Path, ...]): Files or directories passed to the checker.
        options (tuple[str, ...]): Extra checker flags appended before the paths.

    Returns:
        int: The checker's process exit code; negative when it was terminated.
    """
    command = [sys.executable, str(CHECKER), *options]
    command.extend(str(path) for path in paths)
    return subprocess.run(  # noqa: S603 - fixed checker and repository paths, no shell
        command, check=False
    ).returncode


def run(root: Path) -> int:
    """Run convention, magic-number and docstring checks under ``root``; ``1`` on failure."""
    checks: list[tuple[tuple[Path, ...], tuple[str, ...]]] = [
        (tuple(root / name for name in roots), options) for roots, options in _SCOPES
    ]
    portable = tuple(root / name for name in _PORTABLE_ROOTS)
    checks.append((portable, (_TEMPLATES_FLAG, *_STRICT)))
    results = tuple(_run_checker(paths, options=options) for paths, options in checks)
    return int(any(results))


def main() -> int:
    """Run the repository's Python convention gate; ``1`` when any check fails."""
    return run(_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
