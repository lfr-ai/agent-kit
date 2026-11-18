from collections.abc import Callable
from typing import Final

from hypothesis import given
from hypothesis import strategies as st
import pytest

from platform_kit_runtime.retrieval import (
    LabelledQuery,
    RetrievalConfigurationError,
    RetrievalMetrics,
    evaluate_retrieval,
    recall_at_k,
    reciprocal_rank,
)

pytestmark = pytest.mark.unit

IDS: Final[st.SearchStrategy[str]] = st.sampled_from(["a", "b", "c", "d", "e"])


def unchecked[ResultT](function: Callable[..., ResultT]) -> Callable[..., ResultT]:
    return function


def test_recall_counts_unique_relevant_hits_within_cutoff() -> None:
    relevant = frozenset({"a", "c"})
    assert recall_at_k(retrieved=["a", "b", "c"], relevant=relevant, k=2) == 0.5
    assert recall_at_k(retrieved=["a", "b", "c"], relevant=relevant, k=3) == 1.0
    assert recall_at_k(retrieved=["a", "a"], relevant=relevant, k=2) == 0.5
    assert recall_at_k(retrieved=[], relevant=relevant, k=1) == 0.0


def test_reciprocal_rank_uses_first_relevant_result() -> None:
    assert (
        reciprocal_rank(retrieved=["x", "a", "b"], relevant=frozenset({"a", "b"}))
        == 0.5
    )
    assert reciprocal_rank(retrieved=["a"], relevant=frozenset({"a"})) == 1.0
    assert reciprocal_rank(retrieved=["x"], relevant=frozenset({"a"})) == 0.0
    assert reciprocal_rank(retrieved=[], relevant=frozenset({"a"})) == 0.0


def test_dataset_metrics_are_unweighted_means() -> None:
    dataset = (
        LabelledQuery(query_id="q1", relevant_ids=frozenset({"a"})),
        LabelledQuery(query_id="q2", relevant_ids=frozenset({"d", "z"})),
    )
    metrics = evaluate_retrieval(
        dataset=dataset, results={"q1": ["a", "b"], "q2": ["c", "d", "e"]}, k=1
    )
    assert metrics == RetrievalMetrics(k=1, queries=2, recall_at_k=0.5, mrr=0.75)


@pytest.mark.parametrize("k", [0, -1, True, 1.0])
def test_invalid_cutoff_is_rejected(k: object) -> None:
    with pytest.raises(RetrievalConfigurationError):
        unchecked(recall_at_k)(retrieved=["a"], relevant=frozenset({"a"}), k=k)


def test_empty_relevance_is_rejected() -> None:
    with pytest.raises(RetrievalConfigurationError):
        recall_at_k(retrieved=["a"], relevant=frozenset(), k=1)


@pytest.mark.parametrize(
    ("query_id", "relevant_ids"),
    [("", frozenset({"a"})), ("q", frozenset()), ("q", {"a"}), ("q", frozenset({" "}))],
)
def test_labelled_query_validation(query_id: object, relevant_ids: object) -> None:
    with pytest.raises(RetrievalConfigurationError):
        unchecked(LabelledQuery)(query_id=query_id, relevant_ids=relevant_ids)


@pytest.mark.parametrize(
    ("dataset", "results"),
    [
        ((), {}),
        (
            (
                LabelledQuery(query_id="q", relevant_ids=frozenset({"a"})),
                LabelledQuery(query_id="q", relevant_ids=frozenset({"b"})),
            ),
            {"q": ["a"]},
        ),
        ((LabelledQuery(query_id="q", relevant_ids=frozenset({"a"})),), {}),
    ],
)
def test_incomplete_or_ambiguous_datasets_are_rejected(
    dataset: tuple[LabelledQuery, ...], results: dict[str, list[str]]
) -> None:
    with pytest.raises(RetrievalConfigurationError):
        evaluate_retrieval(dataset=dataset, results=results, k=1)


@pytest.mark.property
@given(
    retrieved=st.lists(IDS, max_size=8),
    relevant=st.frozensets(IDS, min_size=1),
    k=st.integers(min_value=1, max_value=9),
)
def test_metric_bounds_and_monotonic_recall(
    retrieved: list[str], relevant: frozenset[str], k: int
) -> None:
    recall = recall_at_k(retrieved=retrieved, relevant=relevant, k=k)
    rank = reciprocal_rank(retrieved=retrieved, relevant=relevant)
    assert 0.0 <= recall <= recall_at_k(retrieved=retrieved, relevant=relevant, k=k + 1)
    assert recall_at_k(retrieved=retrieved, relevant=relevant, k=k + 1) <= 1.0
    assert 0.0 <= rank <= 1.0
    assert (rank == 1.0) == (bool(retrieved) and retrieved[0] in relevant)
    assert (rank == 0.0) == relevant.isdisjoint(retrieved)
