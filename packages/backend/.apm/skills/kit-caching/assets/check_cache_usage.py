"""Flag risky in-process caching and unsafe cache deserialization without importing code.

Rules (select with ``--rule``, repeatable; default: all):

- ``method-cache``: ``functools.lru_cache`` or ``functools.cache`` decorates a
  function defined directly in a class body. The instance becomes part of
  every key, so instances stay alive until evicted and all share one bound.
  Functions also decorated with ``staticmethod`` or ``classmethod`` are exempt:
  they hold no instance, and a class object lives for the whole process.
- ``async-cache``: ``lru_cache``, ``cache``, or ``cached_property`` decorates an
  ``async def``. The cache stores the coroutine object, and awaiting it a
  second time raises ``RuntimeError``.
- ``unbounded-cache``: ``functools.cache`` or ``lru_cache(maxsize=None)``
  decorates a function that takes parameters, in a file not matched by
  ``--allow-unbounded``. Functions without parameters hold one entry and are
  exempt (for example a cached settings factory).
- ``pickle-redis``: a module that imports a Redis-compatible client (``redis``,
  ``valkey``, or ``glide``) calls ``pickle.loads``, ``pickle.load``, or
  ``pickle.Unpickler``. Bytes read from a shared store must not be unpickled.

Decorators and calls count only when their name is bound by an import of
``functools`` or ``pickle`` (aliases included), so project helpers that happen
to be named ``cache`` are ignored. Add the comment ``# cache-usage: reviewed``
to the decorator or call line to accept a reviewed finding.

Output: one ``path:line: [rule] message`` line per finding on stdout, sorted.
Exit codes: 0 no findings, 1 findings, 2 usage error or unreadable input.
Run ``--self-test`` for built-in regressions.
"""

import argparse
import ast
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import sys

_EXIT_FINDINGS = 1
_EXIT_INPUT_ERROR = 2
_EXCLUDED = frozenset({".venv", "venv", "node_modules", "build", "dist", "__pycache__"})
RULES = ("method-cache", "async-cache", "unbounded-cache", "pickle-redis")
_MEMO_DECORATORS = frozenset({"lru_cache", "cache"})
_ASYNC_UNSAFE = _MEMO_DECORATORS | {"cached_property"}
_INSTANCE_FREE = frozenset({"staticmethod", "classmethod"})
_REDIS_MODULES = frozenset({"redis", "valkey", "glide"})
_PICKLE_MODULES = frozenset({"pickle", "_pickle"})
_PICKLE_LOADERS = frozenset({"loads", "load", "Unpickler"})
_SUPPRESSION = "# cache-usage: reviewed"
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
type _Function = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One rule violation.

    Attributes:
        path: Source path as given or discovered.
        line: One-based line of the decorator or call.
        rule: Rule identifier from ``RULES``.
        message: Human-readable explanation and fix.
    """

    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        """Render the finding as ``path:line: [rule] message``."""
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class _Bindings:
    """Names a module binds to ``functools``, ``pickle``, and cache clients."""

    functools_modules: frozenset[str]
    functools_names: Mapping[str, str]
    pickle_modules: frozenset[str]
    pickle_names: Mapping[str, str]
    imports_cache_client: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class _Decorator:
    """A resolved ``functools`` decorator applied to a function."""

    name: str
    line: int
    unbounded: bool


def _bindings(tree: ast.Module) -> _Bindings:
    """Collect import aliases for the modules the rules care about."""
    modules: dict[str, set[str]] = {"functools": set(), "pickle": set()}
    names: dict[str, dict[str, str]] = {"functools": {}, "pickle": {}}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _bind_modules(node, modules, imported)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            _bind_names(node, node.module, names, imported)
    return _Bindings(
        functools_modules=frozenset(modules["functools"]),
        functools_names=names["functools"],
        pickle_modules=frozenset(modules["pickle"]),
        pickle_names=names["pickle"],
        imports_cache_client=any(
            module.split(".")[0] in _REDIS_MODULES for module in imported
        ),
    )


def _bind_modules(
    node: ast.Import, modules: dict[str, set[str]], imported: set[str]
) -> None:
    """Record ``import x as y`` bindings of tracked modules."""
    for alias in node.names:
        imported.add(alias.name)
        family = _family(alias.name)
        if family:
            modules[family].add(alias.asname or alias.name)


def _bind_names(
    node: ast.ImportFrom,
    module: str,
    names: dict[str, dict[str, str]],
    imported: set[str],
) -> None:
    """Record ``from x import a as b`` bindings of tracked modules."""
    imported.add(module)
    family = _family(module)
    if family:
        names[family].update(
            {alias.asname or alias.name: alias.name for alias in node.names}
        )


def _family(module: str) -> str | None:
    """Return the tracked family of a module name, if any."""
    if module == "functools":
        return "functools"
    if module in _PICKLE_MODULES:
        return "pickle"
    return None


def _resolve(
    node: ast.expr, modules: frozenset[str], names: Mapping[str, str]
) -> str | None:
    """Return the attribute name a reference resolves to within one module family."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.attr if node.value.id in modules else None
    return None


def _decorator(node: ast.expr, bindings: _Bindings) -> _Decorator | None:
    """Resolve a decorator expression to a ``functools`` caching decorator."""
    target = node.func if isinstance(node, ast.Call) else node
    name = _resolve(target, bindings.functools_modules, bindings.functools_names)
    if name not in _ASYNC_UNSAFE:
        return None
    unbounded = name == "cache" or (
        name == "lru_cache" and isinstance(node, ast.Call) and _maxsize_is_none(node)
    )
    return _Decorator(name=name, line=node.lineno, unbounded=unbounded)


def _maxsize_is_none(call: ast.Call) -> bool:
    """Return whether an ``lru_cache(...)`` call passes ``maxsize=None``."""
    values = [
        *call.args[:1],
        *(kw.value for kw in call.keywords if kw.arg == "maxsize"),
    ]
    return any(
        isinstance(value, ast.Constant) and value.value is None for value in values
    )


def _has_parameters(function: _Function) -> bool:
    """Return whether a function accepts any argument."""
    arguments = function.args
    return bool(
        arguments.posonlyargs
        or arguments.args
        or arguments.kwonlyargs
        or arguments.vararg
        or arguments.kwarg
    )


def _instance_free(function: _Function) -> bool:
    """Return whether a method is a ``staticmethod`` or ``classmethod``."""
    return any(
        isinstance(decorator, ast.Name) and decorator.id in _INSTANCE_FREE
        for decorator in function.decorator_list
    )


def _methods(tree: ast.Module) -> set[int]:
    """Return identities of functions defined directly in a class body."""
    return {
        id(statement)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for statement in node.body
        if isinstance(statement, _FUNCTIONS)
    }


def _decorator_findings(
    path: str, function: _Function, decorator: _Decorator, *, is_method: bool
) -> Iterator[Finding]:
    """Yield findings for one caching decorator on one function."""
    name = function.name
    if isinstance(function, ast.AsyncFunctionDef):
        yield Finding(
            path=path,
            line=decorator.line,
            rule="async-cache",
            message=(
                f"'{decorator.name}' on async '{name}' caches a coroutine that can be "
                "awaited once; cache results with a single-flight async memo instead"
            ),
        )
    if decorator.name not in _MEMO_DECORATORS:
        return
    if is_method and not _instance_free(function):
        yield Finding(
            path=path,
            line=decorator.line,
            rule="method-cache",
            message=(
                f"'{decorator.name}' on method '{name}' keys on self and keeps "
                "instances alive; cache a module-level function of immutable values "
                "or use cached_property"
            ),
        )
    if decorator.unbounded and _has_parameters(function):
        yield Finding(
            path=path,
            line=decorator.line,
            rule="unbounded-cache",
            message=(
                f"'{name}' has an unbounded cache keyed by its arguments; set "
                "lru_cache(maxsize=...) or allow this path with --allow-unbounded"
            ),
        )


def _cache_findings(
    path: str, tree: ast.Module, bindings: _Bindings
) -> Iterator[Finding]:
    """Yield decorator findings for every function in a module."""
    methods = _methods(tree)
    for function in ast.walk(tree):
        if not isinstance(function, _FUNCTIONS):
            continue
        for node in function.decorator_list:
            decorator = _decorator(node, bindings)
            if decorator is not None:
                yield from _decorator_findings(
                    path, function, decorator, is_method=id(function) in methods
                )


def _pickle_findings(
    path: str, tree: ast.Module, bindings: _Bindings
) -> Iterator[Finding]:
    """Yield unpickling calls in modules that import a cache client."""
    if not bindings.imports_cache_client:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _resolve(node.func, bindings.pickle_modules, bindings.pickle_names)
        if name in _PICKLE_LOADERS:
            yield Finding(
                path=path,
                line=node.lineno,
                rule="pickle-redis",
                message=(
                    f"pickle '{name}' in a module that uses a Redis-compatible client; "
                    "decode cached bytes with JSON or another data-only codec"
                ),
            )


def _allowed(path: str, patterns: Sequence[str]) -> bool:
    """Return whether a path matches any glob, anchored at either end."""
    return any(
        fnmatchcase(path, pattern) or PurePosixPath(path).match(pattern)
        for pattern in patterns
    )


def check_source(
    path: str,
    source: str,
    *,
    rules: frozenset[str] = frozenset(RULES),
    allow_unbounded: Sequence[str] = (),
) -> list[Finding]:
    """Check one module's source text.

    Args:
        path: Display path; also matched against ``allow_unbounded``.
        source: Python source text.
        rules: Rules to report.
        allow_unbounded: Globs of files where unbounded caches are accepted.

    Returns:
        Findings sorted by line and rule, minus reviewed suppressions.

    Raises:
        SyntaxError: The source does not parse.
    """
    tree = ast.parse(source, filename=path)
    bindings = _bindings(tree)
    lines = source.splitlines()
    active = set(rules)
    if _allowed(path, allow_unbounded):
        active.discard("unbounded-cache")
    candidates = [
        *_cache_findings(path, tree, bindings),
        *_pickle_findings(path, tree, bindings),
    ]
    kept = [
        finding
        for finding in candidates
        if finding.rule in active and _SUPPRESSION not in lines[finding.line - 1]
    ]
    return sorted(kept, key=lambda finding: (finding.line, finding.rule))


def collect(paths: Sequence[Path], *, excluded: Sequence[str]) -> list[Path]:
    """Expand files and directories into Python files.

    Args:
        paths: Files or directories.
        excluded: Directory or file names, or globs, to skip.

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
            if candidate.suffix == ".py" and not _is_excluded(candidate, path, excluded)
        )
    return sorted(files)


def _is_excluded(candidate: Path, root: Path, excluded: Sequence[str]) -> bool:
    """Return whether a discovered file sits under an excluded name or glob."""
    relative = (
        candidate.relative_to(root) if candidate != root else Path(candidate.name)
    )
    if set(relative.parts) & set(excluded):
        return True
    return _allowed(candidate.as_posix(), excluded)


class SelfTestError(AssertionError):
    """A built-in regression failed."""


_VIOLATIONS = (
    (
        (
            "import functools\nclass Repo:\n    @functools.lru_cache(maxsize=32)\n"
            "    def find(self, key):\n        return key\n"
        ),
        "method-cache",
    ),
    (
        (
            "from functools import lru_cache\n@lru_cache(maxsize=8)\n"
            "async def fetch(key):\n    return key\n"
        ),
        "async-cache",
    ),
    (
        (
            "from functools import cached_property\nclass View:\n    @cached_property\n"
            "    async def total(self):\n        return 1\n"
        ),
        "async-cache",
    ),
    (
        "from functools import cache\n@cache\ndef price(key):\n    return key\n",
        "unbounded-cache",
    ),
    (
        "import functools as ft\n@ft.lru_cache(None)\ndef rate(code):\n    return code\n",
        "unbounded-cache",
    ),
    (
        "import pickle\nimport redis\ndef decode(raw):\n    return pickle.loads(raw)\n",
        "pickle-redis",
    ),
    (
        (
            "from pickle import loads as unpickle\nfrom redis.asyncio import Redis\n"
            "value = unpickle(b'')\n"
        ),
        "pickle-redis",
    ),
)
_CLEAN = (
    (
        "import functools\nclass Units:\n    @staticmethod\n    @functools.lru_cache(maxsize=4)\n"
        "    def parse(text):\n        return text\n    @classmethod\n"
        "    @functools.lru_cache(maxsize=4)\n    def named(cls, text):\n        return text\n"
    ),
    "from functools import cache\n@cache\ndef get_settings():\n    return 1\n",
    "from shop.helpers import cache\n@cache\ndef price(key):\n    return key\n",
    "import pickle\nvalue = pickle.loads(b'')\n",
    (
        "from functools import cache\n@cache  # cache-usage: reviewed\ndef rate(code):\n"
        "    return code\n"
    ),
    "import functools\n@functools.lru_cache\ndef rate(code):\n    return code\n",
)


def self_test() -> None:
    """Exercise each rule with violating and clean sources.

    Raises:
        SelfTestError: A rule missed a violation or reported a clean source.
    """
    for source, rule in _VIOLATIONS:
        found = check_source("case.py", source)
        if not any(finding.rule == rule for finding in found):
            msg = f"self-test missed {rule}: {[str(item) for item in found]}"
            raise SelfTestError(msg)
    for source in _CLEAN:
        found = check_source("clean.py", source)
        if found:
            msg = f"self-test reported a clean source: {[str(item) for item in found]}"
            raise SelfTestError(msg)
    allowed = check_source(
        "src/shop/settings.py",
        "from functools import cache\n@cache\ndef load(name):\n    return name\n",
        allow_unbounded=("*/settings.py",),
    )
    if allowed:
        msg = f"self-test ignored --allow-unbounded: {[str(item) for item in allowed]}"
        raise SelfTestError(msg)


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--exclude", action="append", default=[], help="directory name or glob to skip"
    )
    parser.add_argument(
        "--allow-unbounded",
        action="append",
        default=[],
        help="glob of files where unbounded caches are reviewed and accepted",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_cache_usage self-test passed.")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    try:
        files = collect(args.paths, excluded=[*_EXCLUDED, *args.exclude])
        findings = [
            finding
            for path in files
            for finding in check_source(
                path.as_posix(),
                path.read_text(encoding="utf-8"),
                rules=frozenset(args.rule or RULES),
                allow_unbounded=args.allow_unbounded,
            )
        ]
    except (OSError, UnicodeError, SyntaxError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return _EXIT_INPUT_ERROR
    for finding in findings:
        print(finding)
    return _EXIT_FINDINGS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
