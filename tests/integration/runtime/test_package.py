"""Build and install the wheel offline, then exercise it without source imports."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tomllib
from zipfile import ZipFile

import pytest

pytestmark = pytest.mark.integration

_INSTALLED_SMOKE = """
import asyncio
from importlib import metadata, resources
from pathlib import Path
import site
import sys

installed, checkout = (Path(value).resolve() for value in sys.argv[1:3])
dependency_paths = {Path(value).resolve() for value in site.getsitepackages()}
sys.path[:] = [
    value for value in sys.path
    if Path(value).resolve() in dependency_paths
    or not Path(value).resolve().is_relative_to(checkout)
]
sys.path.insert(0, str(installed))
assert not Path.cwd().resolve().is_relative_to(checkout)

from httpx import ASGITransport, AsyncClient
import platform_kit_runtime as runtime

distribution = metadata.distribution("platform-kit-runtime")
assert distribution.version == sys.argv[3]
assert Path(distribution.locate_file("")).resolve() == installed
assert resources.files(runtime).joinpath("py.typed").is_file()

async def verify():
    app = runtime.create_app(config=runtime.RuntimeConfig(), probes=())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://runtime.test"
    ) as client:
        for path, status in (("/health/live", "ok"), ("/health/ready", "ready")):
            response = await client.get(path)
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"
            assert response.json() == {"status": status}

asyncio.run(verify())
for name, module in tuple(sys.modules.items()):
    if name == "platform_kit_runtime" or name.startswith("platform_kit_runtime."):
        assert Path(module.__file__).resolve().is_relative_to(installed), name
assert "agent_kit" not in sys.modules
"""


def _run(*, command: tuple[str, ...], cwd: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed tools, temporary paths, no shell
        command,
        cwd=cwd,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "UV_OFFLINE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_offline_distributions_work_without_checkout_source(tmp_path: Path) -> None:
    checkout = Path(__file__).resolve().parents[3]
    package = checkout / "packages/runtime"
    uv = shutil.which("uv.exe" if sys.platform == "win32" else "uv")
    assert uv is not None, "The repository's uv executable is required."
    assert not tmp_path.resolve().is_relative_to(checkout)
    source = tmp_path / "source"
    source.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copyfile(package / name, source / name)
    shutil.copytree(package / "docs", source / "docs")
    shutil.copytree(
        package / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    assert isinstance(version, str)
    root = tomllib.loads((checkout / "pyproject.toml").read_text(encoding="utf-8"))
    constraints = tmp_path / "build-constraints.txt"
    constraints.write_text(
        "\n".join(root["tool"]["uv"]["build-constraint-dependencies"]) + "\n",
        encoding="utf-8",
    )
    wheels = tmp_path / "wheels"
    _run(
        command=(
            uv,
            "build",
            str(source),
            "--offline",
            "--python",
            sys.executable,
            "--build-constraints",
            str(constraints),
            "--out-dir",
            str(wheels),
        ),
        cwd=tmp_path,
    )
    (sdist,) = wheels.glob("*.tar.gz")
    with tarfile.open(sdist, "r:gz") as archive:
        prefix = f"platform_kit_runtime-{version}"
        guides = (
            "ai",
            "database",
            "http-middleware",
            "identity",
            "ocr",
            "retrieval",
            "telemetry",
        )
        assert {
            f"{prefix}/README.md",
            *(f"{prefix}/docs/{guide}.md" for guide in guides),
            f"{prefix}/LICENSE",
        } <= set(archive.getnames())
    (wheel,) = wheels.glob("*.whl")
    with ZipFile(wheel) as archive:
        assert "platform_kit_runtime/py.typed" in archive.namelist()
        assert any(
            name.endswith(".dist-info/licenses/LICENSE") for name in archive.namelist()
        )
    installed = tmp_path / "installed"
    _run(
        command=(
            uv,
            "pip",
            "install",
            "--offline",
            "--no-index",
            "--no-deps",
            "--target",
            str(installed),
            str(wheel),
        ),
        cwd=tmp_path,
    )
    shutil.rmtree(source)
    _run(
        command=(
            sys.executable,
            "-I",
            "-B",
            "-c",
            _INSTALLED_SMOKE,
            str(installed),
            str(checkout),
            version,
        ),
        cwd=tmp_path,
    )
