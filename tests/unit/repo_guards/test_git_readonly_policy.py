"""Literal-input regressions for the opt-in consumer Git guard policy."""

import io
import json
from pathlib import Path
import runpy

import pytest

_ASSETS = (
    Path(__file__).resolve().parents[3]
    / "packages/shared/.apm/skills/kit-agent-runtime/assets"
)
_GUARD = runpy.run_path(str(_ASSETS / "tool_guard.py"))
_POLICY = _ASSETS / "git_readonly_policy.json.template"


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
    assert len(policy.rules) == 8


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
