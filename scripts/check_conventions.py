"""Check toolkit Python conventions and docstrings in capability sources."""

from pathlib import Path
import subprocess
import sys

_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = (
    _ROOT / "packages/backend/.apm/skills/kit-python-service/assets/check_python.py"
)
_DOCSTRINGS_ENABLED = True
_DOCSTRINGS_FLAG = "--docstrings"


def _run_checker(paths: tuple[Path, ...], *, options: tuple[str, ...] = ()) -> int:
    """Run the shared checker on paths with its default rules plus options.

    Args:
        paths (tuple[Path, ...]): Files or directories passed to the checker.
        options (tuple[str, ...]): Extra checker flags appended before the paths.

    Returns:
        The checker's process exit code; negative when it was terminated.
    """
    command = [sys.executable, str(_CHECKER), *options]
    command.extend(str(path) for path in paths)
    return subprocess.run(  # noqa: S603 - fixed checker and repository paths, no shell
        command, check=False
    ).returncode


def run(root: Path, *, docstrings: bool | None = None) -> int:
    """Run toolkit conventions, magic-number, and docstring checks under a root.

    Test modules keep literal expectations; production, script, and portable
    asset code and templates must name numeric literals other than 0 and +/-1.

    Args:
        root (Path): Root containing toolkit code and portable Python sources.
        docstrings (bool | None): Also enforce the Args/Returns docstring contract
            over production roots, portable assets, and portable templates;
            ``None`` follows the enabled module default.

    Returns:
        Zero when every check passes, otherwise one.
    """
    enforce = _DOCSTRINGS_ENABLED if docstrings is None else docstrings
    production = tuple(root / name for name in ("src", "scripts", ".agents/guard"))
    portable = (root / ".apm", root / "packages")
    options = ("--magic-numbers", *((_DOCSTRINGS_FLAG,) if enforce else ()))
    checks = (
        (production, options),
        ((root / "tests",), ()),
        (portable, options),
        (portable, ("--templates", *options)),
    )
    results = tuple(_run_checker(paths, options=options) for paths, options in checks)
    return int(any(results))


def main(argv: list[str] | None = None) -> int:
    """Run the repository's Python convention quality gate.

    Returns zero when every check passes, otherwise one. ``--docstrings``
    explicitly requests the already-default docstring contract.
    """
    enforce = _DOCSTRINGS_FLAG in (sys.argv[1:] if argv is None else argv)
    return run(_ROOT, docstrings=True if enforce else None)


if __name__ == "__main__":
    raise SystemExit(main())
