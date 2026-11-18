import ast
import inspect
import sys
from types import ModuleType

import pytest

from platform_kit_runtime.application import ai as application
from platform_kit_runtime.core import ai as core
from platform_kit_runtime.infrastructure import litellm as infrastructure

pytestmark = pytest.mark.unit


def imports(module: ModuleType) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            result.add(node.module)
    return result


def test_ai_core_imports_only_stdlib() -> None:
    assert all(
        name.split(".")[0] in sys.stdlib_module_names
        or name.startswith("platform_kit_runtime.core.")
        for name in imports(core)
    )


@pytest.mark.parametrize("module", [application, infrastructure])
def test_ai_outer_layers_depend_only_on_core_and_stdlib(module: ModuleType) -> None:
    assert all(
        name.startswith("platform_kit_runtime.core.")
        or name.split(".")[0] in sys.stdlib_module_names
        for name in imports(module)
    )
