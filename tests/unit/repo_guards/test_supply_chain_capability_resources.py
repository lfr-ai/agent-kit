"""Supply-chain skill resources and the lock freshness checker behave as documented."""

from pathlib import Path
import re
import runpy

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SKILL = _ROOT / "packages/shared/.apm/skills/kit-supply-chain"
_CHECKER = runpy.run_path(str(_SKILL / "assets/check_lock_freshness.py"))
_main = _CHECKER["main"]
_LINK = re.compile(r"\]\(([^)#\s]+)")
_HASH = "sha256:" + "a" * 64
_COMMIT = "b" * 40

_MANIFEST = """
[project]
name = "demo-app"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["PyYAML >= 6, < 7", "httpx[http2]>=0.28"]

[project.optional-dependencies]
cli = ["rich>=14; python_version >= '3.13'"]

[dependency-groups]
lint = ["ruff==0.17.1"]
dev = [{include-group = "lint"}, "pytest==9.1.1"]

[tool.uv]
constraint-dependencies = ["idna>=3.10"]
"""


def _package(name: str, version: str, *, hashed: bool = True) -> str:
    digest = f', hash = "{_HASH}"' if hashed else ""
    return (
        f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        f'wheels = [{{ url = "https://example.invalid/{name}.whl"{digest} }}]\n'
    )


def _lock(
    *,
    requires_dist: str = (
        '{ name = "pyyaml", specifier = ">=6,<7" }, '
        '{ name = "httpx", extras = ["http2"], specifier = ">=0.28" }, '
        '{ name = "rich", marker = "extra == \'cli\'", specifier = ">=14" }'
    ),
    dev: str = (
        '{ name = "ruff", specifier = "==0.17.1" }, '
        '{ name = "pytest", specifier = "==9.1.1" }'
    ),
    lint: str = '{ name = "ruff", specifier = "==0.17.1" }',
    constraints: str = '{ name = "idna", specifier = ">=3.10" }',
    requires_python: str = ">=3.13",
    ruff: str = "0.17.1",
    extra_packages: str = "",
    root_name: str = "demo-app",
) -> str:
    packages = "".join(
        _package(name, version)
        for name, version in (
            ("pyyaml", "6.0.3"),
            ("httpx", "0.28.1"),
            ("rich", "14.1.0"),
            ("ruff", ruff),
            ("pytest", "9.1.1"),
        )
    )
    return (
        f'version = 1\nrequires-python = "{requires_python}"\n\n'
        f"[manifest]\nconstraints = [{constraints}]\n\n"
        f'[[package]]\nname = "{root_name}"\nversion = "0.1.0"\n'
        'source = { editable = "." }\n\n'
        f"[package.metadata]\nrequires-dist = [{requires_dist}]\n\n"
        f"[package.metadata.requires-dev]\ndev = [{dev}]\nlint = [{lint}]\n\n"
        f"{packages}{extra_packages}"
    )


def _run(tmp_path: Path, *, manifest: str = _MANIFEST, lock: str | None = None) -> int:
    project = tmp_path / "pyproject.toml"
    lockfile = tmp_path / "uv.lock"
    project.write_text(manifest, encoding="utf-8")
    lockfile.write_text(_lock() if lock is None else lock, encoding="utf-8")
    return _main(["--project", str(project), "--lock", str(lockfile)])


def _frontmatter(path: Path) -> dict[str, object]:
    _, header, _ = path.read_text(encoding="utf-8").split("---\n", 2)
    loaded = yaml.safe_load(header)
    assert isinstance(loaded, dict)
    return loaded


# Skill structure


def test_skill_metadata_is_minimal_and_within_budget() -> None:
    meta = _frontmatter(_SKILL / "SKILL.md")
    assert set(meta) == {"name", "description", "license"}
    assert meta["name"] == "kit-supply-chain"
    assert meta["license"] == "MIT"
    description = meta["description"]
    assert isinstance(description, str)
    assert description.startswith("Use when")
    assert len(description) <= 110
    body = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "## Acceptance gates" in body
    assert len(body.splitlines()) < 300


def test_every_resource_is_linked_from_the_skill() -> None:
    body = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    linked = {(_SKILL / target).resolve() for target in _LINK.findall(body)}
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (_SKILL / folder).iterdir()
        if path.is_file()
    }
    assert resources
    assert resources <= linked
    assert all(path.is_file() for path in linked)


def test_shared_owners_are_linked_by_name_not_copied() -> None:
    body = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    for owner in (
        "kit-verify-change",
        "kit-agent-runtime",
        "kit-repository-setup",
        "kit-ci-review",
        "kit-containers",
        "kit-release",
    ):
        assert f"`{owner}`" in body
    names = {path.name for path in (_SKILL / "assets").iterdir()}
    assert not names & {"check_pins.py", "license_guard.py", "dependabot.yml.template"}


@pytest.mark.parametrize(
    "reference", sorted((_SKILL / "references").glob("*.md")), ids=lambda p: p.name
)
def test_references_cite_primary_sources_with_review_date(reference: Path) -> None:
    text = reference.read_text(encoding="utf-8")
    assert "## Primary sources" in text
    assert "2026-10-23" in text
    sources = text.split("## Primary sources", 1)[1]
    assert sources.count("https://") >= 3
    for target in _LINK.findall(text):
        if ":" not in target:
            assert (reference.parent / target).is_file(), target


# Templates


def test_sbom_workflow_pins_actions_and_attests_the_sbom() -> None:
    text = (_SKILL / "assets/sbom.yml.template").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["build-and-attest"]
    assert job["permissions"]["id-token"] == "write"
    assert job["permissions"]["attestations"] == "write"
    steps = job["steps"]
    uses = [step["uses"] for step in steps if "uses" in step]
    assert uses
    assert all(item.split("@", 1)[1] == "PIN_FULL_COMMIT_SHA" for item in uses)
    assert any(step.get("with", {}).get("sbom-path") for step in steps)
    assert "uv lock --check" in text
    assert "--no-default-groups" in text
    assert "persist-credentials: false" in text


@pytest.mark.parametrize(
    ("name", "headings"),
    [
        (
            "dependency-adoption-review.md.template",
            (
                "## Alternatives considered",
                "## Name and source verification",
                "## Decision",
            ),
        ),
        (
            "supply-chain-policy.md.template",
            ("## Admission", "## Audit", "## Updates", "## Incidents"),
        ),
    ],
)
def test_markdown_templates_keep_their_sections(
    name: str, headings: tuple[str, ...]
) -> None:
    text = (_SKILL / "assets" / name).read_text(encoding="utf-8")
    for heading in headings:
        assert heading in text
    assert "<placeholder>" in text or "`<" in text


# Lock freshness checker


def test_checker_self_test_passes() -> None:
    assert _CHECKER["self_test"]() == []
    assert _main(["--self-test"]) == 0


def test_fresh_hashed_lock_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path) == 0
    assert "0 findings" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("lock_options", "expected"),
    [
        (
            {"requires_dist": '{ name = "pyyaml", specifier = ">=6,<7" }'},
            "declares httpx[http2]>=0.28",
        ),
        (
            {"dev": '{ name = "ruff", specifier = "==0.17.1" }'},
            "'dev' declares pytest==9.1.1",
        ),
        ({"lint": ""}, "'lint' declares ruff==0.17.1"),
        (
            {"lint": '{ name = "ruff", specifier = "==0.17.1" }, { name = "black" }'},
            "records black for dependency group 'lint'",
        ),
        ({"constraints": ""}, "tool.uv.constraint-dependencies declares idna>=3.10"),
        ({"requires_python": ">=3.12"}, "requires-python is '>=3.13'"),
        ({"ruff": "0.16.0"}, "pin drift: ruff==0.17.1"),
        ({"root_name": "other"}, "no local package 'demo-app'"),
        (
            {"extra_packages": _package("idna", "3.10", hashed=False)},
            "idna==3.10: a distribution file has no sha256",
        ),
        (
            {
                "extra_packages": '[[package]]\nname = "tool"\nversion = "1.0.0"\n'
                'source = { git = "https://example.invalid/tool.git?rev=main#main" }\n'
            },
            "tool==1.0.0: Git source is not pinned",
        ),
        (
            {
                "extra_packages": '[[package]]\nname = "bare"\nversion = "1.0.0"\n'
                'source = { registry = "https://pypi.org/simple" }\n'
            },
            "bare==1.0.0: no distribution files are locked",
        ),
    ],
)
def test_stale_or_unverifiable_locks_are_reported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    lock_options: dict[str, str],
    expected: str,
) -> None:
    assert _run(tmp_path, lock=_lock(**lock_options)) == 1
    assert expected in capsys.readouterr().out


def test_pinned_git_and_local_sources_pass(tmp_path: Path) -> None:
    extra = (
        '[[package]]\nname = "tool"\nversion = "1.0.0"\n'
        f'source = {{ git = "https://example.invalid/tool.git?rev=v1#{_COMMIT}" }}\n'
        '[[package]]\nname = "local"\nversion = "0.0.1"\n'
        'source = { directory = "libs/local" }\n'
    )
    assert _run(tmp_path, lock=_lock(extra_packages=extra)) == 0


def test_legacy_dev_dependencies_merge_into_the_dev_group(tmp_path: Path) -> None:
    manifest = _MANIFEST.replace(
        'constraint-dependencies = ["idna>=3.10"]',
        'constraint-dependencies = ["idna>=3.10"]\ndev-dependencies = ["rich>=14"]',
    )
    dev = (
        '{ name = "ruff", specifier = "==0.17.1" }, '
        '{ name = "pytest", specifier = "==9.1.1" }, '
        '{ name = "rich", specifier = ">=14" }'
    )
    assert _run(tmp_path, manifest=manifest, lock=_lock(dev=dev)) == 0
    assert _run(tmp_path, manifest=manifest) == 1


@pytest.mark.parametrize(
    ("manifest", "lock"),
    [
        (
            _MANIFEST.replace('{include-group = "lint"}', '{include-group = "dev"}'),
            None,
        ),
        (
            _MANIFEST.replace('{include-group = "lint"}', '{include-group = "nope"}'),
            None,
        ),
        (_MANIFEST.replace('name = "demo-app"\n', ""), None),
        (_MANIFEST, 'version = 1\npackage = "broken"\n'),
        (_MANIFEST, "version = 1\n[[package]]\n"),
        (_MANIFEST, "not = toml = at all"),
    ],
    ids=["include-cycle", "unknown-group", "no-name", "bad-package", "unnamed", "toml"],
)
def test_unusable_input_exits_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    manifest: str,
    lock: str | None,
) -> None:
    assert _run(tmp_path, manifest=manifest, lock=lock) == 2
    assert "cannot check" in capsys.readouterr().err


def test_missing_files_exit_two(tmp_path: Path) -> None:
    assert _main(["--project", str(tmp_path / "absent.toml")]) == 2


def test_pin_drift_in_an_optional_dependency_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _MANIFEST.replace("cli = [", 'docs = ["mkdocs==1.5.0"]\ncli = [')
    requires_dist = (
        '{ name = "pyyaml", specifier = ">=6,<7" }, '
        '{ name = "httpx", extras = ["http2"], specifier = ">=0.28" }, '
        '{ name = "rich", marker = "extra == \'cli\'", specifier = ">=14" }, '
        '{ name = "mkdocs", marker = "extra == \'docs\'", specifier = "==1.5.0" }'
    )
    lock = _lock(
        requires_dist=requires_dist, extra_packages=_package("mkdocs", "1.6.0")
    )
    assert _run(tmp_path, manifest=manifest, lock=lock) == 1
    output = capsys.readouterr().out
    assert "pin drift: mkdocs==1.5.0 is declared but the lock holds 1.6.0" in output
    assert "stale lock" not in output
    fixed = _lock(
        requires_dist=requires_dist, extra_packages=_package("mkdocs", "1.5.0")
    )
    assert _run(tmp_path, manifest=manifest, lock=fixed) == 0


def test_pin_drift_in_uv_constraints_is_reported_but_not_build_constraints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _MANIFEST.replace('["idna>=3.10"]', '["idna==3.10"]') + (
        'build-constraint-dependencies = ["setuptools==80.0.0"]\n'
    )
    lock = _lock(
        constraints='{ name = "idna", specifier = "==3.10" }',
        extra_packages=_package("idna", "3.11") + _package("setuptools", "81.0.0"),
    ).replace(
        "[manifest]\n",
        '[manifest]\nbuild-constraints = [{ name = "setuptools", specifier = "==80.0.0" }]\n',
    )
    assert _run(tmp_path, manifest=manifest, lock=lock) == 1
    output = capsys.readouterr().out
    assert "pin drift: idna==3.10 is declared but the lock holds 3.11" in output
    assert "setuptools" not in output


def test_requirement_parsing_normalizes_names_extras_and_clauses() -> None:
    parse = _CHECKER["parse_requirement"]
    requirement = parse("Py_YAML[Fast, c] ( >= 6 , <7 ) ; python_version < '4'")
    assert requirement.render() == "py-yaml[c,fast]<7,>=6"
    assert parse("tool @ https://example.invalid/tool.whl").render() == "tool"
    with pytest.raises(ValueError, match="unsupported requirement"):
        parse("[broken")
