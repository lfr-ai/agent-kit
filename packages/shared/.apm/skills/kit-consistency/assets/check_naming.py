"""Check file and directory naming conventions without reading file contents.

Rules:

- Python module file names are snake_case and not Python keywords, so they can
  be imported ('__init__', '__main__' and similar dunder modules are exempt).
- Directories that directly contain Python modules are snake_case too.
- Directories below each '--kebab-root' that hold no Python modules are
  kebab-case (lower-case words joined by hyphens), for example docs, assets
  and configuration trees.
- With '--forbid-stdlib-shadow', a module outside any package that is named
  like a standard-library module is reported, because it can shadow the real
  module when its directory is on 'sys.path'.

Hidden names (starting with '.') are not checked but their children are.
Findings are printed as 'path:1: message'; the exit status is 1 on findings.

Example:
    python check_naming.py . --kebab-root docs --kebab-root .apm/skills
"""

import argparse
import fnmatch
import keyword
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import NamedTuple

_SNAKE = re.compile(r"_?[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_DUNDER = re.compile(r"__[a-z][a-z0-9_]*__")
_DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    ".tox",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "*.egg-info",
)


class Finding(NamedTuple):
    """One naming problem.

    Attributes:
        path: Offending file or directory, relative to the scanned root.
        message: Human-readable description.
    """

    path: str
    message: str

    def render(self) -> str:
        """Return the finding as 'path:1: message'."""
        return f"{self.path}:1: {self.message}"


class Options(NamedTuple):
    """Naming policy switches.

    Attributes:
        kebab_roots: Directories whose non-Python descendants must be kebab-case.
        packages_only: Only directories with '__init__.py' must be snake_case.
        forbid_stdlib_shadow: Report top-level modules named like stdlib modules.
        ignore: fnmatch patterns of relative paths that are never reported.
    """

    kebab_roots: tuple[PurePosixPath, ...] = ()
    packages_only: bool = False
    forbid_stdlib_shadow: bool = False
    ignore: tuple[str, ...] = ()


def is_snake_case(name: str) -> bool:
    """Return whether 'name' is lower snake_case without double underscores.

    Args:
        name: A module stem or directory name.

    Returns:
        True for names such as 'invoice_repository' or '_private'.
    """
    return _SNAKE.fullmatch(name) is not None


def is_kebab_case(name: str) -> bool:
    """Return whether 'name' is lower-case words joined by single hyphens.

    Args:
        name: A directory name.

    Returns:
        True for names such as 'getting-started' or 'v2'.
    """
    return _KEBAB.fullmatch(name) is not None


def _hidden(name: str) -> bool:
    """Return whether a path component is a dot-name."""
    return name.startswith(".")


def _module_problem(stem: str) -> str | None:
    """Describe why a module stem is not importable-style, if it is not."""
    if _DUNDER.fullmatch(stem):
        return None
    if not is_snake_case(stem):
        return f"module '{stem}.py' is not snake_case"
    if keyword.iskeyword(stem):
        return f"module '{stem}.py' is a Python keyword and cannot be imported"
    return None


def _under(path: PurePosixPath, root: PurePosixPath) -> bool:
    """Return whether 'path' is strictly below 'root' ('.' contains everything)."""
    if str(root) == ".":
        return str(path) != "."
    return path != root and path.is_relative_to(root)


def check_tree(files: Iterable[PurePosixPath], *, options: Options) -> list[Finding]:
    """Check relative file paths and the directories they imply.

    Args:
        files: File paths relative to the scanned root.
        options: Naming policy.

    Returns:
        Findings sorted by path and message.
    """
    paths = sorted(set(files))
    modules = [path for path in paths if path.suffix == ".py"]
    python_dirs = {path.parent for path in modules}
    packages = {path.parent for path in modules if path.name == "__init__.py"}
    snake_dirs = packages if options.packages_only else python_dirs
    directories = {parent for path in paths for parent in path.parents} - {
        PurePosixPath()
    }
    findings: list[Finding] = []
    for module in modules:
        problem = _module_problem(module.stem)
        if problem:
            findings.append(Finding(str(module), problem))
        elif (
            options.forbid_stdlib_shadow
            and module.parent not in packages
            and module.stem in sys.stdlib_module_names
        ):
            findings.append(
                Finding(
                    str(module),
                    f"module '{module.name}' shadows the standard-library "
                    f"module '{module.stem}'",
                )
            )
    for directory in sorted(directories):
        name = directory.name
        if _hidden(name):
            continue
        if directory in snake_dirs:
            problem = (
                None
                if is_snake_case(name)
                else f"Python directory '{name}' is not snake_case"
            )
        elif directory in python_dirs or not any(
            _under(directory, root) for root in options.kebab_roots
        ):
            problem = None
        else:
            problem = (
                None if is_kebab_case(name) else f"directory '{name}' is not kebab-case"
            )
        if problem:
            findings.append(Finding(f"{directory}/", problem))
    return sorted(
        finding
        for finding in findings
        if not any(
            fnmatch.fnmatch(finding.path.rstrip("/"), pattern)
            for pattern in options.ignore
        )
    )


def collect(root: Path, *, excludes: Sequence[str]) -> list[PurePosixPath]:
    """List files below 'root' as relative POSIX paths, skipping excluded names.

    Args:
        root: Directory to scan.
        excludes: fnmatch patterns matched against each path component.

    Returns:
        Sorted relative file paths.
    """

    def excluded(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pattern) for pattern in excludes)

    found: list[PurePosixPath] = []
    for directory, dirnames, filenames in root.walk():
        dirnames[:] = sorted(name for name in dirnames if not excluded(name))
        relative = directory.relative_to(root)
        found.extend(
            PurePosixPath(relative.as_posix()) / name
            for name in filenames
            if not excluded(name)
        )
    return sorted(found)


def self_test() -> list[str]:
    """Check the rules on an in-memory tree and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    tree = [
        PurePosixPath(item)
        for item in (
            "src/app/__init__.py",
            "src/app/invoice_repository.py",
            "src/app/InvoiceService.py",
            "src/app/class.py",
            "src/My-Pkg/__init__.py",
            "src/app/__main__.py",
            "docs/getting-started/index.md",
            "docs/Release_Notes/v1.md",
            "scripts/logging.py",
            ".github/workflows/ci.yml",
        )
    ]
    options = Options(kebab_roots=(PurePosixPath("docs"),), forbid_stdlib_shadow=True)
    rendered = "\n".join(item.render() for item in check_tree(tree, options=options))
    expectations = {
        "camel-case module": "InvoiceService.py' is not snake_case",
        "keyword module": "'class.py' is a Python keyword",
        "hyphenated package": "src/My-Pkg/:1: Python directory",
        "non-kebab docs dir": "docs/Release_Notes/:1: directory",
        "stdlib shadow": "scripts/logging.py:1: module 'logging.py' shadows",
    }
    failures = [
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    ]
    failures.extend(
        f"valid name was reported: {clean}"
        for clean in ("invoice_repository", "__main__", "getting-started", ".github")
        if clean in rendered
    )
    ignored = check_tree(
        tree, options=options._replace(ignore=("src/*", "docs/*", "scripts/*"))
    )
    if ignored:
        failures.append(f"ignored paths were reported: {ignored}")
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", nargs="?", type=Path, default=Path(), help="root")
    parser.add_argument(
        "--kebab-root",
        action="append",
        default=[],
        metavar="DIR",
        help="relative directory whose non-Python subdirectories must be kebab-case",
    )
    parser.add_argument(
        "--packages-only",
        action="store_true",
        help="require snake_case only for directories containing '__init__.py'",
    )
    parser.add_argument(
        "--forbid-stdlib-shadow",
        action="store_true",
        help="report modules outside packages that reuse a stdlib module name",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="extra path component pattern to skip; repeatable",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="GLOB",
        help="relative path pattern never reported; repeatable",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Scan a tree and print naming findings.

    Args:
        argv: Command-line arguments; 'sys.argv[1:]' when None.

    Returns:
        0 when clean, 1 when findings exist, 2 when the root is unusable.
    """
    args = _parser().parse_args(argv)
    if args.self_test:
        failures = self_test()
        for failure in failures:
            print(failure, file=sys.stderr)
        if failures:
            return 1
        print("check_naming self-test passed.")
        return 0
    root: Path = args.root
    if not root.is_dir():
        print(f"{root.as_posix()}: not a directory", file=sys.stderr)
        return 2
    options = Options(
        kebab_roots=tuple(PurePosixPath(item) for item in args.kebab_root),
        packages_only=args.packages_only,
        forbid_stdlib_shadow=args.forbid_stdlib_shadow,
        ignore=tuple(args.ignore),
    )
    files = collect(root, excludes=(*_DEFAULT_EXCLUDES, *args.exclude))
    findings = check_tree(files, options=options)
    prefix = root.as_posix().rstrip("/")
    for finding in findings:
        shown = finding.path if prefix == "." else f"{prefix}/{finding.path}"
        print(Finding(shown, finding.message).render())
    if not findings:
        print(f"Naming conventions hold for {len(files)} file(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
