"""Offline behavioral contracts for opt-in generated application services."""

from importlib.util import find_spec
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

from copier import run_copy
import pytest
from scripts.checks.conventions import CHECKER
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_COMMIT = "1234567890abcdef1234567890abcdef12345678"
_TIMEOUT_SECONDS = 180
_SENSITIVE_MARKER = "credential-leak-sentinel"
_OPTIONS = {
    "data": "postgresql",
    "cache": "redis",
    "auth": "entra-bearer",
    "ai_service": "text",
}


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("services-source")
    shutil.copyfile(_ROOT / "copier.yml", root / "copier.yml")
    shutil.copytree(
        _ROOT / "packages/starter/template", root / "packages/starter/template"
    )
    return root


def _render(*, source: Path, destination: Path, **answers: str) -> Path:
    run_copy(
        str(source),
        destination,
        data={"service": "api", "kit_commit": _COMMIT, **answers},
        defaults=True,
        quiet=True,
    )
    return destination


def _run(
    *, project: Path, code: str, **environment: str
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 - fixed offline Python probes
        [sys.executable, "-c", code],
        cwd=project,
        env={
            **{
                key: value
                for key, value in os.environ.items()
                if not key.startswith("APP_")
            },
            "PYTHONPATH": "src",
            "PYTHONDONTWRITEBYTECODE": "1",
            "APP_ENVIRONMENT": "test",
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No Python files found" not in result.stdout + result.stderr
    return result


@pytest.mark.parametrize("commit", ["", "main", "A" * 40, "0" * 40, "a" * 39])
def test_api_requires_an_explicit_reviewed_commit(
    source: Path, tmp_path: Path, commit: str
) -> None:
    with pytest.raises(ValueError, match=r"reviewed.*40"):
        _render(source=source, destination=tmp_path / "app", kit_commit=commit)


@pytest.mark.parametrize(("option", "selection"), _OPTIONS.items())
def test_executable_services_require_api(
    source: Path, tmp_path: Path, option: str, selection: str
) -> None:
    with pytest.raises(ValueError, match="requires service=api"):
        _render(
            source=source,
            destination=tmp_path / "app",
            service="none",
            **{option: selection},
        )


@pytest.mark.parametrize("stage", ["local", "dev", "test", "staging", "prod"])
def test_generated_settings_require_explicit_supported_environment(
    source: Path, tmp_path: Path, stage: str
) -> None:
    project = _render(source=source, destination=tmp_path / "app")
    _run(
        project=project,
        code=f"""
from app.settings import load_settings
assert load_settings().environment.value == {stage!r}
""",
        APP_ENVIRONMENT=stage,
    )


@pytest.mark.parametrize("iac", ["none", "bicep", "terraform"])
@pytest.mark.parametrize("ci", ["github", "azure-devops"])
def test_generated_stage_env_examples_start_without_azure(
    source: Path, tmp_path: Path, iac: str, ci: str
) -> None:
    project = _render(source=source, destination=tmp_path / "app", iac=iac, ci=ci)
    _run(
        project=project,
        code="""
import os, shutil, sys
from fastapi.testclient import TestClient
for key in tuple(os.environ):
    if key.startswith(("APP_", "AZURE_", "OTEL_", "APPLICATIONINSIGHTS_")):
        del os.environ[key]
for stage in ("local", "dev", "test", "staging", "prod"):
    example = ".env.example" if stage == "local" else f".env.{stage}.example"
    shutil.copyfile(example, ".env")
    from app.settings import load_settings
    settings = load_settings()
    assert settings.environment.value == stage
    assert settings.runtime_config().tracing is False
    from app.main import build_app
    with TestClient(build_app()) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
    assert not any(name == "azure" or name.startswith("azure.") for name in sys.modules)
    os.environ["APP_ENVIRONMENT"] = "test"
    assert load_settings().environment.value == "test"
    del os.environ["APP_ENVIRONMENT"]
""",
    )


_REMOTE_PLAINTEXT_OR_LOOPBACK = ("localhost", "127.0.0.1", "::1", "redis://", "http://")
# Synthetic operator values for every blank a remote stage example leaves open.
_REMOTE_STAGE_VALUES = {
    "APP_POSTGRES_HOST": "db.private.example",
    "APP_POSTGRES_DATABASE": "app",
    "APP_POSTGRES_USER": "app",
    "APP_POSTGRES_PASSWORD": "synthetic-password",
    "APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID": "44444444-4444-4444-8444-444444444444",
    "APP_REDIS_URL": "rediss://cache.private.example:6380/0",
    "APP_AUTH_TENANT_ID": "11111111-1111-4111-8111-111111111111",
    "APP_AUTH_CLIENT_ID": "22222222-2222-4222-8222-222222222222",
    "APP_AUTH_AUDIENCE": "synthetic-api",
    "APP_AUTH_ORIGIN": "https://app.example",
    "APP_AI_MODEL": "openai/synthetic",
    "APP_AI_API_KEY": "synthetic-key",
    "APP_AI_API_BASE": "https://provider.invalid/openai/v1/",
    "APP_AI_MANAGED_IDENTITY_CLIENT_ID": "33333333-3333-4333-8333-333333333333",
}


@pytest.mark.parametrize("iac", ["none", "bicep", "terraform"])
def test_stage_env_examples_keep_remote_service_configuration_explicit(
    source: Path, tmp_path: Path, iac: str
) -> None:
    project = _render(
        source=source,
        destination=tmp_path / "app",
        iac=iac,
        data="postgresql",
        cache="redis" if iac == "none" else "none",
        auth="entra-bearer",
        ai_service="text",
    )
    for stage in ("dev", "test", "staging", "prod"):
        example = project / f".env.{stage}.example"
        values = dict(
            line.split("=", 1)
            for line in example.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        )
        assert values["APP_ENVIRONMENT"] == stage
        assert values["APP_POSTGRES_REQUIRE_TLS"] == "true"
        assert values["APP_POSTGRES_HOST"] == ""
        assert values["APP_AUTH_TENANT_ID"] == ""
        assert values["APP_AUTH_ROLES"] == "[]"
        assert "APPLICATIONINSIGHTS_CONNECTION_STRING" not in values
        assert not [
            key
            for key, value in values.items()
            if any(marker in value for marker in _REMOTE_PLAINTEXT_OR_LOOPBACK)
        ]
        if iac == "none":
            assert values["APP_POSTGRES_ENTRA_AUTHENTICATION"] == "false"
            assert values["APP_POSTGRES_PASSWORD"] == ""
            assert values["APP_AI_API_KEY"] == ""
            assert values["APP_REDIS_URL"] == ""
        else:
            assert values["APP_POSTGRES_ENTRA_AUTHENTICATION"] == "true"
            assert values["APP_AI_ENTRA_AUTHENTICATION"] == "true"
            assert "APP_POSTGRES_PASSWORD" not in values
            assert "APP_AI_API_KEY" not in values
            assert "APP_AI_API_VERSION" not in values
        blanks = {key for key, value in values.items() if not value}
        assert blanks <= _REMOTE_STAGE_VALUES.keys()
        completed = {key: _REMOTE_STAGE_VALUES[key] for key in blanks}
        completed["APP_AUTH_SCOPES"] = '["access"]'
        shutil.copyfile(example, project / ".env")
        # The stage must come from the selected file, not the harness default.
        _run(
            project=project,
            code=f"""
import os
from app.settings import ConfigurationError, load_settings
del os.environ["APP_ENVIRONMENT"]
try:
    load_settings()
except ConfigurationError:
    pass
else:
    raise AssertionError("Unconfigured remote dependencies must not start")
os.environ.update({completed!r})
assert load_settings().environment.value == {stage!r}
""",
        )


@pytest.mark.parametrize("stage", [None, "", "production", "DEV", "unknown"])
def test_generated_settings_reject_missing_or_unknown_environment(
    source: Path, tmp_path: Path, stage: str | None
) -> None:
    project = _render(source=source, destination=tmp_path / "app")
    result = _run(
        project=project,
        code=f"""
import os, traceback
from app.settings import load_settings, ConfigurationError
os.environ.pop("APP_ENVIRONMENT", None)
value = {stage!r}
if value is not None:
    os.environ["APP_ENVIRONMENT"] = value
try:
    load_settings()
except ConfigurationError as error:
    assert error.fields == ("APP_ENVIRONMENT",)
    print(traceback.format_exc())
else:
    raise AssertionError("Invalid environment accepted")
""",
    )
    assert "Invalid APP_" in result.stdout


_AI_ENTRA_ENV = {
    "APP_AI_MODEL": "openai/deployment",
    "APP_AI_API_BASE": "https://provider.invalid/openai/v1/",
    "APP_AI_ENTRA_AUTHENTICATION": "true",
    "APP_AI_MANAGED_IDENTITY_CLIENT_ID": "33333333-3333-4333-8333-333333333333",
}


def test_generated_ai_settings_accept_explicit_keyless_authentication(
    source: Path, tmp_path: Path
) -> None:
    project = _render(source=source, destination=tmp_path / "app", ai_service="text")
    _run(
        project=project,
        code="""
from app.settings import load_settings
settings = load_settings()
assert settings.text_config().entra_authentication is True
assert settings.text_config().api_key is None
""",
        APP_ENVIRONMENT="test",
        **_AI_ENTRA_ENV,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("APP_AI_API_KEY", ""),
        ("APP_AI_API_KEY", _SENSITIVE_MARKER),
        ("APP_AI_MANAGED_IDENTITY_CLIENT_ID", None),
        ("APP_AI_MANAGED_IDENTITY_CLIENT_ID", _SENSITIVE_MARKER),
        ("APP_AI_ENTRA_AUTHENTICATION", "false"),
        ("APP_AI_API_BASE", "https://provider.invalid"),
        ("APP_AI_MODEL", "azure/deployment"),
        ("APP_AI_API_VERSION", "2024-10-21"),
    ],
)
def test_generated_ai_rejects_conflicting_authentication_safely(
    source: Path, tmp_path: Path, field: str, value: str | None
) -> None:
    project = _render(source=source, destination=tmp_path / "app", ai_service="text")
    result = _run(
        project=project,
        code=f"""
import os, traceback
from app.settings import load_settings, ConfigurationError
os.environ.pop({field!r}, None)
value = {value!r}
if value is not None:
    os.environ[{field!r}] = value
try:
    load_settings()
except ConfigurationError:
    print(traceback.format_exc())
else:
    raise AssertionError("Conflicting AI configuration accepted")
""",
        APP_ENVIRONMENT="test",
        **_AI_ENTRA_ENV,
    )
    assert _SENSITIVE_MARKER not in result.stdout


_AI_ENTRA_LIFECYCLE_PROBE = """
import asyncio, json, os, socket, time
from unittest.mock import patch
from azure.core.credentials import AccessToken
from platform_kit_runtime.ai import AsyncTokenProvider
events = []
def no_network(*args, **kwargs):
    raise AssertionError("Offline lifecycle test attempted network access")
class Credential:
    def __init__(self, *, client_id):
        assert client_id == "33333333-3333-4333-8333-333333333333"
        events.append("credential.create")
        self.calls = 0
    async def get_token(self, *scopes, **kwargs):
        assert scopes == ("https://ai.azure.com/.default",)
        self.calls += 1
        events.append("credential.token")
        return AccessToken(f"synthetic-token-{self.calls}", int(time.time()) + 60)
    async def close(self):
        events.append("credential.close")
def generator(*, config, token_provider: AsyncTokenProvider):
    assert config.entra_authentication is True
    assert config.api_key is None
    events.append("generator.create")
    if os.environ.get("FAIL_STARTUP"):
        raise RuntimeError("synthetic startup failure")
    return token_provider
async def check():
    from app.main import app
    assert events == []
    try:
        async with app.router.lifespan_context(app):
            provider = app.state.text_generator
            assert await provider() == "synthetic-token-1"
            assert await provider() == "synthetic-token-2"
    except RuntimeError as error:
        assert os.environ.get("FAIL_STARTUP")
        assert str(error) == "synthetic startup failure"
    assert not hasattr(app.state, "text_generator")
with asyncio.Runner() as runner:
    runner.get_loop()
    with patch("socket.socket.connect", no_network), \\
         patch("socket.getaddrinfo", no_network), \\
         patch("azure.identity.aio.ManagedIdentityCredential", Credential), \\
         patch("azure.identity.aio.DefaultAzureCredential", side_effect=AssertionError), \\
         patch("platform_kit_runtime.ai.create_text_generator", generator):
        runner.run(check())
print(json.dumps(events))
"""


@pytest.mark.parametrize("fail_startup", [False, True])
def test_generated_ai_owns_explicit_renewable_credential_lifecycle(
    source: Path, tmp_path: Path, fail_startup: bool
) -> None:
    project = _render(source=source, destination=tmp_path / "app", ai_service="text")
    result = _run(
        project=project,
        code=_AI_ENTRA_LIFECYCLE_PROBE,
        **_AI_ENTRA_ENV,
        **({"FAIL_STARTUP": "1"} if fail_startup else {}),
    )
    assert json.loads(result.stdout) == [
        "credential.create",
        "generator.create",
        *([] if fail_startup else ["credential.token", "credential.token"]),
        "credential.close",
    ]


@pytest.mark.parametrize(
    ("answers", "extras", "suffix"),
    [
        ({}, [], ""),
        ({"data": "postgresql"}, ["database"], ""),
        ({"cache": "redis"}, ["ratelimit"], ""),
        ({"auth": "entra-bearer"}, ["auth"], "-identity"),
        ({"ai_service": "text"}, ["ai"], "-ai"),
        (_OPTIONS, ["database", "ratelimit", "auth", "ai"], "-ai-identity"),
    ],
)
def test_features_select_only_required_dependencies_and_guidance(
    source: Path,
    tmp_path: Path,
    answers: dict[str, str],
    extras: list[str],
    suffix: str,
) -> None:
    project = _render(source=source, destination=tmp_path / "app", **answers)
    manifest = tomllib.loads((project / "pyproject.toml").read_text())
    qualifier = f"[{','.join(extras)}]" if extras else ""
    assert manifest["project"]["dependencies"][0].startswith(
        f"platform-kit-runtime{qualifier}>="
    )
    assert manifest["tool"]["uv"]["sources"]["platform-kit-runtime"]["rev"] == _COMMIT
    apm = yaml.safe_load((project / "apm.yml").read_text())
    assert apm["dependencies"]["apm"] == [
        f"lfr-ai/agent-kit/profiles/starters/backend{suffix}#v0.1.0"
    ]
    compose = yaml.safe_load((project / "compose.yaml").read_text())
    assert set(compose["services"]) == {
        "app",
        *({"postgres"} if answers.get("data") else set()),
        *({"redis"} if answers.get("cache") else set()),
    }


@pytest.mark.parametrize(
    ("port_setting", "published_port"),
    [("APP_POSTGRES_PORT=55432\n", "55432"), ("", "5432")],
)
def test_compose_postgres_host_port_follows_settings(
    source: Path, tmp_path: Path, port_setting: str, published_port: str
) -> None:
    docker = shutil.which("docker")
    if (
        docker is None
        or subprocess.run(  # noqa: S603 - fixed Compose availability probe
            [docker, "compose", "version"],
            capture_output=True,
            check=False,
            timeout=_TIMEOUT_SECONDS,
        ).returncode
    ):
        pytest.skip("Docker Compose is unavailable")
    project = _render(source=source, destination=tmp_path / "app", data="postgresql")
    (project / ".env").write_text(
        f"{port_setting}APP_POSTGRES_USER=app\n"
        "APP_POSTGRES_DATABASE=app\nAPP_POSTGRES_PASSWORD=local-only\n",
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 - fixed local Compose model probe
        [docker, "compose", "--profile", "postgres", "config", "--format", "json"],
        cwd=project,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("APP_", "COMPOSE_"))
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    published = [port["published"] for port in services["postgres"]["ports"]]
    assert published == [published_port]
    environment = services["app"]["environment"]
    assert environment["APP_POSTGRES_HOST"] == "postgres"
    assert environment["APP_POSTGRES_PORT"] == "5432"


@pytest.mark.parametrize(
    ("port_settings", "app_port", "redis_port"),
    [
        ("LOCAL_APP_PORT=18080\nLOCAL_REDIS_PORT=16379\n", "18080", "16379"),
        ("", "8080", "6379"),
    ],
)
def test_compose_loopback_host_ports_follow_local_settings(
    source: Path, tmp_path: Path, port_settings: str, app_port: str, redis_port: str
) -> None:
    docker = shutil.which("docker")
    if (
        docker is None
        or subprocess.run(  # noqa: S603 - fixed Compose availability probe
            [docker, "compose", "version"],
            capture_output=True,
            check=False,
            timeout=_TIMEOUT_SECONDS,
        ).returncode
    ):
        pytest.skip("Docker Compose is unavailable")
    project = _render(source=source, destination=tmp_path / "app", cache="redis")
    example = (project / ".env.example").read_text(encoding="utf-8")
    assert "# LOCAL_APP_PORT=8080\n" in example
    assert "# LOCAL_REDIS_PORT=6379\n" in example
    (project / ".env").write_text(port_settings, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed local Compose model probe
        [docker, "compose", "--profile", "redis", "config", "--format", "json"],
        cwd=project,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("APP_", "COMPOSE_", "LOCAL_"))
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for name, published in (("app", app_port), ("redis", redis_port)):
        ports = services[name]["ports"]
        assert [(port["host_ip"], port["published"]) for port in ports] == [
            ("127.0.0.1", published)
        ]


_BASE_PROBE = """
import asyncio, json, logging, sys
from httpx import ASGITransport, AsyncClient
from app.main import app
async def check():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://local.test") as client:
            live = await client.get("/health/live")
            ready = await client.get("/health/ready")
            response = await client.get("/private-secret?token=secret-value",
                                        headers={"Authorization": "Bearer secret-value"})
    try:
        raise ValueError("secret-value")
    except ValueError:
        logging.getLogger("app").exception("secret-value")
    logging.getLogger("uvicorn.access").info("secret-value")
    return [live.status_code, ready.status_code, response.status_code]
print(json.dumps({"statuses": asyncio.run(check()), "modules": list(sys.modules)}))
"""


def test_default_is_local_and_emits_sanitized_structured_access_logs(
    source: Path, tmp_path: Path
) -> None:
    project = _render(source=source, destination=tmp_path / "app")
    result = _run(project=project, code=_BASE_PROBE)
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload["statuses"] == [200, 200, 404]
    loaded = payload["modules"]
    assert not any(
        name.split(".")[0]
        in {"redis", "sqlalchemy", "asyncpg", "jwt", "msal", "litellm"}
        for name in loaded
    )
    assert result.stderr == ""
    logs = "\n".join(result.stdout.splitlines()[:-1])
    assert "secret-value" not in logs
    assert "private-secret" not in logs
    events = [json.loads(line) for line in logs.splitlines()]
    access = [event for event in events if event["event"] == "runtime.http_request"]
    assert len(access) == 1
    assert access[0]["http_status"] == 404
    assert access[0]["request_id"]
    problems = [event for event in events if event["event"] == "runtime.problem"]
    assert len(problems) == 1
    assert problems[0]["http_status"] == 404
    assert problems[0]["problem_code"]
    assert re.fullmatch(r"urn:uuid:[0-9a-f-]{36}", problems[0]["instance"])
    assert set(problems[0]) <= {
        "level",
        "event",
        "logger",
        "module",
        "function",
        "line",
        "request_id",
        "trace_id",
        "http_status",
        "problem_code",
        "instance",
        "failure_reason",
    }
    taskfile = yaml.safe_load((project / "Taskfile.yml").read_text())
    assert "apm" not in str(taskfile["tasks"]["local:setup"])
    assert "--no-access-log" in str(taskfile["tasks"]["start"])
    assert "--no-access-log" in (project / "Dockerfile").read_text()


@pytest.mark.parametrize(("option", "selection"), _OPTIONS.items())
def test_enabled_features_fail_safely_without_configuration(
    source: Path, tmp_path: Path, option: str, selection: str
) -> None:
    project = _render(
        source=source, destination=tmp_path / "app", **{option: selection}
    )
    result = _run(
        project=project,
        code="""
import json, traceback
try:
    import app.main
except RuntimeError:
    print(json.dumps(traceback.format_exc()))
else:
    raise AssertionError("Missing feature settings were accepted")
""",
        APP_POSTGRES_PASSWORD=_SENSITIVE_MARKER,
        APP_REDIS_URL=_SENSITIVE_MARKER,
        APP_AI_API_KEY=_SENSITIVE_MARKER,
    )
    assert "Invalid APP_" in json.loads(result.stdout)
    assert _SENSITIVE_MARKER not in result.stdout


_FEATURE_ENV = {
    "APP_POSTGRES_HOST": "127.0.0.1",
    "APP_POSTGRES_DATABASE": "app",
    "APP_POSTGRES_USER": "app",
    "APP_POSTGRES_PASSWORD": "synthetic-password",
    "APP_REDIS_URL": "redis://127.0.0.1:6379/0",
    "APP_RATE_LIMIT": '{"limit": 100, "window_seconds": 60}',
    "APP_AUTH_TENANT_ID": "11111111-1111-4111-8111-111111111111",
    "APP_AUTH_CLIENT_ID": "22222222-2222-4222-8222-222222222222",
    "APP_AUTH_AUDIENCE": "synthetic-api",
    "APP_AUTH_ORIGIN": "https://local.example",
    "APP_AUTH_SCOPES": '["access"]',
    "APP_AI_MODEL": "openai/synthetic",
    "APP_AI_API_KEY": "synthetic-key",
}

_LIFECYCLE_PROBE = """
import asyncio, json, os
from contextlib import asynccontextmanager
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient
from platform_kit_runtime.identity import AuthenticationRequiredError, Principal
events = []
class Probe:
    healthy = True
    async def check(self):
        events.append("database.check")
        return self.healthy
class Database:
    probe = Probe()
    @asynccontextmanager
    async def lifespan(self, app):
        events.append("database.open")
        try:
            yield
        finally:
            events.append("database.close")
class Redis:
    count = 0
    async def execute_command(self, *args):
        events.append("redis.hit")
        self.count += 1
        return [self.count, 60000]
    async def aclose(self):
        events.append("redis.close")
class Validator:
    async def validate(self, *, token, audience):
        assert audience == "synthetic-api"
        if token == "invalid":
            raise AuthenticationRequiredError
        return Principal(tenant_id="tenant", subject_id="subject",
                         scopes=frozenset({"access"} if token == "valid" else set()))
@asynccontextmanager
async def bearer(**kwargs):
    events.append("bearer.open")
    try:
        yield Validator()
    finally:
        events.append("bearer.close")
def generator(**kwargs):
    events.append("text.create")
    if os.environ.get("FAIL_STARTUP"):
        raise RuntimeError("synthetic startup failure")
    return object()
database, redis = Database(), Redis()
async def check():
    from app.main import app
    if os.environ.get("FAIL_STARTUP"):
        try:
            async with app.router.lifespan_context(app):
                raise AssertionError("startup unexpectedly succeeded")
        except RuntimeError as error:
            assert str(error) == "synthetic startup failure"
        assert not hasattr(app.state, "database")
        assert not hasattr(app.state, "bearer_guard")
        return []
    async with app.router.lifespan_context(app):
        assert app.state.database is database
        assert app.state.text_generator is not None
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://local.test") as client:
            results = []
            for token in ("", "invalid", "forbidden", "valid"):
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                response = await client.get("/technical/identity", headers=headers)
                results.append(response.status_code)
                if token == "valid":
                    assert response.json() == {"tenant_id": "tenant", "subject_id": "subject"}
            results.append((await client.post("/text")).status_code)
            results.append((await client.get("/health/ready")).status_code)
            database.probe.healthy = False
            results.append((await client.get("/health/ready")).status_code)
            results.append((await client.get("/health/live")).status_code)
            redis.count = 100
            results.append((await client.get("/technical/identity")).status_code)
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "bearer_guard")
    assert not hasattr(app.state, "text_generator")
    return results
with patch("platform_kit_runtime.database.create_database", return_value=database), \\
     patch("redis.asyncio.Redis.from_url", return_value=redis), \\
     patch("platform_kit_runtime.identity.open_entra_bearer", bearer), \\
     patch("platform_kit_runtime.ai.create_text_generator", generator):
    statuses = asyncio.run(check())
print(json.dumps({"statuses": statuses, "events": events}))
"""


@pytest.mark.parametrize("fail_startup", [False, True])
def test_selected_services_use_runtime_factories_and_close_resources(
    source: Path, tmp_path: Path, fail_startup: bool
) -> None:
    project = _render(source=source, destination=tmp_path / "app", **_OPTIONS)
    environment = {**_FEATURE_ENV, **({"FAIL_STARTUP": "1"} if fail_startup else {})}
    result = json.loads(
        _run(project=project, code=_LIFECYCLE_PROBE, **environment).stdout.splitlines()[
            -1
        ]
    )
    assert result["statuses"] == (
        [] if fail_startup else [401, 401, 403, 200, 404, 200, 503, 200, 429]
    )
    events = result["events"]
    assert events[:3] == ["database.open", "bearer.open", "text.create"]
    assert events[-3:] == ["bearer.close", "redis.close", "database.close"]
    assert events.count("text.create") == 1
    if not fail_startup:
        assert events.count("database.check") == 2
        assert events.count("redis.hit") == 6


def test_redis_requires_an_explicit_policy(source: Path, tmp_path: Path) -> None:
    project = _render(source=source, destination=tmp_path / "app", cache="redis")
    result = _run(
        project=project,
        code="""
import json
from app.settings import load_settings
try:
    load_settings()
except RuntimeError as error:
    print(json.dumps(str(error)))
else:
    raise AssertionError("Redis without a rate policy was accepted")
""",
        APP_REDIS_URL="redis://127.0.0.1:6379/0",
    )
    assert "Invalid APP_" in json.loads(result.stdout)


@pytest.mark.parametrize("iac", ["none", "bicep", "terraform"])
def test_full_generated_service_passes_its_own_checks_offline(
    source: Path, tmp_path: Path, iac: str
) -> None:
    deployable = {"cache": "none", "telemetry": "application-insights"}
    options = {**_OPTIONS, **(deployable if iac != "none" else {})}
    project = _render(source=source, destination=tmp_path / "app", iac=iac, **options)
    environment = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("APP_")
        },
        "PYTHONPATH": "src",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DEBUG_TEMPROOT": str(project),
    }
    # Mirror the generated Taskfile's lint scope, then hold the rendered code to
    # the same naming, magic-number and docstring rules as the kit's sources.
    code = ["src", *(["scripts"] if iac != "none" else [])]
    for arguments in [
        ["-m", "ruff", "format", "--check", "--no-cache", *code, "tests"],
        ["-m", "ruff", "check", "--no-cache", *code, "tests"],
        [str(CHECKER), "--magic-numbers", "--docstrings", *code],
        ["-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
    ]:
        result = subprocess.run(  # noqa: S603 - fixed offline tool invocations
            [sys.executable, *arguments],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, result.stdout + result.stderr


_DIAGNOSTIC_PROBE = """
import json, logging
from app.logging import configure_logging
configure_logging()
def first_failure():
    try:
        raise ValueError("credential-leak-sentinel")
    except ValueError:
        logging.getLogger("app.service").exception(
            "https://private.example/path?secret=credential-leak-sentinel")
def second_failure():
    try:
        raise RuntimeError("credential-leak-sentinel")
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("credential-leak-sentinel")
first_failure()
second_failure()
logging.getLogger("app.service").error("credential-leak-sentinel")
print(json.dumps(True))
"""


def test_console_errors_keep_code_attribution_without_diagnostic_content(
    source: Path, tmp_path: Path
) -> None:
    project = _render(source=source, destination=tmp_path / "app")
    result = _run(project=project, code=_DIAGNOSTIC_PROBE)
    assert result.stderr == ""
    assert _SENSITIVE_MARKER not in result.stdout
    assert "private.example" not in result.stdout
    records = [json.loads(line) for line in result.stdout.splitlines()[:-1]]
    first, second, ordinary = records
    assert first["logger"] == "app.service"
    assert second["logger"] == "uvicorn.error"
    assert first["function"] == "first_failure"
    assert second["function"] == "second_failure"
    assert first["line"] != second["line"]
    assert first["exception_type"] == "builtins.ValueError"
    assert second["exception_type"] == "builtins.RuntimeError"
    assert first["exception_frames"] == [
        {"module": "__main__", "function": "first_failure", "line": 7}
    ]
    assert "exception_type" not in ordinary
    assert ordinary["logger"] == "app.service"
    assert ordinary["line"] > 0


_SETTINGS_DIAGNOSTIC_PROBE = """
import json, logging, os, traceback
from app.logging import configure_logging
from app.settings import load_settings
configure_logging()
original = dict(os.environ)
cases = [
    ("APP_POSTGRES_HOST", None),
    ("APP_RATE_LIMIT", "credential-leak-sentinel"),
    ("APP_TRUSTED_PROXY_HOPS", "17"),
    ("APP_POSTGRES_PORT", "credential-leak-sentinel"),
    ("APP_AUTH_TENANT_ID", "credential-leak-sentinel"),
    ("APP_AI_MODEL", ""),
]
results = []
for field, value in cases:
    os.environ.clear()
    os.environ.update(original)
    if value is None:
        os.environ.pop(field)
    else:
        os.environ[field] = value
    try:
        load_settings()
    except RuntimeError as error:
        results.append({
            "expected": field,
            "fields": getattr(error, "fields", ()),
            "cause_type": getattr(error, "cause_type", ""),
            "message": str(error),
            "traceback": traceback.format_exc(),
            "context": error.__context__ is not None,
            "cause": error.__cause__ is not None,
        })
        logging.getLogger("app").exception("credential-leak-sentinel")
    else:
        raise AssertionError("Invalid settings were accepted")
print(json.dumps(results))
"""


def test_settings_diagnostics_identify_fields_without_values_or_context(
    source: Path, tmp_path: Path
) -> None:
    project = _render(source=source, destination=tmp_path / "app", **_OPTIONS)
    result = _run(project=project, code=_SETTINGS_DIAGNOSTIC_PROBE, **_FEATURE_ENV)
    assert _SENSITIVE_MARKER not in result.stdout + result.stderr
    for failure in json.loads(result.stdout.splitlines()[-1]):
        assert failure["expected"] in failure["fields"]
        assert failure["expected"] in failure["message"]
        assert failure["cause_type"]
        assert failure["context"] is False
        assert failure["cause"] is False
    assert result.stderr == ""
    records = [json.loads(line) for line in result.stdout.splitlines()[:-1]]
    assert all(record["configuration_fields"] for record in records)


_MANAGED_DATABASE_PROBE = """
import asyncio, json, os, sys
from contextlib import asynccontextmanager
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient
events = []
class Credential:
    def __init__(self, *, client_id):
        assert client_id == "33333333-3333-4333-8333-333333333333"
        events.append("credential.create")
    async def close(self):
        events.append("credential.close")
class Probe:
    async def check(self):
        events.append("database.check")
        return True
class Database:
    probe = Probe()
    @asynccontextmanager
    async def lifespan(self, app):
        events.append("database.open")
        try:
            if os.environ.get("FAIL_STARTUP"):
                raise RuntimeError("synthetic startup failure")
            yield
        finally:
            events.append("database.close")
def database_factory(*, settings, credential):
    assert settings.entra_authentication is True
    assert settings.require_tls is True
    assert settings.password is None
    assert isinstance(credential, Credential)
    return Database()
async def check():
    from app.main import app
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://local.test") as client:
                response = await client.get("/health/ready")
                assert response.status_code == 200
    except RuntimeError as error:
        assert os.environ.get("FAIL_STARTUP")
        assert str(error) == "synthetic startup failure"
with patch("azure.identity.aio.ManagedIdentityCredential", Credential), \\
     patch("platform_kit_runtime.database.create_database", database_factory):
    asyncio.run(check())
print(json.dumps(events))
"""


@pytest.mark.parametrize("fail_startup", [False, True])
def test_postgresql_managed_identity_is_explicit_and_closed(
    source: Path, tmp_path: Path, fail_startup: bool
) -> None:
    project = _render(source=source, destination=tmp_path / "app", data="postgresql")
    environment = {
        key: value
        for key, value in _FEATURE_ENV.items()
        if key.startswith("APP_POSTGRES_") and key != "APP_POSTGRES_PASSWORD"
    }
    environment.update(
        APP_POSTGRES_ENTRA_AUTHENTICATION="true",
        APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID="33333333-3333-4333-8333-333333333333",
    )
    if fail_startup:
        environment["FAIL_STARTUP"] = "1"
    result = _run(project=project, code=_MANAGED_DATABASE_PROBE, **environment)
    expected = ["credential.create", "database.open"]
    if not fail_startup:
        expected.append("database.check")
    expected.extend(["database.close", "credential.close"])
    assert json.loads(result.stdout) == expected


def test_postgresql_managed_identity_rejects_unsafe_or_implicit_settings(
    source: Path, tmp_path: Path
) -> None:
    project = _render(source=source, destination=tmp_path / "app", data="postgresql")
    result = _run(
        project=project,
        code="""
import json, os
from app.settings import load_settings
original = dict(os.environ)
cases = [
    ({"APP_POSTGRES_ENTRA_AUTHENTICATION": "true"}, "APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID"),
    ({"APP_POSTGRES_ENTRA_AUTHENTICATION": "true",
      "APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID": "credential-leak-sentinel"},
     "APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID"),
    ({"APP_POSTGRES_ENTRA_AUTHENTICATION": "true",
      "APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID": "33333333-3333-4333-8333-333333333333"},
     "APP_POSTGRES_PASSWORD"),
    ({"APP_POSTGRES_ENTRA_AUTHENTICATION": "true",
      "APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID": "33333333-3333-4333-8333-333333333333",
      "APP_POSTGRES_PASSWORD": None, "APP_POSTGRES_REQUIRE_TLS": "false"},
     "APP_POSTGRES_REQUIRE_TLS"),
    ({"APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID": "33333333-3333-4333-8333-333333333333"},
     "APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID"),
]
fields = []
for changes, expected in cases:
    os.environ.clear()
    os.environ.update(original)
    for name, value in changes.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    try:
        load_settings()
    except RuntimeError as error:
        assert expected in str(error)
        assert "credential-leak-sentinel" not in str(error)
        assert error.__context__ is None
        fields.append(expected)
    else:
        raise AssertionError("Unsafe credential settings were accepted")
print(json.dumps(fields))
""",
        **_FEATURE_ENV,
    )
    assert len(json.loads(result.stdout)) == 5


def test_readmes_link_the_deployment_guide_at_the_correct_location(
    source: Path, tmp_path: Path
) -> None:
    project = _render(source=source, destination=tmp_path / "app")
    assert (
        f"https://github.com/lfr-ai/agent-kit/blob/{_COMMIT}/packages/starter/DEPLOYMENT.md"
        in (project / "README.md").read_text()
    )
    assert "(DEPLOYMENT.md)" in (_ROOT / "packages/starter/README.md").read_text()


def test_postgresql_password_default_does_not_load_azure_identity(
    source: Path, tmp_path: Path
) -> None:
    project = _render(source=source, destination=tmp_path / "app", data="postgresql")
    result = _run(
        project=project,
        code="""
import json, sys
from unittest.mock import Mock, patch
with patch("platform_kit_runtime.database.create_database", return_value=Mock()) as create:
    from app.main import app
    settings = create.call_args.kwargs["settings"]
    assert settings.entra_authentication is False
    assert settings.password == "synthetic-password"
    assert create.call_args.kwargs["credential"] is None
print(json.dumps(not any(name.startswith("azure.identity") for name in sys.modules)))
""",
        **_FEATURE_ENV,
    )
    assert json.loads(result.stdout) is True
    runtime = tomllib.loads((_ROOT / "packages/runtime/pyproject.toml").read_text())
    assert any(
        dependency.startswith("azure-identity>=")
        for dependency in runtime["project"]["optional-dependencies"]["database"]
    )


_AZURE_MONITOR_VARIABLES = {
    "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=55555555-5555-4555-8555-555555555555",
    "AZURE_CLIENT_ID": "44444444-4444-4444-8444-444444444444",
}


@pytest.mark.parametrize(
    ("iac", "telemetry"),
    [
        ("none", "none"),
        ("bicep", "none"),
        ("terraform", "none"),
        ("bicep", "application-insights"),
        ("terraform", "application-insights"),
    ],
)
def test_only_selected_telemetry_installs_azure_export(
    source: Path, tmp_path: Path, iac: str, telemetry: str
) -> None:
    project = _render(
        source=source, destination=tmp_path / "app", iac=iac, telemetry=telemetry
    )
    azure = telemetry == "application-insights"
    dependencies = tomllib.loads((project / "pyproject.toml").read_text())["project"][
        "dependencies"
    ]
    assert dependencies[0].startswith(
        f"platform-kit-runtime{'[telemetry]' if azure else ''}>="
    )
    names = {dependency.partition(">=")[0] for dependency in dependencies[1:]}
    assert ("azure-identity" in names) is azure
    assert any(name.startswith("azure-monitor-") for name in names) is azure
    for document in (".env.example", ".env.dev.example", ".env.prod.example"):
        text = (project / document).read_text()
        assert ("APPLICATIONINSIGHTS_CONNECTION_STRING" in text) is azure


@pytest.mark.parametrize(("service", "iac"), [("none", "bicep"), ("api", "none")])
def test_application_insights_requires_api_and_cloud(
    source: Path, tmp_path: Path, service: str, iac: str
) -> None:
    with pytest.raises(ValueError, match="requires service=api and"):
        _render(
            source=source,
            destination=tmp_path / "app",
            service=service,
            iac=iac,
            telemetry="application-insights",
        )


_AZURE_MONITOR_PROBE = """
import asyncio, atexit, json, os, sys, types
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from platform_kit_runtime.telemetry import OpenTelemetryInferenceTracer
events, shutdown = [], []
class Credential:
    def __init__(self, *, client_id):
        assert client_id == os.environ["AZURE_CLIENT_ID"]
        events.append("credential.create")
    def close(self):
        events.append("credential.close")
class Exporter(InMemorySpanExporter):
    def __init__(self, **kwargs):
        assert isinstance(kwargs["credential"], Credential)
        assert kwargs["connection_string"] == os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
        assert kwargs["disable_offline_storage"] is True
        for name in ("APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL",
                     "APPLICATIONINSIGHTS_SDKSTATS_DISABLED",
                     "APPLICATIONINSIGHTS_CONTROLPLANE_DISABLED",
                     "APPLICATIONINSIGHTS_OPENTELEMETRY_RESOURCE_METRIC_DISABLED"):
            assert os.environ[name] == "true"
        events.append("exporter.create")
        super().__init__()
    def shutdown(self):
        events.append("exporter.close")
        super().shutdown()
exporters = []
def make_exporter(**kwargs):
    exporter = Exporter(**kwargs)
    exporters.append(exporter)
    return exporter
module = types.ModuleType("azure.monitor.opentelemetry.exporter")
module.AzureMonitorTraceExporter = make_exporter
with patch.dict(sys.modules, {"azure.monitor.opentelemetry.exporter": module}), \\
     patch("azure.identity.ManagedIdentityCredential", Credential), \\
     patch("atexit.register", side_effect=shutdown.append):
    from app.main import app, build_app
    from app.settings import load_settings
    assert load_settings().runtime_config().tracing
    assert "connection_string" not in repr(load_settings().azure_monitor())
    build_app()
    assert events == ["credential.create", "exporter.create"]
    from dataclasses import replace
    from app.telemetry import configure_azure_tracing, TelemetryConfigurationError
    try:
        configure_azure_tracing(replace(load_settings().azure_monitor(), connection_string="credential-leak-sentinel"))
    except TelemetryConfigurationError:
        pass
    else:
        raise AssertionError("Conflicting process configuration was accepted")
    @app.get("/items/{item_id}")
    def item(item_id: str):
        with OpenTelemetryInferenceTracer().span(model="openai/test", max_output_tokens=1):
            pass
        return {"ok": True}
    async def exercise():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://local.test") as client:
                await client.get("/health/live")
                await client.get("/health/ready")
                response = await client.get(
                    "/items/credential-leak-sentinel?token=credential-leak-sentinel")
        return response.status_code
    assert asyncio.run(exercise()) == 200
    trace.get_tracer_provider().force_flush()
    spans = exporters[0].get_finished_spans()
    servers = [span for span in spans if span.kind == SpanKind.SERVER]
    assert len(servers) == 1
    assert servers[0].attributes["http.route"] == "/items/{item_id}"
    assert any(span.name == "chat test" for span in spans)
    assert "credential-leak-sentinel" not in str([span.to_json() for span in spans])
    # The runtime's dotted find_spec imports code-free PEP 420 parents only.
    assert not [name for name, loaded in list(sys.modules.items())
                if name.startswith(("opentelemetry.instrumentation.fastapi",
                                    "opentelemetry.exporter.otlp"))
                and getattr(loaded, "__file__", None) is not None]
    # The SDK is process-owned, not closed by the first app lifespan.
    assert events == ["credential.create", "exporter.create"]
    for close in shutdown:
        close()
        close()
    assert events == ["credential.create", "exporter.create", "exporter.close", "credential.close"]
print(json.dumps(True))
"""


def test_azure_deployment_exports_through_the_runtime_identity(
    source: Path, tmp_path: Path
) -> None:
    project = _render(
        source=source,
        destination=tmp_path / "app",
        iac="bicep",
        telemetry="application-insights",
    )
    result = _run(
        project=project, code=_AZURE_MONITOR_PROBE, **_AZURE_MONITOR_VARIABLES
    )
    assert _SENSITIVE_MARKER not in result.stdout + result.stderr
    assert result.stderr == ""
    events = [json.loads(line) for line in result.stdout.splitlines()[:-1]]
    requests = [event for event in events if event["event"] == "runtime.http_request"]
    assert len(requests) == 1
    assert requests[0]["trace_id"]


_LOCAL_PROBE = """
import json, os, sys
for name in ("APPLICATIONINSIGHTS_CONNECTION_STRING", "AZURE_CLIENT_ID"):
    os.environ.pop(name, None)
from app.main import app
from app.settings import load_settings
print(json.dumps({
    "azure": sorted(name for name in sys.modules if name.partition(".")[0] == "azure"),
    "tracing": load_settings().runtime_config().tracing,
}))
"""


@pytest.mark.parametrize("telemetry", ["none", "application-insights"])
def test_azure_starter_runs_locally_without_azure_sdks_or_tracing(
    source: Path, tmp_path: Path, telemetry: str
) -> None:
    project = _render(
        source=source,
        destination=tmp_path / "app",
        iac="terraform",
        telemetry=telemetry,
    )
    result = _run(project=project, code=_LOCAL_PROBE)
    assert json.loads(result.stdout) == {"azure": [], "tracing": False}


_AZURE_MONITOR_SETTINGS_PROBE = """
import json, os
from app.settings import load_settings
connection = "InstrumentationKey=credential-leak-sentinel"
client_id = "44444444-4444-4444-8444-444444444444"
cases = [
    ({"APPLICATIONINSIGHTS_CONNECTION_STRING": connection}, "AZURE_CLIENT_ID"),
    ({"APPLICATIONINSIGHTS_CONNECTION_STRING": connection,
      "AZURE_CLIENT_ID": "credential-leak-sentinel"}, "AZURE_CLIENT_ID"),
    ({"APPLICATIONINSIGHTS_CONNECTION_STRING": "", "AZURE_CLIENT_ID": client_id},
     "APPLICATIONINSIGHTS_CONNECTION_STRING"),
    ({"APPLICATIONINSIGHTS_CONNECTION_STRING": connection, "AZURE_CLIENT_ID": client_id,
      "OTEL_EXPORTER_OTLP_ENDPOINT": "https://credential-leak-sentinel.invalid"},
     "OTEL_EXPORTER_OTLP_ENDPOINT"),
    ({"APPLICATIONINSIGHTS_CONNECTION_STRING": connection, "AZURE_CLIENT_ID": client_id,
      "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://credential-leak-sentinel.invalid"},
     "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"),
]
original = {
    key: value for key, value in os.environ.items()
    if key not in ("APPLICATIONINSIGHTS_CONNECTION_STRING", "AZURE_CLIENT_ID")
}
results = []
for changes, expected in cases:
    os.environ.clear()
    os.environ.update(original, **changes)
    try:
        load_settings()
    except RuntimeError as error:
        results.append({
            "expected": expected,
            "fields": list(error.fields),
            "message": str(error),
            "context": error.__context__ is not None,
        })
    else:
        raise AssertionError("Invalid Azure Monitor settings were accepted")
print(json.dumps(results))
"""


def test_azure_monitor_settings_fail_with_names_only(
    source: Path, tmp_path: Path
) -> None:
    project = _render(
        source=source,
        destination=tmp_path / "app",
        iac="bicep",
        telemetry="application-insights",
    )
    result = _run(project=project, code=_AZURE_MONITOR_SETTINGS_PROBE)
    assert _SENSITIVE_MARKER not in result.stdout + result.stderr
    failures = json.loads(result.stdout)
    assert len(failures) == 5
    for failure in failures:
        assert failure["expected"] in failure["fields"]
        assert failure["expected"] in failure["message"]
        assert failure["context"] is False


def test_none_ignores_azure_telemetry_environment(source: Path, tmp_path: Path) -> None:
    project = _render(source=source, destination=tmp_path / "app", iac="bicep")
    _run(
        project=project,
        code="""
import importlib.abc, sys
class Forbidden(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("azure", "opentelemetry.sdk", "opentelemetry.exporter")):
            raise AssertionError("Off mode imported an exporter or Azure SDK")
sys.meta_path.insert(0, Forbidden())
from app.main import build_app
from fastapi.testclient import TestClient
with TestClient(build_app()) as client:
    assert client.get("/health/ready").status_code == 200
""",
        **_AZURE_MONITOR_VARIABLES,
    )


@pytest.mark.parametrize("failure", ["missing", "invalid", "existing"])
def test_azure_initialization_failures_have_safe_diagnostics(
    source: Path, tmp_path: Path, failure: str
) -> None:
    project = _render(
        source=source,
        destination=tmp_path / "app",
        iac="bicep",
        telemetry="application-insights",
    )
    result = _run(
        project=project,
        code="""
import importlib.abc, logging, os, sys, types
from unittest.mock import patch
from app.logging import configure_logging
from app.settings import load_settings
from app.telemetry import configure_azure_tracing, TelemetryConfigurationError
configure_logging()
mode = os.environ["FAILURE"]
closed = []
class Credential:
    def __init__(self, **kwargs):
        pass
    def close(self):
        closed.append(True)
def fail(**kwargs):
    raise ValueError("credential-leak-sentinel")
class Missing(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("azure.monitor"):
            raise ModuleNotFoundError("credential-leak-sentinel")
if mode == "existing":
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    trace.set_tracer_provider(TracerProvider(shutdown_on_exit=False))
elif mode == "missing":
    sys.meta_path.insert(0, Missing())
else:
    module = types.ModuleType("azure.monitor.opentelemetry.exporter")
    module.AzureMonitorTraceExporter = fail
    sys.modules[module.__name__] = module
with patch("azure.identity.ManagedIdentityCredential", Credential):
    try:
        configure_azure_tracing(load_settings().azure_monitor())
    except TelemetryConfigurationError as error:
        assert "credential-leak-sentinel" not in str(error)
        if mode != "existing":
            assert error.__cause__ is not None
        logging.getLogger("app").exception("credential-leak-sentinel")
    else:
        raise AssertionError("Invalid telemetry was accepted")
assert closed == ([True] if mode == "invalid" else [])
""",
        FAILURE=failure,
        **_AZURE_MONITOR_VARIABLES,
    )
    assert _SENSITIVE_MARKER not in result.stdout + result.stderr
    assert result.stderr == ""
    [event] = [json.loads(line) for line in result.stdout.splitlines()]
    assert event["exception_type"] == "app.telemetry.TelemetryConfigurationError"


def test_real_azure_trace_exporter_constructs_without_other_pipelines(
    source: Path, tmp_path: Path
) -> None:
    try:
        installed = find_spec("azure.monitor.opentelemetry.exporter") is not None
    except ModuleNotFoundError:
        installed = False
    if not installed:
        pytest.skip("Azure trace exporter requires a reviewed root test dependency")
    project = _render(
        source=source,
        destination=tmp_path / "app",
        iac="bicep",
        telemetry="application-insights",
    )
    _run(
        project=project,
        code="""
import atexit, sys
from unittest.mock import patch
from app.settings import load_settings
from app.telemetry import configure_azure_tracing
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from fastapi.testclient import TestClient
shutdown = []
with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \\
     patch("atexit.register", side_effect=shutdown.append):
    configure_azure_tracing(load_settings().azure_monitor())
    from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
    from opentelemetry.sdk.trace.export import SpanExportResult
    with patch.object(AzureMonitorTraceExporter, "export", return_value=SpanExportResult.SUCCESS):
        memory = InMemorySpanExporter()
        provider = trace.get_tracer_provider()
        provider.add_span_processor(SimpleSpanProcessor(memory))
        from app.main import build_app
        app = build_app()
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/missing").status_code == 404
        assert len(memory.get_finished_spans()) == 1
        for close in shutdown:
            close()
assert "azure.monitor.opentelemetry._configure" not in sys.modules
assert "azure.monitor.opentelemetry.exporter.statsbeat._statsbeat" not in sys.modules
assert "opentelemetry.instrumentation.fastapi" not in sys.modules
""",
        **_AZURE_MONITOR_VARIABLES,
    )
