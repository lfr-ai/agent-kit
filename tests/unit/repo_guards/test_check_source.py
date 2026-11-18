import json
from pathlib import Path

import pytest
import scripts.checks.source as source_checker

from agent_kit.core.models import CheckReport, Finding, ProfileSummary


def test_report_dict_renders_stable_machine_fields() -> None:
    report = CheckReport(
        findings=(Finding(code="E1", message="broken", path="catalog.json"),),
        profiles=(
            ProfileSummary(
                body_lines=10,
                description_chars=20,
                limits=(("skills", 5),),
                policy_lines=3,
                profile="shared",
                skill_count=2,
            ),
        ),
        version="0.1.0",
    )

    rendered = source_checker._report_dict(report)

    assert rendered == {
        "valid": False,
        "version": "0.1.0",
        "findings": [{"code": "E1", "message": "broken", "path": "catalog.json"}],
        "profiles": {
            "shared": {
                "skill_count": 2,
                "body_lines": 10,
                "description_chars": 20,
                "policy_lines": 3,
                "limits": {"skills": 5},
            }
        },
    }
    json.dumps(rendered)


def test_main_reports_findings_for_empty_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("sys.argv", ["source", "--root", str(tmp_path)])

    assert source_checker.main() == 1
    assert "[catalog.read]" in capsys.readouterr().err


def test_main_keeps_json_report_and_failure_status_for_invalid_source(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("sys.argv", ["source", "--root", str(tmp_path), "--json"])

    assert source_checker.main() == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["valid"] is False
    assert report["findings"]
    assert captured.err == ""


def test_main_reports_catalog_load_errors_actionably(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    load_error = OSError("cannot read source root")

    def fail_validate_source(root: Path) -> CheckReport:
        raise load_error

    monkeypatch.setattr(source_checker, "validate_source", fail_validate_source)
    monkeypatch.setattr("sys.argv", ["source", "--root", str(tmp_path)])

    assert source_checker.main() == 1
    diagnostic = capsys.readouterr().err

    assert "cannot read source root" in diagnostic
