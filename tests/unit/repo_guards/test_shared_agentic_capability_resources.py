"""Agentic development skills, prompts and checkers behave as documented."""

from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import re
import runpy

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SHARED = _ROOT / "packages/shared/.apm"
_SKILLS = _SHARED / "skills"
_MEMORY = _SKILLS / "kit-project-memory"
_LOOP = _SKILLS / "kit-feedback-loop"
_DELIVERY = _SKILLS / "kit-subagent-delivery"
_CONTEXT = _SKILLS / "kit-context-engineering"
_NEW_SKILLS = (_MEMORY, _LOOP, _DELIVERY, _CONTEXT)
_PROMPTS = ("kit-hand-off", "kit-run-feedback-loop")
_MEMORY_CHECK = runpy.run_path(str(_MEMORY / "assets/check_memory_files.py"))
_HANDOFF_CHECK = runpy.run_path(str(_DELIVERY / "assets/check_handoff.py"))
_BUDGET_CHECK = runpy.run_path(str(_CONTEXT / "assets/check_context_budget.py"))
_LINK = re.compile(r"\]\(([^)\s#]+)")
_TODAY = "--today=2026-10-23"
_REVIEW_TODAY = datetime.now(tz=UTC).date()


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    metadata = yaml.safe_load(header)
    assert isinstance(metadata, dict)
    return {str(key): str(value) for key, value in metadata.items()}, body


# Skill structure


def _assert_review_date(text: str) -> None:
    match = re.search(
        r"^Reviewed: ([0-9]{4}-[0-9]{2}-[0-9]{2})\.(?:\s|$)", text, re.MULTILINE
    )
    assert match is not None, "missing ISO review date"
    assert date.fromisoformat(match[1]) <= _REVIEW_TODAY, "review date is in the future"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Reviewed: 2026-02-30.",
        "Reviewed: 20261028.",
        f"Reviewed: {(_REVIEW_TODAY + timedelta(days=1)).isoformat()}.",
    ],
)
def test_reference_review_date_rejects_missing_invalid_or_future_values(
    text: str,
) -> None:
    with pytest.raises((AssertionError, ValueError)):
        _assert_review_date(text)


def test_reference_review_date_accepts_a_completed_review() -> None:
    _assert_review_date("Reviewed: 2026-10-23.")
    _assert_review_date(f"Reviewed: {_REVIEW_TODAY.isoformat()}. Notes follow.")


@pytest.mark.parametrize(
    "relative",
    [
        "skills/kit-feedback-loop/SKILL.md",
        "skills/kit-feedback-loop/assets/rubric.md.template",
        "skills/kit-feedback-loop/assets/review-checklist.md.template",
        "skills/kit-feedback-loop/assets/iteration-log.md.template",
        "prompts/kit-run-feedback-loop.prompt.md",
    ],
)
def test_feedback_entrypoints_distinguish_completion_from_blocking(
    relative: str,
) -> None:
    """Keep the declared outcome vocabulary consistent, not certify model behavior."""
    text = (_SHARED / relative).read_text(encoding="utf-8")
    for outcome in ("ITERATE", "COMPLETE", "BLOCKED"):
        assert outcome in text, f"{relative}: missing {outcome}"


def test_feedback_facade_does_not_request_numerical_scoring() -> None:
    text = (_SHARED / "prompts/kit-run-feedback-loop.prompt.md").read_text(
        encoding="utf-8"
    )
    assert "score the change" not in text.casefold()


@pytest.mark.parametrize("skill", _NEW_SKILLS, ids=lambda path: path.name)
def test_skill_metadata_and_body_follow_the_contract(skill: Path) -> None:
    metadata, body = _frontmatter(skill / "SKILL.md")
    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == skill.name
    assert metadata["license"] == "MIT"
    assert metadata["description"].startswith("Use when")
    assert len(metadata["description"]) <= 350
    assert len(body.splitlines()) < 300
    assert "## Acceptance gates" in body
    assert re.search(r"^1\. ", body, re.MULTILINE)


@pytest.mark.parametrize("skill", _NEW_SKILLS, ids=lambda path: path.name)
def test_every_resource_is_linked_from_skill_and_cites_sources(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    linked = {(skill / target).resolve() for target in _LINK.findall(text)}
    resources = [
        path
        for folder in ("references", "assets")
        for path in (skill / folder).iterdir()
        if path.is_file() and path.suffix != ".pyc"
    ]
    assert resources
    assert {path.resolve() for path in resources} <= linked
    for reference in (skill / "references").glob("*.md"):
        content = reference.read_text(encoding="utf-8")
        assert "## Primary sources" in content, reference.name
        _assert_review_date(content)
        assert re.search(r"\]\(https://", content), reference.name


def test_portable_text_has_no_local_paths_or_pinned_models() -> None:
    files = [
        path
        for skill in _NEW_SKILLS
        for path in skill.rglob("*")
        if path.is_file() and path.suffix != ".pyc"
    ]
    files += [_SHARED / f"prompts/{name}.prompt.md" for name in _PROMPTS]
    files.append(_SHARED / "instructions/kit-prompt-files.instructions.md")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b[A-Za-z]:\\[A-Za-z]|/home/|/Users/", text), path.name
        assert not re.search(r"claude-[a-z]+-\d|gpt-\d", text), path.name


def test_prompt_files_instruction_is_narrow_and_short() -> None:
    path = _SHARED / "instructions/kit-prompt-files.instructions.md"
    metadata, body = _frontmatter(path)
    assert set(metadata) == {"description", "applyTo"}
    assert metadata["applyTo"] == (
        "**/*.prompt.md,**/*.instructions.md,**/SKILL.md,**/*.agent.md,"
        "**/AGENTS.md,**/CLAUDE.md"
    )
    assert ":" not in metadata["description"]
    bullets = [line for line in body.splitlines() if line.startswith("- ")]
    assert 4 <= len(bullets) <= 10
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 20


@pytest.mark.parametrize("name", _PROMPTS)
def test_prompts_follow_the_shared_prompt_format(name: str) -> None:
    path = _SHARED / f"prompts/{name}.prompt.md"
    raw = path.read_bytes()
    metadata, body = _frontmatter(path)
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert set(metadata) == {"description", "argument-hint", "agent"}
    assert 0 < len(metadata["description"]) <= 160
    assert metadata["agent"] in {"agent", "ask"}
    assert 25 <= len(raw.decode("utf-8").splitlines()) <= 80
    for section in ("## Input", "## Procedure", "## Acceptance gates", "## Output"):
        assert section in body
    assert "user-supplied argument" in body
    assert re.search(r"\]\(\.\./skills/kit-[a-z-]+/SKILL\.md\)", body)
    for target in _LINK.findall(body):
        if "://" not in target:
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), target
            assert resolved.is_relative_to(_SHARED.resolve()), target


# check_memory_files.py


def test_memory_checker_self_test_passes() -> None:
    assert _MEMORY_CHECK["self_test"]() == []


def test_memory_checker_accepts_filled_templates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lesson = (_MEMORY / "assets/lesson.md.template").read_text(encoding="utf-8")
    lesson = lesson.replace("YYYY-MM-DD", "2026-10-01").replace(
        "../path/to/evidence", "../src/app.py"
    )
    _write(tmp_path, "memories/lessons.md", lesson)
    _write(tmp_path, "src/app.py", "")
    record = (_MEMORY / "assets/adr.md.template").read_text(encoding="utf-8")
    _write(
        tmp_path,
        "docs/decisions/0001-use-events.md",
        record.replace("status: proposed", "status: accepted").replace(
            "YYYY-MM-DD", "2026-09-01"
        ),
    )
    readme = (_MEMORY / "assets/knowledge-base-README.md.template").read_text(
        encoding="utf-8"
    )
    _write(tmp_path, "docs/README.md", readme.split("## Topics")[0])
    paths = [str(tmp_path / "memories"), str(tmp_path / "docs")]
    assert _MEMORY_CHECK["main"]([*paths, f"--root={tmp_path}", _TODAY]) == 0
    assert "3 file(s) checked" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "## 2026-10-01 No evidence\n- Status: active\n",
            "is missing field 'Evidence'",
        ),
        (
            "## 2025-01-01 Old\n- Status: active\n- Evidence: a test\n",
            "was last verified 660 days ago (limit 180)",
        ),
        (
            "## 2026-12-01 Later\n- Status: active\n- Evidence: a test\n",
            "entry date 2026-12-01 is in the future",
        ),
        (
            "## 2026-10-01 Gone\n- Status: superseded\n- Evidence: a test\n",
            "superseded entry does not link its replacement",
        ),
        (
            "## 2026-10-01 Odd\n- Status: maybe\n- Evidence: a test\n",
            "entry status 'maybe' is not one of",
        ),
        (
            "## 2026-10-01 Linked\n- Status: active\n- Evidence: [x](missing.md)\n",
            "link 'missing.md' points to a missing file",
        ),
        (
            "## 2026-10-01 Escape\n- Status: active\n- Evidence: [x](../../out.md)\n",
            "link '../../out.md' leaves the checked root",
        ),
        (
            "## 2026-10-01 Fine\n- Status: active\n- Evidence: a test\n## Plain\n",
            "entry heading 'Plain' has no date",
        ),
        (
            "---\nstatus: superseded\ndate: 2026-01-01\n---\n# 0002 Old\n",
            "superseded record does not link its replacement",
        ),
        ("---\nstatus: accepted\n---\n# 0003 Undated\n", "is missing field 'date'"),
    ],
)
def test_memory_checker_reports_each_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, message: str
) -> None:
    path = _write(tmp_path, "memories/lessons.md", text)
    assert _MEMORY_CHECK["main"]([str(path), f"--root={tmp_path}", _TODAY]) == 1
    assert message in capsys.readouterr().out


def test_memory_checker_honors_verification_and_history(tmp_path: Path) -> None:
    text = (
        "## 2025-01-01 Re-checked\n- Status: active\n- Evidence: a test\n"
        "- Last verified: 2026-10-01\n"
        "## 2024-01-01 Replaced\n- Status: superseded\n- Evidence: a test\n"
        "- Superseded by: [check](lessons.md)\n"
    )
    path = _write(tmp_path, "memories/lessons.md", text)
    assert _MEMORY_CHECK["main"]([str(path), f"--root={tmp_path}", _TODAY]) == 0
    options = [str(path), f"--root={tmp_path}", _TODAY, "--require", "Owner"]
    assert _MEMORY_CHECK["main"](options) == 1


def test_memory_checker_rejects_bad_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _MEMORY_CHECK["main"]([str(tmp_path / "absent"), _TODAY]) == 2
    assert _MEMORY_CHECK["main"]([str(tmp_path), "--today=2026-13-01"]) == 2
    assert _MEMORY_CHECK["main"]([str(tmp_path), "--max-age-days=-1"]) == 2
    assert "not a YYYY-MM-DD date" in capsys.readouterr().err


# check_handoff.py


def test_handoff_checker_self_test_passes() -> None:
    assert _HANDOFF_CHECK["self_test"]() == []


def test_handoff_checker_rejects_unfilled_template_and_accepts_filled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = (_DELIVERY / "assets/handoff.md.template").read_text(encoding="utf-8")
    raw = _write(tmp_path, "raw.md", template)
    assert _HANDOFF_CHECK["main"]([str(raw)]) == 1
    assert "unfilled placeholder '<task id>'" in capsys.readouterr().out
    filled = _write(
        tmp_path,
        "filled.md",
        "# Handoff: T1 add retries\n\n- Status: done\n\n"
        "## Changed paths\n\n- `src/retry.py`: created\n\n"
        "## Evidence\n\n- `uv run pytest tests/unit/test_retry.py -q`: 4 passed\n"
        "- `uv run ruff check src`: All checks passed\n\n"
        "## Limitations\n\n- Not verified against the live service.\n",
    )
    assert _HANDOFF_CHECK["main"]([str(filled)]) == 0


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "## Evidence\n- `make test`: passed\n## Limitations\n- none\n",
            "'changed paths'",
        ),
        ("## Changed paths\n- a/b.py\n## Limitations\n- none\n", "'evidence'"),
        (
            "## Changed paths\n- a/b.py\n## Evidence\n- `make test`: ok\n",
            "'limitations'",
        ),
        (
            "## Changed paths\n- a/b.py\n## Evidence\n- ran tests\n## Limitations\n- none\n",
            "records no command in inline code",
        ),
        (
            "## Changed paths\n- a/b.py\n## Evidence\n- `make test`\n## Limitations\n- none\n",
            "command `make test` has no recorded result",
        ),
        (
            "## Changed paths\n- some edits\n## Evidence\n- `x`: ok\n## Limitations\n- none\n",
            "section 'changed paths' lists no path",
        ),
        (
            "## Changed paths\n- a/b.py\n## Evidence\n- `x`: ok\n## Limitations\n",
            "section 'limitations' is empty",
        ),
    ],
)
def test_handoff_checker_reports_each_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, message: str
) -> None:
    path = _write(tmp_path, "handoff.md", text)
    assert _HANDOFF_CHECK["main"]([str(path)]) == 1
    assert message in capsys.readouterr().out


def test_handoff_checker_accepts_numbered_and_table_handoffs(tmp_path: Path) -> None:
    numbered = _write(
        tmp_path,
        "numbered.md",
        "1. Changed and created paths: `pkg/a.py`, `tests/test_a.py`.\n"
        "2. Suggested remaps: none.\n"
        "3. Each verification command with its result:\n"
        "   - `uv run pytest tests/test_a.py -q`: 3 passed\n"
        "4. Limitations: no live host session was exercised.\n",
    )
    table = _write(
        tmp_path,
        "table.md",
        "## Changed files\n\n| Path | Change |\n| --- | --- |\n| `src/x.py` | modified |\n\n"
        "## Verification\n\n| Command | Exit | Result |\n| --- | --- | --- |\n"
        "| `task test` | 0 | |\n\n## Open items\n\n- None.\n"
        "<!-- <placeholder in a comment> -->\n",
    )
    assert _HANDOFF_CHECK["main"]([str(numbered), str(table)]) == 0


def test_handoff_checker_rejects_missing_file_and_no_arguments(tmp_path: Path) -> None:
    assert _HANDOFF_CHECK["main"]([str(tmp_path / "absent.md")]) == 2
    assert _HANDOFF_CHECK["main"]([]) == 2


# check_context_budget.py


def test_budget_checker_self_test_passes() -> None:
    assert _BUDGET_CHECK["self_test"]() == []


def _context_repo(root: Path) -> None:
    _write(root, "AGENTS.md", "a" * 100)
    _write(root, "CLAUDE.md", "@AGENTS.md\n@docs/style.md\n`@docs/ignored.md`\n")
    _write(root, "docs/style.md", "s" * 40 + "\n@nested.md\n")
    _write(root, "docs/nested.md", "n" * 10)
    _write(root, "docs/ignored.md", "i" * 999)
    _write(root, ".github/copilot-instructions.md", "c" * 20)
    _write(
        root, ".github/instructions/all.instructions.md", '---\napplyTo: "**"\n---\nx\n'
    )
    _write(
        root,
        ".github/instructions/py.instructions.md",
        '---\napplyTo: "**/*.py"\n---\nx\n',
    )
    _write(root, ".claude/rules/general.md", "# General\n")
    _write(root, ".claude/rules/api.md", '---\npaths:\n  - "src/api/**"\n---\nx\n')


def test_budget_checker_discovers_always_on_files_once(tmp_path: Path) -> None:
    _context_repo(tmp_path)
    files = _BUDGET_CHECK["discover"](
        tmp_path, instruction_dirs=[".github/instructions"], extras=[]
    )
    assert [(item.path, item.kind) for item in files] == [
        (".claude/rules/general.md", "rule"),
        (".github/copilot-instructions.md", "entry"),
        (".github/instructions/all.instructions.md", "instruction"),
        ("AGENTS.md", "entry"),
        ("CLAUDE.md", "entry"),
        ("docs/nested.md", "import"),
        ("docs/style.md", "import"),
    ]
    assert next(item for item in files if item.path == "AGENTS.md").chars == 100


def test_budget_checker_reports_limits_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _context_repo(tmp_path)
    root = f"--root={tmp_path}"
    assert _BUDGET_CHECK["main"]([root]) == 0
    assert "total" in capsys.readouterr().out
    assert _BUDGET_CHECK["main"]([root, "--max-file-chars=50"]) == 1
    output = capsys.readouterr().out
    assert "AGENTS.md:1: 100 characters exceeds the per-file limit of 50" in output
    assert _BUDGET_CHECK["main"]([root, "--max-total-chars=100", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] > 100
    assert payload["findings"][0].startswith("(total):1:")


def test_budget_checker_rejects_bad_arguments(tmp_path: Path) -> None:
    assert _BUDGET_CHECK["main"]([f"--root={tmp_path / 'absent'}"]) == 2
    assert _BUDGET_CHECK["main"]([f"--root={tmp_path}", "--max-file-chars=0"]) == 2
    extra = f"--extra={tmp_path / 'missing.md'}"
    assert _BUDGET_CHECK["main"]([f"--root={tmp_path}", extra]) == 2


@pytest.mark.parametrize("check", [_MEMORY_CHECK, _HANDOFF_CHECK])
@pytest.mark.parametrize("closer", ["-->", "--!>"])
def test_markdown_comments_end_at_either_html_closer(
    check: dict[str, object], closer: str
) -> None:
    """Text after an HTML comment closer is content, never silently hidden."""
    content_lines = check["content_lines"]
    assert callable(content_lines)
    single = content_lines(f"keep <!-- hidden {closer} after\n")
    multi = content_lines(f"<!--\nhidden\n{closer}\nvisible\n")

    assert single == [(1, "keep  after")]
    assert multi == [(1, ""), (4, "visible")]
