"""Installed facade remains optional, plus identity-specific import-direction proof."""

import ast
from importlib import resources
import os
from pathlib import Path
import sys
import tomllib
from zipfile import ZipFile

import pytest
from tests.integration.runtime import test_package

import platform_kit_runtime

pytestmark = pytest.mark.integration

_IDENTITY_INSTALLED_SMOKE = """
import importlib.abc

class DenyIdentitySDKs(importlib.abc.MetaPathFinder):
    blocked = {"msal", "jwt", "redis", "cryptography"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.blocked:
            raise AssertionError("Optional SDK imported by the public facade: " + fullname)
        return None

guard = DenyIdentitySDKs()
assert not guard.blocked.intersection(sys.modules)
sys.meta_path.insert(0, guard)
import platform_kit_runtime.identity as identity
assert Path(identity.__file__).resolve().is_relative_to(installed)
assert identity.IdentityConfig(
    tenant_id="11111111-1111-4111-8111-111111111111",
    client_id="22222222-2222-4222-8222-222222222222",
    api_audience="api://offline",
    origin="https://app.test",
).issuer.endswith("/v2.0")
asyncio.run(verify())
assert not guard.blocked.intersection(sys.modules)
guard.blocked = {"msal", "redis"}

async def verify_api_only():
    config = identity.IdentityConfig(
        tenant_id="11111111-1111-4111-8111-111111111111",
        client_id="22222222-2222-4222-8222-222222222222",
        api_audience="api://offline",
        origin="https://app.test",
    )
    async with identity.open_entra_bearer(config=config) as validator:
        assert callable(identity.BearerGuard(
            config=config, validator=validator,
            scopes=frozenset({"read"}), roles=frozenset(),
        ))

asyncio.run(verify_api_only())
assert not guard.blocked.intersection(sys.modules)
"""

_ADAPTER_LAYOUT_SMOKE = """
sys.meta_path.remove(guard)
import importlib
import socket

def no_network(*args, **kwargs):
    raise AssertionError("Artifact smoke must not access the network")

import platform_kit_runtime.ai as ai
assert "litellm" not in sys.modules
for name in (
    "core.identity.models", "core.identity.data", "core.identity.ports",
    "infrastructure.identity.graph", "infrastructure.identity.http",
    "infrastructure.identity.jwt", "infrastructure.identity.msal",
    "infrastructure.identity.msal_http", "infrastructure.identity.redis",
    "infrastructure.identity.upstream", "presentation.identity.problems",
    "presentation.identity.routes", "presentation.identity.security",
):
    importlib.import_module("platform_kit_runtime." + name)

async def verify_bff():
    # Windows creates an internal socketpair when the event loop starts.
    socket.socket.connect = no_network
    config = identity.IdentityConfig(
        tenant_id="11111111-1111-4111-8111-111111111111",
        client_id="22222222-2222-4222-8222-222222222222",
        api_audience="api://offline",
        origin="https://app.test",
    )
    async with identity.open_entra_identity(
        config=config, redis_url="rediss://redis.invalid",
        assertion=lambda: "synthetic-unused-assertion",
    ) as bundle:
        assert bundle.config is config
        bundle.install(app=runtime.create_app(config=runtime.RuntimeConfig(), probes=()))

asyncio.run(verify_bff())
for name, module in tuple(sys.modules.items()):
    if name == "platform_kit_runtime" or name.startswith("platform_kit_runtime."):
        assert Path(module.__file__).resolve().is_relative_to(installed), name
"""


def test_extracted_wheel_without_installer(tmp_path: Path) -> None:
    wheel = os.environ.get("RUNTIME_TEST_WHEEL")
    if wheel is None:
        pytest.skip("Set RUNTIME_TEST_WHEEL to a prebuilt local wheel; no installs")
    checkout = Path(__file__).resolve().parents[3]
    installed = tmp_path / "extracted"
    with ZipFile(wheel) as archive:
        assert "platform_kit_runtime/core/identity/models.py" in archive.namelist()
        assert not any(".data/" in name for name in archive.namelist())
        archive.extractall(installed)
    project = tomllib.loads(
        (checkout / "packages/runtime/pyproject.toml").read_text(encoding="utf-8")
    )
    test_package._run(
        command=(
            sys.executable,
            "-I",
            "-B",
            "-c",
            test_package._INSTALLED_SMOKE
            + _IDENTITY_INSTALLED_SMOKE
            + _ADAPTER_LAYOUT_SMOKE,
            str(installed),
            str(checkout),
            project["project"]["version"],
        ),
        cwd=tmp_path,
    )


def test_identity_facade_in_offline_installed_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        test_package,
        "_INSTALLED_SMOKE",
        test_package._INSTALLED_SMOKE + _IDENTITY_INSTALLED_SMOKE,
    )
    test_package.test_offline_distributions_work_without_checkout_source(tmp_path)


def test_identity_layers_have_only_inward_imports() -> None:
    package = resources.files(platform_kit_runtime)
    for layer in ("core", "application", "presentation"):
        for file in Path(str(package.joinpath(layer))).rglob("*.py"):
            tree = ast.parse(file.read_text(encoding="utf-8"))
            imports = [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            ]
            imports.extend(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            if layer in {"core", "application"}:
                allowed = (
                    ("platform_kit_runtime.core.",)
                    if layer == "core"
                    else (
                        "platform_kit_runtime.core.",
                        "platform_kit_runtime.application.",
                    )
                )
                assert all(
                    name.split(".")[0] in sys.stdlib_module_names
                    or name.startswith(allowed)
                    for name in imports
                ), file.name
            assert not any(
                name.startswith(
                    (
                        "platform_kit_runtime.infrastructure",
                        "platform_kit_runtime.composition",
                        "platform_kit_runtime.identity",
                    )
                )
                for name in imports
            ), file.name
