"""Real subprocess boundaries for APM and repository maintainer scripts."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from scripts import apm_smoke

import agent_kit.infrastructure.apm_adapter as apm_module
from agent_kit.infrastructure.apm_adapter import ApmCliAdapter, ApmExitError

_ROOT = Path(__file__).resolve().parents[2]
# Cold Windows runners and synced folders need minutes, not seconds, for source checks.
_PROCESS_TIMEOUT_SECONDS = 300


def test_smoke_failure_names_the_command_even_without_vendor_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        apm_smoke.run(
            [sys.executable, "-c", "raise SystemExit(7)"],
            cwd=tmp_path,
            env=os.environ.copy(),
        )

    assert error.value.code == 7
    assert "Failed (exit 7): -c raise SystemExit(7)" in capsys.readouterr().err


def test_smoke_streams_output_and_closes_interactive_input(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    apm_smoke.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; print('visible progress', flush=True); "
                "assert sys.stdin.read() == ''"
            ),
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
    )
    output = capfd.readouterr().out
    assert output.index("Running (limit") < output.index("visible progress")
    assert output.index("visible progress") < output.index("Passed (")


def test_smoke_timeout_terminates_the_launcher_and_its_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_pid = tmp_path / "child.pid"
    child = (
        "import os,time; from pathlib import Path; "
        f"Path({str(child_pid)!r}).write_text(str(os.getpid())); time.sleep(300)"
    )
    parent = (
        "import subprocess,sys; "
        f"subprocess.run([sys.executable, '-c', {child!r}], check=True)"
    )
    command = [sys.executable, "-c", parent]
    original_wait = subprocess.Popen.wait

    def wait_when_ready(
        process: subprocess.Popen[bytes], timeout: float | None = None
    ) -> int:
        if process.args == command and timeout == 3:
            ready_deadline = time.monotonic() + 30
            while not child_pid.exists():
                if process.poll() is not None or time.monotonic() >= ready_deadline:
                    apm_smoke._stop_process_tree(process)
                    pytest.fail("Fixture child did not become ready within 30 seconds")
                time.sleep(0.05)
        return original_wait(process, timeout=timeout)

    # Exercise descendant cleanup, rather than a race with cold interpreter startup.
    monkeypatch.setattr(subprocess.Popen, "wait", wait_when_ready)
    started = time.monotonic()
    with pytest.raises(SystemExit, match="Timed out after 3s") as error:
        apm_smoke.run(
            command,
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_seconds=3,
        )
    assert isinstance(error.value.__cause__, subprocess.TimeoutExpired)
    assert time.monotonic() - started < 75
    pid = int(child_pid.read_text())
    if sys.platform == "win32":
        result = subprocess.run(  # noqa: S603 - fixed system executable, fixture PID
            [
                str(
                    Path(os.environ["SYSTEMROOT"])
                    / "System32/WindowsPowerShell/v1.0/powershell.exe"
                ),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) "
                    "{ exit 1 }"
                ),
            ],
            check=False,
            timeout=10,
        )
        assert result.returncode == 0
    else:
        # A reparented zombie is terminated too; Linux may retain it until reaped.
        status = Path(f"/proc/{pid}/stat")
        assert not status.exists() or status.read_text().split()[2] == "Z"


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
        "check_commands",
        lambda executable: (("audit", [executable, "-c", program]),),
    )
    if returncode:
        with pytest.raises(ApmExitError, match="exit code 9"):
            ApmCliAdapter(timeout_seconds=_PROCESS_TIMEOUT_SECONDS).check(tmp_path)
        with pytest.raises(SystemExit) as error:
            apm_smoke.run(
                [sys.executable, "-c", program],
                cwd=tmp_path,
                env=os.environ.copy(),
            )
        assert error.value.code == returncode
    else:
        ApmCliAdapter(timeout_seconds=_PROCESS_TIMEOUT_SECONDS).check(tmp_path)
        apm_smoke.run(
            [sys.executable, "-c", program], cwd=tmp_path, env=os.environ.copy()
        )


def _run_script(
    script: str, *arguments: str, cwd: Path
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(  # noqa: S603 - repository-owned script and fixed interpreter
        [sys.executable, str(_ROOT / "scripts" / script), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_PROCESS_TIMEOUT_SECONDS,
        check=False,
    )


def test_source_check_script_runs_outside_checkout_and_reports_json(
    tmp_path: Path,
) -> None:
    """Source validation remains usable as repository-local maintainer tooling."""
    result = _run_script(
        "check_source.py",
        "--root",
        str(_ROOT),
        "--json",
        cwd=tmp_path,
    )
    report = json.loads(result.stdout)
    catalog = json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))

    assert result.returncode == 0, result.stderr
    assert report["valid"] is True
    assert report["version"] == catalog["version"]
    assert set(report["profiles"]) == set(catalog["profiles"])


def test_session_hook_script_reads_stdin_and_emits_advisory_json(
    tmp_path: Path,
) -> None:
    """The standalone hook adapter emits a valid native SessionStart response."""
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [sys.executable, str(_ROOT / "scripts" / "session_context.py")],
        input=json.dumps({"cwd": str(tmp_path)}),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_PROCESS_TIMEOUT_SECONDS,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    assert "Missing agent context files" in output["additionalContext"]


def test_module_execution_no_longer_exposes_the_public_cli() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "agent_kit"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_PROCESS_TIMEOUT_SECONDS,
        check=False,
    )

    assert result.returncode != 0
    assert "agent_kit.__main__" in result.stderr
