import ast
import inspect
import sys
from types import ModuleType
from typing import Final

import pytest

from platform_kit_runtime import documents, retrieval
from platform_kit_runtime.application import retrieval as application
from platform_kit_runtime.core import retrieval as core_package
from platform_kit_runtime.core.retrieval import (
    chunking,
    evaluation,
    models,
    ocr,
    ports,
)
from platform_kit_runtime.infrastructure import retrieval as infrastructure_package
from platform_kit_runtime.infrastructure.retrieval import (
    azure_failures,
    azure_search,
    embeddings,
    failures,
)
from platform_kit_runtime.infrastructure.retrieval import ocr as ocr_adapter

pytestmark = pytest.mark.unit

CORE: Final[tuple[ModuleType, ...]] = (
    core_package,
    chunking,
    evaluation,
    models,
    ocr,
    ports,
)
INFRASTRUCTURE: Final[tuple[ModuleType, ...]] = (
    infrastructure_package,
    azure_failures,
    azure_search,
    embeddings,
    failures,
    ocr_adapter,
)


def imported(nodes: list[ast.stmt] | ast.AST) -> set[str]:
    roots = nodes if isinstance(nodes, list) else [nodes]
    names: set[str] = set()
    for node in (child for root in roots for child in ast.walk(root)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            names.add(node.module)
    return names


def tree(module: ModuleType) -> ast.Module:
    return ast.parse(inspect.getsource(module))


def is_stdlib(name: str) -> bool:
    return name.split(".", maxsplit=1)[0] in sys.stdlib_module_names


@pytest.mark.parametrize("module", CORE)
def test_retrieval_core_imports_only_stdlib_and_core(module: ModuleType) -> None:
    assert all(
        is_stdlib(name) or name.startswith("platform_kit_runtime.core.")
        for name in imported(tree(module))
    )


def test_retrieval_application_depends_only_on_core() -> None:
    assert all(
        is_stdlib(name) or name.startswith("platform_kit_runtime.core.")
        for name in imported(tree(application))
    )


@pytest.mark.parametrize("module", INFRASTRUCTURE)
def test_retrieval_adapters_do_not_depend_on_outer_layers(module: ModuleType) -> None:
    internal = {
        name
        for name in imported(tree(module))
        if name.startswith("platform_kit_runtime")
    }
    assert all(
        name.startswith(
            (
                "platform_kit_runtime.core.",
                "platform_kit_runtime.infrastructure.retrieval.",
            )
        )
        for name in internal
    )


def test_shared_failure_classification_is_vendor_free() -> None:
    assert all(
        is_stdlib(name) or name.startswith("platform_kit_runtime.core.")
        for name in imported(tree(failures))
    )


@pytest.mark.parametrize("module", [retrieval, documents])
def test_facades_load_vendor_sdks_only_on_demand(module: ModuleType) -> None:
    body = tree(module).body
    eager = imported(
        [node for node in body if isinstance(node, ast.Import | ast.ImportFrom)]
    )
    functions = ast.FunctionDef | ast.AsyncFunctionDef
    lazy = imported([node for node in body if isinstance(node, functions)])
    assert all(
        is_stdlib(name)
        or name.startswith(
            ("platform_kit_runtime.core.", "platform_kit_runtime.application.")
        )
        for name in eager
    )
    assert lazy
    assert all(
        name.startswith("platform_kit_runtime.infrastructure.retrieval.")
        for name in lazy
    )


@pytest.mark.parametrize("module", [retrieval, documents])
def test_facade_exports_are_sorted_and_resolvable(module: ModuleType) -> None:
    exported: list[str] = vars(module)["__all__"]
    assert exported == sorted(exported)
    assert all(hasattr(module, name) for name in exported)
