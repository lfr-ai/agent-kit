"""Portable validators distinguish wrong types from invalid values and shapes."""

import asyncio
import json
import re
import runpy
import shutil
import sys
from pathlib import Path
from typing import NoReturn

import pytest

_PACKAGES = Path(__file__).resolve().parents[3] / "packages"
_PLAN = "iac/.apm/skills/kit-terraform-validation/assets/review_plan.py"
_WHATIF = "iac/.apm/skills/kit-azure-validation/assets/review_whatif.py"
_LICENSE = "shared/.apm/skills/kit-agent-runtime/assets/license_guard.py"
_EVIDENCE = "shared/.apm/skills/kit-agent-runtime/assets/review_package.py"
_HOOK = "shared/.apm/skills/kit-agent-runtime/assets/tool_guard.py"
_REPORT = (
    "workflows/.apm/skills/kit-duplication-review/assets/summarize_jscpd_report.py"
)
_TASKS = "shared/.apm/skills/kit-editor/assets/check_task_wiring.py"
_HAR = "frontend/.apm/skills/kit-browser-debugging/assets/check_har.py"
_OPENAPI = "backend/.apm/skills/kit-api-contracts/assets/compare_openapi.py"


@pytest.mark.parametrize(
    ("asset", "function", "payload", "error_type", "message"),
    [
        (_PLAN, "analyze_plan", [], TypeError, "plan must be an object"),
        (
            _PLAN,
            "analyze_plan",
            {},
            ValueError,
            "supported Terraform format_version is 1.x",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": 1},
            TypeError,
            "supported Terraform format_version is 1.x",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "2.0"},
            ValueError,
            "supported Terraform format_version is 1.x",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2"},
            ValueError,
            "resource_changes must be an explicit array",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2", "resource_changes": None},
            TypeError,
            "resource_changes must be an explicit array",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2", "resource_changes": [0]},
            TypeError,
            "each resource change must be an object",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2", "resource_changes": [{"address": 0}]},
            TypeError,
            "each resource needs a nonempty unique address",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2", "resource_changes": [{"address": ""}]},
            ValueError,
            "each resource needs a nonempty unique address",
        ),
        (
            _PLAN,
            "analyze_plan",
            {
                "format_version": "1.2",
                "resource_changes": [{"address": "a", "change": []}],
            },
            TypeError,
            "each resource needs a change object",
        ),
        (
            _PLAN,
            "analyze_plan",
            {
                "format_version": "1.2",
                "resource_changes": [{"address": "a", "change": {"actions": [1]}}],
            },
            TypeError,
            "change.actions must be a supported string array",
        ),
        (
            _PLAN,
            "analyze_plan",
            {
                "format_version": "1.2",
                "resource_changes": [{"address": "a", "change": {"actions": []}}],
            },
            ValueError,
            "unsupported change.actions require manual review",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2", "deferred_changes": None},
            TypeError,
            "deferred changes require manual review",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2", "deferred_changes": [1]},
            ValueError,
            "deferred changes require manual review",
        ),
        (
            _PLAN,
            "analyze_plan",
            {"format_version": "1.2", "complete": 1},
            TypeError,
            "errored or incomplete plan cannot be reviewed",
        ),
        (_WHATIF, "analyze_whatif", [], TypeError, "what-if result must be an object"),
        (
            _WHATIF,
            "analyze_whatif",
            {},
            ValueError,
            "expected changes or properties.changes",
        ),
        (
            _WHATIF,
            "analyze_whatif",
            {"changes": None},
            TypeError,
            "changes must be an explicit array",
        ),
        (
            _WHATIF,
            "analyze_whatif",
            {"changes": [0]},
            TypeError,
            "each change must be an object",
        ),
        (
            _WHATIF,
            "analyze_whatif",
            {"changes": [{"resourceId": 1}]},
            TypeError,
            "each change needs a nonempty unique resourceId",
        ),
        (
            _WHATIF,
            "analyze_whatif",
            {"changes": [{"resourceId": ""}]},
            ValueError,
            "each change needs a nonempty unique resourceId",
        ),
        (
            _WHATIF,
            "analyze_whatif",
            {"changes": [{"resourceId": "/a", "changeType": []}]},
            TypeError,
            "unsupported or missing changeType",
        ),
        (
            _WHATIF,
            "analyze_whatif",
            {"changes": [{"resourceId": "/a", "changeType": "Unknown"}]},
            ValueError,
            "unsupported or missing changeType",
        ),
        (
            _WHATIF,
            "analyze_whatif",
            {"status": 1},
            TypeError,
            "failed or unfinished what-if result cannot be reviewed",
        ),
        (_LICENSE, "parse_allowlist", [], TypeError, "allowlist must be a JSON object"),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": True},
            TypeError,
            "schema_version must be 1",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 2},
            ValueError,
            "schema_version must be 1",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1},
            ValueError,
            "allowed must be a list of non-empty strings",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1, "allowed": "MIT"},
            TypeError,
            "allowed must be a list of non-empty strings",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1, "allowed": [1]},
            TypeError,
            "allowed must be a list of non-empty strings",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1, "allowed": [""]},
            ValueError,
            "allowed must be a list of non-empty strings",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1, "allowed": [], "exceptions": []},
            TypeError,
            "exceptions must be an object keyed by distribution name",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1, "allowed": [], "exceptions": {"x": []}},
            TypeError,
            "exceptions.x must use only ['expires', 'license', 'reason']",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1, "allowed": [], "exceptions": {"x": {"license": 1}}},
            TypeError,
            "exceptions.x.license must name the observed license",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {"schema_version": 1, "allowed": [], "exceptions": {"x": {"license": ""}}},
            ValueError,
            "exceptions.x.license must name the observed license",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {
                "schema_version": 1,
                "allowed": [],
                "exceptions": {"x": {"license": "MIT", "reason": 1}},
            },
            TypeError,
            "exceptions.x.reason must record the review decision",
        ),
        (
            _LICENSE,
            "parse_allowlist",
            {
                "schema_version": 1,
                "allowed": [],
                "exceptions": {"x": {"license": "MIT", "reason": "r", "expires": 1}},
            },
            TypeError,
            "exceptions.x.expires must be an ISO date",
        ),
        (_EVIDENCE, "parse_evidence", [], TypeError, "evidence must be an object"),
        (_EVIDENCE, "parse_evidence", {}, ValueError, "task must be non-empty text"),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": None},
            TypeError,
            "task must be non-empty text",
        ),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": 1},
            TypeError,
            "task must be non-empty text",
        ),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": ""},
            ValueError,
            "task must be non-empty text",
        ),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": "t", "commands": {}},
            TypeError,
            "commands must be a list",
        ),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": "t", "commands": [[]]},
            TypeError,
            "commands[0] must be an object",
        ),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": "t", "commands": [{"command": "test", "exit_code": True}]},
            TypeError,
            "commands[0].exit_code must be an integer",
        ),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": "t", "commands": [{"command": "test"}]},
            ValueError,
            "commands[0].exit_code must be an integer",
        ),
        (
            _EVIDENCE,
            "parse_evidence",
            {"task": "t", "acceptance": [{"status": []}]},
            TypeError,
            "acceptance[0].status must be one of ['met', 'partial', 'unmet', 'not-applicable']",
        ),
        (_HOOK, "parse_payload", [], TypeError, "hook payload must be a JSON object"),
        (
            _HOOK,
            "extract_call",
            {"tool_name": []},
            TypeError,
            "hook payload has no tool name",
        ),
        (_HOOK, "extract_call", {}, ValueError, "hook payload has no tool name"),
        (
            _HOOK,
            "extract_call",
            {"tool_name": ""},
            ValueError,
            "hook payload has no tool name",
        ),
        (
            _REPORT,
            "parse_report",
            [],
            TypeError,
            "report must be an object with a 'duplicates' list",
        ),
        (
            _REPORT,
            "parse_report",
            {},
            ValueError,
            "report must be an object with a 'duplicates' list",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": {}},
            TypeError,
            "report must be an object with a 'duplicates' list",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [0]},
            TypeError,
            "duplicates[0] must be an object",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [{"lines": True}]},
            TypeError,
            "duplicates[0].lines must be a non-negative integer",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [{"lines": None}]},
            TypeError,
            "duplicates[0].lines must be a non-negative integer",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [{}]},
            ValueError,
            "duplicates[0].lines must be a non-negative integer",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [{"lines": 0, "firstFile": None}]},
            TypeError,
            "duplicates[0].firstFile must be an object",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [{"lines": 0}]},
            ValueError,
            "duplicates[0].firstFile must be an object",
        ),
        (
            _REPORT,
            "parse_report",
            {
                "duplicates": [
                    {"lines": 0, "firstFile": {"name": "a", "start": None, "end": 0}}
                ]
            },
            TypeError,
            "duplicates[0].firstFile.start must be a non-negative integer",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [{"lines": 0, "firstFile": {"name": "a", "end": 0}}]},
            ValueError,
            "duplicates[0].firstFile.start must be a non-negative integer",
        ),
        (
            _REPORT,
            "parse_report",
            {
                "duplicates": [
                    {
                        "lines": 0,
                        "firstFile": {
                            "name": "a",
                            "startLoc": {"line": None},
                            "end": 0,
                        },
                    }
                ]
            },
            TypeError,
            "duplicates[0].firstFile.start must be a non-negative integer",
        ),
        (
            _REPORT,
            "parse_report",
            {"duplicates": [{"lines": -1}]},
            ValueError,
            "duplicates[0].lines must be a non-negative integer",
        ),
        (
            _TASKS,
            "invocations",
            [],
            TypeError,
            "tasks.json must be an object with a 'tasks' list",
        ),
        (
            _TASKS,
            "invocations",
            {},
            ValueError,
            "tasks.json must be an object with a 'tasks' list",
        ),
        (
            _TASKS,
            "invocations",
            {"tasks": {}},
            TypeError,
            "tasks.json must be an object with a 'tasks' list",
        ),
    ],
)
def test_portable_input_exception_contract(
    asset: str,
    function: str,
    payload: object,
    error_type: type[Exception],
    message: str,
) -> None:
    namespace = runpy.run_path(str(_PACKAGES / asset))
    value = payload
    if function in {"parse_allowlist", "parse_evidence", "invocations"}:
        value = json.dumps(payload)
    elif function == "parse_payload":
        value = json.dumps(payload).encode()
    with pytest.raises(error_type, match=f"^{re.escape(message)}$") as caught:
        namespace[function](value)
    assert type(caught.value) is not error_type
    other_type = ValueError if error_type is TypeError else TypeError
    assert not isinstance(caught.value, other_type)


async def _run_asset(
    script: Path, arguments: list[str], directory: Path
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(script),
        *arguments,
        cwd=directory,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(b"[]"), timeout=30)
    assert process.returncode is not None
    return process.returncode, stdout.decode(), stderr.decode()


@pytest.mark.parametrize(
    ("asset", "function", "payload", "error_type", "message"),
    [
        (_HAR, "check", [], TypeError, "{path}: not a HAR file (missing log.entries)"),
        (
            _HAR,
            "check",
            {"log": []},
            TypeError,
            "{path}: not a HAR file (missing log.entries)",
        ),
        (
            _HAR,
            "check",
            {"log": {"entries": None}},
            TypeError,
            "{path}: not a HAR file (missing log.entries)",
        ),
        (_HAR, "check", {}, ValueError, "{path}: not a HAR file (missing log.entries)"),
        (
            _OPENAPI,
            "_load",
            [],
            TypeError,
            "{path} is not an OpenAPI JSON object with 'paths'",
        ),
        (
            _OPENAPI,
            "_load",
            {"paths": []},
            TypeError,
            "{path} is not an OpenAPI JSON object with 'paths'",
        ),
        (
            _OPENAPI,
            "_load",
            {},
            ValueError,
            "{path} is not an OpenAPI JSON object with 'paths'",
        ),
    ],
)
def test_file_parser_exception_contract(
    tmp_path: Path,
    asset: str,
    function: str,
    payload: object,
    error_type: type[Exception],
    message: str,
) -> None:
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    namespace = runpy.run_path(str(_PACKAGES / asset))
    with pytest.raises(error_type, match=f"^{re.escape(message.format(path=path))}$"):
        namespace[function](path)


@pytest.mark.parametrize(
    ("asset", "arguments", "code", "diagnostic"),
    [
        (_PLAN, ["--file", "input.json"], 2, "Cannot review plan"),
        (_WHATIF, ["--file", "input.json"], 2, "Cannot review what-if"),
        (_LICENSE, ["--allowlist", "input.json"], 2, "allowlist is unusable"),
        (
            _EVIDENCE,
            ["--diff", "change.diff", "--evidence", "input.json"],
            2,
            "inputs are unusable",
        ),
        (
            _HOOK,
            ["hook", "--policy", "policy.json"],
            2,
            "hook payload must be a JSON object",
        ),
        (_REPORT, ["input.json"], 2, "cannot summarize report"),
        (
            _TASKS,
            ["--tasks", "input.json", "--taskfile", "Taskfile.yml"],
            2,
            "Cannot check task wiring",
        ),
        (_HAR, ["input.json"], 1, "Cannot check HAR input"),
        (_OPENAPI, ["input.json", "input.json"], 2, "cannot compare"),
    ],
)
def test_relocated_cli_handles_only_intended_input_type_failures(
    tmp_path: Path, asset: str, arguments: list[str], code: int, diagnostic: str
) -> None:
    script = tmp_path / Path(asset).name
    shutil.copyfile(_PACKAGES / asset, script)
    (tmp_path / "input.json").write_text("[]", encoding="utf-8")
    (tmp_path / "change.diff").write_text("", encoding="utf-8")
    (tmp_path / "Taskfile.yml").write_text(
        "version: '3'\ntasks: {}\n", encoding="utf-8"
    )
    (tmp_path / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": [
                    {
                        "id": "deny",
                        "decision": "deny",
                        "match": "command",
                        "pattern": ".*",
                        "reason": "blocked",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    status, _, stderr = asyncio.run(_run_asset(script, arguments, tmp_path))
    assert status == code, stderr
    assert diagnostic in stderr
    assert "Traceback" not in stderr


@pytest.mark.parametrize(
    ("asset", "arguments"),
    [
        (_PLAN, ["--file", "input.json"]),
        (_WHATIF, ["--file", "input.json"]),
        (_LICENSE, ["--allowlist", "input.json"]),
        (_EVIDENCE, ["--diff", "change.diff", "--evidence", "input.json"]),
        (_HOOK, ["hook", "--policy", "policy.json"]),
        (_HAR, ["input.json"]),
        (_OPENAPI, ["input.json", "input.json"]),
        (_REPORT, ["input.json"]),
        (_TASKS, ["--tasks", "input.json", "--taskfile", "Taskfile.yml"]),
    ],
)
def test_cli_does_not_swallow_programmer_type_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asset: str, arguments: list[str]
) -> None:
    namespace = runpy.run_path(str(_PACKAGES / asset))
    main = namespace["main"]
    (tmp_path / "input.json").write_text("{}", encoding="utf-8")
    (tmp_path / "Taskfile.yml").write_text(
        "version: '3'\ntasks: {}\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [asset, *arguments])
    defect = TypeError("synthetic programmer defect")

    def broken_open(self: Path, *args: object, **kwargs: object) -> NoReturn:
        raise defect

    monkeypatch.setattr(Path, "open", broken_open)
    with pytest.raises(TypeError) as caught:
        main() if asset in {_PLAN, _WHATIF} else main(arguments)
    assert caught.value is defect


@pytest.mark.parametrize(
    "asset",
    [
        "backend/.apm/skills/kit-config/assets/check_from_config_pattern.py",
        "backend/.apm/skills/kit-database-migrations/assets/check_migration_safety.py",
        "backend/.apm/skills/kit-jinja/assets/check_template_safety.py",
        "backend/.apm/skills/kit-polars-v2/assets/check_polars_usage.py",
        "backend/.apm/skills/kit-pydantic-v2/assets/check_pydantic_v2.py",
        "backend/.apm/skills/kit-python-package/assets/check_pyproject.py",
        _HAR,
        "frontend/.apm/skills/kit-react-feature/assets/check_feature_imports.py",
        "frontend/.apm/skills/kit-runtime-config/assets/scan_public_bundle.py",
        _PLAN,
        _WHATIF,
        "iac/.apm/skills/kit-ci-review/assets/check_workflow_permissions.py",
        _LICENSE,
        _EVIDENCE,
        _HOOK,
        "shared/.apm/skills/kit-context-onboarding/assets/check_context.py",
        "shared/.apm/skills/kit-context-onboarding/assets/check_memory_freshness.py",
        _TASKS,
        "shared/.apm/skills/kit-parallel-work/assets/new_worktree.py",
        _REPORT,
        "workflows/.apm/skills/kit-graph-analysis/assets/import_graph.py",
        "workflows/.apm/skills/kit-simplify-review/assets/collect_debt_markers.py",
        "workflows/.apm/skills/kit-spec-workflow/assets/check_spec_change.py",
    ],
)
def test_changed_self_tests_run_standalone(tmp_path: Path, asset: str) -> None:
    script = tmp_path / Path(asset).name
    shutil.copyfile(_PACKAGES / asset, script)
    status, stdout, stderr = asyncio.run(_run_asset(script, ["--self-test"], tmp_path))
    assert status == 0, stderr
    assert "self-test" in stdout.lower()
