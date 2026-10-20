"""Validate task envelope samples against the queue message contract.

Input: one or more JSON files, each holding a list of envelope objects as
produced by 'TaskEnvelope.to_json()'. Use it on fixtures, contract samples,
or dead-letter exports before replay.

Checks per envelope: required string fields 'task_id', 'task_type' and
'idempotency_key'; integer 'version' of at least 1; object 'payload';
timezone-aware ISO 8601 'created_at'; no secret-like payload keys; compact
size within '--max-bytes'; and, when '--supported TYPE:VERSION' is given, a
supported type and version. Across files: duplicate 'task_id' values are
findings; duplicate 'idempotency_key' values are findings unless
'--allow-duplicate-keys' is given (useful for duplicate-delivery fixtures).

Exit codes: 0 clean, 1 findings, 2 unreadable input or bad arguments.
Limitations: validates message bodies only; it does not inspect broker
configuration, visibility timeouts, or delivery guarantees.
"""

import argparse
import json
import sys
from datetime import datetime
from enum import StrEnum
from pathlib import Path

SECRET_KEYS = frozenset({"password", "secret", "token", "api_key", "authorization"})


class QueueInputIssue(StrEnum):
    """Supported queue input validation failures and their stable messages."""

    ARRAY_REQUIRED = "expected a JSON array of envelopes"
    UNTERMINATED_ARRAY = "unterminated JSON array"
    TRAILING_CONTENT = "unexpected content after the array"
    SUPPORTED_FORMAT = "--supported expects TYPE:VERSION, got {value!r}"


class QueueInputError(ValueError):
    """An input violates the queue input contract."""

    def __init__(self, issue: QueueInputIssue, *, value: str | None = None) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            value: Diagnostic value for the invalid input.
        """
        super().__init__(issue.value.format(value=value))


def items_with_lines(text: str) -> list[tuple[int, object]]:
    """Decode a top-level JSON array, keeping the line of each element.

    Args:
        text: JSON document text.

    Returns:
        Pairs of one-based line number and decoded element.

    Raises:
        ValueError: If the document is not a JSON array.
    """
    decoder = json.JSONDecoder()
    index = len(text) - len(text.lstrip())
    if not text.startswith("[", index):
        raise QueueInputError(QueueInputIssue.ARRAY_REQUIRED)
    index += 1
    items: list[tuple[int, object]] = []
    while True:
        while index < len(text) and text[index] in " \t\r\n,":
            index += 1
        if index >= len(text):
            raise QueueInputError(QueueInputIssue.UNTERMINATED_ARRAY)
        if text[index] == "]":
            if text[index + 1 :].strip():
                raise QueueInputError(QueueInputIssue.TRAILING_CONTENT)
            return items
        line = text.count("\n", 0, index) + 1
        value, index = decoder.raw_decode(text, index)
        items.append((line, value))


def parse_supported(values: list[str]) -> dict[str, set[int]]:
    """Parse '--supported TYPE:VERSION' values.

    Args:
        values: Raw option values.

    Returns:
        Task type to supported versions.

    Raises:
        ValueError: If a value is malformed.
    """
    supported: dict[str, set[int]] = {}
    for value in values:
        task_type, _, version = value.rpartition(":")
        if not task_type or not version.isdigit():
            raise QueueInputError(QueueInputIssue.SUPPORTED_FORMAT, value=value)
        supported.setdefault(task_type, set()).add(int(version))
    return supported


def check_envelope(
    item: object,
    *,
    where: str,
    max_bytes: int,
    supported: dict[str, set[int]],
) -> list[str]:
    """Return findings for one envelope.

    Args:
        item: Decoded element.
        where: 'path:line' prefix.
        max_bytes: Maximum compact JSON size.
        supported: Task type to versions; empty means accept any.

    Returns:
        Findings for this envelope.
    """
    if not isinstance(item, dict):
        return [f"{where}: envelope must be an object"]
    findings = [
        f"{where}: '{name}' must be a non-empty string"
        for name in ("task_id", "task_type", "idempotency_key")
        if not isinstance(item.get(name), str) or not item.get(name)
    ]
    version = item.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        findings.append(f"{where}: 'version' must be an integer >= 1")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        findings.append(f"{where}: 'payload' must be an object")
    else:
        leaked = sorted(key for key in payload if str(key).casefold() in SECRET_KEYS)
        if leaked:
            findings.append(f"{where}: payload carries secret-like keys {leaked}")
    created = item.get("created_at")
    try:
        if datetime.fromisoformat(str(created)).tzinfo is None:
            findings.append(f"{where}: 'created_at' must include a timezone offset")
    except ValueError:
        findings.append(f"{where}: 'created_at' must be ISO 8601")
    size = len(json.dumps(item, separators=(",", ":"), ensure_ascii=False).encode())
    if size > max_bytes:
        findings.append(f"{where}: envelope is {size} bytes, limit {max_bytes}")
    task_type = item.get("task_type")
    if supported and isinstance(task_type, str) and isinstance(version, int):
        if task_type not in supported:
            findings.append(f"{where}: unsupported task type {task_type!r}")
        elif version not in supported[task_type]:
            findings.append(f"{where}: unsupported version {version} for {task_type!r}")
    return findings


def main(argv: list[str] | None = None) -> int:
    """Validate each sample file and print findings.

    Args:
        argv: Command-line arguments; defaults to 'sys.argv[1:]'.

    Returns:
        0 when clean, 1 with findings, 2 on unreadable input or bad arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="JSON envelope samples")
    parser.add_argument("--max-bytes", type=int, default=64 * 1024)
    parser.add_argument(
        "--supported",
        action="append",
        default=[],
        help="TYPE:VERSION accepted by deployed workers; repeatable",
    )
    parser.add_argument(
        "--allow-duplicate-keys",
        action="store_true",
        help="accept repeated idempotency keys, for duplicate-delivery fixtures",
    )
    args = parser.parse_args(argv)
    try:
        supported = parse_supported(args.supported)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    findings: list[str] = []
    seen_ids: dict[str, str] = {}
    seen_keys: dict[str, str] = {}
    for path in args.paths:
        try:
            items = items_with_lines(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            print(f"{path}:1: cannot read envelopes: {error}", file=sys.stderr)
            return 2
        if not items:
            findings.append(f"{path}:1: sample has no envelopes")
        for line, item in items:
            where = f"{path}:{line}"
            findings.extend(
                check_envelope(
                    item, where=where, max_bytes=args.max_bytes, supported=supported
                )
            )
            if not isinstance(item, dict):
                continue
            task_id, key = item.get("task_id"), item.get("idempotency_key")
            if isinstance(task_id, str) and task_id:
                if task_id in seen_ids:
                    findings.append(
                        f"{where}: duplicate task_id (first at {seen_ids[task_id]})"
                    )
                seen_ids.setdefault(task_id, where)
            if isinstance(key, str) and key:
                if key in seen_keys and not args.allow_duplicate_keys:
                    findings.append(
                        f"{where}: duplicate idempotency_key (first at {seen_keys[key]})"
                    )
                seen_keys.setdefault(key, where)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
