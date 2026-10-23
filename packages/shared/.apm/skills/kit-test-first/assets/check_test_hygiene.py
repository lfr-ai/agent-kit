"""Check test files for habits that make suites slow, flaky or ambiguous.

Rules (each can be switched off):

- Heavy imports at module level: importing a module from the heavy list at the
  top of a test module (outside functions) is reported, because every test run
  pays for it during collection, even when the tests that need it are
  deselected. Import it inside the test or fixture, or use
  ``pytest.importorskip``. Imports under ``if TYPE_CHECKING:`` are ignored.
- Sleeping: ``time.sleep(...)`` anywhere in test code, and ``asyncio.sleep(...)``
  with anything other than a literal 0, are reported. Wait on an explicit
  condition, inject a clock, or use a fake timer instead.
- Duplicate basenames: two test modules with the same file name in different
  directories are reported, because without packages (``__init__.py``) or
  ``--import-mode=importlib`` pytest cannot import both.

Scanned files: ``test_*.py``, ``*_test.py`` and ``conftest.py``. Output lines are
``path:line: message``; the exit status is 1 when anything is reported.

Example:
    python check_test_hygiene.py tests --heavy-module polars --heavy-module torch
"""

import argparse
import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
import fnmatch
from pathlib import Path, PurePosixPath
import sys
from typing import NamedTuple

_DEFAULT_HEAVY = (
    "pandas",
    "numpy",
    "scipy",
    "sklearn",
    "matplotlib",
    "torch",
    "tensorflow",
    "polars",
    "pyspark",
)
_TEST_PATTERNS = ("test_*.py", "*_test.py", "conftest.py")
_EXCLUDED_DIRS = frozenset(
    {".git", ".venv", "venv", ".tox", "node_modules", "__pycache__", "build", "dist"}
)
_EXIT_USAGE = 2


class Options(NamedTuple):
    """Rule switches.

    Attributes:
        heavy_modules: Top-level module names that must not be imported at
            module level in tests.
        check_sleep: Report sleeping calls.
        check_duplicates: Report duplicate test module basenames.
    """

    heavy_modules: frozenset[str] = frozenset(_DEFAULT_HEAVY)
    check_sleep: bool = True
    check_duplicates: bool = True


class Finding(NamedTuple):
    """One reported problem.

    Attributes:
        path: Test file path.
        line: One-based line number.
        message: Human-readable description.
    """

    path: str
    line: int
    message: str

    def render(self) -> str:
        """Return the finding as ``path:line: message``."""
        return f"{self.path}:{self.line}: {self.message}"


def is_test_file(name: str) -> bool:
    """Return whether a file name is a pytest test module or conftest.

    Args:
        name: File name without directories.

    Returns:
        True for ``test_x.py``, ``x_test.py`` and ``conftest.py``.
    """
    return any(fnmatch.fnmatch(name, pattern) for pattern in _TEST_PATTERNS)


def _is_type_checking(node: ast.If) -> bool:
    """Return whether an ``if`` tests ``TYPE_CHECKING`` or ``typing.TYPE_CHECKING``."""
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _import_time_statements(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield statements executed at import time, without entering functions."""
    for node in body:
        yield node
        for block in _import_time_blocks(node):
            yield from _import_time_statements(block)


def _import_time_blocks(node: ast.stmt) -> list[Sequence[ast.stmt]]:
    """Return nested statement blocks that run when ``node`` runs at import time."""
    if isinstance(node, ast.If):
        return [node.orelse] if _is_type_checking(node) else [node.body, node.orelse]
    if isinstance(node, ast.Try | ast.TryStar):
        return [
            node.body,
            node.orelse,
            node.finalbody,
            *(handler.body for handler in node.handlers),
        ]
    if isinstance(node, ast.With | ast.ClassDef):
        return [node.body]
    return []


def _heavy_imports(tree: ast.Module, path: str, heavy: frozenset[str]) -> list[Finding]:
    """Report module-level imports of heavy modules."""
    findings: list[Finding] = []
    for node in _import_time_statements(tree.body):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        findings.extend(
            Finding(
                path,
                node.lineno,
                f"module-level import of heavy module '{name}'; import it inside "
                "the test or fixture that needs it",
            )
            for name in names
            if name.partition(".")[0] in heavy
        )
    return findings


def _aliases(tree: ast.Module) -> tuple[set[str], set[str], set[str], set[str]]:
    """Return local names bound to time, time.sleep, asyncio and asyncio.sleep."""
    time_modules: set[str] = set()
    time_sleeps: set[str] = set()
    asyncio_modules: set[str] = set()
    asyncio_sleeps: set[str] = set()
    modules = {"time": time_modules, "asyncio": asyncio_modules}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in modules:
                    modules[alias.name].add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module in {"time", "asyncio"}:
            target = time_sleeps if node.module == "time" else asyncio_sleeps
            target.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "sleep"
            )
    return time_modules, time_sleeps, asyncio_modules, asyncio_sleeps


def _is_zero(call: ast.Call) -> bool:
    """Return whether the first argument is the literal 0 (a cooperative yield)."""
    if not call.args:
        return any(
            keyword.arg == "delay"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == 0
            for keyword in call.keywords
        )
    first = call.args[0]
    return isinstance(first, ast.Constant) and first.value == 0


def _sleeps(tree: ast.Module, path: str) -> list[Finding]:
    """Report ``time.sleep`` and non-zero ``asyncio.sleep`` calls."""
    time_modules, time_sleeps, asyncio_modules, asyncio_sleeps = _aliases(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        owner = (
            func.value.id
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "sleep"
                and isinstance(func.value, ast.Name)
            )
            else None
        )
        if owner in time_modules or (
            isinstance(func, ast.Name) and func.id in time_sleeps
        ):
            findings.append(
                Finding(
                    path,
                    node.lineno,
                    "time.sleep in tests slows the suite and hides races; wait on "
                    "a condition or inject a clock",
                )
            )
        elif (
            owner in asyncio_modules
            or (isinstance(func, ast.Name) and func.id in asyncio_sleeps)
        ) and not _is_zero(node):
            findings.append(
                Finding(
                    path,
                    node.lineno,
                    "asyncio.sleep with a delay in tests; await an event or "
                    "condition instead",
                )
            )
    return findings


def check_source(path: str, text: str, *, options: Options) -> list[Finding]:
    """Apply the per-file rules to one test module.

    Args:
        path: POSIX path used in findings.
        text: Module source.
        options: Rule switches.

    Returns:
        Findings for this module.
    """
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as error:
        return [Finding(path, error.lineno or 1, f"cannot parse: {error.msg}")]
    findings = _heavy_imports(tree, path, options.heavy_modules)
    if options.check_sleep:
        findings.extend(_sleeps(tree, path))
    return findings


def duplicate_basenames(paths: Iterable[str]) -> list[Finding]:
    """Report test modules whose file names repeat in other directories.

    Args:
        paths: POSIX paths of scanned files.

    Returns:
        One finding per repeated module, pointing at the first occurrence.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted(paths):
        name = PurePosixPath(path).name
        if name != "conftest.py" and is_test_file(name):
            groups[name].append(path)
    return [
        Finding(
            path,
            1,
            f"test module name '{name}' is also used by '{group[0]}'; rename it, "
            "add '__init__.py' packages, or use '--import-mode=importlib'",
        )
        for name, group in sorted(groups.items())
        for path in group[1:]
    ]


def check_files(
    sources: Sequence[tuple[str, str]], *, options: Options
) -> list[Finding]:
    """Check several test modules, including the cross-file duplicate rule.

    Args:
        sources: ``(path, text)`` pairs of test files.
        options: Rule switches.

    Returns:
        Findings sorted by path, line and message.
    """
    findings: list[Finding] = []
    for path, text in sources:
        findings.extend(check_source(path, text, options=options))
    if options.check_duplicates:
        findings.extend(duplicate_basenames(path for path, _ in sources))
    return sorted(findings)


def _test_files(paths: Sequence[Path]) -> list[Path]:
    """Expand paths into test modules and conftest files."""
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*.py")
                if is_test_file(candidate.name)
                and not _EXCLUDED_DIRS.intersection(candidate.parts)
            )
    return sorted(files)


_UNIT_REPORT = """import pandas as pd
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import numpy
import time
def test_report_is_written_after_flush() -> None:
    import scipy
    time.sleep(0.1)
"""
_INTEGRATION_REPORT = """import asyncio
from time import sleep as pause
async def test_worker_drains_queue_before_stop() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(1)
    pause(2)
"""
_SELF_TEST_SOURCES = (
    ("tests/unit/test_report.py", _UNIT_REPORT),
    ("tests/integration/test_report.py", _INTEGRATION_REPORT),
    (
        "tests/unit/test_clean.py",
        "def test_total_is_sum_of_lines() -> None:\n    assert 1 + 1 == 2\n",
    ),
)


def self_test() -> list[str]:
    """Run the rules on in-memory files and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    rendered = "\n".join(
        finding.render()
        for finding in check_files(_SELF_TEST_SOURCES, options=Options())
    )
    expectations = {
        "heavy import": "test_report.py:1: module-level import of heavy module 'pandas'",
        "time.sleep": "unit/test_report.py:8: time.sleep",
        "aliased sleep": "integration/test_report.py:6: time.sleep",
        "asyncio delay": "integration/test_report.py:5: asyncio.sleep",
        "duplicate": "unit/test_report.py:1: test module name 'test_report.py'",
    }
    failures = [
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    ]
    unexpected = ("'numpy'", "'scipy'", "integration/test_report.py:4:", "test_clean")
    failures.extend(
        f"unexpected finding containing {needle}"
        for needle in unexpected
        if needle in rendered
    )
    relaxed = check_files(
        _SELF_TEST_SOURCES,
        options=Options(
            heavy_modules=frozenset(), check_sleep=False, check_duplicates=False
        ),
    )
    if relaxed:
        failures.append(f"disabled rules still reported: {relaxed}")
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("tests")])
    parser.add_argument(
        "--heavy-module",
        action="append",
        default=[],
        metavar="NAME",
        help="top-level module that is slow to import; repeatable",
    )
    parser.add_argument(
        "--no-default-heavy",
        action="store_true",
        help="start from an empty heavy-module list",
    )
    parser.add_argument(
        "--allow-sleep", action="store_true", help="do not report sleeping calls"
    )
    parser.add_argument(
        "--allow-duplicate-basenames",
        action="store_true",
        help="do not report repeated test module names",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Check test files and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on usage or read errors.
    """
    args = _parser().parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if _report_missing(args.paths):
        return _EXIT_USAGE
    heavy = set() if args.no_default_heavy else set(_DEFAULT_HEAVY)
    heavy.update(args.heavy_module)
    options = Options(
        heavy_modules=frozenset(heavy),
        check_sleep=not args.allow_sleep,
        check_duplicates=not args.allow_duplicate_basenames,
    )
    try:
        sources = [
            (path.as_posix(), path.read_text(encoding="utf-8"))
            for path in _test_files(args.paths)
        ]
    except (OSError, UnicodeDecodeError) as error:
        print(f"cannot read tests: {error}", file=sys.stderr)
        return _EXIT_USAGE
    findings = check_files(sources, options=options)
    for finding in findings:
        print(finding.render())
    if not findings:
        print(f"Test hygiene holds for {len(sources)} file(s).")
    return 1 if findings else 0


def _run_self_test() -> int:
    """Print self-test failures and return the matching exit status."""
    failures = self_test()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print("check_test_hygiene self-test passed.")
    return 0


def _report_missing(paths: Iterable[Path]) -> bool:
    """Print each path that does not exist and return whether any is missing."""
    missing = [path for path in paths if not path.exists()]
    for path in missing:
        print(f"{path.as_posix()}: path does not exist", file=sys.stderr)
    return bool(missing)


if __name__ == "__main__":
    raise SystemExit(main())
