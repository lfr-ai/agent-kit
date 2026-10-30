# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check that adapters implement port Protocols with matching signatures.

The checker parses source with ``ast`` and never imports or executes it. Ports are
``typing.Protocol`` classes found under the ``--ports`` paths. An implementation is
either a class that names the port as a base class (explicit) or, with
``--structural``, any other class that defines every member of the port.

For each implementation it reports missing members, extra public methods,
callable-kind differences, parameter name, order or kind differences, and default
value differences. Coroutines must match coroutines; async generators are not
coroutines. A normal ``def`` port annotated with a bare or qualified
``AsyncIterator`` (optionally subscripted) also accepts an async generator.
Ordinary functions and synchronous generators remain compatible.

This is a syntactic body check: nested function, class and lambda scopes are
skipped, including their headers. Annotation aliases, strings, decorators that
change call behavior and general return-type equivalence are not resolved.
Other return-type checking belongs to a type checker. Output lines are
``path:line: message``; the exit status is 1 when anything is reported.

Example:
    python check_ports_adapters.py src tests --ports src/app/application/ports
"""

import argparse
import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import sys
from typing import NamedTuple

_EXCLUDED_DIRS = frozenset(
    {".git", ".venv", "venv", ".tox", "node_modules", "__pycache__", "build", "dist"}
)
_IGNORED_MEMBERS = frozenset(
    {
        "__init__",
        "__post_init__",
        "__slots__",
        "__match_args__",
        "__class_getitem__",
        "__init_subclass__",
        "__hash__",
        "__eq__",
        "__repr__",
    }
)
_SKIPPED_DECORATORS = frozenset({"setter", "deleter", "overload"})
_PROPERTY_DECORATORS = frozenset({"property", "cached_property"})
_DATA_KINDS = frozenset({"attribute", "property"})
_CALLABLE_KINDS = frozenset(
    {"method", "classmethod", "staticmethod", "async method", "async generator method"}
)
_ANY_DEFAULT = "..."
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


class Param(NamedTuple):
    """One parameter of a method signature, excluding ``self`` and ``cls``.

    Attributes:
        name: Parameter name as written.
        kind: ``positional-only``, ``positional``, ``*args``, ``keyword-only`` or ``**kwargs``.
        default: Unparsed default expression, or None when there is no default.
    """

    name: str
    kind: str
    default: str | None


class Member(NamedTuple):
    """A method, property or attribute declared in a class body.

    Attributes:
        name: Member name.
        kind: Method binding or execution label, ``property`` or ``attribute``.
        params: Parameters after the implicit first argument.
        line: Line of the declaration.
        contract: Invocation shape for a function; absent for attributes.
    """

    name: str
    kind: str
    params: tuple[Param, ...]
    line: int
    contract: _CallableContract | None = None


class ClassInfo(NamedTuple):
    """A top-level class and the members declared directly in its body.

    Attributes:
        name: Class name.
        path: Source path as given to the checker.
        line: Line of the ``class`` statement.
        bases: Simple names of the base classes.
        members: Members declared in the class body, by name.
        is_protocol: True when ``Protocol`` is a direct base.
    """

    name: str
    path: str
    line: int
    bases: tuple[str, ...]
    members: dict[str, Member]
    is_protocol: bool


class Options(NamedTuple):
    """Switches that tune what the checker reports.

    Attributes:
        structural: Also check classes that match a port without naming it.
        report_extra: Report public methods the implemented ports do not declare.
        allow_extra: Method names that are never reported as extra.
        require_implementation: Report ports without any implementation.
        skip: Class names that are never treated as implementations.
    """

    structural: bool = True
    report_extra: bool = True
    allow_extra: frozenset[str] = frozenset()
    require_implementation: bool = True
    skip: frozenset[str] = frozenset()


class Finding(NamedTuple):
    """One reported problem.

    Attributes:
        path: Source path.
        line: One-based line number.
        message: Human-readable description.
    """

    path: str
    line: int
    message: str

    def render(self) -> str:
        """Return the finding as ``path:line: message``."""
        return f"{self.path}:{self.line}: {self.message}"


def _simple_name(node: ast.expr) -> str:
    """Return ``Protocol`` for ``Protocol``, ``typing.Protocol`` and ``Protocol[T]``."""
    if isinstance(node, ast.Subscript):
        return _simple_name(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _simple_name(node.func)
    return ""


def _unparse(node: ast.expr | None) -> str | None:
    """Render a default expression, keeping None for ``no default``."""
    return None if node is None else ast.unparse(node)


def _params(arguments: ast.arguments) -> tuple[Param, ...]:
    """Flatten an argument list into ordered parameters with defaults."""
    positional = [*arguments.posonlyargs, *arguments.args]
    padding: list[ast.expr | None] = [None] * (
        len(positional) - len(arguments.defaults)
    )
    defaults = [*padding, *arguments.defaults]
    params = [
        Param(
            arg.arg,
            "positional-only" if index < len(arguments.posonlyargs) else "positional",
            _unparse(default),
        )
        for index, (arg, default) in enumerate(zip(positional, defaults, strict=True))
    ]
    if arguments.vararg is not None:
        params.append(Param(arguments.vararg.arg, "*args", None))
    params.extend(
        Param(arg.arg, "keyword-only", _unparse(default))
        for arg, default in zip(
            arguments.kwonlyargs, arguments.kw_defaults, strict=True
        )
    )
    if arguments.kwarg is not None:
        params.append(Param(arguments.kwarg.arg, "**kwargs", None))
    return tuple(params)


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return simple decorator names, for example ``property`` or ``setter``."""
    return {_simple_name(item) for item in node.decorator_list}


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
    annotation = function.returns
    if isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    return _CallableContract(
        kind=kind,
        returns_async_iterator=isinstance(annotation, ast.Name | ast.Attribute)
        and _simple_name(annotation) == "AsyncIterator",
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


def _binding_kind(decorators: set[str]) -> str:
    """Describe binding separately from callable execution."""
    if decorators & _PROPERTY_DECORATORS:
        return "property"
    if "staticmethod" in decorators:
        return "staticmethod"
    if "classmethod" in decorators:
        return "classmethod"
    return "method"


def _function_member(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Member:
    """Describe one function definition as a class member."""
    decorators = _decorators(node)
    params = _params(node.args)
    contract = _callable_contract(node)
    kind = _binding_kind(decorators)
    if kind in _CALLABLE_KINDS:
        kind = {
            _CallableKind.COROUTINE: "async method",
            _CallableKind.ASYNC_GENERATOR: "async generator method",
        }.get(contract.kind, kind)
    if "staticmethod" not in decorators:
        params = params[1:]
    return Member(node.name, kind, params, node.lineno, contract)


def _instance_attributes(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Member]:
    """Find ``self.name = ...`` assignments inside an initializer."""
    if not node.args.args:
        return []
    owner = node.args.args[0].arg
    found: list[Member] = []
    for item in ast.walk(node):
        targets: list[ast.expr] = []
        if isinstance(item, ast.Assign):
            targets = item.targets
        elif isinstance(item, ast.AnnAssign):
            targets = [item.target]
        found.extend(
            Member(target.attr, "attribute", (), target.lineno)
            for target in targets
            if isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == owner
        )
    return found


def _members(node: ast.ClassDef) -> dict[str, Member]:
    """Collect methods, properties and attributes declared by a class body."""
    members: dict[str, Member] = {}
    attributes: list[Member] = []
    for item in node.body:
        if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            attributes.extend(_assigned_attributes(item))
        elif not _decorators(item) & _SKIPPED_DECORATORS:
            members[item.name] = _function_member(item)
            if item.name == "__init__":
                attributes.extend(_instance_attributes(item))
    for attribute in attributes:
        members.setdefault(attribute.name, attribute)
    return members


def _assigned_attributes(item: ast.stmt) -> list[Member]:
    """Describe class-level attributes assigned by one class body statement."""
    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
        return [Member(item.target.id, "attribute", (), item.lineno)]
    if isinstance(item, ast.Assign):
        return [
            Member(target.id, "attribute", (), item.lineno)
            for target in item.targets
            if isinstance(target, ast.Name)
        ]
    return []


def parse_classes(path: str, text: str) -> list[ClassInfo]:
    """Parse one module and describe its top-level classes.

    Args:
        path: Path used in findings.
        text: Module source.

    Returns:
        Top-level classes in source order.

    Raises:
        SyntaxError: If the source is not valid Python.
    """
    tree = ast.parse(text, filename=path)
    classes: list[ClassInfo] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = tuple(name for name in map(_simple_name, node.bases) if name)
        classes.append(
            ClassInfo(
                name=node.name,
                path=path,
                line=node.lineno,
                bases=bases,
                members=_members(node),
                is_protocol="Protocol" in bases,
            )
        )
    return classes


def _is_interface_name(name: str) -> bool:
    """Return whether a member name is part of a port's public surface."""
    if name in _IGNORED_MEMBERS:
        return False
    if name.startswith("__") and name.endswith("__"):
        return True
    return not name.startswith("_")


def _port_members(
    port: ClassInfo, protocols: dict[str, ClassInfo], seen: frozenset[str]
) -> dict[str, Member]:
    """Merge a port's members with those of the protocols it extends."""
    merged: dict[str, Member] = {}
    for base in reversed(port.bases):
        parent = protocols.get(base)
        if parent is not None and parent.name not in seen:
            merged.update(_port_members(parent, protocols, seen | {port.name}))
    merged.update(
        (name, member)
        for name, member in port.members.items()
        if _is_interface_name(name)
    )
    return merged


def _resolved_members(
    cls: ClassInfo, classes: dict[str, ClassInfo], seen: frozenset[str]
) -> dict[str, Member]:
    """Merge members inherited from scanned non-protocol base classes."""
    merged: dict[str, Member] = {}
    for base in reversed(cls.bases):
        parent = classes.get(base)
        if parent is not None and not parent.is_protocol and base not in seen:
            merged.update(_resolved_members(parent, classes, seen | {cls.name}))
    merged.update(cls.members)
    return merged


def _render(params: Sequence[Param]) -> str:
    """Render parameters roughly like ``inspect.signature`` would."""
    parts: list[str] = []
    keyword_marker_needed = True
    for index, param in enumerate(params):
        if param.kind == "keyword-only" and keyword_marker_needed:
            parts.append("*")
        if param.kind in {"*args", "keyword-only", "**kwargs"}:
            keyword_marker_needed = False
        prefix = {"*args": "*", "**kwargs": "**"}.get(param.kind, "")
        default = "" if param.default is None else f"={param.default}"
        parts.append(f"{prefix}{param.name}{default}")
        is_last_positional_only = param.kind == "positional-only" and (
            index + 1 == len(params) or params[index + 1].kind != "positional-only"
        )
        if is_last_positional_only:
            parts.append("/")
    return f"({', '.join(parts)})"


def _kinds_compatible(expected: str, actual: str) -> bool:
    """Compare data or method categories; invocation shape is checked separately."""
    if expected == actual:
        return True
    if expected in _DATA_KINDS and actual in _DATA_KINDS:
        return True
    return expected in _CALLABLE_KINDS and actual in _CALLABLE_KINDS


def _members_compatible(expected: Member, actual: Member) -> bool:
    """Check member categories and, for callables, their invocation contracts."""
    if not _kinds_compatible(expected.kind, actual.kind):
        return False
    if expected.kind in _DATA_KINDS:
        return True
    if expected.contract is None or actual.contract is None:
        return expected.contract is actual.contract
    return _callables_compatible(expected.contract, actual.contract)


def _compare(
    port: ClassInfo, expected: Member, owner: ClassInfo, actual: Member
) -> list[Finding]:
    """Compare one implemented member with the port declaration."""
    where = f"'{owner.name}.{actual.name}'"
    declared = f"port '{port.name}.{expected.name}'"
    if not _members_compatible(expected, actual):
        return [
            Finding(
                owner.path,
                actual.line,
                f"{where} is {_article(actual.kind)} but {declared} is "
                f"{_article(expected.kind)}",
            )
        ]
    if expected.kind in _DATA_KINDS:
        return []
    expected_shape = [(param.name, param.kind) for param in expected.params]
    actual_shape = [(param.name, param.kind) for param in actual.params]
    if expected_shape != actual_shape:
        return [
            Finding(
                owner.path,
                actual.line,
                f"{where}{_render(actual.params)} does not match "
                f"{declared}{_render(expected.params)}",
            )
        ]
    findings: list[Finding] = []
    for wanted, got in zip(expected.params, actual.params, strict=True):
        message = _default_mismatch(wanted, got, where=where, declared=declared)
        if message is not None:
            findings.append(Finding(owner.path, actual.line, message))
    return findings


def _default_mismatch(
    wanted: Param, got: Param, *, where: str, declared: str
) -> str | None:
    """Describe how an implemented default differs from the port, if it does."""
    if wanted.default is not None and got.default is None:
        return f"{where} parameter '{got.name}' needs a default as in {declared}"
    if wanted.default is None and got.default is not None:
        return (
            f"{where} parameter '{got.name}' has a default that {declared} "
            "does not declare"
        )
    if wanted.default not in {None, _ANY_DEFAULT, got.default}:
        return (
            f"{where} parameter '{got.name}' defaults to {got.default} but "
            f"{declared} defaults to {wanted.default}"
        )
    return None


def _article(kind: str) -> str:
    """Return ``an async method`` or ``a property`` style phrases."""
    return f"an {kind}" if kind.startswith(("a", "e", "i", "o", "u")) else f"a {kind}"


def _check_implementation(
    cls: ClassInfo,
    ports: list[tuple[ClassInfo, dict[str, Member]]],
    resolved: dict[str, Member],
    options: Options,
) -> list[Finding]:
    """Report missing, mismatched and extra members of one implementation."""
    findings: list[Finding] = []
    declared: set[str] = set()
    for port, expected in ports:
        declared.update(expected)
        for name, member in sorted(expected.items()):
            actual = resolved.get(name)
            if actual is None:
                findings.append(
                    Finding(
                        cls.path,
                        cls.line,
                        f"class '{cls.name}' does not implement '{port.name}.{name}'",
                    )
                )
            else:
                findings.extend(_compare(port, member, cls, actual))
    if options.report_extra:
        port_names = ", ".join(sorted(port.name for port, _ in ports))
        findings.extend(
            Finding(
                cls.path,
                member.line,
                f"'{cls.name}.{name}' is a public method not declared by "
                f"port {port_names}",
            )
            for name, member in sorted(cls.members.items())
            if member.kind != "attribute"
            and _is_interface_name(name)
            and not name.startswith("__")
            and name not in declared
            and name not in options.allow_extra
        )
    return findings


def analyze(
    port_sources: Sequence[tuple[str, str]],
    sources: Sequence[tuple[str, str]],
    *,
    options: Options = Options(),  # noqa: B008 - immutable NamedTuple default
) -> list[Finding]:
    """Check every implementation of every port found in ``port_sources``.

    Args:
        port_sources: ``(path, text)`` pairs whose Protocol classes are ports.
        sources: ``(path, text)`` pairs searched for implementations.
        options: Reporting switches.

    Returns:
        Findings sorted by path, line and message.
    """
    by_path = dict(sources)
    by_path.update(port_sources)
    port_paths = {path for path, _ in port_sources}
    all_classes, findings = _parse_sources(by_path)
    protocols = {
        cls.name: cls
        for cls in all_classes
        if cls.is_protocol and cls.path in port_paths
    }
    known = {cls.name: cls for cls in reversed(all_classes)}
    port_members = {
        name: _port_members(port, protocols, frozenset())
        for name, port in protocols.items()
    }
    implemented: set[str] = set()
    for cls in all_classes:
        if cls.is_protocol or cls.name in options.skip:
            continue
        resolved = _resolved_members(cls, known, frozenset())
        matched = _matched_ports(cls, resolved, protocols, port_members, options)
        if matched:
            implemented.update(port.name for port, _ in matched)
            findings.extend(_check_implementation(cls, matched, resolved, options))
    if options.require_implementation:
        findings.extend(
            Finding(port.path, port.line, f"port '{name}' has no implementation")
            for name, port in protocols.items()
            if name not in implemented
        )
    return sorted(set(findings))


def _parse_sources(
    by_path: dict[str, str],
) -> tuple[list[ClassInfo], list[Finding]]:
    """Parse every source in path order, reporting unparsable modules."""
    findings: list[Finding] = []
    all_classes: list[ClassInfo] = []
    for path, text in sorted(by_path.items()):
        try:
            all_classes.extend(parse_classes(path, text))
        except SyntaxError as error:
            findings.append(
                Finding(path, error.lineno or 1, f"cannot parse: {error.msg}")
            )
    return all_classes, findings


def _matched_ports(
    cls: ClassInfo,
    resolved: dict[str, Member],
    protocols: dict[str, ClassInfo],
    port_members: dict[str, dict[str, Member]],
    options: Options,
) -> list[tuple[ClassInfo, dict[str, Member]]]:
    """Return the ports a class implements explicitly or structurally."""
    return [
        (protocols[name], members)
        for name, members in sorted(port_members.items())
        if name in cls.bases
        or (options.structural and members and set(members) <= set(resolved))
    ]


def _python_files(paths: Iterable[Path]) -> list[Path]:
    """Expand files and directories into Python files, skipping tool folders."""
    files: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.add(path)
        elif path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*.py")
                if not _EXCLUDED_DIRS.intersection(candidate.parts)
            )
    return sorted(files)


def _read(paths: Iterable[Path]) -> list[tuple[str, str]]:
    """Read sources as ``(posix path, text)`` pairs."""
    return [
        (path.as_posix(), path.read_text(encoding="utf-8"))
        for path in _python_files(paths)
    ]


_SELF_TEST_PORT = """
from collections.abc import AsyncIterator
from typing import Protocol

class DocumentStore(Protocol):
    async def get(self, key: str) -> bytes: ...
    def put(self, key: str, data: bytes, *, overwrite: bool = False) -> None: ...
    limit: int

class AuditedStore(DocumentStore, Protocol):
    def history(self, key: str, /) -> list[str]: ...

class Unused(Protocol):
    def ping(self) -> None: ...

class EventStream(Protocol):
    def events(self) -> AsyncIterator[bytes]: ...
"""

_SELF_TEST_ADAPTERS = """
from ports import DocumentStore

class GoodStore(DocumentStore):
    limit = 10
    async def get(self, key: str) -> bytes: return b""
    def put(self, key: str, data: bytes, *, overwrite: bool = False) -> None: pass
    def _helper(self) -> None: pass

class BadStore(DocumentStore):
    def __init__(self) -> None:
        self.limit = 1
    def get(self, key: str) -> bytes: return b""
    def put(self, key: str, data: bytes, *, overwrite: bool) -> None: pass
    def flush(self) -> None: pass

class Audited:
    @property
    def limit(self) -> int: return 1
    async def get(self, key: str) -> bytes: return b""
    def put(self, name: str, data: bytes, *, overwrite: bool = True) -> None: pass
    def history(self, key: str, /) -> list[str]: return []

class PartialAudit(AuditedStore):
    limit = 1
    async def get(self, key: str) -> bytes: return b""
    def put(self, key: str, data: bytes, *, overwrite: bool = False) -> None: pass

class GoodStream:
    async def events(self):
        yield b""

class BadStream:
    async def events(self):
        def helper():
            yield b""
        return helper()
"""


def self_test() -> list[str]:
    """Run the checker on in-memory sources and return any unmet expectation.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    findings = analyze(
        [("ports.py", _SELF_TEST_PORT)], [("adapters.py", _SELF_TEST_ADAPTERS)]
    )
    rendered = "\n".join(finding.render() for finding in findings)
    expectations = {
        "sync/async mismatch": "'BadStore.get' is a method but port",
        "missing default": "parameter 'overwrite' needs a default",
        "extra method": "'BadStore.flush' is a public method",
        "renamed parameter": "'Audited.put'(name, data",
        "missing member": "does not implement 'AuditedStore.history'",
        "unimplemented port": "port 'Unused' has no implementation",
        "coroutine is not an iterator factory": "'BadStream.events' is an async method",
    }
    failures = [
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    ]
    if "GoodStore" in rendered or "GoodStream" in rendered:
        failures.append("a matching adapter was reported")
    lenient = analyze(
        [("ports.py", _SELF_TEST_PORT)],
        [("adapters.py", _SELF_TEST_ADAPTERS)],
        options=Options(
            structural=False,
            report_extra=False,
            require_implementation=False,
            skip=frozenset({"BadStore", "PartialAudit"}),
        ),
    )
    if lenient:
        failures.append(f"lenient options still reported: {lenient}")
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path()],
        help="files or directories searched for implementations (default: .)",
    )
    parser.add_argument(
        "--ports",
        action="append",
        type=Path,
        default=[],
        help="file or package holding port Protocols; repeatable",
    )
    parser.add_argument(
        "--explicit-only",
        action="store_true",
        help="only check classes that name the port as a base class",
    )
    parser.add_argument(
        "--allow-extra",
        action="append",
        default=[],
        metavar="NAME",
        help="public method name allowed on adapters; repeatable",
    )
    parser.add_argument(
        "--ignore-extra",
        action="store_true",
        help="do not report public methods missing from the port",
    )
    parser.add_argument(
        "--allow-unimplemented",
        action="store_true",
        help="do not report ports without an implementation",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="CLASS",
        help="class name never treated as an implementation; repeatable",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the checker and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on usage or read errors.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.ports:
        parser.error("at least one '--ports' path is required")
    if _report_missing([*args.ports, *args.paths]):
        return _EXIT_USAGE
    try:
        port_sources = _read(args.ports)
        sources = _read(args.paths)
    except (OSError, UnicodeDecodeError) as error:
        sys.stderr.write(f"cannot read sources: {error}\n")
        return _EXIT_USAGE
    options = Options(
        structural=not args.explicit_only,
        report_extra=not args.ignore_extra,
        allow_extra=frozenset(args.allow_extra),
        require_implementation=not args.allow_unimplemented,
        skip=frozenset(args.skip),
    )
    findings = analyze(port_sources, sources, options=options)
    return _report(findings, port_module_count=len(port_sources))


def _report(findings: list[Finding], *, port_module_count: int) -> int:
    """Print findings or a success line and return the exit status."""
    for finding in findings:
        sys.stdout.write(f"{finding.render()}\n")
    if not findings:
        sys.stdout.write(
            f"Ports and adapters agree ({port_module_count} port module(s)).\n"
        )
    return 1 if findings else 0


def _run_self_test() -> int:
    """Print self-test failures and return the matching exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write("check_ports_adapters self-test passed.\n")
    return 0


def _report_missing(paths: Iterable[Path]) -> bool:
    """Print each path that does not exist and return whether any is missing."""
    missing = [path for path in paths if not path.exists()]
    for path in missing:
        sys.stderr.write(f"{path.as_posix()}: path does not exist\n")
    return bool(missing)


if __name__ == "__main__":
    raise SystemExit(main())
