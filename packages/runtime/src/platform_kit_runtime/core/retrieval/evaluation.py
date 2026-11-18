"""Pure retrieval quality metrics over a labelled dataset; stdlib only."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import fsum

from platform_kit_runtime.core.retrieval.models import RetrievalConfigurationError
from platform_kit_runtime.core.validation import is_nonblank


@dataclass(frozen=True, kw_only=True, slots=True)
class LabelledQuery:
    """A query and the IDs a correct retriever should return.

    Attributes:
        query_id (str): Nonblank identifier, unique within a dataset.
        relevant_ids (frozenset[str]): Nonempty set of relevant document or chunk IDs.
    """

    query_id: str
    relevant_ids: frozenset[str]

    def __post_init__(self) -> None:
        """Reject blank identifiers and empty relevance labels.

        Raises:
            RetrievalConfigurationError: A field is blank, empty or mistyped.
        """
        labelled = isinstance(self.relevant_ids, frozenset) and all(
            is_nonblank(item) for item in self.relevant_ids
        )
        if not is_nonblank(self.query_id) or not labelled or not self.relevant_ids:
            raise RetrievalConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class RetrievalMetrics:
    """Mean retrieval quality over a dataset.

    Attributes:
        k (int): Cutoff used for recall.
        queries (int): Number of evaluated queries.
        recall_at_k (float): Mean fraction of relevant IDs found in the top ``k``.
        mrr (float): Mean reciprocal rank of the first relevant ID; zero when none.
    """

    k: int
    queries: int
    recall_at_k: float
    mrr: float


def recall_at_k(*, retrieved: Sequence[str], relevant: frozenset[str], k: int) -> float:
    """Return the fraction of relevant IDs found in the first ``k`` results.

    Args:
        retrieved (Sequence[str]): Ranked result IDs, best first; repeats count once.
        relevant (frozenset[str]): Nonempty set of relevant IDs.
        k (int): Positive cutoff.

    Returns:
        float: A value from zero to one.

    Raises:
        RetrievalConfigurationError: ``k`` is not positive or ``relevant`` is empty.
    """
    if type(k) is not int or k < 1 or not relevant:
        raise RetrievalConfigurationError
    return len(relevant.intersection(retrieved[:k])) / len(relevant)


def reciprocal_rank(*, retrieved: Sequence[str], relevant: frozenset[str]) -> float:
    """Return ``1 / rank`` of the first relevant result, or zero when none is found.

    Args:
        retrieved (Sequence[str]): Ranked result IDs, best first.
        relevant (frozenset[str]): Relevant IDs.

    Returns:
        float: A value from zero to one.
    """
    ranks = (rank for rank, item in enumerate(retrieved, start=1) if item in relevant)
    first = next(ranks, None)
    return 0.0 if first is None else 1 / first


def evaluate_retrieval(
    *,
    dataset: Sequence[LabelledQuery],
    results: Mapping[str, Sequence[str]],
    k: int,
) -> RetrievalMetrics:
    """Compute mean recall@k and MRR for ranked results keyed by query ID.

    Args:
        dataset (Sequence[LabelledQuery]): Nonempty labelled queries with unique IDs.
        results (Mapping[str, Sequence[str]]): Ranked result IDs for every query.
        k (int): Positive recall cutoff.

    Returns:
        RetrievalMetrics: Dataset means; each query has equal weight.

    Raises:
        RetrievalConfigurationError: The dataset is empty, has duplicate IDs, or a
            query has no results entry.
    """
    identifiers = [query.query_id for query in dataset]
    complete = all(identifier in results for identifier in identifiers)
    if not identifiers or len(set(identifiers)) != len(identifiers) or not complete:
        raise RetrievalConfigurationError
    recalls = [
        recall_at_k(retrieved=results[query.query_id], relevant=query.relevant_ids, k=k)
        for query in dataset
    ]
    ranks = [
        reciprocal_rank(retrieved=results[query.query_id], relevant=query.relevant_ids)
        for query in dataset
    ]
    return RetrievalMetrics(
        k=k,
        queries=len(dataset),
        recall_at_k=fsum(recalls) / len(dataset),
        mrr=fsum(ranks) / len(dataset),
    )
