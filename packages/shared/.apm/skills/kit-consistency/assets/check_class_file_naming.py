# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check that each module is named after the public class it defines.

A module ``invoice_repository.py`` is expected to define ``InvoiceRepository``.
Rules applied to every scanned module that is not exempt:

- The public top-level classes are counted, ignoring classes whose names end
  with an ``--ignore-suffix`` (default: Error, Exception, Warning) or that derive
  directly from an ``--ignore-base``.
- One counted class must correspond to the module name. With ``--match exact``
  (default) its snake_case name equals the module stem; with ``--match affix``
  either name may extend the other by whole underscore-separated words, so
  ``SqliteInvoiceRepository`` in ``invoice_repository.py`` also passes.
- More than ``--max-public-classes`` counted classes (default 1, 0 = unlimited)
  reports each surplus class as a candidate for its own module or for privacy.

Exempt modules by fnmatch pattern with ``--exempt``; defaults cover package
markers, test modules and conventional grouping modules. Output lines are
``path:line: message``; the exit status is 1 when anything is reported.

Example:
    python check_class_file_naming.py src --match affix --exempt "*/models.py"
"""

import argparse
import ast
from collections.abc import Iterable, Sequence
import fnmatch
from pathlib import Path, PurePosixPath
import re
import sys
from typing import NamedTuple

_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_EXCLUDED_DIRS = frozenset(
    {".git", ".venv", "venv", ".tox", "node_modules", "__pycache__", "build", "dist"}
)
_DEFAULT_EXEMPT = (
    "__init__.py",
    "__main__.py",
    "conftest.py",
    "test_*.py",
    "*_test.py",
    "exceptions.py",
    "errors.py",
    "types.py",
    "constants.py",
)
_DEFAULT_SUFFIXES = ("Error", "Exception", "Warning")
_EXIT_USAGE = 2


class Options(NamedTuple):
    """Policy switches.

    Attributes:
        exempt: fnmatch patterns for module paths or names to skip.
        ignore_suffixes: Class name suffixes that are not counted.
        ignore_bases: Direct base names whose subclasses are not counted.
        match: ``exact`` or ``affix``.
        max_public_classes: Counted classes allowed per module; 0 means unlimited.
    """

    exempt: tuple[str, ...] = _DEFAULT_EXEMPT
    ignore_suffixes: tuple[str, ...] = _DEFAULT_SUFFIXES
    ignore_bases: frozenset[str] = frozenset()
    match: str = "exact"
    max_public_classes: int = 1


class Finding(NamedTuple):
    """One reported problem.

    Attributes:
        path: Module path.
        line: One-based line number.
        message: Human-readable description.
    """

    path: str
    line: int
    message: str

    def render(self) -> str:
        """Return the finding as ``path:line: message``."""
        return f"{self.path}:{self.line}: {self.message}"


def snake_case(name: str) -> str:
    """Convert a CapWords class name to the expected snake_case module stem.

    Args:
        name: Class name such as ``HTTPClient`` or ``InvoiceRepository``.

    Returns:
        ``http_client`` or ``invoice_repository``.
    """
    return _BOUNDARY.sub("_", name).lower()


def names_correspond(class_stem: str, module_stem: str, *, match: str) -> bool:
    """Return whether a class's snake name fits a module stem.

    Args:
        class_stem: snake_case form of the class name.
        module_stem: Module file name without ``.py``.
        match: ``exact``, or ``affix`` to allow whole-word prefixes and suffixes.

    Returns:
        True when the names correspond under the chosen rule.
    """
    if class_stem == module_stem:
        return True
    if match != "affix":
        return False
    longer, shorter = sorted((class_stem, module_stem), key=len, reverse=True)
    return longer.startswith(f"{shorter}_") or longer.endswith(f"_{shorter}")


def _base_name(node: ast.expr) -> str:
    """Return the simple name of a base class expression."""
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _counted(tree: ast.Module, options: Options) -> list[ast.ClassDef]:
    """Return public top-level classes that the one-class rule applies to."""
    return [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and not node.name.startswith("_")
        and not node.name.endswith(options.ignore_suffixes)
        and not {_base_name(base) for base in node.bases} & options.ignore_bases
    ]


def is_exempt(path: str, options: Options) -> bool:
    """Return whether a module path matches an exemption pattern.

    Args:
        path: POSIX module path.
        options: Policy holding the patterns.

    Returns:
        True when the full path or the file name matches a pattern.
    """
    name = PurePosixPath(path).name
    return any(
        fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in options.exempt
    )


def _primary_class(
    classes: list[ast.ClassDef], stem: str, *, options: Options
) -> ast.ClassDef | None:
    """Return the class named after ``stem``, preferring exact over affix matches."""
    exact = [node for node in classes if snake_case(node.name) == stem]
    affix = [
        node
        for node in classes
        if names_correspond(snake_case(node.name), stem, match=options.match)
    ]
    return (exact or affix or [None])[0]


def _mismatch_message(
    classes: list[ast.ClassDef], anchor: ast.ClassDef, stem: str
) -> str:
    """Describe a module whose public classes are not named after it."""
    if len(classes) == 1:
        return (
            f"public class '{anchor.name}' does not match module '{stem}.py' "
            f"(expected '{snake_case(anchor.name)}.py')"
        )
    listed = ", ".join(node.name for node in classes)
    return (
        f"module '{stem}.py' defines public classes {listed} "
        "but none is named after the module"
    )


def check_source(path: str, text: str, *, options: Options) -> list[Finding]:
    """Check one module's classes against its file name.

    Args:
        path: POSIX module path used in findings.
        text: Module source.
        options: Policy switches.

    Returns:
        Findings for this module.
    """
    if is_exempt(path, options):
        return []
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as error:
        return [Finding(path, error.lineno or 1, f"cannot parse: {error.msg}")]
    classes = _counted(tree, options)
    if not classes:
        return []
    stem = PurePosixPath(path).stem
    primary = _primary_class(classes, stem, options=options)
    findings: list[Finding] = []
    anchor = primary or classes[0]
    if primary is None:
        findings.append(
            Finding(path, anchor.lineno, _mismatch_message(classes, anchor, stem))
        )
    others = [node for node in classes if node is not anchor]
    if options.max_public_classes and len(classes) > options.max_public_classes:
        findings.extend(
            Finding(
                path,
                node.lineno,
                f"extra public class '{node.name}' in '{stem}.py'; move it to "
                f"'{snake_case(node.name)}.py' or make it private",
            )
            for node in others[options.max_public_classes - 1 :]
        )
    return findings


def check_files(
    sources: Iterable[tuple[str, str]], *, options: Options
) -> list[Finding]:
    """Check several modules.

    Args:
        sources: ``(path, text)`` pairs.
        options: Policy switches.

    Returns:
        Findings sorted by path, line and message.
    """
    findings: list[Finding] = []
    for path, text in sources:
        findings.extend(check_source(path, text, options=options))
    return sorted(findings)


def _python_files(paths: Sequence[Path]) -> list[Path]:
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


_SELF_TEST_SOURCES = (
    ("pkg/invoice_repository.py", "class InvoiceRepository: ...\n"),
    ("pkg/http_client.py", "class HTTPClient: ...\nclass _Helper: ...\n"),
    ("pkg/orders.py", "class OrderService: ...\n"),
    ("pkg/billing.py", "class Billing: ...\nclass Ledger: ...\nclass Audit: ...\n"),
    ("pkg/reports.py", "class Summary: ...\nclass Detail: ...\n"),
    (
        "pkg/payment_gateway.py",
        "class PaymentGateway: ...\nclass ChargeError(Exception): ...\n",
    ),
    ("pkg/sqlite_store.py", "class SqliteStoreAdapter: ...\n"),
    ("pkg/__init__.py", "class Anything: ...\nclass Else: ...\n"),
    ("pkg/test_orders.py", "class TestOrders: ...\n"),
)


def self_test() -> list[str]:
    """Run the rules on in-memory modules and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    rendered = "\n".join(
        finding.render()
        for finding in check_files(_SELF_TEST_SOURCES, options=Options())
    )
    expectations = {
        "mismatched single class": "'OrderService' does not match module 'orders.py'",
        "extra class": "extra public class 'Ledger' in 'billing.py'",
        "second extra class": "extra public class 'Audit' in 'billing.py'",
        "no primary": "defines public classes Summary, Detail",
        "exact mode rejects affix": "'SqliteStoreAdapter' does not match",
    }
    failures = [
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    ]
    failures.extend(
        f"valid module was reported: {clean}"
        for clean in (
            "invoice_repository",
            "http_client",
            "payment_gateway",
            "__init__",
            "test_orders",
        )
        if clean in rendered
    )
    affix = check_files(
        [("pkg/sqlite_store.py", "class SqliteStoreAdapter: ...\n")],
        options=Options(match="affix"),
    )
    if affix:
        failures.append(f"affix mode rejected a whole-word suffix: {affix}")
    preferred = "\n".join(
        finding.render()
        for finding in check_files(
            [
                (
                    "pkg/settle_invoice.py",
                    "class SettleInvoiceCommand: ...\nclass SettleInvoice: ...\n",
                )
            ],
            options=Options(match="affix"),
        )
    )
    if "'SettleInvoiceCommand'" not in preferred or "'SettleInvoice'" in preferred:
        failures.append(f"exact match was not preferred over affix: {preferred}")
    unlimited = check_files(
        [("pkg/billing.py", "class Billing: ...\nclass Ledger: ...\n")],
        options=Options(max_public_classes=0),
    )
    if unlimited:
        failures.append(f"unlimited mode reported extras: {unlimited}")
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path()])
    parser.add_argument(
        "--exempt",
        action="append",
        default=[],
        metavar="GLOB",
        help="extra module path or name pattern to skip; repeatable",
    )
    parser.add_argument(
        "--no-default-exempt",
        action="store_true",
        help="drop the built-in exemption patterns",
    )
    parser.add_argument(
        "--ignore-suffix",
        action="append",
        default=None,
        metavar="SUFFIX",
        help="class name suffix that is not counted; replaces the defaults",
    )
    parser.add_argument(
        "--ignore-base",
        action="append",
        default=[],
        metavar="NAME",
        help="direct base class whose subclasses are not counted; repeatable",
    )
    parser.add_argument("--match", choices=("exact", "affix"), default="exact")
    parser.add_argument("--max-public-classes", type=int, default=1, metavar="N")
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write("check_class_file_naming self-test passed.\n")
    return 0


def _report_missing(paths: Sequence[Path]) -> bool:
    """Print every nonexistent path and return whether any was found."""
    missing = [path for path in paths if not path.exists()]
    for path in missing:
        sys.stderr.write(f"{path.as_posix()}: path does not exist\n")
    return bool(missing)


def _options(args: argparse.Namespace) -> Options:
    """Build the policy from parsed command-line arguments."""
    exempt = () if args.no_default_exempt else _DEFAULT_EXEMPT
    suffixes = (
        _DEFAULT_SUFFIXES if args.ignore_suffix is None else tuple(args.ignore_suffix)
    )
    return Options(
        exempt=(*exempt, *args.exempt),
        ignore_suffixes=suffixes,
        ignore_bases=frozenset(args.ignore_base),
        match=args.match,
        max_public_classes=args.max_public_classes,
    )


def _report(findings: list[Finding], *, module_count: int) -> int:
    """Print findings or a success summary and return the exit status."""
    for finding in findings:
        sys.stdout.write(f"{finding.render()}\n")
    if not findings:
        sys.stdout.write(f"Class and module names agree in {module_count} module(s).\n")
    return 1 if findings else 0


def main(argv: list[str] | None = None) -> int:
    """Check modules and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on usage or read errors.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if args.max_public_classes < 0:
        parser.error("--max-public-classes must be 0 or more")
    if _report_missing(args.paths):
        return _EXIT_USAGE
    options = _options(args)
    try:
        sources = [
            (path.as_posix(), path.read_text(encoding="utf-8"))
            for path in _python_files(args.paths)
        ]
    except (OSError, UnicodeDecodeError) as error:
        sys.stderr.write(f"cannot read sources: {error}\n")
        return _EXIT_USAGE
    return _report(check_files(sources, options=options), module_count=len(sources))


if __name__ == "__main__":
    raise SystemExit(main())
