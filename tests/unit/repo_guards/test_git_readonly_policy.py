"""Regressions for the Git guard policy delivered with the shared hook."""

from collections.abc import Mapping
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "packages/shared/.apm/hooks/scripts"
_GUARD = runpy.run_path(str(_SCRIPTS / "tool_guard.py"))
_POLICY = _SCRIPTS / "git-guard.policy"
_KIT = "AGENT_KIT_DIR"


@pytest.mark.parametrize(
    "command",
    [
        "git diff",
        "git.exe diff --stat",
        "git --no-pager diff --stat",
        "git --no-optional-locks status --short",
        "git log --oneline -5",
        "git show HEAD",
        "git blame src/example.py",
        "git ls-files",
        "git rev-parse HEAD",
        "gh pr view 1",
        "gh.exe pr view 1",
        "gh run list",
        "python -m pytest",
    ],
)
def test_inspection_does_not_override_native_permission_flow(command: str) -> None:
    """Unmatched calls are not affirmative hook grants."""
    policy = _GUARD["load_policy"](_POLICY)
    call = _GUARD["ToolCall"](tool_name="Bash", commands=(command,), paths=())
    decision = _GUARD["evaluate"](policy, call)

    assert decision.decision == "allow"
    assert _GUARD["render"](decision, "claude") is None


@pytest.mark.parametrize(
    "command",
    [
        "git add .",
        "git commit -m fix",
        "git push",
        "git fetch",
        "git pull --ff-only",
        "git switch -c fix/example",
        "git update-index --add example.py",
        "git -C ../agent-kit add .",
        "git.exe add .",
        'g"i"t add .',
        "git diff-custom",
        "git show-custom HEAD",
        "git diff.exe",
        "git diff --output=changes.patch",
        "git diff --out=changes.patch",
        "git diff -ochanges.patch",
        "git diff --ext-diff",
        "git show --textconv HEAD",
        "git diff > changes.patch",
        "git diff && git add .",
        "git status; git commit -m fix",
        "git status\n git add .",
        "gh api repos/example/project/git/refs",
        "gh pr create --fill",
        "gh pr view-custom 1",
        "gh pr merge --auto",
        "gh release create v1",
        "python -c \"open('.git/index', 'w').write('replacement')\"",
        "Set-Content .git\\config replacement",
    ],
)
def test_git_changes_are_denied_in_both_shell_payloads(command: str) -> None:
    """Git mutations have no approval fallback in the consumer policy."""
    policy = _GUARD["load_policy"](_POLICY)
    for tool in ("Bash", "powershell"):
        call = _GUARD["ToolCall"](tool_name=tool, commands=(command,), paths=())
        assert _GUARD["evaluate"](policy, call).decision == "deny"


@pytest.mark.parametrize(
    ("tool", "path"),
    [
        ("Edit", "project/.git/index"),
        ("apply_patch", "project/.git/refs/heads/main"),
        ("Write", "project/.github/hooks/guard.json"),
        ("edit", "project/.agents/hooks/tool_guard.py"),
        ("create", "project/.claude/settings.json"),
    ],
)
def test_file_tools_cannot_change_git_metadata_or_the_guard(
    tool: str, path: str
) -> None:
    """File-edit tools must not bypass the shell restriction."""
    policy = _GUARD["load_policy"](_POLICY)
    call = _GUARD["ToolCall"](tool_name=tool, commands=(), paths=(path,))

    assert _GUARD["evaluate"](policy, call).decision == "deny"


@pytest.mark.parametrize("runtime", ["claude", "copilot-cli", "vscode"])
def test_git_denials_use_the_existing_native_hook_protocol(runtime: str) -> None:
    """A denial is returned in the selected runtime's decision JSON."""
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "git add ."}}
    ).encode()
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = _GUARD["run_hook"](
        policy_path=_POLICY,
        runtime=runtime,
        fail_mode="closed",
        audit_log=None,
        stdin=io.BytesIO(payload),
        stdout=stdout,
        stderr=stderr,
    )
    output = json.loads(stdout.getvalue())
    body = output if runtime == "copilot-cli" else output["hookSpecificOutput"]

    assert code == 0
    assert body["permissionDecision"] == "deny"
    assert stderr.getvalue() == ""


def test_policy_is_a_separate_fail_closed_enforcement_layer() -> None:
    """The stricter Git policy augments, rather than replaces, baseline rules."""
    policy = _GUARD["load_policy"](_POLICY)

    assert policy.fail_mode == "closed"
    assert policy.mode == "enforce"
    assert len(policy.rules) == 25


def _decide(command: str, *, cwd: str, kit: str | None) -> str:
    policy = _GUARD["load_policy"](_POLICY)
    call = _GUARD["ToolCall"](tool_name="Bash", commands=(command,), paths=(), cwd=cwd)
    environ = {} if kit is None else {_KIT: kit}
    return _GUARD["evaluate"](policy, call, environ).decision


@pytest.mark.parametrize(
    "command",
    [
        "git add .",
        "git commit -m fix",
        "git switch x",
        "git fetch origin",
        "git pull --ff-only",
        "git push origin feature/example",
    ],
)
def test_kit_checkout_may_stage_and_commit(command: str, tmp_path: Path) -> None:
    """Scoped commands pass to native approval, not affirmative hook grants."""
    kit = tmp_path / "kit"
    (kit / "src").mkdir(parents=True)

    assert _decide(command, cwd=str(kit / "src"), kit=str(kit)) == "allow"


@pytest.mark.parametrize("command", ["git add .", "git commit -m fix"])
def test_other_checkouts_stay_read_only(command: str, tmp_path: Path) -> None:
    """Outside the kit checkout, or with no registration, commits are denied."""
    kit = tmp_path / "kit"
    other = tmp_path / "other"
    kit.mkdir()
    other.mkdir()

    assert _decide(command, cwd=str(other), kit=str(kit)) == "deny"
    assert _decide(command, cwd=str(kit), kit=None) == "deny"
    assert _decide(command, cwd=str(kit), kit="") == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push origin main",
        "git push origin master",
        "git push origin HEAD",
        "git push origin feature/x:main",
        "git push origin feature/x --force",
        "git push --force-with-lease origin feature/x",
        "git push origin +feature/x",
        "git push origin :feature/x",
        "git push origin --delete feature/x",
        "git push origin --all",
        "git push origin --tags",
        "git push origin feature/x --no-verify",
        "git reset --hard",
        "git tag v1",
        "git commit --no-verify -m x",
        "git commit -n -m x",
        "git commit -an -m x",
        "git commit --no-ver -m x",
        "git commit --no-v",
        "git add . && git push",
    ],
)
def test_kit_checkout_never_publishes_or_skips_hooks(
    command: str, tmp_path: Path
) -> None:
    """Pushing, rewriting history and bypassing hooks stay operator decisions."""
    assert _decide(command, cwd=str(tmp_path), kit=str(tmp_path)) == "deny"


def test_hook_bypass_is_denied_everywhere(tmp_path: Path) -> None:
    """The bypass rule has no scope, so it applies outside the kit too."""
    assert _decide("git commit --no-verify", cwd=str(tmp_path), kit=None) == "deny"


@pytest.mark.parametrize("tool", ["edit", "create", "apply_patch"])
def test_guard_files_are_read_only_outside_the_kit(tool: str, tmp_path: Path) -> None:
    """An installed guard cannot be edited by the agent it restrains."""
    policy = _GUARD["load_policy"](_POLICY)
    path = ".github/hooks/scripts/shared/scripts/tool_guard.py"
    call = _GUARD["ToolCall"](
        tool_name=tool, commands=(), paths=(path,), cwd=str(tmp_path)
    )

    assert _GUARD["evaluate"](policy, call, {}).decision == "deny"


def _launch(
    payload: Mapping[str, object], kit: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(_SCRIPTS / "git_guard.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={_KIT: str(kit), "PATH": ""},
    )


@pytest.mark.parametrize(
    ("command", "denied"),
    [
        ("git status", False),
        ("git fetch origin", False),
        ("git push origin feature/example", False),
        ("git push", True),
        ("git commit --no-verify", True),
        ("pip install sample", True),
    ],
)
def test_launcher_applies_the_policy_beside_it(
    command: str, denied: bool, tmp_path: Path
) -> None:
    """The registered launcher finds its policy without any argument."""
    payload = {
        "toolName": "bash",
        "toolArgs": json.dumps({"command": command}),
        "cwd": str(tmp_path),
    }
    result = _launch(payload, tmp_path)

    assert result.returncode == 0
    assert ("permissionDecision" in result.stdout) is denied


def test_launcher_blocks_unreadable_input(tmp_path: Path) -> None:
    """A malformed payload fails closed instead of allowing the call."""
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(_SCRIPTS / "git_guard.py")],
        input="{",
        capture_output=True,
        text=True,
        check=False,
        env={_KIT: str(tmp_path), "PATH": ""},
    )

    assert result.returncode != 0


@pytest.mark.parametrize("payload", [b"{", b"[]", b'{"tool_name": false}'])
def test_unreadable_hook_inputs_block_instead_of_granting_access(
    payload: bytes,
) -> None:
    """Malformed inputs produce a blocking status, not an empty success."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = _GUARD["run_hook"](
        policy_path=_POLICY,
        runtime="claude",
        fail_mode="closed",
        audit_log=None,
        stdin=io.BytesIO(payload),
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 2
    assert stdout.getvalue() == ""
    assert "blocked" in stderr.getvalue()


def test_missing_git_policy_is_not_a_successful_enforcement_run(
    tmp_path: Path,
) -> None:
    """A missing policy must fail even before a tool input is evaluated."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = _GUARD["run_hook"](
        policy_path=tmp_path / "missing.json",
        runtime="claude",
        fail_mode="closed",
        audit_log=None,
        stdin=io.BytesIO(b"{}"),
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 2
    assert stdout.getvalue() == ""
    assert "blocked" in stderr.getvalue()
