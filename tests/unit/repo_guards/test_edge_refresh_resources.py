"""Edge networking load balancing, ingress, caching, and checker rules behave as documented."""

from collections.abc import Callable
from pathlib import Path
import re
import runpy
import shutil

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_EDGE = _ROOT / "packages/iac/.apm/skills/kit-edge-networking"
_ASSETS = _EDGE / "assets"
_CHECKER = _ASSETS / "check_nginx_config.py"
_INSTRUCTION = (
    _ROOT / "packages/iac/.apm/instructions/kit-edge-networking.instructions.md"
)
_NEW_REFERENCES = (
    "load-balancing.md",
    "kubernetes-ingress.md",
    "cdn-and-proxy-caching.md",
)
_DESCRIPTION = (
    "Use when configuring a reverse proxy, load balancer, CDN, TLS, forwarded "
    "headers, or streaming edge routes."
)
_HEADERS = "proxy_set_header Host $host;\nproxy_set_header X-Forwarded-Proto $scheme;\n"
_DURATION = re.compile(r"^(?P<value>\d+)(?P<unit>ms|s|m|h)$")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
_HSTS_FIRST_STAGE_SECONDS = 300


def _main() -> Callable[[list[str]], int]:
    main = runpy.run_path(str(_CHECKER))["main"]
    assert callable(main)

    def invoke(arguments: list[str]) -> int:
        result = main(arguments)
        assert isinstance(result, int)
        return result

    return invoke


def _write(root: Path, text: str) -> Path:
    path = root / "site.conf"
    path.write_text(text, encoding="utf-8")
    return path


def _config(*, http_extra: str = "", server_extra: str = "", location: str) -> str:
    return (
        "events {}\nhttp {\nserver_tokens off;\n"
        f"{http_extra}"
        "server {\nlisten 443 ssl;\nclient_max_body_size 10m;\n"
        f"{_HEADERS}{server_extra}{location}"
        "}\n}\n"
    )


def _findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> tuple[int, list[str]]:
    path = _write(tmp_path, text)
    status = _main()([str(path)])
    lines = capsys.readouterr().out.splitlines()
    prefix = f"{path.as_posix()}:"
    return status, [
        line.removeprefix(prefix) for line in lines if line.startswith(prefix)
    ]


def _seconds(value: str) -> float:
    match = _DURATION.match(value)
    assert match is not None, value
    return int(match["value"]) * _UNIT_SECONDS[match["unit"]]


def _documents(name: str) -> list[dict[str, object]]:
    text = (_ASSETS / name).read_text(encoding="utf-8")
    documents = [document for document in yaml.safe_load_all(text) if document]
    assert all(isinstance(document, dict) for document in documents)
    return documents


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _sequence(value: object) -> list[object]:
    assert isinstance(value, list)
    return value


# Skill structure


def test_skill_keeps_description_and_links_new_material() -> None:
    text = (_EDGE / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    metadata = _mapping(yaml.safe_load(match.group(1)))
    assert metadata["description"] == _DESCRIPTION
    assert len(text.splitlines()) <= 300
    for reference in _NEW_REFERENCES:
        assert f"](references/{reference})" in text
    for asset in (
        "assets/envoy.yaml.template",
        "assets/gateway-api/gateway.yaml.template",
        "assets/gateway-api/httproute.yaml.template",
    ):
        assert f"]({asset})" in text


@pytest.mark.parametrize("name", _NEW_REFERENCES)
def test_new_references_are_dated_and_name_owners(name: str) -> None:
    text = (_EDGE / "references" / name).read_text(encoding="utf-8")
    assert "2026-10-27" in text
    assert "as of 2026-10" in text
    assert "## Primary sources" in text
    links = re.findall(r"\]\(([^)]+)\)", text)
    assert all(not link.startswith(("../../", "/")) for link in links), links
    assert re.search(r"`kit-[a-z-]+`", text)


def test_instruction_stays_within_budget() -> None:
    text = _INSTRUCTION.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) <= 20
    scope = re.search(r'^applyTo:\s*"(?P<scope>[^"]*)"', text, re.MULTILINE)
    assert scope is not None
    globs = scope["scope"].split(",")
    assert "**" not in globs
    assert "**/*" not in globs
    bullets = [line for line in lines if line.startswith("- ")]
    assert 4 <= len(bullets) <= 10
    assert "`kit-edge-networking`" in bullets[-1]


# check_nginx_config.py: upstream keepalive


def test_upstream_without_keepalive_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _config(
        http_extra="upstream app {\nserver 10.0.0.1:8000;\n}\n",
        server_extra="proxy_http_version 1.1;\n",
        location="location / { proxy_pass http://app/api; }\n",
    )
    status, findings = _findings(tmp_path, capsys, text)
    assert status == 1
    assert len(findings) == 1
    assert findings[0].startswith("4: upstream 'app' has no 'keepalive'")
    assert "line 13 proxies to it with proxy_http_version 1.1" in findings[0]


@pytest.mark.parametrize(
    ("upstream", "version"),
    [
        ("upstream app {\nserver 10.0.0.1:8000;\nkeepalive 16;\n}\n", "1.1"),
        ("upstream app {\nserver 10.0.0.1:8000;\n}\n", "1.0"),
        ("upstream other {\nserver 10.0.0.1:8000;\n}\n", "1.1"),
    ],
    ids=["keepalive-set", "http-1.0", "upstream-not-referenced"],
)
def test_upstream_keepalive_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], upstream: str, version: str
) -> None:
    text = _config(
        http_extra=upstream,
        server_extra=f"proxy_http_version {version};\n",
        location="location / { proxy_pass http://app; }\n",
    )
    assert _findings(tmp_path, capsys, text) == (0, [])


def test_keepalive_zero_counts_as_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _config(
        http_extra="upstream app {\nserver 10.0.0.1:8000;\nkeepalive 0;\n}\n",
        server_extra="proxy_http_version 2;\n",
        location="location / { proxy_pass https://app; }\n",
    )
    status, findings = _findings(tmp_path, capsys, text)
    assert status == 1
    assert "proxy_http_version 2" in findings[0]


# check_nginx_config.py: caching of credential-bearing requests


@pytest.mark.parametrize(
    ("location", "signal"),
    [
        (
            "location /api/ {\nproxy_pass http://app;\nproxy_cache edge;\n"
            + _HEADERS
            + "proxy_set_header Authorization $http_authorization;\n}\n",
            "proxy_set_header authorization",
        ),
        (
            'location /admin/ {\nproxy_pass http://app;\nproxy_cache edge;\nauth_basic "x";\n}\n',
            "auth_basic",
        ),
        (
            (
                "location /me/ {\n# edge:authenticated\nproxy_pass http://app;\n"
                "proxy_cache edge;\nproxy_no_cache $http_authorization;\n}\n"
            ),
            "# edge:authenticated",
        ),
    ],
    ids=["authorization-header", "auth-basic", "marker-with-only-no-cache"],
)
def test_cached_credentials_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], location: str, signal: str
) -> None:
    status, findings = _findings(tmp_path, capsys, _config(location=location))
    assert status == 1
    assert len(findings) == 1
    assert findings[0].startswith("9: location ")
    assert "caches responses (proxy_cache edge)" in findings[0]
    assert signal in findings[0]
    assert "'proxy_cache_bypass'" in findings[0]


@pytest.mark.parametrize(
    "location",
    [
        "location /api/ {\nproxy_pass http://app;\nproxy_cache edge;\n"
        + _HEADERS
        + "proxy_set_header Authorization $http_authorization;\n"
        + "proxy_no_cache $http_authorization;\nproxy_cache_bypass $http_authorization;\n}\n",
        'location /admin/ {\nproxy_pass http://app;\nproxy_cache off;\nauth_basic "x";\n}\n',
        "location /admin/ {\nproxy_pass http://app;\nproxy_cache edge;\nauth_basic off;\n}\n",
        "location /assets/ {\nproxy_pass http://app;\nproxy_cache edge;\n}\n",
    ],
    ids=["skips-configured", "cache-off", "auth-basic-off", "public-route"],
)
def test_cache_without_credentials_or_with_skips_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], location: str
) -> None:
    assert _findings(tmp_path, capsys, _config(location=location)) == (0, [])


def test_inherited_cache_and_skips_are_resolved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    risky = _config(
        server_extra="proxy_cache edge;\n",
        location="location /a/ {\nproxy_pass http://app;\nauth_request /auth;\n}\n",
    )
    status, findings = _findings(tmp_path, capsys, risky)
    assert status == 1
    assert "auth_request" in findings[0]
    clean = _config(
        server_extra=(
            "proxy_cache edge;\nproxy_no_cache $http_authorization;\n"
            "proxy_cache_bypass $http_authorization;\n"
        ),
        location="location /a/ {\nproxy_pass http://app;\nauth_request /auth;\n}\n",
    )
    assert _findings(tmp_path, capsys, clean) == (0, [])


# check_nginx_config.py: unused limit zones


def test_unused_limit_zones_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _config(
        http_extra=(
            "limit_req_zone $binary_remote_addr zone=used:10m rate=5r/s;\n"
            "limit_req_zone $binary_remote_addr zone=idle:1m rate=1r/s;\n"
            "limit_conn_zone $binary_remote_addr zone=conns:1m;\n"
        ),
        location="location / {\nproxy_pass http://app;\nlimit_req zone=used burst=5;\n}\n",
    )
    status, findings = _findings(tmp_path, capsys, text)
    assert status == 1
    assert findings == [
        (
            "5: limit_req_zone zone 'idle' is not used by any 'limit_req' directive "
            "in this file; apply it or remove it"
        ),
        (
            "6: limit_conn_zone zone 'conns' is not used by any 'limit_conn' directive "
            "in this file; apply it or remove it"
        ),
    ]


@pytest.mark.parametrize(
    ("http_extra", "server_extra"),
    [
        (
            (
                "limit_req_zone $binary_remote_addr zone=per_client:10m rate=5r/s;\n"
                "limit_conn_zone $binary_remote_addr zone=conns:1m;\n"
            ),
            "limit_req zone=per_client;\nlimit_conn conns 10;\n",
        ),
        (
            (
                "include /etc/nginx/mime.types;\n"
                "limit_req_zone $binary_remote_addr zone=per_client:10m rate=5r/s;\n"
                "include /etc/nginx/conf.d/*.conf;\n"
            ),
            "",
        ),
    ],
    ids=["zones-used", "include-may-use-zone"],
)
def test_used_or_possibly_included_zones_pass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    http_extra: str,
    server_extra: str,
) -> None:
    text = _config(
        http_extra=http_extra,
        server_extra=server_extra,
        location="location / { proxy_pass http://app; }\n",
    )
    assert _findings(tmp_path, capsys, text) == (0, [])


def test_stream_context_zones_are_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "stream {\nlimit_conn_zone $binary_remote_addr zone=tcp:1m;\n"
        "upstream db { server 10.0.0.2:5432; }\n"
        "server { listen 5432; proxy_pass db; }\n}\n"
    ) + _config(location="location / { proxy_pass http://app; }\n")
    assert _findings(tmp_path, capsys, text) == (0, [])


def test_checker_self_test_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert _main()(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


# Templates


def test_nginx_template_balances_caches_and_passes_checker(tmp_path: Path) -> None:
    text = (_ASSETS / "nginx.conf.template").read_text(encoding="utf-8")
    for expected in (
        "least_conn;",
        "keepalive 32;",
        "max_fails=3 fail_timeout=10s",
        "proxy_cache_path ",
        "proxy_cache_lock on;",
        "proxy_cache_use_stale error timeout updating",
        "proxy_cache_background_update on;",
        "proxy_no_cache $http_authorization",
        "proxy_cache_bypass $http_authorization",
        "limit_conn conn_per_client",
        "proxy_next_upstream_tries 2;",
    ):
        assert expected in text, expected
    assert "non_idempotent" not in text.replace("non-idempotent", "")
    target = tmp_path / "nginx.conf"
    shutil.copyfile(_ASSETS / "nginx.conf.template", target)
    assert _main()([str(target)]) == 0


def test_envoy_template_parses_with_resilience_settings() -> None:
    documents = _documents("envoy.yaml.template")
    assert len(documents) == 1
    resources = _mapping(documents[0]["static_resources"])
    cluster = _mapping(_sequence(resources["clusters"])[0])
    assert cluster["lb_policy"] == "LEAST_REQUEST"
    least_request = _mapping(cluster["least_request_lb_config"])
    assert least_request["choice_count"] == 2
    assert "slow_start_window" in _mapping(least_request["slow_start_config"])
    outlier = _mapping(cluster["outlier_detection"])
    assert 0 < int(str(outlier["max_ejection_percent"])) <= 50
    threshold = _mapping(
        _sequence(_mapping(cluster["circuit_breakers"])["thresholds"])[0]
    )
    budget = _mapping(threshold["retry_budget"])
    assert float(str(_mapping(budget["budget_percent"])["value"])) <= 25.0
    health = _mapping(_sequence(cluster["health_checks"])[0])
    assert _mapping(health["http_health_check"])["path"] == "/readyz"
    admin = _mapping(_mapping(documents[0]["admin"])["address"])
    assert _mapping(admin["socket_address"])["address"] == "127.0.0.1"


def test_envoy_template_retries_only_safe_requests() -> None:
    text = (_ASSETS / "envoy.yaml.template").read_text(encoding="utf-8")
    routes = re.findall(r'retry_on: "([^"]+)"', text)
    assert routes == [
        "connect-failure,refused-stream,gateway-error",
        "connect-failure,refused-stream,reset-before-request",
    ]
    assert 'safe_regex: {regex: "GET|HEAD|OPTIONS"}' in text
    assert text.index("GET|HEAD|OPTIONS") < text.index("gateway-error")
    assert "5xx" not in routes[1]


_GATEWAY_FILES = (
    "cluster-issuer.yaml.template",
    "gateway.yaml.template",
    "httproute.yaml.template",
    "https-redirect.yaml.template",
    "grpcroute.yaml.template",
)


def _resource(name: str) -> dict[str, object]:
    loaded = yaml.safe_load(
        (_ASSETS / "gateway-api" / name).read_text(encoding="utf-8")
    )
    return _mapping(loaded)


def _listeners() -> dict[str, dict[str, object]]:
    spec = _mapping(_resource("gateway.yaml.template")["spec"])
    listeners = [_mapping(item) for item in _sequence(spec["listeners"])]
    return {str(listener["name"]): listener for listener in listeners}


@pytest.mark.parametrize("name", _GATEWAY_FILES)
def test_gateway_api_templates_are_single_resources(name: str) -> None:
    text = (_ASSETS / "gateway-api" / name).read_text(encoding="utf-8")
    assert len([doc for doc in yaml.safe_load_all(text) if doc]) == 1
    resource = _resource(name)
    assert resource["apiVersion"] in {
        "gateway.networking.k8s.io/v1",
        "cert-manager.io/v1",
    }
    assert re.search(r"^\s+retry:", text, re.MULTILINE) is None


def test_gateway_template_uses_cert_manager_and_scoped_routes() -> None:
    gateway = _resource("gateway.yaml.template")
    assert gateway["kind"] == "Gateway"
    annotations = _mapping(_mapping(gateway["metadata"])["annotations"])
    issuer = _resource("cluster-issuer.yaml.template")
    assert issuer["kind"] == "ClusterIssuer"
    assert (
        annotations["cert-manager.io/cluster-issuer"]
        == _mapping(issuer["metadata"])["name"]
    )
    for listener in _listeners().values():
        namespaces = _mapping(_mapping(listener["allowedRoutes"])["namespaces"])
        assert namespaces["from"] != "All"
        if listener["protocol"] == "HTTPS":
            tls = _mapping(listener["tls"])
            assert tls["mode"] == "Terminate"
            assert listener["hostname"]
            assert _sequence(tls["certificateRefs"])
    solver = _mapping(
        _sequence(_mapping(_mapping(issuer["spec"])["acme"])["solvers"])[0]
    )
    parent = _mapping(
        _sequence(
            _mapping(_mapping(solver["http01"])["gatewayHTTPRoute"])["parentRefs"]
        )[0]
    )
    assert parent["name"] == _mapping(gateway["metadata"])["name"]
    assert parent["sectionName"] == "http"


@pytest.mark.parametrize(
    ("name", "kind", "section"),
    [
        ("httproute.yaml.template", "HTTPRoute", "https"),
        ("https-redirect.yaml.template", "HTTPRoute", "http"),
        ("grpcroute.yaml.template", "GRPCRoute", "grpc"),
    ],
)
def test_routes_attach_to_matching_listeners(
    name: str, kind: str, section: str
) -> None:
    route = _resource(name)
    assert route["kind"] == kind
    spec = _mapping(route["spec"])
    parent = _mapping(_sequence(spec["parentRefs"])[0])
    assert parent["name"] == "shop-edge"
    assert parent["sectionName"] == section
    listener = _listeners()[section]
    if "hostname" in listener:
        assert listener["hostname"] in _sequence(spec["hostnames"])
    allowed = _sequence(
        _mapping(listener["allowedRoutes"]).get("kinds", [{"kind": kind}])
    )
    assert {"kind": kind} in allowed


def test_redirect_covers_every_https_hostname() -> None:
    spec = _mapping(_resource("https-redirect.yaml.template")["spec"])
    hostnames = set(_sequence(spec["hostnames"]))
    https = {
        listener["hostname"]
        for listener in _listeners().values()
        if listener["protocol"] == "HTTPS"
    }
    assert https <= hostnames
    rule = _mapping(_sequence(spec["rules"])[0])
    redirect = _mapping(_mapping(_sequence(rule["filters"])[0])["requestRedirect"])
    assert redirect == {"scheme": "https", "statusCode": 301}


def test_route_template_has_ordered_timeouts_and_canary_weights() -> None:
    spec = _mapping(_resource("httproute.yaml.template")["spec"])
    rules = [_mapping(rule) for rule in _sequence(spec["rules"])]
    for rule in rules:
        timeouts = _mapping(rule["timeouts"])
        request = _seconds(str(timeouts["request"]))
        if "backendRequest" in timeouts:
            assert 0 < _seconds(str(timeouts["backendRequest"])) <= request
    weights = [_mapping(ref)["weight"] for ref in _sequence(rules[-1]["backendRefs"])]
    assert weights == [90, 10]


def test_traefik_template_balances_and_limits_per_client() -> None:
    loaded = _documents("traefik-dynamic.yaml.template")[0]
    http = _mapping(loaded["http"])
    services = _mapping(http["services"])
    split = _mapping(_mapping(services["app-split"])["weighted"])
    assert split["healthCheck"] == {}
    names = [str(_mapping(service)["name"]) for service in _sequence(split["services"])]
    assert names == ["app", "app-canary"]
    for name in names:
        balancer = _mapping(_mapping(services[name])["loadBalancer"])
        assert _mapping(balancer["healthCheck"])["path"] == "/readyz"
    app = _mapping(_mapping(services["app"])["loadBalancer"])
    assert app["strategy"] == "p2c"
    assert set(_mapping(app["passiveHealthCheck"])) == {
        "failureWindow",
        "maxFailedAttempts",
    }
    middlewares = _mapping(http["middlewares"])
    for name, kind in (("rate-limit", "rateLimit"), ("in-flight", "inFlightReq")):
        settings = _mapping(_mapping(middlewares[name])[kind])
        assert "ipStrategy" in _mapping(settings["sourceCriterion"])
    retry = _mapping(_mapping(middlewares["retry"])["retry"])
    assert retry.get("retryNonIdempotentMethod", False) is False
    routers = _mapping(http["routers"])
    assert "retry" not in _sequence(_mapping(routers["app-events"])["middlewares"])
    transport = _mapping(_mapping(http["serversTransports"])["app-transport"])
    idle = _mapping(transport["forwardingTimeouts"])["idleConnTimeout"]
    assert _seconds(str(idle)) < 5


@pytest.mark.parametrize(
    ("template", "pattern"),
    [
        pytest.param(
            "nginx.conf.template",
            r'Strict-Transport-Security "max-age=(\d+)"',
            id="nginx",
        ),
        pytest.param(
            "Caddyfile.template",
            r'Strict-Transport-Security "max-age=(\d+)"',
            id="caddy",
        ),
        pytest.param(
            "traefik-dynamic.yaml.template", r"stsSeconds: (\d+)", id="traefik"
        ),
    ],
)
def test_templates_ship_the_first_hsts_stage(template: str, pattern: str) -> None:
    """A copied template must not pin browsers to HTTPS for years on day one."""
    text = (_ASSETS / template).read_text(encoding="utf-8")
    values = re.findall(pattern, text)

    assert values == [str(_HSTS_FIRST_STAGE_SECONDS)]
    assert "stsPreload" not in text
