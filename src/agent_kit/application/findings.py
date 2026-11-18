"""Own the shared collector helper for application validation diagnostics."""

from __future__ import annotations

from agent_kit.core.models import Finding


def add_finding(findings: list[Finding], code: str, message: str, path: str) -> None:
    """Append a ``Finding`` with a dotted ``code`` at a source-relative ``path``."""
    findings.append(Finding(code=code, message=message, path=path))
