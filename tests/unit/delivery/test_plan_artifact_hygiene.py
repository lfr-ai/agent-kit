"""Reusable pipelines never publish Terraform state and keep plan artifacts short-lived."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from delivery_tools.catalog import ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit
_WORKFLOWS = ROOT.parent.parent / ".github/workflows"
_MAX_RETENTION_DAYS = 7
_UPLOAD = "actions/upload-artifact@"
_STEPS = ROOT / "azure-devops/steps/azure-deploy.yml"


def _uploads(path: Path) -> list[dict[str, object]]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith(_UPLOAD)
    ]


@pytest.mark.parametrize("path", sorted(_WORKFLOWS.glob("delivery-*.yml")), ids=str)
def test_github_uploads_never_include_state_and_expire_quickly(path: Path) -> None:
    for step in _uploads(path):
        options = step["with"]
        assert isinstance(options, dict)
        assert "tfstate" not in str(options.get("path", "")).lower()
        assert "tfstate" not in str(options.get("name", "")).lower()
        retention = options.get("retention-days")
        assert isinstance(retention, int)
        assert 1 <= retention <= _MAX_RETENTION_DAYS


def test_github_deploy_plan_upload_is_present_and_one_day() -> None:
    (step,) = _uploads(_WORKFLOWS / "delivery-azure-deploy.yml")
    options = step["with"]
    assert isinstance(options, dict)
    assert options["retention-days"] == 1


def test_azure_devops_publishes_only_the_preview_directory() -> None:
    steps = yaml.safe_load(_STEPS.read_text(encoding="utf-8"))
    published = [
        str(step["publish"])
        for step in _flatten(steps)
        if isinstance(step, dict) and "publish" in step
    ]
    assert published == [
        "$(Pipeline.Workspace)/delivery-azure-deploy-${{ parameters.environment }}"
    ]
    assert not any("tfstate" in item.lower() for item in published)


def _flatten(value: object) -> list[object]:
    if isinstance(value, list):
        return [leaf for item in value for leaf in _flatten(item)]
    if isinstance(value, dict):
        return [value, *(leaf for item in value.values() for leaf in _flatten(item))]
    return []
