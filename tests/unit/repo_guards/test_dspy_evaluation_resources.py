"""DSPy-style candidates reuse the harness without SDK, label or network access."""

from dataclasses import dataclass
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
def evaluation(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    package = ModuleType("evals")
    vars(package)["__path__"] = []
    monkeypatch.setitem(sys.modules, "evals", package)
    harness = ModuleType("evals.harness")
    monkeypatch.setitem(sys.modules, "evals.harness", harness)
    vars(harness).update(
        runpy.run_path(
            str(_ASSETS / "eval_harness.py.template"), run_name="evals.harness"
        )
    )
    task = runpy.run_path(str(_ASSETS / "dspy_task.py.template"))
    return SimpleNamespace(harness=harness, **task)


@dataclass(frozen=True, kw_only=True, slots=True)
class Prediction:
    answer: object


def test_candidate_receives_only_input_and_scores_with_existing_harness(
    evaluation: SimpleNamespace,
) -> None:
    received: list[str] = []

    def candidate(*, question: str) -> Prediction:
        received.append(question)
        return Prediction(answer="answer")

    case = evaluation.harness.EvalCase(
        case_id="synthetic-1",
        input="question",
        expected="answer",
        source="private-reference-source",
        tags=("held-out",),
    )
    task = evaluation.DspyTask(program=candidate)
    outputs = evaluation.harness.run_task(cases=[case], task=task, repeats=1)
    summaries = evaluation.harness.summarize(
        cases=[case], outputs=outputs, scorers=[evaluation.harness.ExactMatch()]
    )
    report = evaluation.harness.build_report(
        dataset_version="synthetic-v1",
        fingerprint="a" * 64,
        scorer_versions={"exact_match": evaluation.harness.ExactMatch().version},
        summaries=summaries,
        failures=[],
    )

    assert received == ["question"]
    assert task(case) == "answer"
    assert report["metrics"] == {"exact_match": 1.0}


@pytest.mark.parametrize("answer", [None, 1, True, {}, ["answer"]])
def test_nontext_prediction_is_explicit_and_never_echoed(
    evaluation: SimpleNamespace, answer: object
) -> None:
    def candidate(*, question: str) -> Prediction:
        return Prediction(answer=answer)

    case = evaluation.harness.EvalCase(
        case_id="synthetic-1", input="input", expected="private-reference"
    )
    with pytest.raises(
        evaluation.InvalidPredictionError, match="text answer"
    ) as caught:
        evaluation.DspyTask(program=candidate)(case)
    assert "private-reference" not in str(caught.value)


def test_missing_answer_is_an_explicit_error(evaluation: SimpleNamespace) -> None:
    def candidate(*, question: str) -> object:
        return object()

    case = evaluation.harness.EvalCase(case_id="x", input="input", expected="answer")
    with pytest.raises(evaluation.InvalidPredictionError) as caught:
        evaluation.DspyTask(program=candidate)(case)
    assert isinstance(caught.value.__cause__, AttributeError)


def test_candidate_failure_propagates_without_retry(
    evaluation: SimpleNamespace,
) -> None:
    calls: list[str] = []
    failure = RuntimeError("synthetic provider unavailable")

    def candidate(*, question: str) -> Prediction:
        calls.append(question)
        raise failure

    case = evaluation.harness.EvalCase(case_id="x", input="input", expected="answer")
    with pytest.raises(RuntimeError) as caught:
        evaluation.DspyTask(program=candidate)(case)
    assert caught.value is failure
    assert calls == ["input"]


def test_empty_text_remains_a_valid_scoring_input(evaluation: SimpleNamespace) -> None:
    def candidate(*, question: str) -> Prediction:
        return Prediction(answer="")

    case = evaluation.harness.EvalCase(case_id="x", input="input", expected="")
    assert evaluation.DspyTask(program=candidate)(case) == ""
