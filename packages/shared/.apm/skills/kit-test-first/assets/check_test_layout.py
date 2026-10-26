"""Check that a test suite follows its tier layout and that every test asserts.

Rules:

- ``outside-tier``: a test module (``test_*.py`` or ``*_test.py``) that is not
  inside one of the tier directories directly under the tests root. Default
  tiers: ``unit``, ``integration``, ``property``, ``e2e``, ``contract``;
  replace them with repeated ``--tier`` options.
- ``module-name``: a Python file that defines ``test_*`` functions but is not
  named ``test_*.py`` (``conftest.py`` is exempt), so the default pytest
  discovery or the project convention would miss or mis-tier it.
- ``no-assertion``: a ``test_*`` function or ``Test*`` method with no
  ``assert`` statement, no ``pytest.raises``/``warns``/``fail``/
  ``deprecated_call`` call, and no call to a helper whose name starts with
  ``assert``. Such a test passes whatever the code does. Functions decorated
  with ``fixture`` or ``pytest.fixture`` are fixtures, not tests, and are
  exempt even when named ``test_*``.

Directories named ``__pycache__``, ``.hypothesis`` and ``.pytest_cache`` are
skipped. Output is one ``path:line: [rule] message`` per finding, sorted.
Exit status: 0 when clean, 1 when findings exist, 2 for usage or read errors.

Example:
    python check_test_layout.py tests --tier unit --tier integration
    python check_test_layout.py --self-test
"""

import argparse
import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile

_USAGE_ERROR = 2
DEFAULT_TIERS: tuple[str, ...] = ("unit", "integration", "property", "e2e", "contract")
_CACHE_DIRECTORIES = frozenset({"__pycache__", ".hypothesis", ".pytest_cache"})
_PYTEST_EXPECTATIONS = frozenset({"raises", "warns", "fail", "deprecated_call"})


@dataclass(frozen=True, kw_only=True, slots=True, order=True)
class Issue:
    """One layout or assertion problem.

    Attributes:
        path: POSIX path relative to the tests root's parent.
        line: One-based line, or 1 for a whole-file problem.
        rule: Rule identifier.
        message: Description and fix.
    """

    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        """Return ``path:line: [rule] message``."""
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


def is_test_module_name(name: str) -> bool:
    """Return whether a file name is a pytest test module name.

    Args:
        name: File name without directories.

    Returns:
        True for ``test_*.py`` and ``*_test.py``.
    """
    return name.endswith(".py") and (
        name.startswith("test_") or name.endswith("_test.py")
    )


def _expectation_call(node: ast.Call) -> bool:
    """Return whether a call is a pytest expectation or an ``assert*`` helper."""
    func = node.func
    if isinstance(func, ast.Attribute):
        owner_is_pytest = isinstance(func.value, ast.Name) and func.value.id == "pytest"
        return (owner_is_pytest and func.attr in _PYTEST_EXPECTATIONS) or (
            func.attr.startswith("assert")
        )
    return isinstance(func, ast.Name) and func.id.startswith("assert")


def asserts_something(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return whether a test body contains an assertion or expectation.

    Args:
        function: Test function or method definition.

    Returns:
        True when the body has ``assert``, a pytest expectation, or an
        ``assert*`` helper call.
    """
    return any(
        isinstance(node, ast.Assert)
        or (isinstance(node, ast.Call) and _expectation_call(node))
        for node in ast.walk(function)
    )


def find_tests(
    tree: ast.Module,
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield module-level ``test_*`` functions and ``test_*`` methods of ``Test*`` classes.

    Args:
        tree: Parsed module.

    Yields:
        Test function definitions in source order.
    """
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            yield from _tests_in(node.body)
        else:
            yield from _tests_in([node])


def _tests_in(
    body: Sequence[ast.stmt],
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield the test definitions among statements, skipping pytest fixtures."""
    for node in body:
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test")
            and not any(_is_fixture(item) for item in node.decorator_list)
        ):
            yield node


def _is_fixture(decorator: ast.expr) -> bool:
    """Return whether a decorator is ``fixture`` or ``pytest.fixture``, called or not."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Attribute):
        return target.attr == "fixture"
    return isinstance(target, ast.Name) and target.id == "fixture"


def check_module(path: str, text: str, *, in_tier: bool) -> list[Issue]:
    """Check one Python file under the tests root.

    Args:
        path: Display path.
        text: Module source.
        in_tier: Whether the file lies inside an accepted tier directory.

    Returns:
        Issues for the file.
    """
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as error:
        return [
            Issue(path=path, line=error.lineno or 1, rule="syntax", message=error.msg)
        ]
    name = Path(path).name
    tests = list(find_tests(tree))
    issues = [
        Issue(
            path=path,
            line=test.lineno,
            rule="no-assertion",
            message=f"{test.name} asserts nothing; add an assert or pytest.raises",
        )
        for test in tests
        if not asserts_something(test)
    ]
    if is_test_module_name(name) and not in_tier:
        issues.append(
            _issue(path, "outside-tier", "move the module into a tier directory")
        )
    if tests and name != "conftest.py" and not name.startswith("test_"):
        issues.append(
            _issue(path, "module-name", "rename the module to test_<subject>.py")
        )
    return issues


def _issue(path: str, rule: str, message: str) -> Issue:
    """Build a whole-file issue."""
    return Issue(path=path, line=1, rule=rule, message=message)


def check_tree(root: Path, *, tiers: Sequence[str] = DEFAULT_TIERS) -> list[Issue]:
    """Check every Python file under a tests root.

    Args:
        root: Tests directory, for example ``tests``.
        tiers: Directory names directly under ``root`` that hold tests.

    Returns:
        Sorted issues.

    Raises:
        OSError: If a file cannot be read.
        UnicodeDecodeError: If a file is not UTF-8.
    """
    issues: list[Issue] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if _CACHE_DIRECTORIES.intersection(relative.parts):
            continue
        in_tier = len(relative.parts) > 1 and relative.parts[0] in tiers
        display = (Path(root.name) / relative).as_posix()
        issues.extend(
            check_module(display, path.read_text(encoding="utf-8"), in_tier=in_tier)
        )
    return sorted(issues)


_SELF_TEST_TREE = {
    "conftest.py": "import pytest\n",
    "factories.py": "def build() -> int:\n    return 1\n",
    "test_root.py": "def test_lonely():\n    assert True\n",
    "unit/test_good.py": (
        "import pytest\n"
        "def test_sum_is_exact():\n    assert 1 + 1 == 2\n"
        "def test_bad_input_raises():\n"
        "    with pytest.raises(ValueError):\n        int('x')\n"
        "class TestRefund:\n"
        "    def test_reason_is_kept(self):\n        assert_refunded()\n"
    ),
    "unit/invoice_test.py": "def test_total_matches():\n    assert True\n",
    "unit/test_quiet.py": "def test_runs_only():\n    compute()\n",
}
_SELF_TEST_ISSUES = (
    "tests/test_root.py:1: [outside-tier]",
    "tests/unit/invoice_test.py:1: [module-name]",
    "tests/unit/test_quiet.py:1: [no-assertion]",
)


def self_test() -> list[str]:
    """Check a synthetic suite in a temporary directory.

    Returns:
        Unmet expectations; empty when the rules behave as documented.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "tests"
        for relative, text in _SELF_TEST_TREE.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        reported = [issue.render() for issue in check_tree(root)]
    unmet = [
        f"expected an issue starting with {prefix}"
        for prefix in _SELF_TEST_ISSUES
        if not any(line.startswith(prefix) for line in reported)
    ]
    if len(reported) != len(_SELF_TEST_ISSUES):
        unmet.append(f"unexpected issues: {reported}")
    return unmet


def _report_self_test() -> int:
    """Print the self-test verdict; return 0 when it passed and 1 otherwise."""
    unmet = self_test()
    for line in unmet:
        print(line, file=sys.stderr)
    verdict = "failed" if unmet else "passed"
    print(f"check_test_layout self-test {verdict}.")
    return int(bool(unmet))


def main(argv: list[str] | None = None) -> int:
    """Check a tests directory and print issues.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when issues exist, 2 on usage or read errors.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", nargs="?", type=Path, default=Path("tests"))
    parser.add_argument(
        "--tier", action="append", default=[], help="tier directory name; repeatable"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="check a built-in synthetic suite"
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return _report_self_test()
    if not args.root.is_dir():
        print(f"{args.root.as_posix()}: tests root is not a directory", file=sys.stderr)
        return _USAGE_ERROR
    try:
        issues = check_tree(args.root, tiers=tuple(args.tier) or DEFAULT_TIERS)
    except (OSError, UnicodeDecodeError) as error:
        print(f"cannot read tests: {error}", file=sys.stderr)
        return _USAGE_ERROR
    for issue in issues:
        print(issue.render())
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
