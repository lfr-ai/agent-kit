# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Report missing community files, README emojis and unsafe ``.env.example`` lines.

Checks:

- Community health files: README, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT,
  SECURITY, SUPPORT, GOVERNANCE, CODEOWNERS, a pull request template and at
  least one issue form, looked up in the root, ``.github/`` and ``docs/``.
  ``--skip NAME`` drops a requirement the project has decided not to meet.
- README: any emoji or pictograph code point is reported with its line.
- Environment examples (``.env.example`` in the root by default, or every
  ``--env-file``): each ``NAME=value`` line needs a comment line directly
  above it, a valid unique name, and a placeholder value. Accepted values are
  empty, ``<angle-bracketed>``, values containing a placeholder marker such as
  ``change-me`` or ``example``, short numbers, booleans and common mode words,
  and URLs whose host is local or reserved (``localhost``, ``example.com``,
  ``.test``) with no real-looking password. ``--allow-value`` adds exact values.

Output is one ``path:line: message`` per finding (``path: message`` for missing
files), sorted. Exit status: 0 when clean, 1 when findings exist, 2 for usage
or read errors.

Limitations: placeholder detection is a conservative allow-list; it reports
harmless values it does not recognize and cannot prove that an accepted value
is not sensitive. Remote settings (rulesets, private vulnerability reporting)
are not visible in files and are not checked.

Example:
    python check_repository_files.py --root . --skip GOVERNANCE
    python check_repository_files.py --self-test
"""

import argparse
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

_USAGE_ERROR = 2
_HEALTH_DIRS = ("", ".github/", "docs/")
_ISSUE_CONFIG_NAMES = frozenset({"config.yml", "config.yaml"})
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE0F, 0xFE0F),
)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PLACEHOLDER_MARKERS = (
    "change-me",
    "replace-me",
    "placeholder",
    "example",
    "your-",
    "your_",
    "dummy",
    "xxx",
)
_SAFE_WORDS = frozenset(
    {
        "true",
        "false",
        "yes",
        "no",
        "on",
        "off",
        "none",
        "debug",
        "info",
        "warning",
        "error",
        "critical",
        "local",
        "dev",
        "development",
        "test",
        "staging",
        "production",
        "json",
        "text",
        "console",
        "utc",
    }
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
_RESERVED_HOST_SUFFIXES = (
    "example.com",
    "example.org",
    "example.net",
    ".example",
    ".test",
    ".invalid",
    ".localhost",
)
_MAX_NUMBER_LENGTH = 10


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One reported problem.

    Attributes:
        path: POSIX path relative to the checked root.
        line: One-based line number, or 0 for a whole-file finding.
        message: Actionable description.
    """

    path: str
    line: int
    message: str

    def render(self) -> str:
        """Return the finding as ``path:line: message`` or ``path: message``."""
        location = f"{self.path}:{self.line}" if self.line else self.path
        return f"{location}: {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class Requirement:
    """A community file and the paths that satisfy it.

    Attributes:
        name: Identifier used by ``--skip``.
        patterns: Glob patterns relative to the root; any match satisfies it.
        expected: Path reported when nothing matches.
    """

    name: str
    patterns: tuple[str, ...]
    expected: str


def _health(*names: str) -> tuple[str, ...]:
    """Return the root, ``.github/`` and ``docs/`` locations for file names."""
    return tuple(f"{folder}{name}" for name in names for folder in _HEALTH_DIRS)


REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(name="README", patterns=_health("README.md"), expected="README.md"),
    Requirement(
        name="LICENSE",
        patterns=("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"),
        expected="LICENSE",
    ),
    Requirement(
        name="CONTRIBUTING",
        patterns=_health("CONTRIBUTING.md"),
        expected="CONTRIBUTING.md",
    ),
    Requirement(
        name="CODE_OF_CONDUCT",
        patterns=_health("CODE_OF_CONDUCT.md"),
        expected="CODE_OF_CONDUCT.md",
    ),
    Requirement(
        name="SECURITY", patterns=_health("SECURITY.md"), expected="SECURITY.md"
    ),
    Requirement(name="SUPPORT", patterns=_health("SUPPORT.md"), expected="SUPPORT.md"),
    Requirement(
        name="GOVERNANCE", patterns=_health("GOVERNANCE.md"), expected="GOVERNANCE.md"
    ),
    Requirement(
        name="CODEOWNERS", patterns=_health("CODEOWNERS"), expected=".github/CODEOWNERS"
    ),
    Requirement(
        name="PULL_REQUEST_TEMPLATE",
        patterns=(
            *_health("pull_request_template.md", "PULL_REQUEST_TEMPLATE.md"),
            ".github/PULL_REQUEST_TEMPLATE/*.md",
        ),
        expected=".github/pull_request_template.md",
    ),
    Requirement(
        name="ISSUE_FORMS",
        patterns=(".github/ISSUE_TEMPLATE/*.yml", ".github/ISSUE_TEMPLATE/*.yaml"),
        expected=".github/ISSUE_TEMPLATE/",
    ),
)


def missing_files(root: Path, *, skipped: frozenset[str]) -> list[Finding]:
    """Report each community file requirement that no file satisfies.

    Args:
        root: Repository root.
        skipped: Requirement names the project decided not to meet.

    Returns:
        One finding per unmet requirement.
    """
    return [
        Finding(
            path=requirement.expected,
            line=0,
            message=f"missing community file ({requirement.name})",
        )
        for requirement in REQUIREMENTS
        if requirement.name not in skipped and not _satisfied(root, requirement)
    ]


def _satisfied(root: Path, requirement: Requirement) -> bool:
    """Return whether any non-configuration file matches the requirement."""
    return any(
        path.is_file() and path.name not in _ISSUE_CONFIG_NAMES
        for pattern in requirement.patterns
        for path in root.glob(pattern)
    )


def is_emoji(character: str) -> bool:
    """Return whether a character is an emoji, pictograph or emoji selector.

    Args:
        character: A single character.

    Returns:
        True when its code point is in an emoji or symbol-pictograph block.
    """
    point = ord(character)
    return any(low <= point <= high for low, high in _EMOJI_RANGES)


def readme_emojis(path: str, text: str) -> list[Finding]:
    """Report README lines that contain emojis.

    Args:
        path: Path used in findings.
        text: README content.

    Returns:
        One finding per line with at least one emoji.
    """
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        found = [character for character in line if is_emoji(character)]
        if found:
            points = ", ".join(f"U+{ord(item):04X}" for item in found)
            findings.append(
                Finding(
                    path=path,
                    line=number,
                    message=f"emoji in README ({points}); use plain words",
                )
            )
    return findings


def is_placeholder(value: str, *, allowed: frozenset[str] = frozenset()) -> bool:
    """Return whether an environment value is an obvious placeholder.

    Args:
        value: Raw value after ``=``, with surrounding quotes allowed.
        allowed: Extra exact values the project accepts.

    Returns:
        True for empty, marked, numeric, mode-word and local-URL values.
    """
    text = value.strip().strip("\"'")
    lowered = text.lower()
    if not text or text in allowed or lowered in _SAFE_WORDS:
        return True
    if "://" in text:
        return _is_local_url(text)
    if text.startswith("<") and text.endswith(">"):
        return True
    return _is_short_number(text) or any(
        marker in lowered for marker in _PLACEHOLDER_MARKERS
    )


def _is_short_number(text: str) -> bool:
    """Return whether text is a plain number short enough to be a setting."""
    try:
        float(text)
    except ValueError:
        return False
    return len(text) <= _MAX_NUMBER_LENGTH


def _is_local_url(text: str) -> bool:
    """Return whether a URL targets a local or reserved host without a real password."""
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        password = parts.password
    except ValueError:
        return False
    local = host in _LOCAL_HOSTS or host.endswith(_RESERVED_HOST_SUFFIXES)
    return local and (password is None or is_placeholder(password))


def env_findings(
    path: str, text: str, *, allowed: frozenset[str] = frozenset()
) -> list[Finding]:
    """Check an environment example for documentation and placeholder values.

    Args:
        path: Path used in findings.
        text: File content.
        allowed: Extra exact values the project accepts.

    Returns:
        Findings for invalid, duplicate, undocumented or real-looking entries.
    """
    findings: list[Finding] = []
    seen: set[str] = set()
    previous = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line and not line.startswith("#"):
            findings.extend(
                _entry_findings(line, previous, seen=seen, allowed=allowed).located(
                    path, number
                )
            )
        previous = line
    return findings


@dataclass(frozen=True, kw_only=True, slots=True)
class _Messages:
    """Messages for one environment entry, located later."""

    items: tuple[str, ...]

    def located(self, path: str, line: int) -> Iterator[Finding]:
        """Yield the messages as findings at one location."""
        for message in self.items:
            yield Finding(path=path, line=line, message=message)


def _entry_findings(
    line: str, previous: str, *, seen: set[str], allowed: frozenset[str]
) -> _Messages:
    """Return the problems of one ``NAME=value`` entry and record its name."""
    name, separator, value = line.removeprefix("export ").partition("=")
    name = name.strip()
    if not separator or not _NAME.fullmatch(name):
        return _Messages(items=("not a NAME=value entry or comment",))
    messages: list[str] = []
    if name in seen:
        messages.append(f"{name} is defined more than once")
    seen.add(name)
    if not previous.startswith("#") or previous == "#":
        messages.append(f"{name} has no comment directly above it")
    if not is_placeholder(value, allowed=allowed):
        messages.append(
            f"{name} has a value that is not an obvious placeholder; "
            "use an empty value, <placeholder>, change-me or a local URL"
        )
    return _Messages(items=tuple(messages))


def check(
    root: Path,
    *,
    env_files: Iterable[Path],
    skipped: frozenset[str] = frozenset(),
    allowed: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Run every check under a root.

    Args:
        root: Repository root.
        env_files: Environment example files to check.
        skipped: Community file requirements to ignore.
        allowed: Extra exact environment values to accept.

    Returns:
        Findings sorted by path, line and message.

    Raises:
        OSError: If a file cannot be read.
        UnicodeDecodeError: If a file is not UTF-8.
    """
    findings = missing_files(root, skipped=skipped)
    readme = root / "README.md"
    if readme.is_file():
        findings.extend(readme_emojis("README.md", readme.read_text(encoding="utf-8")))
    for env_file in env_files:
        label = _label(env_file, root)
        text = env_file.read_text(encoding="utf-8")
        findings.extend(env_findings(label, text, allowed=allowed))
    return sorted(findings, key=lambda item: (item.path, item.line, item.message))


def _label(path: Path, root: Path) -> str:
    """Return a POSIX path relative to the root when possible."""
    resolved = path.resolve()
    if resolved.is_relative_to(root.resolve()):
        return resolved.relative_to(root.resolve()).as_posix()
    return path.as_posix()


_SELF_TEST_FILES = (
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".github/SECURITY.md",
    "docs/SUPPORT.md",
    "GOVERNANCE.md",
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/config.yml",
)
_SELF_TEST_README = "# Demo\nLaunch \U0001f680 now\nPlain line\n"
_SELF_TEST_ENV = (
    "# Port the server binds to.\n"
    "APP_PORT=8000\n"
    "APP_TOKEN=\n"
    "# Database URL for the dev container.\n"
    # pragma: allowlist nextline secret: public local development fixture
    "APP_DATABASE_URL=postgresql://app:change-me@localhost:5432/app\n"
    "# Signing key.\n"
    "APP_SECRET=hunter2\n"
)


def self_test() -> list[str]:
    """Run the checks on a synthetic temporary repository.

    Returns:
        Unmet expectations; empty when every rule behaves as documented.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for relative, text in (
            *((name, "content\n") for name in _SELF_TEST_FILES),
            ("README.md", _SELF_TEST_README),
            (".env.example", _SELF_TEST_ENV),
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        rendered = [
            finding.render()
            for finding in check(root, env_files=[root / ".env.example"])
        ]
        empty = Path(directory, "empty")
        empty.mkdir()
        missing = missing_files(empty, skipped=frozenset({"GOVERNANCE"}))
    expected = [
        ".env.example:3: APP_TOKEN has no comment directly above it",
        (
            ".env.example:7: APP_SECRET has a value that is not an obvious "
            "placeholder; use an empty value, <placeholder>, change-me or a local URL"
        ),
        ".github/ISSUE_TEMPLATE/: missing community file (ISSUE_FORMS)",
        "README.md:2: emoji in README (U+1F680); use plain words",
    ]
    failures = [
        f"expected finding: {item}" for item in expected if item not in rendered
    ]
    failures.extend(
        f"unexpected finding: {item}" for item in rendered if item not in expected
    )
    if len(missing) != len(REQUIREMENTS) - 1:
        failures.append(
            f"empty repository: expected 9 missing files, got {len(missing)}"
        )
    return failures


def _run_self_test() -> int:
    """Print the self-test outcome and return its exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    sys.stdout.write(
        f"{'check_repository_files self-test ' + ('failed.' if failures else 'passed.')}\n"
    )
    return 1 if failures else 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path())
    parser.add_argument(
        "--env-file",
        action="append",
        type=Path,
        default=[],
        help="environment example to check; default: ROOT/.env.example if present",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        choices=[requirement.name for requirement in REQUIREMENTS],
        help="community file requirement to ignore; repeatable",
    )
    parser.add_argument(
        "--allow-value",
        action="append",
        default=[],
        help="exact environment value to accept; repeatable",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="check built-in synthetic cases in a temporary directory and exit",
    )
    return parser


def _env_files(root: Path, explicit: list[Path]) -> list[Path] | None:
    """Return files to check, or None when the root or an explicit file is missing."""
    if not root.is_dir():
        sys.stderr.write(f"{root.as_posix()}: root is not a directory\n")
        return None
    if explicit:
        missing = [path for path in explicit if not path.is_file()]
        for path in missing:
            sys.stderr.write(f"{path.as_posix()}: environment file not found\n")
        return None if missing else explicit
    default = root / ".env.example"
    return [default] if default.is_file() else []


def main(argv: list[str] | None = None) -> int:
    """Check a repository and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on usage or read errors.
    """
    args = _parser().parse_args(argv)
    if args.self_test:
        return _run_self_test()
    root: Path = args.root
    env_files = _env_files(root, args.env_file)
    if env_files is None:
        return _USAGE_ERROR
    try:
        findings = check(
            root,
            env_files=env_files,
            skipped=frozenset(args.skip),
            allowed=frozenset(args.allow_value),
        )
    except (OSError, UnicodeDecodeError) as error:
        sys.stderr.write(f"cannot read repository files: {error}\n")
        return _USAGE_ERROR
    for finding in findings:
        sys.stdout.write(f"{finding.render()}\n")
    if not findings:
        sys.stdout.write("Repository files are complete and safe.\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
