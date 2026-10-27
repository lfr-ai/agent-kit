"""Multi-cloud IaC selection and cloud-neutral Terraform resources stay valid."""

import json
from pathlib import Path
import re
import runpy
import sys

import pytest
from scripts.check_resources import _reachable
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = _ROOT / "packages/iac/.apm"
_INFRA = _PACKAGE / "skills/kit-infra-review"
_TERRAFORM = _ROOT / "packages/terraform/.apm/skills/kit-terraform-validation"
_BLUEPRINT = _TERRAFORM / "assets/blueprint"
_REVIEWER = _TERRAFORM / "assets/review_plan.py"
_INSTRUCTIONS = _PACKAGE / "instructions"
_TOFU_WORKFLOW = _BLUEPRINT / "github/tofu-plan.yml.template"
_MAX_DESCRIPTION = 110
_MAX_BODY_LINES = 300
_MAX_INSTRUCTION_LINES = 20
_FRONTMATTER = re.compile(r"\A---\n(?P<meta>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_HCL_TEMPLATES = sorted(
    path
    for folder in ("aws", "gcp")
    for path in (_BLUEPRINT / folder).glob("*.template")
)
_CLOSERS = {"}": ("{", "${"), "]": ("[",), ")": ("(",)}


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match, f"{path.name} has no frontmatter"
    meta = yaml.safe_load(match["meta"])
    assert isinstance(meta, dict)
    return {str(key): str(value) for key, value in meta.items()}, match["body"]


def _skip_comment(text: str, index: int) -> int:
    """Return the index after a comment starting at ``index``, or ``index``."""
    if text.startswith("/*", index):
        end = text.find("*/", index + 2)
        return len(text) if end < 0 else end + 2
    if text[index] == "#" or text.startswith("//", index):
        end = text.find("\n", index)
        return len(text) if end < 0 else end
    return index


def _string_step(text: str, index: int, stack: list[str]) -> int:
    """Advance inside a quoted string; return -1 when the string is broken."""
    if text[index] == "\\":
        return index + 2
    if text.startswith(("${", "%{"), index):
        stack.append("${")
        return index + 2
    if text[index] == "\n":
        return -1
    if text[index] == '"':
        stack.pop()
    return index + 1


def _code_step(text: str, index: int, stack: list[str]) -> int:
    """Advance over code; return -1 on an unmatched closing bracket."""
    skipped = _skip_comment(text, index)
    if skipped != index:
        return skipped
    char = text[index]
    if char in '"{[(':
        stack.append(char)
    elif char in _CLOSERS:
        if not stack or stack[-1] not in _CLOSERS[char]:
            return -1
        stack.pop()
    return index + 1


def _hcl_balanced(text: str) -> bool:
    """Check bracket and quote balance, honoring comments and interpolation."""
    stack: list[str] = []
    index = 0
    while 0 <= index < len(text):
        step = _string_step if stack and stack[-1] == '"' else _code_step
        index = step(text, index, stack)
    return index >= 0 and not stack


def _plan(changes: list[tuple[str, str, list[str]]]) -> dict[str, object]:
    return {
        "format_version": "1.2",
        "terraform_version": "1.17.0",
        "resource_changes": [
            {
                "address": address,
                "type": address.split(".")[0],
                "name": address.split(".")[1],
                "provider_name": provider,
                "change": {"actions": actions},
            }
            for address, provider, actions in changes
        ],
    }


_AWS = "registry.terraform.io/hashicorp/aws"
_GOOGLE = "registry.terraform.io/hashicorp/google"
_TOFU_AWS = "registry.opentofu.org/hashicorp/aws"


def _reviewer() -> dict[str, object]:
    return runpy.run_path(str(_REVIEWER))


def _run_reviewer(
    plan: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> int:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["review_plan.py", "--file", str(path)])
    main = _reviewer()["main"]
    assert callable(main)
    result = main()
    assert isinstance(result, int)
    return result


def test_selection_procedure_is_an_on_demand_infra_review_reference() -> None:
    """Tool choice loads from the review skill instead of costing a description."""
    meta, body = _frontmatter(_INFRA / "SKILL.md")
    selection = (_INFRA / "references/iac-selection.md").resolve()

    assert selection in _reachable(_INFRA / "SKILL.md")
    assert not (_PACKAGE / "skills/kit-iac-selection").exists()
    assert set(meta) == {"name", "description", "license"}
    assert meta["name"] == _INFRA.name
    assert meta["license"] == "MIT"
    assert meta["description"].startswith("Use when")
    assert "\n" not in meta["description"]
    assert len(meta["description"]) <= _MAX_DESCRIPTION
    assert len(body.splitlines()) <= _MAX_BODY_LINES


def test_terraform_skill_description_names_both_cli_flavors() -> None:
    meta, _ = _frontmatter(_TERRAFORM / "SKILL.md")

    assert meta["description"] == (
        "Use when writing Terraform or OpenTofu, or reviewing a plan for "
        "destructive or ownership changes."
    )


@pytest.mark.parametrize("skill", [_INFRA, _TERRAFORM], ids=lambda path: path.name)
def test_every_resource_is_reachable(skill: Path) -> None:
    reached = _reachable(skill / "SKILL.md")
    resources = [
        path.resolve()
        for folder in ("references", "assets")
        for path in (skill / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]

    assert [path for path in resources if path not in reached] == []


@pytest.mark.parametrize(
    "reference",
    [
        *sorted(
            path
            for path in (_INFRA / "references").glob("iac-*.md")
            if path.name != "iac-selection.md"
        ),
        _TERRAFORM / "references/providers-and-clouds.md",
    ],
    ids=lambda path: path.name,
)
def test_references_cite_official_sources(reference: Path) -> None:
    text = reference.read_text(encoding="utf-8")
    sources = text.partition("\n## Sources\n")[2]

    assert sources, f"{reference.name} has no Sources section"
    links = re.findall(r"<(https?://[^>]+)>", sources)
    assert links
    assert all(link.startswith("https://") for link in links)
    assert "2026-10" in text


@pytest.mark.parametrize(
    "template",
    sorted((_INFRA / "assets/templates").glob("iac-*.md.template")),
    ids=lambda path: path.name,
)
def test_selection_templates_have_placeholders(template: Path) -> None:
    text = template.read_text(encoding="utf-8")

    assert text.startswith("# ")
    assert "<" in text
    assert "Facts verified on" in text


@pytest.mark.parametrize("template", _HCL_TEMPLATES, ids=lambda path: path.as_posix())
def test_cloud_blueprint_hcl_is_balanced(template: Path) -> None:
    text = template.read_text(encoding="utf-8")

    assert text.strip()
    assert text.endswith("\n")
    assert "\r" not in text
    assert _hcl_balanced(text), template.name


@pytest.mark.parametrize(
    ("text", "balanced"),
    [
        ('a = "${var.x}-${var.y}"\nb = { c = [1, (2)] }\n', True),
        ('# comment with { and "\nblock {\n  a = "x}"\n}\n', True),
        ("/* { */ x = [1]\n", True),
        ("block {\n  a = [1, 2\n}\n", False),
        ('a = "unterminated\n', False),
        ("a = 1 }\n", False),
    ],
)
def test_balance_checker_detects_errors(text: str, balanced: bool) -> None:
    assert _hcl_balanced(text) is balanced


def test_cloud_blueprints_keep_secure_defaults() -> None:
    aws = {
        path.name: path.read_text(encoding="utf-8")
        for path in (_BLUEPRINT / "aws").iterdir()
    }
    gcp = {
        path.name: path.read_text(encoding="utf-8")
        for path in (_BLUEPRINT / "gcp").iterdir()
    }

    assert 'backend "s3" {}' in aws["versions.tf.template"]
    assert re.search(r"(?m)^use_lockfile\s*=\s*true$", aws["backend.hcl.template"])
    assert not re.search(r"(?m)^dynamodb_table", aws["backend.hcl.template"])
    assert "default_tags" in aws["providers.tf.template"]
    for setting in (
        "block_public_acls       = true",
        "restrict_public_buckets = true",
        'status = "Enabled"',
        "aws:SecureTransport",
        "BucketOwnerEnforced",
    ):
        assert setting in aws["main.tf.template"]
    assert 'backend "gcs" {}' in gcp["versions.tf.template"]
    assert "default_labels" in gcp["providers.tf.template"]
    for setting in (
        "uniform_bucket_level_access = true",
        'public_access_prevention = "enforced"',
        "enabled = true",
    ):
        assert setting in gcp["main.tf.template"]


def test_tofu_workflow_parses_and_pins_opentofu() -> None:
    workflow = yaml.safe_load(_TOFU_WORKFLOW.read_text(encoding="utf-8"))

    assert isinstance(workflow, dict)
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["plan"]["steps"]
    uses = [step["uses"] for step in steps if "uses" in step]
    assert "opentofu/setup-opentofu@PIN_FULL_COMMIT_SHA" in uses
    setup = next(step for step in steps if "setup-opentofu" in step.get("uses", ""))
    assert setup["with"]["tofu_wrapper"] is False
    assert workflow["jobs"]["plan"]["permissions"]["id-token"] == "write"


def test_cloud_instruction_is_narrow_and_names_owner() -> None:
    path = _INSTRUCTIONS / "kit-cloud-iac.instructions.md"
    meta, body = _frontmatter(path)
    skills = {item.name for item in (_PACKAGE / "skills").iterdir()}

    assert set(meta) == {"description", "applyTo"}
    scopes = meta["applyTo"].split(",")
    assert "**" not in scopes
    assert "**/*" not in scopes
    assert "**/cdk.json" in scopes
    assert path.name.removesuffix(".instructions.md") not in skills
    last = body.strip().splitlines()[-1]
    owner = re.search(r"`(kit-[a-z-]+)`", last)
    assert owner
    assert owner[1] in skills


@pytest.mark.parametrize(
    "path",
    [
        _INSTRUCTIONS / "kit-cloud-iac.instructions.md",
        _INSTRUCTIONS / "kit-iac.instructions.md",
        _TERRAFORM.parents[1] / "instructions/kit-terraform.instructions.md",
    ],
    ids=lambda path: path.name,
)
def test_instruction_line_budget(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    assert len(text.splitlines()) <= _MAX_INSTRUCTION_LINES


def test_reviewer_classifies_aws_and_google_resources_generically() -> None:
    analyze = _reviewer()["analyze_plan"]
    assert callable(analyze)
    plan = _plan(
        [
            ("aws_s3_bucket.this", _AWS, ["delete", "create"]),
            ("aws_iam_role.deploy", _AWS, ["update"]),
            ("aws_s3_bucket_versioning.this", _TOFU_AWS, ["no-op"]),
            ("google_storage_bucket.this", _GOOGLE, ["delete"]),
            ("google_project_iam_member.reader", _GOOGLE, ["create"]),
            ("data_source_like.read", _GOOGLE, ["read"]),
        ]
    )

    groups = analyze(plan)

    assert isinstance(groups, dict)
    assert groups["replace"] == ["aws_s3_bucket.this"]
    assert groups["update"] == ["aws_iam_role.deploy"]
    assert groups["no-op"] == ["aws_s3_bucket_versioning.this"]
    assert groups["delete"] == ["google_storage_bucket.this"]
    assert groups["create"] == ["google_project_iam_member.reader"]
    assert groups["read"] == ["data_source_like.read"]


def test_reviewer_flags_aws_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan(
        [
            ("aws_s3_bucket.this", _AWS, ["create", "delete"]),
            ("aws_s3_bucket_policy.this", _AWS, ["update"]),
        ]
    )

    assert _run_reviewer(plan, tmp_path, monkeypatch) == 4
    output = capsys.readouterr()
    assert json.loads(output.out)["summary"]["replace"] == 1
    assert "no apply is authorized" in output.err


def test_reviewer_flags_google_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan(
        [
            ("google_storage_bucket.this", _GOOGLE, ["delete"]),
            ("google_compute_network.main", _GOOGLE, ["delete", "create"]),
        ]
    )

    assert _run_reviewer(plan, tmp_path, monkeypatch) == 3
    summary = json.loads(capsys.readouterr().out)["summary"]
    assert summary["delete"] == 1
    assert summary["replace"] == 1


def test_reviewer_passes_non_destructive_plan_across_clouds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan(
        [
            ("aws_s3_bucket.this", _TOFU_AWS, ["create"]),
            ("google_storage_bucket.this", _GOOGLE, ["update"]),
            ("aws_s3_bucket_versioning.this", _AWS, ["no-op"]),
        ]
    )

    assert _run_reviewer(plan, tmp_path, monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["create"] == 1


def test_reviewer_rejects_incomplete_cloud_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan([("aws_s3_bucket.this", _AWS, ["create"])])
    plan["complete"] = False

    assert _run_reviewer(plan, tmp_path, monkeypatch) == 2
    assert "Cannot review plan" in capsys.readouterr().err
