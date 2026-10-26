"""Shared repository readiness, security and quality assets behave as documented."""

import ast
import doctest
import json
from pathlib import Path
import re
import runpy
import shutil
import sys
import tomllib

import pytest
import yaml

_SHARED = Path(__file__).resolve().parents[3] / "packages/shared/.apm"
_SKILLS = _SHARED / "skills"
_SETUP = _SKILLS / "kit-repository-setup"
_SECURE = _SKILLS / "kit-secure-code"
_MCP = _SKILLS / "kit-mcp-integration"
_TESTS = _SKILLS / "kit-test-first"
_DOCS = _SKILLS / "kit-documentation"
_VERIFY = _SKILLS / "kit-verify-change"
_REPO = runpy.run_path(str(_SETUP / "assets/check_repository_files.py"))
_PATTERNS = runpy.run_path(str(_SECURE / "assets/check_secure_patterns.py"))
_LAYOUT = runpy.run_path(str(_TESTS / "assets/check_test_layout.py"))
_LINK = re.compile(r"\]\(([^)#\s]+)")
_NEW_SKILLS = (_SETUP, _SECURE, _MCP)
_EXTENDED_RESOURCES = (
    _TESTS / "references/test-suite-architecture.md",
    _TESTS / "assets/check_test_layout.py",
    _TESTS / "assets/noxfile.py.template",
    _DOCS / "references/mermaid-diagrams.md",
    _DOCS / "references/docstring-conventions.md",
    _DOCS / "assets/diagrams.md.template",
    _DOCS / "assets/docstrings.py.template",
    _VERIFY / "references/quality-gate-catalog.md",
    _VERIFY / "assets/gate-plan.md.template",
)
_COMMUNITY_FILES = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "GOVERNANCE.md",
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/bug.yml",
)


def _write(root: Path, relative: str, text: str = "content\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _complete_repository(root: Path) -> Path:
    for relative in _COMMUNITY_FILES:
        _write(root, relative)
    return root


def _frontmatter(path: Path) -> dict[str, object]:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    loaded = yaml.safe_load(parts[1])
    assert isinstance(loaded, dict)
    return loaded


def _reachable(skill: Path) -> set[Path]:
    pending = [skill / "SKILL.md"]
    seen: set[Path] = set()
    while pending:
        current = pending.pop().resolve()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        if current.suffix == ".md":
            text = current.read_text(encoding="utf-8")
            pending.extend(
                current.parent / target
                for target in _LINK.findall(text)
                if not target.startswith(("http://", "https://", "mailto:"))
            )
    return seen


# Skill metadata and resource reachability


@pytest.mark.parametrize("skill", _NEW_SKILLS, ids=lambda path: path.name)
def test_new_skill_metadata_is_minimal_and_triggered(skill: Path) -> None:
    metadata = _frontmatter(skill / "SKILL.md")
    description = str(metadata.pop("description", ""))
    assert metadata == {"name": skill.name, "license": "MIT"}
    assert description.startswith("Use when")
    assert len(description) <= 350
    body = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "## Acceptance gates" in body
    assert len(body.splitlines()) < 300


@pytest.mark.parametrize("skill", _NEW_SKILLS, ids=lambda path: path.name)
def test_every_new_skill_resource_is_linked(skill: Path) -> None:
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (skill / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert resources
    assert resources <= _reachable(skill)


def test_extended_skill_resources_are_linked_from_their_skill() -> None:
    reachable = set().union(*(_reachable(skill) for skill in (_TESTS, _DOCS, _VERIFY)))
    missing = [
        path.name for path in _EXTENDED_RESOURCES if path.resolve() not in reachable
    ]
    assert missing == []


def test_repository_files_instruction_is_narrow_and_points_to_the_skill() -> None:
    path = _SHARED / "instructions/kit-repository-files.instructions.md"
    metadata = _frontmatter(path)
    assert metadata["applyTo"] == (
        "README.md,CONTRIBUTING.md,SECURITY.md,.env.example,**/.env.example,"
        ".github/**/*.md"
    )
    bullets = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("- ")
    ]
    assert 4 <= len(bullets) <= 10
    assert any("`kit-repository-setup`" in bullet for bullet in bullets)


# Template syntax


@pytest.mark.parametrize(
    "path",
    [
        _SETUP / "assets/renovate.json.template",
        _SETUP / "assets/devcontainer.json.template",
        _SETUP / "assets/cspell.json.template",
        _MCP / "assets/mcp-vscode-server.json.template",
        _MCP / "assets/mcp-claude-server.json.template",
    ],
    ids=lambda path: path.name,
)
def test_json_templates_are_strict_json(path: Path) -> None:
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize(
    "path",
    [
        _MCP / "assets/mcp_server.py.template",
        _MCP / "assets/test_mcp_server.py.template",
        _TESTS / "assets/noxfile.py.template",
        _DOCS / "assets/docstrings.py.template",
        _SECURE / "assets/safe_subprocess.py.template",
        _SECURE / "assets/safe_paths.py.template",
    ],
    ids=lambda path: f"{path.parent.parent.name}/{path.name}",
)
def test_python_templates_parse(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_dependabot_template_covers_each_ecosystem_once_with_delay_and_groups() -> None:
    config = yaml.safe_load(
        (_SETUP / "assets/dependabot.yml.template").read_text(encoding="utf-8")
    )
    updates = config["updates"]
    keys = [(item["package-ecosystem"], item["directory"]) for item in updates]
    assert len(keys) == len(set(keys))
    assert all(item["cooldown"]["default-days"] >= 3 for item in updates)
    assert all(item["schedule"]["interval"] == "weekly" for item in updates)
    uv = next(item for item in updates if item["package-ecosystem"] == "uv")
    assert uv["groups"]["python-security"]["applies-to"] == "security-updates"


def test_renovate_template_delays_releases_but_not_security_fixes() -> None:
    config = json.loads(
        (_SETUP / "assets/renovate.json.template").read_text(encoding="utf-8")
    )
    assert config["minimumReleaseAge"] == "7 days"
    assert config["vulnerabilityAlerts"]["minimumReleaseAge"] is None
    assert "helpers:pinGitHubActionDigests" in config["extends"]
    major = [
        rule
        for rule in config["packageRules"]
        if rule.get("matchUpdateTypes") == ["major"]
    ]
    assert len(major) == 1
    assert major[0]["dependencyDashboardApproval"] is True


def test_precommit_template_uses_only_frozen_revision_placeholders() -> None:
    config = yaml.safe_load(
        (_SETUP / "assets/pre-commit-config.yaml.template").read_text(encoding="utf-8")
    )
    remote = [repo for repo in config["repos"] if repo["repo"] not in {"meta", "local"}]
    assert remote
    assert {repo["rev"] for repo in remote} == {"REVIEWED_COMMIT_SHA"}


def test_devcontainer_template_pins_image_digest_and_feature_versions() -> None:
    config = json.loads(
        (_SETUP / "assets/devcontainer.json.template").read_text(encoding="utf-8")
    )
    assert "@sha256:REVIEWED_SHA256" in config["image"]
    versions = [feature["version"] for feature in config["features"].values()]
    assert versions
    assert all(version.startswith("REVIEWED_") for version in versions)


def test_ruff_security_snippet_is_toml_selecting_bandit_rules() -> None:
    config = tomllib.loads(
        (_SECURE / "assets/ruff-security.toml.template").read_text(encoding="utf-8")
    )
    assert "S" in config["lint"]["extend-select"]
    assert config["lint"]["per-file-ignores"]["tests/**"] == ["S101", "S105", "S106"]


def test_mcp_templates_define_equivalent_pinned_servers_without_secrets() -> None:
    vscode = json.loads(
        (_MCP / "assets/mcp-vscode-server.json.template").read_text(encoding="utf-8")
    )
    claude = json.loads(
        (_MCP / "assets/mcp-claude-server.json.template").read_text(encoding="utf-8")
    )
    assert set(vscode["servers"]) == set(claude["mcpServers"])
    assert vscode["inputs"][0]["password"] is True
    for servers in (vscode["servers"], claude["mcpServers"]):
        text = json.dumps(servers)
        assert "latest" not in text
        assert "npx" not in text
        assert "Bearer ${" in text
        assert servers["reviewed-remote"]["url"].startswith("https://")
        assert servers["project-tools"]["args"][:2] == ["run", "--locked"]


def test_mcp_server_template_exposes_typed_bounded_tools() -> None:
    tree = ast.parse(
        (_MCP / "assets/mcp_server.py.template").read_text(encoding="utf-8")
    )
    tools = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and ast.unparse(decorator.func) == "server.tool"
            for decorator in node.decorator_list
        )
    }
    assert set(tools) == {"search_notes", "read_note"}
    for function in tools.values():
        assert function.returns is not None
        assert all(argument.annotation for argument in function.args.args)
        assert "Field(" in ast.unparse(function.args)
    imports = [node.module for node in tree.body if isinstance(node, ast.ImportFrom)]
    assert "mcp.server" in imports


def test_noxfile_template_defines_a_session_per_tier() -> None:
    tree = ast.parse(
        (_TESTS / "assets/noxfile.py.template").read_text(encoding="utf-8")
    )
    sessions = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any("nox.session" in ast.unparse(item) for item in node.decorator_list)
    }
    assert {
        "unit",
        "property",
        "integration",
        "contract",
        "e2e",
        "coverage",
    } <= sessions


def test_diagram_templates_hold_six_accessible_mermaid_blocks() -> None:
    text = (_DOCS / "assets/diagrams.md.template").read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)```", text, flags=re.DOTALL)
    kinds = {block.split(maxsplit=1)[0] for block in blocks}
    assert len(blocks) == 6
    assert kinds == {"flowchart", "sequenceDiagram", "stateDiagram-v2", "erDiagram"}
    assert all("accTitle:" in block and "accDescr:" in block for block in blocks)
    assert all(len(block.splitlines()) <= 31 for block in blocks)


def test_docstring_template_examples_and_behavior_hold() -> None:
    namespace = runpy.run_path(str(_DOCS / "assets/docstrings.py.template"))
    runner = doctest.DocTestRunner()
    tests = doctest.DocTestFinder().find(
        namespace["split_amount"], "split_amount", globs=namespace
    )
    results = [runner.run(test) for test in tests]
    assert sum(result.attempted for result in results) == 1
    assert sum(result.failed for result in results) == 0
    with pytest.raises(ValueError, match="parts"):
        namespace["split_amount"](namespace["CENT"], parts=0)


# check_repository_files.py


def test_repository_checker_accepts_a_complete_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _complete_repository(tmp_path)
    shutil.copy(_SETUP / "assets/env.example.template", root / ".env.example")
    assert _REPO["main"](["--root", str(root)]) == 0
    assert "complete and safe" in capsys.readouterr().out


def test_repository_checker_reports_each_missing_community_file(tmp_path: Path) -> None:
    findings = _REPO["missing_files"](tmp_path, skipped=frozenset({"GOVERNANCE"}))
    rendered = {finding.render() for finding in findings}
    assert "SECURITY.md: missing community file (SECURITY)" in rendered
    assert ".github/ISSUE_TEMPLATE/: missing community file (ISSUE_FORMS)" in rendered
    assert not any("GOVERNANCE" in item for item in rendered)
    assert len(findings) == 9


def test_repository_checker_accepts_alternate_locations_but_not_issue_config(
    tmp_path: Path,
) -> None:
    _complete_repository(tmp_path)
    (tmp_path / "SECURITY.md").unlink()
    _write(tmp_path, ".github/SECURITY.md")
    (tmp_path / ".github/ISSUE_TEMPLATE/bug.yml").unlink()
    _write(tmp_path, ".github/ISSUE_TEMPLATE/config.yml")
    findings = _REPO["missing_files"](tmp_path, skipped=frozenset())
    assert [finding.message for finding in findings] == [
        "missing community file (ISSUE_FORMS)"
    ]


def test_repository_checker_reports_readme_emojis_by_line() -> None:
    findings = _REPO["readme_emojis"](
        "README.md", "# Tool\nFast \U0001f680 start\nok\n"
    )
    assert [finding.render() for finding in findings] == [
        "README.md:2: emoji in README (U+1F680); use plain words"
    ]
    assert _REPO["readme_emojis"]("README.md", "Plain text, arrows -> and (c).\n") == []


@pytest.mark.parametrize(
    "value",
    [
        "",
        '""',
        "<api-key>",
        "change-me",
        "your-token-here",
        "8000",
        "false",
        "info",
        "http://localhost:8000",
        "https://sandbox.example.com/v1",
        # pragma: allowlist nextline secret: public local development fixture
        "postgresql://app:change-me@localhost:5432/app",
        "redis://cache.test:6379/0",
    ],
)
def test_placeholder_values_are_accepted(value: str) -> None:
    assert _REPO["is_placeholder"](value)


@pytest.mark.parametrize(
    "value",
    [
        "sk-live-4f9a8b7c6d5e4f3a2b1c",
        "hunter2",
        "https://api.payments.internal/v1",
        # pragma: allowlist nextline secret: synthetic rejection fixture
        "postgresql://app:S3cr3tPassw0rd@localhost:5432/app",
        "12345678901234567890",
        "ops@company.internal",
    ],
)
def test_real_looking_values_are_rejected(value: str) -> None:
    assert not _REPO["is_placeholder"](value)


def test_env_checker_reports_undocumented_duplicate_invalid_and_real_values() -> None:
    text = (
        "# --- Application ---\n"
        "\n"
        "# Port the server binds to.\n"
        "APP_PORT=8000\n"
        "APP_TOKEN=\n"
        "# Signing key.\n"
        "APP_SECRET=hunter2\n"
        "# Port again.\n"
        "APP_PORT=9000\n"
        "not a variable\n"
    )
    rendered = [
        finding.render() for finding in _REPO["env_findings"](".env.example", text)
    ]
    assert rendered == [
        ".env.example:5: APP_TOKEN has no comment directly above it",
        (
            ".env.example:7: APP_SECRET has a value that is not an obvious "
            "placeholder; use an empty value, <placeholder>, change-me or a local URL"
        ),
        ".env.example:9: APP_PORT is defined more than once",
        ".env.example:10: not a NAME=value entry or comment",
    ]


def test_env_checker_respects_explicitly_allowed_values() -> None:
    text = "# Region used by the local emulator.\nAPP_REGION=westeurope\n"
    assert _REPO["env_findings"](".env.example", text) != []
    allowed = frozenset({"westeurope"})
    assert _REPO["env_findings"](".env.example", text, allowed=allowed) == []


def test_repository_checker_cli_reports_findings_and_usage_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _complete_repository(tmp_path / "repo")
    _write(root, "README.md", "# Project \u2728\n")
    env = _write(tmp_path, "config.env.example", "TOKEN=ghp_realLookingValue123\n")
    assert _REPO["main"](["--root", str(root), "--env-file", str(env)]) == 1
    output = capsys.readouterr().out
    assert "README.md:1: emoji in README (U+2728)" in output
    assert "config.env.example:1: TOKEN has no comment" in output
    assert _REPO["main"](["--root", str(root), "--env-file", str(tmp_path / "x")]) == 2
    assert _REPO["main"](["--root", str(tmp_path / "missing")]) == 2


def test_repository_templates_pass_their_own_checker() -> None:
    text = (_SETUP / "assets/env.example.template").read_text(encoding="utf-8")
    assert _REPO["env_findings"](".env.example", text) == []
    readme = (_SETUP / "assets/README.md.template").read_text(encoding="utf-8")
    assert _REPO["readme_emojis"]("README.md", readme) == []
    assert readme.index("## Quick start") < readme.index("## Usage")


# check_secure_patterns.py


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("import subprocess\nsubprocess.run('ls', shell=True)\n", "shell-true"),
        ("eval(user_input)\n", "eval-exec"),
        ("exec(code)\n", "eval-exec"),
        ("import pickle as p\np.loads(data)\n", "pickle-load"),
        ("from marshal import loads\nloads(data)\n", "pickle-load"),
        ("import yaml\nyaml.load(text)\n", "yaml-unsafe"),
        ("import yaml\nyaml.load(text, Loader=yaml.Loader)\n", "yaml-unsafe"),
        ("import yaml\nyaml.unsafe_load(text)\n", "yaml-unsafe"),
        ("from yaml import full_load\nfull_load(text)\n", "yaml-unsafe"),
        ("import tempfile\ntempfile.mktemp()\n", "mktemp"),
        ("import requests\nrequests.get(url)\n", "http-no-timeout"),
        ("import httpx as h\nh.post(url, json=body)\n", "http-no-timeout"),
    ],
)
def test_secure_checker_reports_risky_calls(source: str, rule: str) -> None:
    findings = _PATTERNS["check_source"]("app.py", source)
    assert [finding.rule for finding in findings] == [rule]
    assert findings[0].render().startswith(f"app.py:{findings[0].line}: [{rule}]")


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(['ls'], shell=False, timeout=5)\n",
        "import ast\nast.literal_eval(text)\n",
        "import json\njson.loads(data)\n",
        "import yaml\nyaml.safe_load(text)\n",
        "import yaml\nyaml.load(text, Loader=yaml.SafeLoader)\n",
        "import yaml\nfrom yaml import CSafeLoader\nyaml.load(text, CSafeLoader)\n",
        "import tempfile\ntempfile.mkstemp()\n",
        "import requests\nrequests.get(url, timeout=(3, 10))\n",
        "import requests\nrequests.get(url, **options)\n",
        "session.get(url)\n",
        "from sample_library import eval\neval(text)\n",
    ],
)
def test_secure_checker_accepts_safe_or_unattributable_calls(source: str) -> None:
    assert _PATTERNS["check_source"]("app.py", source) == []


def test_secure_checker_honors_rule_specific_allow_comments() -> None:
    source = (
        "import subprocess\n"
        "subprocess.run(cmd, shell=True)  # secure: allow[shell-true] fixed command\n"
        "subprocess.run(cmd, shell=True)  # secure: allow[eval-exec] wrong rule\n"
    )
    findings = _PATTERNS["check_source"]("app.py", source)
    assert [(finding.line, finding.rule) for finding in findings] == [(3, "shell-true")]


def test_secure_checker_rule_selection_and_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "src/app.py", "import pickle\npickle.loads(b)\neval(x)\n")
    _write(tmp_path, "src/clean.py", "VALUE = 1\n")
    _write(tmp_path, ".venv/lib/skipped.py", "eval(x)\n")
    assert _PATTERNS["main"]([str(tmp_path)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(": ", 1)[1].split("]")[0] for line in lines] == [
        "[pickle-load",
        "[eval-exec",
    ]
    assert _PATTERNS["main"]([str(tmp_path / "src"), "--rule", "mktemp"]) == 0
    assert _PATTERNS["main"]([str(tmp_path / "absent")]) == 2


def test_secure_checker_reports_unparsable_files() -> None:
    findings = _PATTERNS["check_source"]("bad.py", "def broken(:\n")
    assert [finding.rule for finding in findings] == ["syntax"]


# check_test_layout.py


def test_layout_checker_accepts_a_tiered_asserting_suite(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    _write(tests, "conftest.py", "import pytest\n")
    _write(tests, "factories.py", "def build() -> int:\n    return 1\n")
    _write(
        tests,
        "unit/test_invoice.py",
        "import pytest\n"
        "def test_total_is_sum_of_lines():\n    assert 1 + 1 == 2\n"
        "def test_negative_total_is_rejected():\n"
        "    with pytest.raises(ValueError):\n        int('x')\n"
        "class TestRefund:\n"
        "    def test_refund_records_reason(self):\n        assert_refunded(1)\n",
    )
    _write(
        tests, "integration/test_store.py", "def test_round_trip():\n    assert True\n"
    )
    assert _LAYOUT["check_tree"](tests) == []


def test_layout_checker_reports_tier_name_and_assertion_problems(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    _write(tests, "test_root.py", "def test_lonely():\n    assert True\n")
    _write(
        tests, "unit/invoice_test.py", "def test_total_matches():\n    assert True\n"
    )
    _write(tests, "unit/checks.py", "def test_hidden():\n    assert True\n")
    _write(
        tests,
        "unit/test_quiet.py",
        "def test_runs_without_checking():\n    compute()\n"
        "async def test_async_without_checking():\n    await compute()\n",
    )
    _write(tests, "unit/.hypothesis/test_cache.py", "def test_x():\n    pass\n")
    rendered = [issue.render() for issue in _LAYOUT["check_tree"](tests)]
    assert rendered == [
        "tests/test_root.py:1: [outside-tier] move the module into a tier directory",
        "tests/unit/checks.py:1: [module-name] rename the module to test_<subject>.py",
        (
            "tests/unit/invoice_test.py:1: [module-name] rename the module to "
            "test_<subject>.py"
        ),
        (
            "tests/unit/test_quiet.py:1: [no-assertion] test_runs_without_checking "
            "asserts nothing; add an assert or pytest.raises"
        ),
        (
            "tests/unit/test_quiet.py:3: [no-assertion] test_async_without_checking "
            "asserts nothing; add an assert or pytest.raises"
        ),
    ]


def test_layout_checker_custom_tiers_and_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tests = tmp_path / "tests"
    _write(tests, "smoke/test_ping.py", "def test_ping_answers():\n    assert True\n")
    assert _LAYOUT["main"]([str(tests)]) == 1
    assert "[outside-tier]" in capsys.readouterr().out
    assert _LAYOUT["main"]([str(tests), "--tier", "smoke"]) == 0
    assert _LAYOUT["main"]([str(tmp_path / "missing")]) == 2


# Secure helper templates


def _copy_template(tmp_path: Path, name: str) -> str:
    target = tmp_path / name.removesuffix(".template")
    shutil.copy(_SECURE / "assets" / name, target)
    return str(target)


def test_safe_subprocess_runs_argument_lists_and_bounds_failures(
    tmp_path: Path,
) -> None:
    helpers = runpy.run_path(_copy_template(tmp_path, "safe_subprocess.py.template"))
    run_command = helpers["run_command"]
    error = helpers["CommandError"]
    result = run_command(sys.executable, ["-c", "print('a b; echo c')"])
    assert result.stdout.strip() == "a b; echo c"
    with pytest.raises(error, match="exited with status 3"):
        run_command(sys.executable, ["-c", "raise SystemExit(3)"])
    failed = run_command(sys.executable, ["-c", "raise SystemExit(3)"], check=False)
    assert failed.returncode == 3
    with pytest.raises(error, match="timed out"):
        run_command(
            sys.executable,
            ["-c", "import threading; threading.Event().wait(5)"],
            timeout_seconds=0.2,
        )
    with pytest.raises(error, match="not found"):
        run_command("definitely-not-an-installed-program", [])


def test_safe_subprocess_environment_and_option_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helpers = runpy.run_path(_copy_template(tmp_path, "safe_subprocess.py.template"))
    monkeypatch.setenv("APP_SECRET_FOR_TEST", "not-inherited")
    assert "APP_SECRET_FOR_TEST" not in helpers["minimal_environment"]()
    assert helpers["minimal_environment"](extra={"MODE": "x"})["MODE"] == "x"
    assert helpers["reject_option_like"]("report.txt") == "report.txt"
    with pytest.raises(helpers["CommandError"], match="option"):
        helpers["reject_option_like"]("--output=/etc/passwd")


@pytest.mark.parametrize(
    "parts",
    [
        ("..", "secret.txt"),
        ("a/../../b",),
        ("/etc/passwd",),
        ("C:\\Windows",),
        ("a\x00b",),
        ("",),
    ],
)
def test_safe_join_rejects_escapes(tmp_path: Path, parts: tuple[str, ...]) -> None:
    helpers = runpy.run_path(_copy_template(tmp_path, "safe_paths.py.template"))
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(helpers["UnsafePathError"]):
        helpers["safe_join"](base, *parts)


def test_safe_join_and_file_name_validation_accept_plain_names(
    tmp_path: Path,
) -> None:
    helpers = runpy.run_path(_copy_template(tmp_path, "safe_paths.py.template"))
    base = tmp_path / "base"
    base.mkdir()
    joined = helpers["safe_join"](base, "reports", "2026.csv")
    assert joined == (base / "reports" / "2026.csv").resolve()
    assert helpers["validate_file_name"]("invoice-01.pdf") == "invoice-01.pdf"


@pytest.mark.parametrize("name", ["../x", "con.txt", ".hidden", "a b.txt", "x" * 300])
def test_file_name_validation_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    helpers = runpy.run_path(_copy_template(tmp_path, "safe_paths.py.template"))
    with pytest.raises(helpers["UnsafePathError"]):
        helpers["validate_file_name"](name)


@pytest.mark.parametrize(
    "checker", [_REPO, _PATTERNS, _LAYOUT], ids=["repository", "secure", "layout"]
)
def test_checkers_pass_their_built_in_self_test(
    checker: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    main = checker["main"]
    assert callable(main)
    assert main(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


@pytest.mark.parametrize("parent", ["venv", "build", ".venv"])
def test_secure_checker_scans_directories_below_a_skipped_parent_name(
    tmp_path: Path, parent: str, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / parent / "proj"
    module = _write(project, "a.py", "eval(x)\n")
    _write(project, "venv/lib/skipped.py", "eval(x)\n")
    assert _PATTERNS["main"]([str(project)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        (
            f"{module.as_posix()}:1: [eval-exec] eval runs arbitrary code; "
            "use ast.literal_eval or a parser"
        )
    ]


def test_secure_checker_never_drops_explicitly_named_files(tmp_path: Path) -> None:
    module = _write(tmp_path, "node_modules/venv/a.py", "eval(x)\n")
    assert _PATTERNS["python_files"]([module]) == [module]
    assert _PATTERNS["main"]([str(module)]) == 1


@pytest.mark.parametrize(
    "decorator",
    [
        "@pytest.fixture",
        "@pytest.fixture()",
        "@pytest.fixture(scope='session')",
        "@fixture",
        "@fixture(autouse=True)",
    ],
)
def test_layout_checker_ignores_fixtures_named_like_tests(
    tmp_path: Path, decorator: str
) -> None:
    tests = tmp_path / "tests"
    _write(
        tests,
        "conftest.py",
        "import pytest\nfrom pytest import fixture\n"
        f"{decorator}\ndef test_database():\n    return {{}}\n",
    )
    _write(
        tests,
        "unit/test_store.py",
        f"import pytest\nfrom pytest import fixture\n{decorator}\n"
        "def test_client():\n    return None\n"
        "def test_store_starts_empty(test_client):\n    assert test_client is None\n",
    )
    assert _LAYOUT["check_tree"](tests) == []
