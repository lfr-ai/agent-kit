"""Check explicit consumer context entries and their local links without execution."""

import argparse
from enum import StrEnum
from pathlib import Path, PureWindowsPath
import re
import sys
from tempfile import TemporaryDirectory
from urllib.parse import unquote

_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_DEFAULT_ENTRIES = ("AGENTS.md", "PROJECT.md", "llms.txt")
_SELF_TEST_INVALID_LINKS = 2


def _is_unsafe_relative(value: str) -> bool:
    """Return whether ``value`` is absolute, drive-qualified or parent-relative."""
    relative = Path(value)
    return (
        relative.is_absolute()
        or bool(PureWindowsPath(value).drive)
        or ".." in relative.parts
    )


def _entry_failure(root: Path, base: Path, entry: str) -> str | None:
    """Return why ``entry`` cannot be read as a contained context file."""
    if _is_unsafe_relative(entry):
        return f"unsafe entry path: {entry}"
    path = root / entry
    if not path.resolve().is_relative_to(base):
        return f"escaping entry: {entry}"
    if not path.is_file():
        return f"missing entry: {entry}"
    return None


def _link_failures(entry: str, path: Path, base: Path, text: str) -> list[str]:
    """Return missing or unsafe local link failures found in ``text``."""
    failures: list[str] = []
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


def check(root: Path, *, entries: tuple[str, ...] = _DEFAULT_ENTRIES) -> list[str]:
    """Validate nonempty contained entries and links, not their factual accuracy."""
    failures: list[str] = []
    base = root.resolve()
    for entry in entries:
        failure = _entry_failure(root, base, entry)
        if failure is not None:
            failures.append(failure)
            continue
        path = root / entry
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            failures.append(f"empty entry: {entry}")
        failures.extend(_link_failures(entry, path, base, text))
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


def _expect(issue: SelfTestIssue, *, holds: bool) -> None:
    """Raise ``SelfTestError`` for ``issue`` unless the expectation ``holds``."""
    if not holds:
        raise SelfTestError(issue)


def self_test() -> None:
    """Exercise missing, empty, valid and escaping links with synthetic files."""
    with TemporaryDirectory(prefix="agent-kit-context-") as directory:
        root = Path(directory)
        _expect(
            SelfTestIssue.MISSING_CONTEXT_ACCEPTED,
            holds=len(check(root)) == len(_DEFAULT_ENTRIES),
        )
        for entry in _DEFAULT_ENTRIES:
            (root / entry).write_text("# Synthetic context\n", encoding="utf-8")
        _expect(SelfTestIssue.VALID_CONTEXT_REJECTED, holds=not check(root))
        (root / "PROJECT.md").write_text("", encoding="utf-8")
        _expect(SelfTestIssue.EMPTY_CONTEXT_ACCEPTED, holds=bool(check(root)))
        (root / "PROJECT.md").write_text(
            "[outside](../outside.md)\n[missing](absent.md)", encoding="utf-8"
        )
        _expect(
            SelfTestIssue.INVALID_LINK_ACCEPTED,
            holds=len(check(root)) == _SELF_TEST_INVALID_LINKS,
        )
        _expect(
            SelfTestIssue.ESCAPING_ENTRY_ACCEPTED,
            holds=bool(check(root, entries=("../outside.md",))),
        )


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
