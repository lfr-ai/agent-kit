"""Exercise the operator CLI with scripted Azure replies, never Azure or Git."""

from collections.abc import Callable
from dataclasses import dataclass, field
import importlib.util
import json
import subprocess
import sys
from types import ModuleType
from typing import Final
from uuid import UUID

import pytest

from delivery_tools.catalog import ROOT

pytestmark = pytest.mark.integration


def _load_bootstrap() -> ModuleType:
    """Load the standalone operator script by path; it is not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "bootstrap_azure", ROOT / "scripts/bootstrap_azure.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap()
TENANT: Final[str] = "54c20bb8-0341-4ad0-9f62-021234ce0493"
SUBSCRIPTION: Final[str] = "03f5c670-3cfa-41b8-8ba0-532ea8a4c272"
PRINCIPAL: Final[str] = "9fb77c58-2ab3-4495-8746-1c3fb908b386"
CLIENT: Final[str] = "94d6cbce-352e-4474-a36b-272523da0b35"
OTHER: Final[str] = "6db98ca1-e2f0-4463-833c-d969dce72559"


@pytest.fixture(autouse=True)
def forbid_real_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Tests must never execute Azure, Git or another real process")

    monkeypatch.setattr(bootstrap.subprocess, "Popen", forbidden)


def arguments(*extra: str) -> list[str]:
    return [
        "--tenant-id",
        TENANT,
        "--subscription-id",
        SUBSCRIPTION,
        "--resource-group",
        "billing-dev",
        "--location",
        "westeurope",
        "--identity-name",
        "billing-ci",
        "--ci-host",
        "github",
        "--issuer",
        "https://token.actions.githubusercontent.com",
        "--subject",
        "repo:billing-team/billing:environment:dev",
        "--audience",
        "api://AzureADTokenExchange",
        "--oidc-reviewed",
        *extra,
    ]


def changed(flag: str, value: str, *, apply: bool = False) -> list[str]:
    result = arguments(*(["--apply"] if apply else []))
    result[result.index(flag) + 1] = value
    return result


@dataclass(kw_only=True, slots=True)
class FakeAzure:
    replies: list[object]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, command: tuple[str, ...]) -> str:
        self.calls.append(command)
        assert command[0] == "az"
        if command[1:3] != ("cloud", "show"):
            assert command[command.index("--subscription") + 1] == SUBSCRIPTION
        assert "--output" in command
        assert "--only-show-errors" in command
        assert self.replies, f"Unexpected command: {command}"
        response = self.replies.pop(0)
        if isinstance(response, bootstrap.BootstrapError):
            raise response
        return json.dumps(response)


def preflight() -> list[object]:
    return [
        {
            "id": SUBSCRIPTION,
            "tenantId": TENANT,
            "environmentName": "AzureCloud",
            "state": "Enabled",
        },
        {
            "name": "AzureCloud",
            "endpoints": {
                "resourceManager": "https://management.azure.com/",
                "activeDirectory": "https://login.microsoftonline.com",
            },
        },
    ]


def resources() -> tuple[dict[str, object], ...]:
    options = bootstrap.parse_options(arguments())
    group: dict[str, object] = {
        "id": options.scope,
        "name": options.resource_group,
        "location": options.location,
        "tags": options.tags,
        "properties": {"provisioningState": "Succeeded"},
    }
    identity: dict[str, object] = {
        "id": options.identity_id,
        "name": options.identity_name,
        "location": options.location,
        "tags": options.tags,
        "tenantId": TENANT,
        "principalId": PRINCIPAL,
        "clientId": CLIENT,
    }
    credential: dict[str, object] = {
        "id": options.credential_id("ci"),
        "name": "ci",
        "issuer": options.issuer,
        "subject": options.subjects[0],
        "audiences": [options.audience],
    }
    (role,) = assignments(options)
    return group, identity, credential, role


def assignments(options: bootstrap.Options) -> list[dict[str, object]]:
    return [
        {
            "name": grant.name,
            "scope": options.scope,
            "principalId": PRINCIPAL,
            "principalType": "ServicePrincipal",
            "roleDefinitionId": grant.role_id,
            "condition": grant.condition,
            "conditionVersion": grant.condition_version,
        }
        for grant in options.grants
    ]


def mutations(runner: FakeAzure) -> list[tuple[str, ...]]:
    return [call for call in runner.calls if "create" in call]


def test_default_is_deterministic_and_does_not_resolve_or_run_any_executable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Offline plan attempted executable discovery or a subprocess")

    monkeypatch.setattr(bootstrap.shutil, "which", forbidden)
    monkeypatch.setattr(bootstrap.subprocess, "run", forbidden)
    assert bootstrap.main(arguments()) == 0
    first = capsys.readouterr().out
    assert bootstrap.main(arguments()) == 0
    assert capsys.readouterr().out == first
    plan = json.loads(first)
    assert plan["mode"] == "plan"
    assert plan["tenant_id"] == TENANT
    assert plan["subscription_id"] == SUBSCRIPTION
    assert plan["role"] == "Reader"
    assert len(plan["create_commands"]) == 4
    assert "login" not in [word for cmd in plan["create_commands"] for word in cmd]


@pytest.mark.parametrize(
    "flag",
    [
        "--tenant-id",
        "--subscription-id",
        "--resource-group",
        "--location",
        "--identity-name",
        "--ci-host",
        "--issuer",
        "--subject",
        "--audience",
        "--oidc-reviewed",
    ],
)
def test_required_operator_inputs(flag: str) -> None:
    argv = arguments()
    index = argv.index(flag)
    del argv[index : index + (1 if flag == "--oidc-reviewed" else 2)]
    with pytest.raises(SystemExit) as error:
        bootstrap.parse_options(argv)
    assert error.value.code == 2


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--tenant-id", "missing"),
        ("--subscription-id", "--debug"),
        ("--resource-group", "rg;whoami"),
        ("--resource-group", "../billing"),
        ("--location", "west europe"),
        ("--identity-name", "$(whoami)"),
        ("--issuer", "https://token.actions.githubusercontent.com.evil.test"),
        ("--issuer", "https://user:password@token.actions.githubusercontent.com"),
        ("--issuer", "https://token.actions.githubusercontent.com/?token=secret"),
        ("--subject", "repo:billing-team/billing:*"),
        ("--subject", "repo:billing-team/billing:environment:%PATH%"),
        ("--subject", "repo:billing-team/billing:environment:dev\n--debug"),
        ("--subject", "sc://org/project/connection"),
        ("--audience", "api://wrong-cloud"),
        ("--ci-host", "guess"),
    ],
)
def test_malformed_inputs_refused_without_commands(flag: str, value: str) -> None:
    runner = FakeAzure(replies=[])
    with pytest.raises(SystemExit) as error:
        bootstrap.main(changed(flag, value, apply=True), execute=runner)
    assert error.value.code == 2
    assert not runner.calls


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--tenant-id", "00000000-0000-0000-0000-000000000000"),
        ("--subscription-id", "11111111-1111-1111-1111-111111111111"),
        ("--resource-group", "example-rg"),
        ("--location", "placeholder"),
        ("--identity-name", "placeholder-ci"),
        ("--subject", "repo:example/repository:environment:dev"),
    ],
)
def test_apply_rejects_synthetic_targets_before_commands(flag: str, value: str) -> None:
    runner = FakeAzure(replies=[])
    with pytest.raises(SystemExit):
        bootstrap.main(changed(flag, value, apply=True), execute=runner)
    assert not runner.calls


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", OTHER),
        ("tenantId", OTHER),
        ("environmentName", "AzureUSGovernment"),
        ("state", "Disabled"),
    ],
)
def test_account_mismatch_refuses_before_mutation(
    field_name: str, value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    replies = preflight()
    account = replies[0]
    assert isinstance(account, dict)
    account[field_name] = value
    runner = FakeAzure(replies=replies)
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert len(runner.calls) == 1
    assert "account" in capsys.readouterr().err
    assert not mutations(runner)


def test_wrong_active_cloud_refuses_before_resource_inspection() -> None:
    replies = preflight()
    replies[1] = {"name": "AzureChinaCloud"}
    runner = FakeAzure(replies=replies)
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert len(runner.calls) == 2
    assert not mutations(runner)


def test_empty_target_creates_only_four_bounded_resources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeAzure(replies=[*preflight(), [], *resources()])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["client_id"] == CLIENT
    assert result["principal_id"] == PRINCIPAL
    assert not any("No commands executed" in step for step in result["instructions"])
    assert len(mutations(runner)) == 4
    assert not runner.replies
    role = runner.calls[-1]
    assert role[1:4] == ("role", "assignment", "create")
    assert role[role.index("--assignee-object-id") + 1] == PRINCIPAL
    assert role[role.index("--assignee-principal-type") + 1] == "ServicePrincipal"
    assert role[role.index("--scope") + 1] == resources()[0]["id"]
    assert not {"login", "set", "ad", "gh", "git"}.intersection(
        word for call in runner.calls for word in call
    )


def test_rerun_is_read_only_and_role_inspection_avoids_graph() -> None:
    group, identity, credential, role = resources()
    runner = FakeAzure(
        replies=[*preflight(), [group], [identity], [credential], [role]]
    )
    assert bootstrap.main(arguments("--apply"), execute=runner) == 0
    assert not runner.replies
    assert not mutations(runner)
    role_read = runner.calls[-1]
    assert role_read[role_read.index("--fill-principal-name") + 1] == "false"
    assert "--include-inherited" in role_read


@pytest.mark.parametrize(
    ("index", "field_name", "value"),
    [
        (0, "tags", {}),
        (0, "location", "eastus"),
        (0, "id", "/subscriptions/wrong/resourceGroups/billing-dev"),
        (1, "tags", {}),
        (1, "tenantId", OTHER),
        (1, "principalId", "not-a-uuid"),
        (1, "principalId", "00000000-0000-0000-0000-000000000000"),
        (2, "issuer", "https://wrong.test"),
        (2, "subject", "repo:other/billing:environment:dev"),
        (2, "audiences", ["api://AzureADTokenExchange", "another"]),
        (2, "name", "unexpected-trust"),
        (3, "principalId", OTHER),
        (
            3,
            "roleDefinitionId",
            "/providers/Microsoft.Authorization/roleDefinitions/owner",
        ),
        (3, "scope", f"/subscriptions/{SUBSCRIPTION}"),
        (3, "condition", "unexpected condition"),
    ],
)
def test_existing_conflicts_fail_before_any_mutation(
    index: int, field_name: str, value: object
) -> None:
    entries = resources()
    entries[index][field_name] = value
    runner = FakeAzure(replies=[*preflight(), *[[entry] for entry in entries]])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


def test_resume_after_identity_creation_only_creates_missing_trust_and_role() -> None:
    group, identity, credential, role = resources()
    runner = FakeAzure(
        replies=[*preflight(), [group], [identity], [], [], credential, role]
    )
    assert bootstrap.main(arguments("--apply"), execute=runner) == 0
    assert len(mutations(runner)) == 2
    assert not runner.replies


def test_failure_is_explicit_and_does_not_continue_or_undo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    group, identity, _, _ = resources()
    runner = FakeAzure(
        replies=[
            *preflight(),
            [],
            group,
            identity,
            bootstrap.BootstrapError("Azure operation failed; exit 17"),
        ]
    )
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "exit 17" in captured.err
    assert "Partial resources may remain" in captured.err
    assert len(mutations(runner)) == 3


@pytest.mark.parametrize("response", [None, {"unexpected": True}, "secret-token"])
def test_bad_account_response_fails_closed_without_echo(
    response: object, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeAzure(replies=[response])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert "secret-token" not in capsys.readouterr().err
    assert not mutations(runner)


def test_ado_accepts_generated_entra_trust_without_inventing_subject(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = arguments()
    values = {
        "--ci-host": "ado",
        "--issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "--subject": "/eid1/c/pub/t/generated/a/generated/sc/generated",
    }
    for flag, value in values.items():
        argv[argv.index(flag) + 1] = value
    assert bootstrap.main(argv, execute=FakeAzure(replies=[])) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["oidc"]["subject"] == values["--subject"]


def test_native_adapter_redacts_failure_and_never_uses_shell(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs.get("shell", False) is False
        assert kwargs["stdin"] == subprocess.DEVNULL
        return subprocess.CompletedProcess(
            command, 17, "SECRET stdout", "SECRET stderr"
        )

    monkeypatch.setattr(bootstrap.shutil, "which", lambda _: "fake-az")
    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    assert bootstrap.main(arguments("--apply")) == 1
    error = capsys.readouterr().err
    assert "17" in error
    assert "SECRET" not in error
    assert calls[0][0] == "fake-az"


@pytest.mark.parametrize("kind", ["missing", "os-error", "timeout", "decode"])
def test_native_adapter_failures_are_explicit_and_redacted(
    kind: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if kind == "timeout":
            raise subprocess.TimeoutExpired(command, 120, output="SECRET")
        if kind == "decode":
            error = UnicodeDecodeError("utf-8", b"\xffSECRET", 0, 1, "invalid")
            raise error
        message = "SECRET"
        raise OSError(message)

    monkeypatch.setattr(
        bootstrap.shutil, "which", lambda _: None if kind == "missing" else "fake-az"
    )
    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    assert bootstrap.main(arguments("--apply")) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "Bootstrap refused/failed" in captured.err
    assert "SECRET" not in captured.err


def test_invalid_json_never_becomes_a_missing_resource(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid(command: tuple[str, ...]) -> str:
        return "SECRET not JSON"

    assert bootstrap.main(arguments("--apply"), execute=invalid) == 1
    error = capsys.readouterr().err
    assert "invalid JSON" in error
    assert "SECRET" not in error


@pytest.mark.parametrize(
    "reply",
    [None, {}, [{"id": "missing-name"}], bootstrap.BootstrapError("Read denied")],
)
def test_group_read_failures_are_not_absence(reply: object) -> None:
    runner = FakeAzure(replies=[*preflight(), reply])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


def test_wrong_cloud_endpoint_refuses_before_mutation() -> None:
    replies = preflight()
    replies[1] = {
        "name": "AzureCloud",
        "endpoints": {
            "resourceManager": "https://wrong.test/",
            "activeDirectory": "https://login.microsoftonline.com",
        },
    }
    runner = FakeAzure(replies=replies)
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_duplicate_resources_or_additional_trust_refused(index: int) -> None:
    entries = [[entry] for entry in resources()]
    entries[index].append(entries[index][0].copy())
    runner = FakeAzure(replies=[*preflight(), *entries])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


def test_role_conflict_is_checked_before_creating_missing_credential() -> None:
    group, identity, _, role = resources()
    role["scope"] = f"/subscriptions/{SUBSCRIPTION}"
    runner = FakeAzure(replies=[*preflight(), [group], [identity], [], [role]])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


def test_unknown_role_shape_is_not_treated_as_absence() -> None:
    group, identity, credential, _ = resources()
    runner = FakeAzure(
        replies=[
            *preflight(),
            [group],
            [identity],
            [credential],
            [{"unexpected": True}],
        ]
    )
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


def test_existing_group_with_no_identity_resumes_safely() -> None:
    group, identity, credential, role = resources()
    runner = FakeAzure(
        replies=[*preflight(), [group], [], [], identity, credential, role]
    )
    assert bootstrap.main(arguments("--apply"), execute=runner) == 0
    assert len(mutations(runner)) == 3
    assert not runner.replies


def test_created_identity_is_verified_before_trust_or_role_writes() -> None:
    group, identity, _, _ = resources()
    identity["tenantId"] = OTHER
    runner = FakeAzure(replies=[*preflight(), [], group, identity])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert len(mutations(runner)) == 2


def test_case_variant_extra_grant_is_not_ignored() -> None:
    group, identity, credential, expected_role = resources()
    extra_role = {**expected_role, "name": OTHER, "principalId": PRINCIPAL.upper()}
    runner = FakeAzure(
        replies=[
            *preflight(),
            [group],
            [identity],
            [credential],
            [extra_role],
            expected_role,
        ]
    )
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


def test_failed_created_group_state_stops_before_identity_creation() -> None:
    group, identity, credential, role = resources()
    group["properties"] = {"provisioningState": "Failed"}
    runner = FakeAzure(replies=[*preflight(), [], group, identity, credential, role])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert len(mutations(runner)) == 1


@pytest.mark.parametrize(
    ("issuer", "subject", "accepted"),
    [
        (
            f"https://vstoken.dev.azure.com/{OTHER}",
            "sc://billing-org/Billing Project/azure-dev",
            True,
        ),
        (
            f"https://vstoken.dev.azure.com/{OTHER}",
            "/eid1/c/pub/t/not-a-legacy-subject",
            False,
        ),
        (
            f"https://login.microsoftonline.com/{OTHER}/v2.0",
            "/eid1/c/pub/t/generated",
            False,
        ),
    ],
)
def test_ado_issuer_and_subject_validation(
    issuer: str, subject: str, accepted: bool
) -> None:
    argv = arguments()
    for flag, value in {
        "--ci-host": "ado",
        "--issuer": issuer,
        "--subject": subject,
    }.items():
        argv[argv.index(flag) + 1] = value
    if accepted:
        assert bootstrap.main(argv, execute=FakeAzure(replies=[])) == 0
    else:
        with pytest.raises(SystemExit):
            bootstrap.main(argv, execute=FakeAzure(replies=[]))


def test_apply_refuses_synthetic_ado_issuer_without_commands() -> None:
    argv = arguments("--apply")
    values = {
        "--ci-host": "ado",
        "--issuer": "https://vstoken.dev.azure.com/00000000-0000-0000-0000-000000000000",
        "--subject": "sc://billing-org/Billing Project/azure-dev",
    }
    for flag, value in values.items():
        argv[argv.index(flag) + 1] = value
    runner = FakeAzure(replies=[])
    with pytest.raises(SystemExit):
        bootstrap.main(argv, execute=runner)
    assert not runner.calls


ROLES: Final[str] = (
    "1407120a-92aa-4202-b7e9-c0e197c71c8f, 3913510d-42f4-4e42-8a64-420c390055eb, "
    "4633458b-17de-408a-b874-0445c86b69e6, 53ca6127-db72-4b80-b1b0-d745d6d5456d, "
    "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 7f951dda-4ed3-4680-a7ca-43fe172d538d, "
    "8311e382-0749-4cb8-b61a-304f252e45ec, 8ebe5a00-799e-43f5-93ac-243d3dce84a7, "
    "a97b65f3-24c7-4388-baec-2e87135dc908, ba92f5b4-2d11-453d-a403-e96b0029c9fe"
)
CONDITION: Final[str] = (
    "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR "
    "(@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] "
    "ForAnyOfAnyValues:GuidEquals {" + ROLES + "} AND "
    "@Request[Microsoft.Authorization/roleAssignments:PrincipalType] "
    "ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND "
    "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR "
    "(@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] "
    "ForAnyOfAnyValues:GuidEquals {" + ROLES + "} AND "
    "@Resource[Microsoft.Authorization/roleAssignments:PrincipalType] "
    "ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
)
ROLE_PREFIX: Final[str] = (
    f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/"
)
CONTRIBUTOR: Final[str] = ROLE_PREFIX + "b24988ac-6180-42a0-ab88-20f7382dd24c"
RBAC_ADMIN: Final[str] = ROLE_PREFIX + "f58310d9-a9f6-439a-9e8d-f62e7b41a168"
READER: Final[str] = ROLE_PREFIX + "acdd72a7-3385-48ef-bd42-f606fba81ae7"


def deploy_state() -> tuple[dict[str, object], ...]:
    group, identity, credential, _ = resources()
    contributor, admin = assignments(
        bootstrap.parse_options(arguments("--access", "deploy"))
    )
    return group, identity, credential, contributor, admin


def test_delegable_roles_are_unique_canonical_guids() -> None:
    roles = bootstrap.DELEGABLE_ROLES
    assert len(roles) == 10
    assert len(set(roles)) == len(roles)
    assert all(str(UUID(role)) == role for role in roles)
    assert ", ".join(sorted(roles)) == ROLES


def test_access_defaults_to_read_with_unchanged_plan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert bootstrap.main(arguments()) == 0
    default = capsys.readouterr().out
    assert bootstrap.main(arguments("--access", "read")) == 0
    assert capsys.readouterr().out == default
    plan = json.loads(default)
    assert "access" not in plan
    assert "role_assignments" not in plan
    assert plan["role"] == "Reader"
    role = plan["create_commands"][-1]
    assert role[role.index("--role") + 1] == READER
    assert "--condition" not in role


def test_deploy_plan_shows_both_grants_with_exact_condition(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert bootstrap.main(arguments("--access", "deploy")) == 0
    plan = json.loads(capsys.readouterr().out)
    scope = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/billing-dev"
    assert plan["access"] == "deploy"
    assert "role" not in plan
    contributor, admin = plan["role_assignments"]
    assert (contributor["role"], contributor["role_definition_id"]) == (
        "Contributor",
        CONTRIBUTOR,
    )
    assert contributor["condition"] is None
    assert admin["role"] == "Role Based Access Control Administrator"
    assert admin["role_definition_id"] == RBAC_ADMIN
    assert admin["condition"] == CONDITION
    assert admin["condition_version"] == "2.0"
    assert {contributor["scope"], admin["scope"]} == {scope}
    assert contributor["assignment_name"] != admin["assignment_name"]
    commands = plan["create_commands"]
    assert len(commands) == 5
    assert READER not in [word for command in commands for word in command]
    assert commands[-1][commands[-1].index("--condition") + 1] == CONDITION


def test_deploy_apply_issues_exact_role_creates() -> None:
    group, identity, credential, contributor, admin = deploy_state()
    runner = FakeAzure(
        replies=[*preflight(), [], group, identity, credential, contributor, admin]
    )
    assert (
        bootstrap.main(arguments("--apply", "--access", "deploy"), execute=runner) == 0
    )
    assert not runner.replies
    assert len(mutations(runner)) == 5
    scope = str(group["id"])
    tail = ("--subscription", SUBSCRIPTION, "--only-show-errors", "--output", "json")
    base = ("--assignee-object-id", PRINCIPAL, "--assignee-principal-type")
    assert runner.calls[-2:] == [
        (
            "az",
            "role",
            "assignment",
            "create",
            "--name",
            str(contributor["name"]),
            *base,
            "ServicePrincipal",
            "--role",
            CONTRIBUTOR,
            "--scope",
            scope,
            *tail,
        ),
        (
            "az",
            "role",
            "assignment",
            "create",
            "--name",
            str(admin["name"]),
            *base,
            "ServicePrincipal",
            "--role",
            RBAC_ADMIN,
            "--scope",
            scope,
            "--condition",
            CONDITION,
            "--condition-version",
            "2.0",
            *tail,
        ),
    ]


def _lock_steps(instructions: list[str]) -> list[str]:
    return [step for step in instructions if "Microsoft.Authorization/locks/" in step]


def test_deploy_instructions_require_operator_owned_lock_writer_role(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prod-like locks need a custom write-only lock role the script never creates."""
    assert bootstrap.main(arguments("--access", "deploy")) == 0
    plan = json.loads(capsys.readouterr().out)
    (step,) = _lock_steps(plan["instructions"])
    for text in (
        "CanNotDelete",
        "Before the first prod-like deploy",
        "at this resource group",
        "Microsoft.Authorization/locks/read and Microsoft.Authorization/locks/write",
        "no delete",
        "never creates it",
    ):
        assert text in step
    assert "locks/delete" not in step
    assert "locks" not in json.dumps(plan["create_commands"])
    group, identity, credential, contributor, admin = deploy_state()
    runner = FakeAzure(
        replies=[*preflight(), [], group, identity, credential, contributor, admin]
    )
    assert (
        bootstrap.main(arguments("--apply", "--access", "deploy"), execute=runner) == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert _lock_steps(applied["instructions"]) == [step]
    assert not any("locks" in word for call in runner.calls for word in call)


def test_read_instructions_do_not_mention_lock_role(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert bootstrap.main(arguments()) == 0
    assert not _lock_steps(json.loads(capsys.readouterr().out)["instructions"])


@pytest.mark.parametrize(
    "condition",
    [CONDITION, CONDITION.replace(" AND ((", "\n AND\n (\n (").replace("((!", "( (!")],
)
def test_deploy_rerun_with_matching_assignments_writes_nothing(
    condition: str, capsys: pytest.CaptureFixture[str]
) -> None:
    group, identity, credential, contributor, admin = deploy_state()
    admin["condition"] = condition
    runner = FakeAzure(
        replies=[*preflight(), [group], [identity], [credential], [admin, contributor]]
    )
    assert (
        bootstrap.main(arguments("--apply", "--access", "deploy"), execute=runner) == 0
    )
    assert not runner.replies
    assert not mutations(runner)
    assert len(json.loads(capsys.readouterr().out)["role_assignments"]) == 2


def test_deploy_resume_creates_only_missing_assignment() -> None:
    group, identity, credential, contributor, admin = deploy_state()
    runner = FakeAzure(
        replies=[*preflight(), [group], [identity], [credential], [contributor], admin]
    )
    assert (
        bootstrap.main(arguments("--apply", "--access", "deploy"), execute=runner) == 0
    )
    assert not runner.replies
    (create,) = mutations(runner)
    assert create[create.index("--role") + 1] == RBAC_ADMIN


def _reader_leftover(roles: list[dict[str, object]]) -> None:
    (reader,) = assignments(bootstrap.parse_options(arguments()))
    roles.append(reader)


def _extra_role(roles: list[dict[str, object]]) -> None:
    roles.append({**roles[0], "name": OTHER, "roleDefinitionId": READER})


def _condition(
    value: object, version: object = "2.0"
) -> Callable[[list[dict[str, object]]], None]:
    def change(roles: list[dict[str, object]]) -> None:
        roles[1]["condition"] = value
        roles[1]["conditionVersion"] = version

    return change


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_reader_leftover, id="reader-leftover"),
        pytest.param(_extra_role, id="extra-role"),
        pytest.param(_condition(None, None), id="unconditional-admin"),
        pytest.param(_condition(CONDITION, "1.0"), id="condition-version"),
        pytest.param(
            _condition(CONDITION.replace(", ba92f5b4-2d11-453d-a403-e96b0029c9fe", "")),
            id="fewer-roles",
        ),
        pytest.param(
            _condition(CONDITION.replace("'ServicePrincipal'", "'Service Principal'")),
            id="quoted-whitespace",
        ),
        pytest.param(
            _condition(CONDITION.split(" AND ((!")[0]), id="missing-delete-clause"
        ),
    ],
)
def test_deploy_conflicts_refused_before_mutation(
    mutate: Callable[[list[dict[str, object]]], None],
) -> None:
    group, identity, _, contributor, admin = deploy_state()
    roles = [contributor, admin]
    mutate(roles)
    runner = FakeAzure(replies=[*preflight(), [group], [identity], [], roles])
    assert (
        bootstrap.main(arguments("--apply", "--access", "deploy"), execute=runner) == 1
    )
    assert not mutations(runner)


def test_read_refuses_deploy_leftovers_before_mutation() -> None:
    group, identity, _, contributor, _ = deploy_state()
    runner = FakeAzure(replies=[*preflight(), [group], [identity], [], [contributor]])
    assert bootstrap.main(arguments("--apply"), execute=runner) == 1
    assert not mutations(runner)


@pytest.mark.parametrize(
    "extra",
    [("--access", "write"), ("--access",), ("--acc", "deploy"), ("--access", "DEPLOY")],
)
def test_access_argument_validation(extra: tuple[str, ...]) -> None:
    runner = FakeAzure(replies=[])
    with pytest.raises(SystemExit) as error:
        bootstrap.main(arguments("--apply", *extra), execute=runner)
    assert error.value.code == 2
    assert not runner.calls


PROD: Final[str] = "repo:billing-team/billing:environment:prod"
ADO_FLAGS: Final[tuple[str, ...]] = (
    "--emit",
    "azure-devops",
    "--ado-organization",
    "https://dev.azure.com/billing",
    "--ado-project",
    "Billing",
    "--ado-environment",
    "billing-prod",
)


def multi(*extra: str) -> list[str]:
    return [*arguments(*extra), "--subject", PROD]


def ado_arguments(*extra: str) -> list[str]:
    argv = arguments(*extra)
    values = {
        "--ci-host": "ado",
        "--issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "--subject": "/eid1/c/pub/t/generated/a/generated/sc/generated",
    }
    for flag, value in values.items():
        argv[argv.index(flag) + 1] = value
    return argv


def trust_record(
    options: bootstrap.Options, name: str, subject: str
) -> dict[str, object]:
    return {
        "id": options.credential_id(name),
        "name": name,
        "issuer": options.issuer,
        "subject": subject,
        "audiences": [options.audience],
    }


def no_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Emit must print commands, never resolve or run them")

    monkeypatch.setattr(bootstrap.shutil, "which", forbidden)
    monkeypatch.setattr(bootstrap.subprocess, "run", forbidden)


def test_single_subject_plan_keeps_ci_name_and_original_keys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert bootstrap.main(arguments()) == 0
    plan = json.loads(capsys.readouterr().out)
    options = bootstrap.parse_options(arguments())
    assert plan["credential_id"] == options.credential_id("ci")
    assert plan["oidc"]["subject"] == options.subjects[0]
    assert plan["oidc"]["subjects"] == list(options.subjects)
    assert [item["name"] for item in plan["federated_credentials"]] == ["ci"]
    assert "emit" not in plan


def test_multiple_subjects_plan_one_deterministic_credential_each(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert bootstrap.main(multi()) == 0
    first = capsys.readouterr().out
    assert bootstrap.main(multi()) == 0
    assert capsys.readouterr().out == first
    plan = json.loads(first)
    names = [item["name"] for item in plan["federated_credentials"]]
    assert len(set(names)) == len(names) == 2
    assert all(name.startswith("ci-") for name in names)
    assert "credential_id" not in plan
    assert "subject" not in plan["oidc"]
    creates = [cmd for cmd in plan["create_commands"] if "federated-credential" in cmd]
    assert [cmd[cmd.index("--name") + 1] for cmd in creates] == names
    assert [cmd[cmd.index("--subject") + 1] for cmd in creates] == [
        "repo:billing-team/billing:environment:dev",
        PROD,
    ]
    assert len(plan["create_commands"]) == 5


def test_multiple_subjects_apply_creates_each_trust() -> None:
    options = bootstrap.parse_options(multi())
    group, identity, _, role = resources()
    trusts = [trust_record(options, t.name, t.subject) for t in options.trusts]
    runner = FakeAzure(replies=[*preflight(), [], group, identity, *trusts, role])
    assert bootstrap.main(multi("--apply"), execute=runner) == 0
    assert not runner.replies
    assert len(mutations(runner)) == 5


def test_rerun_adopts_legacy_ci_trust_and_creates_only_missing_subject() -> None:
    options = bootstrap.parse_options(multi())
    group, identity, legacy, role = resources()
    prod = options.trusts[1]
    created = trust_record(options, prod.name, prod.subject)
    runner = FakeAzure(
        replies=[*preflight(), [group], [identity], [legacy], [role], created]
    )
    assert bootstrap.main(multi("--apply"), execute=runner) == 0
    assert not runner.replies
    (create,) = mutations(runner)
    assert create[create.index("--name") + 1] == prod.name
    assert create[create.index("--subject") + 1] == PROD


@pytest.mark.parametrize("conflict", ["unknown-subject", "duplicate", "wrong-name"])
def test_multi_subject_trust_conflicts_refused(conflict: str) -> None:
    options = bootstrap.parse_options(multi())
    group, identity, legacy, role = resources()
    dev, prod = options.trusts
    existing = {
        "unknown-subject": [
            legacy,
            trust_record(
                options, "ci-other", "repo:billing-team/billing:environment:qa"
            ),
        ],
        "duplicate": [legacy, trust_record(options, dev.name, dev.subject)],
        "wrong-name": [trust_record(options, "ci-guess", prod.subject)],
    }[conflict]
    runner = FakeAzure(replies=[*preflight(), [group], [identity], existing, [role]])
    assert bootstrap.main(multi("--apply"), execute=runner) == 1
    assert not mutations(runner)


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(
            [*arguments(), "--subject", "repo:billing-team/billing:environment:dev"],
            id="duplicate",
        ),
        pytest.param(
            [
                *arguments(),
                *(
                    word
                    for index in range(20)
                    for word in (
                        "--subject",
                        f"repo:billing-team/billing:environment:e{index}",
                    )
                ),
            ],
            id="too-many",
        ),
        pytest.param(arguments("--emit", "azure-devops"), id="emit-host-mismatch"),
        pytest.param(ado_arguments("--emit", "github"), id="emit-host-mismatch-ado"),
        pytest.param(arguments("--ado-project", "Billing"), id="ado-without-emit"),
        pytest.param(
            arguments("--emit", "github", "--ado-project", "Billing"),
            id="ado-with-github",
        ),
        pytest.param(ado_arguments("--emit", "azure-devops"), id="ado-names-missing"),
        pytest.param(arguments("--deploy-branch", "../main"), id="branch-traversal"),
        pytest.param(arguments("--deploy-branch", "main;rm"), id="branch-syntax"),
        pytest.param(
            ado_arguments(
                *ADO_FLAGS[:2],
                "--ado-organization",
                "https://evil.test/x",
                *ADO_FLAGS[4:],
            ),
            id="ado-organization",
        ),
        pytest.param(arguments("--emit", "gitlab"), id="emit-choice"),
    ],
)
def test_subject_and_emit_validation(argv: list[str]) -> None:
    runner = FakeAzure(replies=[])
    with pytest.raises(SystemExit) as error:
        bootstrap.main(argv, execute=runner)
    assert error.value.code == 2
    assert not runner.calls


def test_github_emit_prints_environment_policy_and_variables_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    no_processes(monkeypatch)
    assert bootstrap.main(multi("--emit", "github", "--deploy-branch", "release")) == 0
    emit = json.loads(capsys.readouterr().out)["emit"]
    assert emit["host"] == "github"
    assert "nothing was executed" in emit["notes"][0]
    commands = emit["commands"]
    assert all(cmd[0] == "gh" for cmd in commands)
    paths = {cmd[4] for cmd in commands if cmd[1] == "api"}
    assert "repos/billing-team/billing/environments/prod" in paths
    assert next(
        cmd[5:7] for cmd in commands if cmd[1] == "api" and cmd[3] == "POST"
    ) == ["-f", "name=release"]
    variables = {
        (cmd[cmd.index("--env") + 1], cmd[3]): cmd[-1]
        for cmd in commands
        if cmd[1] == "variable"
    }
    assert variables["prod", "AZURE_CLIENT_ID"] == "CLIENT_ID_FROM_IDENTITY"
    assert variables["dev", "AZURE_TENANT_ID"] == TENANT
    assert variables["dev", "AZURE_SUBSCRIPTION_ID"] == SUBSCRIPTION


def test_github_emit_after_apply_uses_real_client_id_and_runs_no_gh(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeAzure(replies=[*preflight(), [], *resources()])
    assert bootstrap.main(arguments("--apply", "--emit", "github"), execute=runner) == 0
    emit = json.loads(capsys.readouterr().out)["emit"]
    client = [cmd[-1] for cmd in emit["commands"] if "AZURE_CLIENT_ID" in cmd]
    assert client == [CLIENT]
    assert all(call[0] == "az" and "gh" not in call for call in runner.calls)


def test_ado_emit_prints_workload_identity_connection_and_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    no_processes(monkeypatch)
    assert bootstrap.main(ado_arguments(*ADO_FLAGS)) == 0
    emit = json.loads(capsys.readouterr().out)["emit"]
    assert emit["host"] == "azure-devops"
    commands = emit["commands"]
    assert all(cmd[0] == "az" for cmd in commands)
    assert any(cmd[1:4] == ["devops", "service-endpoint", "create"] for cmd in commands)
    assert all(
        cmd[cmd.index("--organization") + 1] == "https://dev.azure.com/billing"
        for cmd in commands
    )
    connection = emit["files"]["service-connection.json"]
    assert connection["name"] == "billing-ci"
    assert connection["authorization"]["scheme"] == "WorkloadIdentityFederation"
    assert connection["authorization"]["parameters"] == {
        "tenantid": TENANT,
        "serviceprincipalid": "CLIENT_ID_FROM_IDENTITY",
    }
    assert connection["isShared"] is False
    assert emit["files"]["environment.json"]["name"] == "billing-prod"
    inputs = emit["files"]["branch-control.json"]["settings"]["inputs"]
    assert inputs["allowedBranches"] == "refs/heads/main"
    assert inputs["ensureProtectionOfBranch"] == "true"
    text = json.dumps(emit)
    assert "secret" not in text.lower()


def with_subjects(subjects: tuple[str, ...], *extra: str) -> list[str]:
    argv = arguments(*extra)
    argv[argv.index("--subject") + 1] = subjects[0]
    for subject in subjects[1:]:
        argv.extend(("--subject", subject))
    return argv


DEV: Final[str] = "repo:billing-team/billing:environment:dev"
BRANCH: Final[str] = "repo:billing-team/billing:ref:refs/heads/main"
ONLY_ENVIRONMENTS: Final[str] = "--access deploy trusts only GitHub environment"
ONE_ENVIRONMENT: Final[str] = "--access deploy trusts one GitHub environment"


@pytest.mark.parametrize(
    ("subjects", "message"),
    [
        pytest.param((BRANCH,), ONLY_ENVIRONMENTS, id="branch"),
        pytest.param(
            ("repo:billing-team/billing:ref:refs/tags/v1",),
            ONLY_ENVIRONMENTS,
            id="tag",
        ),
        pytest.param(
            ("repo:billing-team/billing:pull_request",),
            ONLY_ENVIRONMENTS,
            id="pull-request",
        ),
        pytest.param((PROD, BRANCH), ONLY_ENVIRONMENTS, id="environment-and-branch"),
        pytest.param((DEV, PROD), ONE_ENVIRONMENT, id="two-environments"),
        pytest.param(
            (PROD, "repo:billing-team/payments:environment:prod"),
            ONE_ENVIRONMENT,
            id="two-repositories",
        ),
    ],
)
@pytest.mark.parametrize("mode", [(), ("--apply",)], ids=["plan", "apply"])
def test_deploy_access_trusts_exactly_one_github_environment(
    subjects: tuple[str, ...],
    message: str,
    mode: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Branch, tag, PR or multi-environment trust would bypass the protected environment."""
    runner = FakeAzure(replies=[])
    argv = with_subjects(subjects, *mode, "--access", "deploy")
    with pytest.raises(SystemExit) as error:
        bootstrap.main(argv, execute=runner)
    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert not runner.calls


def test_deploy_access_accepts_case_variants_of_one_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GitHub treats owner, repository and environment names case-insensitively."""
    variant = "repo:Billing-Team/Billing:environment:Prod"
    argv = with_subjects((PROD, variant), "--access", "deploy")
    assert bootstrap.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["oidc"]["subjects"] == [PROD, variant]
    assert plan["access"] == "deploy"


@pytest.mark.parametrize(
    "subjects",
    [
        pytest.param((BRANCH,), id="branch"),
        pytest.param((DEV, PROD, BRANCH), id="environments-and-branch"),
    ],
)
def test_read_access_keeps_branch_and_multi_environment_subjects(
    subjects: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert bootstrap.main(with_subjects(subjects)) == 0
    assert json.loads(capsys.readouterr().out)["oidc"]["subjects"] == list(subjects)


def test_ado_deploy_subjects_are_service_connections_not_environments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert bootstrap.main(ado_arguments("--access", "deploy")) == 0
    assert json.loads(capsys.readouterr().out)["access"] == "deploy"


def test_github_emit_notes_admin_bypass_and_self_review(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The printed PUT cannot clear admin bypass; the deploy gate fails without it."""
    no_processes(monkeypatch)
    assert bootstrap.main(arguments("--access", "deploy", "--emit", "github")) == 0
    notes = " ".join(json.loads(capsys.readouterr().out)["emit"]["notes"])
    assert "prevent_self_review=true" in notes
    assert "Allow administrators to bypass configured protection rules" in notes
