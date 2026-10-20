"""Invariant checks over pure catalog selection and strict unknown fields."""

import string
from dataclasses import replace
from itertools import product
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

_KEY_ALPHABET = string.ascii_lowercase + "-"


def test_unknown_catalog_keys_are_always_rejected(source_root: Path) -> None:
    """An arbitrary extra field cannot become an accepted configuration extension."""
    snapshot = FileCatalogAdapter().load(source_root)
    assert isinstance(snapshot.catalog, dict)
    baseline = dict(snapshot.catalog)

    @given(st.text(alphabet=_KEY_ALPHABET, min_size=1, max_size=30))
    @settings(max_examples=25, database=None, derandomize=True)
    def check(key: str) -> None:
        if key in baseline:
            return
        candidate = {**baseline, key: None}
        report = CatalogService().validate(replace(snapshot, catalog=candidate))

        assert not report.valid
        assert any("unknown" in finding.message for finding in report.findings)

    check()


def test_repeated_features_form_a_unique_deterministic_union(source_root: Path) -> None:
    """Exhaustive small feature sequences preserve deterministic unique selection."""
    snapshot = FileCatalogAdapter().load(source_root)
    service = CatalogService()
    # Three distinct features plus one repeated slot cover every set and order.
    for length in range(5):
        for features in product(("frontend", "iac", "backend"), repeat=length):
            first = service.compose(snapshot, "shared", features, ())
            second = service.compose(snapshot, "shared", features, ())

            assert first.files == second.files
            assert len(first.bundles) == len(set(first.bundles))
