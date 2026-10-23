"""The source catalog boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from agent_kit.core.models import CatalogSnapshot


class CatalogPort(Protocol):
    """Read catalog source data without exposing filesystem operations inward."""

    def load(self, root: Path) -> CatalogSnapshot:
        """Capture catalog, policy, manifests, resources, and root documents."""
