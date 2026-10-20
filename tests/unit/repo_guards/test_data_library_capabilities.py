"""Source contracts for optional Pydantic v2 and Polars 2 guidance."""

import ast
import json
from pathlib import Path

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _ROOT / "packages/backend/.apm"
_PYDANTIC = _BACKEND / "skills/kit-pydantic-v2"
_POLARS = _BACKEND / "skills/kit-polars-v2"


def test_backend_and_fullstack_profiles_include_versioned_data_skills() -> None:
    """Data-library guidance is selected with backend work, not shared globally."""
    snapshot = FileCatalogAdapter().load(_ROOT)
    service = CatalogService()

    backend = service.compose(snapshot, "backend", (), (), skills=())
    fullstack = service.compose(snapshot, "fullstack", (), (), skills=())
    frontend = service.compose(snapshot, "frontend", (), (), skills=())

    for plan in (backend, fullstack):
        paths = {item.relative_path for item in plan.files}
        assert ".apm/skills/kit-pydantic-v2/SKILL.md" in paths
        assert ".apm/skills/kit-polars-v2/SKILL.md" in paths
        assert ".apm/instructions/kit-pydantic-v2.instructions.md" in paths
        assert ".apm/instructions/kit-polars-v2.instructions.md" in paths

    frontend_paths = {item.relative_path for item in frontend.files}
    assert not any("kit-pydantic-v2" in path for path in frontend_paths)
    assert not any("kit-polars-v2" in path for path in frontend_paths)


def test_pydantic_templates_are_v2_only_and_parse() -> None:
    """Copyable examples use v2 APIs and do not carry v1 compatibility shims."""
    templates = sorted((_PYDANTIC / "assets").glob("*.py.template"))
    assert {path.name for path in templates} == {
        "cross_field_model.py.template",
        "request_model.py.template",
        "settings.py.template",
        "test_request_model.py.template",
    }
    trees = {
        path.name: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in templates
    }
    request = trees["request_model.py.template"]
    validator = trees["cross_field_model.py.template"]
    settings = trees["settings.py.template"]
    test = trees["test_request_model.py.template"]

    assert any(
        isinstance(node, ast.Name) and node.id == "ConfigDict"
        for node in ast.walk(request)
    )
    assert any(
        isinstance(node, ast.Name) and node.id == "model_validator"
        for node in ast.walk(validator)
    )
    assert any(
        isinstance(node, ast.ImportFrom) and node.module == "pydantic_settings"
        for node in ast.walk(settings)
    )
    assert any(
        isinstance(node, ast.Name) and node.id == "SecretStr"
        for node in ast.walk(settings)
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "model_validate"
        for node in ast.walk(test)
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "model_dump"
        for node in ast.walk(test)
    )
    for tree in trees.values():
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("pydantic.v1")
            for node in ast.walk(tree)
        )


def test_polars_templates_use_lazy_v2_pipeline_and_stable_order() -> None:
    """Polars examples keep lazy execution and explicitly sort observable output."""
    templates = sorted((_POLARS / "assets").glob("*.py.template"))
    assert {path.name for path in templates} == {
        "lazy_pipeline.py.template",
        "test_lazy_pipeline.py.template",
    }
    trees = {
        path.name: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in templates
    }
    pipeline = trees["lazy_pipeline.py.template"]
    test = trees["test_lazy_pipeline.py.template"]
    pipeline_text = (_POLARS / "assets/lazy_pipeline.py.template").read_text()

    assert "pl.scan_parquet" in pipeline_text
    assert "maintain_order" not in pipeline_text
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "group_by"
        for node in ast.walk(pipeline)
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "sort"
        for node in ast.walk(pipeline)
    )
    assert any(
        isinstance(node, ast.Name) and node.id == "assert_frame_equal"
        for node in ast.walk(test)
    )


def test_versioned_instructions_have_narrow_globs_and_references() -> None:
    """Version-specific guidance is scoped and points to its full procedure."""
    expectations = (
        (
            _BACKEND / "instructions/kit-pydantic-v2.instructions.md",
            ("*dto*.py", "*schema*.py", "*request*.py", "*response*.py"),
            "kit-pydantic-v2/SKILL.md",
        ),
        (
            _BACKEND / "instructions/kit-polars-v2.instructions.md",
            ("*polars*.py", "*dataframe*.py", "*analytics*.py"),
            "kit-polars-v2/SKILL.md",
        ),
    )
    for path, expected_globs, target in expectations:
        text = path.read_text(encoding="utf-8")
        assert all(glob in text for glob in expected_globs)
        assert "**/*.py" not in text
        assert target in text


def test_one_data_library_session_omits_the_other_library() -> None:
    """A task can activate one versioned library without the neighboring skill."""
    snapshot = FileCatalogAdapter().load(_ROOT)
    plan = CatalogService().compose(
        snapshot,
        "backend",
        (),
        (),
        skills=("kit-pydantic-v2", "kit-python-service"),
    )
    paths = {item.relative_path for item in plan.files}

    assert ".apm/skills/kit-pydantic-v2/SKILL.md" in paths
    assert not any("kit-polars-v2" in path for path in paths)
    assert ".apm/instructions/kit-pydantic-v2.instructions.md" in paths
    assert ".apm/instructions/kit-polars-v2.instructions.md" not in paths
    assert ".apm/instructions/kit-backend.instructions.md" in paths
    report = json.loads(
        next(
            item.content
            for item in plan.files
            if item.relative_path == ".apm/selection.json"
        )
    )
    assert "kit-pydantic-v2" in report["instructions"]
    assert "kit-python-conventions" in report["instructions"]
    assert "kit-polars-v2" not in report["instructions"]
