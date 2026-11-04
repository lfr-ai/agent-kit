# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check Python convention invariants in explicit paths without importing them.

Rules (``bool-trap``, ``magic-number``, ``redundant-default``, and the ``docstring-*``
contract rules below are opt-in; others default on):

- ``docstring-backtick``: inline code uses paired double-backtick literals.
- ``any-cast``: no ``typing.Any`` or ``typing.cast``, imported or attribute-accessed.
- ``logging-import``: use ``import logging``, not names imported from it.
- ``quoted-annotation``: no string-literal argument, return, or variable annotations.
- ``private-constant``: ``_UPPER`` module constants are unannotated or ``Final``.
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
- ``docstring-args``: explanatory initializer prose names every parameter in double
  backticks, or uses ``Args:``; any ``Args:`` header is unindented and lists each
  parameter in signature order (enable
  the docstring rules with ``--docstrings``).
- ``docstring-args-type``: each ``Args:`` entry reads ``name (type): meaning`` where
  ``type`` equals the unparsed annotation (whitespace and quotes normalised).
- ``docstring-returns``: a multi-line docstring for a tuple of two or more elements,
  mapping, nested generic, ``Callable``, or union of two or more non-``None`` types
  needs ``Returns:``; a one-line summary may state the shape instead (generators
  document ``Yields:``; ``TypeGuard``/``TypeIs`` are bool-like).
- ``docstring-returns-none``: ``Returns:`` is not allowed on ``-> None``.

The docstring rules exempt test modules, dunder methods other than ``__init__``,
``@overload`` stubs, properties, and ``@override`` methods. Missing docstrings
outside parameterized initializers are left to the project's documentation linter.
Concision and caller-relevant detail need review, not a parameter-count heuristic.
"""

import argparse
import ast
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePath
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
_DOCSTRING_RULES = frozenset(
    {
        "docstring-args",
        "docstring-args-type",
        "docstring-returns",
        "docstring-returns-none",
    }
)
ALL_RULES = (
    _DEFAULT_RULES
    | _DOCSTRING_RULES
    | {"bool-trap", "magic-number", "redundant-default"}
)
_RECEIVERS = frozenset({"self", "cls"})
_EXEMPT_DECORATORS = frozenset(
    {
        "overload",
        "property",
        "cached_property",
        "override",
        "setter",
        "getter",
        "deleter",
    }
)
_MAPPING_NAMES = frozenset(
    {"dict", "Dict", "Mapping", "MutableMapping", "OrderedDict", "defaultdict"}
)
_TUPLE_NAMES = frozenset({"tuple", "Tuple"})
_MULTI_FIELD_TUPLE_LENGTH = 2
_PREDICATE_NAMES = frozenset({"TypeGuard", "TypeIs"})
_SECTION_HEADER = re.compile(
    r"^(Args|Returns|Yields|Raises|Attributes|Examples?|Notes?|Todo|Warnings?"
    r"|References|See Also|Keyword Args|Other Parameters):\s*$",
    re.MULTILINE,
)
_REFERENCE_SECTIONS = frozenset({"Example", "Examples", "References", "See Also"})
_INDENTED_ARGS_HEADER = re.compile(r"^[ \t]+Args:\s*$", re.MULTILINE)
_ENTRY = re.compile(r"^(\*{0,2}\w+)\s*(.*)$")
_NAMED_NUMBERS = frozenset({0, 1, -1})
_CONSTANT_NAME = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
_TYPE_FIELDS = frozenset({"annotation", "returns"})


def violations(
    text: str, path: str, *, rules: frozenset[str] = _DEFAULT_RULES
) -> list[str]:
    """Find concrete convention defects without executing the target module.

    Args:
        text (str): Python source text.
        path (str): Display path used as the finding prefix.
        rules (frozenset[str]): Rule names to apply; defaults exclude the opt-in rules.

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
    findings.extend(_contract_lines(tree, path, rules))
    return [f"{path}:{line}: {message}" for line, message in sorted(findings)]


def _contract_lines(
    tree: ast.Module, path: str, rules: frozenset[str]
) -> Iterator[tuple[int, str]]:
    if not rules & _DOCSTRING_RULES:
        return
    for rule, line, message in _contract_findings(tree, path):
        if rule in rules:
            yield line, message


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
    return all(_is_constant_target(target) for target in targets)


def _is_constant_target(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return _CONSTANT_NAME.match(target.id) is not None
    if isinstance(target, ast.Tuple | ast.List):
        return all(_is_constant_target(item) for item in target.elts)
    if isinstance(target, ast.Starred):
        return _is_constant_target(target.value)
    return False


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
        and not _is_final(node.annotation)
    ):
        yield (
            "private-constant",
            node.lineno,
            "internal constant must be unannotated or Final",
        )


def _is_final(annotation: ast.expr) -> bool:
    target = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    label = target.id if isinstance(target, ast.Name) else _attribute_name(target)
    return label == "Final"


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


def _contract_findings(tree: ast.Module, path: str) -> Iterator[tuple[str, int, str]]:
    if not _is_test_module(path):
        for node in ast.walk(tree):
            if isinstance(node, _FUNCTIONS):
                yield from _callable_findings(node)


def _is_test_module(path: str) -> bool:
    parts = PurePath(path)
    return (
        parts.name.startswith("test_")
        or parts.name.endswith("_test.py")
        or parts.name == "conftest.py"
        or "tests" in parts.parts
    )


def _is_exempt(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    name = function.name
    if name.startswith("__") and name.endswith("__") and name != "__init__":
        return True
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        label = target.id if isinstance(target, ast.Name) else _attribute_name(target)
        if label in _EXEMPT_DECORATORS:
            return True
    return False


def _attribute_name(node: ast.expr) -> str:
    return node.attr if isinstance(node, ast.Attribute) else ""


def _parameters(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, ast.arg]]:
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    if positional and positional[0].arg in _RECEIVERS:
        positional = positional[1:]
    items = [(argument.arg, argument) for argument in positional]
    if arguments.vararg:
        items.append((f"*{arguments.vararg.arg}", arguments.vararg))
    items.extend((argument.arg, argument) for argument in arguments.kwonlyargs)
    if arguments.kwarg:
        items.append((f"**{arguments.kwarg.arg}", arguments.kwarg))
    return items


def _callable_findings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[tuple[str, int, str]]:
    if _is_exempt(function):
        return
    parameters = _parameters(function)
    docstring = ast.get_docstring(function)
    sections = _sections(docstring or "")
    prose = "\n".join(
        line
        for section, lines in sections.items()
        if section not in _REFERENCE_SECTIONS
        for line in lines
    )
    needs_args = function.name == "__init__" and any(
        f"``{label}``" not in prose for label, _ in parameters
    )
    if docstring is None:
        if needs_args:
            yield (
                "docstring-args",
                function.lineno,
                f"'{function.name}' needs a docstring documenting its parameters",
            )
        return
    if _INDENTED_ARGS_HEADER.search(prose):
        yield (
            "docstring-args",
            function.lineno,
            "Args: header must align with the docstring's explanatory prose",
        )
    if needs_args or "Args" in sections:
        yield from _args_findings(function, parameters, sections)
    yield from _returns_findings(
        function, sections, one_line="\n" not in docstring.strip()
    )


def _sections(docstring: str) -> dict[str, list[str]]:
    sections = {"": _SECTION_HEADER.split(docstring, maxsplit=1)[0].splitlines()}
    current: list[str] | None = None
    for line in docstring.splitlines():
        header = _SECTION_HEADER.match(line)
        if header:
            current = sections.setdefault(header.group(1), [])
        elif current is not None and line[:1].strip():
            current = None
        elif current is not None:
            current.append(line)
    return sections


def _args_findings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameters: list[tuple[str, ast.arg]],
    sections: dict[str, list[str]],
) -> Iterator[tuple[str, int, str]]:
    expected = [label for label, _ in parameters]
    if "Args" not in sections:
        yield (
            "docstring-args",
            function.lineno,
            f"document {expected} in prose with double backticks or add Args:",
        )
        return
    documented = _documented_args(sections["Args"])
    if [label for label, _ in documented] != expected:
        found = [label for label, _ in documented]
        message = f"Args must list {expected} in signature order; found {found}"
        yield "docstring-args", function.lineno, message
        return
    for (label, argument), (_, doc_type) in zip(parameters, documented, strict=True):
        if argument.annotation is None:
            continue
        want = _normalise_type(ast.unparse(argument.annotation))
        if doc_type is None or _normalise_type(doc_type) != want:
            yield (
                "docstring-args-type",
                function.lineno,
                f"Args entry '{label}' must read '{label} ({want}): ...'",
            )


def _documented_args(lines: list[str]) -> list[tuple[str, str | None]]:
    body = [line for line in lines if line.strip()]
    if not body:
        return []
    indent = len(body[0]) - len(body[0].lstrip())
    entries = (
        _parse_entry(line.strip())
        for line in body
        if len(line) - len(line.lstrip()) == indent
    )
    return [entry for entry in entries if entry is not None]


def _parse_entry(text: str) -> tuple[str, str | None] | None:
    match = _ENTRY.match(text)
    if match is None:
        return None
    name, rest = match.groups()
    if rest.startswith(":"):
        return name, None
    if not rest.startswith("("):
        return None
    depth = 0
    for index, character in enumerate(rest):
        depth += character == "("
        depth -= character == ")"
        if depth == 0:
            return name, rest[1:index]
    return None


def _normalise_type(text: str) -> str:
    unquoted = text.replace("'", "").replace('"', "")
    try:
        return ast.unparse(ast.parse(unquoted, mode="eval"))
    except SyntaxError:
        return " ".join(unquoted.split())


def _returns_findings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    sections: dict[str, list[str]],
    *,
    one_line: bool,
) -> Iterator[tuple[str, int, str]]:
    returns = function.returns
    if returns is None:
        return
    described = any(line.strip() for line in sections.get("Returns", []))
    if isinstance(returns, ast.Constant) and returns.value is None:
        if "Returns" in sections:
            yield (
                "docstring-returns-none",
                function.lineno,
                "remove Returns: from a function annotated -> None",
            )
    elif not described and not one_line and _requires_returns(function):
        yield (
            "docstring-returns",
            function.lineno,
            "structured return type needs Returns: describing its shape",
        )


def _requires_returns(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    returns = function.returns
    return (
        returns is not None
        and not (isinstance(returns, ast.Constant) and returns.value is None)
        and _is_structured(returns)
        and not _yields(function)
    )


def _yields(node: ast.AST) -> bool:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Yield | ast.YieldFrom):
            return True
        if not isinstance(child, (*_FUNCTIONS, ast.Lambda, ast.ClassDef)) and _yields(
            child
        ):
            return True
    return False


def _is_structured(annotation: ast.expr) -> bool:
    members = _union_members(annotation)
    if len(members) != 1:
        return len(members) > 1
    member = members[0]
    base = _base_name(member)
    if base in _PREDICATE_NAMES:
        return False
    if base in _MAPPING_NAMES or base == "Callable":
        return True
    if base in _TUPLE_NAMES and isinstance(member, ast.Subscript):
        elements = _elements(member.slice)
        if len(elements) >= _MULTI_FIELD_TUPLE_LENGTH and not any(
            isinstance(item, ast.Constant) and item.value is Ellipsis
            for item in elements
        ):
            return True
    return isinstance(member, ast.Subscript) and any(
        isinstance(item, ast.Subscript) for item in ast.walk(member.slice)
    )


def _elements(node: ast.expr) -> list[ast.expr]:
    return list(node.elts) if isinstance(node, ast.Tuple) else [node]


def _base_name(node: ast.expr) -> str:
    target = node.value if isinstance(node, ast.Subscript) else node
    return target.id if isinstance(target, ast.Name) else _attribute_name(target)


def _union_members(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return [node]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_union_members(node.left), *_union_members(node.right)]
    if isinstance(node, ast.Subscript) and _base_name(node) in {"Union", "Optional"}:
        return [
            member
            for element in _elements(node.slice)
            for member in _union_members(element)
        ]
    if isinstance(node, ast.Constant) and node.value is None:
        return []
    return [node]


def collect(
    paths: Iterable[Path], *, excluded: frozenset[str], templates: bool = False
) -> tuple[list[Path], list[str]]:
    """Expand explicit targets into Python files, rejecting missing or linked paths.

    Args:
        paths (Iterable[Path]): Files or directories named by the caller.
        excluded (frozenset[str]): Directory names skipped during recursion.
        templates (bool): Scan production Python templates instead of Python modules.

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
    """Scan ``argv`` targets (default ``sys.argv[1:]``); return ``1`` on any finding."""
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
        "--docstrings",
        action="store_true",
        help="also enforce the docstring-* rules (Args and Returns)",
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
        | (_DOCSTRING_RULES if args.docstrings else set())
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
        sys.stderr.write(f"{finding}\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
