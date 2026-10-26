"""Scan built frontend output for secret-like values and forbidden public content.

Everything a browser downloads is public. This checker reads files below a build
directory (for example ``dist``) as text and reports likely credentials, private
keys, tokens, optional deny patterns such as internal host names, and, when asked,
published source maps. It never executes or uploads anything; a clean result is
evidence about the scanned patterns only, not proof that no secret exists.
"""

import argparse
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

_DEFAULT_SUFFIXES = (".js", ".mjs", ".cjs", ".css", ".html", ".json", ".map", ".txt")
_MAX_BYTES = 5_000_000
_PREVIEW_CHARS = 6


@dataclass(frozen=True, kw_only=True, slots=True)
class Rule:
    """One named pattern with a short remediation hint."""

    name: str
    pattern: re.Pattern[str]
    hint: str


_RULES: tuple[Rule, ...] = (
    Rule(
        name="private-key",
        pattern=re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        hint="private keys never belong in client assets",
    ),
    Rule(
        name="connection-string-secret",
        pattern=re.compile(
            r"(?i)\b(?:AccountKey|SharedAccessKey|Password|Pwd)=[^;\s\"']{8,}"
        ),
        hint="connection strings with keys belong on the server",
    ),
    Rule(
        name="client-secret",
        pattern=re.compile(
            r"(?i)[\"']?client[_-]?secret[\"']?\s*[:=]\s*[\"'][^\"']{8,}[\"']"
        ),
        hint="public clients use PKCE, not a client secret",
    ),
    Rule(
        name="jwt",
        pattern=re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
        ),
        hint="tokens must be obtained at runtime, not bundled",
    ),
    Rule(
        name="cloud-access-key-id",
        pattern=re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        hint="cloud credentials must not reach the browser",
    ),
    Rule(
        name="vcs-token",
        pattern=re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        hint="source-control tokens must not reach the browser",
    ),
    Rule(
        name="secret-assignment",
        pattern=re.compile(
            r"(?i)[\"']?\b(?:api[_-]?secret|secret[_-]?key|private[_-]?token)\b[\"']?"
            r"\s*[:=]\s*[\"'][A-Za-z0-9_\-+/=]{16,}[\"']"
        ),
        hint="move the value server-side and call it through an API",
    ),
)


def _redact(value: str) -> str:
    """Show only a short prefix of a match so reports never repeat the secret."""
    return f"{value[:_PREVIEW_CHARS]}... ({len(value)} chars)"


def _candidates(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """List scannable files below root in deterministic order."""
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


class BundleInputError(ValueError):
    """An input violates the bundle input contract."""

    def __init__(self, *, root: Path) -> None:
        """Describe the violated invariant.

        Args:
            root: Diagnostic root for the failing input.
        """
        super().__init__(f"not a directory: {root}")


def scan(
    root: Path,
    *,
    deny: tuple[str, ...] = (),
    allow: tuple[str, ...] = (),
    forbid_source_maps: bool = False,
    suffixes: tuple[str, ...] = _DEFAULT_SUFFIXES,
    max_bytes: int = _MAX_BYTES,
) -> list[str]:
    """Return sorted ``path:line: [rule] message`` findings for a build directory.

    Args:
        root: Build output directory to scan.
        deny: Extra regular expressions that must not appear (for example
            internal host names).
        allow: Regular expressions; a match fully covered by one is ignored.
        forbid_source_maps: Report every ``.map`` file as a finding.
        suffixes: File suffixes to read.
        max_bytes: Files larger than this are reported instead of read.

    Returns:
        Findings ordered by path and line; empty when nothing matched.

    Raises:
        BundleInputError: If root is not a directory.
        re.error: If a pattern is invalid.
    """
    if not root.is_dir():
        raise BundleInputError(root=root)
    rules = list(_RULES)
    rules.extend(
        Rule(name="denied-pattern", pattern=re.compile(item), hint=f"matches {item}")
        for item in deny
    )
    allowed = [re.compile(item) for item in allow]
    findings: list[str] = []
    for path in _candidates(root, suffixes):
        relative = path.relative_to(root).as_posix()
        if forbid_source_maps and path.suffix.lower() == ".map":
            findings.append(f"{relative}:1: [source-map] published source map")
        if path.stat().st_size > max_bytes:
            findings.append(f"{relative}:1: [too-large] not scanned (> {max_bytes})")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            findings.extend(
                _line_findings(f"{relative}:{number}", line, rules, allowed)
            )
    return sorted(findings)


def _line_findings(
    where: str, line: str, rules: list[Rule], allowed: list[re.Pattern[str]]
) -> list[str]:
    """Return rule matches on one line that no allow pattern fully covers."""
    return [
        f"{where}: [{rule.name}] {_redact(match.group(0))}; {rule.hint}"
        for rule in rules
        for match in rule.pattern.finditer(line)
        if not any(item.fullmatch(match.group(0)) for item in allowed)
    ]


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    CLEAN_BUNDLE_REJECTED = "clean bundle must pass"
    UNEXPECTED_FINDINGS = "unexpected findings: {findings}"
    MATCHED_VALUE_ECHOED = "findings must redact matched values"
    ALLOW_PATTERN_IGNORED = "allow patterns must suppress full matches"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self, issue: SelfTestIssue, *, findings: list[str] | None = None
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            findings: Observed findings for the failing case.
        """
        super().__init__(issue.value.format(findings=findings))


def self_test() -> None:
    """Exercise clean, secret, denied, allowed and source-map cases in a temp dir.

    Raises:
        SelfTestError: If any synthetic expectation does not hold.
    """
    with TemporaryDirectory(prefix="agent-kit-bundle-scan-") as directory:
        root = Path(directory)
        assets = root / "assets"
        assets.mkdir()
        (assets / "index.js").write_text(
            'const api="https://api.example.test/";\n', encoding="utf-8"
        )
        if scan(root):
            raise SelfTestError(SelfTestIssue.CLEAN_BUNDLE_REJECTED)
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        header = "-----BEGIN " + "PRIVATE KEY-----"
        (assets / "index.js").write_text(
            f'const a="{fake_key}";\n'
            f"const b=`{header}`;\n"
            'fetch("http://intranet.corp.test");\n',
            encoding="utf-8",
        )
        (assets / "index.js.map").write_text("{}", encoding="utf-8")
        findings = scan(root, deny=(r"intranet\.corp\.test",), forbid_source_maps=True)
        names = [finding.split("[", 1)[1].split("]", 1)[0] for finding in findings]
        # Sorted by path: 'index.js.map' sorts before 'index.js:'.
        expected = [
            "source-map",
            "cloud-access-key-id",
            "private-key",
            "denied-pattern",
        ]
        if names != expected:
            raise SelfTestError(SelfTestIssue.UNEXPECTED_FINDINGS, findings=findings)
        if fake_key in "".join(findings):
            raise SelfTestError(SelfTestIssue.MATCHED_VALUE_ECHOED)
        if len(scan(root, allow=(re.escape(fake_key), r"-----BEGIN.*"))) != 0:
            raise SelfTestError(SelfTestIssue.ALLOW_PATTERN_IGNORED)


def main(argv: list[str] | None = None) -> int:
    """Scan a build directory or run the self-test; return a process exit code.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when no findings exist, 1 when findings or input errors exist.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", type=Path, default=Path("dist"))
    parser.add_argument("--deny", action="append", default=[], help="extra regex")
    parser.add_argument("--allow", action="append", default=[], help="ignore regex")
    parser.add_argument("--forbid-source-maps", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=_MAX_BYTES)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Public bundle scanner self-test passed.")
        return 0
    try:
        findings = scan(
            args.root,
            deny=tuple(args.deny),
            allow=tuple(args.allow),
            forbid_source_maps=args.forbid_source_maps,
            max_bytes=args.max_bytes,
        )
    except (OSError, ValueError, re.error) as error:
        print(f"Cannot scan build output: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if not findings:
        print(f"No secret-like patterns found in {args.root} (pattern scan only).")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
