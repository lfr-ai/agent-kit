"""Read captured composed-workspace values shared by provenance checks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agent_kit.application.findings import add_finding
from agent_kit.application.provenance.record import PROVENANCE_FILE
from agent_kit.core.guards import is_json_object

if TYPE_CHECKING:
    from agent_kit.core.models import ComposedSnapshot, Finding, SourceDocument


def selected_targets(manifest: object) -> list[object]:
    """Return the ``targets`` list of a decoded manifest, or empty when absent."""
    targets = manifest.get("targets") if is_json_object(manifest) else None
    return targets if isinstance(targets, list) else []


def json_value(document: SourceDocument | None) -> object:
    """Decode captured JSON; return ``None`` for absent or invalid configuration."""
    try:
        return json.loads(document.text or "") if document is not None else None
    except ValueError:
        return None


def check_composed_links(snapshot: ComposedSnapshot, findings: list[Finding]) -> None:
    """Report a symlinked composed root or provenance file."""
    if snapshot.root_is_symlink:
        add_finding(findings, "provenance.symlink", "composed root is a symlink", ".")
    if snapshot.provenance_is_symlink:
        add_finding(
            findings,
            "provenance.symlink",
            "provenance file is a symlink",
            PROVENANCE_FILE,
        )
