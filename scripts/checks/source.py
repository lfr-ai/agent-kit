"""Validate the canonical Agent Kit catalog and package sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from agent_kit.composition.root import validate_source
from agent_kit.core.primitives import JSON_INDENT

if TYPE_CHECKING:
    from collections.abc import Iterable

    from agent_kit.core.models import CheckReport, Finding

_ROOT = Path(__file__).resolve().parent.parent.parent


def write_findings(findings: Iterable[Finding]) -> None:
    """Write each finding to stderr as ``path: message [code]``."""
    for finding in findings:
        sys.stderr.write(f"{finding.path}: {finding.message} [{finding.code}]\n")


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
        report = validate_source(arguments.root.resolve())
    except (OSError, ValueError) as error:
        sys.stderr.write(f"source catalog could not be checked: {error}\n")
        return 1
    if arguments.json:
        sys.stdout.write(
            f"{json.dumps(_report_dict(report), indent=JSON_INDENT, ensure_ascii=True)}\n"
        )
    elif report.valid:
        sys.stdout.write(f"Source catalog valid: {report.version}\n")
    else:
        write_findings(report.findings)
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
