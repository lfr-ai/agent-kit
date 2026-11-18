"""Keep the tested APM executable and dependency resolution aligned."""

from pathlib import Path
import re
import tomllib

from agent_kit.infrastructure.apm import APM_VERSION

_ROOT = Path(__file__).resolve().parents[3]


def test_apm_version_matches_manifest_and_lock() -> None:
    manifest = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert f"apm-cli=={APM_VERSION}" in manifest["dependency-groups"]["dev"]
    locked_versions = [
        package["version"]
        for package in lock["package"]
        if package["name"] == "apm-cli"
    ]
    assert locked_versions == [APM_VERSION]


def test_workspace_versions_follow_the_coordinated_release() -> None:
    manifest = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = tomllib.loads(
        (_ROOT / "packages/runtime/pyproject.toml").read_text(encoding="utf-8")
    )
    version = manifest["project"]["version"]
    assert runtime["project"]["version"] == version
    extras = ",".join(sorted(runtime["project"]["optional-dependencies"]))
    dependency = f"platform-kit-runtime[{extras}]=={version}"
    assert dependency in manifest["dependency-groups"]["dev"]
    starter = (_ROOT / "packages/starter/template/apm.yml.jinja").read_text(
        encoding="utf-8"
    )
    assert re.findall(r"#v([0-9]+\.[0-9]+\.[0-9]+)", starter) == [version]
    bump = tomllib.loads((_ROOT / ".cz.toml").read_text(encoding="utf-8"))
    assert {
        "packages/runtime/pyproject.toml:^version",
        "pyproject.toml:platform-kit-runtime.*==",
        "packages/starter/template/apm.yml.jinja:#v",
    } <= set(bump["tool"]["commitizen"]["version_files"])
    assert re.search(r"platform-kit-runtime.*==", dependency)
    assert not re.search(
        r"platform-kit-runtime.*==", "platform-kit-runtime = { workspace = true }"
    )
