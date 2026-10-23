"""Executable checkers and copyable templates for backend data skills stay valid."""

import ast
from collections.abc import Callable
import json
from pathlib import Path
import re
import runpy
import tomllib

import pytest
import yaml

_SKILLS = Path(__file__).resolve().parents[3] / "packages/backend/.apm/skills"
_OWNED = (
    "kit-config",
    "kit-database-migrations",
    "kit-jinja",
    "kit-pydantic-v2",
    "kit-polars-v2",
    "kit-python-package",
)
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _checker(skill: str, name: str) -> dict[str, object]:
    return runpy.run_path(str(_SKILLS / skill / "assets" / name))


def _main(namespace: dict[str, object]) -> Callable[..., object]:
    main = namespace["main"]
    assert callable(main)
    return main


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _templates(*suffixes: str) -> list[Path]:
    return sorted(
        path
        for skill in _OWNED
        for path in (_SKILLS / skill / "assets").rglob("*.template")
        if path.name.removesuffix(".template").endswith(suffixes)
    )


@pytest.mark.parametrize(
    ("skill", "name"),
    [
        ("kit-config", "check_from_config_pattern.py"),
        ("kit-database-migrations", "check_migration_safety.py"),
        ("kit-jinja", "check_template_safety.py"),
        ("kit-pydantic-v2", "check_pydantic_v2.py"),
        ("kit-polars-v2", "check_polars_usage.py"),
        ("kit-python-package", "check_pyproject.py"),
    ],
)
def test_checker_self_tests_pass(
    skill: str, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(_checker(skill, name))(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


def test_config_checker_flags_env_reads_outside_settings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _main(_checker("kit-config", "check_from_config_pattern.py"))
    _write(tmp_path / "app/settings.py", "import os\nURL = os.environ['ORDERS_URL']\n")
    service = _write(
        tmp_path / "app/orders.py", "import os\nLIMIT = os.getenv('ORDERS_LIMIT')\n"
    )

    assert main([str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert f"{service.as_posix()}:2: environment access" in output
    assert "settings.py" not in output

    service.write_text(
        "import os\nLIMIT = os.getenv('X')  # config: env-access-reviewed\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 0


def test_config_checker_allow_glob_is_configurable(tmp_path: Path) -> None:
    main = _main(_checker("kit-config", "check_from_config_pattern.py"))
    _write(
        tmp_path / "boot/env_loader.py", "from os import environ\nX = environ['A']\n"
    )

    assert main([str(tmp_path)]) == 1
    assert main([str(tmp_path), "--allow", "*boot/*.py"]) == 0


def test_migration_checker_flags_risky_upgrade_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _main(_checker("kit-database-migrations", "check_migration_safety.py"))
    revision = _write(
        tmp_path / "versions/0002_drop.py",
        "from alembic import op\n\n\ndef upgrade():\n"
        "    op.drop_column('orders', 'note')\n"
        "    op.create_index('ix', 'orders', ['a'])\n\n\n"
        "def downgrade():\n    op.drop_table('orders')\n",
    )

    assert main([str(tmp_path / "versions")]) == 1
    output = capsys.readouterr().out
    assert f"{revision.as_posix()}:5: upgrade: op.drop_column" in output
    assert f"{revision.as_posix()}:6: upgrade: op.create_index" in output
    assert "downgrade" not in output
    assert main([str(revision), "--dialect", "generic"]) == 1
    assert main([str(revision), "--include-downgrade"]) == 1


def test_migration_checker_accepts_safe_and_waived_revisions(tmp_path: Path) -> None:
    main = _main(_checker("kit-database-migrations", "check_migration_safety.py"))
    _write(
        tmp_path / "0003_safe.py",
        "import sqlalchemy as sa\nfrom alembic import op\n\n\ndef upgrade():\n"
        "    op.add_column('orders', sa.Column('n', sa.Text(), nullable=True))\n"
        "    with op.get_context().autocommit_block():\n"
        "        op.create_index('ix', 'orders', ['n'], postgresql_concurrently=True)\n"
        "    # migration-safety: reviewed (unused since two releases)\n"
        "    op.drop_column('orders', 'legacy')\n",
    )

    assert main([str(tmp_path)]) == 0


def test_migration_revision_template_is_clean_under_its_own_checker(
    tmp_path: Path,
) -> None:
    main = _main(_checker("kit-database-migrations", "check_migration_safety.py"))
    template = _SKILLS / "kit-database-migrations/assets/alembic_revision.py.template"
    revision = _write(tmp_path / "rev.py", template.read_text(encoding="utf-8"))

    assert main([str(revision)]) == 0


def test_template_checker_flags_unsafe_environment_and_markup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _main(_checker("kit-jinja", "check_template_safety.py"))
    _write(tmp_path / "render.py", "import jinja2\nENV = jinja2.Environment()\n")
    _write(tmp_path / "page.html", "<p>{{ body|safe }}</p>\n")

    assert main([str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "render.py:2: Environment without autoescape" in output
    assert "page.html:1: '|safe' disables escaping" in output


def test_template_checker_accepts_safe_setup(tmp_path: Path) -> None:
    main = _main(_checker("kit-jinja", "check_template_safety.py"))
    _write(
        tmp_path / "render.py",
        "from jinja2 import Environment, StrictUndefined, select_autoescape\n"
        "ENV = Environment(autoescape=select_autoescape(), undefined=StrictUndefined)\n",
    )
    _write(tmp_path / "page.j2", "{% include 'footer.html' %}{{ name }}\n")
    renderer = _SKILLS / "kit-jinja/assets/renderer.py.template"
    _write(tmp_path / "renderer.py", renderer.read_text(encoding="utf-8"))

    assert main([str(tmp_path)]) == 0


def test_pydantic_checker_flags_v1_and_accepts_v2(tmp_path: Path) -> None:
    main = _main(_checker("kit-pydantic-v2", "check_pydantic_v2.py"))
    legacy = _write(
        tmp_path / "legacy.py",
        "from pydantic import BaseModel, validator\n\n\nclass A(BaseModel):\n"
        "    class Config:\n        orm_mode = True\n",
    )

    assert main([str(legacy)]) == 1
    patterns = sorted((_SKILLS / "kit-pydantic-v2/assets").rglob("*.py.template"))
    for index, template in enumerate(patterns):
        _write(tmp_path / f"v2/m{index}.py", template.read_text(encoding="utf-8"))
    assert main([str(tmp_path / "v2")]) == 0


def test_polars_checker_flags_eager_reads_and_accepts_templates(tmp_path: Path) -> None:
    main = _main(_checker("kit-polars-v2", "check_polars_usage.py"))
    bad = _write(
        tmp_path / "bad.py",
        "import polars as pl\nout = pl.read_csv('a.csv').lazy().collect()\n",
    )

    assert main([str(bad)]) == 1
    templates = sorted((_SKILLS / "kit-polars-v2/assets").rglob("*.py.template"))
    for index, template in enumerate(templates):
        _write(tmp_path / f"ok/m{index}.py", template.read_text(encoding="utf-8"))
    assert main([str(tmp_path / "ok")]) == 0


def test_pyproject_checker_accepts_template_and_rejects_dev_tools(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _main(_checker("kit-python-package", "check_pyproject.py"))
    template = _SKILLS / "kit-python-package/assets/pyproject.toml.template"
    project = _write(tmp_path / "pyproject.toml", template.read_text(encoding="utf-8"))
    _write(tmp_path / "README.md", "# Example\n")

    assert main([str(tmp_path)]) == 0
    project.write_text(
        project.read_text(encoding="utf-8").replace(
            '"httpx>=0.27",', '"httpx>=0.27",\n    "pytest>=8",'
        ),
        encoding="utf-8",
    )
    assert main([str(project)]) == 1
    assert "development tool 'pytest'" in capsys.readouterr().out


def test_pyproject_checker_reports_missing_file(tmp_path: Path) -> None:
    main = _main(_checker("kit-python-package", "check_pyproject.py"))

    assert main([str(tmp_path / "absent.toml")]) == 1


@pytest.mark.parametrize(
    "path", _templates(".py", ".spec"), ids=lambda p: p.relative_to(_SKILLS).as_posix()
)
def test_python_templates_parse(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize(
    "path", _templates(".json"), ids=lambda p: p.relative_to(_SKILLS).as_posix()
)
def test_json_templates_parse(path: Path) -> None:
    json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "path", _templates(".yml", ".yaml"), ids=lambda p: p.relative_to(_SKILLS).as_posix()
)
def test_yaml_templates_parse(path: Path) -> None:
    assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize(
    "path", _templates(".toml"), ids=lambda p: p.relative_to(_SKILLS).as_posix()
)
def test_toml_templates_parse(path: Path) -> None:
    assert tomllib.loads(path.read_text(encoding="utf-8"))


def test_pydantic_patterns_avoid_v1_shims() -> None:
    for template in (_SKILLS / "kit-pydantic-v2/assets/patterns").glob("*.template"):
        tree = ast.parse(template.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("pydantic.v1")
            for node in ast.walk(tree)
        )


@pytest.mark.parametrize("skill", _OWNED)
def test_every_resource_is_linked_from_its_skill(skill: str) -> None:
    home = _SKILLS / skill
    pending = [home / "SKILL.md"]
    reached: set[Path] = set()
    while pending:
        current = pending.pop().resolve()
        if current in reached:
            continue
        reached.add(current)
        if current.suffix != ".md":
            continue
        for target in _LINK.findall(current.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "<")):
                continue
            resolved = (current.parent / target.partition("#")[0]).resolve()
            assert resolved.is_relative_to(home.resolve()), target
            assert resolved.is_file(), f"{current.name}: broken link {target}"
            pending.append(resolved)
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (home / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert resources - reached == set()
