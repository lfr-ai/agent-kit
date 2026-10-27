"""IaC skill resources must parse, stay reachable, and gate risky workflows."""

import ast
from collections.abc import Callable
import json
from pathlib import Path
import re
import runpy

import pytest
from scripts.check_resources import _reachable
import yaml

_SKILLS = Path(__file__).resolve().parents[3] / "packages/iac/.apm/skills"
_CHECKER = _SKILLS / "kit-ci-review/assets/check_workflow_permissions.py"
_SHA = "0123456789abcdef" * 2 + "01234567"
_WORKFLOW_TEMPLATES = sorted(
    path
    for path in _SKILLS.rglob("*.yml.template")
    if re.search(r"(?m)^on:", path.read_text(encoding="utf-8"))
)


def _checker() -> dict[str, object]:
    return runpy.run_path(str(_CHECKER))


def _main() -> Callable[[list[str]], int]:
    main = _checker()["main"]
    assert callable(main)

    def invoke(arguments: list[str]) -> int:
        result = main(arguments)
        assert isinstance(result, int)
        return result

    return invoke


def _templates(*suffixes: str) -> list[Path]:
    return sorted(
        path
        for path in _SKILLS.rglob("*.template")
        if path.name.removesuffix(".template").endswith(suffixes)
    )


def _template_id(path: Path) -> str:
    """Name a template by its skill-relative path so equal file names stay unique."""
    return path.relative_to(_SKILLS).as_posix()


@pytest.mark.parametrize("path", _templates(".json"), ids=_template_id)
def test_json_templates_parse(path: Path) -> None:
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize("path", _templates(".yml", ".yaml"), ids=_template_id)
def test_yaml_templates_parse(path: Path) -> None:
    assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize("path", _templates(".py"), ids=_template_id)
def test_python_templates_parse(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize(
    "skill", sorted(path.parent for path in _SKILLS.glob("*/SKILL.md")), ids=str
)
def test_every_reference_and_asset_is_reachable(skill: Path) -> None:
    reached = _reachable(skill / "SKILL.md")
    resources = [
        path.resolve()
        for folder in ("references", "assets")
        for path in (skill / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    assert resources
    assert [path for path in resources if path not in reached] == []


def test_checker_self_test_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert _main()(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


def test_clean_workflow_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "on: push\npermissions:\n  contents: read\njobs:\n  build:\n"
        "    runs-on: ubuntu-latest\n    steps:\n"
        f"      - uses: actions/checkout@{_SHA} # v5\n"
        "      - env:\n          REF: ${{ github.head_ref }}\n"
        '        run: echo "$REF"\n',
        encoding="utf-8",
    )
    assert _main()([str(tmp_path)]) == 0
    assert "No findings in 1 file(s)." in capsys.readouterr().out


def test_risky_workflow_reports_each_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = tmp_path / "pr.yaml"
    workflow.write_text(
        "on: pull_request_target\njobs:\n  build:\n"
        "    permissions: write-all\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - run: |\n          echo ${{ github.event.pull_request.title }}\n",
        encoding="utf-8",
    )
    assert _main()([str(workflow)]) == 1
    lines = capsys.readouterr().out.splitlines()
    prefix = workflow.as_posix()
    assert [line.split(": ", 1)[0] for line in lines] == [
        f"{prefix}:1",
        f"{prefix}:4",
        f"{prefix}:6",
        f"{prefix}:8",
    ]
    assert "top-level 'permissions'" in lines[0]
    assert "write-all" in lines[1]
    assert "mutable ref 'v4'" in lines[2]
    assert "github.event.pull_request.title" in lines[3]


def test_flags_relax_only_named_policy(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "on: push\njobs:\n  build:\n    steps:\n"
        "      - uses: my-org/setup@main\n"
        "      - run: echo ${{ runner.temp }}\n",
        encoding="utf-8",
    )
    assert _main()([str(workflow)]) == 1
    assert (
        _main()(
            [
                str(workflow),
                "--trusted-owner",
                "my-org",
                "--allow-expression",
                "runner.",
                "--no-require-permissions",
            ]
        )
        == 0
    )


@pytest.mark.parametrize(
    ("reference", "accepted"),
    [
        ("./.github/actions/setup", True),
        ("$/.github/workflows/build.yml", True),
        ("$/.github/actions/setup", True),
        (f"owner/repo/.github/workflows/build.yml@{_SHA}", True),
        (f"docker://alpine@sha256:{'a' * 64}", True),
        ("docker://alpine:3", False),
        ("owner/action@v1.2.3", False),
        (f"owner/action@{_SHA[:7]}", False),
        ("owner/action", False),
    ],
)
def test_reference_pinning_rules(reference: str, accepted: bool) -> None:
    namespace = _checker()
    options_type = namespace["Options"]
    check = namespace["check_reference"]
    assert callable(options_type)
    assert callable(check)
    options = options_type(
        trusted_owners=frozenset(), allowed_expressions=(), require_permissions=True
    )
    assert (check(reference, options) is None) is accepted


def test_missing_path_is_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main()([str(tmp_path / "absent")]) == 2
    assert "Cannot scan workflows" in capsys.readouterr().err


@pytest.mark.parametrize("path", _WORKFLOW_TEMPLATES, ids=_template_id)
def test_workflow_templates_fail_until_pinned_then_pass(
    tmp_path: Path, path: Path
) -> None:
    text = path.read_text(encoding="utf-8")
    assert "PIN_FULL_COMMIT_SHA" in text
    unpinned = tmp_path / "unpinned.yml"
    unpinned.write_text(text, encoding="utf-8")
    assert _main()([str(unpinned)]) == 1
    pinned = tmp_path / "pinned.yml"
    pinned.write_text(text.replace("PIN_FULL_COMMIT_SHA", _SHA), encoding="utf-8")
    assert _main()([str(pinned)]) == 0
