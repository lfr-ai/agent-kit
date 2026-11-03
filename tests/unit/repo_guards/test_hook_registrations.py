"""Delivery contracts for hook registrations shipped by the shared package."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

_HOOKS = Path(__file__).resolve().parents[3] / "packages/shared/.apm/hooks"
_SCRIPTS = _HOOKS / "scripts"
_REGISTRATIONS = sorted(_HOOKS.glob("*.json"))
_COPILOT_DEFAULT_TIMEOUT_SECONDS = 30
_PRE_TOOL_BUDGET_SECONDS = 10
_BLOCK_EXIT = 2


def _entries(registration: Path) -> list[dict[str, object]]:
    data = json.loads(registration.read_text(encoding="utf-8"))
    return [entry for event in data["hooks"].values() for entry in event]


def test_registrations_exist() -> None:
    assert [path.name for path in _REGISTRATIONS] == ["git-guard.json"]


@pytest.mark.parametrize("registration", _REGISTRATIONS, ids=lambda path: path.name)
def test_registration_uses_the_copilot_schema_version(registration: Path) -> None:
    data = json.loads(registration.read_text(encoding="utf-8"))

    assert data["version"] == 1
    assert set(data["hooks"]) == {"preToolUse"}


@pytest.mark.parametrize("registration", _REGISTRATIONS, ids=lambda path: path.name)
def test_every_entry_names_both_shells(registration: Path) -> None:
    """Windows hosts read ``powershell``; Linux hosts and the cloud agent read ``bash``."""
    for entry in _entries(registration):
        assert entry["type"] == "command"
        assert str(entry["bash"]).startswith("python3 ./scripts/")
        assert str(entry["powershell"]).startswith("python ./scripts/")
        assert (
            str(entry["bash"]).split("/")[-1] == str(entry["powershell"]).split("/")[-1]
        )


@pytest.mark.parametrize("registration", _REGISTRATIONS, ids=lambda path: path.name)
def test_timeouts_are_explicit_and_below_the_host_default(registration: Path) -> None:
    """A timed-out command hook fails open, so the budget stays small and explicit."""
    for entry in _entries(registration):
        timeout = entry["timeoutSec"]
        assert type(timeout) is int
        assert (
            1 <= timeout <= _PRE_TOOL_BUDGET_SECONDS < _COPILOT_DEFAULT_TIMEOUT_SECONDS
        )


@pytest.mark.parametrize("registration", _REGISTRATIONS, ids=lambda path: path.name)
def test_commands_are_relative_so_the_installer_can_root_them(
    registration: Path,
) -> None:
    """APM rewrites ``./scripts/...`` to the deployed hook directory per host."""
    for entry in _entries(registration):
        for key in ("bash", "powershell"):
            command = str(entry[key])
            assert " ./scripts/" in command
            assert not Path(command.rsplit(maxsplit=1)[-1]).is_absolute()
            assert "cwd" not in entry
            assert ".." not in command


@pytest.mark.parametrize("registration", _REGISTRATIONS, ids=lambda path: path.name)
def test_registered_scripts_and_their_policy_ship_together(registration: Path) -> None:
    for entry in _entries(registration):
        script = _SCRIPTS / str(entry["bash"]).rsplit("/", 1)[-1]
        assert script.is_file()
    assert (_SCRIPTS / "git-guard.policy").is_file()


def test_policy_enforces_and_fails_closed() -> None:
    policy = json.loads((_SCRIPTS / "git-guard.policy").read_text(encoding="utf-8"))

    assert policy["mode"] == "enforce"
    assert policy["fail_mode"] == "closed"


def _run_launcher(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and copied repository script
        [sys.executable, str(directory / "git_guard.py")],
        input="{}",
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": ""},
    )


def test_launcher_blocks_when_the_engine_is_missing(tmp_path: Path) -> None:
    """A traceback exits 1, which Claude Code treats as a non-blocking error."""
    shutil.copy(_SCRIPTS / "git_guard.py", tmp_path / "git_guard.py")

    result = _run_launcher(tmp_path)

    assert result.returncode == _BLOCK_EXIT
    assert "blocked" in result.stderr
    assert result.stdout == ""


def test_launcher_blocks_when_the_engine_is_broken(tmp_path: Path) -> None:
    shutil.copy(_SCRIPTS / "git_guard.py", tmp_path / "git_guard.py")
    (tmp_path / "tool_guard.py").write_text("def broken(:\n", encoding="utf-8")

    result = _run_launcher(tmp_path)

    assert result.returncode == _BLOCK_EXIT
    assert "blocked" in result.stderr
