"""Keep the identity guide, bootstrap delegation and template role IDs in sync."""

from __future__ import annotations

import importlib.util
import re
import sys
from typing import TYPE_CHECKING

import pytest

from delivery_tools.catalog import ROOT

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.unit


def _load_bootstrap() -> ModuleType:
    """Load the standalone operator script by path; it is not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "bootstrap_azure", ROOT / "scripts/bootstrap_azure.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap_azure = _load_bootstrap()

_GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# Azure RBAC role definitions only. Service-native grants, such as Cosmos DB
# sqlRoleDefinitions or Redis access policies, are not delegated through RBAC.
_BICEP_ROLE = re.compile(
    r"subscriptionResourceId\(\s*'Microsoft\.Authorization/roleDefinitions',\s*(\w+)\s*\)"
)
_TERRAFORM_ROLE = re.compile(r'roleDefinitionId\s*=\s*"([^"\n]*)"')
_TERRAFORM_LOCAL = re.compile(r"\$\{local\.(\w+)\}")
_TERRAFORM_RBAC_PREFIXES = (
    "/providers/Microsoft.Authorization/roleDefinitions/",
    "${local.role_definitions}/",
)
_CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"
_RBAC_ADMINISTRATOR = "f58310d9-a9f6-439a-9e8d-f62e7b41a168"
_MONITORING_CONTRIBUTOR = "749f88d5-cbae-40b8-bcfc-e573ddc772fa"
_GUIDE = ROOT / "docs/identity-and-network.md"


def _constant(text: str, name: str, *, quote: str) -> str:
    match = re.search(rf"\b{name}\s*=\s*{quote}({_GUID.pattern}){quote}", text)
    assert match is not None, f"role {name} is not a GUID literal"
    return match.group(1)


def _bicep_roles(path: Path) -> Iterator[str]:
    text = path.read_text(encoding="utf-8")
    for name in _BICEP_ROLE.findall(text):
        yield _constant(text, name, quote="'")


def _terraform_roles(path: Path) -> Iterator[str]:
    text = path.read_text(encoding="utf-8")
    for value in _TERRAFORM_ROLE.findall(text):
        if any(prefix in value for prefix in _TERRAFORM_RBAC_PREFIXES):
            yield _constant(text, _TERRAFORM_LOCAL.findall(value)[-1], quote='"')


def _bicep() -> set[str]:
    return {
        role
        for path in ROOT.glob("infra/*/bicep/*.bicep")
        for role in _bicep_roles(path)
    }


def _terraform() -> set[str]:
    return {
        role
        for path in ROOT.glob("infra/*/terraform/*.tf")
        for role in _terraform_roles(path)
    }


def _guide_section(heading: str) -> str:
    text = _GUIDE.read_text(encoding="utf-8")
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_bicep_and_terraform_assign_the_same_roles() -> None:
    assert _bicep()
    assert _bicep() == _terraform()


def test_bootstrap_delegates_exactly_the_template_roles() -> None:
    assert set(bootstrap_azure.DELEGABLE_ROLES) == _bicep()


def test_guide_lists_exactly_the_template_roles() -> None:
    documented = set(_GUID.findall(_guide_section("Data-plane roles")))

    assert documented == _bicep()


def test_guide_condition_matches_bootstrap_roles() -> None:
    section = _guide_section("Deployment roles")
    condition = re.search(r"```text\n(.+?)\n```", section, re.DOTALL)
    assert condition is not None
    roles = ", ".join(sorted(bootstrap_azure.DELEGABLE_ROLES))

    assert condition.group(1).count(f"GuidEquals {{{roles}}}") == 2
    assert set(_GUID.findall(section)) == {
        *bootstrap_azure.DELEGABLE_ROLES,
        _CONTRIBUTOR,
        _RBAC_ADMINISTRATOR,
        _MONITORING_CONTRIBUTOR,
    }
