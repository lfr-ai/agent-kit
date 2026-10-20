"""Check that adapters implement port Protocols with matching signatures.

The checker parses source with 'ast' and never imports or executes it. Ports are
'typing.Protocol' classes found under the '--ports' paths. An implementation is
either a class that names the port as a base class (explicit) or, with
'--structural', any other class that defines every member of the port.

For each implementation it reports missing members, extra public methods,
sync/async differences, parameter name, order or kind differences, and default
value differences. Return annotations are left to a type checker. Output lines
are 'path:line: message'; the exit status is 1 when anything is reported.

Example:
    python check_ports_adapters.py src tests --ports src/app/application/ports
"""

import argparse
import ast
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
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
_CALLABLE_KINDS = frozenset({"method", "classmethod", "staticmethod"})
_ANY_DEFAULT = "..."


class Param(NamedTuple):
    """One parameter of a method signature, excluding 'self' and 'cls'.

    Attributes:
        name: Parameter name as written.
        kind: 'positional-only', 'positional', '*args', 'keyword-only' or '**kwargs'.
        default: Unparsed default expression, or None when there is no default.
    """

    name: str
    kind: str
    default: str | None


class Member(NamedTuple):
    """A method, property or attribute declared in a class body.

    Attributes:
        name: Member name.
        kind: 'method', 'async method', 'classmethod', 'staticmethod',
            'property' or 'attribute'.
        params: Parameters after the implicit first argument.
        line: Line of the declaration.
    """

    name: str
    kind: str
    params: tuple[Param, ...]
    line: int


class ClassInfo(NamedTuple):
    """A top-level class and the members declared directly in its body.

    Attributes:
        name: Class name.
        path: Source path as given to the checker.
        line: Line of the 'class' statement.
        bases: Simple names of the base classes.
        members: Members declared in the class body, by name.
        is_protocol: True when 'Protocol' is a direct base.
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
        """Return the finding as 'path:line: message'."""
        return f"{self.path}:{self.line}: {self.message}"


def _simple_name(node: ast.expr) -> str:
    """Return 'Protocol' for 'Protocol', 'typing.Protocol' and 'Protocol[T]'."""
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
    """Render a default expression, keeping None for 'no default'."""
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
    """Return simple decorator names, for example 'property' or 'setter'."""
    return {_simple_name(item) for item in node.decorator_list}


def _function_member(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Member:
    """Describe one function definition as a class member."""
    decorators = _decorators(node)
    params = _params(node.args)
    if decorators & _PROPERTY_DECORATORS:
        kind = "property"
    elif "staticmethod" in decorators:
        kind = "staticmethod"
    elif "classmethod" in decorators:
        kind = "classmethod"
    elif isinstance(node, ast.AsyncFunctionDef):
        kind = "async method"
    else:
        kind = "method"
    if kind != "staticmethod":
        params = params[1:]
    return Member(node.name, kind, params, node.lineno)


def _instance_attributes(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Member]:
    """Find 'self.name = ...' assignments inside an initializer."""
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
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            if _decorators(item) & _SKIPPED_DECORATORS:
                continue
            members[item.name] = _function_member(item)
            if item.name == "__init__":
                attributes.extend(_instance_attributes(item))
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            attributes.append(Member(item.target.id, "attribute", (), item.lineno))
        elif isinstance(item, ast.Assign):
            attributes.extend(
                Member(target.id, "attribute", (), item.lineno)
                for target in item.targets
                if isinstance(target, ast.Name)
            )
    for attribute in attributes:
        members.setdefault(attribute.name, attribute)
    return members


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
    """Render parameters roughly like 'inspect.signature' would."""
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
    """Treat attributes and properties alike, and all synchronous callables alike."""
    if expected == actual:
        return True
    if expected in _DATA_KINDS and actual in _DATA_KINDS:
        return True
    return expected in _CALLABLE_KINDS and actual in _CALLABLE_KINDS


def _compare(
    port: ClassInfo, expected: Member, owner: ClassInfo, actual: Member
) -> list[Finding]:
    """Compare one implemented member with the port declaration."""
    where = f"'{owner.name}.{actual.name}'"
    declared = f"port '{port.name}.{expected.name}'"
    if not _kinds_compatible(expected.kind, actual.kind):
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
        if wanted.default is not None and got.default is None:
            message = f"{where} parameter '{got.name}' needs a default as in {declared}"
        elif wanted.default is None and got.default is not None:
            message = (
                f"{where} parameter '{got.name}' has a default that {declared} "
                "does not declare"
            )
        elif wanted.default not in {None, _ANY_DEFAULT, got.default}:
            message = (
                f"{where} parameter '{got.name}' defaults to {got.default} but "
                f"{declared} defaults to {wanted.default}"
            )
        else:
            continue
        findings.append(Finding(owner.path, actual.line, message))
    return findings


def _article(kind: str) -> str:
    """Return 'an async method' or 'a property' style phrases."""
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
    """Check every implementation of every port found in 'port_sources'.

    Args:
        port_sources: '(path, text)' pairs whose Protocol classes are ports.
        sources: '(path, text)' pairs searched for implementations.
        options: Reporting switches.

    Returns:
        Findings sorted by path, line and message.
    """
    by_path = dict(sources)
    by_path.update(port_sources)
    port_paths = {path for path, _ in port_sources}
    findings: list[Finding] = []
    all_classes: list[ClassInfo] = []
    for path, text in sorted(by_path.items()):
        try:
            all_classes.extend(parse_classes(path, text))
        except SyntaxError as error:
            findings.append(
                Finding(path, error.lineno or 1, f"cannot parse: {error.msg}")
            )
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
        matched = [
            (protocols[name], members)
            for name, members in sorted(port_members.items())
            if name in cls.bases
            or (options.structural and members and set(members) <= set(resolved))
        ]
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
    """Read sources as '(posix path, text)' pairs."""
    return [
        (path.as_posix(), path.read_text(encoding="utf-8"))
        for path in _python_files(paths)
    ]


_SELF_TEST_PORT = """
from typing import Protocol

class DocumentStore(Protocol):
    async def get(self, key: str) -> bytes: ...
    def put(self, key: str, data: bytes, *, overwrite: bool = False) -> None: ...
    limit: int

class AuditedStore(DocumentStore, Protocol):
    def history(self, key: str, /) -> list[str]: ...

class Unused(Protocol):
    def ping(self) -> None: ...
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
    }
    failures = [
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    ]
    if "GoodStore" in rendered:
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
        argv: Command-line arguments; 'sys.argv[1:]' when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on usage or read errors.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        for failure in failures:
            print(failure, file=sys.stderr)
        if failures:
            return 1
        print("check_ports_adapters self-test passed.")
        return 0
    if not args.ports:
        parser.error("at least one '--ports' path is required")
    missing = [path for path in [*args.ports, *args.paths] if not path.exists()]
    if missing:
        for path in missing:
            print(f"{path.as_posix()}: path does not exist", file=sys.stderr)
        return 2
    try:
        port_sources = _read(args.ports)
        sources = _read(args.paths)
    except (OSError, UnicodeDecodeError) as error:
        print(f"cannot read sources: {error}", file=sys.stderr)
        return 2
    options = Options(
        structural=not args.explicit_only,
        report_extra=not args.ignore_extra,
        allow_extra=frozenset(args.allow_extra),
        require_implementation=not args.allow_unimplemented,
        skip=frozenset(args.skip),
    )
    findings = analyze(port_sources, sources, options=options)
    for finding in findings:
        print(finding.render())
    if not findings:
        print(f"Ports and adapters agree ({len(port_sources)} port module(s)).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
