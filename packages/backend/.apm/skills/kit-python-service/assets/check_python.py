"""Check Python convention invariants in explicit paths without importing them.

Rules (``bool-trap``, ``magic-number``, and ``redundant-default`` are opt-in;
others default on):

- ``docstring-backtick``: inline code uses paired double-backtick literals.
- ``any-cast``: no ``typing.Any`` or ``typing.cast``, imported or attribute-accessed.
- ``logging-import``: use ``import logging``, not names imported from it.
- ``quoted-annotation``: no string-literal argument, return, or variable annotations.
- ``private-constant``: ``_UPPER`` module constants are unannotated.
- ``initializer-return``: ``__init__`` and ``__post_init__`` declare ``-> None``.
- ``dataclass-kw-only``: dataclasses pass ``kw_only=True``.
- ``dataclass-frozen-slots``: frozen dataclasses also pass ``slots=True``.
- ``bare-except``: no bare ``except:`` clause.
- ``bool-trap``: no positional parameter annotated ``bool`` (enable with ``--bool-trap``;
  ``test_*`` functions are exempt because pytest injects parameters by name).
- ``magic-number``: numeric literals other than ``0``, ``1``, and ``-1`` appear only in
  ``UPPER_CASE`` constant assignments (enable with ``--magic-numbers``; annotations
  are exempt). Leave test expectations to the test style rules.
- ``redundant-default``: a call to a function or class defined once at module level
  passes a keyword argument equal to that parameter's default (a literal, an
  ``UPPER_CASE`` constant, or a ``Class.MEMBER`` reference); omit the argument
  (enable with ``--redundant-defaults``). Methods and imported callees are not traced.
"""

import argparse
import ast
from collections.abc import Iterable, Iterator
from pathlib import Path
import re
import sys

_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_BACKTICK = "\N{GRAVE ACCENT}"
_DOUBLE_BACKTICK_SPAN = re.compile(r"``(?=\S)[^`\n]*?(?<=\S)``")
_SINGLE_QUOTED_SPAN = re.compile(r"(?<![\w'])'([^'\n]+)'(?![\w'])")
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
ALL_RULES = _DEFAULT_RULES | {"bool-trap", "magic-number", "redundant-default"}
_NAMED_NUMBERS = frozenset({0, 1, -1})
_CONSTANT_NAME = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
_TYPE_FIELDS = frozenset({"annotation", "returns"})


def violations(
    text: str, path: str, *, rules: frozenset[str] = _DEFAULT_RULES
) -> list[str]:
    """Find concrete convention defects without executing the target module.

    Args:
        text: Python source text.
        path: Display path used as the finding prefix.
        rules: Rule names to apply; defaults exclude the opt-in rules.

    Returns:
        Findings formatted as ``path:line: message``, sorted by line.
    """
    tree = ast.parse(text, filename=path)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for rule, line, message in _node_findings(node):
            if rule in rules:
                findings.append((line, message))
    if "magic-number" in rules:
        findings.extend(
            (
                line,
                f"magic number {value!r}; name it as an UPPER_CASE constant",
            )
            for line, value in _magic_numbers(tree, named=False)
        )
    if "redundant-default" in rules:
        findings.extend(_redundant_defaults(tree))
    return [f"{path}:{line}: {message}" for line, message in sorted(findings)]


def _redundant_defaults(tree: ast.Module) -> Iterator[tuple[int, str]]:
    defaults = _module_defaults(tree)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        known = defaults.get(node.func.id, {})
        for keyword in node.keywords:
            default = known.get(keyword.arg or "")
            if default is not None and ast.dump(keyword.value) == default:
                argument = f"{keyword.arg}={ast.unparse(keyword.value)}"
                message = f"argument {argument} repeats the default of "
                yield keyword.value.lineno, f"{message}'{node.func.id}'; omit it"


def _module_defaults(tree: ast.Module) -> dict[str, dict[str, str]]:
    definitions: dict[str, list[ast.stmt]] = {}
    for statement in tree.body:
        for name in _defined_names(statement):
            definitions.setdefault(name, []).append(statement)
    return {
        name: _callable_defaults(statements[0])
        for name, statements in definitions.items()
        if len(statements) == 1
    }


def _callable_defaults(statement: ast.stmt) -> dict[str, str]:
    if isinstance(statement, _FUNCTIONS):
        return _parameter_defaults(statement)
    if isinstance(statement, ast.ClassDef):
        return _class_defaults(statement)
    return {}


def _defined_names(statement: ast.stmt) -> Iterator[str]:
    if isinstance(statement, (*_FUNCTIONS, ast.ClassDef)):
        yield statement.name
    elif isinstance(statement, ast.Assign | ast.AnnAssign | ast.AugAssign):
        targets = statement.targets if isinstance(statement, ast.Assign) else []
        if not isinstance(statement, ast.Assign):
            targets = [statement.target]
        yield from (item.id for item in targets if isinstance(item, ast.Name))


def _parameter_defaults(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, str]:
    arguments = function.args
    # Defaults align with the tail of positional-only plus ordinary parameters.
    positional = [*arguments.posonlyargs, *arguments.args]
    defaulted = positional[len(positional) - len(arguments.defaults) :]
    positional_only = {argument.arg for argument in arguments.posonlyargs}
    pairs = [
        *zip(defaulted, arguments.defaults, strict=True),
        *zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True),
    ]
    return {
        argument.arg: ast.dump(default)
        for argument, default in pairs
        if default is not None
        and argument.arg not in positional_only
        and _is_simple_default(default)
    }


def _class_defaults(node: ast.ClassDef) -> dict[str, str]:
    if not any(_is_dataclass_decorator(item) for item in node.decorator_list):
        initializer = next(
            (
                item
                for item in node.body
                if isinstance(item, ast.FunctionDef) and item.name == "__init__"
            ),
            None,
        )
        return _parameter_defaults(initializer) if initializer else {}
    defaults: dict[str, str] = {}
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            value = _field_default(item.value)
            if value is not None and _is_simple_default(value):
                defaults[item.target.id] = ast.dump(value)
    return defaults


def _is_dataclass_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (isinstance(target, ast.Name) and target.id == "dataclass") or (
        isinstance(target, ast.Attribute) and target.attr == "dataclass"
    )


def _field_default(value: ast.expr | None) -> ast.expr | None:
    if not (isinstance(value, ast.Call) and _callee_name(value) == "field"):
        return value
    return next((item.value for item in value.keywords if item.arg == "default"), None)


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def _is_simple_default(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return isinstance(node.operand, ast.Constant)
    if isinstance(node, ast.Name):
        return _CONSTANT_NAME.match(node.id) is not None
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id[:1].isupper()
    )


def _magic_numbers(
    node: ast.AST, *, named: bool
) -> Iterator[tuple[int, int | float | complex]]:
    if isinstance(node, ast.expr) and (number := _numeric_value(node)) is not None:
        if not named and number not in _NAMED_NUMBERS:
            yield node.lineno, number
        return
    named = named or _assigns_constant(node)
    for child in _value_children(node):
        yield from _magic_numbers(child, named=named)


def _value_children(node: ast.AST) -> Iterator[ast.AST]:
    for field, value in ast.iter_fields(node):
        if field in _TYPE_FIELDS:
            continue
        for child in value if isinstance(value, list) else [value]:
            if isinstance(child, ast.AST):
                yield child


def _numeric_value(node: ast.expr) -> int | float | complex | None:
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        node = node.operand
    if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
        return None
    value = node.value
    return sign * value if isinstance(value, int | float | complex) else None


def _assigns_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        targets = [node.target]
    else:
        return False
    names = [
        item
        for target in targets
        for item in (target.elts if isinstance(target, ast.Tuple) else [target])
    ]
    return all(
        isinstance(name, ast.Name) and _CONSTANT_NAME.match(name.id) for name in names
    )


def _node_findings(node: ast.AST) -> Iterator[tuple[str, int, str]]:
    yield from _docstring_findings(node)
    yield from _reference_findings(node)
    yield from _definition_findings(node)


def _reference_findings(node: ast.AST) -> Iterator[tuple[str, int, str]]:
    if isinstance(node, ast.ImportFrom):
        yield from _import_findings(node)
    elif isinstance(node, ast.Attribute):
        yield from _attribute_findings(node)
    elif isinstance(node, ast.arg) and _is_string(node.annotation):
        yield "quoted-annotation", node.lineno, "quoted argument annotation"
    elif isinstance(node, ast.AnnAssign):
        yield from _annotated_assignment_findings(node)


def _definition_findings(node: ast.AST) -> Iterator[tuple[str, int, str]]:
    if isinstance(node, _FUNCTIONS):
        yield from _function_findings(node)
    elif isinstance(node, ast.ClassDef):
        yield from _dataclass_findings(node)
    elif isinstance(node, ast.ExceptHandler) and node.type is None:
        yield "bare-except", node.lineno, "bare 'except:' catches every exception"


def _docstring_findings(node: ast.AST) -> Iterator[tuple[str, int, str]]:
    if not isinstance(node, _DOCUMENTED):
        return
    docstring = ast.get_docstring(node, clean=False) or ""
    unmarked = _DOUBLE_BACKTICK_SPAN.sub("", docstring)
    if _BACKTICK in unmarked or _SINGLE_QUOTED_SPAN.search(unmarked):
        line = 1 if isinstance(node, ast.Module) else node.lineno
        yield (
            "docstring-backtick",
            line,
            "use paired double backticks for docstring code; avoid single-quoted tokens",
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
    yield from _bool_trap_findings(node)


def _bool_trap_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[tuple[str, int, str]]:
    if node.name.startswith("test_"):
        return
    for argument in [*node.args.posonlyargs, *node.args.args]:
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
        if not _is_dataclass_decorator(decorator):
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
    paths: Iterable[Path], *, excluded: frozenset[str], templates: bool = False
) -> tuple[list[Path], list[str]]:
    """Expand explicit targets into Python files, rejecting missing or linked paths.

    Args:
        paths: Files or directories named by the caller.
        excluded: Directory names skipped during recursion.
        templates: Scan production Python templates instead of Python modules.

    Returns:
        Sorted unique Python files and findings for unusable targets.
    """
    files: set[Path] = set()
    problems: list[str] = []
    for path in paths:
        if not path.exists() or path.is_symlink():
            problems.append(f"{path}: missing or linked source target")
            continue
        files.update(_source_files(path, excluded=excluded, templates=templates))
    return sorted(files), problems


def _source_files(
    path: Path, *, excluded: frozenset[str], templates: bool
) -> Iterator[Path]:
    pattern = "*.py.template" if templates else "*.py"
    candidates = [path] if path.is_file() else path.rglob(pattern)
    for candidate in candidates:
        if (
            _is_source(candidate, templates=templates)
            and not candidate.is_symlink()
            and not excluded.intersection(candidate.relative_to(path).parts)
        ):
            yield candidate


def _is_source(path: Path, *, templates: bool) -> bool:
    if not templates:
        return path.suffix == ".py"
    return (
        path.name.endswith(".py.template")
        and not path.name.startswith("test_")
        and path.name != "conftest.py.template"
    )


def main(argv: list[str] | None = None) -> int:
    """Scan explicit source targets and report every finding.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

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
        "--only",
        action="append",
        default=[],
        choices=sorted(ALL_RULES),
        help="run only the selected rule (repeatable)",
    )
    parser.add_argument(
        "--bool-trap", action="store_true", help="also flag positional bool parameters"
    )
    parser.add_argument(
        "--magic-numbers",
        action="store_true",
        help="also flag numeric literals outside UPPER_CASE constants",
    )
    parser.add_argument(
        "--redundant-defaults",
        action="store_true",
        help="also flag keyword arguments that repeat a module-level callee's default",
    )
    parser.add_argument(
        "--templates",
        action="store_true",
        help="scan production *.py.template files instead of modules; omit test fixtures",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="additional directory name to skip (repeatable)",
    )
    args = parser.parse_args(argv)
    selected = (
        frozenset(args.only)
        if args.only
        else _DEFAULT_RULES
        | ({"bool-trap"} if args.bool_trap else set())
        | ({"magic-number"} if args.magic_numbers else set())
        | ({"redundant-default"} if args.redundant_defaults else set())
    )
    rules = selected - set(args.disable)
    files, findings = collect(
        args.paths,
        excluded=_EXCLUDED | set(args.exclude),
        templates=args.templates,
    )
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
