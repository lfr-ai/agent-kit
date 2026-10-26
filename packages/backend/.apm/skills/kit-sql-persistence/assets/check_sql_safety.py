"""Flag formatted SQL text and sessions that escape a context manager.

Input: Python files or directories (``*.py``; ``--templates`` also scans
``*.py.template``). Sources are parsed with ``ast`` and never imported.

Rules:

- ``formatted-sql``: an f-string, ``+`` concatenation, ``%`` formatting, or
  ``str.format`` call reaches ``text()`` or a statement-executing method
  (``execute``, ``executemany``, ``executescript``, ``exec_driver_sql``,
  ``scalar``, ``scalars``, ``stream``, ``stream_scalars``), directly or through a
  local name assigned from such an expression in the same function or module
  body. ``UPPER_CASE`` names are treated as reviewed constants.
- ``unmanaged-session``: ``Session(...)``, ``AsyncSession(...)``, or a session
  factory call (a name bound to ``sessionmaker``/``async_sessionmaker`` in the
  module, or a callee named ``*session_factory``, ``*session_maker``, or
  ``SessionLocal``) is neither the context expression of ``with``/``async with``
  nor an argument of ``enter_context``/``enter_async_context``. Calls inside
  ``__enter__`` or ``__aenter__`` are exempt: that context manager owns the session.

Waive a reviewed line with a trailing ``# sql-safety: reviewed`` comment.

Output: ``path:line: rule: message`` on stdout, sorted per file. Exit codes:
0 clean, 1 findings, 2 usage error or unreadable or unparsable input (stderr).
``--self-test`` runs built-in synthetic cases instead of scanning paths.

Limits: data flow covers simple assignments within one scope; SQL assembled in
another module, by helper calls, or through attributes is not traced.
"""

import argparse
import ast
from collections.abc import Iterable, Iterator
from pathlib import Path
import re
import sys

_EXIT_FINDINGS = 1
_EXIT_INPUT_ERROR = 2
_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_SQL_METHODS = frozenset(
    {
        "execute",
        "executemany",
        "executescript",
        "exec_driver_sql",
        "scalar",
        "scalars",
        "stream",
        "stream_scalars",
    }
)
_SQL_KEYWORDS = frozenset({"statement", "sql", "text"})
_SESSION_CLASSES = frozenset({"Session", "AsyncSession"})
_FACTORY_BUILDERS = frozenset({"sessionmaker", "async_sessionmaker"})
_FACTORY_NAME = re.compile(
    r"(?:^|_)session_?(?:factory|maker)$|^SessionLocal$", re.IGNORECASE
)
_CONTEXT_REGISTRARS = frozenset({"enter_context", "enter_async_context"})
_LIFECYCLE_METHODS = frozenset({"__enter__", "__aenter__"})
_CONSTANT_NAME = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
_WAIVER = "# sql-safety: reviewed"
_FORMATTED_MESSAGE = (
    "{kind} reaches {sink}(); bind values as parameters and allow-list identifiers"
)
_SESSION_MESSAGE = (
    "session created outside a context manager; open it with "
    "'with' or 'async with' so it always closes"
)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)

type _Finding = tuple[int, int, str, str]

_SELF_TEST_CASES = (
    ("session.execute(text(f'SELECT {a}'))\n", ("formatted-sql",)),
    ("q = 'SELECT ' + a\ncursor.execute(q)\n", ("formatted-sql",)),
    ("session.execute(text('SELECT :a'), {'a': a})\n", ()),
    ("session.execute(text(f'SELECT {a}'))  # sql-safety: reviewed\n", ()),
    ("s = Session(engine)\n", ("unmanaged-session",)),
    ("with Session(engine) as s:\n    pass\n", ()),
)


def check_source(text: str, path: str) -> list[str]:
    """Return findings for one module.

    Args:
        text: Python source text.
        path: Display path used as the finding prefix.

    Returns:
        Findings formatted as ``path:line: rule: message``, sorted by line.

    Raises:
        SyntaxError: If ``text`` is not valid Python.
    """
    tree = ast.parse(text, filename=path)
    lines = text.splitlines()
    findings = {*_formatted_sql(tree), *_unmanaged_sessions(tree)}
    return [
        f"{path}:{line}: {rule}: {message}"
        for line, end, rule, message in sorted(findings)
        if not any(_WAIVER in row for row in lines[line - 1 : end])
    ]


def _formatted_sql(tree: ast.Module) -> Iterator[_Finding]:
    scopes: list[ast.AST] = [
        tree,
        *(n for n in ast.walk(tree) if isinstance(n, _FUNCTIONS)),
    ]
    for scope in scopes:
        nodes = list(_own_nodes(scope))
        tainted = _tainted_names(nodes)
        for node in nodes:
            if not isinstance(node, ast.Call):
                continue
            sink = _sql_sink(node)
            argument = _statement_argument(node) if sink else None
            kind = _formatting_kind(argument, tainted) if argument else None
            if sink and kind:
                message = _FORMATTED_MESSAGE.format(kind=kind, sink=sink)
                end = node.end_lineno or node.lineno
                yield node.lineno, end, "formatted-sql", message


def _own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, (*_FUNCTIONS, ast.Lambda)):
            pending.extend(ast.iter_child_nodes(node))


def _tainted_names(nodes: Iterable[ast.AST]) -> set[str]:
    assignments = [item for node in nodes for item in _assignments(node)]
    tainted: set[str] = set()
    changed = True
    while changed:
        before = len(tainted)
        tainted.update(
            name for name, value in assignments if _formatting_kind(value, tainted)
        )
        changed = len(tainted) != before
    return tainted


def _assignments(node: ast.AST) -> Iterator[tuple[str, ast.expr]]:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                yield target.id, node.value
    elif isinstance(node, ast.AnnAssign | ast.AugAssign) and isinstance(
        node.target, ast.Name
    ):
        value = _assigned_value(node)
        if value is not None:
            yield node.target.id, value


def _assigned_value(node: ast.AnnAssign | ast.AugAssign) -> ast.expr | None:
    if isinstance(node, ast.AnnAssign):
        return node.value
    # ``sql += fragment`` extends earlier text, so judge it as ``"" + fragment``.
    prefix = ast.Constant(value="") if isinstance(node.op, ast.Add) else node.target
    return ast.BinOp(left=prefix, op=node.op, right=node.value)


def _sql_sink(call: ast.Call) -> str | None:
    function = call.func
    if isinstance(function, ast.Name) and function.id == "text":
        return "text"
    if isinstance(function, ast.Attribute) and (
        function.attr in _SQL_METHODS or function.attr == "text"
    ):
        return function.attr
    return None


def _statement_argument(call: ast.Call) -> ast.expr | None:
    if call.args:
        return call.args[0]
    return next(
        (item.value for item in call.keywords if item.arg in _SQL_KEYWORDS), None
    )


def _formatting_kind(node: ast.expr, tainted: set[str]) -> str | None:
    if isinstance(node, ast.Name):
        return f"name '{node.id}' built by formatting" if node.id in tainted else None
    if isinstance(node, ast.JoinedStr):
        return "an f-string" if not _is_static(node) else None
    if isinstance(node, ast.BinOp):
        return _binary_kind(node, tainted)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and _is_string(node.func.value)
    ):
        arguments = [*node.args, *(item.value for item in node.keywords)]
        return None if all(map(_is_static, arguments)) else "str.format()"
    return None


def _binary_kind(node: ast.BinOp, tainted: set[str]) -> str | None:
    if isinstance(node.op, ast.Mod) and _is_string(node.left):
        return None if _is_static(node.right) else "%-formatting"
    if not isinstance(node.op, ast.Add):
        return None
    if _formatting_kind(node.left, tainted) or _formatting_kind(node.right, tainted):
        return "concatenation"
    involves_text = _is_string(node.left) or _is_string(node.right)
    static = _is_static(node.left) and _is_static(node.right)
    return "concatenation" if involves_text and not static else None


def _is_string(node: ast.expr) -> bool:
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _is_static(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return _CONSTANT_NAME.match(node.id) is not None
    if isinstance(node, ast.FormattedValue):
        return _is_static(node.value)
    if isinstance(node, ast.JoinedStr | ast.Tuple):
        items = node.values if isinstance(node, ast.JoinedStr) else node.elts
        return all(map(_is_static, items))
    if isinstance(node, ast.BinOp):
        return _is_static(node.left) and _is_static(node.right)
    return False


def _unmanaged_sessions(tree: ast.Module) -> Iterator[_Finding]:
    factories = _factory_names(tree)
    managed = _managed_calls(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and id(node) not in managed
            and _creates_session(node, factories)
        ):
            end = node.end_lineno or node.lineno
            yield node.lineno, end, "unmanaged-session", _SESSION_MESSAGE


def _callee(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _factory_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and _callee(node.value) in _FACTORY_BUILDERS
        ):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return names


def _managed_calls(tree: ast.Module) -> set[int]:
    managed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With | ast.AsyncWith):
            managed.update(id(item.context_expr) for item in node.items)
        elif isinstance(node, ast.Call) and _callee(node) in _CONTEXT_REGISTRARS:
            managed.update(id(argument) for argument in node.args)
        elif isinstance(node, _FUNCTIONS) and node.name in _LIFECYCLE_METHODS:
            managed.update(id(inner) for inner in ast.walk(node))
    return managed


def _creates_session(call: ast.Call, factories: set[str]) -> bool:
    name = _callee(call)
    if name is None or name in _FACTORY_BUILDERS:
        return False
    return (
        name in _SESSION_CLASSES
        or name in factories
        or _FACTORY_NAME.search(name) is not None
    )


def self_test() -> list[str]:
    """Check both rules on in-memory sources and return unmet expectations.

    Returns:
        One message per synthetic case whose rules differ from the expectation.
    """
    failures: list[str] = []
    for source, expected in _SELF_TEST_CASES:
        rules = [finding.split(": ")[1] for finding in check_source(source, "case.py")]
        if rules != list(expected):
            failures.append(f"expected {list(expected)} for {source!r}, got {rules}")
    return failures


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return _EXIT_FINDINGS
    print("check_sql_safety self-test passed.")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--templates", action="store_true", help="also scan *.py.template files"
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="additional directory name to skip (repeatable)",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Scan files or directories and print every finding.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Zero without findings, one with findings, two for unusable input.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.paths:
        parser.error("at least one path is required without --self-test")
    errors: list[str] = []
    excluded = _EXCLUDED | set(args.exclude)
    sources = _sources(args.paths, excluded, templates=args.templates, errors=errors)
    findings = [finding for path in sources for finding in _check_file(path, errors)]
    for finding in findings:
        print(finding)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return _EXIT_INPUT_ERROR
    return _EXIT_FINDINGS if findings else 0


def _check_file(path: Path, errors: list[str]) -> list[str]:
    try:
        return check_source(path.read_text(encoding="utf-8"), path.as_posix())
    except (OSError, UnicodeError, SyntaxError) as error:
        errors.append(f"{path.as_posix()}: cannot parse: {error}")
        return []


def _sources(
    paths: Iterable[Path],
    excluded: frozenset[str],
    *,
    templates: bool,
    errors: list[str],
) -> list[Path]:
    suffixes = (".py", ".py.template") if templates else (".py",)
    found: set[Path] = set()
    for root in paths:
        if not root.exists():
            errors.append(f"{root.as_posix()}: path does not exist")
            continue
        candidates = [root] if root.is_file() else root.rglob("*")
        found.update(
            candidate
            for candidate in candidates
            if candidate.is_file()
            and candidate.name.endswith(suffixes)
            and not excluded.intersection(candidate.relative_to(root).parts)
        )
    return sorted(found)


if __name__ == "__main__":
    raise SystemExit(main())
