"""Check a HAR (HTTP Archive) file for credentials and personal data before sharing.

Browser network exports often contain cookies, bearer tokens, one-time codes, and
full response bodies. This checker reads a HAR file with the standard library,
reports every sensitive location as ``path:entry: message``, and exits 1 when any
exist. It never prints the sensitive values themselves and never modifies the
file; redact with the browser's sanitized export or a dedicated tool, then rerun.
"""

import argparse
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
    }
)
_SENSITIVE_PARAMS = re.compile(
    r"(?i)^(?:access_token|id_token|refresh_token|token|code|password|passwd|"
    r"secret|client_secret|api[_-]?key|key|sig|signature|session|sessionid)$"
)
_SENSITIVE_BODY = re.compile(
    r"(?i)\"(?:password|passwd|secret|client_secret|access_token|refresh_token|"
    r"id_token|ssn|card_?number|cvv)\"\s*:"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SELF_TEST_RESPONSE_BYTES = 10
_SELF_TEST_LEAKY_FINDINGS = 5


def _mapping(value: object) -> Mapping[str, object]:
    """Return value when it is a JSON object, otherwise an empty mapping."""
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _sequence(value: object) -> Sequence[object]:
    """Return value when it is a JSON array, otherwise an empty sequence."""
    return value if isinstance(value, list) else []


def _named_values(items: object) -> Iterable[tuple[str, str]]:
    """Yield (name, value) pairs from HAR header, cookie, or query arrays."""
    for item in _sequence(items):
        record = _mapping(item)
        name = record.get("name")
        value = record.get("value")
        if isinstance(name, str) and isinstance(value, str):
            yield name, value


def _entry_findings(
    index: int, entry: Mapping[str, object], *, allow_bodies: bool
) -> list[str]:
    """Collect findings for one HAR entry without echoing sensitive values."""
    request = _mapping(entry.get("request"))
    response = _mapping(entry.get("response"))
    findings: list[str] = []
    for side, message in (("request", request), ("response", response)):
        findings.extend(_message_findings(index, side, message))
    findings.extend(_query_findings(index, request))
    findings.extend(_request_body_findings(index, request))
    findings.extend(_response_body_findings(index, response, allow_bodies=allow_bodies))
    return findings


def _message_findings(
    index: int, side: str, message: Mapping[str, object]
) -> list[str]:
    """Report sensitive header values and any cookie values of one message."""
    findings = [
        f"{index}: {side} header '{name}' has a value"
        for name, value in _named_values(message.get("headers"))
        if name.lower() in _SENSITIVE_HEADERS and value
    ]
    findings.extend(
        f"{index}: {side} cookie '{name}' has a value"
        for name, value in _named_values(message.get("cookies"))
        if value
    )
    return findings


def _query_findings(index: int, request: Mapping[str, object]) -> list[str]:
    """Report sensitive query parameter values and embedded email addresses."""
    findings: list[str] = []
    for name, value in _named_values(request.get("queryString")):
        if _SENSITIVE_PARAMS.match(name) and value:
            findings.append(f"{index}: query parameter '{name}' has a value")
        if _EMAIL.search(value):
            findings.append(f"{index}: query parameter '{name}' contains an email")
    return findings


def _request_body_findings(index: int, request: Mapping[str, object]) -> list[str]:
    """Report sensitive fields and email addresses in the request body."""
    post_text = _mapping(request.get("postData")).get("text")
    if not isinstance(post_text, str) or not post_text:
        return []
    findings: list[str] = []
    if _SENSITIVE_BODY.search(post_text):
        findings.append(f"{index}: request body contains a sensitive field")
    if _EMAIL.search(post_text):
        findings.append(f"{index}: request body contains an email")
    return findings


def _response_body_findings(
    index: int, response: Mapping[str, object], *, allow_bodies: bool
) -> list[str]:
    """Report sensitive or, unless allowed, any retained response body."""
    text = _mapping(response.get("content")).get("text")
    if not isinstance(text, str) or not text:
        return []
    if _SENSITIVE_BODY.search(text):
        return [f"{index}: response body contains a sensitive field"]
    if not allow_bodies:
        return [f"{index}: response body retained (export without content)"]
    return []


class HarInputIssue(StrEnum):
    """Supported HAR input validation failures and their stable messages."""

    DOCUMENT_SHAPE = "{path}: not a HAR file (missing log.entries)"


class HarInputError(ValueError):
    """An input violates the HAR input contract."""

    def __init__(self, issue: HarInputIssue, *, path: Path | None = None) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            path: Diagnostic path for the invalid input.
        """
        super().__init__(issue.value.format(path=path))


class HarInputTypeError(TypeError):
    """An input has the wrong Python type for the HAR input contract."""

    def __init__(self, issue: HarInputIssue, *, path: Path | None = None) -> None:
        """Describe a wrong input type.

        Args:
            issue: The violated input invariant.
            path: Diagnostic path for the invalid input.
        """
        super().__init__(issue.value.format(path=path))


def check(path: Path, *, allow_bodies: bool = False) -> list[str]:
    """Return findings for a HAR file as ``file:entry: message`` strings.

    Args:
        path: HAR file to inspect.
        allow_bodies: Accept response bodies that match no sensitive field.

    Returns:
        Findings in entry order; empty when the archive looks safe to share.

    Raises:
        ValueError: If the file is not a HAR document.
        TypeError: If a present HAR container has the wrong Python type.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise HarInputTypeError(HarInputIssue.DOCUMENT_SHAPE, path=path)
    if "log" in document and not isinstance(document["log"], dict):
        raise HarInputTypeError(HarInputIssue.DOCUMENT_SHAPE, path=path)
    log = _mapping(_mapping(document).get("log"))
    entries = log.get("entries")
    if "entries" not in log:
        raise HarInputError(HarInputIssue.DOCUMENT_SHAPE, path=path)
    if not isinstance(entries, list):
        raise HarInputTypeError(HarInputIssue.DOCUMENT_SHAPE, path=path)
    findings: list[str] = []
    for index, entry in enumerate(entries):
        findings.extend(
            f"{path.name}:{finding}"
            for finding in _entry_findings(
                index, _mapping(entry), allow_bodies=allow_bodies
            )
        )
    return findings


def _har(entries: list[dict[str, object]]) -> str:
    """Build a minimal HAR document for self-tests."""
    return json.dumps({"log": {"version": "1.2", "entries": entries}})


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    CLEAN_ARCHIVE_REJECTED = "clean archive must pass"
    UNEXPECTED_FINDINGS = "unexpected findings: {findings}"
    SENSITIVE_VALUE_ECHOED = "findings must not echo sensitive values"
    NEUTRAL_BODY_REJECTED = "allow_bodies must accept neutral bodies"
    INVALID_ARCHIVE_ACCEPTED = "non-HAR input must be rejected"


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
    """Exercise clean, header, query, body and invalid archives in a temp dir.

    Raises:
        AssertionError: If any synthetic expectation does not hold.
    """
    clean: dict[str, object] = {
        "request": {
            "headers": [{"name": "Accept", "value": "application/json"}],
            "queryString": [{"name": "page", "value": "2"}],
        },
        "response": {"headers": [], "content": {"size": _SELF_TEST_RESPONSE_BYTES}},
    }
    leaky: dict[str, object] = {
        "request": {
            "headers": [{"name": "Authorization", "value": "Bearer abc"}],
            "queryString": [{"name": "code", "value": "xyz"}],
            "postData": {"text": '{"password": "p"}'},
        },
        "response": {
            "cookies": [{"name": "sid", "value": "s1"}],
            "content": {"text": '{"items": []}'},
        },
    }
    with TemporaryDirectory(prefix="agent-kit-har-") as directory:
        path = Path(directory) / "capture.har"
        path.write_text(_har([clean]), encoding="utf-8")
        if check(path):
            raise SelfTestError(SelfTestIssue.CLEAN_ARCHIVE_REJECTED)
        path.write_text(_har([clean, leaky]), encoding="utf-8")
        findings = check(path)
        expected = _SELF_TEST_LEAKY_FINDINGS
        if len(findings) != expected or not all(":1: " in item for item in findings):
            raise SelfTestError(SelfTestIssue.UNEXPECTED_FINDINGS, findings=findings)
        if any("abc" in item or "xyz" in item for item in findings):
            raise SelfTestError(SelfTestIssue.SENSITIVE_VALUE_ECHOED)
        if len(check(path, allow_bodies=True)) != expected - 1:
            raise SelfTestError(SelfTestIssue.NEUTRAL_BODY_REJECTED)
        path.write_text("{}", encoding="utf-8")
        if not _rejects(path):
            raise SelfTestError(SelfTestIssue.INVALID_ARCHIVE_ACCEPTED)


def _rejects(path: Path) -> bool:
    """Return whether ``check`` rejects the file as a non-HAR document."""
    try:
        check(path)
    except ValueError:
        return True
    return False


def _check_all(files: list[Path], *, allow_bodies: bool) -> list[str]:
    """Return findings for every file in order."""
    findings: list[str] = []
    for path in files:
        findings.extend(check(path, allow_bodies=allow_bodies))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Check HAR files or run the self-test; return a process exit code.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when every file is clean, 1 on findings or unreadable input.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--allow-bodies", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("HAR checker self-test passed.")
        return 0
    if not args.files:
        parser.error("provide at least one HAR file or --self-test")
    try:
        findings = _check_all(args.files, allow_bodies=args.allow_bodies)
    except (OSError, UnicodeError, ValueError, HarInputTypeError) as error:
        print(f"Cannot check HAR input: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if not findings:
        print("No credentials or retained bodies found in the HAR input.")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
