# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check explicit Python paths without executing inspected source.

Enforce concrete syntax, constant visibility, acronym casing and native enum
conventions. Optional docstring checks accept concise prose, validate supplied
typed sections, reject sections on single-parameter delegators and ``Raises:``
entries the body never raises; semantic completeness remains reviewer-owned.
Local exception ancestry is parsed, never imported; dynamic behavior is not inferred.
Policy and limits: ``../references/docstrings.md`` and ``../references/python-idioms.md``.
"""

import argparse
import ast
import builtins
from collections.abc import Collection, Iterable, Iterator
from pathlib import Path, PurePath
import re
import sys
from typing import Final

_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_BACKTICK = "\N{GRAVE ACCENT}"
_DOUBLE_BACKTICK_SPAN = re.compile(r"``(?=\S)[^`\n]*?(?<=\S)``")
_SINGLE_QUOTED_SPAN = re.compile(r"(?<![\w'])'([^'\n]+)'(?![\w'])")
_DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_FORBIDDEN_TYPING = frozenset({"Any", "cast"})
_TYPING = "typing"
_TYPING_MODULES = frozenset({_TYPING, "typing_extensions"})
_TYPE_ALIAS = "TypeAlias"
_DEFAULT_RULES = frozenset(
    {
        "docstring-backtick",
        "any-cast",
        "logging-import",
        "quoted-annotation",
        "private-constant",
        "enum-unique",
        "enum-auto",
        "initializer-return",
        "dataclass-kw-only",
        "dataclass-frozen-slots",
        "bare-except",
        "acronym-case",
    }
)
_DOCSTRING_RULES = frozenset(
    {
        "docstring-args",
        "docstring-args-type",
        "docstring-returns",
        "docstring-returns-none",
        "docstring-yields",
        "docstring-raises",
        "docstring-raises-extra",
        "docstring-missing",
        "docstring-property",
        "docstring-one-line",
        "docstring-class-sections",
    }
)
ALL_RULES: Final[frozenset[str]] = (
    _DEFAULT_RULES
    | _DOCSTRING_RULES
    | {"bool-trap", "magic-number", "redundant-default", "repeated-literal"}
)
_RECEIVERS = frozenset({"self", "cls"})
_EXEMPT_DECORATORS = frozenset(
    {
        "overload",
        "override",
    }
)
_PROPERTY_DECORATORS = frozenset({"property", "cached_property"})
_ABSTRACT_DECORATORS = frozenset({"abstractmethod"})
_ARGS = "Args"
_RETURNS = "Returns"
_STRUCTURED_SECTIONS = frozenset({_ARGS, _RETURNS, "Yields", "Raises"})
_INITIALIZER = "__init__"
# Initializers document constructor arguments even when there is only one.
_INITIALIZERS = frozenset({_INITIALIZER, "__post_init__"})
_SECTION_HEADER = re.compile(
    r"^(Args|Returns|Yields|Raises|Attributes|Examples?|Notes?|Todo|Warnings?"
    r"|References|See Also|Keyword Args|Other Parameters):\s*$",
    re.MULTILINE,
)
_TYPED_SECTION_PREFIX = re.compile(
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\[.*\])?"
    r"(?:\s*\|\s*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\[.*\])?)*\Z"
)
_REFERENCE_SECTIONS = frozenset({"Example", "Examples", "References", "See Also"})
_INDENTED_ARGS_HEADER = re.compile(r"^[ \t]+Args:\s*$", re.MULTILINE)
_ENTRY = re.compile(r"^(\*{0,2}\w+)\s*(.*)$")
_NAMED_NUMBERS = frozenset({0, 1, -1})
_EQUALITY_OPERATORS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)
# Entry guards are idiomatic, and type checkers narrow only literal comparisons
# against sys.platform; a named platform constant would hide that narrowing.
_LITERAL_SUBJECTS = frozenset({"__name__", "sys.platform"})
_CONSTANT_NAME = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
_TYPE_FIELDS = frozenset({"annotation", "returns"})
_CLOSED_ENUMS = frozenset({"Enum", "StrEnum", "IntEnum"})
_NEXT_VALUE_HOOK = "_generate_next_value_"
# Preserve acronym casing; allow short words such as Id, Db, Io and Os.
_ACRONYMS = frozenset(
    {
        "Ai",
        "Api",
        "Apm",
        "Cli",
        "Csv",
        "Dns",
        "Html",
        "Http",
        "Https",
        "Json",
        "Jwt",
        "Llm",
        "Mcp",
        "Msal",
        "Ocr",
        "Oidc",
        "Pdf",
        "Rag",
        "Sdk",
        "Smtp",
        "Smtps",
        "Sql",
        "Ssl",
        "Tcp",
        "Tls",
        "Ui",
        "Uri",
        "Url",
        "Uuid",
        "Xml",
        "Yaml",
    }
)
_ACRONYM_CASE_EXCEPTIONS = ("HttpOnly", "XMLHttpRequest")
_CAPWORDS_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+")
_TITLE_ACRONYM_PATTERNS = tuple(
    (
        acronym,
        re.compile(rf"{acronym}s?(?=[A-Z0-9]|$)"),
    )
    for acronym in sorted(_ACRONYMS, key=len, reverse=True)
)
_TYPE_FACTORIES = frozenset(
    {"TypeVar", "TypeVarTuple", "ParamSpec", "NewType", "NamedTuple", "TypedDict"}
)
_GENERATOR_TYPES = frozenset(
    {
        "Iterator",
        "Iterable",
        "Generator",
        "AsyncIterator",
        "AsyncIterable",
        "AsyncGenerator",
    }
)


def violations(
    text: str, path: str, *, rules: frozenset[str] = _DEFAULT_RULES
) -> list[str]:
    """Find concrete convention defects without executing the target module.

    Args:
        text (str): Python source text.
        path (str): Finding prefix and source location for parsing local imported
            exception classes; no inspected module is executed.
        rules (frozenset[str]): Rule names to apply; defaults exclude the opt-in rules.

    Returns:
        list[str]: Findings formatted as ``path:line: message``, sorted by line;
        unparsable source propagates ``SyntaxError`` from ``ast.parse``.
    """
    tree = ast.parse(text, filename=path)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for rule, line, message in _node_findings(node):
            if rule in rules:
                findings.append((line, message))
    findings.extend(_module_lines(tree, rules))
    findings.extend(_opt_in_lines(tree, path, rules))
    findings.extend(_contract_lines(tree, path, rules))
    return [f"{path}:{line}: {message}" for line, message in sorted(findings)]


def _module_lines(tree: ast.Module, rules: frozenset[str]) -> Iterator[tuple[int, str]]:
    if "acronym-case" in rules:
        yield from _type_alias_acronym_findings(tree)
    if "private-constant" in rules:
        yield from _constant_findings(tree)
    if rules & {"enum-unique", "enum-auto"}:
        yield from _enum_findings(tree, rules)


def _opt_in_lines(
    tree: ast.Module, path: str, rules: frozenset[str]
) -> Iterator[tuple[int, str]]:
    if "redundant-default" in rules:
        yield from _redundant_defaults(tree)
    # Test expectations keep their literals inline.
    if _is_test_module(path):
        return
    if "magic-number" in rules:
        for line, value in _magic_numbers(tree, named=False):
            yield line, f"magic number {value!r}; name it as an UPPER_CASE constant"
    if "repeated-literal" in rules:
        yield from _repeated_literals(tree)


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
                if isinstance(item, ast.FunctionDef) and item.name == _INITIALIZER
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
    return _decorator_label(decorator) == "dataclass"


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


def _repeated_literals(tree: ast.Module) -> Iterator[tuple[int, str]]:
    places: dict[str, list[tuple[int, int]]] = {}
    for node in _comparison_literals(tree, module_scope=True):
        value = _literal_value(node)
        if value is not None:
            places.setdefault(repr(value), []).append((node.lineno, node.col_offset))
    for label, positions in places.items():
        count = len(positions)
        for line, _column in sorted(positions)[1:]:
            yield line, f"literal {label} is compared {count} times; name it once"


def _comparison_literals(node: ast.AST, *, module_scope: bool) -> Iterator[ast.expr]:
    if isinstance(node, ast.JoinedStr) or (module_scope and _assigns_constant(node)):
        return
    if isinstance(node, ast.Compare) and not _is_literal_subject(node):
        yield from _equality_operands(node)
    elif isinstance(node, ast.MatchValue):
        yield node.value
    nested = module_scope and not isinstance(node, (*_FUNCTIONS, ast.ClassDef))
    for child in ast.iter_child_nodes(node):
        yield from _comparison_literals(child, module_scope=nested)


def _equality_operands(node: ast.Compare) -> Iterator[ast.expr]:
    operands = [node.left, *node.comparators]
    positions = {
        position
        for index, operator in enumerate(node.ops)
        if isinstance(operator, _EQUALITY_OPERATORS)
        for position in (index, index + 1)
    }
    for position in sorted(positions):
        operand = operands[position]
        membership = position > 0 and isinstance(
            node.ops[position - 1], ast.In | ast.NotIn
        )
        if membership and isinstance(operand, ast.Tuple | ast.List | ast.Set):
            yield from operand.elts
        else:
            yield operand


def _is_literal_subject(node: ast.Compare) -> bool:
    return any(
        _subject_name(operand) in _LITERAL_SUBJECTS
        for operand in (node.left, *node.comparators)
    )


def _subject_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _literal_value(node: ast.expr) -> str | bytes | int | float | complex | None:
    value = node.value if isinstance(node, ast.Constant) else None
    if isinstance(value, str | bytes):
        return value or None
    number = _numeric_value(node)
    return None if number in _NAMED_NUMBERS else number


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
        yield from _acronym_findings(node.name, node.lineno)
    elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
        yield from _acronym_findings(node.name.id, node.lineno)
    elif isinstance(node, ast.ExceptHandler) and node.type is None:
        yield "bare-except", node.lineno, "bare 'except:' catches every exception"


def _acronym_findings(name: str, line: int) -> Iterator[tuple[str, int, str]]:
    original_name = name
    scan_name = name.lstrip("_")
    for exception in _ACRONYM_CASE_EXCEPTIONS:
        if scan_name.startswith(exception) and (
            len(scan_name) == len(exception)
            or scan_name[len(exception)].isupper()
            or scan_name[len(exception)].isdigit()
        ):
            scan_name = scan_name[len(exception) :]
            break
    found = {
        match.start(): match.group()
        for match in _CAPWORDS_TOKEN.finditer(scan_name)
        if match.group() in _ACRONYMS
    }
    for acronym, pattern in _TITLE_ACRONYM_PATTERNS:
        for match in pattern.finditer(scan_name):
            found.setdefault(match.start(), acronym)
    acronyms = [token for _, token in sorted(found.items())]
    if acronyms:
        expected = [token.upper() for token in acronyms]
        yield (
            "acronym-case",
            line,
            f"{original_name!r} spells acronyms {acronyms}; PEP 8 CapWords uses {expected}",
        )


def _type_alias_acronym_findings(
    tree: ast.Module,
) -> Iterator[tuple[int, str]]:
    aliases = _module_aliases(tree, _TYPING) | _module_aliases(
        tree, "typing_extensions"
    )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and _typing_name(node.annotation, aliases) == _TYPE_ALIAS
        ):
            for _, line, message in _acronym_findings(node.target.id, node.lineno):
                yield line, message


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
    if node.module == _TYPING and any(
        item.name in _FORBIDDEN_TYPING for item in node.names
    ):
        yield "any-cast", node.lineno, "forbidden Any/cast import"
    if node.module in {"logging", "logging.handlers"}:
        yield "logging-import", node.lineno, "use qualified logging imports"


def _attribute_findings(node: ast.Attribute) -> Iterator[tuple[str, int, str]]:
    if (
        isinstance(node.value, ast.Name)
        and node.value.id == _TYPING
        and node.attr in _FORBIDDEN_TYPING
    ):
        yield "any-cast", node.lineno, f"forbidden 'typing.{node.attr}' use"


def _annotated_assignment_findings(
    node: ast.AnnAssign,
) -> Iterator[tuple[str, int, str]]:
    if _is_string(node.annotation):
        yield "quoted-annotation", node.lineno, "quoted variable annotation"


def _constant_findings(tree: ast.Module) -> Iterator[tuple[int, str]]:
    aliases = _module_aliases(tree, _TYPING) | _module_aliases(
        tree, "typing_extensions"
    )
    for node in _body_nodes(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            continue
        if _type_declaration(node, aliases):
            continue
        yield from _constant_assignment_findings(node, aliases)


def _constant_assignment_findings(
    node: ast.Assign | ast.AnnAssign | ast.AugAssign, aliases: dict[str, str]
) -> Iterator[tuple[int, str]]:
    annotation = node.annotation if isinstance(node, ast.AnnAssign) else None
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        for name in _constant_bindings(target):
            message = _constant_message(name, annotation, aliases)
            if message is not None:
                yield node.lineno, message


def _constant_message(
    name: str, annotation: ast.expr | None, aliases: dict[str, str]
) -> str | None:
    if name.startswith("_"):
        return (
            f"private module constant '{name}' must be unannotated"
            if annotation
            else None
        )
    if not (
        isinstance(annotation, ast.Subscript)
        and _typing_name(annotation.value, aliases) == "Final"
    ):
        return f"public module constant '{name}' requires explicit Final[T]"
    return None


def _type_declaration(
    node: ast.Assign | ast.AnnAssign | ast.AugAssign, aliases: dict[str, str]
) -> bool:
    if (
        isinstance(node, ast.AnnAssign)
        and _typing_name(node.annotation, aliases) == _TYPE_ALIAS
    ):
        return True
    return (
        isinstance(node.value, ast.Call)
        and _typing_name(node.value.func, aliases) in _TYPE_FACTORIES
    )


def _typing_name(node: ast.expr, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if (
        isinstance(node, ast.Attribute)
        and _typing_name(node.value, aliases) in _TYPING_MODULES
    ):
        return node.attr
    return None


def _constant_bindings(target: ast.expr) -> Iterator[str]:
    if isinstance(target, ast.Name) and _CONSTANT_NAME.fullmatch(target.id):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for item in target.elts:
            yield from _constant_bindings(item)
    elif isinstance(target, ast.Starred):
        yield from _constant_bindings(target.value)


def _enum_findings(
    tree: ast.Module, rules: frozenset[str]
) -> Iterator[tuple[int, str]]:
    aliases = _enum_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {_enum_name(base, aliases) for base in node.bases}
        if not bases & _CLOSED_ENUMS or bases & {"Flag", "IntFlag"}:
            continue
        if "enum-unique" in rules and not any(
            _declares_unique(item, aliases) for item in node.decorator_list
        ):
            yield node.lineno, "closed enum requires @unique or @verify(UNIQUE)"
        if "enum-auto" in rules and bases == {"StrEnum"}:
            yield from _enum_auto_findings(node)


def _enum_auto_findings(node: ast.ClassDef) -> Iterator[tuple[int, str]]:
    if any(
        (isinstance(item, _FUNCTIONS) and item.name == _NEXT_VALUE_HOOK)
        or (
            isinstance(item, ast.Name)
            and isinstance(item.ctx, ast.Store)
            and item.id in {_NEXT_VALUE_HOOK, "_ignore_"}
        )
        for item in ast.walk(node)
    ):
        return
    for member in node.body:
        if not isinstance(member, ast.Assign | ast.AnnAssign) or not isinstance(
            member.value, ast.Constant
        ):
            continue
        targets = member.targets if isinstance(member, ast.Assign) else [member.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name = targets[0].id
        if not (name.startswith("_") and name.endswith("_")) and (
            member.value.value == name.lower()
        ):
            yield member.lineno, f"StrEnum member '{name}' should use auto()"


def _enum_aliases(tree: ast.Module) -> dict[str, str]:
    return _module_aliases(tree, "enum")


def _module_aliases(tree: ast.Module, module: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            aliases.update({item.asname or item.name: item.name for item in node.names})
        elif isinstance(node, ast.Import):
            aliases.update(
                {
                    item.asname or item.name: module
                    for item in node.names
                    if item.name == module
                }
            )
    return aliases


def _enum_name(node: ast.expr, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute) and _enum_name(node.value, aliases) == "enum":
        return node.attr
    return None


def _declares_unique(node: ast.expr, aliases: dict[str, str]) -> bool:
    if isinstance(node, ast.Call):
        return _enum_name(node.func, aliases) == "verify" and any(
            _enum_name(arg, aliases) == "UNIQUE" for arg in node.args
        )
    return _enum_name(node, aliases) == "unique"


def _function_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[tuple[str, int, str]]:
    if _is_string(node.returns):
        yield "quoted-annotation", node.lineno, "quoted return annotation"
    if node.name in _INITIALIZERS and not (
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
        yield from _scope_contracts(tree, _error_bases(tree, Path(path)), public=True)


def _scope_contracts(
    node: ast.AST, bases: dict[str, set[str | None]], *, public: bool
) -> Iterator[tuple[str, int, str]]:
    for child in ast.iter_child_nodes(node):
        visible = public
        if isinstance(child, _FUNCTIONS):
            required = child.name == _INITIALIZER or (
                public and not child.name.startswith("_")
            )
            yield from _callable_findings(child, bases, required=required)
            visible = False
        elif isinstance(child, ast.ClassDef):
            visible = public and not child.name.startswith("_")
            yield from _class_findings(child)
        yield from _scope_contracts(child, bases, public=visible)


def _class_findings(node: ast.ClassDef) -> Iterator[tuple[str, int, str]]:
    misplaced = sorted(
        _STRUCTURED_SECTIONS & _sections(ast.get_docstring(node) or "").keys()
    )
    if misplaced:
        yield (
            "docstring-class-sections",
            node.lineno,
            (
                f"class docstring has {misplaced}; document fields under Attributes: "
                "and initializer arguments and failures on __init__ or __post_init__"
            ),
        )


def _is_test_module(path: str) -> bool:
    parts = PurePath(path.replace("\\", "/").removesuffix(".template"))
    return (
        parts.name.startswith("test_")
        or parts.name.endswith("_test.py")
        or parts.name == "conftest.py"
        or "tests" in parts.parts
    )


def _is_property(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        _decorator_label(decorator) in _PROPERTY_DECORATORS
        for decorator in function.decorator_list
    )


def _decorator_label(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return target.id if isinstance(target, ast.Name) else _attribute_name(target)


def _attribute_name(node: ast.expr) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else None


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
    bases: dict[str, set[str | None]],
    *,
    required: bool,
) -> Iterator[tuple[str, int, str]]:
    docstring = ast.get_docstring(function)
    sections = _sections(docstring or "")
    # Overrides and dunders skip contract checks but still keep one-input docs short.
    yield from _one_line_findings(function, sections)
    if _is_exempt(function):
        return
    parameters = _parameters(function)
    prose = "\n".join(
        line
        for section, lines in sections.items()
        if section not in _REFERENCE_SECTIONS
        for line in lines
    )
    if not docstring and required:
        yield (
            "docstring-missing",
            function.lineno,
            f"public callable '{function.name}' needs a docstring",
        )
    if _INDENTED_ARGS_HEADER.search(prose):
        yield (
            "docstring-args",
            function.lineno,
            "Args: header must align with the docstring's explanatory prose",
        )
    elif _ARGS in sections or (
        function.name == _INITIALIZER and _unmentioned_parameters(parameters, prose)
    ):
        yield from _args_findings(function, parameters, sections)
    yield from _returns_findings(function, sections)
    yield from _raises_findings(function, sections, bases, prose=prose)


def _is_exempt(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    name = function.name
    if name.startswith("test_"):
        return True
    if name.startswith("__") and name.endswith("__") and name != _INITIALIZER:
        return True
    for decorator in function.decorator_list:
        if _decorator_label(decorator) in _EXEMPT_DECORATORS:
            return True
    return False


def _unmentioned_parameters(parameters: list[tuple[str, ast.arg]], prose: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(label.lstrip('*'))}\b", prose) is None
        for label, _ in parameters
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
    if _ARGS not in sections:
        yield (
            "docstring-args",
            function.lineno,
            f"explain initializer parameters {expected} in prose or Args:",
        )
        return
    documented = _documented_args(sections[_ARGS])
    if not documented or [label for label, _ in documented] != expected:
        found = [label for label, _ in documented]
        message = f"Args must list {expected} in signature order; found {found}"
        yield "docstring-args", function.lineno, message
        return
    for (label, argument), (_, doc_type) in zip(parameters, documented, strict=True):
        if argument.annotation is None or doc_type is None:
            continue
        want = _normalise_type(ast.unparse(argument.annotation))
        if doc_type is None or _normalise_type(doc_type) != want:
            yield (
                "docstring-args-type",
                function.lineno,
                f"Args entry '{label}' must read '{label} ({want}): ...'",
            )


def _documented_args(lines: list[str]) -> list[tuple[str, str | None]]:
    entries = (_parse_entry(entry) for entry in _section_entries(lines))
    return [entry for entry in entries if entry is not None]


def _section_entries(lines: list[str]) -> list[str]:
    body = [line for line in lines if line.strip()]
    if not body:
        return []
    indent = len(body[0]) - len(body[0].lstrip())
    entries: list[str] = []
    for line in body:
        if len(line) - len(line.lstrip()) == indent:
            entries.append(line.strip())
        elif entries:
            entries[-1] += " " + line.strip()
    return entries


def _parse_entry(text: str) -> tuple[str, str | None] | None:
    match = _ENTRY.match(text)
    if match is None:
        return None
    name, rest = match.groups()
    if rest.startswith(":"):
        return (name, None) if rest[1:].strip() else None
    if not rest.startswith("("):
        return None
    return _typed_arg(name, rest)


def _typed_arg(name: str, rest: str) -> tuple[str, str] | None:
    depth = 0
    for index, character in enumerate(rest):
        depth += character == "("
        depth -= character == ")"
        if depth == 0:
            suffix = rest[index + 1 :].strip()
            if suffix.startswith(":") and suffix[1:].strip():
                return name, rest[1:index]
            return None
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
) -> Iterator[tuple[str, int, str]]:
    generator = _yields(function)
    meaningful = _requires_returns(function)
    if _RETURNS in sections and _is_property(function):
        yield (
            "docstring-property",
            function.lineno,
            "document a property like an attribute in one line; remove Returns:",
        )
    elif not meaningful or generator:
        if _RETURNS in sections:
            yield (
                "docstring-returns-none",
                function.lineno,
                "remove Returns: from a procedure, generator or never-returning callable",
            )
    elif _RETURNS in sections and not _described_section(
        sections.get(_RETURNS, []), function.returns
    ):
        yield (
            "docstring-returns",
            function.lineno,
            "Returns: needs a description; any included type must match the annotation",
        )
    yield from _yields_findings(function, sections)


def _yields_findings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    sections: dict[str, list[str]],
) -> Iterator[tuple[str, int, str]]:
    if "Yields" not in sections:
        return
    if _yields(function):
        if not _described_section(
            sections.get("Yields", []), _yield_type(function.returns)
        ):
            yield (
                "docstring-yields",
                function.lineno,
                "Yields: needs a description; any included type must match the yielded type",
            )
    else:
        yield (
            "docstring-yields",
            function.lineno,
            "remove Yields: from a callable that does not yield",
        )


def _described_section(lines: list[str], annotation: ast.expr | None) -> bool:
    entry = " ".join(line.strip() for line in lines if line.strip())
    if not entry or entry.endswith(":"):
        return False
    prefix, separator, _description = entry.partition(":")
    return (
        _typed_section(lines, annotation)
        if separator and _TYPED_SECTION_PREFIX.fullmatch(prefix.strip())
        else True
    )


def _typed_section(lines: list[str], annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    expected = _normalise_type(ast.unparse(annotation))
    # A Literal type may itself contain a colon; compare complete type prefixes.
    entry = " ".join(line.strip() for line in lines)
    return any(
        _normalise_type(entry[:index]) == expected and bool(entry[index + 1 :].strip())
        for index, char in enumerate(entry)
        if char == ":"
    )


def _yield_type(annotation: ast.expr | None) -> ast.expr | None:
    if (
        isinstance(annotation, ast.Subscript)
        and _base_name(annotation) in _GENERATOR_TYPES
    ):
        return _elements(annotation.slice)[0]
    return None


def _requires_returns(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    returns = function.returns
    if returns is not None:
        return not _is_none(returns) and _base_name(returns) not in {
            "Never",
            "NoReturn",
        }
    return any(
        isinstance(node, ast.Return)
        and node.value is not None
        and not _is_none(node.value)
        for node in _body_nodes(function)
    )


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _yields(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Yield | ast.YieldFrom) for child in _body_nodes(node)
    )


def _body_nodes(node: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (*_FUNCTIONS, ast.Lambda, ast.ClassDef)):
            yield child
            yield from _body_nodes(child)


def _raises_findings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    sections: dict[str, list[str]],
    bases: dict[str, set[str | None]],
    *,
    prose: str,
) -> Iterator[tuple[str, int, str]]:
    if "Raises" not in sections:
        return
    entries = _section_entries(sections["Raises"])
    documented = {
        name.strip().rsplit(".", 1)[-1]
        for entry in entries
        for name, colon, description in [entry.partition(":")]
        if colon and description.strip()
    }
    escaping = set(_escaping_errors(function, bases))
    raised = {error for error in escaping if error is not None}
    missing = sorted(
        error
        for error in raised - documented
        if _caught_type(error, {"BaseException"}, bases)
        and re.search(rf"\b{re.escape(error)}\b", prose) is None
    )
    if missing or not entries or len(documented) != len(entries):
        detail = f"; missing {missing}" if missing else ""
        yield (
            "docstring-raises",
            function.lineno,
            f"Raises: must describe caller-relevant errors{detail}",
        )
    # Contracts and dynamic raises (factories, variables) cannot be resolved statically.
    dynamic = None in escaping or not all(_is_class(error, bases) for error in raised)
    if _is_contract(function) or dynamic:
        return
    extra = sorted(
        name
        for name in documented
        if not any(_caught_type(error, {name}, bases) for error in raised)
    )
    if extra:
        yield (
            "docstring-raises-extra",
            function.lineno,
            (
                f"Raises: lists {extra} that the body never raises; document direct "
                "raises, translations and re-raises only, not callee failures"
            ),
        )


def _is_contract(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    abstract = any(
        _decorator_label(decorator) in _ABSTRACT_DECORATORS
        for decorator in function.decorator_list
    )
    return abstract or all(_is_placeholder(statement) for statement in _code(function))


def _code(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    documented = ast.get_docstring(function, clean=False) is not None
    return function.body[1:] if documented else function.body


def _is_placeholder(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Expr):
        return (
            isinstance(statement.value, ast.Constant) and statement.value.value is ...
        )
    return (
        isinstance(statement, ast.Raise)
        and statement.exc is not None
        and _raised_label(statement.exc) == "NotImplementedError"
    )


def _is_class(label: str, bases: dict[str, set[str | None]]) -> bool:
    return label[:1].isupper() and label in bases


def _one_line_findings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    sections: dict[str, list[str]],
) -> Iterator[tuple[str, int, str]]:
    supplied = sorted(_STRUCTURED_SECTIONS & sections.keys())
    if supplied and len(_parameters(function)) <= 1 and not _keeps_sections(function):
        yield (
            "docstring-one-line",
            function.lineno,
            (
                f"'{function.name}' takes at most one input; fold the result and any "
                "raised error into a one-line summary (prose detail may follow) "
                f"instead of {supplied}"
            ),
        )


def _keeps_sections(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    labels = {_decorator_label(decorator) for decorator in function.decorator_list}
    return (
        function.name in _INITIALIZERS
        or function.name.startswith("test_")
        or _is_property(function)
        or "overload" in labels
    )


def _escaping_errors(
    node: ast.AST,
    bases: dict[str, set[str | None]],
    *,
    handler: ast.ExceptHandler | None = None,
) -> Iterator[str | None]:
    if isinstance(node, ast.Raise):
        yield from _raise_types(node, handler=handler)
    elif isinstance(node, ast.Try | ast.TryStar):
        yield from _try_errors(node, bases, handler=handler)
    else:
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (*_FUNCTIONS, ast.Lambda, ast.ClassDef)):
                yield from _escaping_errors(
                    child,
                    bases,
                    handler=node if isinstance(node, ast.ExceptHandler) else handler,
                )


def _raised_label(error: ast.expr) -> str | None:
    return _base_name(error.func if isinstance(error, ast.Call) else error)


def _raise_types(
    node: ast.Raise, *, handler: ast.ExceptHandler | None
) -> Iterator[str | None]:
    reraises = handler is not None and (
        node.exc is None
        or (isinstance(node.exc, ast.Name) and node.exc.id == handler.name)
    )
    if reraises and handler is not None and handler.type is None:
        yield None  # A bare handler re-raises an unknown type: dynamic.
    elif reraises and handler is not None and handler.type is not None:
        yield from (_raised_label(item) for item in _elements(handler.type))
    elif node.exc is not None:
        yield _raised_label(node.exc)


def _try_errors(
    node: ast.Try | ast.TryStar,
    bases: dict[str, set[str | None]],
    *,
    handler: ast.ExceptHandler | None,
) -> Iterator[str | None]:
    caught = {
        _base_name(item)
        for handler in node.handlers
        if handler.type is not None
        for item in _elements(handler.type)
    }
    catches_all = any(handler.type is None for handler in node.handlers)
    for statement in node.body:
        for error in _escaping_errors(statement, bases, handler=handler):
            if not catches_all and not _caught_type(error, caught, bases):
                yield error
    for statement in [*node.handlers, *node.orelse, *node.finalbody]:
        yield from _escaping_errors(statement, bases, handler=handler)


def _caught_type(
    error: str | None,
    caught: Collection[str | None],
    bases: dict[str, set[str | None]],
) -> bool:
    # ``None`` is the unknown label: only an unknown handler type catches it.
    pending = {error}
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in caught:
            return True
        if name is not None and name not in visited:
            visited.add(name)
            pending.update(bases.get(name, set()))
    return False


def _error_bases(tree: ast.Module, path: Path) -> dict[str, set[str | None]]:
    bases: dict[str, set[str | None]] = {
        name: {base.__name__ for base in value.__bases__}
        for name, value in vars(builtins).items()
        if isinstance(value, type) and issubclass(value, BaseException)
    }
    _add_class_bases(tree, bases)
    for module, level in _imported_modules(tree):
        imported = _local_module(path, module, level=level)
        if imported is not None:
            _add_class_bases(imported, bases)
    return bases


def _add_class_bases(tree: ast.Module, bases: dict[str, set[str | None]]) -> None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases.setdefault(node.name, set()).update(
                _base_name(base) for base in node.bases
            )
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                if item.asname:
                    bases[item.asname] = {item.name}
                    bases.setdefault(item.name, set()).add(item.asname)
                else:
                    # Imported names are known labels even when their ancestry is not.
                    bases.setdefault(item.name, set())


def _imported_modules(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, node.level
        elif isinstance(node, ast.Import):
            for item in node.names:
                yield item.name, 0


def _local_module(origin: Path, module: str, *, level: int) -> ast.Module | None:
    root = origin.absolute().parent
    if level:
        for _ in range(level - 1):
            root = root.parent
    else:
        while (root / "__init__.py").is_file():
            root = root.parent
    candidate = root.joinpath(*module.split(".")).with_suffix(".py")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(
        root.resolve()
    ):
        return None
    try:
        return ast.parse(candidate.read_text(encoding="utf-8"), filename=str(candidate))
    except (OSError, UnicodeError, SyntaxError):
        # Unknown ancestry remains a finding, never an assumed handled error.
        return None


def _elements(node: ast.expr) -> list[ast.expr]:
    return list(node.elts) if isinstance(node, ast.Tuple) else [node]


def _base_name(node: ast.expr) -> str | None:
    target = node.value if isinstance(node, ast.Subscript) else node
    return target.id if isinstance(target, ast.Name) else _attribute_name(target)


def collect(
    paths: Iterable[Path], *, excluded: frozenset[str], templates: bool = False
) -> tuple[list[Path], list[str]]:
    """Expand explicit targets into Python files, rejecting missing or linked paths.

    Args:
        paths (Iterable[Path]): Files or directories named by the caller.
        excluded (frozenset[str]): Directory names skipped during recursion.
        templates (bool): Scan production Python templates instead of Python modules.

    Returns:
        tuple[list[Path], list[str]]: Sorted unique files and unusable-target findings.
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
    """Scan explicit targets without executing their source.

    The exit status is 0 when clean and 1 for findings, unreadable files or
    invalid source; ``argv=None`` reads ``sys.argv[1:]``.
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
        "--repeated-literals",
        action="store_true",
        help="also flag str, bytes and number literals compared twice in one module",
    )
    parser.add_argument(
        "--docstrings",
        action="store_true",
        help="require public docs and initializer explanations; validate supplied typed sections",
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
        | ({"repeated-literal"} if args.repeated_literals else set())
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
