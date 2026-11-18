"""Verification, dependency-audit, and dependency-review workflow contracts."""

from __future__ import annotations

from typing import Final

from agent_kit.core.guards import is_json_object
from scripts.checks.governance.actions import PYTHON_CHECK_REFERENCE
from scripts.checks.governance.inputs import (
    child_list,
    child_value,
    job_needs,
    run_commands,
)

CI_WORKFLOW: Final[str] = "toolkit-ci.yml"
AUDIT_WORKFLOW: Final[str] = "security-dependency-audit.yml"
REVIEW_WORKFLOW: Final[str] = "security-dependency-review.yml"
AUDIT_CALL: Final[str] = f"$/.github/workflows/{AUDIT_WORKFLOW}"

_AUDIT_COMMAND = "uv run --no-project python scripts/audit_dependencies.py"
_SYNC_COMMAND = "uv sync --locked"
_REVIEW_SCOPES = {"runtime", "development", "unknown"}


def _ci_audit_consumers(jobs: dict[str, object]) -> list[str]:
    """Keep full-install jobs behind a successful audit with no failure override."""
    findings: list[str] = []
    for identifier in ("verify", "precommit", "smoke"):
        job = jobs.get(identifier)
        needed = job_needs(job)
        if (
            not is_json_object(job)
            or needed is None
            or "audit" not in needed
            or job.get("if") not in (None, "success()")
        ):
            findings.append(
                f"{CI_WORKFLOW}: {identifier} dependencies must be audited before installation; "
                "need audit with success-only execution"
            )
    return findings


def _ci_python_check(jobs: dict[str, object]) -> list[str]:
    """Keep toolkit verification on the reviewed delivery gate without bypasses."""
    calls = [
        step
        for step in child_list(jobs.get("verify"), "steps")
        if is_json_object(step) and step.get("uses") == PYTHON_CHECK_REFERENCE
    ]
    if len(calls) != 1:
        return [f"{CI_WORKFLOW}: verify must invoke the source-bound Python check once"]
    step = calls[0]
    if (
        step.get("if") not in (None, "success()")
        or "continue-on-error" in step
        or child_value(step.get("with"), "task") not in (None, "verify")
    ):
        return [
            f"{CI_WORKFLOW}: the delivery verification gate must not be skipped or replaced"
        ]
    return []


def ci_findings(triggers: dict[str, object], jobs: dict[str, object]) -> list[str]:
    """Require gate triggers, a complete summary, and audit-before-install edges.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of the CI workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the CI workflow.

    Returns:
        list[str]: One message per violated CI rule; empty when the workflow passes.
    """
    findings: list[str] = []
    if not {"pull_request", "merge_group", "workflow_call"}.issubset(triggers):
        findings.append(
            f"{CI_WORKFLOW}: PR, merge queue, and reusable verification triggers are required"
        )
    summary = jobs.get("checks")
    needed = job_needs(summary)
    if (
        not is_json_object(summary)
        or needed is None
        or sorted(str(item) for item in needed) != sorted(set(jobs) - {"checks"})
        or summary.get("if") != "always()"
    ):
        findings.append(
            f"{CI_WORKFLOW}: the required summary must always run and need every other job"
        )
    audit = jobs.get("audit")
    if not is_json_object(audit) or audit.get("uses") != AUDIT_CALL:
        findings.append(f"{CI_WORKFLOW}: the dependency audit must be a required job")
    findings.extend(_ci_audit_consumers(jobs))
    findings.extend(_ci_python_check(jobs))
    return findings


def dependency_audit(triggers: dict[str, object], jobs: dict[str, object]) -> list[str]:
    """Require scheduled, reusable auditing that precedes installing the lock.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the workflow.

    Returns:
        list[str]: Trigger and ordering findings; empty when the workflow passes.
    """
    findings: list[str] = []
    if not {"schedule", "workflow_call"}.issubset(triggers):
        findings.append(
            f"{AUDIT_WORKFLOW}: scheduled and reusable triggers are required"
        )
    commands = run_commands(jobs.get("audit"))
    if (
        _AUDIT_COMMAND not in commands
        or _SYNC_COMMAND not in commands
        or commands.index(_AUDIT_COMMAND) > commands.index(_SYNC_COMMAND)
    ):
        findings.append(
            f"{AUDIT_WORKFLOW}: the lock must be audited before it is installed"
        )
    return findings


def _dependency_review(jobs: dict[str, object]) -> list[str]:
    """Require vulnerability and license review for every dependency scope."""
    job = jobs.get("review")
    options = next(
        (
            step.get("with")
            for step in child_list(job, "steps")
            if is_json_object(step)
            and str(step.get("uses", "")).startswith(
                "actions/dependency-review-action@"
            )
        ),
        None,
    )
    scopes = (
        {scope.strip() for scope in str(options.get("fail-on-scopes", "")).split(",")}
        if is_json_object(options)
        else set()
    )
    if (
        not is_json_object(options)
        or options.get("vulnerability-check") != "true"
        or options.get("license-check") != "true"
        or options.get("fail-on-severity") != "low"
        or not str(options.get("allow-licenses", "")).strip()
        or scopes != _REVIEW_SCOPES
    ):
        return [
            f"{REVIEW_WORKFLOW}: vulnerability and license review must cover every dependency scope"
        ]
    return []


def dependency_review_workflow(
    triggers: dict[str, object], jobs: dict[str, object]
) -> list[str]:
    """Require complete dependency review limited to pull requests.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the workflow.

    Returns:
        list[str]: Review-scope and trigger findings; empty when the workflow passes.
    """
    findings = _dependency_review(jobs)
    if set(triggers) != {"pull_request"}:
        findings.append(
            f"{REVIEW_WORKFLOW}: dependency review is supported only for pull_request events"
        )
    return findings
