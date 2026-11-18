"""Azure DevOps deploy-branch gate, preview artifact guidance and check caching."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from delivery_tools.catalog import ROOT
from delivery_tools.documents import mapping, read_yaml

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit
WORKFLOWS: Final[Path] = ROOT.parents[1] / ".github/workflows"
EXTENDS: Final[Path] = ROOT / "azure-devops/extends/azure-deploy.yml"
STEPS: Final[Path] = ROOT / "azure-devops/steps/azure-deploy.yml"
ADO_CHECK: Final[Path] = ROOT / "azure-devops/steps/terraform-check.yml"
GITHUB_CHECK: Final[Path] = WORKFLOWS / "delivery-terraform-check.yml"
GITHUB_DEPLOY: Final[Path] = WORKFLOWS / "delivery-azure-deploy.yml"


def _parameters(path: Path) -> dict[str, dict[str, object]]:
    items = read_yaml(path)["parameters"]
    assert isinstance(items, list)
    return {str(mapping(item)["name"]): mapping(item) for item in items}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _deploy_stage() -> dict[str, object]:
    return _stage("deploy_")


def _stage(prefix: str) -> dict[str, object]:
    (each,) = mapping(_stage_list()[0]).values()
    assert isinstance(each, list)
    (stage,) = (
        mapping(item) for item in each if str(mapping(item)["stage"]).startswith(prefix)
    )
    return stage


def _stage_list() -> list[object]:
    stages = read_yaml(EXTENDS)["stages"]
    assert isinstance(stages, list)
    return stages


def test_deploy_branch_defaults_to_main() -> None:
    assert _parameters(EXTENDS)["deployBranch"]["default"] == "refs/heads/main"
    assert _parameters(STEPS)["deployBranch"]["default"] == ""


def test_deploy_stage_requires_branch_and_rejects_pull_requests() -> None:
    condition = " ".join(str(_deploy_stage()["condition"]).split())
    assert condition.startswith("and(succeeded(),")
    assert (
        "eq(variables['Build.SourceBranch'], '${{ parameters.deployBranch }}')"
        in condition
    )
    assert "ne(variables['Build.Reason'], 'PullRequest')" in condition


def test_preview_stage_has_the_deploy_branch_gate() -> None:
    """A what-if or plan runs consumer code with the deploy identity, so gate it too."""
    preview = _stage("preview_")
    assert "condition" in preview
    assert preview["condition"] == _deploy_stage()["condition"]


@pytest.mark.parametrize("prefix", ["preview_", "deploy_"])
def test_stages_select_hosted_or_named_pool(prefix: str) -> None:
    assert _parameters(EXTENDS)["pool"]["default"] == "hosted"
    assert _parameters(EXTENDS)["vmImage"]["default"] == "ubuntu-24.04"
    assert _stage(prefix)["pool"] == {
        "${{ if eq(parameters.pool, 'hosted') }}": {
            "vmImage": "${{ parameters.vmImage }}"
        },
        "${{ else }}": {"name": "${{ parameters.pool }}"},
    }


def test_both_stages_pass_branch_to_step_guard() -> None:
    text = _text(EXTENDS)
    assert text.count("deployBranch: ${{ parameters.deployBranch }}") == 2
    steps = _text(STEPS)
    assert "DEPLOY_BRANCH: ${{ parameters.deployBranch }}" in steps
    assert 'fail "Pull-request builds must not preview or deploy"' in steps
    assert 'fail "Only ${DEPLOY_BRANCH} may preview or deploy"' in steps
    assert '[[ "${BUILD_SOURCEBRANCH:-}" == "$DEPLOY_BRANCH" ]] ||' in steps
    assert '"${MODE:-}" == deploy' not in steps


def test_environment_checks_stay_documented_as_defence_in_depth() -> None:
    header = _text(EXTENDS).split("parameters:", 1)[0]
    for check in ("Branch control", "Approvals", "Exclusive lock", "Required template"):
        assert check in header
    for text in ("Preview and deploy stages", "bicep-check.yml", "terraform-check.yml"):
        assert text in header


def test_deploy_guide_documents_gated_preview_and_connection_checks() -> None:
    guide = " ".join(_text(ROOT / "docs/deploy.md").split())
    assert "Each `preview_<name>` and `deploy_<name>` stage runs only when" in guide
    assert "On every `azure-<env>` service connection, add *Branch control*" in guide
    assert "On the prod service connection" not in guide


def test_preview_artifact_documents_retention_and_secret_handling() -> None:
    publish = _text(STEPS).split("Preview artifact retention and secrets", 1)[1]
    assert "retention" in publish
    assert "Key Vault" in publish
    assert "sensitive" in publish


def test_terraform_checks_cache_providers() -> None:
    ado = _text(ADO_CHECK)
    assert "task: Cache@2" in ado
    assert ".terraform.lock.hcl" in ado
    assert "variable=TF_PLUGIN_CACHE_DIR" in ado
    github = _text(GITHUB_CHECK)
    assert "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0" in github
    assert "TF_PLUGIN_CACHE_DIR=" in github
    for path in (ADO_CHECK, GITHUB_CHECK):
        assert "terraform init -backend=false -input=false -lockfile=readonly" in _text(
            path
        )


@pytest.mark.parametrize("path", [STEPS, EXTENDS, GITHUB_DEPLOY])
def test_privileged_deploy_paths_restore_no_cache(path: Path) -> None:
    text = _text(path)
    assert "Cache@2" not in text
    assert "actions/cache@" not in text
