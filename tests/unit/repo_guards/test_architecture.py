"""Package import direction and forbidden annotation architecture contracts."""

from __future__ import annotations

import ast
from configparser import ConfigParser
from pathlib import Path
import sys

SOURCE = Path(__file__).parents[3] / "src" / "agent_kit"


def test_import_linter_enforces_the_infrastructure_boundary() -> None:
    config = ConfigParser()
    config.read(SOURCE.parents[1] / ".importlinter", encoding="utf-8")
    contracts = [
        config[section]
        for section in config.sections()
        if section.startswith("importlinter:contract:")
        and config[section].get("type") == "forbidden"
    ]

    assert any(
        "agent_kit.infrastructure" in contract.get("source_modules", "").split()
        and "agent_kit.application" in contract.get("forbidden_modules", "").split()
        for contract in contracts
    )


def test_architecture_guard_rejects_outward_infrastructure_imports() -> None:
    tree = ast.parse(
        "from agent_kit.application.services import catalog_service\n"
        "from agent_kit.core import models\n"
    )

    assert _layer_violations("infrastructure/adapter.py", tree) == [
        "infrastructure/adapter.py: Infrastructure imports outward"
    ]
    assert (
        _layer_violations(
            "infrastructure/adapter.py", ast.parse("from agent_kit.core import models")
        )
        == []
    )


def _nonstandard_imports(tree: ast.Module) -> set[str]:
    """Identify dependencies outside stdlib and the toolkit package."""
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module.partition(".")[0])
        elif isinstance(node, ast.Import):
            imports.update(alias.name.partition(".")[0] for alias in node.names)
    return imports - sys.stdlib_module_names - {"agent_kit"}


def _first_party_imports(tree: ast.Module) -> set[str]:
    """Collect absolute first-party module references."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("agent_kit.")
        ):
            modules.add(node.module)
        if isinstance(node, ast.Import):
            modules.update(
                alias.name
                for alias in node.names
                if alias.name.startswith("agent_kit.")
            )
    return modules


_OUTWARD_IMPORTS = (
    (
        "application/",
        ("agent_kit.infrastructure",),
        "Application imports outward",
    ),
    (
        "infrastructure/",
        ("agent_kit.application",),
        "Infrastructure imports outward",
    ),
)


def _core_violations(tree: ast.Module, imports: set[str]) -> list[str]:
    """Describe Core imports of other layers or non-stdlib dependencies."""
    violations: list[str] = []
    if any(not item.startswith("agent_kit.core.") for item in imports):
        violations.append("Core imports outside Core")
    if _nonstandard_imports(tree):
        violations.append("Core imports a non-stdlib dependency")
    return violations


def _layer_violations(relative: str, tree: ast.Module) -> list[str]:
    """Describe every dependency-direction violation of one source module."""
    imports = _first_party_imports(tree)
    messages = _core_violations(tree, imports) if relative.startswith("core/") else []
    messages.extend(
        message
        for prefix, forbidden, message in _OUTWARD_IMPORTS
        if relative.startswith(prefix)
        and any(item.startswith(forbidden) for item in imports)
    )
    return [f"{relative}: {message}" for message in messages]


def test_core_is_stdlib_only_and_other_layers_point_inward() -> None:
    violations: list[str] = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_layer_violations(path.relative_to(SOURCE).as_posix(), tree))
    assert violations == []


def test_core_guard_recognizes_arbitrary_non_stdlib_imports() -> None:
    """The guard is not limited to a short list of known framework packages."""
    tree = ast.parse("import arbitrary_provider\nfrom pathlib import Path\n")

    assert _nonstandard_imports(tree) == {"arbitrary_provider"}


def _is_quoted(annotation: ast.expr | None) -> bool:
    """Report a string-literal (forward-reference) annotation."""
    return isinstance(annotation, ast.Constant) and isinstance(annotation.value, str)


def _annotation_violation(node: ast.AST) -> str | None:
    """Describe one forbidden Any, cast, or quoted annotation, if present."""
    if isinstance(node, ast.Name) and node.id in {"Any", "cast"}:
        return f"forbidden name {node.id}"
    if isinstance(node, ast.arg) and _is_quoted(node.annotation):
        return "quoted argument annotation"
    if isinstance(node, ast.AnnAssign) and _is_quoted(node.annotation):
        return "quoted variable annotation"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_quoted(
        node.returns
    ):
        return "quoted return annotation"
    return None


def test_source_has_no_any_cast_or_quoted_forward_annotations() -> None:
    violations = [
        f"{path.name}: {message}"
        for path in SOURCE.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if (message := _annotation_violation(node)) is not None
    ]
    assert violations == []


def test_source_initializers_explicitly_return_none() -> None:
    violations = [
        f"{path.name}:{node.name}"
        for path in SOURCE.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)
        and node.name in {"__init__", "__post_init__"}
        and not (isinstance(node.returns, ast.Constant) and node.returns.value is None)
    ]
    assert violations == []
