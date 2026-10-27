"""Workflow and fullstack skill resources behave as their skills document."""

import configparser
import json
from pathlib import Path
import runpy

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS = _ROOT / "packages/workflows/.apm/skills"
_FULLSTACK = _ROOT / "packages/coordination/.apm/skills/kit-fullstack-workflow"
_SPEC = _WORKFLOWS / "kit-spec-workflow/assets"


def _main(path: Path, argv: list[str]) -> object:
    """Run a checker's ``main`` in-process with explicit arguments."""
    namespace = runpy.run_path(str(path))
    main = namespace["main"]
    assert callable(main)
    return main(argv)


# Spec change checker


_VALID_CHANGE = {
    "proposal.md": "# Export\n\nStatus: verified\n",
    "requirements.md": (
        "## REQ-001 Export invoices\n\n"
        "The service MUST export one month of invoices as CSV.\n\n"
        "### Scenario: Month with invoices\n\n"
        "- Given two invoices in March\n"
        "- When the user exports March\n"
        "- Then the file has two rows\n\n"
        "## REQ-002 Old export\n\nChange: remove\nReason: replaced by REQ-001.\n"
    ),
    "tasks.md": "# Tasks\n\n- [x] 1.1 Write CSV export (REQ-001)\n",
    "verification.md": "# Verification\n\nResult: pass\n",
}


def _change(tmp_path: Path, **overrides: str) -> Path:
    folder = tmp_path / "add-invoice-export"
    folder.mkdir()
    for name, text in {**_VALID_CHANGE, **overrides}.items():
        (folder / name.replace("_", ".")).write_text(text, encoding="utf-8")
    return folder


def test_valid_change_folder_passes_with_trace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _change(tmp_path)
    assert _main(_SPEC / "check_spec_change.py", [str(folder), "--trace"]) == 0
    assert "1 change folder(s) passed." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"requirements_md": "## REQ-001 Export\n\nThe service MUST export.\n"},
            "REQ-001: requirement has no scenario",
        ),
        (
            {
                "requirements_md": (
                    "## REQ-001 Export\n\nThe service exports.\n\n"
                    "### Scenario: Month\n\n- When exporting\n- Then rows exist\n"
                )
            },
            "lacks a normative keyword",
        ),
        (
            {
                "requirements_md": (
                    "## REQ-001 Export\n\nThe service MUST export.\n\n"
                    "### Scenario: Month\n\n- Given data\n- When exporting\n"
                )
            },
            "scenario 'Month' has no Then step",
        ),
        (
            {"requirements_md": "## REQ-001 Old\n\nChange: remove\n"},
            "removed requirement needs a Reason line",
        ),
        (
            {"tasks_md": "- [x] Write export (REQ-001)\n- document it\n"},
            "tasks.md:2: list item is not a checkbox",
        ),
        (
            {"tasks_md": "Nothing planned yet.\n"},
            "no checkbox tasks found",
        ),
        (
            {"tasks_md": "- [ ] Write export (REQ-001)\n"},
            "status 'verified' with 1 unchecked task(s)",
        ),
        (
            {"verification_md": "Result: fail\n"},
            "requires a verification 'Result: pass'",
        ),
        (
            {"proposal_md": "# Export\n\nStatus: shipped\n"},
            "unknown status 'shipped'",
        ),
        (
            {"proposal_md": "# Export\n\nOwner: TBD\nStatus: draft\n"},
            "proposal.md:3: unresolved marker 'TBD'",
        ),
    ],
)
def test_change_defects_are_reported_with_locations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, str],
    message: str,
) -> None:
    folder = _change(tmp_path, **overrides)
    assert _main(_SPEC / "check_spec_change.py", [str(folder)]) == 1
    assert message in capsys.readouterr().out


def test_trace_and_duplicate_identifiers_are_enforced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario = "### Scenario: S\n\n- When x\n- Then y\n\n"
    requirements = (
        f"## REQ-001 A\n\nIt MUST a.\n\n{scenario}"
        f"## REQ-001 B\n\nIt MUST b.\n\n{scenario}"
        f"## REQ-003 C\n\nIt MAY c.\n\n{scenario}"
    )
    folder = _change(tmp_path, requirements_md=requirements)
    assert _main(_SPEC / "check_spec_change.py", [str(folder), "--trace"]) == 1
    output = capsys.readouterr().out
    assert "REQ-001: duplicate identifier (first on line 1)" in output
    assert "REQ-003: no task references this requirement" in output


def test_missing_files_and_custom_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "empty-change"
    folder.mkdir()
    (folder / "notes.md").write_text("PENDING decision\n", encoding="utf-8")
    code = _main(
        _SPEC / "check_spec_change.py",
        [str(folder), "--marker", "PENDING", "--required", "proposal.md"],
    )
    output = capsys.readouterr().out
    assert code == 1
    assert "proposal.md:1: missing or empty required file" in output
    assert "notes.md:1: unresolved marker 'PENDING'" in output
    assert "tasks.md" not in output


def test_markers_inside_code_fences_are_ignored(tmp_path: Path) -> None:
    folder = _change(
        tmp_path, design_md="# Design\n\n```text\nTODO example only\n```\n"
    )
    assert _main(_SPEC / "check_spec_change.py", [str(folder)]) == 0


def test_invalid_input_exits_two(tmp_path: Path) -> None:
    folder = _change(tmp_path)
    checker = _SPEC / "check_spec_change.py"
    assert _main(checker, [str(folder), "--id-pattern", "("]) == 2
    assert _main(checker, []) == 2


def test_spec_templates_fail_until_filled_then_pass(tmp_path: Path) -> None:
    folder = tmp_path / "template-change"
    folder.mkdir()
    for name in ("proposal", "requirements", "design", "tasks", "verification"):
        text = (_SPEC / f"{name}.md.template").read_text(encoding="utf-8")
        (folder / f"{name}.md").write_text(text, encoding="utf-8")
    checker = _SPEC / "check_spec_change.py"
    assert _main(checker, [str(folder), "--trace"]) == 1
    for path in folder.glob("*.md"):
        text = path.read_text(encoding="utf-8").replace("TBD", "example")
        path.write_text(text, encoding="utf-8")
    assert _main(checker, [str(folder), "--trace"]) == 0


# Debt marker collector

_DEBT = _WORKFLOWS / "kit-simplify-review/assets/collect_debt_markers.py"


def test_debt_ledger_lists_markers_and_passes_when_well_formed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "cache.py").write_text(
        "LIMIT_DEBT = 1\n# DEBT(owner=@orders-team, revisit=2027-01-01): per-process\n",
        encoding="utf-8",
    )
    (source / "export.ts").write_text(
        "// SHORTCUT(owner=@web-team): in-memory CSV\n", encoding="utf-8"
    )
    ledger = tmp_path / "ledger.md"
    code = _main(
        _DEBT,
        [
            str(source),
            "--as-of",
            "2026-06-01",
            "--require-owner",
            "--output",
            str(ledger),
        ],
    )
    text = ledger.read_text(encoding="utf-8")
    assert code == 0
    assert capsys.readouterr().err == ""
    assert "Total: 2 (DEBT: 1, SHORTCUT: 1)" in text
    assert text.index("cache.py:2") < text.index("export.ts:1")
    assert b"\r\n" not in ledger.read_bytes()


def test_debt_findings_cover_reason_owner_expiry_and_dates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "job.py"
    target.write_text(
        "# DEBT(revisit=2026-01-31): batch size fixed\n"
        "# SHORTCUT\n"
        "# DEBT(owner=@data-team, revisit=2026-02-30): bad date\n",
        encoding="utf-8",
    )
    code = _main(_DEBT, [str(target), "--as-of", "2026-06-01", "--require-owner"])
    err = capsys.readouterr().err
    assert code == 1
    assert "job.py:1: DEBT expired on 2026-01-31 (as of 2026-06-01)" in err
    assert "job.py:1: DEBT marker has no owner" in err
    assert "job.py:2: SHORTCUT marker has no ': reason'" in err
    assert "job.py:3: invalid revisit date '2026-02-30'" in err


def test_debt_scan_respects_excludes_extensions_and_custom_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text(
        "// DEBT: vendored\n", encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("# COMPAT: old API\n", encoding="utf-8")
    assert _main(_DEBT, [str(tmp_path)]) == 0
    assert "No debt markers found." in capsys.readouterr().out
    assert _main(_DEBT, [str(tmp_path), "--all-files", "--marker", "COMPAT"]) == 0
    assert "COMPAT: 1" in capsys.readouterr().out
    assert _main(_DEBT, [str(tmp_path / "missing")]) == 2


# Import graph


_GRAPH = _WORKFLOWS / "kit-graph-analysis/assets/import_graph.py"


def _package(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root / "shop"


_CYCLIC = {
    "shop/__init__.py": "",
    "shop/orders.py": "from . import billing\n",
    "shop/billing.py": "import shop.orders\n",
    "shop/api.py": "from shop.orders import create\n",
    "shop/types.py": (
        "import typing\nif typing.TYPE_CHECKING:\n    from shop import api\n"
    ),
}


def test_cycles_are_findings_with_import_locations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _package(tmp_path, _CYCLIC)
    assert _main(_GRAPH, [str(package)]) == 1
    output = capsys.readouterr().out
    assert (
        "billing.py:1: import cycle: shop.billing -> shop.orders -> shop.billing"
        in (output)
    )
    assert "5 modules, 4 imports, 1 cycle(s)." in output


def test_acyclic_package_passes_and_type_checking_is_optional(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {**_CYCLIC, "shop/billing.py": ""}
    package = _package(tmp_path, files)
    assert _main(_GRAPH, [str(package)]) == 0
    assert "3 imports" in capsys.readouterr().out
    assert _main(_GRAPH, [str(package), "--skip-type-checking"]) == 0
    assert "2 imports" in capsys.readouterr().out


def test_reverse_forward_and_chain_queries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _package(tmp_path, {**_CYCLIC, "shop/billing.py": ""})
    assert _main(_GRAPH, [str(package), "--reverse", "shop.orders"]) == 0
    reverse = capsys.readouterr().out.splitlines()
    assert reverse[0].endswith("shop.api -> shop.orders (depth 1)")
    assert reverse[-1].endswith("shop.types -> shop.api (depth 2)")
    assert _main(_GRAPH, [str(package), "--forward", "shop.api", "--depth", "1"]) == 0
    assert capsys.readouterr().out.strip().endswith("shop.api -> shop.orders (depth 1)")
    assert _main(_GRAPH, [str(package), "--chain", "shop.types", "shop.billing"]) == 0
    assert (
        capsys.readouterr().out.strip()
        == "shop.types -> shop.api -> shop.orders -> shop.billing"
    )
    assert _main(_GRAPH, [str(package), "--reverse", "shop.unknown"]) == 2


def test_graph_exports_and_unusable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _package(tmp_path, _CYCLIC)
    assert _main(_GRAPH, [str(package), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"from": "shop.api", "to": "shop.orders", "line": 1} in payload["edges"]
    assert _main(_GRAPH, [str(package), "--dot"]) == 0
    assert '"shop.orders" -> "shop.billing";' in capsys.readouterr().out
    (package / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    assert _main(_GRAPH, [str(package)]) == 2
    assert _main(_GRAPH, [str(tmp_path / "absent")]) == 2


def test_external_imports_are_opt_in(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _package(tmp_path, {"shop/__init__.py": "import json\n"})
    assert _main(_GRAPH, [str(package), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["edges"] == []
    assert _main(_GRAPH, [str(package), "--json", "--include-external"]) == 0
    assert json.loads(capsys.readouterr().out)["edges"] == [
        {"from": "shop", "to": "json", "line": 1}
    ]


# jscpd report summarizer


_SUMMARY = _WORKFLOWS / "kit-duplication-review/assets/summarize_jscpd_report.py"
_SMALL_CLONE = {
    "format": "python",
    "lines": 9,
    "tokens": 80,
    "firstFile": {"name": "src/a.py", "start": 3, "end": 11},
    "secondFile": {"name": "src/b.py", "start": 20, "end": 28},
}
_REPORT = {
    "duplicates": [
        _SMALL_CLONE,
        {
            "format": "python",
            "lines": 15,
            "tokens": 120,
            "firstFile": {"name": "src/c.py", "startLoc": {"line": 1}, "end": 15},
            "secondFile": {"name": "src/d.py", "start": 5, "end": 19},
        },
    ],
    "statistics": {"total": {"percentage": 2.5}},
}


def _report(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "jscpd-report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_clones_are_findings_largest_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(_SUMMARY, [str(_report(tmp_path, _REPORT))]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "src/c.py:1: 15-line python clone of src/d.py:5-19 (120 tokens)",
        "src/a.py:3: 9-line python clone of src/b.py:20-28 (80 tokens)",
    ]


def test_filters_and_percentage_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = str(_report(tmp_path, _REPORT))
    assert _main(_SUMMARY, [report, "--min-lines", "16"]) == 0
    assert _main(_SUMMARY, [report, "--ignore", "src/*"]) == 0
    capsys.readouterr()
    assert _main(_SUMMARY, [report, "--min-lines", "16", "--max-percentage", "2"]) == 1
    assert "duplication 2.50% exceeds 2.00%" in capsys.readouterr().out
    assert _main(_SUMMARY, [report, "--markdown"]) == 1
    assert "| `src/c.py:1-15` | `src/d.py:5-19` | 15 | 120 | python | |" in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"duplicates": [{"lines": 2}]},
        {"duplicates": [{**_SMALL_CLONE, "lines": -1}]},
    ],
)
def test_malformed_report_exits_two(tmp_path: Path, payload: object) -> None:
    assert _main(_SUMMARY, [str(_report(tmp_path, payload))]) == 2


# Templates, role and self-tests


def test_config_templates_parse() -> None:
    jscpd = json.loads(
        (_WORKFLOWS / "kit-duplication-review/assets/jscpd.json.template").read_text(
            encoding="utf-8"
        )
    )
    assert jscpd["reporters"] == ["console", "json"]
    assert jscpd["minTokens"] > 0
    openapi = yaml.safe_load(
        (_FULLSTACK / "assets/openapi.yaml.template").read_text(encoding="utf-8")
    )
    assert openapi["openapi"].startswith("3.1")
    assert "/orders/{orderId}" in openapi["paths"]
    linter = configparser.ConfigParser()
    linter.read_string(
        (_WORKFLOWS / "kit-graph-analysis/assets/importlinter.ini.template").read_text(
            encoding="utf-8"
        )
    )
    types = {linter[name]["type"] for name in linter.sections() if "contract" in name}
    assert types == {"layers", "forbidden", "independence"}


def test_fullstack_role_keeps_schema_and_has_procedure_body() -> None:
    data = json.loads((_FULLSTACK / "assets/agents.json").read_text(encoding="utf-8"))
    (role,) = data["roles"]
    assert data["schema_version"] == 1
    assert list(role) == ["id", "kind", "tier", "description", "body", "workers"]
    assert (role["id"], role["kind"], role["tier"]) == (
        "kit-fullstack",
        "primary",
        "coordinator",
    )
    assert (
        role["description"] == "Coordinate a complete backend/frontend vertical slice."
    )
    assert role["workers"] == [
        "kit-backend-implementer",
        "kit-frontend-implementer",
        "kit-contract-iac-lint",
        "kit-code-reviewer",
        "kit-test-author",
    ]
    assert 15 <= len(role["body"].splitlines()) <= 60


@pytest.mark.parametrize(
    "script",
    [
        _SPEC / "check_spec_change.py",
        _DEBT,
        _GRAPH,
        _SUMMARY,
    ],
    ids=lambda path: path.stem,
)
def test_self_tests_pass(script: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _main(script, ["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


@pytest.mark.parametrize("closer", ["-->", "--!>", "*/"])
def test_debt_reason_strips_trailing_comment_closers(closer: str) -> None:
    """Reasons written inside HTML or block comments do not keep the closer."""
    clean = runpy.run_path(str(_DEBT))["_clean_reason"]

    assert clean(f"per-process cache {closer}") == "per-process cache"
