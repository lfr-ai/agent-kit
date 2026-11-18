"""Wire repository workflows to application and infrastructure collaborators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_kit.application.catalog import CatalogService
from agent_kit.application.provenance import ProvenanceService
from agent_kit.infrastructure.catalog import FileCatalogAdapter
from agent_kit.infrastructure.output import OutputAdapter

if TYPE_CHECKING:
    from pathlib import Path

    from agent_kit.core.models import CheckReport, CompositionPlan


def validate_source(root: Path) -> CheckReport:
    """Validate the canonical source tree at ``root``."""
    snapshot = FileCatalogAdapter().load(root)
    return CatalogService().validate(snapshot)


def plan_composition(
    root: Path,
    profile: str,
    features: tuple[str, ...],
    runtimes: tuple[str, ...],
    *,
    skills: tuple[str, ...] = (),
) -> CompositionPlan:
    """Capture the source tree at ``root`` and plan one validated composition.

    Invalid source or selection raises ``ValueError``; failed reads raise
    ``OSError``.
    """
    snapshot = FileCatalogAdapter().load(root)
    return CatalogService().compose(
        snapshot, profile, features, runtimes, skills=skills
    )


def compose_workspace(
    root: Path,
    profile: str,
    features: tuple[str, ...],
    runtimes: tuple[str, ...],
    output: Path,
    *,
    skills: tuple[str, ...] = (),
) -> Path:
    """Compose a selected source profile into a new workspace.

    Invalid source, selection or output containment raises ``ValueError``; an
    existing output or failed I/O raises ``OSError``; a host that cannot publish
    without replacement raises ``UnsupportedPublicationError``.

    Args:
        root (Path): Source checkout to capture and validate.
        profile (str): Base capability profile.
        features (tuple[str, ...]): Additional feature profiles.
        runtimes (tuple[str, ...]): Native targets; empty uses catalog defaults.
        output (Path): New destination that must not already exist.
        skills (tuple[str, ...]): Session skill selection; empty selects the profile.

    Returns:
        Path: Absolute destination after atomic, no-replace publication.
    """
    plan = plan_composition(root, profile, features, runtimes, skills=skills)
    return OutputAdapter().write(plan, output)


def verify_provenance(root: Path) -> CheckReport:
    """Verify the integrity of a composed workspace at ``root``."""
    snapshot = FileCatalogAdapter().load_composed(root)
    return ProvenanceService().verify(snapshot)
