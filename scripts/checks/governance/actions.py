"""Pinned, credential-free workflow steps and the source-bound Python check."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import yaml

from agent_kit.core.guards import is_json_object
from scripts.checks.governance.delivery import DEPLOY_ARTIFACT, DEPLOY_ARTIFACT_PATH
from scripts.checks.governance.inputs import child_list, child_value, load_workflow

if TYPE_CHECKING:
    from pathlib import Path

_ACTION = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}\Z")
_PYTHON_CHECK_ACTION = "packages/delivery/actions/python-check/action.yml"
PYTHON_CHECK_REFERENCE: Final[str] = "$/packages/delivery/actions/python-check"
_PYTHON_CHECK_CALLERS = {"toolkit-ci.yml", "delivery-python-ci.yml"}
_UPLOADS = {
    ("release-artifacts", "build/release/*", "error"),
    ("coverage-report", "build/coverage/coverage.xml", "error"),
    (DEPLOY_ARTIFACT, DEPLOY_ARTIFACT_PATH, "error"),
}
_DOWNLOADS = {
    ("release-artifacts", "artifacts"),
    ("coverage-report", "build/coverage"),
    (DEPLOY_ARTIFACT, DEPLOY_ARTIFACT_PATH),
}


def _checkout_reviewed(options: object) -> bool:
    """Return whether checkout disables persistent credentials."""
    return is_json_object(options) and options.get("persist-credentials") == "false"


def _upload_reviewed(options: object) -> bool:
    """Return whether an artifact upload uses a reviewed name and path."""
    return (
        is_json_object(options)
        and (
            options.get("name"),
            options.get("path"),
            options.get("if-no-files-found"),
        )
        in _UPLOADS
    )


def _download_reviewed(options: object) -> bool:
    """Return whether an artifact download matches a reviewed upload."""
    return (
        is_json_object(options)
        and (options.get("name"), options.get("path")) in _DOWNLOADS
    )


def _codecov_reviewed(options: object) -> bool:
    """Return whether Codecov pins its CLI, keeps validation, and uses OIDC."""
    return (
        is_json_object(options)
        and str(options.get("version", "")).startswith("v")
        and options.get("skip_validation") in {None, "false"}
        and "token" not in options
    )


_ACTION_OPTION_RULES = (
    (
        "actions/checkout@",
        _checkout_reviewed,
        "checkout must disable persistent credentials",
    ),
    (
        "actions/upload-artifact@",
        _upload_reviewed,
        "artifact upload must use a reviewed name and path",
    ),
    (
        "actions/download-artifact@",
        _download_reviewed,
        "artifact download must match a reviewed upload",
    ),
    (
        "codecov/codecov-action@",
        _codecov_reviewed,
        "Codecov must pin its CLI, keep validation, and use OIDC",
    ),
)


def step_findings(name: str, step: object) -> list[str]:
    """Reject mutable actions, interpolated scripts, and unreviewed options.

    Args:
        name (str): Workflow file name used to prefix each finding.
        step (object): Decoded workflow step.

    Returns:
        list[str]: One message per violated step rule; empty when the step passes.
    """
    if not is_json_object(step):
        return [f"{name}: malformed workflow step"]
    findings: list[str] = []
    action = step.get("uses")
    source_bound = name in _PYTHON_CHECK_CALLERS and action == PYTHON_CHECK_REFERENCE
    if (
        action is not None
        and not source_bound
        and (not isinstance(action, str) or not _ACTION.fullmatch(action))
    ):
        findings.append(f"{name}: actions must use an immutable full commit SHA")
    command = step.get("run")
    if isinstance(command, str) and "${{" in command:
        findings.append(
            f"{name}: expressions belong in env, not interpolated run scripts"
        )
    if isinstance(action, str):
        findings.extend(
            f"{name}: {message}"
            for prefix, reviewed, message in _ACTION_OPTION_RULES
            if action.startswith(prefix) and not reviewed(step.get("with"))
        )
    return findings


def python_action_findings(root: Path) -> list[str]:
    """Inspect the actual source-bound composite, not only its caller reference."""
    try:
        document = load_workflow(root / _PYTHON_CHECK_ACTION)
    except (OSError, ValueError, yaml.YAMLError):
        return ["Python check action: missing, invalid, or duplicate keys"]
    runs = child_value(document, "runs")
    if child_value(runs, "using") != "composite" or not isinstance(
        child_value(runs, "steps"), list
    ):
        return ["Python check action: a composite step list is required"]
    return [
        finding
        for step in child_list(runs, "steps")
        for finding in step_findings(_PYTHON_CHECK_ACTION, step)
    ]
