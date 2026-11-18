"""Regression coverage for opt-in, content-free console diagnostics."""

import json
import logging
import subprocess
import sys

import pytest

from platform_kit_runtime.logging import ConsoleFormatter

pytestmark = pytest.mark.unit

_TIMEOUT_SECONDS = 60


def test_console_configuration_is_opt_in_idempotent_and_uses_stdout() -> None:
    script = """
import json, logging, sys
before = tuple(logging.getLogger().handlers)
from platform_kit_runtime.logging import configure_console_logging
assert tuple(logging.getLogger().handlers) == before
configure_console_logging()
configure_console_logging()
logging.getLogger("app.service").info("credential-leak-sentinel")
logging.getLogger("uvicorn.access").info("credential-leak-sentinel")
logging.getLogger("httpx").info("credential-leak-sentinel")
logging.getLogger("vendor").warning("credential-leak-sentinel")
assert len(logging.getLogger("app").handlers) == 1
"""
    result = subprocess.run(  # noqa: S603 - fixed offline interpreter probe
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(event["logger"], event["level"]) for event in events] == [
        ("app.service", "INFO"),
        ("vendor", "WARNING"),
    ]
    assert {event["event"] for event in events} == {"application.log"}
    assert "credential-leak-sentinel" not in result.stdout


def test_console_discards_foreign_http_fields_and_nonfinite_values() -> None:
    record = logging.makeLogRecord(
        {
            "name": "vendor",
            "msg": "credential-leak-sentinel",
            "event": "https://private.invalid/credential-leak-sentinel",
            "http_route": "/credential-leak-sentinel",
            "duration_ms": float("nan"),
        }
    )
    output = ConsoleFormatter().format(record)
    assert json.loads(output)["event"] == "unknown"
    assert "credential-leak-sentinel" not in output
    assert "duration_ms" not in json.loads(output)
