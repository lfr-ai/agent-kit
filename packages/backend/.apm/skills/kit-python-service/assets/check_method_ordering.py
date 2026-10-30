# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Report private helpers that break the stepdown order relative to their sole caller.

A private helper is a function or method named with one leading underscore
(not a special method). When exactly one function, method, or class in the same scope
refers to it from deferred code (a function body), the helper should be placed
after that caller (``--order after``, the default stepdown rule) or before it
(``--order before``). Helpers with several callers, or referenced by code that
runs at definition time (decorators, defaults, class bodies, module
statements), are never reported because their position is constrained or
ambiguous.
"""

import argparse
import ast
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
import sys

_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = ("module", "class")
_EXIT_USAGE = 2

type _Matcher = Callable[[ast.AST, str], bool]


@dataclass(frozen=True, kw_only=True, slots=True)
class _Unit:
    """One statement of a scope body with the helper names it references."""

    index: int
    line: int
    name: str | None
    deferred: frozenset[str]
    immediate: frozenset[str]


class OrderingOptionIssue(StrEnum):
    """Supported ordering option validation failures and their stable messages."""

    UNKNOWN_ORDER = "unknown order {order!r}"
    UNKNOWN_SCOPE = "unknown scope {scope!r}"


class OrderingOptionError(ValueError):
    """An input violates the ordering option contract."""

    def __init__(
        self,
        issue: OrderingOptionIssue,
        *,
        order: str | None = None,
        scope: str | None = None,
    ) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            order: Diagnostic order for the invalid input.
            scope: Diagnostic scope for the invalid input.
        """
        super().__init__(issue.value.format(order=order, scope=scope))


def check_source(
    text: str,
    path: str,
    *,
    order: str = "after",
    scopes: frozenset[str] = frozenset(_SCOPES),
    ignore: tuple[re.Pattern[str], ...] = (),
) -> list[str]:
    """Return ordering findings for one module's source text.

    Args:
        text: Python source text.
        path: Display path used as the finding prefix.
        order: ``after`` requires helpers below their caller; ``before`` above it.
        scopes: Which scopes to check: ``module``, ``class``, or both.
        ignore: Helper-name patterns that are never reported.

    Returns:
        Findings formatted as ``path:line: message``, sorted by line.

    Raises:
        ValueError: If ``order`` or a scope name is unknown.
    """
    _validate_options(order, scopes)
    tree = ast.parse(text, filename=path)
    findings: list[tuple[int, str]] = []
    if "module" in scopes:
        findings.extend(_scope_findings(tree.body, _name_reference, order, ignore))
    if "class" in scopes:
        findings.extend(_class_findings(tree, order, ignore))
    return [f"{path}:{line}: {message}" for line, message in sorted(findings)]


def _validate_options(order: str, scopes: frozenset[str]) -> None:
    if order not in {"after", "before"}:
        raise OrderingOptionError(OrderingOptionIssue.UNKNOWN_ORDER, order=order)
    unknown = scopes - set(_SCOPES)
    if unknown:
        raise OrderingOptionError(OrderingOptionIssue.UNKNOWN_SCOPE, scope=min(unknown))


def _class_findings(
    tree: ast.Module, order: str, ignore: tuple[re.Pattern[str], ...]
) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield from _scope_findings(node.body, _attribute_reference, order, ignore)


def _scope_findings(
    body: list[ast.stmt],
    matcher: _Matcher,
    order: str,
    ignore: tuple[re.Pattern[str], ...],
) -> Iterator[tuple[int, str]]:
    helpers = _helpers(body, ignore)
    if not helpers:
        return
    units = [
        _unit(index, statement, frozenset(helpers), matcher)
        for index, statement in enumerate(body)
    ]
    positions = {unit.name: unit for unit in units if unit.name is not None}
    for name, node in helpers.items():
        caller = _sole_caller(name, units)
        if caller is None:
            continue
        helper_index = positions[name].index
        misplaced = (
            helper_index < caller.index
            if order == "after"
            else helper_index > caller.index
        )
        if misplaced:
            relation = "before" if order == "after" else "after"
            yield (
                node.lineno,
                (
                    f"private helper '{name}' is defined {relation} its sole caller "
                    f"'{caller.name}' (line {caller.line}); move it {order} the caller"
                ),
            )


def _helpers(
    body: list[ast.stmt], ignore: tuple[re.Pattern[str], ...]
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    definitions: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for statement in body:
        if isinstance(statement, _FUNCTIONS):
            definitions.setdefault(statement.name, []).append(statement)
    return {
        name: nodes[0]
        for name, nodes in definitions.items()
        if len(nodes) == 1
        and _is_private(name)
        and not any(pattern.search(name) for pattern in ignore)
    }


def _sole_caller(name: str, units: list[_Unit]) -> _Unit | None:
    if any(name in unit.immediate for unit in units):
        return None
    callers = [unit for unit in units if name in unit.deferred and unit.name != name]
    if len(callers) != 1 or callers[0].name is None:
        return None
    return callers[0]


def _unit(
    index: int, statement: ast.stmt, helpers: frozenset[str], matcher: _Matcher
) -> _Unit:
    deferred: list[ast.AST] = []
    immediate: list[ast.AST] = []
    _split(statement, deferred, immediate)
    name = (
        statement.name if isinstance(statement, (*_FUNCTIONS, ast.ClassDef)) else None
    )
    return _Unit(
        index=index,
        line=statement.lineno,
        name=name,
        deferred=_references(deferred, helpers, _deferred_matcher(matcher)),
        immediate=_references(immediate, helpers, matcher),
    )


def _split(node: ast.AST, deferred: list[ast.AST], immediate: list[ast.AST]) -> None:
    """Separate code that runs later (function bodies) from definition-time code."""
    if isinstance(node, _FUNCTIONS):
        immediate.extend(node.decorator_list)
        immediate.append(node.args)
        if node.returns is not None:
            immediate.append(node.returns)
        deferred.extend(node.body)
    elif isinstance(node, ast.ClassDef):
        immediate.extend([*node.decorator_list, *node.bases, *node.keywords])
        for statement in node.body:
            _split(statement, deferred, immediate)
    else:
        immediate.append(node)


def _references(
    nodes: Iterable[ast.AST], helpers: frozenset[str], matcher: _Matcher
) -> frozenset[str]:
    found: set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            found.update(name for name in helpers if matcher(node, name))
    return frozenset(found)


def _deferred_matcher(matcher: _Matcher) -> _Matcher:
    """Inside method bodies a class-scope helper is reachable only as an attribute."""
    if matcher is _attribute_reference:
        return _method_body_reference
    return matcher


def _name_reference(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _attribute_reference(node: ast.AST, name: str) -> bool:
    return _name_reference(node, name) or _method_body_reference(node, name)


def _method_body_reference(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == name


def _is_private(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


def main(argv: list[str] | None = None) -> int:
    """Check helper placement in the given files and directories.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Zero when every helper is placed correctly, otherwise one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--order", choices=("after", "before"), default="after")
    parser.add_argument("--scope", choices=("module", "class", "all"), default="all")
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="regular expression for helper names to skip (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="additional directory name to skip (repeatable)",
    )
    args = parser.parse_args(argv)
    scopes = frozenset(_SCOPES) if args.scope == "all" else frozenset({args.scope})
    try:
        ignore = tuple(re.compile(pattern) for pattern in args.ignore)
    except re.error as error:
        sys.stderr.write(f"invalid --ignore pattern: {error}\n")
        return _EXIT_USAGE
    files, findings = _python_files(args.paths, _EXCLUDED | set(args.exclude))
    for path in files:
        try:
            findings.extend(
                check_source(
                    path.read_text(encoding="utf-8"),
                    path.as_posix(),
                    order=args.order,
                    scopes=scopes,
                    ignore=ignore,
                )
            )
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{path.as_posix()}:1: source cannot be parsed")
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    return 1 if findings else 0


def _python_files(
    paths: Iterable[Path], excluded: frozenset[str]
) -> tuple[list[Path], list[str]]:
    files: set[Path] = set()
    problems: list[str] = []
    for path in paths:
        if not path.exists():
            problems.append(f"{path}: missing source target")
            continue
        candidates = [path] if path.is_file() else path.rglob("*.py")
        files.update(
            candidate
            for candidate in candidates
            if candidate.suffix == ".py"
            and not excluded.intersection(candidate.relative_to(path).parts)
        )
    return sorted(files), problems


if __name__ == "__main__":
    raise SystemExit(main())
