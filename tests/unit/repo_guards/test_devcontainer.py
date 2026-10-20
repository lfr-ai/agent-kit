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
    """The container image uses the interpreter recorded in '.python-version'."""
    baseline = (_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    image = _devcontainer()["image"]
    assert isinstance(image, str)
    assert image.endswith((f":3-{baseline}-trixie", f":{baseline}-trixie"))


def test_container_extensions_match_workspace_recommendations() -> None:
    """One extension list, installed automatically in the container."""
    recommended = json.loads((_ROOT / ".vscode/extensions.json").read_text())
    customizations = _devcontainer()["customizations"]
    assert isinstance(customizations, dict)
    installed = customizations["vscode"]["extensions"]
    assert sorted(installed) == sorted(recommended["recommendations"])


def test_container_environment_keeps_apm_non_interactive() -> None:
    """APM never prompts or runs package scripts inside the container."""
    environment = _devcontainer()["containerEnv"]
    assert isinstance(environment, dict)
    assert environment["APM_NO_SCRIPTS"] == "1"
    assert environment["APM_NON_INTERACTIVE"] == "1"
    assert _devcontainer()["postCreateCommand"] == "uv sync --locked"
