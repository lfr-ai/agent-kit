"""Validate the canonical Agent Kit catalog and package sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

if TYPE_CHECKING:
    from agent_kit.core.models import CheckReport

_ROOT = Path(__file__).resolve().parents[1]
_JSON_INDENT = 2


def _report_dict(report: CheckReport) -> dict[str, object]:
    """Render the stable source-validation fields used by maintainer tooling."""
    return {
        "valid": report.valid,
        "version": report.version,
        "findings": [
            {"code": item.code, "message": item.message, "path": item.path}
            for item in report.findings
        ],
        "profiles": {
            item.profile: {
                "skill_count": item.skill_count,
                "body_lines": item.body_lines,
                "description_chars": item.description_chars,
                "policy_lines": item.policy_lines,
                "limits": dict(item.limits),
            }
            for item in report.profiles
        },
    }


def main() -> int:
    """Validate a source checkout and print human- or machine-readable results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    try:
        snapshot = FileCatalogAdapter().load(arguments.root.resolve())
        report = CatalogService().validate(snapshot)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"source catalog could not be checked: {error}\n")
        return 1
    if arguments.json:
        sys.stdout.write(
            f"{json.dumps(_report_dict(report), indent=_JSON_INDENT, ensure_ascii=True)}\n"
        )
    elif report.valid:
        sys.stdout.write(f"Source catalog valid: {report.version}\n")
    else:
        for finding in report.findings:
            sys.stderr.write(f"{finding.path}: {finding.message} [{finding.code}]\n")
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
