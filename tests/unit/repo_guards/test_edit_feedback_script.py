"""Contracts for the advisory post-edit feedback hook."""

import io
import json
from pathlib import Path, PurePosixPath

import pytest
from scripts.checks.conventions import file_options

from scripts import edit_feedback

_ROOT = Path(__file__).resolve().parents[3]
_CLEAN = '"""Clean module."""\n'
_SECTIONED = (
    '"""Module."""\n\n\n'
    "def parse(value: object) -> str:\n"
    '    """Parse a value.\n\n'
    "    Args:\n"
    "        value: Untrusted input.\n\n"
    "    Returns:\n"
    "        The text.\n"
    '    """\n'
    "    return str(value)\n"
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"tool_input": {"file_path": "/repo/a.py"}}, "/repo/a.py"),
        ({"toolArgs": {"path": "a.py"}, "cwd": "/repo"}, "/repo/a.py"),
        ({"toolArgs": json.dumps({"filePath": "/repo/b.py"})}, "/repo/b.py"),
    ],
)
def test_edited_file_reads_each_host_payload_shape(
    payload: dict[str, object], expected: str
) -> None:
    path = edit_feedback.edited_file(payload)

    assert path is not None
    assert path.as_posix().endswith(expected)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"toolArgs": "{"},
        {"toolArgs": ["a.py"]},
        {"tool_input": {"command": "ls"}},
        {"tool_input": {"file_path": ""}},
        {"tool_input": {"file_path": 3}},
    ],
)
def test_edited_file_ignores_payloads_without_a_file(payload: object) -> None:
    assert edit_feedback.edited_file(payload) is None


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("tests/unit/test_x.py", ()),
        ("src/agent_kit/core/x.py", ("--magic-numbers", "--docstrings")),
        ("scripts/x.py", ("--magic-numbers", "--docstrings")),
        ("packages/a/.apm/skills/s/assets/x.py", ("--magic-numbers", "--docstrings")),
        (
            "packages/a/.apm/skills/s/assets/x.py.template",
            ("--templates", "--magic-numbers", "--docstrings"),
        ),
        ("noxfile.py", None),
    ],
)
def test_file_options_match_the_conventions_gate_scope(
    relative: str, expected: tuple[str, ...] | None
) -> None:
    assert file_options(PurePosixPath(relative)) == expected


def test_findings_skip_files_outside_the_root_or_not_python(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text(_SECTIONED, encoding="utf-8")
    notes = root / "scripts" / "notes.md"
    notes.write_text("# Notes\n", encoding="utf-8")

    assert edit_feedback.findings(outside, root=root) == ""
    assert edit_feedback.findings(notes, root=root) == ""
    assert edit_feedback.findings(root / "scripts" / "absent.py", root=root) == ""


def test_findings_report_convention_violations_and_pass_clean_files(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "scripts" / "probe.py"
    probe.parent.mkdir()
    probe.write_text(_SECTIONED, encoding="utf-8")
    report = edit_feedback.findings(probe, root=tmp_path)
    probe.write_text(_CLEAN, encoding="utf-8")

    assert "one-line summary" in report
    assert edit_feedback.findings(probe, root=tmp_path) == ""


def test_claude_response_uses_hook_specific_output() -> None:
    response = edit_feedback.response("finding", host=edit_feedback.Host.CLAUDE)

    assert response == {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "Fix these findings in the file you just edited:\nfinding"
            ),
        }
    }


def test_copilot_response_truncates_long_reports() -> None:
    response = edit_feedback.response("x" * 10_000, host=edit_feedback.Host.COPILOT)

    context = response["additionalContext"]
    assert isinstance(context, str)
    assert context.endswith("[findings truncated]")
    assert len(context) < 5_000


def test_main_is_silent_for_clean_or_unrelated_edits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_input": {"file_path": str(_ROOT / "README.md")}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert edit_feedback.main(["claude"]) == 0
    assert capsys.readouterr().out == ""


def test_main_emits_findings_for_the_named_host(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(edit_feedback, "findings", lambda path: f"{path.name}:1: x")
    payload = {"toolArgs": {"path": "a.py"}, "cwd": str(_ROOT)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert edit_feedback.main(["copilot"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["additionalContext"].endswith("a.py:1: x")


@pytest.mark.parametrize(
    "raw",
    ["{", "x" * (edit_feedback._MAX_INPUT_CHARS + 1)],
    ids=["malformed", "oversized"],
)
def test_main_rejects_unusable_input_without_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], raw: str
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))

    assert edit_feedback.main(["claude"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "edit feedback" in captured.err
