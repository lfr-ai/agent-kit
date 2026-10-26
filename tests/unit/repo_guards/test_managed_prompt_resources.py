"""Run the shipped managed-prompt examples in memory, without an SDK or network."""

from collections.abc import Mapping
from pathlib import Path
import runpy
import sys
from types import FunctionType, ModuleType

import pytest

_ASSETS = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "ai"
    / ".apm"
    / "skills"
    / "kit-llm-client"
    / "assets"
)
_CASES = (
    "test_version_selection_and_metadata",
    "test_label_can_resolve_to_a_different_version",
    "test_invalid_selection_is_rejected",
    "test_missing_and_extra_variables_are_private",
    "test_fetch_failure_is_private_and_fail_closed",
    "test_zero_cache_ttl_is_forwarded",
    "test_cache_ttl_must_be_explicit",
    "test_cache_ttl_requires_a_nonnegative_actual_integer",
    "test_resolved_version_requires_a_positive_actual_integer",
    "test_unapproved_prompt_shapes_are_rejected",
    "test_mismatched_identity_is_rejected",
    "test_invalid_adapter_configuration_is_rejected",
)


@pytest.fixture
def managed_prompt_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> Mapping[str, object]:
    for name in ("llm", "llm.adapters"):
        package = ModuleType(name)
        vars(package)["__path__"] = []
        monkeypatch.setitem(sys.modules, name, package)
    for name, filename in (
        ("llm.port", "llm_port.py.template"),
        ("llm.managed_prompts", "managed_prompts.py.template"),
        ("llm.adapters.langfuse_prompts", "langfuse_prompts.py.template"),
    ):
        module = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, module)
        vars(module).update(runpy.run_path(str(_ASSETS / filename), run_name=name))
    return runpy.run_path(str(_ASSETS / "test_managed_prompts.py.template"))


@pytest.mark.parametrize("case", _CASES)
def test_copied_managed_prompt_behavior(
    case: str, managed_prompt_cases: Mapping[str, object]
) -> None:
    example = managed_prompt_cases[case]
    assert isinstance(example, FunctionType)
    example()
