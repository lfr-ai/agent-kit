"""Workflow inventory, root and job permissions, and per-workflow contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from agent_kit.core.guards import is_json_object
from scripts.checks.governance.actions import step_findings
from scripts.checks.governance.ci import (
    AUDIT_CALL,
    AUDIT_WORKFLOW,
    CI_WORKFLOW,
    REVIEW_WORKFLOW,
    ci_findings,
    dependency_audit,
    dependency_review_workflow,
)
from scripts.checks.governance.delivery import (
    DELIVERY_WORKFLOWS,
    DEPLOY_WORKFLOW,
    delivery_workflow,
    deploy_findings,
)
from scripts.checks.governance.inputs import load_workflow
from scripts.checks.governance.release import (
    RELEASE_WORKFLOW,
    VERIFY_CALL,
    release_findings,
)

if TYPE_CHECKING:
    from pathlib import Path

# GitHub loads workflows only from the flat .github/workflows directory, so a
# purpose prefix groups them: toolkit-* (this repository), security-* (scans) and
# delivery-* (reusable consumer interface).
_CODEQL_WORKFLOW = "security-codeql.yml"
_SCORECARD_WORKFLOW = "security-scorecard.yml"
_WORKFLOWS = {
    CI_WORKFLOW,
    RELEASE_WORKFLOW,
    AUDIT_WORKFLOW,
    REVIEW_WORKFLOW,
    _CODEQL_WORKFLOW,
    _SCORECARD_WORKFLOW,
} | DELIVERY_WORKFLOWS
_REUSABLE = {CI_WORKFLOW: AUDIT_CALL, RELEASE_WORKFLOW: VERIFY_CALL}
_OIDC_READ = {"contents": "read", "id-token": "write"}
_PERMISSIONS = {
    (RELEASE_WORKFLOW, "publish"): {
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
    },
    # Caller grant for the reusable gate's Codecov OIDC upload job.
    (RELEASE_WORKFLOW, "verify"): _OIDC_READ,
    (CI_WORKFLOW, "coverage"): _OIDC_READ,
    (_CODEQL_WORKFLOW, "analyze"): {"contents": "read", "security-events": "write"},
    (_SCORECARD_WORKFLOW, "analysis"): {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
        "security-events": "write",
    },
    # Preflight reads environment protection rules; preview and apply use Azure OIDC.
    (DEPLOY_WORKFLOW, "preflight"): {"contents": "read", "actions": "read"},
    (DEPLOY_WORKFLOW, "plan"): _OIDC_READ,
    (DEPLOY_WORKFLOW, "deploy"): _OIDC_READ,
}


def _job_policy_findings(
    name: str, identifier: str, job: dict[str, object]
) -> list[str]:
    """Require timeouts, approved permissions, no secrets, and reviewed reuse.

    Args:
        name (str): Workflow file name used to prefix each finding.
        identifier (str): Job key within the workflow.
        job (dict[str, object]): Decoded job mapping.

    Returns:
        list[str]: One message per violated job rule; empty when the job passes.
    """
    findings: list[str] = []
    if "steps" in job and not isinstance(job.get("timeout-minutes"), str):
        findings.append(f"{name}: job {identifier} needs an explicit timeout")
    permissions = job.get("permissions")
    permitted = _PERMISSIONS.get((name, identifier), {"contents": "read"})
    if permissions is not None and permissions != permitted:
        findings.append(f"{name}: job {identifier} has unapproved permissions")
    if "secrets" in job:
        findings.append(f"{name}: job secrets must not be inherited or declared")
    reusable = job.get("uses")
    if reusable is not None and reusable != _REUSABLE.get(name):
        findings.append(f"{name}: unapproved reusable workflow")
    return findings


def _job_findings(name: str, identifier: str, job: object) -> list[str]:
    """Check one job's policy and every step it runs.

    Args:
        name (str): Workflow file name used to prefix each finding.
        identifier (str): Job key within the workflow.
        job (object): Decoded job value.

    Returns:
        list[str]: Policy and step findings; empty when the job passes.
    """
    if not is_json_object(job):
        return [f"{name}: job {identifier} must be a mapping"]
    findings = _job_policy_findings(name, identifier, job)
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        findings.append(f"{name}: steps must be a list")
        return findings
    for step in steps:
        findings.extend(step_findings(name, step))
    return findings


def _root_findings(
    name: str, raw: dict[str, object], triggers: dict[str, object]
) -> list[str]:
    """Reject privileged triggers and broader default permissions.

    Args:
        name (str): Workflow file name used to prefix each finding.
        raw (dict[str, object]): Decoded workflow document.
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.

    Returns:
        list[str]: One message per violated root rule; empty when the root passes.
    """
    findings: list[str] = []
    if "pull_request_target" in triggers:
        findings.append(f"{name}: pull_request_target is not an approved trigger")
    if raw.get("permissions") != {"contents": "read"}:
        findings.append(f"{name}: root permissions must be contents: read only")
    return findings


def _workflow_specific(
    name: str, triggers: dict[str, object], jobs: dict[str, object]
) -> list[str]:
    """Apply the contract owned by one named workflow, if any.

    Args:
        name (str): Workflow file name that selects the contract.
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the workflow.

    Returns:
        list[str]: Workflow-specific findings; empty for workflows without one.
    """
    if name in DELIVERY_WORKFLOWS:
        return delivery_workflow(name, triggers)
    if name == CI_WORKFLOW:
        return ci_findings(triggers, jobs)
    if name == AUDIT_WORKFLOW:
        return dependency_audit(triggers, jobs)
    if name == REVIEW_WORKFLOW:
        return dependency_review_workflow(triggers, jobs)
    if name == RELEASE_WORKFLOW:
        return release_findings(triggers, jobs)
    return []


def _workflow(root: Path, name: str) -> list[str]:
    """Reject unsafe or unreviewed executable workflow surfaces.

    Args:
        root (Path): Repository root that holds ``.github/workflows``.
        name (str): Workflow file name to check.

    Returns:
        list[str]: Root, job, and workflow-specific findings; empty when it passes.
    """
    raw = load_workflow(root / ".github/workflows" / name)
    if not is_json_object(raw):
        return [f"{name}: workflow must be a mapping"]
    triggers = raw.get("on")
    if not is_json_object(triggers):
        return [f"{name}: explicit trigger mapping is required"]
    findings = _root_findings(name, raw, triggers)
    jobs = raw.get("jobs")
    if not is_json_object(jobs):
        return [*findings, f"{name}: jobs must be explicit"]
    for identifier, job in jobs.items():
        findings.extend(_job_findings(name, identifier, job))
    findings.extend(_workflow_specific(name, triggers, jobs))
    if name == DEPLOY_WORKFLOW:
        findings.extend(deploy_findings(raw))
    return findings


def workflow_findings(root: Path) -> list[str]:
    """Check the reviewed workflow inventory and every reviewed workflow under ``root``."""
    findings: list[str] = []
    workflow_root = root / ".github/workflows"
    actual = (
        {
            path.name
            for path in workflow_root.iterdir()
            if path.suffix in {".yml", ".yaml"}
        }
        if workflow_root.is_dir()
        else set()
    )
    if actual != _WORKFLOWS:
        findings.append(
            "workflow inventory differs from the reviewed verification/release/scanning contract"
        )
    for name in sorted(actual & _WORKFLOWS):
        try:
            findings.extend(_workflow(root, name))
        except (OSError, ValueError, yaml.YAMLError):
            findings.append(f"{name}: invalid workflow or duplicate keys")
    return findings
