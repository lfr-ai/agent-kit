"""Keep the dev container, CI pins and editor recommendations on one toolchain."""

import json
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[3]


def _devcontainer() -> dict[str, object]:
    value = json.loads((_ROOT / ".devcontainer/devcontainer.json").read_text())
    assert isinstance(value, dict)
    return value


def _feature_version(name: str) -> str:
    features = _devcontainer()["features"]
    assert isinstance(features, dict)
    matches = [
        options
        for reference, options in features.items()
        if reference.rsplit("/", 1)[-1].split(":", 1)[0] == name
    ]
    assert len(matches) == 1, f"exactly one {name} feature is expected"
    options = matches[0]
    assert isinstance(options, dict)
    version = options.get("version")
    assert isinstance(version, str)
    return version


def _ci_step_inputs(action: str, key: str) -> set[str]:
    values: set[str] = set()
    for path in (_ROOT / ".github/workflows").glob("*.yml"):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if uses.startswith(f"{action}@"):
                    values.add(str(step["with"][key]))
    return values


def test_uv_version_matches_every_ci_pin() -> None:
    """Contributors and CI resolve the lockfile with the same uv release."""
    assert _ci_step_inputs("astral-sh/setup-uv", "version") == {_feature_version("uv")}


def test_bun_version_matches_the_ci_pin() -> None:
    """Hooks that run through Bun see the same runtime locally and in CI."""
    assert _ci_step_inputs("oven-sh/setup-bun", "bun-version") == {
        _feature_version("bun")
    }


def test_python_image_matches_the_project_baseline() -> None:
    """The container image uses the interpreter recorded in ``.python-version``."""
    baseline = (_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert _devcontainer()["build"] == {"dockerfile": "Dockerfile"}
    assert "image" not in _devcontainer()
    lines = (_ROOT / ".devcontainer/Dockerfile").read_text(encoding="utf-8")
    sources = [line for line in lines.splitlines() if line.startswith("FROM ")]
    assert len(sources) == 1
    image, digest = sources[0].removeprefix("FROM ").split("@sha256:")
    assert image.endswith((f":3-{baseline}-trixie", f":{baseline}-trixie"))
    assert len(digest) == 64
    assert int(digest, 16) >= 0


def test_every_feature_is_locked_by_digest() -> None:
    """Feature tags can move; the lockfile pins each one by content digest."""
    features = _devcontainer()["features"]
    lock = json.loads((_ROOT / ".devcontainer/devcontainer-lock.json").read_text())
    assert isinstance(features, dict)
    assert set(lock["features"]) == set(features)
    for entry in lock["features"].values():
        assert "@sha256:" in entry["resolved"]
        assert entry["integrity"].startswith("sha256:")


_HOST_ONLY_EXTENSIONS = {
    "ms-vscode-remote.remote-containers",
    "ms-vscode.powershell",
}


def test_container_extensions_match_workspace_recommendations() -> None:
    """One extension list; only named host-side extensions stay out of the container."""
    recommended = json.loads((_ROOT / ".vscode/extensions.json").read_text())
    customizations = _devcontainer()["customizations"]
    assert isinstance(customizations, dict)
    installed = customizations["vscode"]["extensions"]
    assert set(recommended["recommendations"]) >= _HOST_ONLY_EXTENSIONS
    assert sorted(installed) == sorted(
        set(recommended["recommendations"]) - _HOST_ONLY_EXTENSIONS
    )


def test_container_environment_keeps_apm_non_interactive() -> None:
    """APM never prompts or runs package scripts inside the container."""
    environment = _devcontainer()["containerEnv"]
    assert isinstance(environment, dict)
    assert environment["APM_NO_SCRIPTS"] == "1"
    assert environment["APM_NON_INTERACTIVE"] == "1"
    # Installs dependencies in a prebuild-cacheable step; it needs no user secrets.
    assert _devcontainer()["updateContentCommand"] == "task bootstrap"
    assert "postCreateCommand" not in _devcontainer()
