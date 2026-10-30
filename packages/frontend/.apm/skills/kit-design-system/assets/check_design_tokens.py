# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Report hard-coded colors and pixel values outside the design token file.

The scan reads ``.css`` and ``.tsx`` files (configurable with ``--suffix``)
below each given path and reports three rules:

- ``hex-color``: ``#`` followed by three, four, six, or eight hex digits,
  including Tailwind arbitrary values such as ``bg-[#1d4ed8]``;
- ``literal-color``: ``rgb()``, ``hsl()``, ``oklch()`` and related color
  functions whose first argument is a number instead of ``var()``;
- ``arbitrary-px``: pixel lengths such as ``13px`` or ``w-[37px]``, except the
  allowed magnitudes (``0`` and ``1`` by default, for resets and hairlines).

Token files (``--token-file`` glob, default ``theme.css`` and ``tokens.css``)
are skipped because raw palette values belong there. Comments are ignored. A
line containing ``design-tokens: allow`` is exempt; state the reason on it.

Output is ``path:line:column: [rule] message`` sorted by path and position.
Exit status: 0 clean, 1 findings, 2 usage error or unreadable input.
``--self-test`` checks the rules on synthetic sources and exits.

Limitations: this is pattern matching. Named colors, unit-free inline style
numbers, values assembled at runtime, and ``#`` fragments that look like hex
(``href="#add"``) are not classified precisely; suppress or refactor those.

Example:
    python check_design_tokens.py src --token-file "src/styles/theme.css"
"""

import argparse
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import fnmatch
from pathlib import Path
import re
import sys

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
DEFAULT_SUFFIXES: tuple[str, ...] = (".css", ".tsx")
DEFAULT_TOKEN_FILES: tuple[str, ...] = ("theme.css", "tokens.css")
DEFAULT_ALLOWED_PX: tuple[float, ...] = (0.0, 1.0)
SUPPRESSION = "design-tokens: allow"
_SKIPPED_DIRECTORIES = frozenset(
    {".git", "node_modules", "dist", "build", "coverage", "storybook-static"}
)
_HEX = re.compile(
    r"(?<![\w&#])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])"
)
_COLOR_FUNCTION = re.compile(
    r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(\s*[-+]?(?:\d|\.\d)"
)
_PIXELS = re.compile(r"(?<![\w.#-])(-?\d+(?:\.\d+)?)px\b")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<![:\w\"'/])//[^\n]*")


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One hard-coded design value.

    Attributes:
        path: File as given or discovered, in POSIX form.
        line: One-based line number.
        column: One-based column of the match.
        rule: Rule identifier.
        message: Remediation hint including the matched text.
    """

    path: str
    line: int
    column: int
    rule: str
    message: str

    def render(self) -> str:
        """Return ``path:line:column: [rule] message``."""
        return f"{self.path}:{self.line}:{self.column}: [{self.rule}] {self.message}"


def _blank(match: re.Match[str]) -> str:
    """Replace a comment with spaces, keeping newlines so positions stay valid."""
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_comments(text: str, *, suffix: str) -> str:
    """Blank out comments without changing line or column positions.

    Args:
        text: File content.
        suffix: File suffix; ``//`` comments are removed only outside ``.css``.

    Returns:
        Text of the same length with comment characters replaced by spaces.
    """
    stripped = _BLOCK_COMMENT.sub(_blank, text)
    if suffix != ".css":
        stripped = _LINE_COMMENT.sub(_blank, stripped)
    return stripped


def _line_findings(
    line: str, *, where: tuple[str, int], allowed_px: frozenset[float]
) -> Iterator[Finding]:
    """Yield findings for one comment-free line."""
    path, number = where
    for match in _HEX.finditer(line):
        yield Finding(
            path=path,
            line=number,
            column=match.start() + 1,
            rule="hex-color",
            message=f"{match.group(0)} is a raw color; use a semantic color token",
        )
    for match in _COLOR_FUNCTION.finditer(line):
        yield Finding(
            path=path,
            line=number,
            column=match.start() + 1,
            rule="literal-color",
            message=f"{match.group(0)}...) is a raw color; use a semantic color token",
        )
    for match in _PIXELS.finditer(line):
        if abs(float(match.group(1))) in allowed_px:
            continue
        yield Finding(
            path=path,
            line=number,
            column=match.start() + 1,
            rule="arbitrary-px",
            message=f"{match.group(0)} bypasses the scale; use a spacing or size token",
        )


def scan_text(
    text: str, *, path: str, suffix: str, allowed_px: frozenset[float]
) -> list[Finding]:
    """Return findings for one file's content.

    Args:
        text: File content.
        path: Path used in findings.
        suffix: File suffix that selects comment syntax.
        allowed_px: Pixel magnitudes that are not reported.

    Returns:
        Findings in line and column order.
    """
    original = text.splitlines()
    findings: list[Finding] = []
    stripped = strip_comments(text, suffix=suffix).splitlines()
    for number, line in enumerate(stripped, start=1):
        if SUPPRESSION in original[number - 1]:
            continue
        findings.extend(
            _line_findings(line, where=(path, number), allowed_px=allowed_px)
        )
    return findings


def _is_token_file(path: Path, token_files: Sequence[str]) -> bool:
    """Return whether a file name or POSIX path matches a token-file pattern."""
    posix = path.as_posix()
    return any(
        fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(posix, pattern)
        for pattern in token_files
    )


def iter_files(
    paths: Sequence[Path], *, suffixes: Sequence[str], token_files: Sequence[str]
) -> Iterator[Path]:
    """Yield scannable files in deterministic order.

    Args:
        paths: Files or directories to scan.
        suffixes: File suffixes to include.
        token_files: Glob patterns of token files to skip.

    Yields:
        Every explicitly named file, plus matching files below each directory
        except dependency and build output directories inside it.

    Raises:
        FileNotFoundError: If a given path does not exist.
    """
    for root in paths:
        if not root.exists():
            raise FileNotFoundError(root)
        if root.is_file():
            # Explicitly named files are always scanned.
            yield root
        else:
            yield from _walk(root, suffixes=suffixes, token_files=token_files)


def _walk(
    root: Path, *, suffixes: Sequence[str], token_files: Sequence[str]
) -> Iterator[Path]:
    """Yield matching files below ``root``, judging only the path inside it."""
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and path.suffix in suffixes
            and not _SKIPPED_DIRECTORIES.intersection(relative.parts)
            and not _is_token_file(relative, token_files)
        ):
            yield path


def scan_paths(
    paths: Sequence[Path],
    *,
    suffixes: Sequence[str] = DEFAULT_SUFFIXES,
    token_files: Sequence[str] = DEFAULT_TOKEN_FILES,
    allowed_px: Sequence[float] = DEFAULT_ALLOWED_PX,
) -> list[Finding]:
    """Scan files and directories and return sorted findings.

    Args:
        paths: Files or directories to scan.
        suffixes: File suffixes to include.
        token_files: Glob patterns of token files to skip.
        allowed_px: Pixel magnitudes that are not reported.

    Returns:
        Findings sorted by path, line, and column.

    Raises:
        FileNotFoundError: If a given path does not exist.
        UnicodeDecodeError: If a file is not UTF-8 text.
    """
    allowed = frozenset(abs(value) for value in allowed_px)
    findings: list[Finding] = []
    for path in iter_files(paths, suffixes=suffixes, token_files=token_files):
        text = path.read_text(encoding="utf-8")
        findings.extend(
            scan_text(
                text, path=path.as_posix(), suffix=path.suffix, allowed_px=allowed
            )
        )
    return sorted(
        findings, key=lambda item: (item.path, item.line, item.column, item.rule)
    )


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument(
        "--token-file",
        action="append",
        help="glob of a token file to skip (repeatable; replaces the defaults)",
    )
    parser.add_argument(
        "--allow-px",
        action="append",
        type=float,
        help="pixel magnitude to allow (repeatable; replaces the defaults)",
    )
    parser.add_argument(
        "--suffix",
        action="append",
        help="file suffix to scan, such as .scss (repeatable; replaces defaults)",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="check the rules and exit"
    )
    return parser


class SelfTestError(AssertionError):
    """A documented rule did not behave as expected on synthetic input."""


_SELF_TEST_CASES: tuple[tuple[str, str, list[str]], ...] = (
    (
        ".tsx",
        'export const A = () => <p className="bg-[#1d4ed8] w-[37px]" />;\n',
        ["hex-color", "arbitrary-px"],
    ),
    (
        ".css",
        "a { color: rgb(0 0 0); margin: 13px; border: 1px solid var(--border); }\n",
        ["literal-color", "arbitrary-px"],
    ),
    (
        ".tsx",
        (
            "// #ffffff 13px\n"
            'const a = <a href="#main" className="p-4 text-foreground" />;\n'
            "const b = { width: '3px' }; // design-tokens: allow measured hairline\n"
        ),
        [],
    ),
)


def self_test() -> None:
    """Check each rule, comment stripping, and suppression on synthetic sources.

    Raises:
        SelfTestError: If a case produces unexpected rules.
    """
    allowed = frozenset(DEFAULT_ALLOWED_PX)
    for suffix, text, expected in _SELF_TEST_CASES:
        found = [
            item.rule
            for item in scan_text(text, path="case", suffix=suffix, allowed_px=allowed)
        ]
        if found != expected:
            message = f"{suffix} case: expected {expected}, found {found}"
            raise SelfTestError(message)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scan and print findings.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when clean, 1 with findings, 2 for unreadable input (argparse exits
        with 2 on invalid arguments).
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        sys.stdout.write("Design token checker self-test passed.\n")
        return EXIT_CLEAN
    if not args.paths:
        parser.error("give at least one file or directory")
    try:
        findings = scan_paths(
            args.paths,
            suffixes=tuple(args.suffix or DEFAULT_SUFFIXES),
            token_files=tuple(args.token_file or DEFAULT_TOKEN_FILES),
            allowed_px=tuple(args.allow_px or DEFAULT_ALLOWED_PX),
        )
    except (OSError, UnicodeDecodeError) as error:
        sys.stderr.write(f"Cannot scan: {error}\n")
        return EXIT_USAGE
    for finding in findings:
        sys.stdout.write(f"{finding.render()}\n")
    if findings:
        return EXIT_FINDINGS
    sys.stdout.write(
        "No hard-coded colors or pixel values found (pattern scan only).\n"
    )
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
