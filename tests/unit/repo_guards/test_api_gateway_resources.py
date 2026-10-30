"""kit-api-gateway resources: policy checker, template syntax, and consistency."""

from collections.abc import Callable
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SKILL = _ROOT / "packages/iac/.apm/skills/kit-api-gateway"
_ASSETS = _SKILL / "assets"
_CHECKER = _ASSETS / "check_apim_policy.py"
_INSTRUCTION = (
    _ROOT / "packages/iac/.apm/instructions/kit-api-management.instructions.md"
)
_TERRAFORM_TEMPLATES = sorted(_ASSETS.rglob("*.tf.template"))
_PINNED_PROVIDER = re.compile(r'version\s*=\s*"~> \d+\.\d+"')
_HCL_TOKEN = re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|[{}\[\]()]')
_PAIRS = {"}": "{", "]": "[", ")": "("}
_NAMED_VALUE = re.compile(r"\{\{([^}]+)\}\}")
_BICEP_PARAM = re.compile(r"^param (\w+) (\w+)( = .+)?$", re.MULTILINE)
_BICEPPARAM_VALUE = re.compile(r"^param (\w+) = ", re.MULTILINE)
_NAMED_VALUE_RESOURCE = re.compile(
    r"namedValues@[\d-]+' = (?:if \(.*?\) )?\{\s*parent: service\s*name: '([^']+)'"
)

_CLEAN = """<policies>
  <inbound>
    <base />
    <validate-jwt header-name="Authorization">
      <openid-config url="{{jwt-openid-config-url}}" />
      <audiences><audience>{{orders-api-audience}}</audience></audiences>
    </validate-jwt>
    <rate-limit-by-key calls="10" renewal-period="60"
      counter-key="@(context.Subscription.Id)" />
    <quota-by-key calls="1000" renewal-period="86400"
      counter-key="@(context.Subscription.Id)" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
"""
_RISKY = """<policies>
  <inbound>
    <cors><allowed-origins><origin>*</origin></allowed-origins></cors>
    <set-header name="Ocp-Apim-Subscription-Key" exists-action="override">
      <value>0123456789abcdef0123456789abcdef</value>
    </set-header>
    <!-- pragma: allowlist secret --><authentication-basic username="svc" password="hunter2-literal" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error>
    <base />
    <return-response><set-body>failed</set-body></return-response>
  </on-error>
</policies>
"""


def _main() -> Callable[[list[str]], int]:
    main = runpy.run_path(str(_CHECKER))["main"]
    assert callable(main)

    def invoke(arguments: list[str]) -> int:
        result = main(arguments)
        assert isinstance(result, int)
        return result

    return invoke


def _write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def test_self_test_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert _main()(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


def test_clean_policy_passes_strict_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "orders-api.xml", _CLEAN)
    assert _main()(["--require-auth", "--require-quota", str(path)]) == 0
    assert "No findings in 1 file(s)." in capsys.readouterr().out


def test_risky_policy_reports_rules_with_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "orders-api.xml", _RISKY)
    assert _main()(["--require-auth", "--require-quota", str(path)]) == 1
    lines = capsys.readouterr().out.splitlines()
    prefix = path.as_posix()
    found = {
        (line.split(": ", 1)[0], line.split("[", 1)[1].split("]")[0]) for line in lines
    }
    assert {
        (f"{prefix}:2", "missing-base"),
        (f"{prefix}:2", "missing-rate-limit"),
        (f"{prefix}:2", "missing-quota"),
        (f"{prefix}:2", "missing-auth"),
        (f"{prefix}:3", "cors-wildcard"),
        (f"{prefix}:5", "inline-secret"),
        (f"{prefix}:7", "inline-secret"),
        (f"{prefix}:11", "on-error-status"),
        (f"{prefix}:13", "on-error-status"),
    } <= found
    assert all(line.startswith(f"{prefix}:") for line in lines)


def test_disable_and_fragments_relax_only_named_rules(tmp_path: Path) -> None:
    text = _CLEAN.replace(
        '<rate-limit-by-key calls="10" renewal-period="60"\n'
        '      counter-key="@(context.Subscription.Id)" />\n'
        '    <quota-by-key calls="1000" renewal-period="86400"\n'
        '      counter-key="@(context.Subscription.Id)" />',
        '<include-fragment fragment-id="consumer-limits" />',
    )
    path = _write(tmp_path, "orders-api.xml", text)
    assert _main()(["--require-quota", str(path)]) == 1
    assert (
        _main()(["--require-quota", "--limit-fragment", "consumer-limits", str(path)])
        == 0
    )
    assert (
        _main()(
            [
                "--require-quota",
                "--disable",
                "missing-rate-limit",
                "--disable",
                "missing-quota",
                str(path),
            ]
        )
        == 0
    )


def test_scope_comes_from_file_name_or_flag(tmp_path: Path) -> None:
    minimal = "<policies><inbound /><outbound /></policies>"
    global_path = _write(tmp_path, "global.xml", minimal)
    operation_path = _write(tmp_path, "get-order-operation.xml", minimal)
    assert _main()([str(global_path)]) == 1
    assert _main()(["--disable", "missing-base", str(operation_path)]) == 0
    assert _main()(["--scope", "api", str(operation_path)]) == 1


@pytest.mark.parametrize(
    "text",
    [
        "<policies><inbound>",
        "<!DOCTYPE policies [<!ENTITY x 'y'>]><policies />",
        "<configuration />",
    ],
)
def test_invalid_input_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    path = _write(tmp_path, "bad-api.xml", text)
    assert _main()([str(path)]) == 2
    assert "Cannot check policies" in capsys.readouterr().err


def test_missing_path_exits_two(tmp_path: Path) -> None:
    assert _main()([str(tmp_path / "absent")]) == 2


def test_policy_templates_pass_the_strict_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder = _ASSETS / "policies"
    assert len(list(folder.glob("*.xml.template"))) == 3
    assert _main()(["--require-auth", "--require-quota", str(folder)]) == 0
    assert "No findings in 3 file(s)." in capsys.readouterr().out


def test_named_values_in_policies_are_created_by_bicep() -> None:
    bicep = (_ASSETS / "bicep/apim.bicep.template").read_text(encoding="utf-8")
    bicep += (_ASSETS / "bicep/api.bicep.template").read_text(encoding="utf-8")
    created = {
        name.replace("${apiName}", "orders")
        for name in _NAMED_VALUE_RESOURCE.findall(bicep)
    }
    used: set[str] = set()
    for name in ("global.xml.template", "api.xml.template"):
        text = (_ASSETS / "policies" / name).read_text(encoding="utf-8")
        used |= set(_NAMED_VALUE.findall(re.sub(r"(?s)<!--.*?-->", "", text)))
    assert used
    assert used <= created


def test_bicepparam_matches_main_parameters() -> None:
    main = (_ASSETS / "bicep/main.bicep.template").read_text(encoding="utf-8")
    params = (_ASSETS / "bicep/main.bicepparam.template").read_text(encoding="utf-8")
    declared = {name: default for name, _, default in _BICEP_PARAM.findall(main)}
    assigned = set(_BICEPPARAM_VALUE.findall(params))
    assert "using '../main.bicep'" in params
    assert assigned <= set(declared)
    assert {name for name, default in declared.items() if not default} <= assigned


def test_bicep_loads_files_from_documented_layout() -> None:
    main = (_ASSETS / "bicep/main.bicep.template").read_text(encoding="utf-8")
    apim = (_ASSETS / "bicep/apim.bicep.template").read_text(encoding="utf-8")
    assert "module apim 'modules/apim.bicep'" in main
    assert "module ordersV1 'modules/api.bicep'" in main
    assert "loadTextContent('policies/orders-api.xml')" in main
    assert "loadTextContent('openapi/orders.v1.json')" in main
    assert "loadTextContent('../policies/global.xml')" in apim
    assert "identityClientId: 'SystemAssigned'" in apim


@pytest.mark.parametrize(
    "path",
    sorted(_ASSETS.rglob("*.y*ml.template")),
    ids=lambda path: path.name,
)
def test_yaml_templates_parse(path: Path) -> None:
    assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _sequence(value: object) -> list[object]:
    assert isinstance(value, list)
    return value


def test_gateway_api_templates_are_consistent() -> None:
    def load(name: str) -> dict[str, object]:
        data = yaml.safe_load((_ASSETS / "k8s" / name).read_text(encoding="utf-8"))
        return _mapping(data)

    gateway = load("api-gateway.yaml.template")
    route = load("api-httproute.yaml.template")
    policy = load("security-policy.yaml.template")
    assert (
        gateway["apiVersion"] == route["apiVersion"] == "gateway.networking.k8s.io/v1"
    )
    gateway_spec = _mapping(gateway["spec"])
    gateway_meta = _mapping(gateway["metadata"])
    route_spec = _mapping(route["spec"])
    listeners = {
        _mapping(item)["name"] for item in _sequence(gateway_spec["listeners"])
    }
    parent = _mapping(_sequence(route_spec["parentRefs"])[0])
    assert parent["name"] == gateway_meta["name"]
    assert parent["namespace"] == gateway_meta["namespace"]
    assert parent["sectionName"] in listeners
    rule = _mapping(_sequence(route_spec["rules"])[0])
    timeouts = _mapping(rule["timeouts"])
    assert int(str(timeouts["backendRequest"]).rstrip("s")) <= int(
        str(timeouts["request"]).rstrip("s")
    )
    cors = _mapping(_mapping(_sequence(rule["filters"])[2])["cors"])
    assert "*" not in _sequence(cors["allowOrigins"])
    target = _mapping(_sequence(_mapping(policy["spec"])["targetRefs"])[0])
    assert (target["kind"], target["name"]) == (
        "HTTPRoute",
        _mapping(route["metadata"])["name"],
    )


def test_workflow_template_uses_oidc_and_placeholders() -> None:
    text = (_ASSETS / "github/apiops.yml.template").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert workflow["permissions"] == {"contents": "read"}
    deploy = workflow["jobs"]["deploy-prod"]
    assert deploy["environment"] == "prod"
    assert deploy["permissions"]["id-token"] == "write"
    assert workflow["jobs"]["preview-prod"]["needs"] == "deploy-dev"
    assert "PIN_FULL_COMMIT_SHA" in text
    assert "check_apim_policy.py --require-auth" in text


def test_skill_description_and_references_are_dated() -> None:
    skill = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    description = re.search(r"^description: (.+)$", skill, re.MULTILINE)
    assert description
    assert description[1].startswith("Use when")
    assert len(description[1]) <= 110
    assert len(skill.split("---", 2)[2].splitlines()) <= 300
    for reference in sorted((_SKILL / "references").glob("*.md")):
        text = reference.read_text(encoding="utf-8")
        assert "## Sources" in text, reference.name
        assert "as of 2026-10" in text, reference.name


def test_instruction_is_narrow_and_names_the_skill() -> None:
    text = _INSTRUCTION.read_text(encoding="utf-8")
    lines = text.splitlines()
    scope = re.search(r'^applyTo: "([^"]+)"$', text, re.MULTILINE)
    assert len(lines) <= 20
    assert scope
    assert "**" not in scope[1].split(",")
    assert "`kit-api-gateway`" in lines[-1]
    assert _INSTRUCTION.name.removesuffix(".instructions.md") != _SKILL.name


def test_files_are_lf_utf8_without_bom() -> None:
    paths = [
        *sorted(path for path in _SKILL.rglob("*") if path.is_file()),
        _INSTRUCTION,
    ]
    for path in paths:
        if "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), path.name
        assert b"\r\n" not in data, path.name
        assert data.endswith(b"\n"), path.name
        data.decode("utf-8")


def _unbalanced(text: str) -> list[str]:
    """Return bracket problems outside strings and comments."""
    stack: list[str] = []
    problems: list[str] = []
    for token in _HCL_TOKEN.findall(text):
        if token in _PAIRS.values():
            stack.append(token)
        elif token in _PAIRS and (not stack or stack.pop() != _PAIRS[token]):
            problems.append(f"unexpected {token}")
    problems.extend(f"unclosed {opener}" for opener in stack)
    return problems


@pytest.mark.parametrize("path", _TERRAFORM_TEMPLATES, ids=lambda path: path.name)
def test_terraform_templates_pin_providers_and_balance(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "terraform {" in text
    assert "required_providers {" in text
    assert _PINNED_PROVIDER.search(text)
    assert _unbalanced(text) == []


def test_terraform_templates_are_canonically_formatted(tmp_path: Path) -> None:
    terraform = shutil.which("terraform")
    if terraform is None:
        pytest.skip("terraform is not installed")
    for path in _TERRAFORM_TEMPLATES:
        target = tmp_path / path.parent.name / "main.tf"
        target.parent.mkdir()
        target.write_bytes(path.read_bytes())
    result = subprocess.run(  # noqa: S603 - resolved terraform binary, copied templates
        [terraform, f"-chdir={tmp_path}", "fmt", "-check", "-recursive"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={**os.environ, "CHECKPOINT_DISABLE": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_aws_template_uses_jwt_throttling_and_access_logs() -> None:
    text = (_ASSETS / "aws/api-gateway-http.tf.template").read_text(encoding="utf-8")
    assert 'protocol_type = "HTTP"' in text
    assert 'authorizer_type  = "JWT"' in text
    assert 'authorization_type   = "JWT"' in text
    assert "default_route_settings {" in text
    assert "access_log_settings {" in text
    assert '"*"' not in text


def test_gcp_template_builds_gateway_from_openapi() -> None:
    text = (_ASSETS / "gcp/api-gateway.tf.template").read_text(encoding="utf-8")
    assert 'source  = "hashicorp/google-beta"' in text
    assert (
        text.count("provider     = google-beta")
        + text.count("provider             = google-beta")
        == 3
    )
    assert "filebase64(var.openapi_path)" in text
    assert "create_before_destroy = true" in text
