# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Flag Cypher built by string formatting and unbounded read queries.

Input: Python files, ``*.cypher`` files, or directories. ``--templates`` also
scans ``*.py.template`` and ``*.cypher.template``. Python is parsed with
``ast`` and never imported.

Rules:

- ``formatted-cypher``: query text given to ``run``, ``execute_query``, or
  ``Query`` (first positional argument or the ``query``, ``query_``, or ``text``
  keyword) is an f-string with placeholders, ``+`` concatenation, ``%``
  formatting, or ``str.format``, directly or through a name assigned from one in
  the same scope. For ``run`` the literal fragments must contain an upper-case
  Cypher clause keyword, so ``subprocess.run(f"...")`` is ignored.
  ``UPPER_CASE`` names count as reviewed constants.
- ``unbounded-read``: a read query (``MATCH`` and ``RETURN`` without a write
  clause) has no ``LIMIT``, does not return aggregates only, and is not a
  single-node lookup by a parameter; or any query has a variable-length
  relationship without an upper bound (``*``, ``*2..``). Checked for literals
  passed to the calls above, ``UPPER_CASE`` string constants, and every
  ``;``-separated statement of a Cypher file.

Waive a reviewed finding with ``# cypher-safety: reviewed`` on the Python line
or ``// cypher-safety: reviewed`` inside the Cypher text.

Output: ``path:line: rule: message`` on stdout. Exit codes: 0 clean, 1 findings,
2 usage error or unreadable or unparsable input (stderr). ``--self-test`` runs
built-in synthetic cases instead of scanning paths.

Limits: heuristics over text; quantified path patterns, queries assembled in
other modules, and uniqueness of lookup keys are not analyzed.
"""

import argparse
import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import re
import sys

_EXIT_FINDINGS = 1
_EXIT_INPUT_ERROR = 2
_SKIPPED_DIRECTORIES = frozenset(
    {".venv", "node_modules", "apm_modules", "build", "__pycache__"}
)
_GENERIC_SINKS = frozenset({"run"})
_CYPHER_SINKS = frozenset({"execute_query", "Query"})
_QUERY_KEYWORDS = frozenset({"query", "query_", "text"})
_PYTHON_WAIVER = "# cypher-safety: reviewed"
_CYPHER_WAIVER = "// cypher-safety: reviewed"
_CONSTANT = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
_CLAUSE = re.compile(r"\b(?:MATCH|MERGE|CREATE|RETURN|UNWIND|CALL|DETACH)\b")
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_LINE_COMMENT = re.compile(r"//[^\n]*")
_MATCH = re.compile(r"\bMATCH\b", re.IGNORECASE)
_RETURN = re.compile(r"\bRETURN\b", re.IGNORECASE)
_LIMIT = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_WRITE = re.compile(
    r"\b(?:CREATE|MERGE|SET|DELETE|REMOVE|DETACH|FOREACH|LOAD\s+CSV)\b", re.IGNORECASE
)
_RELATIONSHIP = re.compile(r"-\[|\]-|--|->|<-")
_PARAMETER_LOOKUP = re.compile(r"\{[^{}]*:\s*\$\w+[^{}]*\}|=\s*\$\w+")
_AGGREGATE_ONLY = re.compile(
    r"^\s*(?:DISTINCT\s+)?(?:(?:count|sum|avg|min|max|collect)\s*\([^()]*\)"
    r"(?:\s+AS\s+\w+)?\s*(?:,\s*|$))+$",
    re.IGNORECASE,
)
_OPEN_LENGTH = re.compile(r"\*\s*(?:\d*\s*\.\.\s*)?\]")
_FORMATTED_MESSAGE = "{kind} builds Cypher for {sink}(); pass values as $parameters"
_OPEN_LENGTH_MESSAGE = "variable-length relationship without an upper bound"
_UNBOUNDED_MESSAGE = (
    "read query without LIMIT; bound it, aggregate, or seek a unique key"
)
_SELF_TEST_CASES = (
    ("tx.run(f'MATCH (n:{label}) RETURN n LIMIT 1')\n", False, ("formatted-cypher",)),
    ("tx.run('MATCH (n:A {id: $id}) RETURN n')\n", False, ()),
    ("ALL = 'MATCH (n:A) RETURN n'\n", False, ("unbounded-read",)),
    ("subprocess.run(f'echo {name}')\n", False, ()),
    ("MATCH (n:A) RETURN count(n);\n", True, ()),
    ("MATCH (a)-[:K*]->(b) RETURN b LIMIT 5;\n", True, ("unbounded-read",)),
)


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One rule violation located in a source file.

    Attributes:
        line: First line of the offending construct.
        rule: Rule name.
        message: Human-readable explanation.
    """

    line: int
    rule: str
    message: str


def check_cypher(text: str) -> list[Finding]:
    """Return unbounded-read findings for Cypher text holding one or more statements.

    Args:
        text: Cypher source; statements are separated by semicolons.

    Returns:
        Findings ordered by line; line 1 is the first line of ``text``.
    """
    findings: list[Finding] = []
    line = 1
    for statement in text.split(";"):
        leading = len(statement) - len(statement.lstrip())
        start = line + statement[:leading].count("\n")
        if _CYPHER_WAIVER not in statement:
            findings.extend(
                Finding(line=start, rule="unbounded-read", message=message)
                for message in _bound_findings(statement)
            )
        line += statement.count("\n")
    return findings


def _bound_findings(statement: str) -> Iterator[str]:
    code = _STRING_LITERAL.sub("''", _LINE_COMMENT.sub("", statement))
    if _OPEN_LENGTH.search(code):
        yield _OPEN_LENGTH_MESSAGE
    is_read = _MATCH.search(code) and _RETURN.search(code) and not _WRITE.search(code)
    if is_read and not _LIMIT.search(code) and not _is_bounded_read(code):
        yield _UNBOUNDED_MESSAGE


def _is_bounded_read(code: str) -> bool:
    projection = _RETURN.split(code)[-1]
    single_node_lookup = not _RELATIONSHIP.search(code) and bool(
        _PARAMETER_LOOKUP.search(code)
    )
    return single_node_lookup or bool(_AGGREGATE_ONLY.match(projection))


def check_python(text: str, path: str) -> list[Finding]:
    """Return formatting and unbounded-read findings for one Python module.

    Args:
        text: Python source text.
        path: File name used in syntax errors.

    Returns:
        Findings ordered by line, excluding waived lines.

    Raises:
        SyntaxError: If ``text`` is not valid Python.
    """
    tree = ast.parse(text, filename=path)
    lines = text.splitlines()
    findings = [*_call_findings(tree), *_constant_findings(tree)]
    return sorted(
        (item for item in findings if _PYTHON_WAIVER not in lines[item.line - 1]),
        key=lambda item: (item.line, item.rule),
    )


def _call_findings(tree: ast.Module) -> Iterator[Finding]:
    for scope in [tree, *_functions(tree)]:
        statements = list(_scope_walk(scope))
        built = _formatted_names(statements)
        for node in statements:
            if isinstance(node, ast.Call) and (sink := _sink_name(node)):
                yield from _judge_query(node, sink, built)


def _functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def _scope_walk(scope: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(scope):
        yield child
        if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            yield from _scope_walk(child)


def _formatted_names(nodes: list[ast.AST]) -> dict[str, str]:
    assignments = [
        (target.id, node.value)
        for node in nodes
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    built: dict[str, str] = {}
    while additions := {
        name: _fragments(value, built)
        for name, value in assignments
        if name not in built and _is_formatted(value, built)
    }:
        built.update(additions)
    return built


def _sink_name(call: ast.Call) -> str | None:
    target = call.func
    name = target.id if isinstance(target, ast.Name) else None
    if isinstance(target, ast.Attribute):
        name = target.attr
    return name if name in _GENERIC_SINKS | _CYPHER_SINKS else None


def _judge_query(call: ast.Call, sink: str, built: dict[str, str]) -> Iterator[Finding]:
    query = _query_argument(call)
    if isinstance(query, ast.Constant) and isinstance(query.value, str):
        if sink in _CYPHER_SINKS or _CLAUSE.search(query.value):
            yield from _relocated(check_cypher(query.value), call.lineno)
    elif (
        query is not None
        and _is_formatted(query, built)
        and (sink in _CYPHER_SINKS or _CLAUSE.search(_fragments(query, built)))
    ):
        message = _FORMATTED_MESSAGE.format(kind=_kind(query), sink=sink)
        yield Finding(line=call.lineno, rule="formatted-cypher", message=message)


def _query_argument(call: ast.Call) -> ast.expr | None:
    if call.args:
        return call.args[0]
    return next(
        (item.value for item in call.keywords if item.arg in _QUERY_KEYWORDS), None
    )


def _constant_findings(tree: ast.Module) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value, targets = node.value, node.targets
        elif isinstance(node, ast.AnnAssign):
            value, targets = node.value, [node.target]
        else:
            continue
        named = any(
            isinstance(item, ast.Name) and _CONSTANT.match(item.id) for item in targets
        )
        if (
            named
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and _CLAUSE.search(value.value)
        ):
            yield from _relocated(check_cypher(value.value), node.lineno)


def _relocated(findings: list[Finding], line: int) -> Iterator[Finding]:
    for item in findings:
        yield Finding(line=line, rule=item.rule, message=item.message)


def _is_formatted(node: ast.expr, built: dict[str, str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in built
    if isinstance(node, ast.JoinedStr):
        return not all(_is_constant(part) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Mod):
        parts = (node.left, node.right)
        return any(_is_formatted(part, built) for part in parts) or (
            any(_is_text(part) for part in parts)
            and not all(_is_constant(part) for part in parts)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        arguments = [*node.args, *(item.value for item in node.keywords)]
        return (
            node.func.attr == "format"
            and _is_text(node.func.value)
            and not all(_is_constant(item) for item in arguments)
        )
    return False


def _is_text(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    return isinstance(node, ast.JoinedStr)


def _is_constant(node: ast.expr) -> bool:
    match node:
        case ast.Constant():
            return True
        case ast.Name(id=name):
            return _CONSTANT.match(name) is not None
        case ast.FormattedValue(value=value):
            return _is_constant(value)
        case ast.JoinedStr(values=values) | ast.Tuple(elts=values):
            return all(_is_constant(item) for item in values)
        case ast.BinOp(left=left, right=right):
            return _is_constant(left) and _is_constant(right)
        case _:
            return False


def _fragments(node: ast.expr, built: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return built.get(node.id, "")
    texts = [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]
    return " ".join(texts)


def _kind(node: ast.expr) -> str:
    if isinstance(node, ast.JoinedStr):
        return "an f-string"
    if isinstance(node, ast.BinOp):
        return "%-formatting" if isinstance(node.op, ast.Mod) else "concatenation"
    if isinstance(node, ast.Name):
        return f"name '{node.id}'"
    return "str.format()"


def self_test() -> list[str]:
    """Check both rules on in-memory Python and Cypher sources.

    Returns:
        One message per synthetic case whose rules differ from the expectation.
    """
    failures: list[str] = []
    for source, is_cypher, expected in _SELF_TEST_CASES:
        found = check_cypher(source) if is_cypher else check_python(source, "case.py")
        rules = [item.rule for item in found]
        if rules != list(expected):
            failures.append(f"expected {list(expected)} for {source!r}, got {rules}")
    return failures


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return _EXIT_FINDINGS
    sys.stdout.write("check_cypher_queries self-test passed.\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--templates",
        action="store_true",
        help="also scan *.py.template and *.cypher.template files",
    )
    parser.add_argument(
        "--exclude", action="append", default=[], help="directory name to skip"
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
    suffixes = (".py", ".cypher")
    templates = (".py.template", ".cypher.template") if args.templates else ()
    skipped = _SKIPPED_DIRECTORIES | frozenset(args.exclude)
    problems: list[str] = []
    reports = [
        report
        for path in _matching_files(args.paths, suffixes + templates, skipped, problems)
        for report in _report(path, problems)
    ]
    for report in reports:
        sys.stdout.write(f"{report}\n")
    for problem in problems:
        sys.stderr.write(f"{problem}\n")
    if problems:
        return _EXIT_INPUT_ERROR
    return _EXIT_FINDINGS if reports else 0


def _matching_files(
    roots: list[Path],
    suffixes: tuple[str, ...],
    skipped: frozenset[str],
    problems: list[str],
) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            problems.append(f"{root.as_posix()}: path does not exist")
        elif root.is_file():
            files.extend([root] if root.name.endswith(suffixes) else [])
        else:
            files.extend(
                sorted(
                    path
                    for path in root.rglob("*")
                    if path.is_file()
                    and path.name.endswith(suffixes)
                    and skipped.isdisjoint(path.relative_to(root).parts)
                )
            )
    return files


def _report(path: Path, problems: list[str]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
        is_cypher = ".cypher" in path.name
        found = check_cypher(text) if is_cypher else check_python(text, str(path))
    except (OSError, UnicodeError, SyntaxError) as error:
        problems.append(f"{path.as_posix()}: cannot parse: {error}")
        return []
    return [
        f"{path.as_posix()}:{item.line}: {item.rule}: {item.message}" for item in found
    ]


if __name__ == "__main__":
    raise SystemExit(main())
