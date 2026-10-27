"""Copyable templates must pass the real toolchains they target, offline."""

import ast
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

_PACKAGES = Path(__file__).resolve().parents[3] / "packages"
_PY_SUFFIX = ".py.template"
_RUFF_RULES = "F,E9,PLE,B006,B008"
_TIMEOUT_SECONDS = 300
# Top-level packages that templates use for the consumer's own modules.
_LOCAL_ROOTS = frozenset(
    {
        "app",
        "llm",
        "myapp",
        "retrieval",
        "shop",
        "streaming",
        "tasks",
        "tests",
        "workflows",
    }
)
# Skills whose templates build on another skill's example code.
_COMPANIONS = {"kit-test-first": ("kit-hexagonal-architecture",)}
# Consumer-owned modules that templates import but deliberately do not ship.
_CONSUMER_MODULES = frozenset({"shop.infrastructure.database"})
_DESTINATION = re.compile(
    r"Copy (?:to|into|as)\s+(?P<quote>'|``)(?P<path>[^'`\n]+)\.py(?P=quote)"
)
_TERRAFORM_BLUEPRINT = (
    _PACKAGES / "terraform/.apm/skills/kit-terraform-validation/assets/blueprint"
)
_TERRAFORM_SUFFIXES = (".tf", ".tfvars", ".tftest.hcl")
_HADOLINT_CONFIG = (
    _PACKAGES / "iac/.apm/skills/kit-containers/assets/templates/hadolint.yaml.template"
)


def _skill_of(path: Path) -> Path:
    return next(parent for parent in path.parents if parent.parent.name == "skills")


def _python_templates(skill: Path) -> list[Path]:
    return sorted(skill.rglob(f"*{_PY_SUFFIX}"))


_PYTHON_SKILLS = sorted({_skill_of(path) for path in _PACKAGES.rglob(f"*{_PY_SUFFIX}")})
_DOCKERFILES = sorted(_PACKAGES.rglob("Dockerfile*.template"))


def _copy_without_suffix(template: Path, source_root: Path, target_root: Path) -> None:
    relative = template.relative_to(source_root)
    target = target_root / relative.with_name(template.name.removesuffix(".template"))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, target)


def _ruff(directory: Path) -> subprocess.CompletedProcess[str]:
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("ruff is not installed")
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--no-cache",
        "--isolated",
        "--select",
        _RUFF_RULES,
        "--target-version",
        "py313",
        "--output-format",
        "concise",
        str(directory),
    ]
    return subprocess.run(  # noqa: S603 - fixed linter invocation on copied templates
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
        cwd=directory,
    )


def _is_local(node: ast.ImportFrom) -> bool:
    module = node.module or ""
    return node.level > 0 or module.split(".")[0] in _LOCAL_ROOTS


def _node_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {
            name.id
            for target in node.targets
            for name in ast.walk(target)
            if isinstance(name, ast.Name)
        }
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    if isinstance(node, ast.TypeAlias):
        return {node.name.id}
    return _imported_names(node)


def _imported_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {(alias.asname or alias.name).split(".")[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and not _is_local(node):
        return {alias.asname or alias.name for alias in node.names}
    return set()


def _defined_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    pending: list[ast.AST] = list(tree.body)
    while pending:
        node = pending.pop()
        names |= _node_names(node)
        if isinstance(node, ast.If | ast.Try | ast.With | ast.ExceptHandler):
            pending.extend(ast.iter_child_nodes(node))
    return names


def _unresolved_imports(skill: Path, companions: tuple[Path, ...]) -> list[str]:
    provided: set[str] = set()
    for source in (skill, *companions):
        for template in _python_templates(source):
            text = template.read_text(encoding="utf-8")
            provided |= _defined_names(ast.parse(text))
            provided.add(template.name.removesuffix(_PY_SUFFIX))
            provided.update(
                Path(match.group("path")).name for match in _DESTINATION.finditer(text)
            )
    findings: list[str] = []
    for template in _python_templates(skill):
        tree = ast.parse(template.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and _is_local(node)
                and node.module not in _CONSUMER_MODULES
            ):
                findings.extend(
                    f"{template.name}: {node.module}.{alias.name}"
                    for alias in node.names
                    if alias.name not in provided
                )
    return findings


@pytest.mark.parametrize("skill", _PYTHON_SKILLS, ids=lambda skill: skill.name)
def test_python_templates_pass_ruff_correctness_rules(
    skill: Path, tmp_path: Path
) -> None:
    """Python templates have no undefined names, redefinitions, or unsafe defaults."""
    for template in _python_templates(skill):
        _copy_without_suffix(template, skill, tmp_path)

    result = _ruff(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff_gate_reports_an_undefined_name(tmp_path: Path) -> None:
    """The ruff gate fails on a synthetic template that uses an undefined name."""
    (tmp_path / "broken.py").write_text(
        "def total() -> int:\n    return missing_value\n", encoding="utf-8"
    )

    result = _ruff(tmp_path)

    assert result.returncode == 1
    assert "F821" in result.stdout


@pytest.mark.parametrize("skill", _PYTHON_SKILLS, ids=lambda skill: skill.name)
def test_python_template_imports_resolve_within_the_skill(skill: Path) -> None:
    """Every name a template imports from example modules is defined by a template."""
    companions = tuple(skill.parent / name for name in _COMPANIONS.get(skill.name, ()))

    assert _unresolved_imports(skill, companions) == []


def test_import_gate_reports_a_renamed_function(tmp_path: Path) -> None:
    """A test template importing a name its module template lacks is reported."""
    skill = tmp_path / "skills" / "kit-example"
    assets = skill / "assets"
    assets.mkdir(parents=True)
    (assets / "service.py.template").write_text(
        '"""Copy to \'shop/service.py\'."""\n\n\ndef settle() -> None:\n    pass\n',
        encoding="utf-8",
    )
    (assets / "test_service.py.template").write_text(
        "from shop.service import settle, settle_invoice\n", encoding="utf-8"
    )

    findings = _unresolved_imports(skill, ())

    assert findings == ["test_service.py.template: shop.service.settle_invoice"]


def test_terraform_blueprint_is_canonically_formatted(tmp_path: Path) -> None:
    """The Terraform blueprint passes ``terraform fmt -check`` without network access."""
    terraform = shutil.which("terraform")
    if terraform is None:
        pytest.skip("terraform is not installed")
    templates = [
        template
        for template in _TERRAFORM_BLUEPRINT.rglob("*.template")
        if template.name.removesuffix(".template").endswith(_TERRAFORM_SUFFIXES)
    ]
    for template in templates:
        _copy_without_suffix(template, _TERRAFORM_BLUEPRINT, tmp_path)

    result = subprocess.run(  # noqa: S603 - resolved terraform binary, copied templates
        [terraform, "fmt", "-check", "-recursive", "-diff", "-no-color", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
        env={**os.environ, "CHECKPOINT_DISABLE": "1", "TF_IN_AUTOMATION": "1"},
    )

    assert templates
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dockerfile", _DOCKERFILES, ids=lambda path: path.name)
def test_dockerfile_templates_pass_hadolint_with_the_shipped_config(
    dockerfile: Path, tmp_path: Path
) -> None:
    """Dockerfile templates meet the failure threshold of the shipped hadolint config."""
    hadolint = shutil.which("hadolint")
    if hadolint is None:
        pytest.skip("hadolint is not installed")
    config = tmp_path / ".hadolint.yaml"
    shutil.copyfile(_HADOLINT_CONFIG, config)
    target = tmp_path / dockerfile.name.removesuffix(".template")
    shutil.copyfile(dockerfile, target)

    result = subprocess.run(  # noqa: S603 - resolved hadolint binary, copied template
        [hadolint, "--no-color", "--config", str(config), str(target)],
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, result.stdout + result.stderr
