"""Recorded evaluation completeness is distinct from a live agent evaluation."""

import json
from pathlib import Path
import runpy

import pytest

_ASSETS = (
    Path(__file__).resolve().parents[3]
    / "packages/shared/.apm/skills/kit-feedback-loop/assets"
)
_CHECKER = runpy.run_path(str(_ASSETS / "check_skill_evaluations.py"))


def _cases() -> dict[str, object]:
    return {
        "schema_version": 1,
        "cases": [
            {
                "id": "positive",
                "skill": "kit-improve",
                "prompt": "Synthetic reusable correction",
                "should_invoke": True,
                "checks": ["source_changed", "no_publication"],
            },
            {
                "id": "negative",
                "skill": "kit-improve",
                "prompt": "Synthetic project-only fact",
                "should_invoke": False,
                "checks": ["shared_source_unchanged"],
            },
        ],
    }


def _results() -> dict[str, object]:
    return {
        "schema_version": 1,
        "run": {
            "source_revision": "candidate-1",
            "host": "synthetic-host",
            "host_version": "1",
            "model": "synthetic-model",
            "dataset_revision": "cases-1",
        },
        "results": [
            {
                "case_id": "positive",
                "invoked": True,
                "checks": {"source_changed": True, "no_publication": True},
                "evidence": "synthetic observation",
            },
            {
                "case_id": "negative",
                "invoked": False,
                "checks": {"shared_source_unchanged": True},
                "evidence": "synthetic observation",
            },
        ],
    }


def test_complete_explicit_observations_pass() -> None:
    """Success requires every case and every individual criterion."""
    assert _CHECKER["failures"](_cases(), _results()) == []


def test_standalone_self_test_does_not_need_a_model(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The embedded acceptance and veto probes run without external services."""
    assert _CHECKER["main"](["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "change",
    [
        {"invoked": False},
        {"checks": {"source_changed": False, "no_publication": True}},
    ],
)
def test_any_observed_regression_fails_without_averaging_it_away(
    change: dict[str, object],
) -> None:
    """A safety failure cannot be hidden behind a good aggregate score."""
    results = _results()
    rows = results["results"]
    assert isinstance(rows, list)
    rows[0].update(change)

    assert _CHECKER["failures"](_cases(), results) == ["positive"]


@pytest.mark.parametrize(
    "change",
    [
        {"invoked": 1},
        {"invoked": None},
        {"checks": {"source_changed": True}},
        {"checks": {"source_changed": True, "no_publication": None}},
        {"checks": {"source_changed": True, "no_publication": 1}},
        {"evidence": ""},
        {"case_id": "unknown"},
    ],
)
def test_incomplete_or_ambiguous_observations_are_input_errors(
    change: dict[str, object],
) -> None:
    """Missing/unchecked criteria are not passes or measured regressions."""
    results = _results()
    rows = results["results"]
    assert isinstance(rows, list)
    rows[0].update(change)

    with pytest.raises(_CHECKER["EvaluationInputError"]):
        _CHECKER["failures"](_cases(), results)


def test_missing_and_duplicate_cases_are_rejected() -> None:
    """Every dataset case is run exactly once within each identified run."""
    observed = _results()["results"]
    assert isinstance(observed, list)
    for rows in ([], observed * 2):
        result = {**_results(), "results": rows}
        with pytest.raises(_CHECKER["EvaluationInputError"]):
            _CHECKER["failures"](_cases(), result)


def test_starter_results_cannot_claim_an_unrun_evaluation_passed() -> None:
    """The shipped empty result template is deliberately incomplete."""
    cases = json.loads(
        (_ASSETS / "skill-evaluation-cases.json.template").read_text("utf-8")
    )
    results = json.loads(
        (_ASSETS / "skill-evaluation-results.json.template").read_text("utf-8")
    )

    with pytest.raises(_CHECKER["EvaluationInputError"]):
        _CHECKER["failures"](cases, results)


def test_run_metadata_must_be_filled() -> None:
    """The source, dataset, host and model must identify the actual run."""
    results = _results()
    run = results["run"]
    assert isinstance(run, dict)
    run["model"] = "REPLACE_WITH_EXACT_MODEL"

    with pytest.raises(_CHECKER["EvaluationInputError"], match="metadata"):
        _CHECKER["failures"](_cases(), results)


def test_cli_rejects_duplicate_json_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ambiguous JSON must fail before any results are counted."""
    cases = tmp_path / "cases.json"
    results = tmp_path / "results.json"
    cases.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
    results.write_text(json.dumps(_results()), encoding="utf-8")

    assert _CHECKER["main"](["--cases", str(cases), "--results", str(results)]) == 2
    assert "duplicate JSON field" in capsys.readouterr().err


@pytest.mark.parametrize(("observed", "expected"), [(True, 0), (False, 1)])
def test_cli_separates_passes_from_observed_regressions(
    tmp_path: Path, observed: bool, expected: int
) -> None:
    """The CLI's exit status describes actual complete observation records."""
    cases = tmp_path / "cases.json"
    results = tmp_path / "results.json"
    data = _results()
    rows = data["results"]
    assert isinstance(rows, list)
    rows[0]["checks"]["no_publication"] = observed
    cases.write_text(json.dumps(_cases()), encoding="utf-8")
    results.write_text(json.dumps(data), encoding="utf-8")

    assert _CHECKER["main"](["--cases", str(cases), "--results", str(results)]) == (
        expected
    )


@pytest.mark.parametrize("section", ["document", "run", "case", "result"])
def test_unknown_evaluation_fields_are_rejected(section: str) -> None:
    """Unreviewed schema extensions must not silently change a gate's meaning."""
    cases = _cases()
    results = _results()
    if section == "document":
        results["unreviewed"] = True
    elif section == "run":
        run = results["run"]
        assert isinstance(run, dict)
        run["unreviewed"] = True
    else:
        rows = cases["cases"] if section == "case" else results["results"]
        assert isinstance(rows, list)
        rows[0]["unreviewed"] = True

    with pytest.raises(_CHECKER["EvaluationInputError"], match="fields"):
        _CHECKER["failures"](cases, results)
