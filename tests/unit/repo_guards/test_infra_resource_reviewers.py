"""Unrecognized or incomplete infrastructure previews must never look approved."""

import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

_PACKAGES = Path(__file__).resolve().parents[3] / "packages"
_OWNERS = {"kit-terraform-validation": "terraform", "kit-azure-validation": "bicep"}


def _asset(skill: str, filename: str) -> Path:
    """Locate a reviewer script in the feature bundle that owns its skill."""
    return _PACKAGES / _OWNERS[skill] / ".apm/skills" / skill / "assets" / filename


@pytest.mark.parametrize(
    ("skill", "filename", "function", "payload", "message", "error_type"),
    [
        (
            "kit-terraform-validation",
            "review_plan.py",
            "analyze_plan",
            {
                "format_version": "1.2",
                "resource_changes": [
                    {"address": "example.item", "change": {"actions": ["unknown"]}}
                ],
            },
            "actions",
            ValueError,
        ),
        (
            "kit-terraform-validation",
            "review_plan.py",
            "analyze_plan",
            {"format_version": "1.2", "resource_changes": None},
            "resource_changes",
            TypeError,
        ),
        (
            "kit-terraform-validation",
            "review_plan.py",
            "analyze_plan",
            {"format_version": "99.0", "resource_changes": []},
            "format_version",
            ValueError,
        ),
        (
            "kit-terraform-validation",
            "review_plan.py",
            "analyze_plan",
            {"format_version": "1.2", "resource_changes": [{"address": "item"}]},
            "change object",
            ValueError,
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            "analyze_whatif",
            {"changes": [{"resourceId": "/example", "changeType": "Unknown"}]},
            "changeType",
            ValueError,
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            "analyze_whatif",
            {"status": "Failed", "changes": []},
            "failed",
            ValueError,
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            "analyze_whatif",
            {"unrelated": {"changes": []}},
            "expected changes",
            ValueError,
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            "analyze_whatif",
            {"changes": [{"resourceId": "/example", "delta": []}]},
            "changeType",
            ValueError,
        ),
    ],
)
def test_incomplete_preview_is_rejected(
    skill: str,
    filename: str,
    function: str,
    payload: object,
    message: str,
    error_type: type[Exception],
) -> None:
    namespace = runpy.run_path(str(_asset(skill, filename)))
    analyze = namespace[function]
    assert callable(analyze)
    with pytest.raises(error_type, match=message):
        analyze(payload)


@pytest.mark.parametrize(
    ("skill", "filename", "payload", "code", "kind"),
    [
        (
            "kit-terraform-validation",
            "review_plan.py",
            {"format_version": "1.2", "resource_changes": []},
            0,
            "create",
        ),
        (
            "kit-terraform-validation",
            "review_plan.py",
            {
                "format_version": "1.2",
                "resource_changes": [
                    {"address": "example.item", "change": {"actions": ["delete"]}}
                ],
            },
            3,
            "delete",
        ),
        (
            "kit-terraform-validation",
            "review_plan.py",
            {
                "format_version": "1.2",
                "resource_changes": [
                    {
                        "address": "example.item",
                        "change": {"actions": ["create", "delete"]},
                    }
                ],
            },
            4,
            "replace",
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            {"changes": [{"resourceId": "/example", "changeType": "Delete"}]},
            3,
            "delete",
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            {"changes": [{"resourceId": "/example", "changeType": "Deploy"}]},
            4,
            "review",
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            {"changes": [{"resourceId": "/example", "changeType": "Ignore"}]},
            4,
            "review",
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            {"changes": [{"resourceId": "/example", "changeType": "Unsupported"}]},
            4,
            "review",
        ),
        (
            "kit-azure-validation",
            "review_whatif.py",
            {"changes": [{"resourceId": "/example", "changeType": "NoChange"}]},
            0,
            "no-change",
        ),
    ],
)
def test_preview_cli_reports_risk_and_exact_summary(
    tmp_path: Path, skill: str, filename: str, payload: object, code: int, kind: str
) -> None:
    path = tmp_path / "preview.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed first-party reviewer, synthetic file
        [sys.executable, str(_asset(skill, filename)), "--file", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == code, result.stderr
    report = json.loads(result.stdout)
    assert set(report) == {"summary", "lists"}
    assert report["summary"][kind] == len(report["lists"][kind])
    if code:
        assert report["summary"][kind] == 1
        assert "operator review" in result.stderr


@pytest.mark.parametrize(
    ("skill", "filename"),
    [
        ("kit-terraform-validation", "review_plan.py"),
        ("kit-azure-validation", "review_whatif.py"),
    ],
)
def test_malformed_preview_cli_is_not_a_success_shaped_summary(
    tmp_path: Path, skill: str, filename: str
) -> None:
    path = tmp_path / "preview.json"
    path.write_text("{}", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed first-party reviewer, synthetic file
        [sys.executable, str(_asset(skill, filename)), "--file", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Cannot review" in result.stderr
