"""Plan an operator-reviewed Azure identity; only ``--apply`` invokes Azure CLI.

``--emit`` additionally prints, and never runs, CI-host setup commands for review.
This stays one standalone file: the Taskfile and tests load it by path, and a
sibling module would need ``sys.path`` changes that break relocation.
"""

# ruff: noqa: INP001 - standalone, relocatable operator script, not a package

import argparse
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum, auto, unique
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Final
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

_READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
_CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"
_RBAC_ADMIN = "f58310d9-a9f6-439a-9e8d-f62e7b41a168"
_CONDITION_VERSION = "2.0"
# Single source of truth for the data-plane roles the delivery infra templates
# assign; the deploy identity may assign or delete only these, and only for
# service principals. Compared against the templates by a parent test.
DELEGABLE_ROLES: Final[tuple[str, ...]] = (
    "1407120a-92aa-4202-b7e9-c0e197c71c8f",  # Search Index Data Reader
    "3913510d-42f4-4e42-8a64-420c390055eb",  # Monitoring Metrics Publisher
    "4633458b-17de-408a-b874-0445c86b69e6",  # Key Vault Secrets User
    "53ca6127-db72-4b80-b1b0-d745d6d5456d",  # Foundry User (formerly Azure AI User)
    "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",  # Cognitive Services OpenAI User
    "7f951dda-4ed3-4680-a7ca-43fe172d538d",  # AcrPull
    "8311e382-0749-4cb8-b61a-304f252e45ec",  # AcrPush
    "8ebe5a00-799e-43f5-93ac-243d3dce84a7",  # Search Index Data Contributor
    "a97b65f3-24c7-4388-baec-2e87135dc908",  # Cognitive Services User
    "ba92f5b4-2d11-453d-a403-e96b0029c9fe",  # Storage Blob Data Contributor
)
_TAG = "agent-kit-bootstrap"
_TIMEOUT_SECONDS = 120
_JSON_INDENT = 2
_MIN_UUID_DIVERSITY = 4
_NAME = r"[a-z][a-z0-9-]{1,62}"
_UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
_SYNTHETIC = r"(^|[-_/:])(example|placeholder|changeme|contoso|fabrikam|your|dummy|sample)($|[-_/:])"
_GITHUB_SUBJECT = (
    r"repo:[A-Za-z0-9_.@-]+/[A-Za-z0-9_.@-]+:"
    r"(environment:[A-Za-z0-9_.:/@-]+|ref:refs/(heads|tags)/[A-Za-z0-9_./@-]+)"
)
_ADO_LEGACY_SUBJECT = r"sc://[A-Za-z0-9_. -]+/[A-Za-z0-9_. -]+/[A-Za-z0-9_. -]+"
_ADO_SUBJECT = rf"(/eid1/[A-Za-z0-9_/-]+|{_ADO_LEGACY_SUBJECT})"
_GITHUB_ENVIRONMENT = r"repo:([A-Za-z0-9_.@-]+/[A-Za-z0-9_.@-]+):environment:(.+)"
# Microsoft Entra allows at most 20 federated credentials per identity.
_MAX_SUBJECTS = 20
# Single-subject runs keep the original credential name; it stays accepted later.
_LEGACY_CREDENTIAL = "ci"
_CREDENTIAL_HASH_LENGTH = 12
_BRANCH = r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}"
_ADO_ORGANIZATION = r"https://dev\.azure\.com/[A-Za-z0-9][A-Za-z0-9-]{0,49}"
_ADO_LABEL = r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}"
_CLIENT_PLACEHOLDER = "CLIENT_ID_FROM_IDENTITY"
_PROJECT_PLACEHOLDER = "PROJECT_ID_FROM_ADO"
_ENVIRONMENT_PLACEHOLDER = "ENVIRONMENT_ID_FROM_CREATE"
_REPOSITORY_PLACEHOLDER = "REPOSITORY_ID_FROM_ADO"
# Azure Pipelines "Branch control" check: a Task Check running evaluatebranchProtection.
_TASK_CHECK = "fe1de3ee-a436-41b4-bb20-f6eb4cb879a7"
_BRANCH_PROTECTION = "86b05a0c-73e6-4f7d-b3cf-e38f3b39a75b"
_CHECK_TIMEOUT_MINUTES = 1440
_EMIT_NOTE = (
    "Printed for review only; nothing was executed. Verify each command against the "
    "current CLI/REST reference and run it as an authorized operator."
)
# --emit choices: CI host whose setup commands are printed, never executed.
_EMIT_GITHUB = "github"
_EMIT_ADO = "azure-devops"
_EMIT_HOSTS = {_EMIT_GITHUB: "github", _EMIT_ADO: "ado"}
_OWNED_STEP = "State backend, CI protections, Teams destination and OAuth consent remain operator-owned."
_READ_STEPS = (
    "Reader cannot deploy workloads or grant roles; arrange narrower workload permissions separately.",
    _OWNED_STEP,
)
_DEPLOY_STEPS = (
    (
        "Contributor deploys in this group only; the constrained RBAC administrator can "
        "assign/delete only DELEGABLE_ROLES for service principals in this group."
    ),
    (
        "Terraform state also needs the terraform-state module's container-scope "
        "Storage Blob Data Contributor assignment."
    ),
    (
        "Staging and prod deploys create CanNotDelete locks, which neither role can "
        "write. Before the first prod-like deploy, an operator assigns the identity, "
        "at this resource group, a custom role with Actions "
        "Microsoft.Authorization/locks/read and Microsoft.Authorization/locks/write "
        "only: no delete, so CI cannot remove protection and a Terraform destroy or "
        "replace of a lock needs an operator. This script never creates it, and a "
        "later --apply stops on that extra grant; see docs/bootstrap.md."
    ),
    _OWNED_STEP,
)
type Record = dict[str, object]
type Execute = Callable[[tuple[str, ...]], str]


def _constrained_delegation(roles: tuple[str, ...]) -> str:
    """Return Microsoft's documented "Constrain roles and principal types" condition."""
    guids = ", ".join(sorted(roles))
    return " AND ".join(
        f"((!(ActionMatches{{'Microsoft.Authorization/roleAssignments/{action}'}})) OR "
        f"(@{source}[Microsoft.Authorization/roleAssignments:RoleDefinitionId] "
        f"ForAnyOfAnyValues:GuidEquals {{{guids}}} AND "
        f"@{source}[Microsoft.Authorization/roleAssignments:PrincipalType] "
        "ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
        for action, source in (("write", "Request"), ("delete", "Resource"))
    )


_DELEGATION_CONDITION = _constrained_delegation(DELEGABLE_ROLES)


@unique
class Access(StrEnum):
    """Select the RG-scoped authorization granted to the CI identity.

    Attributes:
        READ: Reader only; cannot deploy or grant roles.
        DEPLOY: Contributor plus constrained RBAC administration.
    """

    READ = auto()
    DEPLOY = auto()


@dataclass(frozen=True, slots=True, kw_only=True)
class Trust:
    """Describe one bootstrap-owned federated credential.

    Attributes:
        name: Deterministic credential name created for this subject.
        subject: Exact reviewed subject.
    """

    name: str
    subject: str

    @property
    def accepted_names(self) -> frozenset[str]:
        """Names an existing credential for this subject may already carry."""
        return frozenset({self.name, _LEGACY_CREDENTIAL, _hashed_name(self.subject)})


def _hashed_name(subject: str) -> str:
    """Return the stable per-subject credential name used for multi-subject runs."""
    digest = uuid5(NAMESPACE_URL, subject).hex[:_CREDENTIAL_HASH_LENGTH]
    return f"{_LEGACY_CREDENTIAL}-{digest}"


@dataclass(frozen=True, slots=True, kw_only=True)
class AdoTarget:
    """Hold the nonsecret Azure DevOps names used only by ``--emit azure-devops``.

    Attributes:
        organization: ``https://dev.azure.com/<organization>`` URL.
        project: Project name.
        environment: Pipeline environment to create and protect.
        service_connection: Service connection name to create.
    """

    organization: str
    project: str
    environment: str
    service_connection: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Grant:
    """Describe one expected RG-scoped role assignment.

    Attributes:
        role: Built-in role display name, for review only.
        role_id: Pinned role definition ARM ID at the selected subscription.
        name: Deterministic assignment UUID.
        condition: ABAC condition (version 2.0) or ``None`` for unconditional.
    """

    role: str
    role_id: str
    name: str
    condition: str | None

    @property
    def condition_version(self) -> str | None:
        """ABAC condition version, present only with a condition."""
        return None if self.condition is None else _CONDITION_VERSION


class BootstrapError(RuntimeError):
    """Report a refused or failed operation without echoing external output."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Options:
    """Hold explicit, validated, nonsecret operator choices.

    Attributes:
        tenant_id: Expected Entra tenant UUID.
        subscription_id: Selected subscription UUID, never a global default.
        resource_group: Dedicated project resource group name.
        location: Azure public-cloud region name.
        identity_name: Dedicated user-assigned managed identity name.
        ci_host: Reviewed GitHub or Azure DevOps trust source.
        issuer: Exact issuer copied from the CI host.
        subjects: Exact subjects copied from the CI host, one credential each.
        audience: Explicit Azure token-exchange audience.
        apply: Whether native mutations were explicitly requested.
        access: Authorization level granted to the identity at RG scope.
        emit: CI host whose setup commands are printed, or ``None``.
        deploy_branch: Branch allowed to deploy in printed CI-host commands.
        ado: Azure DevOps names for ``--emit azure-devops``, otherwise ``None``.
    """

    tenant_id: str
    subscription_id: str
    resource_group: str
    location: str
    identity_name: str
    ci_host: str
    issuer: str
    subjects: tuple[str, ...]
    audience: str
    apply: bool
    access: Access
    emit: str | None = None
    deploy_branch: str = "main"
    ado: AdoTarget | None = None

    @property
    def scope(self) -> str:
        """Selected resource group ARM ID."""
        return f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"

    @property
    def identity_id(self) -> str:
        """Selected managed identity ARM ID."""
        return f"{self.scope}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{self.identity_name}"

    @property
    def trusts(self) -> tuple[Trust, ...]:
        """One credential per subject; a single subject keeps the original ``ci`` name."""
        if len(self.subjects) == 1:
            return (Trust(name=_LEGACY_CREDENTIAL, subject=self.subjects[0]),)
        return tuple(
            Trust(name=_hashed_name(subject), subject=subject)
            for subject in self.subjects
        )

    def credential_id(self, name: str) -> str:
        """Return the ARM ID of federated credential ``name`` on the identity."""
        return f"{self.identity_id}/federatedIdentityCredentials/{name}"

    def grant(self, role: str, guid: str, condition: str | None = None) -> Grant:
        """Build one pinned assignment with a stable per-identity/role UUID.

        Args:
            role: Built-in role display name.
            guid: Pinned built-in role definition GUID.
            condition: Optional ABAC condition (version 2.0).
        """
        role_id = f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/{guid}"
        name = str(uuid5(NAMESPACE_URL, f"{self.identity_id}|{role_id}"))
        return Grant(role=role, role_id=role_id, name=name, condition=condition)

    @property
    def grants(self) -> tuple[Grant, ...]:
        """Exact RG-scoped assignments expected for the selected access level."""
        if self.access is Access.READ:
            return (self.grant("Reader", _READER),)
        return (
            self.grant("Contributor", _CONTRIBUTOR),
            self.grant(
                "Role Based Access Control Administrator",
                _RBAC_ADMIN,
                _DELEGATION_CONDITION,
            ),
        )

    @property
    def steps(self) -> tuple[str, ...]:
        """Operator follow-ups for the selected access level."""
        return _READ_STEPS if self.access is Access.READ else _DEPLOY_STEPS

    @property
    def tags(self) -> dict[str, str]:
        """Ownership marker, not an authorization or adoption mechanism."""
        return {_TAG: str(uuid5(NAMESPACE_URL, f"{self.tenant_id}|{self.identity_id}"))}


def _require(*, condition: bool, message: str) -> None:
    """Enforce one safety invariant.

    Args:
        condition: Whether the invariant holds.
        message: Safe diagnostic, without untrusted response data.

    Raises:
        BootstrapError: The invariant failed.
    """
    if not condition:
        raise BootstrapError(message)


def _matches(pattern: str, value: str, label: str) -> None:
    """Require a restricted input syntax.

    Args:
        pattern: Complete accepted syntax.
        value: Operator input.
        label: Nonsecret field label for diagnostics.
    """
    _require(
        condition=re.fullmatch(pattern, value) is not None, message=f"Invalid {label}."
    )


def _uuid(value: object) -> str:
    """Return a canonical UUID string or raise ``BootstrapError``."""
    _require(condition=isinstance(value, str), message="Expected a UUID string.")
    text = str(value).lower()
    _matches(_UUID, text, "UUID")
    return str(UUID(text))


def _require_one_environment(subjects: tuple[str, ...]) -> None:
    """Require deploy subjects naming one GitHub environment, else ``BootstrapError``.

    Branch, tag and pull-request subjects mint tokens without the environment's
    reviewers or branch policy, and one identity spanning several environments
    lets a dev deployment write production. GitHub compares owner, repository
    and environment names case-insensitively, so case variants are one target.
    """
    _require(
        condition=all(
            re.fullmatch(_GITHUB_ENVIRONMENT, subject) is not None
            for subject in subjects
        ),
        message=(
            "--access deploy trusts only GitHub environment subjects "
            "(repo:<owner>/<repo>:environment:<name>); branch, tag and "
            "pull-request subjects bypass environment protection rules."
        ),
    )
    # Only owner, repository and environment vary, so case-folding the subject
    # case-folds exactly those names.
    _require(
        condition=len({subject.lower() for subject in subjects}) == 1,
        message=(
            "--access deploy trusts one GitHub environment; "
            "bootstrap one deploy identity per environment."
        ),
    )


def _validate_trust(options: Options) -> None:
    """Reject unsupported trust shapes with ``BootstrapError``."""
    _require(
        condition=options.audience == "api://AzureADTokenExchange",
        message="Only the Azure public-cloud token-exchange audience is supported.",
    )
    if options.ci_host == "github":
        _require(
            condition=options.issuer == "https://token.actions.githubusercontent.com",
            message="GitHub requires the public GitHub Actions issuer.",
        )
        if options.access is Access.DEPLOY:
            _require_one_environment(options.subjects)
        for subject in options.subjects:
            _matches(_GITHUB_SUBJECT, subject, "GitHub subject")
        return
    entra = f"https://login.microsoftonline.com/{options.tenant_id}/v2.0"
    legacy = re.fullmatch(rf"https://vstoken.dev.azure.com/{_UUID}", options.issuer)
    _require(
        condition=options.issuer == entra or legacy is not None,
        message="ADO requires its generated public-cloud issuer; Entra tenant must match.",
    )
    pattern = _ADO_SUBJECT if options.issuer == entra else _ADO_LEGACY_SUBJECT
    for subject in options.subjects:
        _matches(pattern, subject, "ADO subject")


def _validate_subjects(options: Options) -> None:
    """Require 1-20 distinct subjects; Entra caps credentials per identity."""
    _require(
        condition=0 < len(options.subjects) <= _MAX_SUBJECTS,
        message=f"Pass 1-{_MAX_SUBJECTS} --subject values.",
    )
    _require(
        condition=len(set(options.subjects)) == len(options.subjects),
        message="Duplicate --subject values.",
    )


def _validate_emit(options: Options) -> None:
    """Require emit inputs that match the reviewed CI host."""
    _matches(_BRANCH, options.deploy_branch, "deploy branch")
    _require(
        condition=".." not in options.deploy_branch
        and not options.deploy_branch.endswith(("/", ".lock")),
        message="Invalid deploy branch.",
    )
    if options.emit is None:
        _require(
            condition=options.ado is None,
            message="Azure DevOps names require --emit azure-devops.",
        )
        return
    _require(
        condition=_EMIT_HOSTS.get(options.emit) == options.ci_host,
        message="--emit must match --ci-host.",
    )
    if options.emit == _EMIT_GITHUB:
        _require(
            condition=options.ado is None,
            message="Azure DevOps names require --emit azure-devops.",
        )
        return
    ado = options.ado
    _require(
        condition=ado is not None,
        message="--emit azure-devops needs --ado-organization, --ado-project "
        "and --ado-environment.",
    )
    if ado is not None:
        _matches(_ADO_ORGANIZATION, ado.organization, "Azure DevOps organization URL")
        for value, label in (
            (ado.project, "Azure DevOps project"),
            (ado.environment, "Azure DevOps environment"),
            (ado.service_connection, "Azure DevOps service connection"),
        ):
            _matches(_ADO_LABEL, value, label)


def _validate_apply_targets(options: Options) -> None:
    """Reject recognizable example targets with ``BootstrapError``."""
    identifiers = [options.tenant_id, options.subscription_id]
    if options.issuer.startswith("https://vstoken.dev.azure.com/"):
        identifiers.append(options.issuer.rsplit("/", 1)[-1])
    for value in identifiers:
        compact = value.replace("-", "")
        synthetic = len(set(compact)) < _MIN_UUID_DIVERSITY or value.startswith(
            ("00000000", "12345678", "aaaaaaaa")
        )
        _require(
            condition=not synthetic, message="Apply refuses synthetic UUID targets."
        )
    for value in (
        options.resource_group,
        options.location,
        options.identity_name,
        *options.subjects,
    ):
        _require(
            condition=re.search(_SYNTHETIC, value, re.IGNORECASE) is None,
            message="Apply refuses example or placeholder targets.",
        )


def _ado_target(args: argparse.Namespace) -> AdoTarget | None:
    """Collect Azure DevOps names, or ``None`` when none were supplied."""
    values = (args.ado_organization, args.ado_project, args.ado_environment)
    if all(value is None for value in (*values, args.ado_service_connection)):
        return None
    if any(value is None for value in values):
        message = (
            "--emit azure-devops needs --ado-organization, --ado-project "
            "and --ado-environment."
        )
        raise BootstrapError(message)
    return AdoTarget(
        organization=args.ado_organization,
        project=args.ado_project,
        environment=args.ado_environment,
        service_connection=args.ado_service_connection or args.identity_name,
    )


def _parser() -> argparse.ArgumentParser:
    """Declare the explicit operator inputs; nothing is inferred."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
        "tenant-id",
        "subscription-id",
        "resource-group",
        "location",
        "identity-name",
        "issuer",
        "audience",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument(
        "--subject",
        required=True,
        action="append",
        help=(
            "Exact subject, one credential each (max 20); GitHub --access deploy "
            "takes environment subjects for one environment only."
        ),
    )
    parser.add_argument("--ci-host", required=True, choices=("github", "ado"))
    parser.add_argument(
        "--oidc-reviewed",
        required=True,
        action="store_true",
        help="Attest that these exact claims were verified with the CI host.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--access",
        choices=tuple(Access),
        default=Access.READ.value,
        help="RG-scoped grant: read (Reader) or deploy (Contributor + constrained RBAC admin).",
    )
    parser.add_argument(
        "--emit",
        choices=tuple(_EMIT_HOSTS),
        help="Also print, never run, CI-host setup commands for review.",
    )
    parser.add_argument(
        "--deploy-branch",
        default="main",
        help="Branch allowed to deploy in printed commands (default main).",
    )
    for name in ("organization", "project", "environment", "service-connection"):
        parser.add_argument(f"--ado-{name}", help="Only with --emit azure-devops.")
    return parser


def parse_options(argv: list[str] | None) -> Options:
    """Parse explicit inputs, raising ``SystemExit`` for invalid operator choices."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        options = Options(
            tenant_id=_uuid(args.tenant_id),
            subscription_id=_uuid(args.subscription_id),
            resource_group=args.resource_group,
            location=args.location,
            identity_name=args.identity_name,
            ci_host=args.ci_host,
            issuer=args.issuer,
            subjects=tuple(args.subject),
            audience=args.audience,
            apply=args.apply,
            access=Access(args.access),
            emit=args.emit,
            deploy_branch=args.deploy_branch,
            ado=_ado_target(args),
        )
        _matches(_NAME, options.resource_group, "resource group")
        _matches(_NAME, options.identity_name, "identity name")
        _matches(r"[a-z][a-z0-9]{1,31}", options.location, "location")
        _validate_subjects(options)
        _validate_trust(options)
        _validate_emit(options)
        if options.apply:
            _validate_apply_targets(options)
    except BootstrapError as error:
        parser.error(str(error))
    return options


def _execute(command: tuple[str, ...]) -> str:
    """Run native Azure CLI without a shell or raise redacted ``BootstrapError``."""
    executable = shutil.which("az")
    _require(
        condition=executable is not None,
        message="Azure CLI is missing; install it separately.",
    )
    env = {
        **os.environ,
        "AZURE_EXTENSION_USE_DYNAMIC_INSTALL": "no",
        "AZURE_CORE_COLLECT_TELEMETRY": "no",
    }
    try:
        result = subprocess.run(  # noqa: S603 - fixed CLI, validated argv, no shell
            (str(executable), *command[1:]),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            timeout=_TIMEOUT_SECONDS,
            env=env,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError) as error:
        message = "Azure CLI could not complete; inspect the target before retrying."
        raise BootstrapError(message) from error
    _require(
        condition=result.returncode == 0,
        message=f"Azure {command[1]} operation failed; exit {result.returncode}. "
        "Check operator permissions/session separately; CLI output withheld.",
    )
    return result.stdout


def _record(value: object) -> Record:
    """Return a JSON object or raise ``BootstrapError`` without echoing it."""
    if not isinstance(value, dict):
        message = "Azure returned a malformed object."
        raise BootstrapError(message)
    _require(
        condition=all(isinstance(key, str) for key in value),
        message="Invalid JSON keys.",
    )
    return {str(key): item for key, item in value.items()}


def _records(value: object) -> list[Record]:
    """Return JSON objects or raise ``BootstrapError`` without echoing them."""
    if not isinstance(value, list):
        message = "Azure returned a malformed list."
        raise BootstrapError(message)
    return [_record(item) for item in value]


def _command(options: Options, args: tuple[str, ...]) -> tuple[str, ...]:
    """Build native arguments with explicit subscription on scoped operations.

    Args:
        options: Validated target.
        args: Fixed operation and validated arguments.
    """
    subscription = (
        ()
        if args == ("cloud", "show")
        else (
            "--subscription",
            options.subscription_id,
        )
    )
    return ("az", *args, *subscription, "--only-show-errors", "--output", "json")


@dataclass(frozen=True, slots=True, kw_only=True)
class Azure:
    """Adapt native JSON responses to the bounded bootstrap.

    Attributes:
        options: Explicit target choices.
        execute: Injected process boundary; tests supply only fake responses.
    """

    options: Options
    execute: Execute

    def read(self, args: tuple[str, ...]) -> object:
        """Return parsed CLI output or raise ``BootstrapError`` on invalid JSON."""
        output = self.execute(_command(self.options, args))
        try:
            value: object = json.loads(output)
        except json.JSONDecodeError as error:
            message = "Azure returned invalid JSON; output withheld."
            raise BootstrapError(message) from error
        return value


def _equal(actual: Record, expected: Record, label: str) -> None:
    """Require exact reviewed fields without printing external data.

    Args:
        actual: Azure response.
        expected: Fields defining the owned resource.
        label: Safe operation label.
    """
    _require(
        condition=all(actual.get(key) == value for key, value in expected.items()),
        message=f"{label} mismatch or ownership conflict; refusing to overwrite.",
    )


def _verify_account(azure: Azure) -> None:
    """Verify selected subscription, tenant, account state and active cloud."""
    options = azure.options
    _equal(
        _record(azure.read(("account", "show"))),
        {
            "id": options.subscription_id,
            "tenantId": options.tenant_id,
            "environmentName": "AzureCloud",
            "state": "Enabled",
        },
        "account",
    )
    cloud = _record(azure.read(("cloud", "show")))
    _equal(cloud, {"name": "AzureCloud"}, "cloud")
    _equal(
        _record(cloud.get("endpoints")),
        {
            "resourceManager": "https://management.azure.com/",
            "activeDirectory": "https://login.microsoftonline.com",
        },
        "cloud endpoints",
    )


def _owned(resource: Record, options: Options, resource_id: str) -> None:
    """Validate ownership without adopting or retagging existing resources.

    Args:
        resource: Inspected or created Azure resource.
        options: Validated target and ownership marker.
        resource_id: Expected ARM ID.
    """
    _equal(resource, {"id": resource_id, "location": options.location}, "resource")
    _equal(_record(resource.get("tags")), dict(options.tags), "resource tags")


def _group(resource: Record, options: Options) -> None:
    """Require an owned resource group in a completed provisioning state.

    Args:
        resource: Inspected or created group.
        options: Validated target.
    """
    _owned(resource, options, options.scope)
    _equal(
        _record(resource.get("properties")),
        {"provisioningState": "Succeeded"},
        "resource group state",
    )


def _identity(resource: Record, options: Options) -> None:
    """Validate the dedicated identity and its nonsecret UUID outputs.

    Args:
        resource: Inspected or created identity.
        options: Validated target.
    """
    _owned(resource, options, options.identity_id)
    _equal(resource, {"tenantId": options.tenant_id}, "identity tenant")
    for field in ("principalId", "clientId"):
        _require(
            condition=UUID(_uuid(resource.get(field))).int != 0,
            message="Identity returned an empty UUID.",
        )


def _credential(resource: Record, options: Options, trust: Trust) -> None:
    """Require exactly the reviewed explicit OIDC trust for one subject.

    Args:
        resource: Inspected or created credential.
        options: Reviewed trust.
        trust: Expected subject and accepted credential names.
    """
    name = resource.get("name")
    _require(
        condition=isinstance(name, str) and name in trust.accepted_names,
        message="federated credential name mismatch; refusing to overwrite.",
    )
    _equal(
        resource,
        {
            "id": options.credential_id(str(name)),
            "issuer": options.issuer,
            "subject": trust.subject,
            "audiences": [options.audience],
            "claimsMatchingExpression": None,
        },
        "federated credential",
    )


def _named(items: list[Record], name: str) -> Record | None:
    """Select a unique case-insensitive name, refusing duplicates.

    Args:
        items: Inspected resources.
        name: Requested resource name.
    """
    _require(
        condition=all(
            isinstance(item.get("name"), str) and bool(item["name"]) for item in items
        ),
        message="Resource list contains a missing or invalid name.",
    )
    matches = [item for item in items if str(item["name"]).lower() == name]
    _require(
        condition=len(matches) <= 1,
        message="Duplicate resource names; refusing ambiguity.",
    )
    return matches[0] if matches else None


def _compact(condition: str) -> str:
    """Return ``condition`` without whitespace outside single-quoted literals."""
    return re.sub(
        r"'[^']*'|\s+",
        lambda match: match[0] if match[0].startswith("'") else "",
        condition,
    )


def _same_condition(actual: object, expected: str | None) -> bool:
    """Compare ABAC conditions exactly, tolerating only API whitespace reformatting.

    Args:
        actual: Condition returned by Azure.
        expected: Reviewed condition, or ``None`` for an unconditional grant.
    """
    if expected is None or not isinstance(actual, str):
        return actual == expected
    return _compact(actual) == _compact(expected)


def _role(
    resource: Record, grant: Grant, options: Options, principal: str | None
) -> None:
    """Require one owned, RG-only assignment exactly matching ``grant``.

    Args:
        resource: Inspected or created role assignment.
        grant: Expected role, assignment UUID and condition.
        options: Reviewed target.
        principal: Verified identity object ID, never a login identity.
    """
    _require(
        condition=principal is not None,
        message="Role exists without the owned identity.",
    )
    _equal(
        resource,
        {
            "name": grant.name,
            "scope": options.scope,
            "principalId": principal,
            "principalType": "ServicePrincipal",
            "roleDefinitionId": grant.role_id,
            "conditionVersion": grant.condition_version,
            "delegatedManagedIdentityResourceId": None,
        },
        "role assignment",
    )
    _require(
        condition=_same_condition(resource.get("condition"), grant.condition),
        message="role assignment condition mismatch; refusing to overwrite.",
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Inventory:
    """Hold the validated pre-mutation inventory.

    Attributes:
        group: Whether the owned group exists.
        identity: Existing verified identity, if present.
        credentials: Subjects whose exact trust already exists.
        roles: Names of exact expected assignments that already exist.
    """

    group: bool
    identity: Record | None
    credentials: frozenset[str]
    roles: frozenset[str]


def _inspect_trust(azure: Azure, identity: Record | None) -> frozenset[str]:
    """Inspect all identity credentials, refuse additional trust, return satisfied subjects."""
    if identity is None:
        return frozenset()
    options = azure.options
    credentials = _records(
        azure.read(
            (
                "identity",
                "federated-credential",
                "list",
                "--resource-group",
                options.resource_group,
                "--identity-name",
                options.identity_name,
            )
        )
    )
    trusts = {trust.subject: trust for trust in options.trusts}
    found: list[str] = []
    for credential in credentials:
        subject = credential.get("subject")
        _require(
            condition=isinstance(subject, str) and subject in trusts,
            message="Additional federated credentials need review.",
        )
        _credential(credential, options, trusts[str(subject)])
        found.append(str(subject))
    _require(
        condition=len(set(found)) == len(found),
        message="Duplicate federated credentials need review.",
    )
    return frozenset(found)


def _bootstrap_names(options: Options) -> set[str]:
    """Return assignment UUIDs this tool derives for the identity at any level."""
    levels = (replace(options, access=access) for access in Access)
    return {grant.name for level in levels for grant in level.grants}


def _inspect_roles(azure: Azure, identity: Record | None) -> frozenset[str]:
    """Inspect ARM roles without Graph or guessing the logged-in principal."""
    options = azure.options
    principal = _uuid(identity.get("principalId")) if identity else None
    roles = _records(
        azure.read(
            (
                "role",
                "assignment",
                "list",
                "--scope",
                options.scope,
                "--include-inherited",
                "--fill-principal-name",
                "false",
                "--fill-role-definition-name",
                "false",
            )
        )
    )
    owned = _bootstrap_names(options)
    relevant = [
        role
        for role in roles
        if _uuid(role.get("name")) in owned
        or _uuid(role.get("principalId")) == principal
    ]
    expected = {grant.name: grant for grant in options.grants}
    names = [_uuid(role.get("name")) for role in relevant]
    _require(
        condition=len(set(names)) == len(names) and set(names) <= expected.keys(),
        message="Additional identity role assignments need review.",
    )
    for name, role in zip(names, relevant, strict=True):
        _role(role, expected[name], options, principal)
    return frozenset(names)


def _inspect(azure: Azure) -> Inventory:
    """Verify all existing resources before the first possible mutation."""
    _verify_account(azure)
    options = azure.options
    group = _named(_records(azure.read(("group", "list"))), options.resource_group)
    if group is None:
        return Inventory(
            group=False, identity=None, credentials=frozenset(), roles=frozenset()
        )
    _group(group, options)
    identity = _named(
        _records(
            azure.read(
                (
                    "identity",
                    "list",
                    "--resource-group",
                    options.resource_group,
                )
            )
        ),
        options.identity_name,
    )
    if identity is not None:
        _identity(identity, options)
    credentials = _inspect_trust(azure, identity)
    roles = _inspect_roles(azure, identity)
    return Inventory(
        group=True, identity=identity, credentials=credentials, roles=roles
    )


def _creates(options: Options) -> dict[str, tuple[str, ...]]:
    """Compose the group and identity operations; trust and roles are separate."""
    group = ("--resource-group", options.resource_group)
    tag = f"{_TAG}={options.tags[_TAG]}"
    return {
        "group": (
            "group",
            "create",
            "--name",
            options.resource_group,
            "--location",
            options.location,
            "--tags",
            tag,
        ),
        "identity": (
            "identity",
            "create",
            *group,
            "--name",
            options.identity_name,
            "--location",
            options.location,
            "--tags",
            tag,
        ),
    }


def _credential_create(options: Options, trust: Trust) -> tuple[str, ...]:
    """Compose one federated credential for one reviewed subject.

    Args:
        options: Validated operator choices.
        trust: Deterministic credential name and exact subject.
    """
    return (
        "identity",
        "federated-credential",
        "create",
        "--resource-group",
        options.resource_group,
        "--identity-name",
        options.identity_name,
        "--name",
        trust.name,
        "--issuer",
        options.issuer,
        "--subject",
        trust.subject,
        "--audiences",
        options.audience,
    )


def _role_create(options: Options, grant: Grant, principal: str) -> tuple[str, ...]:
    """Compose one RG-scoped assignment for the identity, with any ABAC condition.

    Args:
        options: Validated operator choices.
        grant: Expected role, assignment UUID and condition.
        principal: Verified principal ID or a clearly labelled plan placeholder.
    """
    condition = (
        ()
        if grant.condition is None
        else ("--condition", grant.condition, "--condition-version", _CONDITION_VERSION)
    )
    return (
        "role",
        "assignment",
        "create",
        "--name",
        grant.name,
        "--assignee-object-id",
        principal,
        "--assignee-principal-type",
        "ServicePrincipal",
        "--role",
        grant.role_id,
        "--scope",
        options.scope,
        *condition,
    )


def _access_summary(options: Options) -> Record:
    """Return reviewable grant fields; read keeps its original compact shape."""
    if options.access is Access.READ:
        return {"assignment_name": options.grants[0].name, "role": "Reader"}
    return {
        "access": options.access.value,
        "role_assignments": [
            {
                "assignment_name": grant.name,
                "role": grant.role,
                "role_definition_id": grant.role_id,
                "scope": options.scope,
                "principal_type": "ServicePrincipal",
                "condition": grant.condition,
                "condition_version": grant.condition_version,
            }
            for grant in options.grants
        ],
    }


def _trust_summary(options: Options) -> Record:
    """Return reviewable credential fields; one subject keeps the original keys."""
    summary: Record = {
        "federated_credentials": [
            {
                "name": trust.name,
                "id": options.credential_id(trust.name),
                "subject": trust.subject,
            }
            for trust in options.trusts
        ],
    }
    if len(options.trusts) == 1:
        summary["credential_id"] = options.credential_id(options.trusts[0].name)
    return summary


def _github_emit(options: Options, client_id: str) -> Record:
    """Print GitHub environment, branch-policy and variable commands for review.

    Args:
        options: Validated operator choices.
        client_id: Identity client ID, or a placeholder before apply.
    """
    commands: list[list[str]] = []
    values = (
        ("AZURE_CLIENT_ID", client_id),
        ("AZURE_TENANT_ID", options.tenant_id),
        ("AZURE_SUBSCRIPTION_ID", options.subscription_id),
    )
    for subject in options.subjects:
        match = re.fullmatch(_GITHUB_ENVIRONMENT, subject)
        if match is None:
            continue
        repo, environment = match.groups()
        path = f"repos/{repo}/environments/{quote(environment, safe='')}"
        commands.extend(
            (
                [
                    "gh",
                    "api",
                    "--method",
                    "PUT",
                    path,
                    "-F",
                    "deployment_branch_policy[protected_branches]=false",
                    "-F",
                    "deployment_branch_policy[custom_branch_policies]=true",
                ],
                [
                    "gh",
                    "api",
                    "--method",
                    "POST",
                    f"{path}/deployment-branch-policies",
                    "-f",
                    f"name={options.deploy_branch}",
                    "-f",
                    "type=branch",
                ],
            )
        )
        commands.extend(
            [
                "gh",
                "variable",
                "set",
                name,
                "--repo",
                repo,
                "--env",
                environment,
                "--body",
                value,
            ]
            for name, value in values
        )
    return {
        "host": _EMIT_GITHUB,
        "commands": commands,
        "notes": [
            _EMIT_NOTE,
            "Only environment:<name> subjects get environment commands; ref subjects have none.",
            "PUT replaces environment protection settings; merge with existing reviewers.",
            "Add required reviewers (numeric user/team IDs) with prevent_self_review=true.",
            "Rerunning the branch-policy POST fails if the policy already exists.",
            "Set TFSTATE_STORAGE_ACCOUNT/TFSTATE_CONTAINER for Terraform separately.",
            (
                "In environment settings, clear 'Allow administrators to bypass "
                "configured protection rules'; the deploy gate fails protected "
                "environments that allow it."
            ),
        ],
    }


def _ado_files(options: Options, ado: AdoTarget, client_id: str) -> Record:
    """Build reviewable REST payloads; IDs unknown offline stay labelled placeholders.

    Args:
        options: Validated operator choices.
        ado: Azure DevOps names.
        client_id: Identity client ID, or a placeholder before apply.
    """
    return {
        "service-connection.json": {
            "name": ado.service_connection,
            "type": "azurerm",
            "url": "https://management.azure.com/",
            "authorization": {
                "scheme": "WorkloadIdentityFederation",
                "parameters": {
                    "tenantid": options.tenant_id,
                    "serviceprincipalid": client_id,
                },
            },
            "data": {
                "subscriptionId": options.subscription_id,
                "subscriptionName": options.subscription_id,
                "environment": "AzureCloud",
                "scopeLevel": "Subscription",
                "creationMode": "Manual",
            },
            "isShared": False,
            "serviceEndpointProjectReferences": [
                {
                    "projectReference": {
                        "id": _PROJECT_PLACEHOLDER,
                        "name": ado.project,
                    },
                    "name": ado.service_connection,
                }
            ],
        },
        "environment.json": {
            "name": ado.environment,
            "description": "Protected deployment target; see bootstrap.md.",
        },
        "branch-control.json": {
            "type": {"id": _TASK_CHECK, "name": "Task Check"},
            "settings": {
                "displayName": "Branch control",
                "definitionRef": {
                    "id": _BRANCH_PROTECTION,
                    "name": "evaluatebranchProtection",
                    "version": "0.0.1",
                },
                "inputs": {
                    "allowedBranches": f"refs/heads/{options.deploy_branch}",
                    "ensureProtectionOfBranch": "true",
                    "allowUnknownStatusBranch": "false",
                },
            },
            "timeout": _CHECK_TIMEOUT_MINUTES,
            "resource": {"type": "environment", "id": _ENVIRONMENT_PLACEHOLDER},
        },
    }


def _ado_emit(options: Options, ado: AdoTarget, client_id: str) -> Record:
    """Print Azure DevOps workload identity, environment and policy commands.

    Args:
        options: Validated operator choices.
        ado: Azure DevOps names.
        client_id: Identity client ID, or a placeholder before apply.
    """
    org = ("--organization", ado.organization)
    project = ("--project", ado.project)
    route = ("--route-parameters", f"project={ado.project}", "--http-method", "POST")
    commands = [
        ["az", "devops", "project", "show", *project, *org, "--query", "id"],
        [
            "az",
            "devops",
            "service-endpoint",
            "create",
            "--service-endpoint-configuration",
            "service-connection.json",
            *org,
            *project,
        ],
        [
            "az",
            "devops",
            "invoke",
            *org,
            "--area",
            "distributedtask",
            "--resource",
            "environments",
            *route,
            "--in-file",
            "environment.json",
            "--api-version",
            "7.1",
        ],
        [
            "az",
            "devops",
            "invoke",
            *org,
            "--area",
            "PipelinesChecks",
            "--resource",
            "configurations",
            *route,
            "--in-file",
            "branch-control.json",
            "--api-version",
            "7.1-preview.1",
        ],
        [
            "az",
            "repos",
            "policy",
            "approver-count",
            "create",
            *org,
            *project,
            "--repository-id",
            _REPOSITORY_PLACEHOLDER,
            "--branch",
            options.deploy_branch,
            "--minimum-approver-count",
            "1",
            "--creator-vote-counts",
            "false",
            "--allow-downvotes",
            "false",
            "--reset-on-source-push",
            "true",
            "--blocking",
            "true",
            "--enabled",
            "true",
        ],
    ]
    return {
        "host": _EMIT_ADO,
        "commands": commands,
        "files": _ado_files(options, ado, client_id),
        "notes": [
            _EMIT_NOTE,
            (
                f"Replace {_PROJECT_PLACEHOLDER}, {_ENVIRONMENT_PLACEHOLDER} and "
                f"{_REPOSITORY_PLACEHOLDER} with IDs returned by the earlier commands."
            ),
            (
                "Create the service connection first; its Entra issuer/subject exist only "
                "afterwards. Rerun bootstrap with that exact subject before first use."
            ),
            "Do not grant the service connection to all pipelines; authorize per pipeline.",
            "Add Approvals and Exclusive lock checks in the environment UI (need user IDs).",
            "Check type and definition IDs are from the Branch control check; verify them.",
        ],
    }


def _emit(options: Options, client_id: str) -> Record | None:
    """Return the requested printed-only CI-host setup, or ``None``."""
    if options.emit is None:
        return None
    if options.emit == _EMIT_GITHUB:
        return _github_emit(options, client_id)
    ado = options.ado
    if ado is None:
        message = "Missing Azure DevOps names."
        raise BootstrapError(message)
    return _ado_emit(options, ado, client_id)


def plan(options: Options) -> Record:
    """Return a deterministic nonsecret plan with no environment or process I/O."""
    oidc: Record = {
        "host": options.ci_host,
        "issuer": options.issuer,
        "subjects": list(options.subjects),
        "audience": options.audience,
    }
    if len(options.subjects) == 1:
        oidc["subject"] = options.subjects[0]
    result: Record = {
        "mode": "plan",
        "tenant_id": options.tenant_id,
        "subscription_id": options.subscription_id,
        "resource_group_id": options.scope,
        "identity_id": options.identity_id,
        **_trust_summary(options),
        **_access_summary(options),
        "ownership_tags": options.tags,
        "oidc": oidc,
        "create_commands": [
            list(_command(options, args))
            for args in (
                *_creates(options).values(),
                *(_credential_create(options, trust) for trust in options.trusts),
                *(
                    _role_create(options, grant, "PRINCIPAL_ID_FROM_IDENTITY")
                    for grant in options.grants
                ),
            )
        ],
        "instructions": [
            "No commands executed. Claims are operator-attested, not remotely verified.",
            "Review bootstrap.md, then rerun the same inputs with --apply.",
            "Apply verifies account/cloud and inspects ownership before creating.",
            *options.steps,
        ],
    }
    emitted = _emit(options, _CLIENT_PLACEHOLDER)
    if emitted is not None:
        result["emit"] = emitted
    return result


def _ensure_roles(azure: Azure, existing: frozenset[str], principal: str) -> None:
    """Create and verify each expected assignment not already present.

    Args:
        azure: CLI adapter for the reviewed target.
        existing: Names of exact expected assignments found during inspection.
        principal: Verified identity object ID.
    """
    options = azure.options
    for grant in options.grants:
        if grant.name not in existing:
            command = _role_create(options, grant, principal)
            _role(_record(azure.read(command)), grant, options, principal)


def apply(azure: Azure) -> Record:
    """Inspect before creating; surface every failure and retain partial resources."""
    inventory = _inspect(azure)
    options = azure.options
    commands = _creates(options)
    if not inventory.group:
        _group(_record(azure.read(commands["group"])), options)
    identity = inventory.identity
    if identity is None:
        identity = _record(azure.read(commands["identity"]))
        _identity(identity, options)
    for trust in options.trusts:
        if trust.subject not in inventory.credentials:
            created = _record(azure.read(_credential_create(options, trust)))
            _credential(created, options, trust)
    principal = _uuid(identity.get("principalId"))
    client_id = _uuid(identity.get("clientId"))
    _ensure_roles(azure, inventory.roles, principal)
    result: Record = {
        "mode": "applied",
        "tenant_id": options.tenant_id,
        "subscription_id": options.subscription_id,
        "resource_group_id": options.scope,
        "identity_id": options.identity_id,
        **_trust_summary(options),
        "client_id": client_id,
        "principal_id": principal,
        **_access_summary(options),
        "instructions": list(options.steps),
    }
    emitted = _emit(options, client_id)
    if emitted is not None:
        result["emit"] = emitted
    return result


def main(argv: list[str] | None = None, *, execute: Execute = _execute) -> int:
    """Print the offline plan or explicitly apply through the injected CLI.

    Args:
        argv: CLI arguments; defaults to the process arguments.
        execute: Native process adapter or an offline test fake.
    """
    options = parse_options(argv)
    try:
        result = (
            apply(Azure(options=options, execute=execute))
            if options.apply
            else plan(options)
        )
    except BootstrapError as error:
        sys.stderr.write(
            f"Bootstrap refused/failed: {error}\n"
            "Partial resources may remain; inspect before retrying. No rollback attempted.\n"
        )
        return 1
    sys.stdout.write(json.dumps(result, indent=_JSON_INDENT, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
