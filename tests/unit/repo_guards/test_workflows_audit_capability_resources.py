"""Codebase audit and modernization resources behave as their skills document."""

import json
from pathlib import Path
import re
import runpy
import tomllib

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = _ROOT / "packages/workflows/.apm"
_AUDIT = _PACKAGE / "skills/kit-codebase-audit"
_MODERNIZE = _PACKAGE / "skills/kit-modernize"
_SUMMARIZER = runpy.run_path(str(_AUDIT / "assets/summarize_findings.py"))
_LEGACY = runpy.run_path(str(_MODERNIZE / "assets/check_legacy_syntax.py"))
_LINK = re.compile(r"\]\(([^)#\s]+)")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _json(path: Path, payload: object) -> Path:
    return _write(path, json.dumps(payload))


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, header, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(header)
    assert isinstance(loaded, dict)
    return loaded


# Skill and prompt structure


@pytest.mark.parametrize("skill", [_AUDIT, _MODERNIZE])
def test_skill_metadata_and_every_resource_is_linked(skill: Path) -> None:
    meta = _frontmatter(skill / "SKILL.md")
    assert set(meta) == {"name", "description", "license"}
    assert meta["name"] == skill.name
    assert meta["license"] == "MIT"
    description = meta["description"]
    assert isinstance(description, str)
    assert description.startswith("Use when")
    assert len(description) <= 110
    body = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "## Acceptance gates" in body
    assert len(body.splitlines()) < 300
    linked = {(skill / target).resolve() for target in _LINK.findall(body)}
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (skill / folder).iterdir()
    }
    assert resources <= linked
    assert all(path.is_file() for path in linked)


@pytest.mark.parametrize("skill", [_AUDIT, _MODERNIZE])
def test_references_cite_primary_sources_with_review_date(skill: Path) -> None:
    guide = (skill / "references/guide.md").read_text(encoding="utf-8")
    assert "## Primary sources" in guide
    assert "2026-10-23" in guide
    for reference in (skill / "references").glob("*.md"):
        for target in _LINK.findall(reference.read_text(encoding="utf-8")):
            if ":" not in target:
                assert (reference.parent / target).is_file(), target


@pytest.mark.parametrize(
    ("prompt", "skill"),
    [
        ("kit-audit-codebase.prompt.md", "kit-codebase-audit"),
        ("kit-modernize.prompt.md", "kit-modernize"),
    ],
)
def test_prompts_follow_format_and_load_their_skill(prompt: str, skill: str) -> None:
    path = _PACKAGE / "prompts" / prompt
    meta = _frontmatter(path)
    assert set(meta) == {"description", "argument-hint", "agent"}
    text = path.read_text(encoding="utf-8")
    for heading in ("## Input", "## Procedure", "## Acceptance gates", "## Output"):
        assert heading in text
    assert f"](../skills/{skill}/SKILL.md)" in text
    assert (path.parent / f"../skills/{skill}/SKILL.md").is_file()


# Configuration templates


def test_ruff_audit_template_selects_complexity_and_key_families() -> None:
    config = tomllib.loads(
        (_AUDIT / "assets/ruff-audit.toml.template").read_text(encoding="utf-8")
    )
    selected = set(config["lint"]["select"])
    assert {"C90", "PL", "S", "B", "UP", "D", "BLE", "TRY", "PTH"} <= selected
    assert config["lint"]["mccabe"]["max-complexity"] > 0
    assert "PLR2004" in config["lint"]["per-file-ignores"]["tests/**"]


def test_pyproject_audit_template_configures_each_tool() -> None:
    config = tomllib.loads(
        (_AUDIT / "assets/pyproject-audit.toml.template").read_text(encoding="utf-8")
    )
    tool = config["tool"]
    assert tool["vulture"]["min_confidence"] == 80
    assert tool["deptry"]["known_first_party"] == ["shop"]
    assert tool["ty"]["environment"]["python-version"] == "3.13"
    contracts = tool["importlinter"]["contracts"]
    assert {contract["type"] for contract in contracts} == {"layers", "forbidden"}
    assert all(contract["name"] for contract in contracts)


def test_ruff_modernize_template_keeps_behavior_changing_rewrites_manual() -> None:
    config = tomllib.loads(
        (_MODERNIZE / "assets/ruff-modernize.toml.template").read_text(encoding="utf-8")
    )
    assert {"UP", "FA"} <= set(config["lint"]["select"])
    assert {"UP042", "UP046", "UP047"} <= set(config["lint"]["unfixable"])
    assert config["lint"]["pyupgrade"]["keep-runtime-typing"] is False


@pytest.mark.parametrize(
    "template",
    [
        _AUDIT / "assets/audit-plan.md.template",
        _AUDIT / "assets/audit-report.md.template",
        _MODERNIZE / "assets/modernization-ledger.md.template",
        _MODERNIZE / "assets/upgrade-batch-plan.md.template",
    ],
)
def test_markdown_templates_have_title_and_tables(template: Path) -> None:
    text = template.read_text(encoding="utf-8")
    assert text.startswith("# ")
    assert "| --- |" in text
    assert "\t" not in text


# summarize_findings.py


def _sarif(results: list[dict[str, object]], *, rules: list[object]) -> dict:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "osv-scanner", "rules": rules}},
                "results": results,
            }
        ],
    }


def _sarif_result(rule: str, uri: str, line: int, **extra: object) -> dict:
    return {
        "ruleId": rule,
        "message": {"text": f"{rule} message"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": line},
                }
            }
        ],
        **extra,
    }


def _ruff(code: str | None, filename: str, row: int) -> dict:
    return {
        "code": code,
        "filename": filename,
        "location": {"row": row, "column": 1},
        "message": f"{code} message",
    }


def test_summarizer_merges_formats_into_ranked_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sarif = _json(
        tmp_path / "osv.sarif",
        _sarif(
            [
                _sarif_result("GHSA-1", "file:///C:/repo/uv.lock", 3),
                _sarif_result("GHSA-2", "uv.lock", 9, level="note"),
                _sarif_result("PASS-1", "uv.lock", 1, kind="pass"),
            ],
            rules=[{"id": "GHSA-1", "defaultConfiguration": {"level": "error"}}],
        ),
    )
    ruff = _json(
        tmp_path / "ruff.json",
        [
            _ruff("C901", "C:\\repo\\src\\b.py", 4),
            _ruff("C901", "C:\\repo\\src\\a.py", 2),
            _ruff("S608", "C:\\repo\\src\\db.py", 7),
            _ruff("D103", "C:\\repo\\src\\a.py", 9),
        ],
    )
    ty = _json(
        tmp_path / "ty.json",
        [
            {
                "check_name": "invalid-assignment",
                "description": "bad | value",
                "severity": "major",
                "location": {
                    "path": "src\\a.py",
                    "positions": {"begin": {"line": 5, "column": 1}},
                },
            },
            {
                "check_name": "unused-ignore",
                "description": "unused",
                "severity": "info",
                "location": {"path": "src/a.py", "lines": {"begin": 1}},
            },
        ],
    )
    argv = [str(sarif), str(ruff), str(ty), "--root", "C:/repo", "--max-locations"]
    assert _SUMMARIZER["main"]([*argv, "1"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "| Rank | Level | Tool | Rule | Count | Locations | Message |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| 1 | error | osv-scanner | `GHSA-1` | 1 | `uv.lock:3` | GHSA-1 message |",
        "| 2 | error | ruff | `S608` | 1 | `src/db.py:7` | S608 message |",
        "| 3 | error | ty | `invalid-assignment` | 1 | `src/a.py:5` | bad \\| value |",
        "| 4 | warning | ruff | `C901` | 2 | `src/a.py:2`, +1 more | C901 message |",
        "| 5 | warning | ruff | `D103` | 1 | `src/a.py:9` | D103 message |",
        "| 6 | note | osv-scanner | `GHSA-2` | 1 | `uv.lock:9` | GHSA-2 message |",
        "| 7 | note | ty | `unused-ignore` | 1 | `src/a.py:1` | unused |",
        "",
        "8 finding(s) in 7 rule group(s) from 3 tool(s).",
    ]


def test_summarizer_min_level_error_prefixes_and_output_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruff = _json(
        tmp_path / "ruff.json",
        [_ruff("PLR0912", "src/a.py", 3), _ruff(None, "src/broken.py", 1)],
    )
    output = tmp_path / "out.md"
    argv = [str(ruff), "--min-level", "error", "--output", str(output)]
    assert _SUMMARIZER["main"](argv) == 1
    assert capsys.readouterr().out == ""
    text = output.read_text(encoding="utf-8")
    assert "`syntax-error`" in text
    assert "PLR0912" not in text
    argv = [str(ruff), "--min-level", "error", "--error-prefix", "PLR"]
    assert _SUMMARIZER["main"](argv) == 1
    assert "`PLR0912`" in capsys.readouterr().out


def test_summarizer_clean_reports_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruff = _json(tmp_path / "ruff.json", [])
    sarif = _json(tmp_path / "empty.sarif", _sarif([], rules=[]))
    note = _json(
        tmp_path / "notes.sarif",
        _sarif([_sarif_result("R1", "a.py", 1, level="note")], rules=[]),
    )
    assert _SUMMARIZER["main"]([str(ruff), str(sarif)]) == 0
    assert _SUMMARIZER["main"]([str(note), "--min-level", "warning"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "0 finding(s) in 0 rule group(s) from 0 tool(s).",
        "0 finding(s) in 0 rule group(s) from 0 tool(s).",
    ]


def test_summarizer_truncates_long_messages_deterministically() -> None:
    finding = _SUMMARIZER["Finding"](
        tool="t",
        rule="r",
        level=_SUMMARIZER["Level"].WARNING,
        path="a.py",
        line=0,
        message="x" * 500,
    )
    group = _SUMMARIZER["RuleGroup"](tool="t", rule="r", findings=(finding,))
    table = _SUMMARIZER["render"]([group], max_locations=3)
    row = table.splitlines()[2]
    assert "`a.py`" in row
    assert row.endswith("x" * 157 + "... |")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"version": "2.1.0"}, "neither SARIF"),
        ({"runs": {}}, "runs must be a list"),
        ({"runs": [{"tool": {"driver": {}}}]}, "driver.name must be"),
        ([{"other": 1}], "neither SARIF"),
        ([{"filename": "a.py", "location": {"row": 0}}], "must be a positive"),
        (
            [{"check_name": "x", "severity": "huge", "location": {"path": "a"}}],
            "unsupported level",
        ),
        (
            {
                "runs": [
                    {
                        "tool": {"driver": {"name": "t"}},
                        "results": [{"ruleId": "R", "level": "fatal"}],
                    }
                ]
            },
            "unsupported level",
        ),
        ("text", "neither SARIF"),
    ],
)
def test_summarizer_rejects_malformed_reports_with_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: object,
    message: str,
) -> None:
    report = _json(tmp_path / "report.json", payload)
    assert _SUMMARIZER["main"]([str(report)]) == 2
    assert message in capsys.readouterr().err


def test_summarizer_rejects_missing_and_invalid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = _write(tmp_path / "broken.json", "{not json")
    assert _SUMMARIZER["main"]([str(tmp_path / "absent.json")]) == 2
    assert _SUMMARIZER["main"]([str(broken)]) == 2
    errors = capsys.readouterr().err
    assert "absent.json" in errors
    assert "broken.json" in errors
    with pytest.raises(SystemExit) as raised:
        _SUMMARIZER["main"]([str(broken), "--max-locations", "0"])
    assert raised.value.code == 2


def test_summarizer_normalizes_paths() -> None:
    normalize = _SUMMARIZER["normalize_path"]
    assert normalize("file:///C:/repo/src/a%20b.py", root="C:\\repo") == "src/a b.py"
    assert normalize("src\\a.py", root="") == "src/a.py"
    assert normalize("/other/a.py", root="/repo") == "/other/a.py"


@pytest.mark.parametrize("namespace", [_SUMMARIZER, _LEGACY])
def test_checkers_self_test_and_require_inputs(
    namespace: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    main = namespace["main"]
    assert callable(main)
    assert main(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out
    with pytest.raises(SystemExit) as raised:
        main([])
    assert raised.value.code == 2


# check_legacy_syntax.py


def _rules(*names: str) -> frozenset:
    return frozenset(_LEGACY["Rule"](name) for name in names)


def test_legacy_checker_flags_typing_aliases_and_percent_format() -> None:
    source = (
        "import typing as t\n"
        "from typing import Dict, List, Optional, Protocol, Union\n"
        "from typing_extensions import Text\n"
        "def f(x: t.Tuple[int, ...]) -> Optional[str]:\n"
        "    return 'value %s' % x\n"
    )
    findings = _LEGACY["check_source"](source, "m.py", rules=_LEGACY["DEFAULT_RULES"])
    assert [finding.render() for finding in findings] == [
        "m.py:2: typing-alias: typing.Dict is legacy; use dict",
        "m.py:2: typing-alias: typing.List is legacy; use list",
        "m.py:2: typing-alias: typing.Optional is legacy; use X | None",
        "m.py:2: typing-alias: typing.Union is legacy; use X | Y",
        "m.py:3: typing-alias: typing.Text is legacy; use str",
        "m.py:4: typing-alias: typing.Tuple is legacy; use tuple",
        (
            "m.py:5: percent-format: printf-style % formatting; "
            "use an f-string or str.format"
        ),
    ]


def test_legacy_checker_accepts_modern_code_and_lazy_logging() -> None:
    source = (
        "import logging\n"
        "from collections.abc import Sequence\n"
        "from typing import Protocol, Self\n"
        "LOGGER = logging.getLogger(__name__)\n"
        "def f(items: Sequence[int], name: str | None) -> list[int]:\n"
        "    LOGGER.info('items %s', name)\n"
        "    return [item % 2 for item in items]\n"
    )
    every_rule = frozenset(_LEGACY["Rule"])
    assert _LEGACY["check_source"](source, "m.py", rules=every_rule) == []


def test_legacy_checker_policy_rules_are_opt_in() -> None:
    source = (
        "from __future__ import annotations\n"
        "import os\n"
        "import os.path\n"
        "from os import path\n"
        "joined = os.path.join('a', 'b')\n"
    )
    assert _LEGACY["check_source"](source, "m.py", rules=_LEGACY["DEFAULT_RULES"]) == []
    findings = _LEGACY["check_source"](
        source, "m.py", rules=_rules("future-annotations", "os-path")
    )
    assert [(finding.line, finding.rule.value) for finding in findings] == [
        (1, "future-annotations"),
        (3, "os-path"),
        (4, "os-path"),
        (5, "os-path"),
    ]


def test_legacy_checker_main_options_and_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = _write(tmp_path / "src/clean.py", "value: list[int] = []\n")
    legacy = _write(
        tmp_path / "src/legacy.py",
        "from __future__ import annotations\nimport os.path\nmsg = 'a %s' % 1\n",
    )
    _write(tmp_path / "src/.venv/skipped.py", "from typing import List\n")
    _write(tmp_path / "src/generated/skipped.py", "from typing import List\n")
    main = _LEGACY["main"]
    assert main([str(clean)]) == 0
    assert capsys.readouterr().out == "1 file(s) checked, 0 finding(s).\n"
    assert main([str(tmp_path / "src"), "--exclude", "generated"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out == [
        (
            f"{legacy.as_posix()}:3: percent-format: printf-style % formatting; "
            "use an f-string or str.format"
        ),
        "2 file(s) checked, 1 finding(s).",
    ]
    argv = [str(legacy), "--disable", "percent-format"]
    assert main(argv) == 0
    assert main([*argv, "--pathlib", "--future-annotations"]) == 1
    rules = [line.split(": ")[1] for line in capsys.readouterr().out.splitlines()[1:-1]]
    assert rules == ["future-annotations", "os-path"]


def test_legacy_checker_reports_unusable_input_with_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = _write(tmp_path / "broken.py", "def broken(:\n")
    assert _LEGACY["main"]([str(broken)]) == 2
    assert "broken.py: cannot check" in capsys.readouterr().err
    assert _LEGACY["main"]([str(tmp_path / "absent")]) == 2
    assert "path does not exist" in capsys.readouterr().err
    with pytest.raises(SystemExit) as raised:
        _LEGACY["main"]([str(broken), "--disable", "os-path"])
    assert raised.value.code == 2
