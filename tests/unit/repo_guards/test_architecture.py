"""Package import direction and forbidden annotation architecture contracts."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SOURCE = Path(__file__).parents[3] / "src" / "agent_kit"


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


def test_core_is_stdlib_only_and_other_layers_point_inward() -> None:
    violations: list[str] = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = _first_party_imports(tree)
        relative = path.relative_to(SOURCE).as_posix()
        if relative.startswith("core/") and any(
            not item.startswith("agent_kit.core.") for item in imports
        ):
            violations.append(f"{relative}: Core imports outside Core")
        if relative.startswith("core/") and _nonstandard_imports(tree):
            violations.append(f"{relative}: Core imports a non-stdlib dependency")
        if relative.startswith("application/") and any(
            item.startswith(("agent_kit.infrastructure", "agent_kit.presentation"))
            for item in imports
        ):
            violations.append(f"{relative}: Application imports outward")
        if relative.startswith("infrastructure/") and any(
            item.startswith(("agent_kit.application", "agent_kit.presentation"))
            for item in imports
        ):
            violations.append(f"{relative}: Infrastructure imports outward")
        if relative.startswith("presentation/") and any(
            item.startswith(("agent_kit.infrastructure", "agent_kit.composition"))
            for item in imports
        ):
            violations.append(f"{relative}: Presentation imports outward")
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
