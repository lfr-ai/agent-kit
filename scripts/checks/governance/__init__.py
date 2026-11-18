"""Check local community and workflow contracts without using a GitHub account."""

import argparse
from pathlib import Path
import sys

from scripts.checks.governance.actions import python_action_findings
from scripts.checks.governance.community import (
    community_file_findings,
    dependabot,
    intake,
)
from scripts.checks.governance.ownership import (
    maintainers,
    ownership,
    publication_blockers,
)
from scripts.checks.governance.rulesets import ruleset_findings
from scripts.checks.governance.workflows import workflow_findings

_ROOT = Path(__file__).resolve().parents[3]


def check(root: Path) -> list[str]:
    """Validate local readiness without claiming hosted controls are configured."""
    findings = community_file_findings(root)
    findings.extend(dependabot(root))
    findings.extend(python_action_findings(root))
    try:
        config = maintainers(root)
        findings.extend(ownership(root, config))
        findings.extend(intake(root, config.repository))
    except (OSError, ValueError) as error:
        findings.append(str(error))
    findings.extend(workflow_findings(root))
    findings.extend(ruleset_findings(root))
    return findings


def main() -> int:
    """Report local failures and explicit publication blockers separately."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", action="store_true")
    args = parser.parse_args()
    findings = check(_ROOT)
    blockers = publication_blockers(_ROOT)
    for finding in findings:
        sys.stderr.write(f"{finding}\n")
    for blocker in blockers:
        sys.stderr.write(f"Publication blocked: {blocker}\n")
    if findings or (args.publication and blockers):
        return 1
    sys.stdout.write(
        "Local governance contracts passed; publication prerequisites remain separate.\n"
    )
    return 0
