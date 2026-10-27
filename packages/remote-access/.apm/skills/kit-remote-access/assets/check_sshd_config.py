"""Flag insecure OpenSSH server directives in ``sshd_config`` files.

Each file is read on its own (``Include`` is not followed). Keywords are
case-insensitive; ``Keyword value`` and ``Keyword=value`` are both accepted.
Every finding is printed as ``path:line: message``. Reported problems:

- password, keyboard-interactive, empty-password, host-based, or rhosts login;
- ``PermitRootLogin`` other than ``no``;
- agent, X11, gateway-port forwarding, ``PermitUserEnvironment``, or
  ``StrictModes no``;
- ``LogLevel`` below ``INFO``, which hides authentication audit records;
- legacy ciphers, MACs, key exchanges, or SHA-1 signature algorithms in
  algorithm lists (``-`` removals are ignored);
- a keyword repeated in the global section with a different value; sshd uses
  the first value it reads, so the later line is silently ignored.

With ``--require-baseline`` each file must also set, in its global section:
``PasswordAuthentication no``, ``KbdInteractiveAuthentication no``,
``PermitRootLogin no``, and ``AllowUsers`` or ``AllowGroups``.

Exit codes: 0 clean, 1 findings, 2 unreadable input or bad arguments.
"""

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import sys

_FINDINGS = 1
_INVALID = 2
_LINE = re.compile(r"^(?P<keyword>[A-Za-z][A-Za-z0-9]*)(?:\s*=\s*|\s+)(?P<value>.*)$")
_INSECURE_VALUES = {
    "passwordauthentication": (
        frozenset({"yes"}),
        "password login enabled; use keys or certificates",
    ),
    "kbdinteractiveauthentication": (
        frozenset({"yes"}),
        "keyboard-interactive login enabled; it usually means passwords",
    ),
    "challengeresponseauthentication": (
        frozenset({"yes"}),
        "deprecated alias of KbdInteractiveAuthentication enables passwords",
    ),
    "permitemptypasswords": (
        frozenset({"yes"}),
        "empty passwords are accepted",
    ),
    "hostbasedauthentication": (
        frozenset({"yes"}),
        "host-based authentication trusts other hosts' user mapping",
    ),
    "ignorerhosts": (
        frozenset({"no"}),
        "rhosts files are honored",
    ),
    "pubkeyauthentication": (
        frozenset({"no"}),
        "public key login disabled, which forces weaker methods",
    ),
    "permituserenvironment": (
        frozenset({"yes"}),
        "users can set environment variables that alter login behavior",
    ),
    "x11forwarding": (
        frozenset({"yes"}),
        "X11 forwarding exposes the client display",
    ),
    "allowagentforwarding": (
        frozenset({"yes"}),
        "agent forwarding lets the server use the client's keys; use ProxyJump",
    ),
    "gatewayports": (
        frozenset({"yes", "clientspecified"}),
        "forwarded ports can listen on public interfaces",
    ),
    "strictmodes": (
        frozenset({"no"}),
        "sshd ignores unsafe permissions on key files",
    ),
    "loglevel": (
        frozenset({"quiet", "fatal", "error"}),
        "log level hides authentication events; use VERBOSE",
    ),
}
_WEAK_ALGORITHMS = {
    "ciphers": re.compile(r"cbc|3des|arcfour|blowfish|cast128|^none$"),
    "macs": re.compile(r"md5|sha1(?!\d)|ripemd|umac-64|^none$"),
    "kexalgorithms": re.compile(r"sha1(?!\d)"),
    "hostkeyalgorithms": re.compile(r"^ssh-(?:rsa|dss)(?:-cert-v01@openssh\.com)?$"),
    "pubkeyacceptedalgorithms": re.compile(
        r"^ssh-(?:rsa|dss)(?:-cert-v01@openssh\.com)?$"
    ),
    "pubkeyacceptedkeytypes": re.compile(
        r"^ssh-(?:rsa|dss)(?:-cert-v01@openssh\.com)?$"
    ),
    "casignaturealgorithms": re.compile(r"^ssh-(?:rsa|dss)$"),
}
_ACCUMULATING = frozenset(
    {
        "acceptenv",
        "allowgroups",
        "allowusers",
        "denygroups",
        "denyusers",
        "hostcertificate",
        "hostkey",
        "include",
        "listenaddress",
        "port",
        "subsystem",
    }
)
_BASELINE = (
    ("passwordauthentication", "PasswordAuthentication no"),
    ("kbdinteractiveauthentication", "KbdInteractiveAuthentication no"),
    ("permitrootlogin", "PermitRootLogin no"),
)


class SshdConfigError(ValueError):
    """A line cannot be read as ``Keyword value``."""

    def __init__(self, *, line: int, text: str) -> None:
        """Describe the malformed line.

        Args:
            line: One-based line number.
            text: The offending line without surrounding whitespace.
        """
        super().__init__(f"line {line}: expected 'Keyword value', got '{text}'")


@dataclass(frozen=True, kw_only=True, slots=True)
class Setting:
    """One ``Keyword value`` line.

    Attributes:
        keyword: Keyword in lower case.
        name: Keyword as written.
        value: Value text with one pair of surrounding quotes removed.
        line: One-based line number.
        match_line: Line of the enclosing ``Match`` block, or 0 when global.
    """

    keyword: str
    name: str
    value: str
    line: int
    match_line: int


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One reportable configuration problem.

    Attributes:
        path: File that contains the problem.
        line: One-based line number.
        message: Human-readable explanation.
    """

    path: Path
    line: int
    message: str

    def render(self) -> str:
        """Return the deterministic ``path:line: message`` form."""
        return f"{self.path.as_posix()}:{self.line}: {self.message}"


def _unquote(text: str) -> str:
    """Remove one pair of surrounding double quotes."""
    if len(text) > 1 and text[0] == text[-1] == '"':
        return text[1:-1]
    return text


def parse(text: str) -> list[Setting]:
    """Read every ``Keyword value`` line and note its ``Match`` scope.

    Args:
        text: Complete ``sshd_config`` text.

    Returns:
        Settings in file order; comments and blank lines are skipped.

    Raises:
        SshdConfigError: If a non-comment line has no value.
    """
    settings: list[Setting] = []
    match_line = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parsed = _LINE.match(stripped)
        if parsed is None:
            raise SshdConfigError(line=number, text=stripped)
        keyword = parsed.group("keyword").lower()
        if keyword == "match":
            match_line = number
        settings.append(
            Setting(
                keyword=keyword,
                name=parsed.group("keyword"),
                value=_unquote(parsed.group("value").strip()),
                line=number,
                match_line=match_line,
            )
        )
    return settings


def _scope(setting: Setting) -> str:
    """Describe a ``Match`` scope for a finding message."""
    if setting.match_line:
        return f" (in Match block at line {setting.match_line})"
    return ""


def _value_finding(path: Path, setting: Setting) -> Finding | None:
    """Report an insecure single-value directive."""
    words = setting.value.split()
    first = words[0].lower() if words else ""
    rule = _INSECURE_VALUES.get(setting.keyword)
    if setting.keyword == "permitrootlogin" and first != "no":
        message = (
            f"PermitRootLogin {setting.value} allows root login; set "
            "'PermitRootLogin no' and escalate with sudo"
        )
    elif rule is not None and first in rule[0]:
        message = f"{setting.name} {setting.value}: {rule[1]}"
    else:
        return None
    return Finding(path=path, line=setting.line, message=message + _scope(setting))


def _algorithm_finding(path: Path, setting: Setting) -> Finding | None:
    """Report legacy entries in an algorithm list; removals are ignored."""
    pattern = _WEAK_ALGORITHMS.get(setting.keyword)
    if pattern is None or setting.value.startswith("-"):
        return None
    names = [name.strip() for name in setting.value.lstrip("+^").split(",")]
    weak = [name for name in names if name and pattern.search(name.lower())]
    if not weak:
        return None
    return Finding(
        path=path,
        line=setting.line,
        message=(
            f"{setting.name} allows legacy algorithm(s) {', '.join(weak)}"
            f"{_scope(setting)}"
        ),
    )


def _first_global(settings: Iterable[Setting]) -> dict[str, Setting]:
    """Return the first global setting per keyword, as sshd applies them."""
    first: dict[str, Setting] = {}
    for setting in settings:
        if not setting.match_line:
            first.setdefault(setting.keyword, setting)
    return first


def _duplicate_findings(path: Path, settings: Sequence[Setting]) -> list[Finding]:
    """Report global keywords whose later, different value sshd ignores."""
    first = _first_global(settings)
    findings: list[Finding] = []
    for setting in settings:
        earlier = first.get(setting.keyword)
        if (
            setting.match_line
            or setting.keyword in _ACCUMULATING
            or earlier is None
            or earlier is setting
            or earlier.value.lower() == setting.value.lower()
        ):
            continue
        findings.append(
            Finding(
                path=path,
                line=setting.line,
                message=(
                    f"{setting.name} {setting.value} is ignored; sshd uses the "
                    f"first value '{earlier.value}' from line {earlier.line}"
                ),
            )
        )
    return findings


def _baseline_findings(path: Path, settings: Sequence[Setting]) -> list[Finding]:
    """Report hardening directives missing from the global section."""
    first = _first_global(settings)
    findings = [
        Finding(
            path=path,
            line=1,
            message=f"baseline requires '{expected}' in the global section",
        )
        for keyword, expected in _BASELINE
        if keyword not in first
    ]
    if "allowusers" not in first and "allowgroups" not in first:
        findings.append(
            Finding(
                path=path,
                line=1,
                message=(
                    "baseline requires 'AllowUsers' or 'AllowGroups' in the "
                    "global section"
                ),
            )
        )
    return findings


def scan_text(path: Path, text: str, *, require_baseline: bool) -> list[Finding]:
    """Check one ``sshd_config`` file and return its findings in line order.

    Args:
        path: Path reported in findings.
        text: File content.
        require_baseline: Whether missing hardening directives are findings.

    Returns:
        Findings sorted by line number and message.

    Raises:
        SshdConfigError: If a line cannot be parsed.
    """
    settings = parse(text)
    candidates = [
        check(path, setting)
        for setting in settings
        for check in (_value_finding, _algorithm_finding)
    ]
    findings = [finding for finding in candidates if finding is not None]
    findings.extend(_duplicate_findings(path, settings))
    if require_baseline:
        findings.extend(_baseline_findings(path, settings))
    return sorted(findings, key=lambda finding: (finding.line, finding.message))


class MissingPathError(ValueError):
    """A path named on the command line does not exist."""

    def __init__(self, *, path: Path) -> None:
        """Describe the missing path.

        Args:
            path: The path that was not found.
        """
        super().__init__(f"path does not exist: {path}")


def collect_files(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into sorted ``*.conf`` files; keep explicit files.

    Args:
        paths: Files or directories, such as ``/etc/ssh/sshd_config.d``.

    Returns:
        Sorted, de-duplicated file list.

    Raises:
        MissingPathError: If a path does not exist.
    """
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(
                candidate for candidate in path.glob("*.conf") if candidate.is_file()
            )
        elif path.is_file():
            files.add(path)
        else:
            raise MissingPathError(path=path)
    return sorted(files)


def self_test() -> list[str]:
    """Check the rules on in-memory configurations and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    clean = (
        "# hardened\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n"
        "PermitRootLogin no\nAllowGroups ssh-users\nCiphers -aes128-cbc\n"
        "HostKey /etc/ssh/ssh_host_ed25519_key\nHostKey /etc/ssh/ssh_host_ecdsa_key\n"
    )
    risky = (
        "PasswordAuthentication yes\nPermitRootLogin prohibit-password\n"
        "MACs +hmac-sha1\nPasswordAuthentication no\n"
        "Match Address 10.0.0.0/8\n  X11Forwarding yes\n"
    )
    failures: list[str] = []
    if scan_text(Path("clean.conf"), clean, require_baseline=True):
        failures.append("clean configuration produced findings")
    findings = scan_text(Path("risky.conf"), risky, require_baseline=True)
    rendered = "\n".join(item.render() for item in findings)
    expectations = {
        "password login": "risky.conf:1: PasswordAuthentication yes",
        "root login": "risky.conf:2: PermitRootLogin prohibit-password",
        "legacy MAC": "risky.conf:3: MACs allows legacy algorithm(s) hmac-sha1",
        "ignored duplicate": "risky.conf:4: PasswordAuthentication no is ignored",
        "match scope": "(in Match block at line 5)",
        "baseline group": "risky.conf:1: baseline requires 'AllowUsers'",
    }
    failures.extend(
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    )
    try:
        parse("PasswordAuthentication\n")
    except SshdConfigError:
        pass
    else:
        failures.append("keyword without value was accepted")
    return failures


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return _FINDINGS
    print("check_sshd_config self-test passed.")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths", nargs="*", type=Path, help="sshd_config files or drop-in directories"
    )
    parser.add_argument(
        "--require-baseline",
        action="store_true",
        help="also report missing hardening directives in each file",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def _scan(paths: Iterable[Path], *, require_baseline: bool) -> int:
    """Scan files, print findings, and return the exit status."""
    findings: list[Finding] = []
    try:
        files = collect_files(paths)
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
                findings.extend(
                    scan_text(path, text, require_baseline=require_baseline)
                )
            except SshdConfigError as error:
                print(f"Cannot check {path.as_posix()}: {error}", file=sys.stderr)
                return _INVALID
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Cannot check sshd configuration: {error}", file=sys.stderr)
        return _INVALID
    for finding in findings:
        print(finding.render())
    if findings:
        print(f"{len(findings)} finding(s) in {len(files)} file(s)", file=sys.stderr)
        return _FINDINGS
    print(f"No findings in {len(files)} file(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Check sshd configuration files and print one finding per line.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when clean, 1 with findings (or a failed self-test), 2 for missing
        paths or unreadable input.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.paths:
        parser.error("at least one path is required unless --self-test is given")
    return _scan(args.paths, require_baseline=args.require_baseline)


if __name__ == "__main__":
    raise SystemExit(main())
