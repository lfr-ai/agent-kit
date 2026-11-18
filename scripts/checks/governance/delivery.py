"""Reusable delivery checks and the reviewed Azure deployment workflow."""

from __future__ import annotations

import json
import re
from typing import Final

from agent_kit.core.guards import is_json_object
from scripts.checks.governance.inputs import child_list, child_value, job_needs

DEPLOY_WORKFLOW: Final[str] = "delivery-azure-deploy.yml"
DELIVERY_WORKFLOWS: Final[frozenset[str]] = frozenset(
    {
        "delivery-python-ci.yml",
        "delivery-bun-ci.yml",
        "delivery-bicep-check.yml",
        "delivery-terraform-check.yml",
        DEPLOY_WORKFLOW,
    }
)
# The deploy preview hands its compiled template or saved plan to its own apply job.
DEPLOY_ARTIFACT: Final[str] = "${{ needs.preflight.outputs.artifact }}"
DEPLOY_ARTIFACT_PATH: Final[str] = "${{ runner.temp }}/delivery-azure-deploy"
_DEPLOY_TARGET = "${{ inputs.environment }}"
_DEPLOY_CONCURRENCY = {"group": f"delivery-azure-deploy-{_DEPLOY_TARGET}"}
_DEPLOY_JOBS = ("preflight", "plan", "deploy")
_REVIEWER_CHECK = "Require a reviewed environment"
_SECRET_EXPRESSION = re.compile(r"\$\{\{[^}]*\bsecrets\.")
_AZURE_OIDC_LOGIN = {
    "client-id": "${{ vars.AZURE_CLIENT_ID }}",
    "tenant-id": "${{ vars.AZURE_TENANT_ID }}",
    "subscription-id": "${{ vars.AZURE_SUBSCRIPTION_ID }}",
}


def delivery_workflow(name: str, triggers: dict[str, object]) -> list[str]:
    """Keep reusable delivery checks unprivileged and caller-triggered.

    Args:
        name (str): Delivery workflow file name used to prefix each finding.
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.

    Returns:
        list[str]: Trigger and secret findings; empty when the workflow passes.
    """
    findings: list[str] = []
    if set(triggers) != {"workflow_call"}:
        findings.append(f"{name}: delivery checks require only workflow_call")
    call = triggers.get("workflow_call")
    if is_json_object(call) and "secrets" in call:
        findings.append(f"{name}: delivery checks must not declare secrets")
    return findings


def deploy_findings(raw: dict[str, object]) -> list[str]:
    """Return findings unless the deploy is secretless, queued and preview-gated."""
    text = json.dumps(raw)
    findings: list[str] = []
    if _SECRET_EXPRESSION.search(text) or '"continue-on-error"' in text:
        findings.append(
            f"{DEPLOY_WORKFLOW}: Azure access is OIDC-only and no failure is ignored"
        )
    if raw.get("concurrency") != _DEPLOY_CONCURRENCY:
        findings.append(
            f"{DEPLOY_WORKFLOW}: runs must queue per environment without cancelling"
        )
    jobs = raw.get("jobs")
    if not is_json_object(jobs) or set(jobs) != set(_DEPLOY_JOBS):
        return [*findings, f"{DEPLOY_WORKFLOW}: only preflight, plan and deploy run"]
    findings.extend(_deploy_order_findings(jobs))
    findings.extend(_deploy_identity_findings(jobs))
    return findings


def _deploy_order_findings(jobs: dict[str, object]) -> list[str]:
    """Return findings unless reviewers are verified, then previewed, then applied."""
    preflight, plan, deploy = (jobs[name] for name in _DEPLOY_JOBS)
    reviewer_checks = [
        step
        for step in child_list(preflight, "steps")
        if child_value(step, "name") == _REVIEWER_CHECK
        and child_value(step, "if") is None
    ]
    findings: list[str] = []
    if child_value(preflight, "environment") is not None or len(reviewer_checks) != 1:
        findings.append(
            f"{DEPLOY_WORKFLOW}: preflight must verify reviewers before any job "
            "uses the environment"
        )
    if child_value(plan, "environment") != {
        "name": _DEPLOY_TARGET,
        "deployment": "false",
    } or job_needs(plan) != ["preflight"]:
        findings.append(
            f"{DEPLOY_WORKFLOW}: the preview must follow preflight in the "
            "environment without a deployment record"
        )
    if child_value(deploy, "environment") != _DEPLOY_TARGET or job_needs(deploy) != [
        "preflight",
        "plan",
    ]:
        findings.append(
            f"{DEPLOY_WORKFLOW}: apply must follow the preview in the environment"
        )
    return findings


def _deploy_identity_findings(jobs: dict[str, object]) -> list[str]:
    """Return findings unless Azure uses OIDC and the plan artifact lives one day."""
    steps = {
        job: [step for step in child_list(jobs[job], "steps") if is_json_object(step)]
        for job in ("plan", "deploy")
    }
    logins = [
        step.get("with")
        for job in steps.values()
        for step in job
        if str(step.get("uses", "")).startswith("azure/login@")
    ]
    uploads = [
        step.get("with")
        for job in steps.values()
        for step in job
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    findings: list[str] = []
    if (
        not logins
        or any(options != _AZURE_OIDC_LOGIN for options in logins)
        or any(
            child_value(child_value(jobs[job], "env"), "ARM_USE_OIDC") != "true"
            for job in steps
        )
    ):
        findings.append(
            f"{DEPLOY_WORKFLOW}: Azure login must use environment OIDC variables only"
        )
    if len(uploads) != 1 or child_value(uploads[0], "retention-days") != "1":
        findings.append(
            f"{DEPLOY_WORKFLOW}: keep one preview artifact with retention-days: 1"
        )
    return findings
