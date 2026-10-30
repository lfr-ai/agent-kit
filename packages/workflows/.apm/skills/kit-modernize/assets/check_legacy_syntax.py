# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Flag legacy Python syntax that a modernization batch should replace.

Sources are parsed with ``ast`` and never imported. Default rules:

- ``typing-alias``: deprecated ``typing`` aliases that have built-in or
  ``collections`` replacements (``List``, ``Dict``, ``Optional``, ``Union`` and
  similar), imported from ``typing`` or ``typing_extensions`` or used as
  ``typing.List``;
- ``percent-format``: ``%`` formatting of a string literal, as in
  ``template % value``. Run it on new or changed files; logging calls with
  lazy ``%s`` arguments are not affected.

Opt-in rules follow project policy:

- ``future-annotations`` (``--future-annotations``): the
  ``from __future__ import annotations`` statement. Enable it only when the
  minimum supported Python evaluates annotations lazily (3.14 or later) and the
  project decided to drop the import; on 3.13 removing it changes when
  annotations are evaluated.
- ``os-path`` (``--pathlib``): ``os.path`` imports and attribute access where
  ``pathlib`` is the path policy.

``--disable`` turns off a default rule. Directories are searched for ``*.py``
files, skipping virtual environments, build output and ``--exclude`` names.

Output is ``path:line: rule: message`` sorted by path, line and rule, followed
by a summary line. Exit codes: 0 clean, 1 findings, 2 when a path is missing or
a file cannot be read or parsed. ``--self-test`` runs built-in regressions.
"""

import argparse
import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import sys

_EXIT_FINDINGS = 1
_EXIT_USAGE = 2
_TYPING_MODULES = frozenset({"typing", "typing_extensions"})
_TYPING_REPLACEMENTS = {
    "List": "list",
    "Dict": "dict",
    "Set": "set",
    "FrozenSet": "frozenset",
    "Tuple": "tuple",
    "Type": "type",
    "Text": "str",
    "Deque": "collections.deque",
    "DefaultDict": "collections.defaultdict",
    "OrderedDict": "collections.OrderedDict",
    "Counter": "collections.Counter",
    "ChainMap": "collections.ChainMap",
    "Optional": "X | None",
    "Union": "X | Y",
}
_DEFAULT_EXCLUDES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".nox",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)


class Rule(StrEnum):
    """Rule identifiers printed with each finding."""

    TYPING_ALIAS = "typing-alias"
    PERCENT_FORMAT = "percent-format"
    FUTURE_ANNOTATIONS = "future-annotations"
    OS_PATH = "os-path"


DEFAULT_RULES = frozenset({Rule.TYPING_ALIAS, Rule.PERCENT_FORMAT})


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One legacy construct.

    Args:
        path: File that contains the construct.
        line: One-based line number.
        rule: Rule that matched.
        message: Replacement advice.
    """

    path: str
    line: int
    rule: Rule
    message: str

    def render(self) -> str:
        """Return the deterministic ``path:line: rule: message`` line."""
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"


def _module_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local names bound by ``import`` statements to their modules."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                aliases[local] = alias.name if alias.asname else local
    return aliases


def _typing_message(name: str) -> str:
    """Return replacement advice for one deprecated ``typing`` alias."""
    return f"typing.{name} is legacy; use {_TYPING_REPLACEMENTS[name]}"


class _Scanner(ast.NodeVisitor):
    """Collect legacy constructs in one module."""

    def __init__(self, *, rules: frozenset[Rule], aliases: dict[str, str]) -> None:
        """Create a scanner for the enabled rules.

        Args:
            rules: Rules to report.
            aliases: Local import names mapped to module names.
        """
        self.rules = rules
        self.aliases = aliases
        self.hits: list[tuple[int, Rule, str]] = []

    def _hit(self, node: ast.stmt | ast.expr, rule: Rule, message: str) -> None:
        """Record a finding when its rule is enabled."""
        if rule in self.rules:
            self.hits.append((node.lineno, rule, message))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Flag typing aliases, the annotations future import and os.path.

        Args:
            node: Import statement.
        """
        module = node.module or ""
        names = [alias.name for alias in node.names]
        if module in _TYPING_MODULES:
            for name in names:
                if name in _TYPING_REPLACEMENTS:
                    self._hit(node, Rule.TYPING_ALIAS, _typing_message(name))
        if module == "__future__" and "annotations" in names:
            self._hit(
                node,
                Rule.FUTURE_ANNOTATIONS,
                "from __future__ import annotations is unnecessary when the "
                "minimum Python evaluates annotations lazily",
            )
        if module == "os.path" or (module == "os" and "path" in names):
            self._hit(node, Rule.OS_PATH, "os.path import; use pathlib.Path")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Flag ``import os.path``.

        Args:
            node: Import statement.
        """
        if any(alias.name == "os.path" for alias in node.names):
            self._hit(node, Rule.OS_PATH, "os.path import; use pathlib.Path")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Flag ``typing.List`` style access and ``os.path`` attribute use.

        Args:
            node: Attribute expression.
        """
        if isinstance(node.value, ast.Name):
            module = self.aliases.get(node.value.id)
            if module in _TYPING_MODULES and node.attr in _TYPING_REPLACEMENTS:
                self._hit(node, Rule.TYPING_ALIAS, _typing_message(node.attr))
            if module == "os" and node.attr == "path":
                self._hit(node, Rule.OS_PATH, "os.path use; use pathlib.Path")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Flag ``%`` formatting of a string literal.

        Args:
            node: Binary operation.
        """
        left = node.left
        if (
            isinstance(node.op, ast.Mod)
            and isinstance(left, ast.Constant)
            and isinstance(left.value, str)
        ):
            self._hit(
                node,
                Rule.PERCENT_FORMAT,
                "printf-style % formatting; use an f-string or str.format",
            )
        self.generic_visit(node)


def check_source(source: str, path: str, *, rules: frozenset[Rule]) -> list[Finding]:
    """Return legacy constructs in one source text.

    Args:
        source: Python source code.
        path: Path used in findings.
        rules: Rules to report.

    Returns:
        Findings sorted by line and rule.

    Raises:
        SyntaxError: The source does not parse.
    """
    tree = ast.parse(source, filename=path)
    scanner = _Scanner(rules=rules, aliases=_module_aliases(tree))
    scanner.visit(tree)
    return [
        Finding(path=path, line=line, rule=rule, message=message)
        for line, rule, message in sorted(set(scanner.hits))
    ]


def collect(paths: Iterable[Path], *, excluded: frozenset[str]) -> list[Path]:
    """Expand files and directories into sorted Python files.

    Args:
        paths: Files or directories given on the command line.
        excluded: Directory names skipped below a given directory.

    Returns:
        Sorted, de-duplicated ``*.py`` files.

    Raises:
        FileNotFoundError: A path does not exist.
    """
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*.py")
                if not excluded.intersection(candidate.relative_to(path).parts[:-1])
            )
        else:
            raise FileNotFoundError(path)
    return sorted(files)


_SELF_TEST_SOURCE = """\
from __future__ import annotations
import os.path
import typing as t
from typing import Optional
def f(x: t.List[int]) -> Optional[str]:
    return 'n=%d' % len(x)
"""
_SELF_TEST_EXPECTED = (
    "self.py:1: future-annotations",
    "self.py:2: os-path",
    "self.py:4: typing-alias",
    "self.py:5: typing-alias",
    "self.py:6: percent-format",
)
_SELF_TEST_CLEAN = """\
import logging
LOGGER = logging.getLogger(__name__)
def f(x: list[int] | None) -> int:
    LOGGER.info('size %s', x)
    return len(x or []) % 2
"""


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by ``--self-test``."""

    LEGACY_MISSED = "legacy sample findings differ from the expected findings"
    DEFAULTS_CHANGED = "policy opt-in rules fired with default rules"
    MODERN_FLAGGED = "modern sample produced findings"
    SYNTAX_ACCEPTED = "unparsable source was accepted"


class SelfTestError(RuntimeError):
    """A documented self-test invariant failed."""

    def __init__(self, issue: SelfTestIssue) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
        """
        super().__init__(issue.value)


def self_test() -> None:
    """Exercise every rule, the opt-in defaults and parse failures.

    Raises:
        SelfTestError: A documented behavior regressed.
    """
    every_rule = frozenset(Rule)
    found = check_source(_SELF_TEST_SOURCE, "self.py", rules=every_rule)
    rendered = tuple(item.render().rsplit(": ", 1)[0] for item in found)
    if rendered != _SELF_TEST_EXPECTED:
        raise SelfTestError(SelfTestIssue.LEGACY_MISSED)
    defaults = check_source(_SELF_TEST_SOURCE, "self.py", rules=DEFAULT_RULES)
    if {item.rule for item in defaults} != DEFAULT_RULES:
        raise SelfTestError(SelfTestIssue.DEFAULTS_CHANGED)
    if check_source(_SELF_TEST_CLEAN, "clean.py", rules=every_rule):
        raise SelfTestError(SelfTestIssue.MODERN_FLAGGED)
    try:
        check_source("def broken(:\n", "broken.py", rules=every_rule)
    except SyntaxError:
        return
    raise SelfTestError(SelfTestIssue.SYNTAX_ACCEPTED)


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Flag legacy Python syntax.")
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument(
        "--future-annotations",
        action="store_true",
        help="flag 'from __future__ import annotations' (policy opt-in)",
    )
    parser.add_argument(
        "--pathlib", action="store_true", help="flag os.path (policy opt-in)"
    )
    parser.add_argument(
        "--disable",
        action="append",
        choices=sorted(DEFAULT_RULES),
        default=[],
        help="turn off a default rule (repeatable)",
    )
    parser.add_argument(
        "--exclude", action="append", default=[], help="directory name to skip"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in regressions"
    )
    return parser


def _rules(args: argparse.Namespace) -> frozenset[Rule]:
    """Return the enabled rules for parsed arguments."""
    rules = set(DEFAULT_RULES) - {Rule(name) for name in args.disable}
    if args.future_annotations:
        rules.add(Rule.FUTURE_ANNOTATIONS)
    if args.pathlib:
        rules.add(Rule.OS_PATH)
    return frozenset(rules)


def _scan(files: Sequence[Path], *, rules: frozenset[Rule]) -> tuple[list[str], int]:
    """Return rendered findings and the number of unreadable files."""
    lines: list[str] = []
    failures = 0
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
            findings = check_source(source, path.as_posix(), rules=rules)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as error:
            sys.stderr.write(f"{path.as_posix()}: cannot check: {error}\n")
            failures += 1
            continue
        lines.extend(finding.render() for finding in findings)
    return lines, failures


def _check(args: argparse.Namespace) -> int:
    """Scan the paths named in parsed arguments and print findings."""
    try:
        files = collect(args.paths, excluded=_DEFAULT_EXCLUDES | set(args.exclude))
    except FileNotFoundError as error:
        sys.stderr.write(f"{error}: path does not exist\n")
        return _EXIT_USAGE
    lines, failures = _scan(files, rules=_rules(args))
    for line in lines:
        sys.stdout.write(f"{line}\n")
    sys.stdout.write(f"{len(files)} file(s) checked, {len(lines)} finding(s).\n")
    if failures:
        return _EXIT_USAGE
    return _EXIT_FINDINGS if lines else 0


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    try:
        self_test()
    except SelfTestError as error:
        sys.stderr.write(f"check_legacy_syntax self-test failed: {error}\n")
        return _EXIT_FINDINGS
    sys.stdout.write("check_legacy_syntax self-test passed.\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Scan paths and print findings.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 when clean, 1 on findings, 2 on missing paths or unreadable files.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.paths:
        parser.error("at least one file or directory is required")
    return _check(args)


if __name__ == "__main__":
    sys.exit(main())
