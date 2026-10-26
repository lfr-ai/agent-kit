"""Flag FastAPI wiring mistakes that tests rarely catch, without importing code.

Rules (select with ``--rule``, repeatable; default: all):

- ``router-not-included``: an ``APIRouter()`` assigned to a name is never passed
  to ``include_router`` in the scanned files. Matching uses the defining
  module's file stem (the folder name for ``__init__.py``) and the router name,
  resolving absolute and relative imports, so scan the whole package.
- ``blocking-call``: a known blocking call (``time.sleep``, ``requests``,
  synchronous ``httpx`` helpers and ``httpx.Client``, ``urllib.request.urlopen``,
  ``subprocess``, ``socket.create_connection``) inside an ``async def``, matched
  only when the call's first name is bound by an import.
  Run such work in a sync handler, an async client, or a worker thread.
- ``cors-credentials-wildcard``: ``CORSMiddleware`` configured with
  ``allow_credentials=True`` and ``allow_origins`` containing ``"*"`` or an
  ``allow_origin_regex`` of ``.*``; Starlette then reflects any origin.
- ``on-event``: ``@app.on_event`` handlers, deprecated in favor of lifespan.

Redundant ``response_model`` arguments are reported by the
``check_response_model_redundancy.py`` checker of ``kit-api-contracts``.

Output: one ``path:line: [rule] message`` line per finding on stdout, sorted.
Exit codes: 0 no findings, 1 findings, 2 usage error or unreadable input.
Run ``--self-test`` for built-in regressions.
"""

import argparse
import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
import sys

_EXIT_FINDINGS = 1
_EXIT_INPUT_ERROR = 2
_EXCLUDED = frozenset({".venv", "venv", "node_modules", "build", "dist", "__pycache__"})
RULES = (
    "router-not-included",
    "blocking-call",
    "cors-credentials-wildcard",
    "on-event",
)
_BLOCKING_EXACT = frozenset(
    {
        "time.sleep",
        "urllib.request.urlopen",
        "socket.create_connection",
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "os.system",
        "httpx.get",
        "httpx.post",
        "httpx.put",
        "httpx.patch",
        "httpx.delete",
        "httpx.head",
        "httpx.request",
        "httpx.Client",
    }
)
_BLOCKING_MODULES = ("requests.",)
_WILDCARD_REGEXES = frozenset({".*", "^.*$", ".+", "^.+$"})


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One rule violation.

    Attributes:
        path: Display path of the source file.
        line: One-based line number.
        rule: Rule identifier.
        message: Actionable description.
    """

    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        """Return the ``path:line: [rule] message`` form."""
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class _RouterDefinition:
    """A router assignment with the key used to match inclusions."""

    path: str
    line: int
    key: tuple[str, str]


@dataclass(frozen=True, kw_only=True, slots=True)
class ModuleFacts:
    """Facts extracted from one module.

    Attributes:
        findings: Per-module findings for local rules.
        routers: Router assignments defined in the module.
        included: ``(module stem, name)`` keys passed to ``include_router``.
    """

    findings: tuple[Finding, ...]
    routers: tuple[_RouterDefinition, ...]
    included: frozenset[tuple[str, str]]


def analyze_source(text: str, path: str) -> ModuleFacts:
    """Extract findings and router facts from one module.

    Args:
        text: Python source text.
        path: Display path used in findings.

    Returns:
        Local findings plus router definitions and inclusions.

    Raises:
        SyntaxError: The source cannot be parsed.
    """
    tree = ast.parse(text, filename=path)
    stem = _module_key(path)
    aliases = _import_aliases(tree)
    findings = [
        *_blocking_calls(tree, path, aliases),
        *_cors_findings(tree, path),
        *_on_event_findings(tree, path),
    ]
    routers = tuple(
        _RouterDefinition(path=path, line=node.lineno, key=(stem, target.id))
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and _is_router_call(node.value, aliases)
        for target in node.targets
        if isinstance(target, ast.Name)
    )
    return ModuleFacts(
        findings=tuple(findings),
        routers=routers,
        included=frozenset(_included_keys(tree, stem, aliases)),
    )


def check_sources(
    sources: Iterable[tuple[str, str]], *, rules: frozenset[str] = frozenset(RULES)
) -> list[str]:
    """Check several modules together so router inclusion spans files.

    Args:
        sources: ``(display path, source text)`` pairs.
        rules: Enabled rule identifiers.

    Returns:
        Rendered findings sorted by path and line.

    Raises:
        SyntaxError: A source cannot be parsed.
    """
    facts = [analyze_source(text, path) for path, text in sources]
    included = {key for fact in facts for key in fact.included}
    findings = [finding for fact in facts for finding in fact.findings]
    findings.extend(
        Finding(
            path=router.path,
            line=router.line,
            rule="router-not-included",
            message=f"router '{router.key[1]}' is never passed to include_router",
        )
        for fact in facts
        for router in fact.routers
        if router.key not in included
    )
    selected = [finding for finding in findings if finding.rule in rules]
    return [
        finding.render()
        for finding in sorted(
            selected, key=lambda item: (item.path, item.line, item.rule)
        )
    ]


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local names to the dotted names they import.

    Args:
        tree: Parsed module.

    Returns:
        Local name to fully qualified name, for example ``sleep`` to ``time.sleep``.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                aliases[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom):
            aliases.update(_from_import_aliases(node))
    return aliases


def _from_import_aliases(node: ast.ImportFrom) -> dict[str, str]:
    """Map names bound by one ``from`` import, including relative imports.

    Relative imports keep only the module path written after the dots, which
    is enough because inclusion keys use the last module segment.

    Args:
        node: ``from ... import`` statement.

    Returns:
        Local name to dotted name; ``from . import items`` maps to ``items``.
    """
    return {
        alias.asname or alias.name: (
            f"{node.module}.{alias.name}" if node.module else alias.name
        )
        for alias in node.names
        if alias.name != "*"
    }


def _module_key(path: str) -> str:
    """Return the name importers use for a module; packages use their folder."""
    module = Path(path)
    return module.parent.name if module.stem == "__init__" else module.stem


def _dotted(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """Return the import-resolved dotted name of a call target, if static."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(aliases.get(node.id, node.id))
    return ".".join(reversed(parts))


def _imported_dotted(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """Return the dotted name only when its first name is bound by an import."""
    base = node
    while isinstance(base, ast.Attribute):
        base = base.value
    if not isinstance(base, ast.Name) or base.id not in aliases:
        return None
    return _dotted(node, aliases)


def _is_router_call(node: ast.expr, aliases: dict[str, str]) -> bool:
    """Return whether an expression constructs ``APIRouter``."""
    if not isinstance(node, ast.Call):
        return False
    name = _dotted(node.func, aliases) or ""
    return name == "APIRouter" or name.endswith(".APIRouter")


def _included_keys(
    tree: ast.Module, stem: str, aliases: dict[str, str]
) -> set[tuple[str, str]]:
    """Resolve ``include_router`` arguments to ``(module stem, name)`` keys."""
    keys: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and node.args
        ):
            continue
        target = node.args[0]
        dotted = _dotted(target, aliases)
        if dotted is None:
            continue
        if isinstance(target, ast.Name) and target.id not in aliases:
            keys.add((stem, target.id))
            continue
        module, _, name = dotted.rpartition(".")
        keys.add((module.rpartition(".")[-1], name))
    return keys


def _blocking_calls(
    tree: ast.Module, path: str, aliases: dict[str, str]
) -> list[Finding]:
    """Report blocking calls made directly inside ``async def`` bodies."""
    findings: list[Finding] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.AsyncFunctionDef):
            continue
        for call in _direct_calls(function):
            name = _imported_dotted(call.func, aliases)
            if name and (name in _BLOCKING_EXACT or name.startswith(_BLOCKING_MODULES)):
                findings.append(
                    Finding(
                        path=path,
                        line=call.lineno,
                        rule="blocking-call",
                        message=(
                            f"blocking call '{name}' in async def '{function.name}'; "
                            "use an async client, a sync handler, or a worker thread"
                        ),
                    )
                )
    return findings


def _direct_calls(function: ast.AsyncFunctionDef) -> list[ast.Call]:
    """Return calls in a function body, skipping nested function scopes."""
    calls: list[ast.Call] = []
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(node, ast.Call):
            calls.append(node)
        pending.extend(ast.iter_child_nodes(node))
    return calls


def _cors_findings(tree: ast.Module, path: str) -> list[Finding]:
    """Report CORS configurations that reflect any origin with credentials."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _mentions_cors(node):
            continue
        keywords = {item.arg: item.value for item in node.keywords if item.arg}
        credentials = keywords.get("allow_credentials")
        if not (isinstance(credentials, ast.Constant) and credentials.value is True):
            continue
        if _has_wildcard(keywords.get("allow_origins")) or _is_wildcard_regex(
            keywords.get("allow_origin_regex")
        ):
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    rule="cors-credentials-wildcard",
                    message=(
                        "CORSMiddleware allows credentials for any origin; "
                        "list explicit origins"
                    ),
                )
            )
    return findings


def _mentions_cors(call: ast.Call) -> bool:
    """Return whether a call configures ``CORSMiddleware`` directly or by argument."""
    candidates = [call.func, *call.args[:1]]
    return any(
        (isinstance(item, ast.Name) and item.id == "CORSMiddleware")
        or (isinstance(item, ast.Attribute) and item.attr == "CORSMiddleware")
        for item in candidates
    )


def _has_wildcard(node: ast.expr | None) -> bool:
    """Return whether a literal sequence contains ``"*"``."""
    return isinstance(node, ast.List | ast.Tuple | ast.Set) and any(
        isinstance(item, ast.Constant) and item.value == "*" for item in node.elts
    )


def _is_wildcard_regex(node: ast.expr | None) -> bool:
    """Return whether an origin regex literal matches every origin."""
    return isinstance(node, ast.Constant) and node.value in _WILDCARD_REGEXES


def _on_event_findings(tree: ast.Module, path: str) -> list[Finding]:
    """Report ``on_event`` decorators."""
    return [
        Finding(
            path=path,
            line=decorator.lineno,
            rule="on-event",
            message=f"'{function.name}' uses on_event; move it into the lifespan",
        )
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        for decorator in function.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "on_event"
    ]


def collect(paths: Sequence[Path], *, excluded: frozenset[str]) -> list[Path]:
    """Expand files and directories into Python files.

    Args:
        paths: Files or directories.
        excluded: Directory names to skip.

    Returns:
        Sorted Python files.

    Raises:
        FileNotFoundError: A path does not exist.
    """
    files: set[Path] = set()
    for path in paths:
        if not path.exists():
            msg = f"path does not exist: {path}"
            raise FileNotFoundError(msg)
        candidates = [path] if path.is_file() else path.rglob("*.py")
        files.update(
            candidate
            for candidate in candidates
            if candidate.suffix == ".py"
            and not excluded.intersection(candidate.relative_to(path).parts)
        )
    return sorted(files)


class SelfTestError(AssertionError):
    """A built-in regression failed."""


def self_test() -> None:
    """Exercise each rule with one violating and one clean source.

    Raises:
        SelfTestError: A rule missed a violation or reported a clean source.
    """
    cases = (
        (
            "app.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n",
            "router-not-included",
        ),
        (
            "api.py",
            "import time\nasync def handler():\n    time.sleep(1)\n",
            "blocking-call",
        ),
        (
            "api.py",
            "from requests import get\nasync def handler():\n    get('u')\n",
            "blocking-call",
        ),
        (
            "app.py",
            (
                "app.add_middleware(CORSMiddleware, allow_origins=['*'], "
                "allow_credentials=True)\n"
            ),
            "cors-credentials-wildcard",
        ),
        (
            "app.py",
            "@app.on_event('startup')\nasync def start():\n    pass\n",
            "on-event",
        ),
    )
    for path, source, rule in cases:
        found = check_sources([(path, source)])
        if not any(f"[{rule}]" in item for item in found):
            msg = f"self-test missed {rule}: {found}"
            raise SelfTestError(msg)
    clean = [
        ("items.py", "from fastapi import APIRouter\nrouter = APIRouter()\n"),
        (
            "app.py",
            (
                "import asyncio\nfrom shop.items import router as items\n"
                "app.include_router(items)\n"
                "async def handler():\n    await asyncio.sleep(1)\n"
                "    def worker():\n        time.sleep(1)\n"
                "app.add_middleware(CORSMiddleware, allow_origins=['https://a.test'], "
                "allow_credentials=True)\n"
            ),
        ),
        ("orders.py", "from fastapi import APIRouter\nrouter = APIRouter()\n"),
        ("admin/__init__.py", "from fastapi import APIRouter\nrouter = APIRouter()\n"),
        (
            "main.py",
            (
                "from .orders import router as orders_router\nfrom . import admin\n"
                "app.include_router(orders_router)\napp.include_router(admin.router)\n"
                "async def pending(repo):\n"
                "    requests = await repo.pending()\n    requests.append(1)\n"
            ),
        ),
    ]
    found = check_sources(clean)
    if found:
        msg = f"self-test reported clean sources: {found}"
        raise SelfTestError(msg)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 without findings, 1 with findings, 2 for usage or input errors.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument("--rule", action="append", choices=RULES, default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_fastapi_wiring self-test passed.")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    try:
        files = collect(args.paths, excluded=_EXCLUDED | set(args.exclude))
        sources = [
            (path.as_posix(), path.read_text(encoding="utf-8")) for path in files
        ]
        findings = check_sources(sources, rules=frozenset(args.rule or RULES))
    except (OSError, UnicodeError, SyntaxError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return _EXIT_INPUT_ERROR
    for finding in findings:
        print(finding)
    return _EXIT_FINDINGS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
