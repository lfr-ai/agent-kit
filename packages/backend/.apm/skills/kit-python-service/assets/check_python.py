"""Check Python convention invariants in explicit paths without importing them.

Rules (all enabled unless listed in '--disable'; 'bool-trap' is opt-in):

- 'docstring-backtick': docstring inline code uses single quotes, not backticks.
- 'any-cast': no 'typing.Any' or 'typing.cast', imported or attribute-accessed.
- 'logging-import': use 'import logging', not names imported from it.
- 'quoted-annotation': no string-literal argument, return, or variable annotations.
- 'private-constant': '_UPPER' module constants are unannotated.
- 'initializer-return': '__init__' and '__post_init__' declare '-> None'.
- 'dataclass-kw-only': dataclasses pass 'kw_only=True'.
- 'dataclass-frozen-slots': frozen dataclasses also pass 'slots=True'.
- 'bare-except': no bare 'except:' clause.
- 'bool-trap': no positional parameter annotated 'bool' (enable with '--bool-trap';
  'test_*' functions are exempt because pytest injects parameters by name).
"""

import argparse
import ast
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_BACKTICK = "\N{GRAVE ACCENT}"
_DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_FORBIDDEN_TYPING = frozenset({"Any", "cast"})
_DEFAULT_RULES = frozenset(
    {
        "docstring-backtick",
        "any-cast",
        "logging-import",
        "quoted-annotation",
        "private-constant",
        "initializer-return",
        "dataclass-kw-only",
        "dataclass-frozen-slots",
        "bare-except",
    }
)
ALL_RULES = _DEFAULT_RULES | {"bool-trap"}


def violations(
    text: str, path: str, *, rules: frozenset[str] = _DEFAULT_RULES
) -> list[str]:
    """Find concrete convention defects without executing the target module.

    Args:
        text: Python source text.
        path: Display path used as the finding prefix.
        rules: Rule names to apply; defaults to every rule except 'bool-trap'.

    Returns:
        Findings formatted as 'path:line: message', sorted by line.
    """
    tree = ast.parse(text, filename=path)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for rule, line, message in _node_findings(node):
            if rule in rules:
                findings.append((line, message))
    return [f"{path}:{line}: {message}" for line, message in sorted(findings)]


def _node_findings(node: ast.AST) -> Iterator[tuple[str, int, str]]:
    yield from _docstring_findings(node)
    if isinstance(node, ast.ImportFrom):
        yield from _import_findings(node)
    elif isinstance(node, ast.Attribute):
        yield from _attribute_findings(node)
    elif isinstance(node, ast.arg) and _is_string(node.annotation):
        yield "quoted-annotation", node.lineno, "quoted argument annotation"
    elif isinstance(node, ast.AnnAssign):
        yield from _annotated_assignment_findings(node)
    elif isinstance(node, _FUNCTIONS):
        yield from _function_findings(node)
    elif isinstance(node, ast.ClassDef):
        yield from _dataclass_findings(node)
    elif isinstance(node, ast.ExceptHandler) and node.type is None:
        yield "bare-except", node.lineno, "bare 'except:' catches every exception"


def _docstring_findings(node: ast.AST) -> Iterator[tuple[str, int, str]]:
    if isinstance(node, _DOCUMENTED) and _BACKTICK in (
        ast.get_docstring(node, clean=False) or ""
    ):
        line = 1 if isinstance(node, ast.Module) else node.lineno
        yield (
            "docstring-backtick",
            line,
            "docstring inline code uses 'single quotes', not backticks",
        )


def _import_findings(node: ast.ImportFrom) -> Iterator[tuple[str, int, str]]:
    if node.module == "typing" and any(
        item.name in _FORBIDDEN_TYPING for item in node.names
    ):
        yield "any-cast", node.lineno, "forbidden Any/cast import"
    if node.module in {"logging", "logging.handlers"}:
        yield "logging-import", node.lineno, "use qualified logging imports"


def _attribute_findings(node: ast.Attribute) -> Iterator[tuple[str, int, str]]:
    if (
        isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr in _FORBIDDEN_TYPING
    ):
        yield "any-cast", node.lineno, f"forbidden 'typing.{node.attr}' use"


def _annotated_assignment_findings(
    node: ast.AnnAssign,
) -> Iterator[tuple[str, int, str]]:
    if _is_string(node.annotation):
        yield "quoted-annotation", node.lineno, "quoted variable annotation"
    if (
        isinstance(node.target, ast.Name)
        and node.target.id.startswith("_")
        and node.target.id.isupper()
    ):
        yield (
            "private-constant",
            node.lineno,
            "internal constant must be unannotated",
        )


def _function_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[tuple[str, int, str]]:
    if _is_string(node.returns):
        yield "quoted-annotation", node.lineno, "quoted return annotation"
    if node.name in {"__init__", "__post_init__"} and not (
        isinstance(node.returns, ast.Constant) and node.returns.value is None
    ):
        yield "initializer-return", node.lineno, "initializer must declare -> None"
    positional = [*node.args.posonlyargs, *node.args.args]
    if node.name.startswith("test_"):
        positional = []
    for argument in positional:
        if argument.arg in {"self", "cls"}:
            continue
        if (
            isinstance(argument.annotation, ast.Name)
            and argument.annotation.id == "bool"
        ):
            yield (
                "bool-trap",
                argument.lineno,
                f"positional bool parameter '{argument.arg}'; make it keyword-only",
            )


def _dataclass_findings(node: ast.ClassDef) -> Iterator[tuple[str, int, str]]:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        is_dataclass = (isinstance(target, ast.Name) and target.id == "dataclass") or (
            isinstance(target, ast.Attribute) and target.attr == "dataclass"
        )
        if not is_dataclass:
            continue
        keywords = decorator.keywords if isinstance(decorator, ast.Call) else []
        if not _true_keyword(keywords, "kw_only"):
            yield "dataclass-kw-only", node.lineno, "dataclass must be keyword-only"
        if _true_keyword(keywords, "frozen") and not _true_keyword(keywords, "slots"):
            yield (
                "dataclass-frozen-slots",
                node.lineno,
                "frozen dataclass must also pass slots=True",
            )


def _true_keyword(keywords: Iterable[ast.keyword], name: str) -> bool:
    return any(
        item.arg == name
        and isinstance(item.value, ast.Constant)
        and item.value.value is True
        for item in keywords
    )


def _is_string(annotation: ast.expr | None) -> bool:
    return isinstance(annotation, ast.Constant) and isinstance(annotation.value, str)


def collect(
    paths: Iterable[Path], *, excluded: frozenset[str]
) -> tuple[list[Path], list[str]]:
    """Expand explicit targets into Python files, rejecting missing or linked paths.

    Args:
        paths: Files or directories named by the caller.
        excluded: Directory names skipped during recursion.

    Returns:
        Sorted unique Python files and findings for unusable targets.
    """
    files: set[Path] = set()
    problems: list[str] = []
    for path in paths:
        if not path.exists() or path.is_symlink():
            problems.append(f"{path}: missing or linked source target")
            continue
        candidates = [path] if path.is_file() else path.rglob("*.py")
        files.update(
            candidate
            for candidate in candidates
            if candidate.suffix == ".py"
            and not candidate.is_symlink()
            and not excluded.intersection(candidate.relative_to(path).parts)
        )
    return sorted(files), problems


def main(argv: list[str] | None = None) -> int:
    """Scan explicit source targets and report every finding.

    Args:
        argv: Command-line arguments; defaults to 'sys.argv[1:]'.

    Returns:
        Zero when no finding exists, otherwise one.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--disable",
        action="append",
        default=[],
        choices=sorted(ALL_RULES),
        help="rule name to skip (repeatable)",
    )
    parser.add_argument(
        "--bool-trap", action="store_true", help="also flag positional bool parameters"
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="additional directory name to skip (repeatable)",
    )
    args = parser.parse_args(argv)
    rules = (_DEFAULT_RULES | ({"bool-trap"} if args.bool_trap else set())) - set(
        args.disable
    )
    files, findings = collect(args.paths, excluded=_EXCLUDED | set(args.exclude))
    for path in files:
        try:
            findings.extend(
                violations(path.read_text(encoding="utf-8"), str(path), rules=rules)
            )
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{path}: source cannot be parsed")
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
