"""Statically flag risky operations in Alembic revision files.

The checker parses revision modules without importing them and inspects the
``upgrade`` function (and ``downgrade`` with ``--include-downgrade``). It reports
destructive or locking operations that need an expand/contract plan:
``drop_table``, ``drop_column``, renames, ``alter_column`` type changes, tightening a
column to NOT NULL, adding a NOT NULL column without ``server_default``, raw SQL
that drops or truncates, and, for PostgreSQL, index creation without
``postgresql_concurrently=True`` or concurrent creation outside an
``autocommit_block()``. A finding is waived by the comment
``# migration-safety: reviewed`` on the operation's first line or the line above.
Exit 0 means no findings, 1 means findings or unreadable sources.
Run ``--self-test`` for built-in regressions.
"""

import argparse
import ast
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
import re

_WAIVER = "# migration-safety: reviewed"
_WAIVER_WINDOW_LINES = 2  # the operation line and the line above it
_DIALECTS = ("postgresql", "generic")
_RAW_SQL = re.compile(
    r"\b(DROP\s+(TABLE|COLUMN|SCHEMA|INDEX)|TRUNCATE|ALTER\s+COLUMN\s+\w+\s+TYPE)\b",
    re.IGNORECASE,
)
_INDEX_CREATORS = frozenset({"create_index"})
_INDEX_DROPPERS = frozenset({"drop_index"})
_TIGHTEN_NOT_NULL = (
    "NOT NULL scans the table and fails on existing nulls; "
    "backfill and validate a CHECK constraint first"
)


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return a keyword argument value from a call.

    Args:
        call: Call node.
        name: Keyword name.

    Returns:
        The keyword's value node, or None when absent.
    """
    return next((item.value for item in call.keywords if item.arg == name), None)


def _is_true(node: ast.expr | None) -> bool:
    """Return whether a node is the literal ``True``.

    Args:
        node: Expression or None.

    Returns:
        True only for a literal ``True`` constant.
    """
    return isinstance(node, ast.Constant) and node.value is True


def _is_false(node: ast.expr | None) -> bool:
    """Return whether a node is the literal ``False``.

    Args:
        node: Expression or None.

    Returns:
        True only for a literal ``False`` constant.
    """
    return isinstance(node, ast.Constant) and node.value is False


def _column_not_null_without_default(call: ast.Call) -> bool:
    """Return whether an ``add_column`` call adds NOT NULL without server default.

    Args:
        call: The ``add_column`` call.

    Returns:
        True when a ``Column(...)`` argument has ``nullable=False`` and no
        ``server_default``.
    """
    for argument in call.args:
        if not isinstance(argument, ast.Call):
            continue
        func = argument.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "Column":
            continue
        if _is_false(_keyword(argument, "nullable")) and (
            _keyword(argument, "server_default") is None
        ):
            return True
    return False


def _sql_text(call: ast.Call) -> str:
    """Extract literal SQL from ``op.execute`` arguments, including ``sa.text``.

    Args:
        call: The ``execute`` call.

    Returns:
        Concatenated literal SQL, or an empty string when not literal.
    """
    parts: list[str] = []
    for argument in call.args:
        target = argument
        if isinstance(argument, ast.Call) and argument.args:
            target = argument.args[0]
        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            parts.append(target.value)
    return " ".join(parts)


def _schema_risk(name: str, call: ast.Call) -> str | None:
    """Return the first schema-level risk for an operation.

    Args:
        name: Operation method name.
        call: Call node.

    Returns:
        Human-readable risk, or None.
    """
    is_alter = name == "alter_column"
    risks = {
        "destructive; contract only after no deployed code reads it": name
        in {"drop_table", "drop_column", "drop_constraint"},
        "rename breaks running readers; add, dual-write, then drop": (
            name == "rename_table"
            or (is_alter and _keyword(call, "new_column_name") is not None)
        ),
        "type change may rewrite the table under an exclusive lock": (
            is_alter and _keyword(call, "type_") is not None
        ),
        _TIGHTEN_NOT_NULL: is_alter and _is_false(_keyword(call, "nullable")),
        "NOT NULL column without server_default fails on existing rows": (
            name == "add_column" and _column_not_null_without_default(call)
        ),
    }
    return next((message for message, hit in risks.items() if hit), None)


def _sql_risk(call: ast.Call) -> str | None:
    """Return a risk for literal destructive SQL passed to ``op.execute``.

    Args:
        call: The ``execute`` call.

    Returns:
        Human-readable risk, or None.
    """
    match = _RAW_SQL.search(_sql_text(call))
    if match is None:
        return None
    return f"raw SQL '{match.group(0).upper()}' needs an expand/contract plan"


class _RevisionScanner(ast.NodeVisitor):
    """Collect risky operation findings inside one migration function."""

    def __init__(self, *, operations: set[str], dialect: str) -> None:
        """Create a scanner.

        Args:
            operations: Local names bound to Alembic ``op`` or batch operations.
            dialect: Target dialect, ``postgresql`` or ``generic``.
        """
        self.operations = operations
        self.dialect = dialect
        self.autocommit_depth = 0
        self.hits: list[tuple[int, str]] = []

    def visit_With(self, node: ast.With) -> None:
        """Track batch-operation aliases and autocommit blocks.

        Args:
            node: With statement.
        """
        entered = [self._enter(item) for item in node.items]
        autocommit = any(entered)
        self.autocommit_depth += int(autocommit)
        for item in node.items:
            self.visit(item.context_expr)
        for statement in node.body:
            self.visit(statement)
        self.autocommit_depth -= int(autocommit)

    def _enter(self, item: ast.withitem) -> bool:
        """Register a batch-operation alias and report an autocommit context.

        Args:
            item: One context manager of a with statement.

        Returns:
            True when the item opens an ``autocommit_block``.
        """
        expression = item.context_expr
        if not isinstance(expression, ast.Call) or not isinstance(
            expression.func, ast.Attribute
        ):
            return False
        if expression.func.attr == "batch_alter_table" and isinstance(
            item.optional_vars, ast.Name
        ):
            self.operations.add(item.optional_vars.id)
        return expression.func.attr == "autocommit_block"

    def visit_Call(self, node: ast.Call) -> None:
        """Classify one operation call.

        Args:
            node: Call expression.
        """
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in self.operations
        ):
            message = self._classify(func.attr, node)
            if message:
                self.hits.append((node.lineno, f"op.{func.attr}: {message}"))
        self.generic_visit(node)

    def _classify(self, name: str, call: ast.Call) -> str | None:
        """Return a finding message for a risky operation, if any.

        Args:
            name: Operation method name.
            call: Call node.

        Returns:
            Human-readable risk, or None for a safe operation.
        """
        message = _schema_risk(name, call)
        if message is None and name == "execute":
            message = _sql_risk(call)
        if message is None and self.dialect == "postgresql":
            message = self._postgresql(name, call)
        return message

    def _postgresql(self, name: str, call: ast.Call) -> str | None:
        """Return PostgreSQL-specific index findings.

        Args:
            name: Operation method name.
            call: Call node.

        Returns:
            Human-readable risk, or None.
        """
        if name not in _INDEX_CREATORS | _INDEX_DROPPERS:
            return None
        concurrent = _is_true(_keyword(call, "postgresql_concurrently"))
        if not concurrent:
            action = "build" if name in _INDEX_CREATORS else "drop"
            return (
                f"index {action} takes a blocking lock; "
                "pass postgresql_concurrently=True"
            )
        if self.autocommit_depth == 0:
            return (
                "CONCURRENTLY cannot run in a transaction; wrap it in "
                "'with op.get_context().autocommit_block():'"
            )
        return None


def _operation_names(tree: ast.Module) -> set[str]:
    """Return local names bound to ``alembic.op``.

    Args:
        tree: Parsed module.

    Returns:
        Names such as ``op`` or an alias.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "alembic":
            names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "op"
            )
    return names or {"op"}


def _waived(lines: list[str], line: int) -> bool:
    """Return whether the operation line or the line above carries the waiver.

    Args:
        lines: Source lines.
        line: One-based line number.

    Returns:
        True when the waiver comment is present.
    """
    candidates = lines[max(line - _WAIVER_WINDOW_LINES, 0) : line]
    return any(_WAIVER in candidate for candidate in candidates)


def check_revision(
    text: str,
    path: str,
    *,
    dialect: str = "postgresql",
    include_downgrade: bool = False,
) -> list[str]:
    """Report risky operations in one Alembic revision.

    Args:
        text: Revision source.
        path: Display path.
        dialect: ``postgresql`` enables index-concurrency checks.
        include_downgrade: Also scan the ``downgrade`` function.

    Returns:
        Findings formatted as ``path:line: message``.

    Raises:
        SyntaxError: The source cannot be parsed.
    """
    tree = ast.parse(text, filename=path)
    targets = {"upgrade", "downgrade"} if include_downgrade else {"upgrade"}
    lines = text.splitlines()
    findings: list[tuple[int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            scanner = _RevisionScanner(
                operations=_operation_names(tree), dialect=dialect
            )
            for statement in node.body:
                scanner.visit(statement)
            findings.extend(
                (line, f"{path}:{line}: {node.name}: {message}")
                for line, message in scanner.hits
                if not _waived(lines, line)
            )
    return [message for _, message in sorted(findings)]


def _revision_files(targets: Sequence[Path]) -> tuple[list[Path], list[str]]:
    """Expand targets into revision files.

    Args:
        targets: Files or directories (for example ``migrations/versions``).

    Returns:
        Sorted Python files and findings for missing targets.
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
            and "__pycache__" not in path.parts
            and not path.is_symlink()
        )
    return sorted(files), problems


_SELF_TEST_HEADER = (
    "import sqlalchemy as sa\nfrom alembic import op\n\n\ndef upgrade():\n"
)


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    MISSED_RISKY_OPERATION = "missed risky operation: {body!r} {found}"
    FALSE_POSITIVE = "false positive: {body!r}"
    DOWNGRADE_SCANNED = "downgrade must be skipped by default"
    DOWNGRADE_SKIPPED = "downgrade must be scanned when requested"
    GENERIC_DIALECT_RESTRICTED = "generic dialect must not require CONCURRENTLY"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        body: str | None = None,
        found: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            body: Observed body for the failing case.
            found: Observed found for the failing case.
        """
        super().__init__(issue.value.format(body=body, found=found))


def self_test() -> None:
    """Exercise risky, safe, waived, batch, and autocommit cases.

    Raises:
        AssertionError: A regression was detected.
    """
    _self_test_risky()
    _self_test_safe()
    _self_test_options()


def _self_test_risky() -> None:
    """Require one finding for each risky operation form.

    Raises:
        SelfTestError: A risky operation was missed.
    """
    risky = {
        "    op.drop_column('orders', 'note')\n": "destructive",
        "    op.drop_table('orders')\n": "destructive",
        "    op.alter_column('orders', 'total', type_=sa.Numeric())\n": "type change",
        "    op.alter_column('orders', 'state', nullable=False)\n": "NOT NULL",
        "    op.alter_column('orders', 'a', new_column_name='b')\n": "rename",
        "    op.add_column('orders', sa.Column('x', sa.Integer(), nullable=False))\n": (
            "server_default"
        ),
        "    op.create_index('ix_a', 'orders', ['a'])\n": "postgresql_concurrently",
        "    op.create_index('ix_a', 'orders', ['a'], postgresql_concurrently=True)\n": (
            "autocommit_block"
        ),
        "    op.execute('DROP TABLE legacy_orders')\n": "DROP TABLE",
        (
            "    with op.batch_alter_table('orders') as batch:\n"
            "        batch.drop_column('note')\n"
        ): "destructive",
    }
    for body, fragment in risky.items():
        found = check_revision(_SELF_TEST_HEADER + body, "versions/a.py")
        if len(found) != 1 or fragment not in found[0]:
            raise SelfTestError(
                SelfTestIssue.MISSED_RISKY_OPERATION, body=body, found=found
            )


def _self_test_safe() -> None:
    """Require no findings for additive, waived, and autocommit operations.

    Raises:
        SelfTestError: A safe operation was reported.
    """
    safe = (
        "    op.add_column('orders', sa.Column('note', sa.Text(), nullable=True))\n",
        (
            "    op.add_column('orders', sa.Column('n', sa.Integer(), nullable=False,"
            " server_default='0'))\n"
        ),
        (
            "    with op.get_context().autocommit_block():\n"
            "        op.create_index('ix_a', 'orders', ['a'], postgresql_concurrently=True)\n"
        ),
        "    op.drop_column('orders', 'note')  # migration-safety: reviewed\n",
        (
            "    # migration-safety: reviewed (column unused since release 41)\n"
            "    op.drop_column('orders', 'note')\n"
        ),
    )
    for body in safe:
        if check_revision(_SELF_TEST_HEADER + body, "versions/a.py"):
            raise SelfTestError(SelfTestIssue.FALSE_POSITIVE, body=body)


def _self_test_options() -> None:
    """Require downgrade and dialect options to change the scanned scope.

    Raises:
        SelfTestError: An option did not change the result.
    """
    header = _SELF_TEST_HEADER
    downgrade = header + "    pass\n\n\ndef downgrade():\n    op.drop_table('t')\n"
    if check_revision(downgrade, "versions/a.py"):
        raise SelfTestError(SelfTestIssue.DOWNGRADE_SCANNED)
    if not check_revision(downgrade, "versions/a.py", include_downgrade=True):
        raise SelfTestError(SelfTestIssue.DOWNGRADE_SKIPPED)
    generic = header + "    op.create_index('ix_a', 'orders', ['a'])\n"
    if check_revision(generic, "versions/a.py", dialect="generic"):
        raise SelfTestError(SelfTestIssue.GENERIC_DIALECT_RESTRICTED)


def main(argv: list[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 when clean, 1 when findings were reported.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="revision files or dirs")
    parser.add_argument("--dialect", choices=_DIALECTS, default="postgresql")
    parser.add_argument("--include-downgrade", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_migration_safety self-test passed.")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    files, findings = _revision_files(args.paths)
    for path in files:
        display = path.as_posix()
        try:
            findings.extend(
                check_revision(
                    path.read_text(encoding="utf-8"),
                    display,
                    dialect=args.dialect,
                    include_downgrade=args.include_downgrade,
                )
            )
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{display}:1: source cannot be read or parsed")
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
