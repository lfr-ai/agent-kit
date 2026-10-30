# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check that test function names describe behavior, not just existence.

A test name is the first line of its failure report. ``test_1`` or ``test_it``
says nothing when it fails; ``test_paid_invoice_cannot_be_voided`` says what
broke. Rules:

- Test functions (``test*`` at module level, and ``test*`` methods of ``Test*``
  classes) need at least ``--min-words`` words after the ``test`` prefix
  (default 3), counting underscore-separated parts.
- Generic names from a built-in list (``test_it``, ``test_works``, ``test_basic``,
  ...) and numbered names (``test_1``, ``test_case_2``) are reported regardless of
  length; extend the list with ``--forbid``.
- A test defined twice in the same module or class is reported: Python keeps
  only the last definition, so the first one never runs.

Exempt individual names with ``--allow``. Output lines are ``path:line: message``;
the exit status is 1 when anything is reported.

Example:
    python check_test_naming.py tests --min-words 3 --forbid test_happy_path
"""

import argparse
import ast
from collections.abc import Iterable, Sequence
import fnmatch
from pathlib import Path
import re
import sys
from typing import NamedTuple

_GENERIC = frozenset(
    {
        "test",
        "test_it",
        "test_works",
        "test_it_works",
        "test_basic",
        "test_simple",
        "test_ok",
        "test_success",
        "test_fail",
        "test_foo",
        "test_bar",
        "test_example",
        "test_sample",
        "test_something",
        "test_stuff",
        "test_thing",
        "test_function",
        "test_method",
        "test_main",
        "test_all",
        "test_misc",
        "test_new",
        "test_tmp",
        "test_temp",
        "test_default",
        "test_edge_case",
        "test_happy_path",
    }
)
_NUMBERED = re.compile(r"test_?(?:[a-z]+_)?\d+")
_TEST_PATTERNS = ("test_*.py", "*_test.py")
_EXCLUDED_DIRS = frozenset(
    {".git", ".venv", "venv", ".tox", "node_modules", "__pycache__", "build", "dist"}
)
_EXIT_USAGE = 2
_DEFAULT_MIN_WORDS = 3


class Options(NamedTuple):
    """Rule switches.

    Attributes:
        min_words: Minimum words after the ``test`` prefix.
        forbidden: Names that are always reported.
        allowed: Names that are never reported.
    """

    min_words: int = _DEFAULT_MIN_WORDS
    forbidden: frozenset[str] = _GENERIC
    allowed: frozenset[str] = frozenset()


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


def words(name: str) -> list[str]:
    """Split a test name into the words after its ``test`` prefix.

    Args:
        name: Function name such as ``test_paid_invoice_cannot_be_voided``.

    Returns:
        [``paid``, ``invoice``, ``cannot``, ``be``, ``voided``].
    """
    return [part for part in name.removeprefix("test").split("_") if part]


def name_problem(name: str, *, options: Options) -> str | None:
    """Describe why a test name is not descriptive, if it is not.

    Args:
        name: Test function name.
        options: Rule switches.

    Returns:
        A message, or None for an acceptable name.
    """
    if name in options.allowed:
        return None
    if name in options.forbidden:
        return f"test name '{name}' is generic; name the behavior and outcome"
    parts = words(name)
    if _NUMBERED.fullmatch(name) or (parts and all(part.isdigit() for part in parts)):
        return f"test name '{name}' is numbered; name the behavior and outcome"
    if len(parts) < options.min_words:
        return (
            f"test name '{name}' has {len(parts)} word(s); use at least "
            f"{options.min_words} to describe the behavior and outcome"
        )
    return None


def _scope_tests(
    body: Sequence[ast.stmt], path: str, options: Options
) -> list[Finding]:
    """Check test functions defined directly in one module or class body."""
    findings: list[Finding] = []
    seen: dict[str, int] = {}
    for node in body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test"):
            continue
        if node.name in seen:
            findings.append(
                Finding(
                    path,
                    node.lineno,
                    f"'{node.name}' redefines the test on line {seen[node.name]}; "
                    "the earlier test never runs",
                )
            )
        seen[node.name] = node.lineno
        problem = name_problem(node.name, options=options)
        if problem:
            findings.append(Finding(path, node.lineno, problem))
    return findings


def check_source(path: str, text: str, *, options: Options) -> list[Finding]:
    """Check test names in one module, including ``Test*`` classes.

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
    findings = _scope_tests(tree.body, path, options)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            findings.extend(_scope_tests(node.body, path, options))
    return findings


def check_files(
    sources: Iterable[tuple[str, str]], *, options: Options
) -> list[Finding]:
    """Check several test modules.

    Args:
        sources: ``(path, text)`` pairs.
        options: Rule switches.

    Returns:
        Findings sorted by path, line and message.
    """
    findings: list[Finding] = []
    for path, text in sources:
        findings.extend(check_source(path, text, options=options))
    return sorted(findings)


def _test_files(paths: Sequence[Path]) -> list[Path]:
    """Expand paths into test modules."""
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*.py")
                if any(
                    fnmatch.fnmatch(candidate.name, pattern)
                    for pattern in _TEST_PATTERNS
                )
                and not _EXCLUDED_DIRS.intersection(candidate.parts)
            )
    return sorted(files)


_SELF_TEST_SOURCE = """
def test_1(): ...
def test_it(): ...
def test_total(): ...
def test_case_2(): ...
def test_paid_invoice_cannot_be_voided(): ...
def test_paid_invoice_cannot_be_voided(): ...
def helper(): ...

class TestInvoice:
    def test_works(self): ...
    async def test_void_invoice_rejects_payment(self): ...

class Builder:
    def test(self): ...
"""


def self_test() -> list[str]:
    """Run the rules on an in-memory module and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    rendered = "\n".join(
        finding.render()
        for finding in check_files(
            [("tests/test_names.py", _SELF_TEST_SOURCE)], options=Options()
        )
    )
    expectations = {
        "numbered": "'test_1' is numbered",
        "generic": "'test_it' is generic",
        "too short": "'test_total' has 1 word(s)",
        "numbered case": "'test_case_2' is numbered",
        "redefined": "redefines the test on line 6",
        "generic method": "'test_works' is generic",
    }
    failures = [
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    ]
    failures.extend(
        f"unexpected finding for {needle}"
        for needle in ("void_invoice", "helper", ":15:")
        if needle in rendered
    )
    relaxed = check_files(
        [("tests/test_names.py", "def test_total(): ...\ndef test_it(): ...\n")],
        options=Options(min_words=1, allowed=frozenset({"test_it"})),
    )
    if relaxed:
        failures.append(f"relaxed options still reported: {relaxed}")
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("tests")])
    parser.add_argument(
        "--min-words", type=int, default=_DEFAULT_MIN_WORDS, metavar="N"
    )
    parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        metavar="NAME",
        help="extra generic test name to report; repeatable",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="NAME",
        help="test name never reported; repeatable",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Check test names and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on usage or read errors.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if args.min_words < 1:
        parser.error("--min-words must be at least 1")
    if _report_missing(args.paths):
        return _EXIT_USAGE
    options = Options(
        min_words=args.min_words,
        forbidden=_GENERIC | frozenset(args.forbid),
        allowed=frozenset(args.allow),
    )
    try:
        sources = [
            (path.as_posix(), path.read_text(encoding="utf-8"))
            for path in _test_files(args.paths)
        ]
    except (OSError, UnicodeDecodeError) as error:
        sys.stderr.write(f"cannot read tests: {error}\n")
        return _EXIT_USAGE
    findings = check_files(sources, options=options)
    return _report(findings, file_count=len(sources))


def _report(findings: list[Finding], *, file_count: int) -> int:
    """Print findings or a success line and return the exit status."""
    for finding in findings:
        sys.stdout.write(f"{finding.render()}\n")
    if not findings:
        sys.stdout.write(f"Test names are descriptive in {file_count} file(s).\n")
    return 1 if findings else 0


def _run_self_test() -> int:
    """Print self-test failures and return the matching exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write("check_test_naming self-test passed.\n")
    return 0


def _report_missing(paths: Iterable[Path]) -> bool:
    """Print each path that does not exist and return whether any is missing."""
    missing = [path for path in paths if not path.exists()]
    for path in missing:
        sys.stderr.write(f"{path.as_posix()}: path does not exist\n")
    return bool(missing)


if __name__ == "__main__":
    raise SystemExit(main())
