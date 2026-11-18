# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check explicit consumer context entries and their local links without execution."""

import argparse
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
    """Validate nonempty contained entries and links, not their factual accuracy.

    Args:
        root (Path): Repository root that contains the context entries.
        entries (tuple[str, ...]): Root-relative entry files to require and scan for
            links.
    """
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


def self_test() -> list[str]:
    """Return regressions for missing, empty, valid and escaping synthetic context."""
    with TemporaryDirectory(prefix="agent-kit-context-") as directory:
        root = Path(directory)
        checks = [
            (len(check(root)) == len(_DEFAULT_ENTRIES), "missing context must fail")
        ]
        for entry in _DEFAULT_ENTRIES:
            (root / entry).write_text("# Synthetic context\n", encoding="utf-8")
        checks.append((not check(root), "valid context must pass"))
        (root / "PROJECT.md").write_text("", encoding="utf-8")
        checks.append((bool(check(root)), "empty context must fail"))
        (root / "PROJECT.md").write_text(
            "[outside](../outside.md)\n[missing](absent.md)", encoding="utf-8"
        )
        checks.append(
            (
                len(check(root)) == _SELF_TEST_INVALID_LINKS,
                "missing and escaping links must fail",
            )
        )
        checks.append(
            (bool(check(root, entries=("../outside.md",))), "escaping entry must fail")
        )
    return [message for holds, message in checks if not holds]


def main() -> int:
    """Check a consumer root or run isolated self-tests; never change that root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--entry", action="append", default=[])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        sys.stderr.writelines(f"{failure}\n" for failure in failures)
        verdict = "failed" if failures else "passed"
        sys.stdout.write(f"Context checker self-test {verdict}.\n")
        return int(bool(failures))
    try:
        failures = check(args.root, entries=tuple(args.entry) or _DEFAULT_ENTRIES)
    except (OSError, UnicodeError) as error:
        sys.stderr.write(f"Cannot read context: {error}\n")
        return 1
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if not failures:
        sys.stdout.write("Context entries and their local links passed.\n")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
