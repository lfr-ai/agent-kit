# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Validate recorded SSE event manifests against the stream contract.

Input: one or more JSON files, each holding a list of event objects shaped
like ``{"seq": 1, "event": "start", "data": {}}``. Use it on fixtures, on
recordings captured by contract tests, or on samples exported from logs.

Checks per file: every item is an object with an integer ``seq``, a known
``event`` name, and an object ``data``; sequence numbers start at the given first
value and increase by one; the first event is ``start`` when the recording
begins at sequence 1; exactly one ``end`` event exists and is last unless
``--allow-open`` is given; the ``end`` event has a known ``status``; each event's
compact JSON payload fits ``--max-event-bytes``.

Exit codes: 0 clean, 1 findings, 2 unreadable input or bad arguments.
Limitations: validates recorded payloads only; it does not open connections,
measure timing, or verify proxy behavior.
"""

import argparse
from enum import StrEnum
import json
from pathlib import Path
import sys

DEFAULT_EVENTS = frozenset({"start", "delta", "progress", "end"})
END_STATUSES = frozenset({"completed", "failed", "cancelled", "timeout"})
_DEFAULT_MAX_EVENT_BYTES = 64 * 1024
_EXIT_USAGE = 2


class StreamInputIssue(StrEnum):
    """Supported stream input validation failures and their stable messages."""

    ARRAY_REQUIRED = "expected a JSON array of events"
    UNTERMINATED_ARRAY = "unterminated JSON array"
    TRAILING_CONTENT = "unexpected content after the array"
    NON_JSON_CONSTANT = "unsupported JSON constant: {value}"


class StreamInputError(ValueError):
    """An input violates the stream input contract."""

    def __init__(self, issue: StreamInputIssue, *, value: str | None = None) -> None:
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
        StreamInputError: The document is not one JSON array.
        ValueError: An element is not valid JSON.
    """
    decoder = json.JSONDecoder()
    index = len(text) - len(text.lstrip())
    if not text.startswith("[", index):
        raise StreamInputError(StreamInputIssue.ARRAY_REQUIRED)
    json.loads(text, parse_constant=_reject_constant)
    index += 1
    items: list[tuple[int, object]] = []
    while True:
        index = _skip_separators(text, index)
        if index >= len(text):
            raise StreamInputError(StreamInputIssue.UNTERMINATED_ARRAY)
        if text[index] == "]":
            if text[index + 1 :].strip():
                raise StreamInputError(StreamInputIssue.TRAILING_CONTENT)
            return items
        line = text.count("\n", 0, index) + 1
        value, index = decoder.raw_decode(text, index)
        items.append((line, value))


def _skip_separators(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n,":
        index += 1
    return index


def _reject_constant(value: str) -> object:
    raise StreamInputError(StreamInputIssue.NON_JSON_CONSTANT, value=value)


def check_events(
    items: list[tuple[int, object]],
    *,
    path: str,
    allowed: frozenset[str],
    max_event_bytes: int,
    allow_open: bool,
) -> list[str]:
    """Return contract findings for one recording.

    Args:
        items: Elements with their line numbers.
        path: Display path used in findings.
        allowed: Known event names.
        max_event_bytes: Maximum compact JSON payload size.
        allow_open: Accept recordings without a terminal ``end`` event.

    Returns:
        Findings formatted as ``path:line: message``, in input order.
    """
    findings: list[str] = []
    expected: int | None = None
    end_lines: list[int] = []
    for position, (line, item) in enumerate(items):
        where = f"{path}:{line}"
        if not isinstance(item, dict):
            findings.append(f"{where}: event must be an object")
            continue
        event, data = item.get("event"), item.get("data")
        sequence_findings, expected = _sequence_findings(
            item.get("seq"), event, where=where, position=position, expected=expected
        )
        findings.extend(sequence_findings)
        if event not in allowed:
            findings.append(f"{where}: unknown event {event!r}")
        findings.extend(
            _payload_findings(data, event, where=where, max_event_bytes=max_event_bytes)
        )
        if event == "end" and isinstance(data, dict):
            end_lines.append(line)
    findings.extend(
        _terminal_findings(items, end_lines, path=path, allow_open=allow_open)
    )
    return findings


def _sequence_findings(
    seq: object, event: object, *, where: str, position: int, expected: int | None
) -> tuple[list[str], int | None]:
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        return [f"{where}: 'seq' must be a positive integer"], expected
    findings: list[str] = []
    if expected is not None and seq != expected:
        findings.append(f"{where}: expected seq {expected}, found {seq}")
    if position == 0 and seq == 1 and event != "start":
        findings.append(f"{where}: a stream starting at seq 1 must begin with 'start'")
    return findings, seq + 1


def _payload_findings(
    data: object, event: object, *, where: str, max_event_bytes: int
) -> list[str]:
    if not isinstance(data, dict):
        return [f"{where}: 'data' must be an object"]
    findings: list[str] = []
    size = len(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode())
    if size > max_event_bytes:
        findings.append(f"{where}: payload is {size} bytes, limit {max_event_bytes}")
    if event == "end" and data.get("status") not in END_STATUSES:
        findings.append(f"{where}: 'end' needs status in {sorted(END_STATUSES)}")
    return findings


def _terminal_findings(
    items: list[tuple[int, object]],
    end_lines: list[int],
    *,
    path: str,
    allow_open: bool,
) -> list[str]:
    if not items:
        return [f"{path}:1: recording has no events"]
    last_line = items[-1][0]
    if len(end_lines) > 1:
        return [f"{path}:{line}: duplicate 'end' event" for line in end_lines[1:]]
    if not end_lines:
        if allow_open:
            return []
        return [f"{path}:{last_line}: recording has no terminal 'end' event"]
    if end_lines[0] != last_line:
        return [f"{path}:{end_lines[0]}: 'end' must be the last event"]
    return []


def main(argv: list[str] | None = None) -> int:
    """Validate each manifest and print findings.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 when clean, 1 with findings, 2 on unreadable input.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="JSON event manifests")
    parser.add_argument("--max-event-bytes", type=int, default=_DEFAULT_MAX_EVENT_BYTES)
    parser.add_argument(
        "--allow-event",
        action="append",
        default=[],
        help="additional event name to accept; repeatable",
    )
    parser.add_argument(
        "--allow-open",
        action="store_true",
        help="accept recordings of interrupted connections without 'end'",
    )
    args = parser.parse_args(argv)
    allowed = DEFAULT_EVENTS | frozenset(args.allow_event)
    findings: list[str] = []
    for path in args.paths:
        try:
            items = items_with_lines(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            sys.stderr.write(f"{path}:1: cannot read events: {error}\n")
            return _EXIT_USAGE
        findings.extend(
            check_events(
                items,
                path=str(path),
                allowed=allowed,
                max_event_bytes=args.max_event_bytes,
                allow_open=args.allow_open,
            )
        )
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
