"""Catalog validation and deterministic profile composition."""

from typing import Final

from agent_kit.application.catalog.errors import (
    CompositionCollisionError,
    CompositionError,
    CompositionIssue,
    OmittedResourceError,
    UnavailableBundleError,
    UnavailableSkillsError,
    UnknownProfileError,
)
from agent_kit.application.catalog.service import CatalogService

__all__: Final[list[str]] = [
    "CatalogService",
    "CompositionCollisionError",
    "CompositionError",
    "CompositionIssue",
    "OmittedResourceError",
    "UnavailableBundleError",
    "UnavailableSkillsError",
    "UnknownProfileError",
]
