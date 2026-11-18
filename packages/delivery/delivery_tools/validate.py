"""Offline source contracts, not a hosted workflow or Azure template compiler."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from delivery_tools.catalog import (
    CAPABILITIES,
    PYTHON_CHECK_ACTION,
    PYTHON_CHECK_REFERENCE,
    ROOT,
    infrastructure_files,
    is_source_file,
    nodes,
    parameters,
    python_action_path,
    render,
    workflow_paths,
)
from delivery_tools.documents import DocumentError, mapping, read_json, read_yaml

if TYPE_CHECKING:
    from pathlib import Path

_STEPS = (
    "azure-deploy",
    "bicep-check",
    "terraform-check",
    "setup-bun",
    "setup-python-uv",
    "setup-terraform",
    "setup-tflint",
)
_PRESETS = ("default", "azure-pipelines", "bicep", "terraform", "tool-pins")
_ACTION = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")
_PARAMETER = re.compile(r"\bparameters\.([A-Za-z]\w*)")
_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)\s]*)?\)")
_LOCKED_PYTHON_COMMANDS = (
    "uv sync --locked",
    'uv run --locked --no-sync task "$TASK_NAME"',
)
_ADO_PYTHON_TASK = "azure-devops/jobs/python-task.yml"
_ADO_LOCKED_PYTHON_COMMANDS = (
    "uv sync --locked",
    'uv run --locked --no-sync task "${TASK_NAME}"',
)
_READ = {"contents": "read"}
_OIDC = {"contents": "read", "id-token": "write"}
_DEPLOY_WORKFLOW = "delivery-azure-deploy.yml"
_TARGET = "${{ inputs.environment }}"
# The only escalations: preflight reads environment protection through the REST API;
# preview and deploy exchange the environment's OIDC token for Azure access.
_JOB_PERMISSIONS = {
    _DEPLOY_WORKFLOW: {
        "preflight": {"contents": "read", "actions": "read"},
        "plan": _OIDC,
        "deploy": _OIDC,
    }
}
# Steps duplicated in preview and deploy must stay identical so deploy applies the preview.
_SHARED_DEPLOY_STEPS = (
    "Check environment configuration",
    "Azure login",
    "Set up Terraform",
    "Initialize Terraform state",
)


def _require(message: str, *, condition: bool) -> None:
    if not condition:
        raise DocumentError(message)


def _inventory(root: Path) -> None:
    expected = {
        PYTHON_CHECK_ACTION,
        *infrastructure_files(root),
        *(f"azure-devops/extends/{name}.yml" for name in CAPABILITIES),
        "azure-devops/jobs/python-task.yml",
        *(f"azure-devops/steps/{name}.yml" for name in _STEPS),
        *(f"renovate/{name}.json" for name in _PRESETS),
    }
    actual = {
        path.relative_to(root).as_posix()
        for directory in (
            "workflows",
            ".github/workflows",
            "actions",
            "infra",
            "azure-devops",
            "renovate",
        )
        for path in (root / directory).rglob("*")
        if is_source_file(path, root)
    }
    # No second authored workflow source, including copies outside the old staging directory.
    actual.update(
        path.relative_to(root).as_posix()
        for path in root.rglob("delivery-*.y*ml")
        if path.is_file()
    )
    _require(
        f"Entry point inventory differs: {sorted(actual ^ expected)}",
        condition=actual == expected,
    )


def _workflow(path: Path) -> None:
    doc = read_yaml(path, workflow=True)
    _require(
        f"{path.name}: call-only",
        condition=set(mapping(doc["on"])) == {"workflow_call"},
    )
    _require(
        "Expected read-only permissions",
        condition=doc.get("permissions") == _READ,
    )
    self_reference = (
        PYTHON_CHECK_REFERENCE if path.name == "delivery-python-ci.yml" else None
    )
    jobs = {name: mapping(job) for name, job in mapping(doc.get("jobs", {})).items()}
    approved = _JOB_PERMISSIONS.get(path.name, {})
    for name, permissions in approved.items():
        _require(
            f"{path.name}: job {name} needs exactly {permissions}",
            condition=name in jobs and jobs[name].get("permissions") == permissions,
        )
    _github_nodes(
        doc,
        self_reference=self_reference,
        granted={id(jobs[name]) for name in approved},
    )
    if self_reference is not None:
        _require(
            "Python workflow must invoke its source-bound check action once",
            condition=sum(node.get("uses") == self_reference for node in nodes(doc))
            == 1,
        )
    if path.name == _DEPLOY_WORKFLOW:
        _deploy_workflow(doc, jobs)


def _steps(job: dict[str, object]) -> dict[str, dict[str, object]]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        message = "Job steps must be a list"
        raise DocumentError(message)
    named = [mapping(step) for step in steps]
    return {str(step["name"]): step for step in named if "name" in step}


def _deploy_workflow(
    doc: dict[str, object], jobs: dict[str, dict[str, object]]
) -> None:
    """Keep preview, protection and apply ordered, gated and identical."""
    call = mapping(mapping(doc["on"])["workflow_call"])
    _require("Deploy workflow must not accept secrets", condition="secrets" not in call)
    _require(
        "Deploy runs must queue per environment and never cancel in-progress runs",
        condition=doc.get("concurrency")
        == {"group": f"delivery-azure-deploy-{_TARGET}"},
    )
    _require(
        "Deploy workflow must run preflight, plan and deploy only",
        condition=set(jobs) == {"preflight", "plan", "deploy"},
    )
    preflight, plan, deploy = jobs["preflight"], jobs["plan"], jobs["deploy"]
    _require(
        "Preflight must verify the environment before any job references it",
        condition="environment" not in preflight
        and "Require a reviewed environment" in _steps(preflight),
    )
    _require(
        "Preview must use the environment without creating a deployment",
        condition=plan.get("environment") == {"name": _TARGET, "deployment": "false"}
        and plan.get("needs") == "preflight",
    )
    _require(
        "Deploy must run in the protected environment after preview",
        condition=deploy.get("environment") == _TARGET
        and deploy.get("needs") == ["preflight", "plan"],
    )
    uploads = [
        mapping(step.get("with", {}))
        for step in nodes(plan.get("steps", []))
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    _require(
        "Preview artifacts can contain sensitive values; keep retention-days: 1",
        condition=len(uploads) == 1 and uploads[0].get("retention-days") == "1",
    )
    previewed, applied = _steps(plan), _steps(deploy)
    for name in _SHARED_DEPLOY_STEPS:
        in_both = name in previewed and name in applied
        _require(
            f"Deploy step differs from its preview: {name}",
            condition=in_both
            and all(
                previewed[name].get(key) == applied[name].get(key)
                for key in ("if", "uses", "with", "run")
            ),
        )


def _github_nodes(
    document: dict[str, object],
    *,
    self_reference: str | None = None,
    granted: set[int] | None = None,
) -> None:
    for node in nodes(document):
        if "permissions" in node and id(node) not in (granted or set()):
            _require(
                "Permission escalation",
                condition=node["permissions"] == _READ,
            )
        if "uses" in node:
            uses = str(node["uses"])
            _require(
                f"Unpinned action: {uses}",
                condition=_ACTION.fullmatch(uses) is not None or uses == self_reference,
            )
            if uses.startswith("actions/checkout@"):
                _require(
                    "Checkout must not persist credentials",
                    condition=mapping(node.get("with", {})).get("persist-credentials")
                    == "false",
                )
        if isinstance(node.get("run"), str):
            _require(
                "Expression interpolated into shell",
                condition="${{" not in str(node["run"]),
            )
        _require(
            "Gates must not ignore failures", condition="continue-on-error" not in node
        )


def _python_action(root: Path) -> None:
    document = read_yaml(python_action_path(root), workflow=True)
    runs = mapping(document["runs"])
    _require(
        "Python check must be composite", condition=runs.get("using") == "composite"
    )
    _github_nodes(document)
    inputs = mapping(document["inputs"])
    _require(
        "Python check must default to the verification gate",
        condition=mapping(inputs["task"]).get("default") == "verify",
    )
    raw_steps = runs["steps"]
    _require("Composite steps must be a list", condition=isinstance(raw_steps, list))
    steps = [node for node in nodes(raw_steps) if "run" in node]
    required = steps[-len(_LOCKED_PYTHON_COMMANDS) :]
    _require(
        "Python check must synchronize the lock before running the locked Task",
        condition=[step["run"] for step in required] == list(_LOCKED_PYTHON_COMMANDS),
    )
    for step in required:
        on_success = step.get("if") in (None, "success()")
        in_directory = (
            step.get("working-directory") == "${{ inputs.working-directory }}"
        )
        _require(
            "Required Python check steps must run on success in the selected directory",
            condition=on_success and step.get("shell") == "bash" and in_directory,
        )
    _require(
        "Task name must come from the declared action input",
        condition=mapping(required[-1].get("env", {})).get("TASK_NAME")
        == "${{ inputs.task }}",
    )


def _ado_python_task(root: Path) -> None:
    """Keep the Azure Pipelines Task gate as locked as the GitHub action."""
    steps = [
        node for node in nodes(read_yaml(root / _ADO_PYTHON_TASK)) if "bash" in node
    ]
    locked = [step for step in steps if step["bash"] in _ADO_LOCKED_PYTHON_COMMANDS]
    _require(
        "Azure Python task must synchronize the lock before running the locked Task",
        condition=[step["bash"] for step in locked]
        == list(_ADO_LOCKED_PYTHON_COMMANDS),
    )
    _require(
        "Azure Python task name must come from the declared template parameter",
        condition=mapping(locked[-1].get("env", {})).get("TASK_NAME")
        == "${{ parameters.task }}",
    )


def _template_reference(root: Path, path: Path, node: dict[str, object]) -> None:
    target = (path.parent / str(node["template"])).resolve()
    _require(
        "Template escapes package",
        condition=target.is_relative_to(root / "azure-devops"),
    )
    _require(f"Missing template: {target.name}", condition=target.is_file())
    contract = parameters(read_yaml(target))
    supplied = mapping(node.get("parameters", {}))
    _require(
        "Unknown template parameters", condition=not (supplied.keys() - contract.keys())
    )
    required = {name for name, item in contract.items() if item["required"]}
    _require(
        "Missing required template parameters", condition=required <= supplied.keys()
    )


def _template(root: Path, path: Path) -> None:
    doc = read_yaml(path)
    contract = parameters(doc)
    refs = set(_PARAMETER.findall(path.read_text(encoding="utf-8")))
    _require(
        f"{path.name}: undeclared parameter reference",
        condition=refs <= contract.keys(),
    )
    for node in nodes(doc):
        if "template" in node:
            _template_reference(root, path, node)
        _template_node(node)


def _template_node(node: dict[str, object]) -> None:
    _require(
        "Expression interpolated into shell",
        condition=all(
            "${{" not in str(node.get(key, "")) for key in ("bash", "inlineScript")
        ),
    )
    if "deployment" in node:
        _require(
            "Deployment jobs must target an environment",
            condition=bool(node.get("environment")),
        )
    if "checkout" in node:
        _require(
            "Checkout persists credentials",
            condition=node.get("persistCredentials") is False,
        )
    _require("Gates must not ignore failures", condition="continueOnError" not in node)


def _renovate(root: Path) -> None:
    for path in (root / "renovate").glob("*.json"):
        for node in nodes(read_json(path)):
            _require(
                "Unexpected automerge", condition=node.get("automerge") is not True
            )
    default = read_json(root / "renovate/default.json")
    _require(
        "Release-age gate changed",
        condition=default.get("minimumReleaseAge") == "7 days",
    )
    _require(
        "Release-age gate is not strict",
        condition=default.get("internalChecksFilter") == "strict",
    )
    _require(
        "Major updates require dashboard approval",
        condition=any(
            rule.get("matchUpdateTypes") == ["major"]
            and rule.get("dependencyDashboardApproval") is True
            for rule in nodes(default.get("packageRules"))
        ),
    )


def _links(root: Path) -> None:
    for document in root.rglob("*.md"):
        for link in _LINK.findall(document.read_text(encoding="utf-8")):
            if "://" in link:
                continue
            target = (document.parent / link).resolve()
            _require(
                f"{document.name}: broken or external local link: {link}",
                condition=target.is_relative_to(root) and target.exists(),
            )


def validate(root: Path = ROOT, *, workflow_root: Path) -> None:
    """Fail closed on missing sources, unsafe contracts, broken links or catalog drift."""
    root = root.resolve()
    _inventory(root)
    _python_action(root)
    _ado_python_task(root)
    for path in workflow_paths(workflow_root):
        _workflow(path)
    for path in (root / "azure-devops").rglob("*.yml"):
        _template(root, path)
    _renovate(root)
    _links(root)
    _require(
        "catalog.json is stale; rerun check.py with --write-catalog and --workflow-root",
        condition=(root / "catalog.json").read_text(encoding="utf-8")
        == render(root, workflow_root=workflow_root),
    )
