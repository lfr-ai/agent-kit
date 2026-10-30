# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Flag Polars patterns that defeat the query optimizer or use removed APIs.

Python sources are parsed without importing them. Only files that import
``polars`` are inspected. Findings cover ``map_elements`` (Python UDFs) without
``return_dtype``, row iteration (``iter_rows``, ``rows``), eager reads followed by
``.lazy()``, ``.collect().lazy()`` round trips, the deprecated ``collect(streaming=)``
flag, argument-less ``pl.count()``, and renamed APIs (``groupby``, ``with_row_count``,
``map_dict``, ``cumsum`` family). A line carrying ``# polars: reviewed`` is waived.
Exit 0 means no findings, 1 means findings or unreadable sources.
Run ``--self-test`` for built-in regressions.
"""

import argparse
import ast
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
import sys

_WAIVER = "# polars: reviewed"
_EAGER_READS = frozenset({"read_csv", "read_parquet", "read_ipc", "read_ndjson"})
_ROW_LOOPS = frozenset({"iter_rows", "rows", "iterrows"})
_RENAMED = {
    "groupby": "group_by",
    "with_row_count": "with_row_index",
    "map_dict": "replace or replace_strict",
    "cumsum": "cum_sum",
    "cumprod": "cum_prod",
    "cummin": "cum_min",
    "cummax": "cum_max",
    "cumcount": "cum_count",
}


def _attribute(node: ast.expr) -> str | None:
    """Return the attribute name of a method call target.

    Args:
        node: Call function expression.

    Returns:
        The attribute name, or None when the call is not a method call.
    """
    return node.attr if isinstance(node, ast.Attribute) else None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return a keyword argument value.

    Args:
        call: Call node.
        name: Keyword name.

    Returns:
        The value node, or None.
    """
    return next((item.value for item in call.keywords if item.arg == name), None)


def _classify(call: ast.Call, modules: set[str]) -> str | None:
    """Return a finding for one call, if any.

    Args:
        call: Call node.
        modules: Local names bound to the ``polars`` module.

    Returns:
        Message, or None.
    """
    method = _attribute(call.func)
    if method is None:
        return None
    receiver = call.func.value if isinstance(call.func, ast.Attribute) else None
    inner = receiver.func if isinstance(receiver, ast.Call) else None
    inner_method = _attribute(inner) if inner is not None else None
    messages = {
        "map_elements": "map_elements runs a Python UDF per value; prefer native "
        "expressions or set return_dtype",
        "lazy_after_read": f"eager {inner_method} then .lazy(); use the scan_* "
        "function so pushdown applies",
        "collect_lazy": ".collect().lazy() materializes mid-pipeline; keep the "
        "chain lazy",
        "row_loop": f".{method}() iterates rows in Python; use expressions",
        "streaming_flag": "collect(streaming=...) is deprecated; use the engine "
        "parameter",
        "count": "pl.count() without arguments is deprecated; use pl.len()",
    }
    rules = (
        (
            "map_elements",
            method == "map_elements" and not _keyword(call, "return_dtype"),
        ),
        ("lazy_after_read", method == "lazy" and inner_method in _EAGER_READS),
        ("collect_lazy", method == "lazy" and inner_method == "collect"),
        ("row_loop", method in _ROW_LOOPS),
        (
            "streaming_flag",
            method == "collect" and _keyword(call, "streaming") is not None,
        ),
        (
            "count",
            method == "count"
            and not call.args
            and isinstance(receiver, ast.Name)
            and receiver.id in modules,
        ),
    )
    for key, hit in rules:
        if hit:
            return messages[key]
    if method in _RENAMED:
        return f".{method}() was renamed; use {_RENAMED[method]}"
    return None


def check_source(text: str, path: str) -> list[str]:
    """Report Polars anti-patterns in one source file.

    Args:
        text: Python source.
        path: Display path.

    Returns:
        Findings formatted as ``path:line: message``.

    Raises:
        SyntaxError: The source cannot be parsed.
    """
    tree = ast.parse(text, filename=path)
    imports_polars, modules = _polars_bindings(tree)
    if not imports_polars:
        return []
    lines = text.splitlines()
    findings: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        message = _classify(node, modules)
        line = node.func.end_lineno or node.lineno
        if message and _WAIVER not in lines[line - 1]:
            findings.add((line, f"{path}:{line}: {message}"))
    return [message for _, message in sorted(findings)]


def _polars_bindings(tree: ast.Module) -> tuple[bool, set[str]]:
    """Return whether a module imports Polars and its local module aliases.

    Args:
        tree: Parsed module.

    Returns:
        Whether any Polars import exists, and names bound to ``polars``.
    """
    modules: set[str] = set()
    imports_polars = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases = _polars_aliases(node)
            imports_polars = imports_polars or bool(aliases)
            modules.update(
                alias.asname or "polars" for alias in aliases if alias.name == "polars"
            )
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "polars"
        ):
            imports_polars = True
    return imports_polars, modules


def _polars_aliases(node: ast.Import) -> list[ast.alias]:
    """Return the aliases of an ``import`` statement that name Polars modules.

    Args:
        node: Import statement.

    Returns:
        Aliases for ``polars`` or one of its submodules.
    """
    return [
        alias
        for alias in node.names
        if alias.name == "polars" or alias.name.startswith("polars.")
    ]


def _python_files(targets: Sequence[Path]) -> tuple[list[Path], list[str]]:
    """Expand targets into Python files.

    Args:
        targets: Files or directories.

    Returns:
        Sorted files and findings for missing targets.
    """
    files: set[Path] = set()
    problems: list[str] = []
    for target in targets:
        if not target.exists() or target.is_symlink():
            problems.append(f"{target.as_posix()}:1: missing or linked target")
            continue
        candidates = [target] if target.is_file() else target.rglob("*.py")
        files.update(
            path
            for path in candidates
            if path.suffix == ".py"
            and not path.is_symlink()
            and not {"__pycache__", ".venv", "node_modules"}.intersection(path.parts)
        )
    return sorted(files), problems


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    MISSED_POLARS_ISSUE = "missed Polars issue: {source!r} {found}"
    FALSE_POSITIVE = "false positive: {source!r}"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        source: str | None = None,
        found: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            source: Observed source for the failing case.
            found: Observed found for the failing case.
        """
        super().__init__(issue.value.format(source=source, found=found))


def self_test() -> None:
    """Exercise each rule, waivers, and clean lazy pipelines.

    Raises:
        SelfTestError: A regression was detected.
    """
    risky = {
        "import polars as pl\npl.col('a').map_elements(str.upper)\n": "map_elements",
        "import polars as pl\nfor row in df.iter_rows(): ...\n": "iterates rows",
        "import polars as pl\npl.read_parquet('a.parquet').lazy()\n": "scan_*",
        "import polars as pl\nlf.collect().lazy()\n": "materializes",
        "import polars as pl\nlf.collect(streaming=True)\n": "engine",
        "import polars as pl\ndf.select(pl.count())\n": "pl.len()",
        "import polars as pl\ndf.groupby('a').agg()\n": "group_by",
        "from polars import DataFrame\ndf.with_row_count()\n": "with_row_index",
    }
    for source, fragment in risky.items():
        found = check_source(source, "app/report.py")
        if len(found) != 1 or fragment not in found[0]:
            raise SelfTestError(
                SelfTestIssue.MISSED_POLARS_ISSUE, source=source, found=found
            )
    clean = (
        (
            "import polars as pl\n"
            "out = pl.scan_parquet('a').group_by('k').agg(pl.len()).sort('k').collect()\n"
        ),
        "import polars as pl\npl.col('a').map_elements(f, return_dtype=pl.Int64)\n",
        "import polars as pl\nfor row in df.iter_rows():  # polars: reviewed\n    ...\n",
        "import pandas as pd\ndf.groupby('a').cumsum()\n",
        "import polars as pl\ndf.select(pl.col('a').count())\n",
    )
    for source in clean:
        if check_source(source, "app/report.py"):
            raise SelfTestError(SelfTestIssue.FALSE_POSITIVE, source=source)


def main(argv: list[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 when clean, 1 when findings were reported.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        sys.stdout.write("check_polars_usage self-test passed.\n")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    files, findings = _python_files(args.paths)
    for path in files:
        display = path.as_posix()
        try:
            findings.extend(check_source(path.read_text(encoding="utf-8"), display))
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{display}:1: source cannot be read or parsed")
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
