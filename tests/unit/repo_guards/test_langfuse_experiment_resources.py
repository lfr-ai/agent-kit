"""Execute the portable Langfuse facade with synthetic data and no SDK."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace

import pytest

_ASSETS = (
    Path(__file__).resolve().parents[3]
    / "packages/ai/.apm/skills/kit-llm-evaluation/assets"
)


@pytest.fixture
def experiment(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    harness = ModuleType("evals.harness")
    harness.__dict__.update(runpy.run_path(str(_ASSETS / "eval_harness.py.template")))
    monkeypatch.setitem(sys.modules, "evals", ModuleType("evals"))
    monkeypatch.setitem(sys.modules, "evals.harness", harness)
    return SimpleNamespace(
        harness=harness,
        **runpy.run_path(str(_ASSETS / "langfuse_experiment.py.template")),
    )


def _identity(experiment: SimpleNamespace) -> object:
    return experiment.ExperimentIdentity(
        run_id="synthetic-run",
        dataset_version="synthetic-v1",
        dataset_fingerprint="sha256:" + "a" * 64,
        prompt_name="synthetic-prompt",
        prompt_version=7,
        model_alias="fake-model",
        temperature=0.0,
        seed=42,
    )


def _cases(experiment: SimpleNamespace) -> tuple[object, ...]:
    return (
        experiment.EvalCase(
            case_id="a",
            input="synthetic input",
            expected="yes",
            source="expert-written",
            tags=("adversarial", "must-refuse"),
        ),
        experiment.EvalCase(
            case_id="b",
            input="other input",
            expected="no",
            source="redacted-approved",
            tags=("no-answer",),
        ),
    )


class _Facade:
    def __init__(self, *, experiment: SimpleNamespace) -> None:
        self.experiment = experiment
        self.calls = 0
        self.metadata: dict[str, str] = {}
        self.data: list[Mapping[str, object]] = []
        self.max_concurrency = 0
        self.scores: list[object] = []
        self.name = ""
        self.description = ""
        self.completed = False
        self.summary = experiment.ExperimentSummary(
            run_name="synthetic-run", item_count=2, failed_items=0
        )

    def run_experiment(
        self,
        *,
        name: str,
        description: str,
        data: Sequence[Mapping[str, object]],
        task: Callable[[Mapping[str, object]], str],
        evaluators: Sequence[Callable[[Mapping[str, object], str], object]],
        metadata: Mapping[str, str],
        max_concurrency: int,
    ) -> object:
        self.calls += 1
        self.name, self.description = name, description
        self.data = list(data)
        self.metadata = dict(metadata)
        self.max_concurrency = max_concurrency
        for item in data:
            output = task(item)
            self.scores.extend(evaluate(item, output) for evaluate in evaluators)
        self.completed = True
        return self.summary


class _Scorer:
    name = "provenance"
    version = "provenance-v1"

    def __init__(self) -> None:
        self.cases: list[object] = []

    def score(self, *, case: object, output: str) -> float:
        self.cases.append(case)
        return float(output == "recorded")


class _ValueScorer:
    name = "untrusted"
    version = "untrusted-v1"

    def __init__(self, *, value: object) -> None:
        self.value = value
        self.calls = 0

    def score(self, *, case: object, output: str) -> object:
        self.calls += 1
        return self.value


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        -0.01,
        1.01,
        True,
        False,
        "0.5",
        None,
    ],
)
def test_invalid_scores_propagate_without_score_record_or_success_summary(
    experiment: SimpleNamespace, value: object
) -> None:
    sdk = _Facade(experiment=experiment)
    scorer = _ValueScorer(value=value)
    runner = experiment.LangfuseExperimentRunner(sdk=sdk, export_approved=True)
    with pytest.raises(experiment.harness.EvalInputError, match="untrusted: score"):
        runner.run(
            identity=_identity(experiment),
            cases=_cases(experiment),
            task=lambda _case: "recorded",
            scorers=(scorer,),
            max_concurrency=1,
        )
    assert sdk.calls == scorer.calls == 1
    assert sdk.scores == []
    assert not sdk.completed


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0, 0, 1])
def test_valid_scores_preserve_numeric_bounds(
    experiment: SimpleNamespace, value: float
) -> None:
    sdk = _Facade(experiment=experiment)
    scorer = _ValueScorer(value=value)
    runner = experiment.LangfuseExperimentRunner(sdk=sdk, export_approved=True)
    assert (
        runner.run(
            identity=_identity(experiment),
            cases=_cases(experiment),
            task=lambda _case: "recorded",
            scorers=(scorer,),
            max_concurrency=1,
        )
        is sdk.summary
    )
    assert sdk.scores == [
        experiment.ScoreRecord(name="untrusted", value=float(value)),
        experiment.ScoreRecord(name="untrusted", value=float(value)),
    ]
    assert sdk.completed


def test_denied_export_makes_no_sdk_task_or_scorer_calls(
    experiment: SimpleNamespace,
) -> None:
    sdk = _Facade(experiment=experiment)
    scorer = _Scorer()
    task_cases: list[object] = []
    runner = experiment.LangfuseExperimentRunner(sdk=sdk, export_approved=False)
    with pytest.raises(experiment.ExportNotApprovedError, match="explicit approval"):
        runner.run(
            identity=_identity(experiment),
            cases=_cases(experiment),
            task=lambda case: task_cases.append(case) or "recorded",
            scorers=(scorer,),
            max_concurrency=2,
        )
    assert sdk.calls == 0
    assert task_cases == scorer.cases == []
    assert not sdk.completed


def test_approved_export_roundtrips_provenance_and_bounds_concurrency(
    experiment: SimpleNamespace,
) -> None:
    sdk = _Facade(experiment=experiment)
    scorer = _Scorer()
    cases = _cases(experiment)
    task_cases: list[object] = []
    runner = experiment.LangfuseExperimentRunner(sdk=sdk, export_approved=True)
    summary = runner.run(
        identity=_identity(experiment),
        cases=cases,
        task=lambda case: task_cases.append(case) or "recorded",
        scorers=(scorer,),
        max_concurrency=2,
    )
    assert summary is sdk.summary
    assert sdk.calls == 1
    assert task_cases == scorer.cases == list(cases)
    assert sdk.max_concurrency == 2
    assert sdk.name == "synthetic-run"
    assert sdk.description == "synthetic-prompt v7 on fake-model against synthetic-v1"
    assert sdk.metadata == {
        "run_id": "synthetic-run",
        "dataset_version": "synthetic-v1",
        "dataset_fingerprint": "sha256:" + "a" * 64,
        "prompt_name": "synthetic-prompt",
        "prompt_version": "7",
        "model_alias": "fake-model",
        "temperature": "0.0",
        "seed": "42",
    }
    assert sdk.scores == [
        experiment.ScoreRecord(name="provenance", value=1.0),
        experiment.ScoreRecord(name="provenance", value=1.0),
    ]
    assert all(
        set(item) == {"input", "expected_output", "metadata"} for item in sdk.data
    )


@pytest.mark.parametrize("concurrency", [0, -1])
def test_invalid_concurrency_is_rejected_before_any_calls(
    experiment: SimpleNamespace,
    concurrency: int,
) -> None:
    sdk = _Facade(experiment=experiment)
    scorer = _Scorer()
    task_cases: list[object] = []
    runner = experiment.LangfuseExperimentRunner(sdk=sdk, export_approved=True)
    with pytest.raises(ValueError, match="positive"):
        runner.run(
            identity=_identity(experiment),
            cases=_cases(experiment),
            task=lambda case: task_cases.append(case) or "recorded",
            scorers=(scorer,),
            max_concurrency=concurrency,
        )
    assert sdk.calls == 0
    assert task_cases == scorer.cases == []


@pytest.mark.parametrize("boundary", ["sdk", "task", "scorer"])
def test_failures_propagate_without_retry_or_success_summary(
    experiment: SimpleNamespace,
    boundary: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = _Facade(experiment=experiment)
    scorer = _Scorer()
    error = RuntimeError("synthetic facade failure")
    task_calls: list[object] = []
    failure_calls: list[str] = []

    def task(case: object) -> str:
        task_calls.append(case)
        if boundary == "task":
            raise error
        return "recorded"

    def fail(*args: object, **kwargs: object) -> float:
        failure_calls.append(boundary)
        raise error

    if boundary == "sdk":
        monkeypatch.setattr(sdk, "run_experiment", fail)
    if boundary == "scorer":
        monkeypatch.setattr(scorer, "score", fail)
    runner = experiment.LangfuseExperimentRunner(sdk=sdk, export_approved=True)
    with pytest.raises(RuntimeError) as caught:
        runner.run(
            identity=_identity(experiment),
            cases=_cases(experiment),
            task=task,
            scorers=(scorer,),
            max_concurrency=1,
        )
    assert caught.value is error
    assert len(task_calls) == (0 if boundary == "sdk" else 1)
    assert failure_calls == ([] if boundary == "task" else [boundary])
    assert not sdk.completed


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"case_id": "a", "source": ""},
        {"case_id": "a", "source": 1},
        {"case_id": "a", "tags": "not-a-list"},
        {"case_id": "a", "tags": [1]},
    ],
)
def test_evaluator_rejects_malformed_items_before_scoring(
    experiment: SimpleNamespace,
    metadata: object,
) -> None:
    scorer = _Scorer()
    evaluate = experiment.scorer_evaluator(scorer)
    with pytest.raises(TypeError, match="experiment item"):
        evaluate({"input": "q", "expected_output": "yes", "metadata": metadata}, "yes")
    assert scorer.cases == []


def test_evaluator_keeps_default_provenance_for_minimal_items(
    experiment: SimpleNamespace,
) -> None:
    scorer = _Scorer()
    evaluate = experiment.scorer_evaluator(scorer)
    evaluate(
        {"input": "q", "expected_output": "yes", "metadata": {"case_id": "a"}},
        "recorded",
    )
    assert scorer.cases == [experiment.EvalCase(case_id="a", input="q", expected="yes")]
