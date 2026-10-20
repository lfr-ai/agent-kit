"""Check explicit consumer context entries and their local links without execution."""

import argparse
import re
import sys
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from urllib.parse import unquote

_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_DEFAULT_ENTRIES = ("AGENTS.md", "PROJECT.md", "llms.txt")


def check(root: Path, *, entries: tuple[str, ...] = _DEFAULT_ENTRIES) -> list[str]:
    """Validate nonempty contained entries and links, not their factual accuracy."""
    failures: list[str] = []
    base = root.resolve()
    for entry in entries:
        relative = Path(entry)
        if (
            relative.is_absolute()
            or PureWindowsPath(entry).drive
            or ".." in relative.parts
        ):
            failures.append(f"unsafe entry path: {entry}")
            continue
        path = root / relative
        if not path.resolve().is_relative_to(base):
            failures.append(f"escaping entry: {entry}")
            continue
        if not path.is_file():
            failures.append(f"missing entry: {entry}")
            continue
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            failures.append(f"empty entry: {entry}")
        for raw in _LINK.findall(text):
            target = raw.strip().strip("<>").split(" ", 1)[0]
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            local = unquote(target.partition("#")[0])
            linked = path.parent / local
            if (
                Path(local).is_absolute()
                or PureWindowsPath(local).drive
                or not linked.resolve().is_relative_to(base)
                or not linked.exists()
            ):
                failures.append(f"{entry}: missing or unsafe link: {local}")
    return failures


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    MISSING_CONTEXT_ACCEPTED = "missing context must fail"
    VALID_CONTEXT_REJECTED = "valid context must pass"
    EMPTY_CONTEXT_ACCEPTED = "empty context must fail"
    INVALID_LINK_ACCEPTED = "missing and escaping links must fail"
    ESCAPING_ENTRY_ACCEPTED = "escaping entry must fail"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(self, issue: SelfTestIssue) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
        """
        super().__init__(issue.value)


def self_test() -> None:
    """Exercise missing, empty, valid and escaping links with synthetic files."""
    with TemporaryDirectory(prefix="agent-kit-context-") as directory:
        root = Path(directory)
        if len(check(root)) != len(_DEFAULT_ENTRIES):
            raise SelfTestError(SelfTestIssue.MISSING_CONTEXT_ACCEPTED)
        for entry in _DEFAULT_ENTRIES:
            (root / entry).write_text("# Synthetic context\n", encoding="utf-8")
        if check(root):
            raise SelfTestError(SelfTestIssue.VALID_CONTEXT_REJECTED)
        (root / "PROJECT.md").write_text("", encoding="utf-8")
        if not check(root):
            raise SelfTestError(SelfTestIssue.EMPTY_CONTEXT_ACCEPTED)
        (root / "PROJECT.md").write_text(
            "[outside](../outside.md)\n[missing](absent.md)", encoding="utf-8"
        )
        if len(check(root)) != 2:  # noqa: PLR2004 - two invalid links
            raise SelfTestError(SelfTestIssue.INVALID_LINK_ACCEPTED)
        if not check(root, entries=("../outside.md",)):
            raise SelfTestError(SelfTestIssue.ESCAPING_ENTRY_ACCEPTED)


def main() -> int:
    """Check a consumer root or run isolated self-tests; never change that root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--entry", action="append", default=[])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Context checker self-test passed.")
        return 0
    try:
        failures = check(args.root, entries=tuple(args.entry) or _DEFAULT_ENTRIES)
    except (OSError, UnicodeError) as error:
        print(f"Cannot read context: {error}", file=sys.stderr)
        return 1
    for failure in failures:
        print(failure, file=sys.stderr)
    if not failures:
        print("Context entries and their local links passed.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
