"""Flag process-environment access outside the configured settings modules.

Configuration is parsed once by a typed settings object at the composition root
and passed explicitly to collaborators. This checker parses Python sources
without importing them and reports ``os.environ``, ``os.environb``, ``os.getenv``,
and ``os.putenv`` use in any file that does not match an ``--allow`` glob. A source
line carrying the waiver comment ``# config: env-access-reviewed`` is accepted.
Exit 0 means no findings, 1 means findings or unreadable sources.
Run ``--self-test`` for built-in regressions.
"""

import argparse
import ast
from collections.abc import Iterable, Sequence
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path

_DEFAULT_ALLOW = (
    "*settings.py",
    "*settings/*.py",
    "*config.py",
    "*config/*.py",
)
_DEFAULT_EXCLUDE = (
    "*/.venv/*",
    "*/venv/*",
    "*/node_modules/*",
    "*/__pycache__/*",
    "*/build/*",
    "*/dist/*",
    "*/.tox/*",
    "*/.git/*",
)
_WAIVER = "# config: env-access-reviewed"
_ENV_ATTRIBUTES = frozenset({"environ", "environb", "getenv", "getenvb", "putenv"})
_MAX_EXPRESSION = 72
_ELLIPSIS = "..."


def _bindings(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Collect local names bound to the ``os`` module and to its environment API.

    Args:
        tree: Parsed module.

    Returns:
        Names that refer to the ``os`` module and names that refer directly to
        ``environ``, ``getenv``, or a sibling environment attribute.
    """
    modules: set[str] = set()
    direct: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(_module_aliases(node))
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            direct.update(_direct_aliases(node))
    return modules, direct


def _module_aliases(node: ast.Import) -> set[str]:
    """Return local names that an ``import`` statement binds to ``os``.

    Args:
        node: Import statement.

    Returns:
        Names bound to the ``os`` module.
    """
    return {
        alias.asname or "os"
        for alias in node.names
        if alias.name == "os" or (alias.name.startswith("os.") and alias.asname is None)
    }


def _direct_aliases(node: ast.ImportFrom) -> set[str]:
    """Return local names that ``from os import`` binds to environment attributes.

    Args:
        node: ``from os import`` statement.

    Returns:
        Names bound directly to an environment attribute.
    """
    return {
        alias.asname or alias.name
        for alias in node.names
        if alias.name in _ENV_ATTRIBUTES
    }


def _parents(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    """Map every node to its syntactic parent.

    Args:
        tree: Parsed module.

    Returns:
        Child-to-parent mapping for the whole tree.
    """
    return {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }


def _widen(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST:
    """Expand an environment reference to the expression a reviewer recognizes.

    Args:
        node: The ``os.environ`` style reference.
        parents: Child-to-parent mapping.

    Returns:
        The enclosing subscript or call when the reference is used directly.
    """
    parent = parents.get(node)
    if isinstance(parent, ast.Subscript) and parent.value is node:
        return parent
    if isinstance(parent, ast.Call) and parent.func is node:
        return parent
    if isinstance(parent, ast.Attribute) and parent.value is node:
        grandparent = parents.get(parent)
        if isinstance(grandparent, ast.Call) and grandparent.func is parent:
            return grandparent
    return node


def _is_reference(node: ast.AST, modules: set[str], direct: set[str]) -> bool:
    """Return whether a node names the process environment API.

    Args:
        node: Candidate node.
        modules: Local names bound to ``os``.
        direct: Local names bound to an environment attribute.

    Returns:
        True for ``os.environ``-style attributes and directly imported names.
    """
    if isinstance(node, ast.Attribute):
        return (
            node.attr in _ENV_ATTRIBUTES
            and isinstance(node.value, ast.Name)
            and node.value.id in modules
        )
    return isinstance(node, ast.Name) and node.id in direct


def find_env_access(text: str, path: str) -> list[str]:
    """Report environment access in one source file.

    Args:
        text: Python source text.
        path: Display path used in findings.

    Returns:
        Findings formatted as ``path:line: message``, in source order.

    Raises:
        SyntaxError: The source cannot be parsed.
    """
    tree = ast.parse(text, filename=path)
    modules, direct = _bindings(tree)
    parents = _parents(tree)
    lines = text.splitlines()
    seen: set[tuple[int, str]] = set()
    findings: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not _is_reference(node, modules, direct):
            continue
        expression = _widen(node, parents)
        line = getattr(expression, "lineno", 1)
        source_line = lines[line - 1] if line - 1 < len(lines) else ""
        if _WAIVER in source_line:
            continue
        rendered = ast.unparse(expression)
        if len(rendered) > _MAX_EXPRESSION:
            rendered = rendered[: _MAX_EXPRESSION - len(_ELLIPSIS)] + _ELLIPSIS
        if (line, rendered) in seen:
            continue
        seen.add((line, rendered))
        column = getattr(expression, "col_offset", 0)
        message = (
            f"{path}:{line}: environment access '{rendered}' outside a settings "
            "module; read it in typed settings and pass the value explicitly"
        )
        findings.append((line, column, message))
    return [message for _, _, message in sorted(findings)]


def matches(path: str, patterns: Iterable[str]) -> bool:
    """Return whether a POSIX-style path matches any glob pattern.

    Args:
        path: Path rendered with forward slashes.
        patterns: Case-sensitive ``fnmatch`` patterns; ``*`` also matches ``/``.

    Returns:
        True when at least one pattern matches the path or ``/`` + path.
    """
    candidates = (path, f"/{path}")
    return any(
        fnmatchcase(candidate, pattern)
        for pattern in patterns
        for candidate in candidates
    )


def _python_files(
    targets: Sequence[Path], exclude: Sequence[str]
) -> tuple[list[Path], list[str]]:
    """Expand explicit targets into Python files, reporting missing targets.

    Args:
        targets: Files or directories given on the command line.
        exclude: Glob patterns for paths to skip.

    Returns:
        Sorted Python files and findings for missing or linked targets.
    """
    files: set[Path] = set()
    problems: list[str] = []
    for target in targets:
        if not target.exists() or target.is_symlink():
            problems.append(f"{target.as_posix()}:1: missing or linked target")
            continue
        candidates = [target] if target.is_file() else target.rglob("*.py")
        files.update(
            candidate
            for candidate in candidates
            if candidate.suffix == ".py"
            and not candidate.is_symlink()
            and not matches(candidate.as_posix(), exclude)
        )
    return sorted(files), problems


def scan(
    targets: Sequence[Path], *, allow: Sequence[str], exclude: Sequence[str]
) -> list[str]:
    """Scan targets and return every finding.

    Args:
        targets: Files or directories to scan.
        allow: Globs for settings modules that may read the environment.
        exclude: Globs for paths that are never scanned.

    Returns:
        Findings for disallowed environment access and unreadable sources.
    """
    files, findings = _python_files(targets, exclude)
    for path in files:
        display = path.as_posix()
        if matches(display, allow):
            continue
        try:
            findings.extend(find_env_access(path.read_text(encoding="utf-8"), display))
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{display}:1: source cannot be read or parsed")
    return findings


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    MISSED_ENVIRONMENT_ACCESS = "missed environment access: {source!r} {found}"
    FALSE_POSITIVE = "false positive: {source!r}"
    SETTINGS_REJECTED = "default allow glob must accept settings modules"
    ORDINARY_MODULE_ALLOWED = "default allow glob must reject ordinary modules"
    VIRTUAL_ENVIRONMENT_SCANNED = "virtual environments must be excluded"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        source: str | None = None,
        found: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            source: Observed source for the failing case.
            found: Observed found for the failing case.
        """
        super().__init__(issue.value.format(source=source, found=found))


def self_test() -> None:
    """Exercise aliases, waivers, allow globs, and clean sources.

    Raises:
        AssertionError: A regression was detected.
    """
    _self_test_risky()
    _self_test_clean()
    _self_test_globs()


def _self_test_risky() -> None:
    """Require one finding for each environment access form.

    Raises:
        SelfTestError: An access form was missed.
    """
    risky = {
        "import os\nvalue = os.environ['ORDER_LIMIT']\n": "os.environ['ORDER_LIMIT']",
        "import os\nvalue = os.getenv('REGION', 'west')\n": "os.getenv('REGION'",
        "import os as system\nvalue = system.environ.get('TOKEN')\n": "environ.get",
        "from os import environ as env\nflag = 'DEBUG' in env\n": "'env'",
        "from os import getenv\nvalue = getenv('MODE')\n": "getenv('MODE')",
        "import os.path\nos.environ['MODE'] = 'x'\n": "os.environ['MODE']",
    }
    for source, fragment in risky.items():
        found = find_env_access(source, "app/service.py")
        if len(found) != 1 or fragment not in found[0]:
            raise SelfTestError(
                SelfTestIssue.MISSED_ENVIRONMENT_ACCESS, source=source, found=found
            )


def _self_test_clean() -> None:
    """Require no findings for unrelated names and waived lines.

    Raises:
        SelfTestError: A clean source was reported.
    """
    clean = (
        "import os\npath = os.path.join('a', 'b')\n",
        "environ = {}\nvalue = environ.get('x')\n",
        "import os\nvalue = os.environ['X']  # config: env-access-reviewed\n",
    )
    for source in clean:
        if find_env_access(source, "app/service.py"):
            raise SelfTestError(SelfTestIssue.FALSE_POSITIVE, source=source)


def _self_test_globs() -> None:
    """Require the default allow and exclude globs to classify paths correctly.

    Raises:
        SelfTestError: A default glob misclassified a path.
    """
    if not matches("src/app/settings.py", _DEFAULT_ALLOW):
        raise SelfTestError(SelfTestIssue.SETTINGS_REJECTED)
    if matches("src/app/orders.py", _DEFAULT_ALLOW):
        raise SelfTestError(SelfTestIssue.ORDINARY_MODULE_ALLOWED)
    if not matches("project/.venv/lib/x.py", _DEFAULT_EXCLUDE):
        raise SelfTestError(SelfTestIssue.VIRTUAL_ENVIRONMENT_SCANNED)


def main(argv: list[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 when clean, 1 when findings were reported.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument(
        "--allow",
        action="append",
        default=None,
        help="glob for settings modules allowed to read the environment "
        f"(repeatable; default: {', '.join(_DEFAULT_ALLOW)})",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="additional glob for paths to skip (repeatable)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_from_config_pattern self-test passed.")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    findings = scan(
        args.paths,
        allow=tuple(args.allow or _DEFAULT_ALLOW),
        exclude=(*_DEFAULT_EXCLUDE, *args.exclude),
    )
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
