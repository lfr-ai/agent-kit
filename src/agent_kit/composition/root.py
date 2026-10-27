"""Explicit composition of local validation and filesystem collaborators."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.provenance_service import ProvenanceService
from agent_kit.application.services.selection import parse_selection
from agent_kit.infrastructure.apm_adapter import ApmCliAdapter
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from agent_kit.infrastructure.output_adapter import OutputAdapter
from agent_kit.infrastructure.session_context import session_context
from agent_kit.presentation.cli import CliActions

if TYPE_CHECKING:
    from agent_kit.core.models import CheckReport, Selection


def _source_root_from_working_directory() -> Path:
    """Find the nearest catalog root, or use cwd for explicit error reporting."""
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "catalog.json").is_file():
            return candidate
    return current


def _load_selection(path: Path) -> Selection:
    """Read one selection file and validate it against its schema."""
    return parse_selection(FileCatalogAdapter().load_selection(path))


def build_actions() -> CliActions:
    """Wire adapters and application services for the command-line interface."""
    catalog_adapter = FileCatalogAdapter()
    catalog_service = CatalogService()
    provenance_service = ProvenanceService()
    output_adapter = OutputAdapter()
    apm_adapter = ApmCliAdapter()

    def check(root: Path) -> CheckReport:
        return catalog_service.validate(catalog_adapter.load(root))

    def compose(
        root: Path,
        profile: str,
        features: tuple[str, ...],
        runtimes: tuple[str, ...],
        output: Path,
        skills: tuple[str, ...],
    ) -> Path:
        snapshot = catalog_adapter.load(root)
        plan = catalog_service.compose(
            snapshot, profile, features, runtimes, skills=skills
        )
        return output_adapter.write(plan, output)

    def provenance(root: Path) -> CheckReport:
        return provenance_service.verify(catalog_adapter.load_composed(root))

    def apm_check(root: Path) -> CheckReport | None:
        report = provenance(root)
        if not report.valid:
            return report
        apm_adapter.check(root)
        return None

    return CliActions(
        apm_check=apm_check,
        check=check,
        compose=compose,
        default_root=_source_root_from_working_directory,
        context=session_context,
        load_selection=_load_selection,
        provenance=provenance,
    )
