"""Real console process boundary: module entry point, exit codes, and JSON output."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import apm_smoke

import agent_kit.infrastructure.apm_adapter as apm_module
from agent_kit.infrastructure.apm_adapter import ApmCliAdapter, ApmExitError

_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("returncode", [0, 9])
def test_apm_output_is_independent_of_the_windows_console_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returncode: int
) -> None:
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp1252")
    program = (
        "import sys; payload='\\u2510'.encode('utf-8')*65536; "
        "sys.stdout.buffer.write(payload); sys.stdout.buffer.flush(); "
        "sys.stderr.buffer.write(payload); sys.stderr.buffer.flush(); "
        f"sys.exit({returncode})"
    )
    monkeypatch.setattr(apm_module, "pinned_apm_executable", lambda: sys.executable)
    monkeypatch.setattr(
        apm_module,
        "_commands",
        lambda executable: (("audit", [executable, "-c", program]),),
    )
    if returncode:
        with pytest.raises(ApmExitError, match="exit code 9"):
            ApmCliAdapter(timeout_seconds=10).check(tmp_path)
        with pytest.raises(SystemExit) as error:
            apm_smoke.run(
                [sys.executable, "-c", program],
                cwd=tmp_path,
                env=os.environ.copy(),
            )
        assert error.value.code == returncode
    else:
        ApmCliAdapter(timeout_seconds=10).check(tmp_path)
        apm_smoke.run(
            [sys.executable, "-c", program], cwd=tmp_path, env=os.environ.copy()
        )


def _run(*arguments: str, cwd: Path = _ROOT) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(  # noqa: S603 - fixed interpreter and argv
        [sys.executable, "-m", "agent_kit", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def test_module_help_exits_zero_and_lists_commands() -> None:
    """The documented commands are discoverable from the module entry point."""
    result = _run("--help")

    assert result.returncode == 0, result.stderr
    for command in ("check", "compose", "provenance", "apm-check", "context"):
        assert command in result.stdout


def test_repository_catalog_is_valid_as_json() -> None:
    """The checked-out source validates and reports every declared profile."""
    result = _run("check", "--root", str(_ROOT), "--json")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    catalog = json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))
    assert report["valid"] is True
    assert report["version"] == catalog["version"]
    assert set(report["profiles"]) == set(catalog["profiles"])


def test_invalid_root_exits_nonzero_without_traceback(tmp_path: Path) -> None:
    """A directory without a catalog fails with diagnostics, not a crash."""
    result = _run("check", "--root", str(tmp_path))

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.strip()


def test_session_hook_reads_stdin_and_emits_advisory_json(tmp_path: Path) -> None:
    """The context command is a well-formed SessionStart hook response."""
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-m", "agent_kit", "context"],
        input=json.dumps({"cwd": str(tmp_path)}),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    assert "Missing agent context files" in output["additionalContext"]


@pytest.mark.parametrize("profile", ["shared", "backend", "fullstack"])
def test_compose_then_provenance_round_trip(tmp_path: Path, profile: str) -> None:
    """A real composition verifies, and tampering is detected by the CLI."""
    output = tmp_path / profile

    composed = _run("compose", profile, "--root", str(_ROOT), "--output", str(output))
    assert composed.returncode == 0, composed.stderr
    verified = _run("provenance", "--root", str(output))
    assert verified.returncode == 0, verified.stderr

    (output / "apm.yml").write_bytes((output / "apm.yml").read_bytes() + b"\n")
    tampered = _run("provenance", "--root", str(output))
    assert tampered.returncode == 1
    assert "provenance.drift" in tampered.stderr
