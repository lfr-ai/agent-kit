"""Check toolkit Python conventions and docstrings in capability sources."""

from pathlib import Path
import subprocess
import sys

_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = (
    _ROOT / "packages/backend/.apm/skills/kit-python-service/assets/check_python.py"
)


def _run_checker(paths: tuple[Path, ...], *, options: tuple[str, ...] = ()) -> int:
    """Run the shared checker on paths with its default rules plus options."""
    command = [sys.executable, str(_CHECKER), *options]
    command.extend(str(path) for path in paths)
    return subprocess.run(  # noqa: S603 - fixed checker and repository paths, no shell
        command, check=False
    ).returncode


def run(root: Path) -> int:
    """Run toolkit conventions, magic-number, and docstring checks under a root.

    Test modules keep literal expectations; production, script, and portable
    asset code must name numeric literals other than 0 and +/-1.

    Args:
        root: Root containing toolkit code and portable Python sources.
    """
    production = tuple(root / name for name in ("src", "scripts", ".agents/guard"))
    checks = (
        (production, ("--magic-numbers",)),
        ((root / "tests",), ()),
        (
            (root / ".apm", root / "packages"),
            ("--only", "docstring-backtick", "--only", "magic-number"),
        ),
        (
            (root / ".apm", root / "packages"),
            ("--templates", "--only", "magic-number"),
        ),
    )
    results = tuple(_run_checker(paths, options=options) for paths, options in checks)
    return int(any(results))


def main() -> int:
    """Run the repository's Python convention quality gate."""
    return run(_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
