"""Flag public ``VITE_`` variables whose names suggest secrets.

Vite compiles every variable with a public prefix (``VITE_`` by default) into
JavaScript that browsers download. A public name containing ``SECRET``,
``TOKEN``, ``KEY``, or ``PASSWORD`` (also ``PASSWD``, ``PRIVATE``, and
``CREDENTIAL``) almost always means a credential was placed behind the prefix.

Inputs, below each given file or directory:

- dotenv files named ``.env`` or ``.env.*``: assignments ``NAME=value`` and
  ``export NAME=value``;
- source files (``.ts``, ``.tsx``, ``.js``, ``.jsx``, ``.mjs``, ``.cjs``,
  ``.vue``, ``.svelte``, ``.html``): any prefixed identifier, for example
  ``import.meta.env.VITE_API_TOKEN``.

Dependency and build output directories are skipped. ``--allow NAME`` accepts
a name that a provider documents as publishable (for example an OAuth public
client identifier); a line containing ``frontend-env: allow`` is exempt.

Output is ``path:line: [secret-like-public-name] NAME ...`` sorted by path
and line. Exit status: 0 clean, 1 findings, 2 usage error or unreadable input.
``--self-test`` checks the rules on synthetic text and exits.

Limitations: names only. Values are never read or printed, so a secret stored
under an innocent name is not detected; scan the built output as well.

Example:
    python check_frontend_env.py . --allow VITE_STRIPE_PUBLISHABLE_KEY
"""

import argparse
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import sys

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
DEFAULT_PREFIXES: tuple[str, ...] = ("VITE_",)
SOURCE_SUFFIXES = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".html"}
)
SUPPRESSION = "frontend-env: allow"
RULE = "secret-like-public-name"
_SKIPPED_DIRECTORIES = frozenset(
    {".git", "node_modules", "dist", "build", "coverage", "storybook-static"}
)
_SECRET_SEGMENT = re.compile(
    r"[A-Z0-9]*(?:SECRET|TOKEN|PASSWORD|PASSWD|KEY)S?|PRIVATE|CREDENTIALS?"
)


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One public variable name that looks like a secret.

    Attributes:
        path: File in POSIX form.
        line: One-based line number.
        name: The variable name as written.
    """

    path: str
    line: int
    name: str

    def render(self) -> str:
        """Return ``path:line: [rule] message``."""
        return (
            f"{self.path}:{self.line}: [{RULE}] {self.name} is compiled into "
            "the browser bundle; keep secrets server-side or --allow a "
            "documented publishable value"
        )


def is_secret_like(name: str, *, prefixes: Sequence[str]) -> bool:
    """Return whether a prefixed variable name suggests a secret.

    Args:
        name: Variable name such as ``VITE_API_TOKEN``.
        prefixes: Public prefixes; the matching prefix is removed first.

    Returns:
        True when any underscore-separated segment after the prefix is a
        secret-like word, such as ``TOKEN`` or ``APIKEY``.
    """
    upper = name.upper()
    prefix = next((item for item in prefixes if upper.startswith(item.upper())), None)
    if prefix is None:
        return False
    segments = upper[len(prefix) :].split("_")
    return any(_SECRET_SEGMENT.fullmatch(segment) for segment in segments if segment)


def is_env_file(path: Path) -> bool:
    """Return whether a file name is a dotenv file (``.env`` or ``.env.*``).

    Args:
        path: Candidate file.

    Returns:
        True for ``.env``, ``.env.local``, ``.env.example`` and similar.
    """
    return path.name == ".env" or path.name.startswith(".env.")


def _patterns(prefixes: Sequence[str]) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build the dotenv assignment and source identifier patterns."""
    alternatives = "|".join(re.escape(prefix) for prefix in prefixes)
    assignment = re.compile(rf"^\s*(?:export\s+)?((?:{alternatives})[A-Za-z0-9_]*)\s*=")
    identifier = re.compile(rf"(?<![A-Za-z0-9_$])((?:{alternatives})[A-Za-z0-9_]+)")
    return assignment, identifier


def scan_text(
    text: str, *, path: str, env_file: bool, prefixes: Sequence[str]
) -> list[Finding]:
    """Return secret-like public names in one file.

    Args:
        text: File content.
        path: Path used in findings.
        env_file: Parse dotenv assignments instead of source identifiers.
        prefixes: Public prefixes to check.

    Returns:
        Findings in line order, one per name per line.
    """
    assignment, identifier = _patterns(prefixes)
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if SUPPRESSION in line:
            continue
        if env_file:
            match = assignment.match(line)
            names = [match.group(1)] if match else []
        else:
            names = sorted({match.group(1) for match in identifier.finditer(line)})
        findings.extend(
            Finding(path=path, line=number, name=name)
            for name in names
            if is_secret_like(name, prefixes=prefixes)
        )
    return findings


def _walk(root: Path) -> Iterator[Path]:
    """Yield candidate files below a directory, pruning skipped directories."""
    for directory, dirnames, filenames in root.walk():
        dirnames[:] = sorted(set(dirnames) - _SKIPPED_DIRECTORIES)
        candidates = (directory / name for name in sorted(filenames))
        yield from (
            path
            for path in candidates
            if is_env_file(path) or path.suffix in SOURCE_SUFFIXES
        )


def iter_files(paths: Sequence[Path]) -> Iterator[Path]:
    """Yield dotenv and source files in deterministic order.

    Args:
        paths: Files or directories to scan.

    Yields:
        Candidate files outside dependency and build output directories.

    Raises:
        FileNotFoundError: If a given path does not exist.
    """
    for root in paths:
        if not root.exists():
            raise FileNotFoundError(root)
        if root.is_file():
            yield root
        else:
            yield from _walk(root)


def scan_paths(
    paths: Sequence[Path],
    *,
    prefixes: Sequence[str] = DEFAULT_PREFIXES,
    allow: Sequence[str] = (),
) -> list[Finding]:
    """Scan files and directories for secret-like public names.

    Args:
        paths: Files or directories to scan.
        prefixes: Public prefixes to check.
        allow: Exact names accepted as publishable.

    Returns:
        Findings sorted by path and line.

    Raises:
        FileNotFoundError: If a given path does not exist.
        UnicodeDecodeError: If a file is not UTF-8 text.
    """
    allowed = frozenset(allow)
    findings: list[Finding] = []
    for path in iter_files(paths):
        text = path.read_text(encoding="utf-8")
        findings.extend(
            finding
            for finding in scan_text(
                text,
                path=path.as_posix(),
                env_file=is_env_file(path),
                prefixes=prefixes,
            )
            if finding.name not in allowed
        )
    return sorted(findings, key=lambda item: (item.path, item.line, item.name))


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="exact variable name documented as publishable (repeatable)",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        help="public prefix such as VITE_ (repeatable; replaces the default)",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="check the rules and exit"
    )
    return parser


class SelfTestError(AssertionError):
    """A documented rule did not behave as expected on synthetic input."""


def self_test() -> None:
    """Check dotenv and source parsing on synthetic text.

    Raises:
        SelfTestError: If the reported names differ from the expectation.
    """
    dotenv = (
        "VITE_APP_NAME=Example\n"
        "export VITE_API_KEY=\n"
        "SERVER_SECRET=\n"
        "VITE_KEYBOARD_LAYOUT=us\n"
    )
    source = (
        "const a = import.meta.env.VITE_AUTH_TOKEN;\n"
        "const b = import.meta.env.VITE_SECRET; // frontend-env: allow reviewed\n"
    )
    found = [
        item.name
        for item in scan_text(
            dotenv, path=".env", env_file=True, prefixes=DEFAULT_PREFIXES
        )
    ]
    found += [
        item.name
        for item in scan_text(
            source, path="a.ts", env_file=False, prefixes=DEFAULT_PREFIXES
        )
    ]
    expected = ["VITE_API_KEY", "VITE_AUTH_TOKEN"]
    if found != expected:
        message = f"expected {expected}, found {found}"
        raise SelfTestError(message)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scan and print findings.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when clean, 1 with findings, 2 for usage or input errors (argparse
        exits with 2 on invalid arguments).
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Frontend env checker self-test passed.")
        return EXIT_CLEAN
    if not args.paths:
        parser.error("give at least one file or directory")
    prefixes = tuple(args.prefix or DEFAULT_PREFIXES)
    if not all(prefixes):
        print("An empty prefix would expose every variable.", file=sys.stderr)
        return EXIT_USAGE
    try:
        findings = scan_paths(args.paths, prefixes=prefixes, allow=tuple(args.allow))
    except (OSError, UnicodeDecodeError) as error:
        print(f"Cannot scan: {error}", file=sys.stderr)
        return EXIT_USAGE
    return _report(findings)


def _report(findings: Sequence[Finding]) -> int:
    """Print findings or a clean summary and return the exit status."""
    for finding in findings:
        print(finding.render())
    if findings:
        return EXIT_FINDINGS
    print("No secret-like public variable names found (names only).")
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
