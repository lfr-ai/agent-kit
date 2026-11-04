"""Wire repository workflows to application and infrastructure collaborators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.provenance_service import ProvenanceService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from agent_kit.infrastructure.output_adapter import OutputAdapter

if TYPE_CHECKING:
    from pathlib import Path

    from agent_kit.core.models import CheckReport


def validate_source(root: Path) -> CheckReport:
    """Validate the canonical source tree at ``root``."""
    snapshot = FileCatalogAdapter().load(root)
    return CatalogService().validate(snapshot)


def compose_workspace(
    root: Path,
    profile: str,
    features: tuple[str, ...],
    runtimes: tuple[str, ...],
    output: Path,
    *,
    skills: tuple[str, ...] = (),
) -> Path:
    """Compose a selected source profile into a new workspace."""
    snapshot = FileCatalogAdapter().load(root)
    plan = CatalogService().compose(
        snapshot, profile, features, runtimes, skills=skills
    )
    return OutputAdapter().write(plan, output)


def verify_provenance(root: Path) -> CheckReport:
    """Verify the integrity of a composed workspace at ``root``."""
    snapshot = FileCatalogAdapter().load_composed(root)
    return ProvenanceService().verify(snapshot)
