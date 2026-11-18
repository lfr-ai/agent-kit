# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Summarize a jscpd JSON report into reviewable clone findings.

Reads the file written by the jscpd ``json`` reporter (by default
``report/jscpd-report.json``), filters clones by size and path globs, and prints
one ``path:line: message`` finding per remaining clone pair, largest first. It
exits 1 when any clone remains or the overall duplication percentage exceeds
``--max-percentage``, and 2 when the report is missing or malformed. The tool
never runs jscpd itself.
"""

import argparse
from dataclasses import dataclass
from enum import StrEnum, unique
import fnmatch
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

_EXIT_USAGE = 2
_UNKNOWN_FORMAT = "unknown"


@dataclass(frozen=True, kw_only=True, slots=True)
class Fragment:
    """One side of a clone pair.

    Attributes:
        name: File path from the report, with forward slashes.
        start: First duplicated line, one-based.
        end: Last duplicated line, one-based.
    """

    name: str
    start: int
    end: int


@dataclass(frozen=True, kw_only=True, slots=True)
class Clone:
    """A duplicated fragment pair.

    Attributes:
        fmt: Source format reported by jscpd, such as ``python``.
        lines: Duplicated line count.
        tokens: Duplicated token count, 0 when absent.
        first: The ``firstFile`` fragment; findings are reported at its location.
        second: The ``secondFile`` fragment, cited as the clone source.
    """

    fmt: str
    lines: int
    tokens: int
    first: Fragment
    second: Fragment

    def render(self) -> str:
        """Return the deterministic finding line."""
        return (
            f"{self.first.name}:{self.first.start}: {self.lines}-line {self.fmt} clone "
            f"of {self.second.name}:{self.second.start}-{self.second.end} "
            f"({self.tokens} tokens)"
        )


@unique
class DuplicationInputIssue(StrEnum):
    """Supported duplication input validation failures and their stable messages."""

    NONNEGATIVE_INTEGER = "{where} must be a non-negative integer"
    OBJECT_REQUIRED = "{where} must be an object"
    FRAGMENT_NAME = "{where}.name must be a non-empty string"
    REPORT_SHAPE = "report must be an object with a 'duplicates' list"


class DuplicationInputError(ValueError):
    """An input violates the duplication input contract."""

    def __init__(
        self, issue: DuplicationInputIssue, *, where: str | None = None
    ) -> None:
        """Describe a supported input failure.

        Args:
            issue (DuplicationInputIssue): The violated input invariant.
            where (str | None): JSON path of the offending value, such as
                ``duplicates[0].lines``, substituted into the message.
        """
        super().__init__(issue.value.format(where=where))


class DuplicationInputTypeError(TypeError):
    """An input has the wrong Python type for the duplication input contract."""

    def __init__(
        self, issue: DuplicationInputIssue, *, where: str | None = None
    ) -> None:
        """Describe a wrong input type.

        Args:
            issue (DuplicationInputIssue): The violated input invariant.
            where (str | None): JSON path of the offending value, such as
                ``duplicates[0].lines``, substituted into the message.
        """
        super().__init__(issue.value.format(where=where))


def _int(value: object, where: str) -> int:
    """Return ``value`` if it is a non-negative integer; raise an error at ``where``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise DuplicationInputTypeError(
            DuplicationInputIssue.NONNEGATIVE_INTEGER, where=where
        )
    if value < 0:
        raise DuplicationInputError(
            DuplicationInputIssue.NONNEGATIVE_INTEGER, where=where
        )
    return value


def _required_int(item: dict[str, object], key: str, where: str) -> int:
    """Return the integer field ``key``; a missing field is a value error at ``where``."""
    if key not in item:
        raise DuplicationInputError(
            DuplicationInputIssue.NONNEGATIVE_INTEGER, where=where
        )
    return _int(item[key], where)


def _line(item: dict[str, object], key: str, where: str) -> int:
    """Read a direct line number or its existing location fallback."""
    location = item.get(f"{key}Loc")
    if item.get(key) is None and isinstance(location, dict):
        return _required_int(location, "line", where)
    return _required_int(item, key, where)


def _fragment(value: object, where: str) -> Fragment:
    """Parse ``firstFile`` or ``secondFile`` including the ``startLoc`` fallback.

    A wrong fragment or name type is a type error at ``where``; a missing or empty
    name is a value error.
    """
    if not isinstance(value, dict):
        raise DuplicationInputTypeError(
            DuplicationInputIssue.OBJECT_REQUIRED, where=where
        )
    name = value.get("name")
    if "name" not in value:
        raise DuplicationInputError(DuplicationInputIssue.FRAGMENT_NAME, where=where)
    if not isinstance(name, str):
        raise DuplicationInputTypeError(
            DuplicationInputIssue.FRAGMENT_NAME, where=where
        )
    if not name:
        raise DuplicationInputError(DuplicationInputIssue.FRAGMENT_NAME, where=where)
    return Fragment(
        name=name.replace("\\", "/"),
        start=_line(value, "start", f"{where}.start"),
        end=_line(value, "end", f"{where}.end"),
    )


def _required_fragment(item: dict[str, object], key: str, where: str) -> Fragment:
    """Return the fragment field ``key``; a missing field is a value error at ``where``."""
    if key not in item:
        raise DuplicationInputError(DuplicationInputIssue.OBJECT_REQUIRED, where=where)
    return _fragment(item[key], where)


def parse_report(payload: object) -> tuple[list[Clone], float | None]:
    """Return the clone pairs and overall percentage of a decoded jscpd report.

    The percentage is ``None`` when the report omits it. Raises
    ``DuplicationInputTypeError`` when the document or a present field has the wrong
    type and ``DuplicationInputError`` when it does not match the report shape.
    """
    if not isinstance(payload, dict):
        raise DuplicationInputTypeError(DuplicationInputIssue.REPORT_SHAPE)
    if "duplicates" not in payload:
        raise DuplicationInputError(DuplicationInputIssue.REPORT_SHAPE)
    if not isinstance(payload["duplicates"], list):
        raise DuplicationInputTypeError(DuplicationInputIssue.REPORT_SHAPE)
    clones = [
        _clone(item, f"duplicates[{index}]")
        for index, item in enumerate(payload["duplicates"])
    ]
    return clones, _percentage(payload)


def _clone(item: object, where: str) -> Clone:
    """Parse one ``duplicates`` entry; a non-object entry is a type error at ``where``."""
    if not isinstance(item, dict):
        raise DuplicationInputTypeError(
            DuplicationInputIssue.OBJECT_REQUIRED, where=where
        )
    fmt = item.get("format", _UNKNOWN_FORMAT)
    return Clone(
        fmt=fmt if isinstance(fmt, str) else _UNKNOWN_FORMAT,
        lines=_required_int(item, "lines", f"{where}.lines"),
        tokens=_int(item.get("tokens", 0), f"{where}.tokens"),
        first=_required_fragment(item, "firstFile", f"{where}.firstFile"),
        second=_required_fragment(item, "secondFile", f"{where}.secondFile"),
    )


def _percentage(payload: dict[object, object]) -> float | None:
    """Return the reported overall duplication percentage, if numeric."""
    statistics = payload.get("statistics")
    if not isinstance(statistics, dict) or not isinstance(
        statistics.get("total"), dict
    ):
        return None
    value = statistics["total"].get("percentage")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def select(
    clones: list[Clone], *, min_lines: int, ignore: tuple[str, ...]
) -> list[Clone]:
    """Drop small clones and pairs whose both sides match an ignore glob.

    Args:
        clones (list[Clone]): Parsed clone pairs.
        min_lines (int): Smallest clone size to keep.
        ignore (tuple[str, ...]): Glob patterns matched against report paths.

    Returns:
        Remaining clones, largest first, then by path and line.
    """

    def ignored(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pattern) for pattern in ignore)

    kept = [
        clone
        for clone in clones
        if clone.lines >= min_lines
        and not (ignored(clone.first.name) and ignored(clone.second.name))
    ]
    return sorted(
        kept,
        key=lambda clone: (
            -clone.lines,
            clone.first.name,
            clone.first.start,
            clone.second.name,
            clone.second.start,
        ),
    )


def to_markdown(clones: list[Clone]) -> str:
    """Render clones as a Markdown evidence table."""
    lines = [
        "| First | Second | Lines | Tokens | Format | Decision |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| `{clone.first.name}:{clone.first.start}-{clone.first.end}` "
        f"| `{clone.second.name}:{clone.second.start}-{clone.second.end}` "
        f"| {clone.lines} | {clone.tokens} | {clone.fmt} | |"
        for clone in clones
    )
    return "\n".join(lines) + "\n"


_SAMPLE_PERCENTAGE = 4.5
_SELF_TEST_BROKEN_REPORTS = ({}, {"duplicates": [{"lines": 3}]})
_SAMPLE = {
    "duplicates": [
        {
            "format": "python",
            "lines": 12,
            "tokens": 90,
            "firstFile": {"name": "src/orders/export.py", "start": 10, "end": 21},
            "secondFile": {"name": "src/invoices/export.py", "start": 30, "end": 41},
        },
        {
            "format": "python",
            "lines": 6,
            "firstFile": {
                "name": "tests/a_test.py",
                "startLoc": {"line": 1},
                "endLoc": {"line": 6},
            },
            "secondFile": {"name": "tests/b_test.py", "start": 1, "end": 6},
        },
    ],
    "statistics": {"total": {"percentage": _SAMPLE_PERCENTAGE}},
}


def _sample_failures() -> list[str]:
    """Return regressions in parsing, filtering and rendering the bundled sample."""
    clones, percentage = parse_report(_SAMPLE)
    if percentage != _SAMPLE_PERCENTAGE or len(clones) != len(_SAMPLE["duplicates"]):
        return [f"sample parsed as {clones!r} at {percentage!r}%"]
    kept = select(clones, min_lines=0, ignore=("tests/*",))
    if [clone.first.name for clone in kept] != ["src/orders/export.py"]:
        return [f"ignore globs kept {kept!r}"]
    failures = []
    if not kept[0].render().startswith("src/orders/export.py:10: 12-line python"):
        failures.append(f"unexpected finding line: {kept[0].render()}")
    if "`src/invoices/export.py:30-41`" not in to_markdown(kept):
        failures.append("markdown table is missing the clone")
    return failures


def self_test() -> list[str]:
    """Exercise parsing, filtering, rendering and malformed input; return failures."""
    failures = _sample_failures()
    for broken in _SELF_TEST_BROKEN_REPORTS:
        try:
            parse_report(broken)
        except ValueError:
            continue
        failures.append(f"malformed report accepted: {broken}")
    with TemporaryDirectory(prefix="jscpd-summary-") as raw:
        report = Path(raw) / "jscpd-report.json"
        report.write_text(json.dumps(_SAMPLE), encoding="utf-8")
        if main([str(report), "--min-lines", "20", "--max-percentage", "5"]) != 0:
            failures.append("small clones under the gate must pass")
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", nargs="?", type=Path)
    parser.add_argument("--min-lines", type=int, default=0)
    parser.add_argument("--max-percentage", type=float, default=None)
    parser.add_argument("--ignore", action="append", default=[])
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def _print_clones(kept: list[Clone], *, markdown: bool) -> None:
    """Write selected clones as a Markdown table or finding lines."""
    if markdown:
        sys.stdout.write(to_markdown(kept))
        return
    for clone in kept:
        sys.stdout.write(f"{clone.render()}\n")


def _report_over(report: Path, percentage: float | None, maximum: float | None) -> bool:
    """Print and return whether the duplication percentage exceeds the gate."""
    if maximum is None or percentage is None or not percentage > maximum:
        return False
    sys.stdout.write(
        f"{report.as_posix()}:1: duplication {percentage:.2f}% exceeds {maximum:.2f}%\n"
    )
    return True


def main(argv: list[str] | None = None) -> int:
    """Summarize the report and apply the gates.

    Returns 0 when no clone remains and the percentage gate holds, 1 on findings, 2 on a
    missing or malformed report.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        sys.stderr.writelines(f"{failure}\n" for failure in failures)
        verdict = "failed" if failures else "passed"
        sys.stdout.write(f"summarize_jscpd_report self-test {verdict}.\n")
        return int(bool(failures))
    if args.report is None:
        parser.print_usage(sys.stderr)
        return _EXIT_USAGE
    try:
        clones, percentage = parse_report(
            json.loads(args.report.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeError, ValueError, DuplicationInputTypeError) as error:
        sys.stderr.write(f"cannot summarize report: {error}\n")
        return _EXIT_USAGE
    kept = select(clones, min_lines=args.min_lines, ignore=tuple(args.ignore))
    _print_clones(kept, markdown=args.markdown)
    over = _report_over(args.report, percentage, args.max_percentage)
    sys.stderr.write(
        f"{len(kept)} of {len(clones)} clone(s) reported; "
        f"total duplication {'unknown' if percentage is None else f'{percentage:.2f}%'}.\n"
    )
    return int(bool(kept) or over)


if __name__ == "__main__":
    raise SystemExit(main())
