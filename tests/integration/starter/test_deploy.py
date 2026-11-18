"""Check rendered workflow ordering, immutable inputs and identity boundaries."""

import ast
from collections.abc import Generator
from contextlib import contextmanager
import io
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace
import urllib.request

from copier import run_copy
import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_COMMIT = "1234567890abcdef1234567890abcdef12345678"
_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("deploy-template")
    shutil.copyfile(_ROOT / "copier.yml", directory / "copier.yml")
    shutil.copytree(
        _ROOT / "packages/starter/template", directory / "packages/starter/template"
    )
    return directory


def _render(source: Path, iac: str, registry: str | None, ci: str) -> Path:
    cached = source.parent / f"{source.name}-{iac}-{registry}-{ci}"
    if not cached.exists():
        data = {"service": "api", "iac": iac, "ci": ci, "kit_commit": _COMMIT}
        if registry:
            data["registry"] = registry
        run_copy(str(source), cached, data=data, defaults=True, quiet=True)
    return cached


def _workflows(
    source: Path, destination: Path, iac: str, registry: str | None = None
) -> dict[str, dict]:
    shutil.copytree(_render(source, iac, registry, "github"), destination)
    return {
        path.stem: yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        for path in (destination / ".github/workflows").glob("*.yml")
    }


@pytest.mark.parametrize("iac", ["none", "bicep", "terraform"])
def test_ci_is_callable_read_only_and_sha_pinned(
    source: Path, tmp_path: Path, iac: str
) -> None:
    workflows = _workflows(source, tmp_path / "consumer", iac)
    assert not (tmp_path / "consumer/.azuredevops").exists()
    ci = workflows["ci"]
    assert "workflow_call" in ci["on"]
    assert "pull_request" in ci["on"]
    assert ci["permissions"] == {}
    for job in ci["jobs"].values():
        assert job["permissions"] == {"contents": "read"}
        assert "environment" not in job
        if "uses" in job:
            assert _PIN.fullmatch(job["uses"])
            assert job["uses"].endswith(f"@{_COMMIT}")
    assert ("infra" in ci["jobs"]) == (iac != "none")
    assert "<reviewed-full-sha>" not in str(ci)


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_ghcr_dispatch_checks_then_builds_once_then_passes_exact_digest_to_delivery(
    source: Path, tmp_path: Path, iac: str
) -> None:
    workflows = _workflows(source, tmp_path / "consumer", iac, "ghcr")
    deploy = workflows["deploy"]
    assert set(deploy["on"]) == {"workflow_dispatch"}
    assert deploy["permissions"] == {}
    assert deploy["concurrency"]["cancel-in-progress"] == "false"
    jobs = deploy["jobs"]
    assert jobs["checks"]["uses"] == "./.github/workflows/ci.yml"
    assert jobs["image"]["needs"] == ["checks", "intent"]
    assert jobs["image"]["uses"] == "./.github/workflows/image.yml"
    assert jobs["pullable"]["needs"] == "image"
    assert jobs["deploy"]["needs"] == ["image", "pullable"]
    assert jobs["deploy"]["uses"] == (
        f"lfr-ai/agent-kit/.github/workflows/delivery-azure-deploy.yml@{_COMMIT}"
    )
    assert jobs["deploy"]["with"]["image"] == "${{ needs.image.outputs.image }}"
    assert jobs["deploy"]["with"]["iac"] == iac
    assert jobs["deploy"]["with"]["environment"] == "${{ inputs.environment }}"
    assert jobs["deploy"]["with"]["runs-on"] == "${{ inputs.runs-on }}"
    assert "validate_environment.py" in str(jobs["intent"])
    assert jobs["deploy"]["permissions"] == {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
    }
    assert "secrets" not in jobs["deploy"]
    assert jobs["checks"]["permissions"] == {"contents": "read"}
    assert jobs["intent"]["permissions"] == {"contents": "read"}
    assert jobs["pullable"]["permissions"] == {}
    assert "public-ghcr" in deploy["on"]["workflow_dispatch"]["inputs"]
    assert (
        deploy["on"]["workflow_dispatch"]["inputs"]["public-ghcr"]["default"] == "false"
    )
    assert "refs/heads/main" in str(jobs["intent"])
    assert "Authorization" in str(jobs["pullable"])
    assert "GITHUB_TOKEN" not in str(jobs["pullable"])
    assert "visibility" not in str(jobs["pullable"])
    for step in jobs["pullable"]["steps"]:
        if step.get("shell") == "python3 {0}":
            ast.parse(step["run"])
    assert sum(job.get("uses", "").endswith("/image.yml") for job in jobs.values()) == 1


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_acr_dispatch_pushes_by_oidc_and_supports_registry_bootstrap(
    source: Path, tmp_path: Path, iac: str
) -> None:
    workflows = _workflows(source, tmp_path / "consumer", iac)
    deploy = workflows["deploy"]
    inputs = deploy["on"]["workflow_dispatch"]["inputs"]
    assert "public-ghcr" not in inputs
    assert inputs["registry-bootstrap"]["default"] == "false"
    jobs = deploy["jobs"]
    assert "pullable" not in jobs
    assert "--print-registry" in str(jobs["intent"])
    assert jobs["intent"]["outputs"]["registry"] == (
        "${{ steps.intent.outputs.registry }}"
    )
    image = jobs["image"]
    assert image["needs"] == ["checks", "intent"]
    assert image["if"] == "${{ !inputs.registry-bootstrap }}"
    assert image["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    assert image["with"] == {
        "environment": "${{ inputs.environment }}",
        "registry": "${{ needs.intent.outputs.registry }}",
        "runs-on": "${{ inputs.runs-on }}",
    }
    assert jobs["deploy"]["needs"] == ["checks", "intent", "image"]
    condition = jobs["deploy"]["if"]
    assert "needs.image.result == 'success'" in condition
    assert "inputs.registry-bootstrap && needs.image.result == 'skipped'" in condition
    assert "!cancelled()" in condition
    assert jobs["deploy"]["with"]["image"] == "${{ needs.image.outputs.image }}"
    assert jobs["deploy"]["uses"].endswith(f"@{_COMMIT}")

    build = workflows["image"]
    assert set(build["on"]) == {"workflow_call"}
    assert set(build["on"]["workflow_call"]["inputs"]) == {
        "environment",
        "registry",
        "runs-on",
    }
    job = build["jobs"]["image"]
    assert job["environment"] == "${{ inputs.environment }}"
    assert "packages" not in job["permissions"]
    steps = job["steps"]
    for step in steps:
        if "uses" in step:
            assert _PIN.fullmatch(step["uses"].split(" ")[0])
    assert any(step.get("uses", "").startswith("azure/login@") for step in steps)
    assert "az acr login" in str(steps)
    assert "ghcr.io" not in str(build)


def _ado(source: Path, destination: Path, iac: str) -> dict[str, dict]:
    shutil.copytree(_render(source, iac, None, "azure-devops"), destination)
    files = sorted((destination / ".azuredevops/pipelines").glob("*.yml"))
    return {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) for path in files
    }


def _extends_parameters(template: str) -> set[str]:
    path, _, repository = template.partition("@")
    assert repository == "delivery"
    document = yaml.safe_load((_ROOT / path).read_text(encoding="utf-8"))
    return {parameter["name"] for parameter in document["parameters"]}


@pytest.mark.parametrize("iac", ["none", "bicep", "terraform"])
def test_azure_devops_extends_pinned_delivery_templates_only(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = tmp_path / "consumer"
    pipelines = _ado(source, root, iac)
    assert not (root / ".github").exists()
    assert not (root / "azure-pipelines.yml").exists()
    expected = {"ci"} | ({"iac", "deploy", "image"} if iac != "none" else set())
    assert set(pipelines) == expected
    for name, pipeline in pipelines.items():
        if name == "image":
            continue
        (repository,) = pipeline["resources"]["repositories"]
        assert repository["repository"] == "delivery"
        assert repository["name"] == "lfr-ai/agent-kit"
        assert repository["ref"] == _COMMIT
        template = pipeline["extends"]["template"]
        supplied = {
            key
            for key in pipeline["extends"]["parameters"]
            if not key.startswith("${{")
        }
        assert supplied <= _extends_parameters(template), (name, supplied)
    ci = pipelines["ci"]
    assert ci["extends"]["template"] == (
        "packages/delivery/azure-devops/extends/python-ci.yml@delivery"
    )
    assert ci["pr"]["branches"]["include"] == ["main"]
    if iac != "none":
        assert pipelines["iac"]["extends"]["template"].endswith(
            f"/{'bicep' if iac == 'bicep' else 'terraform'}-check.yml@delivery"
        )


def _assert_named_builder_is_removed(inline: str) -> None:
    """Self-hosted agents must not keep a BuildKit builder after the job."""
    assert "buildx create --use" not in inline
    assert 'docker buildx create --name "$builder"' in inline
    assert 'docker buildx build --builder "$builder"' in inline
    cleanup = inline.split("cleanup() {", 1)[1].split("}", 1)[0]
    assert 'docker buildx rm "$builder"' in cleanup
    assert "trap cleanup EXIT" in inline


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_azure_devops_deploy_and_image_target_one_environment_registry(
    source: Path, tmp_path: Path, iac: str
) -> None:
    pipelines = _ado(source, tmp_path / "consumer", iac)
    deploy = pipelines["deploy"]
    assert deploy["trigger"] == "none"
    assert deploy["pr"] == "none"
    parameters = deploy["extends"]["parameters"]
    assert deploy["extends"]["template"].endswith("/azure-deploy.yml@delivery")
    assert parameters["deployBranch"] == "refs/heads/main"
    assert parameters["pool"] == "${{ parameters.pool }}"
    assert parameters["iac"] == iac
    assert parameters["${{ if parameters.registryBootstrap }}"] == {"image": ""}
    assert parameters["${{ else }}"] == {"image": "${{ parameters.image }}"}
    (environment,) = parameters["environments"]
    assert environment["serviceConnection"] == "azure-${{ parameters.environment }}"
    assert ("resourceGroup" in environment) == (iac == "bicep")
    assert ("tfstateStorageAccount" in environment) == (iac == "terraform")
    runtime = {parameter["name"]: parameter for parameter in deploy["parameters"]}
    assert runtime["environment"]["values"] == ["dev", "test", "staging", "prod"]
    assert runtime["registryBootstrap"]["default"] is False
    assert runtime["pool"]["default"] == "hosted"

    image = pipelines["image"]
    assert image["trigger"] == "none"
    assert image["pr"] == "none"
    (job,) = image["stages"][0]["jobs"]
    assert job["environment"] == "${{ parameters.environment }}"
    steps = job["strategy"]["runOnce"]["deploy"]["steps"]
    assert "refs/heads/main" in steps[1]["bash"]
    assert "--print-registry" in steps[1]["bash"]
    push = steps[2]
    assert push["task"] == "AzureCLI@2"
    assert push["inputs"]["azureSubscription"] == "azure-${{ parameters.environment }}"
    assert "az acr login" in push["inputs"]["inlineScript"]
    _assert_named_builder_is_removed(push["inputs"]["inlineScript"])
    executable = _bash()
    for script in (steps[1]["bash"], push["inputs"]["inlineScript"]):
        result = subprocess.run(  # noqa: S603 - installed Bash syntax-only mode; no script execution
            [executable, "-n"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr


def test_azure_devops_deployment_rejects_public_ghcr(
    source: Path, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="ACR only"):
        run_copy(
            str(source),
            tmp_path / "consumer",
            data={
                "service": "api",
                "iac": "bicep",
                "registry": "ghcr",
                "ci": "azure-devops",
                "kit_commit": _COMMIT,
            },
            defaults=True,
            quiet=True,
        )


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_registry_reader_returns_only_the_environment_registry(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = tmp_path / "consumer"
    shutil.copytree(_render(source, iac, None, "github"), root)
    namespace = runpy.run_path(str(root / "scripts/validate_environment.py"))
    extension = "bicepparam" if iac == "bicep" else "tfvars"
    path = root / "infra" / f"dev.{extension}"
    stage = path.read_text().replace(
        "REPLACE_WITH_RESOURCE_GROUP_ARM_ID",
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/app",
    )
    name = "param registryName = '{}'\n" if iac == "bicep" else 'registry_name = "{}"\n'
    stage = re.sub(r"(?m)^(?:param registryName|registry_name)\s*=.*\n", "", stage)
    path.write_text(stage + name.format("sampledevacr"), encoding="utf-8")
    assert namespace["registry_server"]("dev", root) == "sampledevacr.azurecr.io"
    for text in (
        stage,
        stage + name.format("Bad-Name"),
        stage + name.format("abcde") * 2,
    ):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=r"registry name|Duplicate parameter"):
            namespace["registry_server"]("dev", root)


def test_standalone_image_behavior_is_preserved(source: Path, tmp_path: Path) -> None:
    workflows = _workflows(source, tmp_path / "consumer", "none")
    assert "deploy" not in workflows
    image = workflows["image"]
    assert set(image["on"]) == {"push", "workflow_dispatch", "workflow_call"}
    assert image["on"]["workflow_call"]["outputs"]["image"]["value"] == (
        "${{ jobs.image.outputs.image }}"
    )
    assert "digest" in image["jobs"]["image"]["outputs"]["image"] or (
        image["jobs"]["image"]["outputs"]["image"]
        == "${{ steps.reference.outputs.image }}"
    )
    for step in image["jobs"]["image"]["steps"]:
        if "uses" in step:
            assert _PIN.fullmatch(step["uses"])


@pytest.mark.parametrize("registry", ["acr", "ghcr"])
def test_rendered_workflows_with_installed_actionlint(
    source: Path, tmp_path: Path, registry: str
) -> None:
    root = tmp_path / "consumer"
    _workflows(source, root, "bicep", registry)
    executable = shutil.which("actionlint")
    if not executable:
        pytest.skip("Installed actionlint unavailable; no installation attempted")
    result = subprocess.run(  # noqa: S603 - installed linter and generated local files
        [
            executable,
            "-shellcheck=",
            *map(str, (root / ".github/workflows").glob("*.yml")),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("iac", "registry"),
    [
        ("none", None),
        ("bicep", "acr"),
        ("bicep", "ghcr"),
        ("terraform", "acr"),
        ("terraform", "ghcr"),
    ],
)
def test_rendered_workflows_pass_permission_policy(
    source: Path, tmp_path: Path, iac: str, registry: str | None
) -> None:
    root = tmp_path / "consumer"
    _workflows(source, root, iac, registry)
    result = subprocess.run(  # noqa: S603 - trusted offline repository policy checker
        [
            sys.executable,
            str(
                _ROOT
                / "packages/iac/.apm/skills/kit-ci-review/assets/check_workflow_permissions.py"
            ),
            str(root / ".github/workflows"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("access", ["public", "private", "different-digest"])
def test_digest_pull_check_never_uses_deploy_or_package_credentials(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    workflows = _workflows(source, tmp_path / "consumer", "bicep", "ghcr")
    script = workflows["deploy"]["jobs"]["pullable"]["steps"][0]["run"]
    digest = "sha256:" + "a" * 64
    monkeypatch.setenv("IMAGE", f"ghcr.io/example/app@{digest}")
    calls: list[str] = []

    @contextmanager
    def respond(
        request: str | urllib.request.Request, *, timeout: int
    ) -> Generator[object]:
        assert timeout == 30
        if isinstance(request, str):
            calls.append(request)
            assert request.startswith("https://ghcr.io/token?")
            yield io.BytesIO(b'{"token": "anonymous-pull-token"}')
        else:
            calls.append(request.full_url)
            assert request.get_method() == "HEAD"
            assert request.headers["Authorization"] == "Bearer anonymous-pull-token"
            if access == "private":
                raise OSError
            yield SimpleNamespace(
                headers={
                    "Docker-Content-Digest": digest if access == "public" else "wrong"
                }
            )

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    if access == "public":
        exec(compile(script, "anonymous-pull", "exec"), {})  # noqa: S102 - trusted rendered workflow; HTTP mocked
    else:
        with pytest.raises(SystemExit):
            exec(compile(script, "anonymous-pull", "exec"), {})  # noqa: S102 - trusted rendered workflow; HTTP mocked
    assert len(calls) == 2
    assert calls[-1] == f"https://ghcr.io/v2/example/app/manifests/{digest}"


def _bash() -> str:
    if sys.platform == "win32":
        git = Path(shutil.which("git") or "")
        candidate = git.parent.parent / "bin/bash.exe"
        executable = str(candidate) if candidate.is_file() else None
    else:
        executable = shutil.which("bash")
    if executable is None:
        pytest.skip("Installed Bash unavailable; no shell installation attempted")
    return executable


@pytest.mark.parametrize("registry", ["acr", "ghcr"])
@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_bash_workflow_scripts_parse_without_execution(
    source: Path, tmp_path: Path, iac: str, registry: str
) -> None:
    workflows = _workflows(source, tmp_path / "consumer", iac, registry)
    executable = _bash()
    scripts = [
        step["run"]
        for workflow in workflows.values()
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "run" in step and step.get("shell") != "python3 {0}"
    ]
    for script in scripts:
        result = subprocess.run(  # noqa: S603 - installed Bash syntax-only mode; no script execution
            [executable, "-n"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
