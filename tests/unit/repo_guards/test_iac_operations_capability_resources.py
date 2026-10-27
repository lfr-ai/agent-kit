"""Edge, remote-access, observability, and infra-review assets behave as documented."""

from collections.abc import Callable
import json
from pathlib import Path
import re
import runpy
import shutil

import pytest
from scripts.check_resources import _reachable
import yaml

_SKILLS = Path(__file__).resolve().parents[3] / "packages/iac/.apm/skills"
_INSTRUCTIONS = _SKILLS.parent / "instructions"
_EDGE = _SKILLS / "kit-edge-networking"
_REMOTE = _SKILLS.parents[2] / "remote-access/.apm/skills/kit-remote-access"
_OBSERVABILITY = _SKILLS / "kit-observability/assets/templates"
_INFRA = _SKILLS / "kit-infra-review"
_NGINX_CHECKER = _EDGE / "assets/check_nginx_config.py"
_SSHD_CHECKER = _REMOTE / "assets/check_sshd_config.py"
_NEW_SKILLS = (_EDGE, _REMOTE)
_EXTENDED_SKILLS = (_SKILLS / "kit-observability", _INFRA)


def _main(script: Path) -> Callable[[list[str]], int]:
    main = runpy.run_path(str(script))["main"]
    assert callable(main)

    def invoke(arguments: list[str]) -> int:
        result = main(arguments)
        assert isinstance(result, int)
        return result

    return invoke


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    loaded = yaml.safe_load(match.group(1))
    assert isinstance(loaded, dict)
    return loaded


# Skill and instruction structure


@pytest.mark.parametrize("skill", _NEW_SKILLS, ids=lambda path: path.name)
def test_new_skill_metadata_is_minimal(skill: Path) -> None:
    metadata = _frontmatter(skill / "SKILL.md")
    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == skill.name
    assert metadata["license"] == "MIT"
    description = metadata["description"]
    assert isinstance(description, str)
    assert description.startswith("Use when")
    assert len(description) <= 350
    body = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "## Acceptance gates" in body
    assert len(body.splitlines()) < 300


@pytest.mark.parametrize(
    "skill", [*_NEW_SKILLS, *_EXTENDED_SKILLS], ids=lambda path: path.name
)
def test_every_resource_is_linked(skill: Path) -> None:
    reached = _reachable(skill / "SKILL.md")
    resources = [
        path.resolve()
        for folder in ("references", "assets")
        for path in (skill / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    assert resources
    assert [path for path in resources if path not in reached] == []


@pytest.mark.parametrize("skill", _NEW_SKILLS, ids=lambda path: path.name)
def test_references_cite_primary_sources_with_review_date(skill: Path) -> None:
    for reference in (skill / "references").glob("*.md"):
        text = reference.read_text(encoding="utf-8")
        assert "## Primary sources" in text, reference.name
        assert "2026-10-23" in text, reference.name
        assert re.search(r"<https://[^>]+>", text), reference.name


def test_edge_instruction_is_narrow_and_short() -> None:
    path = _INSTRUCTIONS / "kit-edge-networking.instructions.md"
    metadata = _frontmatter(path)
    assert set(metadata) == {"description", "applyTo"}
    apply_to = metadata["applyTo"]
    assert isinstance(apply_to, str)
    assert "**/*.conf" not in apply_to.split(",")
    bullets = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("- ")
    ]
    assert 4 <= len(bullets) <= 10


# check_nginx_config.py

_PROXY_HEADERS = (
    "proxy_set_header Host $host;\nproxy_set_header X-Forwarded-Proto $scheme;\n"
)


def _nginx(server_body: str, *, http_extra: str = "") -> str:
    return (
        "events {}\n"
        "http {\n"
        "server_tokens off;\n"
        f"{http_extra}"
        "server {\n"
        "listen 443 ssl;\n"
        "client_max_body_size 10m;\n"
        f"{server_body}"
        "}\n"
        "}\n"
    )


def test_nginx_template_is_clean(tmp_path: Path) -> None:
    target = tmp_path / "nginx.conf"
    shutil.copyfile(_EDGE / "assets/nginx.conf.template", target)
    assert _main(_NGINX_CHECKER)([str(target)]) == 0


def test_nginx_clean_config_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _nginx(
        _PROXY_HEADERS
        + "ssl_protocols TLSv1.2 TLSv1.3;\n"
        + "location / { proxy_pass http://app; }\n"
        + "location /api/stream { proxy_pass http://app; proxy_buffering off; }\n"
    )
    path = _write(tmp_path, "site.conf", text)
    assert _main(_NGINX_CHECKER)([str(path)]) == 0
    assert "No findings in 1 file(s)." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        (
            _nginx("ssl_protocols TLSv1 TLSv1.1 TLSv1.2;\n"),
            7,
            "ssl_protocols enables TLSv1, TLSv1.1",
        ),
        (
            _nginx("server_tokens on;\n"),
            7,
            "server_tokens on discloses the nginx version",
        ),
        (
            "http {\nserver { listen 80; }\n}\n",
            1,
            "http block does not set 'server_tokens off'",
        ),
        (
            _nginx("location / {\nproxy_pass http://app;\n}\n"),
            7,
            "location '/' proxies without 'proxy_set_header X-Forwarded-Proto'",
        ),
        (
            _nginx(
                _PROXY_HEADERS
                + "location /ws/ {\nproxy_pass http://app;\n"
                + "proxy_set_header Upgrade $http_upgrade;\n}\n"
            ),
            9,
            "its own proxy_set_header list replaces the inherited one",
        ),
        (
            "http {\nserver_tokens off;\nserver {\n"
            + _PROXY_HEADERS
            + "location / { proxy_pass http://app; }\n}\n}\n",
            3,
            "proxying server has no 'client_max_body_size'",
        ),
        (
            _nginx(_PROXY_HEADERS + "location /events/ { proxy_pass http://app; }\n"),
            9,
            (
                "streaming location '/events/' needs 'proxy_buffering off' "
                "(effective value is 'on')"
            ),
        ),
        (
            _nginx(
                _PROXY_HEADERS
                + "location /feed {\n# edge:stream\nproxy_pass http://app;\n"
                + "proxy_buffering on;\n}\n"
            ),
            12,
            "streaming location '/feed' needs 'proxy_buffering off'",
        ),
    ],
    ids=[
        "legacy-tls",
        "server-tokens-on",
        "server-tokens-default",
        "missing-forwarded-proto",
        "location-replaces-inherited-headers",
        "missing-body-limit",
        "stream-path-default-buffering",
        "stream-marker-explicit-buffering",
    ],
)
def test_nginx_risky_config_reports_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
    line: int,
    message: str,
) -> None:
    path = _write(tmp_path, "site.conf", text)
    assert _main(_NGINX_CHECKER)([str(path)]) == 1
    output = capsys.readouterr().out.splitlines()
    assert any(
        entry.startswith(f"{path.as_posix()}:{line}: ") and message in entry
        for entry in output
    ), output


def test_nginx_inherited_buffering_off_and_stream_context_pass(
    tmp_path: Path,
) -> None:
    text = "stream {\nserver { listen 5432; proxy_pass db:5432; }\n}\n" + _nginx(
        _PROXY_HEADERS
        + "proxy_buffering off;\n"
        + "location /sse/ { proxy_pass http://app; }\n"
    )
    path = _write(tmp_path, "nginx.conf", text)
    assert _main(_NGINX_CHECKER)([str(path)]) == 0


def test_nginx_directory_scan_selects_conf_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "good.conf", _nginx(""))
    _write(tmp_path, "notes.txt", "server_tokens on;\n")
    _write(tmp_path, "bad.conf.template", _nginx("server_tokens build;\n"))
    assert _main(_NGINX_CHECKER)([str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out.count("server_tokens build") == 1
    assert "1 finding(s) in 2 file(s)" in captured.err


@pytest.mark.parametrize(
    "text",
    [
        "http {\nserver {\n",
        "http { }\n}\n",
        "http { server_tokens off }\n",
        'http { log_format x "unterminated; }\n',
    ],
    ids=["unclosed-block", "extra-brace", "missing-semicolon", "open-quote"],
)
def test_nginx_malformed_input_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    path = _write(tmp_path, "broken.conf", text)
    assert _main(_NGINX_CHECKER)([str(path)]) == 2
    assert "Cannot check" in capsys.readouterr().err


def test_nginx_missing_path_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(_NGINX_CHECKER)([str(tmp_path / "absent.conf")]) == 2
    assert "path does not exist" in capsys.readouterr().err


# Edge templates


def test_traefik_template_separates_streaming_route() -> None:
    loaded = yaml.safe_load(
        (_EDGE / "assets/traefik-dynamic.yaml.template").read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    routers = loaded["http"]["routers"]
    middlewares = loaded["http"]["middlewares"]
    services = loaded["http"]["services"]
    assert "buffering" in middlewares["body-limit"]
    assert "body-limit" in routers["app"]["middlewares"]
    assert "body-limit" not in routers["app-events"]["middlewares"]
    assert services["app"]["loadBalancer"]["healthCheck"]["path"] == "/readyz"
    streaming = services["app-streaming"]["loadBalancer"]
    assert streaming["responseForwarding"]["flushInterval"] == "-1"
    assert loaded["tls"]["options"]["default"]["minVersion"] == "VersionTLS12"
    for router in routers.values():
        assert router["tls"]["certResolver"] == "acme"


def test_caddyfile_template_is_balanced_and_hardened() -> None:
    text = (_EDGE / "assets/Caddyfile.template").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert code.count("{") == code.count("}")
    for expected in (
        "trusted_proxies static",
        "protocols tls1.2 tls1.3",
        "max_size 10MB",
        "flush_interval -1",
        "health_uri /readyz",
        "-Server",
    ):
        assert expected in code


# check_sshd_config.py


def test_sshd_template_passes_with_baseline(tmp_path: Path) -> None:
    target = tmp_path / "10-hardening.conf"
    shutil.copyfile(_REMOTE / "assets/sshd-hardening.conf.template", target)
    assert _main(_SSHD_CHECKER)(["--require-baseline", str(target)]) == 0


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        ("PasswordAuthentication yes\n", 1, "password login enabled"),
        ("KbdInteractiveAuthentication=yes\n", 1, "keyboard-interactive"),
        ("PermitRootLogin prohibit-password\n", 1, "allows root login"),
        ("PermitEmptyPasswords yes\n", 1, "empty passwords"),
        ("AllowAgentForwarding yes\n", 1, "use ProxyJump"),
        ("X11Forwarding yes\n", 1, "X11 forwarding"),
        ("LogLevel QUIET\n", 1, "use VERBOSE"),
        ("Ciphers aes256-gcm@openssh.com,aes128-cbc\n", 1, "aes128-cbc"),
        ("MACs +hmac-sha1\n", 1, "hmac-sha1"),
        ("KexAlgorithms diffie-hellman-group14-sha1\n", 1, "group14-sha1"),
        ("PubkeyAcceptedAlgorithms +ssh-rsa\n", 1, "ssh-rsa"),
        (
            (
                "PermitRootLogin no\nMatch Address 10.0.0.0/8\n"
                "  PasswordAuthentication yes\n"
            ),
            3,
            "(in Match block at line 2)",
        ),
        (
            "PasswordAuthentication no\nPasswordAuthentication yes\n",
            2,
            "is ignored; sshd uses the first value 'no' from line 1",
        ),
    ],
    ids=[
        "password",
        "kbd-interactive",
        "root-by-key",
        "empty-password",
        "agent-forwarding",
        "x11",
        "quiet-log",
        "cbc-cipher",
        "sha1-mac-append",
        "sha1-kex",
        "ssh-rsa-signature",
        "match-scope",
        "ignored-duplicate",
    ],
)
def test_sshd_insecure_directive_reports_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
    line: int,
    message: str,
) -> None:
    path = _write(tmp_path, "sshd_config", text)
    assert _main(_SSHD_CHECKER)([str(path)]) == 1
    output = capsys.readouterr().out.splitlines()
    assert any(
        entry.startswith(f"{path.as_posix()}:{line}: ") and message in entry
        for entry in output
    ), output


def test_sshd_secure_values_and_removals_pass(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "sshd_config",
        "# comment\n"
        "PasswordAuthentication no\n"
        "PermitRootLogin no\n"
        "Ciphers -aes128-cbc\n"
        "HostKey /etc/ssh/ssh_host_ed25519_key\n"
        "HostKey /etc/ssh/ssh_host_ecdsa_key\n"
        "LogLevel VERBOSE\n",
    )
    assert _main(_SSHD_CHECKER)([str(path)]) == 0


def test_sshd_baseline_reports_missing_directives(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "10-partial.conf", "PasswordAuthentication no\n")
    assert _main(_SSHD_CHECKER)([str(path)]) == 0
    assert _main(_SSHD_CHECKER)(["--require-baseline", str(path)]) == 1
    output = capsys.readouterr().out
    assert "baseline requires 'KbdInteractiveAuthentication no'" in output
    assert "baseline requires 'PermitRootLogin no'" in output
    assert "baseline requires 'AllowUsers' or 'AllowGroups'" in output
    assert "baseline requires 'PasswordAuthentication no'" not in output


def test_sshd_directory_scan_reads_drop_ins(tmp_path: Path) -> None:
    _write(tmp_path, "10-good.conf", "PermitRootLogin no\n")
    _write(tmp_path, "50-cloud.conf", "PasswordAuthentication yes\n")
    _write(tmp_path, "README", "PasswordAuthentication yes\n")
    assert _main(_SSHD_CHECKER)([str(tmp_path)]) == 1


@pytest.mark.parametrize(
    "arguments",
    [["absent_config"], ["broken_config"]],
    ids=["missing-path", "keyword-without-value"],
)
def test_sshd_invalid_input_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], arguments: list[str]
) -> None:
    _write(tmp_path, "broken_config", "PasswordAuthentication\n")
    paths = [str(tmp_path / argument) for argument in arguments]
    assert _main(_SSHD_CHECKER)(paths) == 2
    assert "Cannot check" in capsys.readouterr().err


def test_ssh_client_template_keeps_safe_defaults_last() -> None:
    text = (_REMOTE / "assets/ssh_config.template").read_text(encoding="utf-8")
    hosts = re.findall(r"(?m)^Host (.+)$", text)
    assert hosts[-1] == "*"
    defaults = text.split("\nHost *\n", 1)[1]
    for expected in (
        "ForwardAgent no",
        "StrictHostKeyChecking yes",
        "PasswordAuthentication no",
    ):
        assert expected in defaults
    assert "ProxyJump bastion" in text
    assert "StrictHostKeyChecking no" not in text
    assert "/dev/null" not in text


# Observability templates


def _yaml(name: str) -> dict[str, object]:
    loaded = yaml.safe_load((_OBSERVABILITY / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _datasource_refs(node: object) -> list[object]:
    if isinstance(node, dict):
        found = [node["datasource"]] if "datasource" in node else []
        return found + [
            ref for value in node.values() for ref in _datasource_refs(value)
        ]
    if isinstance(node, list):
        return [ref for item in node for ref in _datasource_refs(item)]
    return []


def test_grafana_dashboard_uses_datasource_variable_only() -> None:
    dashboard = json.loads(
        (_OBSERVABILITY / "grafana-dashboard.json.template").read_text(encoding="utf-8")
    )
    assert dashboard["id"] is None
    assert dashboard["uid"] is None
    variables = {item["name"]: item for item in dashboard["templating"]["list"]}
    assert variables["datasource"]["type"] == "datasource"
    assert variables["datasource"]["query"] == "prometheus"
    refs = _datasource_refs(dashboard)
    assert refs
    assert all(ref == {"type": "prometheus", "uid": "${datasource}"} for ref in refs)
    assert [panel["id"] for panel in dashboard["panels"]] == [1, 2, 3, 4]


def test_grafana_provisioning_has_no_fixed_uids() -> None:
    datasources = _yaml("grafana-datasources.yaml.template")
    providers = _yaml("grafana-dashboards.yaml.template")
    assert datasources["apiVersion"] == 1
    assert providers["apiVersion"] == 1
    entries = datasources["datasources"]
    assert isinstance(entries, list)
    assert all("uid" not in entry for entry in entries)
    provider_list = providers["providers"]
    assert isinstance(provider_list, list)
    assert provider_list[0]["allowUiUpdates"] is False


def test_red_use_rules_are_named_and_routed() -> None:
    groups = _yaml("red-use-rules.yaml.template")["groups"]
    assert isinstance(groups, list)
    rules = [rule for group in groups for rule in group["rules"]]
    records = [rule["record"] for rule in rules if "record" in rule]
    alerts = [rule for rule in rules if "alert" in rule]
    assert records
    assert all(re.fullmatch(r"[a-z_]+:[a-z_]+:[a-z0-9_]+", name) for name in records)
    assert alerts
    for alert in alerts:
        assert alert["labels"]["severity"] in {"page", "ticket"}
        assert alert["annotations"]["runbook_url"].startswith("https://")
        assert "for" in alert


def _merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge(current, value)
        else:
            merged[key] = value
    return merged


def test_collector_local_override_routes_to_defined_exporters() -> None:
    merged = _merge(
        _yaml("otel-collector.yaml.template"),
        _yaml("otel-collector.local.yaml.template"),
    )
    exporters = merged["exporters"]
    service = merged["service"]
    assert isinstance(exporters, dict)
    assert isinstance(service, dict)
    for name, pipeline in service["pipelines"].items():
        assert set(pipeline["exporters"]) <= set(exporters), name
        assert pipeline["processors"][0] == "memory_limiter", name
        assert pipeline["processors"][-1] == "batch", name
    metrics_exporters = service["pipelines"]["metrics"]["exporters"]
    assert metrics_exporters == ["otlphttp/prometheus"]


def test_observability_compose_pins_images_and_binds_locally() -> None:
    compose = _yaml("observability-compose.yaml.template")
    services = compose["services"]
    assert isinstance(services, dict)
    assert set(services) == {"otel-collector", "prometheus", "grafana"}
    for name, service in services.items():
        assert service["image"].endswith("@sha256:PIN_IMAGE_DIGEST"), name
        assert all(port.startswith("127.0.0.1:") for port in service["ports"]), name
        assert service["cap_drop"] == ["ALL"], name
    assert "--web.enable-otlp-receiver" in services["prometheus"]["command"]
    prometheus = _yaml("prometheus.yaml.template")
    assert prometheus["rule_files"] == ["/etc/prometheus/rules/*.yaml"]
    otlp = prometheus["otlp"]
    assert isinstance(otlp, dict)
    assert "promote_resource_attributes" in otlp


# Infra review


def test_infra_reviewer_role_is_readonly_worker() -> None:
    document = json.loads((_INFRA / "assets/agents.json").read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    (role,) = document["roles"]
    assert set(role) == {"id", "kind", "tier", "description", "body", "workers"}
    assert role["id"] == "kit-infra-reviewer"
    assert role["kind"] == "worker"
    assert role["tier"] == "readonly"
    assert role["workers"] == []
    assert len(role["description"]) <= 180
    assert len(role["body"].splitlines()) <= 125
    assert "delegate" in role["body"]


def test_change_type_worksheet_covers_each_change_type() -> None:
    text = (_INFRA / "assets/templates/change-type-worksheets.md.template").read_text(
        encoding="utf-8"
    )
    headings = re.findall(r"(?m)^## (.+)$", text)
    assert headings == [
        "Network and edge",
        "Identity and access",
        "Data-bearing resources",
        "Compute and scaling",
        "Pipeline and supply chain",
        "Observability and alerting",
        "Cost and drift summary",
    ]
    assert text.count("- [ ] Rollback") >= 5


@pytest.mark.parametrize(
    "script", [_NGINX_CHECKER, _SSHD_CHECKER], ids=lambda path: path.stem
)
def test_checker_self_test_passes_without_paths(
    script: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(script)(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "script", [_NGINX_CHECKER, _SSHD_CHECKER], ids=lambda path: path.stem
)
def test_checker_requires_paths_without_self_test(script: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        _main(script)([])
    assert caught.value.code == 2
