"""Small stdlib JSON formatter: identifiers, not messages or request content."""

import json
import logging
import math
import re
from typing import Protocol, runtime_checkable

_MAX_IDENTIFIER_LENGTH = 160
_MAX_TRACEBACK_FRAMES = 16
_IDENTIFIER = re.compile(rf"[A-Za-z0-9_.<>-]{{1,{_MAX_IDENTIFIER_LENGTH}}}")
_PROBLEM_INSTANCE = re.compile(r"urn:uuid:[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_HTTP_FIELDS = ("http_method", "http_route", "http_status", "duration_ms")
_PROBLEM_FIELDS = ("problem_code", "failure_reason")


@runtime_checkable
class _ConfigurationDiagnostic(Protocol):
    """Structural, value-free configuration diagnostics supplied by consumers."""

    @property
    def fields(self) -> tuple[str, ...]:
        """Declared environment field identifiers."""
        ...

    @property
    def cause_type(self) -> str:
        """Parser exception class name, not its message."""
        ...


class ConsoleFormatter(logging.Formatter):
    """Serialize runtime-owned fields and bounded, content-free error attribution.

    Messages, exception text, source paths, source lines and locals are omitted.
    Configuration exceptions may expose ``fields`` and ``cause_type`` identifiers.
    HTTP metadata is accepted only from the runtime's structured event producers.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Return one JSON event without raw messages, URLs or exception content."""
        payload: dict[str, object] = {
            "level": record.levelname,
            "event": _identifier(vars(record).get("event", "application.log")),
            "logger": _identifier(record.name),
            "module": _identifier(record.module),
            "function": _identifier(record.funcName),
            "line": record.lineno,
        }
        for field in ("request_id", "trace_id"):
            value = vars(record).get(field)
            if value is not None:
                payload[field] = _identifier(value)
        if record.name.startswith("platform_kit_runtime."):
            payload.update(_runtime_fields(record))
        payload.update(_exception_fields(record))
        return json.dumps(payload, ensure_ascii=True, allow_nan=False)


def _identifier(value: object) -> str:
    return (
        value if isinstance(value, str) and _IDENTIFIER.fullmatch(value) else "unknown"
    )


def _runtime_fields(record: logging.LogRecord) -> dict[str, object]:
    fields: dict[str, object] = {}
    for field in _HTTP_FIELDS:
        value = vars(record).get(field)
        if _finite_scalar(value):
            fields[field] = value
    for field in _PROBLEM_FIELDS:
        if field in vars(record):
            fields[field] = _identifier(vars(record)[field])
    instance = vars(record).get("instance")
    if isinstance(instance, str):
        fields["instance"] = (
            instance if _PROBLEM_INSTANCE.fullmatch(instance) else "unknown"
        )
    return fields


def _finite_scalar(value: object) -> bool:
    return (
        math.isfinite(value)
        if isinstance(value, float)
        else isinstance(value, (str, int))
    )


def _exception_fields(record: logging.LogRecord) -> dict[str, object]:
    if record.exc_info is None:
        return {}
    _, error, traceback = record.exc_info
    if error is None:
        return {}
    frames: list[dict[str, str | int]] = []
    while traceback is not None and len(frames) < _MAX_TRACEBACK_FRAMES:
        frame = traceback.tb_frame
        frames.append(
            {
                "module": _identifier(frame.f_globals.get("__name__")),
                "function": _identifier(frame.f_code.co_name),
                "line": traceback.tb_lineno,
            }
        )
        traceback = traceback.tb_next
    fields: dict[str, object] = {
        "exception_type": _identifier(
            f"{type(error).__module__}.{type(error).__qualname__}"
        ),
        "exception_frames": frames,
    }
    if isinstance(error, _ConfigurationDiagnostic):
        fields["configuration_fields"] = tuple(map(_identifier, error.fields))
        fields["configuration_cause_type"] = _identifier(error.cause_type)
    return fields
