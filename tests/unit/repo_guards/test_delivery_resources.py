"""Delivery pipeline skill assets behave as documented."""

import ast
from collections.abc import Callable
import json
from pathlib import Path
import re
import runpy
import shutil
import sys

import pytest
from scripts.check_resources import _reachable
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SKILL = _ROOT / "packages/iac/.apm/skills/kit-delivery-pipelines"
_INSTRUCTIONS = _ROOT / "packages/iac/.apm/instructions"
_CHECKER = _SKILL / "assets/check_delivery_workflow.py"
_WORKFLOWS = _SKILL / "assets/workflows"
_DORA = _SKILL / "assets/dora-metrics.py.template"
_MAX_DESCRIPTION = 110
_MAX_INSTRUCTION_LINES = 20

_RISKY = """\
on: push
concurrency:
  group: everything
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - run: docker build -t app .
  deploy:
    runs-on: ubuntu-24.04
    environment:
      name: production
    concurrency:
      group: prod
      cancel-in-progress: true
    steps:
      - uses: azure/login@0000000000000000000000000000000000000000
      - run: |
          npm run build
          az containerapp update --image ghcr.io/shop/orders:1.4.2
"""

_CLEAN = """\
on: workflow_dispatch
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - run: echo verify
  deploy:
    needs: verify
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    environment: production
    permissions:
      id-token: write
    steps:
      - uses: azure/login@0000000000000000000000000000000000000000
      - run: az containerapp update --image "ghcr.io/shop/orders@${{ inputs.digest }}"
"""


def _namespace(path: Path) -> dict[str, object]:
    return runpy.run_path(str(path))


def _main(path: Path) -> Callable[[list[str]], int]:
    main = _namespace(path)["main"]
    assert callable(main)

    def invoke(arguments: list[str]) -> int:
        result = main(arguments)
        assert isinstance(result, int)
        return result

    return invoke


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    loaded = yaml.safe_load(match.group(1))
    assert isinstance(loaded, dict)
    return loaded


# Skill structure


def test_skill_metadata_fits_the_delivery_budget() -> None:
    metadata = _frontmatter(_SKILL / "SKILL.md")
    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == _SKILL.name
    assert metadata["license"] == "MIT"
    description = metadata["description"]
    assert isinstance(description, str)
    assert description.startswith("Use when")
    assert "\n" not in description
    assert len(description) <= _MAX_DESCRIPTION
    body = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "## Acceptance gates" in body
    assert len(body.splitlines()) < 300


def test_every_resource_is_linked_and_links_stay_inside() -> None:
    reached = _reachable(_SKILL / "SKILL.md")
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (_SKILL / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert resources <= reached
    for path in _SKILL.rglob("*.md"):
        for target in re.findall(r"\]\(([^)#]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_relative_to(_SKILL.resolve()), (path, target)
            assert resolved.exists(), (path, target)


@pytest.mark.parametrize("path", sorted(_SKILL.rglob("*")), ids=lambda path: path.name)
def test_files_are_lf_utf8_with_final_newline(path: Path) -> None:
    if not path.is_file() or "__pycache__" in path.parts:
        return
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    assert data.endswith(b"\n")


def test_references_cite_dated_official_sources() -> None:
    for path in sorted((_SKILL / "references").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "2026-10" in text, path.name
        if path.name != "guide.md":
            assert "## Sources" in text, path.name


# Templates


@pytest.mark.parametrize(
    "path", sorted(_WORKFLOWS.glob("*.yml.template")), ids=lambda path: path.name
)
def test_workflow_templates_parse_and_pin_actions(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    assert "jobs" in loaded
    for uses in re.findall(r"uses:\s*([^\s#]+)", text):
        if uses.startswith("./"):
            continue
        assert uses.endswith("@PIN_FULL_COMMIT_SHA"), uses
    for name, job in loaded["jobs"].items():
        if "uses" not in job:
            assert "timeout-minutes" in job, name


def test_dora_template_parses_and_computes_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ast.parse(_DORA.read_text(encoding="utf-8"))
    script = tmp_path / "dora_metrics.py"
    shutil.copyfile(_DORA, script)
    records = [
        {
            "environment": "production",
            "created_at": "2026-10-01T10:00:00Z",
            "status": "success",
            "status_at": "2026-10-01T10:00:00Z",
            "commit_times": ["2026-10-01T08:00:00Z", "2026-10-01T06:00:00Z"],
            "caused_incident": False,
        },
        {
            "environment": "production",
            "created_at": "2026-10-03T10:00:00Z",
            "status": "inactive",
            "status_at": "2026-10-03T10:00:00Z",
            "commit_times": ["2026-10-03T09:00:00Z"],
            "caused_incident": True,
            "restored_at": "2026-10-03T10:30:00Z",
            "unplanned": True,
        },
        {
            "environment": "test",
            "created_at": "2026-10-02T10:00:00Z",
            "status": "success",
            "status_at": "2026-10-02T10:00:00Z",
        },
    ]
    export = _write(tmp_path, "deployments.json", json.dumps(records))
    main = _main(script)
    arguments = [str(export), "--since", "2026-10-01", "--until", "2026-10-08"]
    assert main([*arguments, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["deployments"] == 2
    assert report["successful_deployments"] == 2
    assert report["deployments_per_week"] == pytest.approx(2.0)
    assert report["lead_time_median_hours"] == pytest.approx(2.0)
    assert report["change_fail_rate"] == pytest.approx(0.5)
    assert report["change_fail_basis"] == "caused_incident"
    assert report["recovery_time_median_hours"] == pytest.approx(0.5)
    assert report["rework_rate"] == pytest.approx(0.5)
    assert main(arguments) == 0
    assert "change fail rate: 50.00 %" in capsys.readouterr().out


def test_dora_template_rejects_naive_timestamps(tmp_path: Path) -> None:
    script = tmp_path / "dora_metrics.py"
    shutil.copyfile(_DORA, script)
    record = {
        "environment": "production",
        "created_at": "2026-10-01T10:00:00",
        "status": "success",
        "status_at": "2026-10-01T10:00:00Z",
    }
    export = _write(tmp_path, "deployments.json", json.dumps([record]))
    main = _main(script)
    assert main([str(export), "--since", "2026-10-01", "--until", "2026-10-02"]) == 2


# Checker


def test_checker_self_test_passes() -> None:
    assert _main(_CHECKER)(["--self-test"]) == 0


def test_checker_accepts_the_shipped_workflow_templates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _main(_CHECKER)([str(_WORKFLOWS)]) == 0
    assert "No findings in 7 file(s)." in capsys.readouterr().out


def test_checker_accepts_a_promoting_workflow(tmp_path: Path) -> None:
    assert _main(_CHECKER)([str(_write(tmp_path, "cd.yml", _CLEAN))]) == 0


def test_checker_reports_every_rule_with_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "cd.yml", _RISKY)
    assert _main(_CHECKER)([str(path)]) == 1
    lines = capsys.readouterr().out.splitlines()
    prefix = path.as_posix()
    image = "'ghcr.io/shop/orders:1.4.2'"
    expected = [
        f"{prefix}:4: [deploy-cancel] workflow concurrency",
        f"{prefix}:11: [deploy-needs]",
        f"{prefix}:11: [deploy-timeout]",
        f"{prefix}:17: [deploy-cancel] deploy job 'deploy'",
        f"{prefix}:19: [oidc-permission]",
        f"{prefix}:21: [rebuild-in-deploy] deploy job 'deploy' builds (npm run build)",
        f"{prefix}:22: [mutable-image] deploy job 'deploy' references image {image}",
    ]
    for needle in expected:
        assert any(line.startswith(needle) for line in lines), needle
    assert len(lines) == len(expected)


def test_checker_options_ignore_rules_and_skip_environments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "cd.yml", _RISKY)
    main = _main(_CHECKER)
    ignored = [f"--ignore={rule}" for rule in ("deploy-needs", "deploy-timeout")]
    assert main([str(path), *ignored]) == 1
    output = capsys.readouterr().out
    assert "[deploy-needs]" not in output
    assert "[deploy-timeout]" not in output
    assert main([str(path), "--skip-environment=^prod"]) == 0


@pytest.mark.parametrize(
    "login",
    [
        "azure/login",
        "aws-actions/configure-aws-credentials",
        "google-github-actions/auth",
        "Azure/Login",
    ],
)
def test_checker_recognizes_every_default_cloud_login(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], login: str
) -> None:
    clean = _CLEAN.replace("azure/login", login)
    assert _main(_CHECKER)([str(_write(tmp_path, "ok.yml", clean))]) == 0
    capsys.readouterr()
    missing = clean.replace("      id-token: write", "      contents: read")
    assert _main(_CHECKER)([str(_write(tmp_path, "cd.yml", missing))]) == 1
    output = capsys.readouterr().out
    assert f":18: [oidc-permission] deploy job 'deploy' runs {login.lower()}" in output


def test_checker_accepts_extra_login_actions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _CLEAN.replace("azure/login", "example-org/cloud-login").replace(
        "      id-token: write", "      contents: read"
    )
    path = _write(tmp_path, "cd.yml", text)
    assert _main(_CHECKER)([str(path)]) == 0
    assert _main(_CHECKER)([str(path), "--login-action=Example-Org/Cloud-Login"]) == 1
    assert "[oidc-permission]" in capsys.readouterr().out


@pytest.mark.parametrize(
    "name", ["cd-aws-ecs.yml.template", "cd-gcp-cloud-run.yml.template"]
)
def test_multi_cloud_templates_share_steps_across_environments(name: str) -> None:
    loaded = yaml.safe_load((_WORKFLOWS / name).read_text(encoding="utf-8"))
    jobs = loaded["jobs"]
    first = jobs["deploy-dev"]
    environments = []
    for job_name in ("deploy-dev", "deploy-test", "deploy-production"):
        job = jobs[job_name]
        assert job["steps"] == first["steps"]
        assert job["env"] == first["env"]
        assert job["permissions"]["id-token"] == "write"
        assert job["concurrency"]["cancel-in-progress"] is False
        assert "@${{ needs.resolve.outputs.digest }}" in job["env"]["IMAGE_REF"]
        environments.append(job["environment"]["name"])
    assert environments == ["dev", "test", "production"]


def test_checker_honors_job_permissions_over_workflow_permissions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _CLEAN.replace("permissions:\n  contents: read", "permissions: write-all")
    text = text.replace("      id-token: write", "      contents: read")
    assert _main(_CHECKER)([str(_write(tmp_path, "cd.yml", text))]) == 1
    assert "[oidc-permission]" in capsys.readouterr().out


def test_checker_treats_reusable_calls_with_environment_as_deploys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "on: push\njobs:\n  release:\n    uses: ./.github/workflows/deploy.yml\n"
        "    with:\n      environment: production\n"
        "      image: ghcr.io/shop/orders:latest\n"
    )
    assert _main(_CHECKER)([str(_write(tmp_path, "call.yml", text))]) == 1
    output = capsys.readouterr().out
    assert ":3: [deploy-needs]" in output
    assert ":7: [mutable-image]" in output
    assert "[deploy-timeout]" not in output


@pytest.mark.parametrize(
    ("word", "mutable"),
    [
        ("ghcr.io/shop/orders:1.4.2", True),
        ("orders:latest", True),
        ("localhost:5000/orders:dev", True),
        ("$REGISTRY/orders:$TAG", True),
        ("ghcr.io/shop/orders@sha256:abc", False),
        ("ghcr.io/shop/orders:1.4.2@sha256:abc", False),
        ("https://example.com/health:ready", False),
        ("C:/work/file:name", False),
        ("scripts/canary-gate.sh", False),
        ("ghcr.io/shop/orders", False),
    ],
)
def test_mutable_reference_heuristic(word: str, mutable: bool) -> None:
    is_mutable = _namespace(_CHECKER)["is_mutable_reference"]
    assert callable(is_mutable)
    assert is_mutable(word) is mutable


def test_checker_rejects_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _main(_CHECKER)
    broken = _write(tmp_path, "broken.yml", "jobs: [unclosed\n")
    assert main([str(broken)]) == 2
    assert "Cannot parse" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.yml")]) == 2
    assert main([str(broken), "--build-pattern=("]) == 2


def test_checker_exits_2_without_pyyaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main = _main(_CHECKER)
    path = _write(tmp_path, "cd.yml", _CLEAN)
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert main([str(path)]) == 2
    assert "PyYAML is required" in capsys.readouterr().err


# Instructions and neighbors


@pytest.mark.parametrize(
    "name", ["kit-devops.instructions.md", "kit-ci-pipelines.instructions.md"]
)
def test_instructions_stay_within_budget_and_name_the_skill(name: str) -> None:
    text = (_INSTRUCTIONS / name).read_text(encoding="utf-8")
    assert len(text.splitlines()) <= _MAX_INSTRUCTION_LINES
    match = re.search(r'^applyTo:\s*"([^"]*)"', text, re.MULTILINE)
    assert match is not None
    assert match.group(1) not in {"**", "**/*"}
    bullets = [line for line in text.splitlines() if line.startswith("- ")]
    assert "`kit-delivery-pipelines`" in bullets[-1]


def test_ci_review_names_the_delivery_owner_without_links() -> None:
    text = (_SKILL.parent / "kit-ci-review/SKILL.md").read_text(encoding="utf-8")
    assert "`kit-delivery-pipelines`" in text
    assert "](../kit-delivery-pipelines" not in text
