"""Report Protocol ports in core packages that no adapter class implements.

A port is a class in a ``--core`` path that lists ``Protocol`` (or
``typing.Protocol``, optionally subscripted) among its bases. Its required
members are its methods and properties, including those inherited from other
ports in the core paths. An adapter is any non-Protocol class in an
``--adapters`` path; its members include those of base classes defined in the
scanned adapter files. A port is bound when at least one adapter provides every
required member, with compatible invocation kinds for methods. Coroutines match
only coroutines; async generators are distinct. A normal ``def`` port annotated
with bare or qualified ``AsyncIterator`` (optionally subscripted) also accepts an
async generator. Ordinary functions and synchronous generators remain compatible.
This is a syntactic body check: nested function, class and lambda scopes,
including their headers, are skipped. Annotation aliases, strings, decorators
that change call behavior and general return-type equivalence are not resolved.
Properties may be satisfied by a method, a property, a class attribute, or an
assignment to ``self.<name>`` in any method. Matching is structural, so adapters need not
inherit from the port. The script parses source and never imports it.

Example:
    check_port_adapter_binding.py --core src/shop/core --adapters src/shop/infrastructure
"""

import argparse
import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import re
import sys

_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SPECIAL_MEMBERS = frozenset(
    {"__call__", "__enter__", "__exit__", "__aenter__", "__aexit__"}
)
_EXIT_USAGE = 2


class _CallableKind(StrEnum):
    """Syntactic execution kinds, independent of method binding."""

    NORMAL = "normal"
    GENERATOR = "generator"
    COROUTINE = "coroutine"
    ASYNC_GENERATOR = "async generator"


@dataclass(frozen=True, kw_only=True, slots=True)
class _CallableContract:
    """Invocation shape and the narrow ``AsyncIterator`` annotation hint.

    Attributes:
        kind: Execution kind derived from the function's own body.
        returns_async_iterator: Whether the annotation names ``AsyncIterator``.
    """

    kind: _CallableKind
    returns_async_iterator: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class ClassInfo:
    """Members declared by one class.

    Attributes:
        name: Class name.
        path: Display path of the defining file.
        line: Line of the class statement.
        bases: Simple names of the base classes.
        is_protocol: Whether ``Protocol`` is a direct base.
        methods: Method names mapped to their syntactic invocation contracts.
        properties: Names declared with ``@property``.
        attributes: Names assigned at class level or on ``self``.
    """

    name: str
    path: str
    line: int
    bases: tuple[str, ...]
    is_protocol: bool
    methods: dict[str, _CallableContract] = field(default_factory=dict)
    properties: frozenset[str] = frozenset()
    attributes: frozenset[str] = frozenset()


def classes_in_source(text: str, path: str) -> list[ClassInfo]:
    """Collect every class definition in a module, including nested ones.

    Args:
        text: Python source text.
        path: Display path stored on each result.

    Returns:
        Class descriptions in source order.
    """
    tree = ast.parse(text, filename=path)
    return [
        _describe(node, path)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]


def unbound_ports(
    core: Iterable[ClassInfo],
    adapters: Iterable[ClassInfo],
    *,
    ignore: tuple[re.Pattern[str], ...] = (),
) -> list[str]:
    """Return one finding per port without a complete adapter.

    Args:
        core: Classes found in the core paths.
        adapters: Classes found in the adapter paths.
        ignore: Port-name patterns that are never reported.

    Returns:
        Findings formatted as ``path:line: message``, sorted by path and line.
    """
    core_index = {info.name: info for info in core}
    adapter_index = {info.name: info for info in adapters if not info.is_protocol}
    findings: list[tuple[str, int, str]] = []
    for port in core_index.values():
        if not port.is_protocol or any(pattern.search(port.name) for pattern in ignore):
            continue
        methods, properties = _port_members(port, core_index)
        if not methods and not properties:
            continue
        gaps = sorted(
            (
                (_missing(adapter, adapter_index, methods, properties), adapter)
                for adapter in adapter_index.values()
            ),
            key=lambda item: (len(item[0]), item[1].path, item[1].line),
        )
        if gaps and not gaps[0][0]:
            continue
        required = ", ".join(sorted([*methods, *properties]))
        message = f"port '{port.name}' has no adapter implementing all of: {required}"
        if gaps and len(gaps[0][0]) < len(methods) + len(properties):
            missing, closest = gaps[0]
            message += (
                f"; closest '{closest.name}' ({closest.path}:{closest.line}) "
                f"lacks: {', '.join(missing)}"
            )
        findings.append((port.path, port.line, message))
    return [f"{path}:{line}: {message}" for path, line, message in sorted(findings)]


def _describe(node: ast.ClassDef, path: str) -> ClassInfo:
    bases = tuple(name for name in (_base_name(base) for base in node.bases) if name)
    methods: dict[str, _CallableContract] = {}
    properties: set[str] = set()
    attributes: set[str] = set()
    for statement in node.body:
        if isinstance(statement, _FUNCTIONS):
            if any(_is_property(decorator) for decorator in statement.decorator_list):
                properties.add(statement.name)
            elif _is_member(statement.name):
                methods[statement.name] = _callable_contract(statement)
            attributes.update(_self_assignments(statement))
        else:
            attributes.update(_assigned_names(statement))
    return ClassInfo(
        name=node.name,
        path=path,
        line=node.lineno,
        bases=bases,
        is_protocol="Protocol" in bases,
        methods=methods,
        properties=frozenset(properties),
        attributes=frozenset(attributes),
    )


def _has_yield(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Find ``yield`` or ``yield from`` without entering nested scopes."""
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Yield | ast.YieldFrom):
            return True
        if not isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
        ):
            pending.extend(ast.iter_child_nodes(node))
    return False


def _callable_contract(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> _CallableContract:
    """Classify a body and recognize only a literal ``AsyncIterator`` name."""
    has_yield = _has_yield(function)
    if isinstance(function, ast.AsyncFunctionDef):
        kind = _CallableKind.ASYNC_GENERATOR if has_yield else _CallableKind.COROUTINE
    else:
        kind = _CallableKind.GENERATOR if has_yield else _CallableKind.NORMAL
    return _CallableContract(
        kind=kind,
        returns_async_iterator=function.returns is not None
        and _base_name(function.returns) == "AsyncIterator",
    )


def _callables_compatible(
    expected: _CallableContract, actual: _CallableContract
) -> bool:
    """Compare invocation shapes without inferring general type equivalence."""
    if (
        expected.kind is _CallableKind.COROUTINE
        or actual.kind is _CallableKind.COROUTINE
    ):
        return expected.kind is actual.kind
    if expected.kind is _CallableKind.ASYNC_GENERATOR:
        return actual.kind is _CallableKind.ASYNC_GENERATOR
    if actual.kind is _CallableKind.ASYNC_GENERATOR:
        return expected.kind is _CallableKind.NORMAL and expected.returns_async_iterator
    return True


def _assigned_names(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return {statement.target.id}
    if isinstance(statement, ast.Assign):
        return {
            target.id for target in statement.targets if isinstance(target, ast.Name)
        }
    return set()


def _base_name(base: ast.expr) -> str | None:
    target = base.value if isinstance(base, ast.Subscript) else base
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _is_property(decorator: ast.expr) -> bool:
    return (isinstance(decorator, ast.Name) and decorator.id == "property") or (
        isinstance(decorator, ast.Attribute) and decorator.attr in {"setter", "getter"}
    )


def _is_member(name: str) -> bool:
    return not name.startswith("_") or name in _SPECIAL_MEMBERS


def _self_assignments(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[str]:
    for node in ast.walk(function):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                yield target.attr


def _port_members(
    port: ClassInfo, index: dict[str, ClassInfo]
) -> tuple[dict[str, _CallableContract], frozenset[str]]:
    methods: dict[str, _CallableContract] = {}
    properties: set[str] = set()
    for info in _lineage(port, index):
        if not info.is_protocol:
            continue
        for name, contract in info.methods.items():
            methods.setdefault(name, contract)
        properties.update(info.properties)
    return methods, frozenset(properties)


def _missing(
    adapter: ClassInfo,
    index: dict[str, ClassInfo],
    methods: dict[str, _CallableContract],
    properties: frozenset[str],
) -> list[str]:
    provided_methods: dict[str, _CallableContract] = {}
    provided_names: set[str] = set()
    for info in _lineage(adapter, index):
        for name, contract in info.methods.items():
            provided_methods.setdefault(name, contract)
        provided_names.update(info.properties, info.attributes, info.methods)
    gaps = [
        name if name not in provided_methods else f"{name} (async mismatch)"
        for name, contract in methods.items()
        if name not in provided_methods
        or not _callables_compatible(contract, provided_methods[name])
    ]
    gaps.extend(name for name in properties if name not in provided_names)
    return sorted(gaps)


def _lineage(start: ClassInfo, index: dict[str, ClassInfo]) -> Iterator[ClassInfo]:
    pending = [start]
    seen: set[str] = set()
    while pending:
        info = pending.pop()
        if info.name in seen:
            continue
        seen.add(info.name)
        yield info
        pending.extend(index[base] for base in info.bases if base in index)


def main(argv: list[str] | None = None) -> int:
    """Check that every core port has a complete adapter.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Zero when every port is bound, one on findings, two on usage errors.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--core", action="append", required=True, type=Path)
    parser.add_argument("--adapters", action="append", required=True, type=Path)
    parser.add_argument(
        "--ignore", action="append", default=[], help="regex of port names to skip"
    )
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        ignore = tuple(re.compile(pattern) for pattern in args.ignore)
    except re.error as error:
        print(f"invalid --ignore pattern: {error}", file=sys.stderr)
        return _EXIT_USAGE
    excluded = _EXCLUDED | set(args.exclude)
    core, core_problems = _scan(args.core, excluded)
    adapters, adapter_problems = _scan(args.adapters, excluded)
    findings = [
        *core_problems,
        *adapter_problems,
        *unbound_ports(core, adapters, ignore=ignore),
    ]
    for finding in findings:
        print(finding)
    ports = sum(1 for info in core if info.is_protocol)
    print(f"checked {ports} port(s) against {len(adapters)} class(es)", file=sys.stderr)
    return 1 if findings else 0


def _scan(
    paths: Iterable[Path], excluded: frozenset[str]
) -> tuple[list[ClassInfo], list[str]]:
    classes: list[ClassInfo] = []
    problems: list[str] = []
    for root in paths:
        if not root.exists():
            problems.append(f"{root.as_posix()}:1: path does not exist")
            continue
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            if excluded.intersection(path.relative_to(root).parts):
                continue
            try:
                classes.extend(
                    classes_in_source(path.read_text(encoding="utf-8"), path.as_posix())
                )
            except (OSError, UnicodeError, SyntaxError):
                problems.append(f"{path.as_posix()}:1: source cannot be parsed")
    return classes, problems


if __name__ == "__main__":
    raise SystemExit(main())
