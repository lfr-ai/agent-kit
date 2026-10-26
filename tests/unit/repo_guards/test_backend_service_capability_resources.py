"""Backend HTTP service, auth, API testing, and CLI capabilities behave as documented."""

import ast
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _ROOT / "packages/backend/.apm"
_SKILLS = _BACKEND / "skills"
_FASTAPI = _SKILLS / "kit-fastapi-service"
_AUTH = _SKILLS / "kit-auth"
_API_TESTING = _SKILLS / "kit-api-testing"
_CLI = _SKILLS / "kit-cli-tool"
_OWNED = (_FASTAPI, _AUTH, _API_TESTING, _CLI)
_WIRING = runpy.run_path(str(_FASTAPI / "assets/check_fastapi_wiring.py"))
_LINK = re.compile(r"\]\(([^)\s#]+)")
_REVIEW_DATE = "2026-10-23"
_POSTMAN_SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    metadata = yaml.safe_load(header)
    assert isinstance(metadata, dict)
    return {str(key): str(value) for key, value in metadata.items()}, body


def _reachable(skill: Path) -> set[Path]:
    pending = [skill / "SKILL.md"]
    seen: set[Path] = set()
    while pending:
        path = pending.pop().resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            pending.extend(
                path.parent / target
                for target in _LINK.findall(text)
                if "://" not in target
            )
    return seen


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _calls(tree: ast.AST, attribute: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]


# Skill structure


@pytest.mark.parametrize("skill", _OWNED, ids=lambda path: path.name)
def test_skill_metadata_and_procedure_shape(skill: Path) -> None:
    metadata, body = _frontmatter(skill / "SKILL.md")
    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == skill.name
    assert metadata["license"] == "MIT"
    assert metadata["description"].startswith("Use when")
    assert len(metadata["description"]) <= 350
    assert len(body.splitlines()) < 300
    assert "## Procedure" in body
    assert "## Acceptance gates" in body
    assert re.search(r"^1\. ", body, re.MULTILINE)


@pytest.mark.parametrize("skill", _OWNED, ids=lambda path: path.name)
def test_every_resource_is_linked_and_local(skill: Path) -> None:
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (skill / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert resources
    assert resources <= _reachable(skill)
    for document in (skill / "references").glob("*.md"):
        text = document.read_text(encoding="utf-8")
        assert f"Reviewed {_REVIEW_DATE}" in text, document.name
        assert "## Primary sources" in text, document.name
        assert "https://" in text.split("## Primary sources", 1)[1]


@pytest.mark.parametrize(
    "path",
    sorted(
        path
        for skill in _OWNED
        for path in (skill / "assets").glob("*.template")
        if path.name.endswith(".py.template")
    ),
    ids=lambda path: path.name,
)
def test_python_templates_parse_and_name_a_destination(path: Path) -> None:
    tree = _tree(path)
    docstring = ast.get_docstring(tree)
    assert docstring
    assert re.search(r"Copy into ``[^`]+\.py``", docstring)
    assert not any(
        isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(tree)
    )


@pytest.mark.parametrize(
    ("name", "apply_to"),
    [
        ("kit-fastapi", "**/api/**/*.py,**/main.py,**/middleware/**/*.py"),
        ("kit-auth", "**/auth/**/*.py,**/security/**/*.py"),
    ],
)
def test_instructions_are_narrow_and_short(name: str, apply_to: str) -> None:
    path = _BACKEND / "instructions" / f"{name}.instructions.md"
    metadata, body = _frontmatter(path)
    bullets = [line for line in body.splitlines() if line.startswith("- ")]
    assert set(metadata) == {"description", "applyTo"}
    assert metadata["applyTo"] == apply_to
    assert 4 <= len(bullets) <= 10
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 20


def test_middleware_prompt_links_its_owning_skill() -> None:
    path = _BACKEND / "prompts/kit-add-middleware.prompt.md"
    raw = path.read_bytes()
    metadata, body = _frontmatter(path)
    assert b"\r" not in raw
    assert set(metadata) == {"description", "argument-hint", "agent"}
    assert len(metadata["description"]) <= 160
    assert "](../skills/kit-fastapi-service/SKILL.md)" in body
    for section in ("## Input", "## Procedure", "## Acceptance gates", "## Output"):
        assert section in body
    assert 25 <= len(raw.decode("utf-8").splitlines()) <= 80


# check_fastapi_wiring.py


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (
            "from fastapi import APIRouter\nrouter = APIRouter()\n",
            "router-not-included",
        ),
        ("import time\nasync def h():\n    time.sleep(1)\n", "blocking-call"),
        ("import time as t\nasync def h():\n    t.sleep(1)\n", "blocking-call"),
        ("from time import sleep\nasync def h():\n    sleep(1)\n", "blocking-call"),
        ("import requests\nasync def h():\n    requests.get('u')\n", "blocking-call"),
        ("import httpx\nasync def h():\n    httpx.Client()\n", "blocking-call"),
        (
            (
                "app.add_middleware(CORSMiddleware, allow_origins=['*'],"
                " allow_credentials=True)\n"
            ),
            "cors-credentials-wildcard",
        ),
        (
            (
                "Middleware(CORSMiddleware, allow_origin_regex='.*',"
                " allow_credentials=True)\n"
            ),
            "cors-credentials-wildcard",
        ),
        ("@app.on_event('shutdown')\ndef stop():\n    pass\n", "on-event"),
    ],
)
def test_wiring_checker_reports_each_rule(source: str, rule: str) -> None:
    findings = _WIRING["check_sources"]([("pkg/app.py", source)])
    assert any(f"[{rule}]" in finding for finding in findings), findings
    assert all(finding.startswith("pkg/app.py:") for finding in findings)


@pytest.mark.parametrize(
    "source",
    [
        "import asyncio\nasync def h():\n    await asyncio.sleep(1)\n",
        "import time\ndef h():\n    time.sleep(1)\n",
        "import time\nasync def h():\n    def work():\n        time.sleep(1)\n",
        "app.add_middleware(CORSMiddleware, allow_origins=['*'])\n",
        (
            "app.add_middleware(CORSMiddleware, allow_origins=['https://a.test'],"
            " allow_credentials=True)\n"
        ),
        "from fastapi import APIRouter\nrouter = APIRouter()\napp.include_router(router)\n",
    ],
)
def test_wiring_checker_accepts_safe_sources(source: str) -> None:
    assert _WIRING["check_sources"]([("pkg/app.py", source)]) == []


def test_router_inclusion_is_resolved_across_modules_and_aliases() -> None:
    routers = (
        "pkg/items.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n",
    )
    orphan = ("pkg/orders.py", "from fastapi import APIRouter\nrouter = APIRouter()\n")
    includes = (
        "pkg/app.py",
        "from pkg.items import router as items_router\napp.include_router(items_router)\n",
    )
    findings = _WIRING["check_sources"]([routers, orphan, includes])
    assert findings == [
        (
            "pkg/orders.py:2: [router-not-included] router 'router' is never "
            "passed to include_router"
        )
    ]
    attribute = (
        "pkg/app.py",
        "from pkg import orders\napp.include_router(orders.router)\n",
    )
    assert _WIRING["check_sources"]([routers, orphan, includes, attribute]) == []
    selected = _WIRING["check_sources"]([orphan], rules=frozenset({"on-event"}))
    assert selected == []


def test_router_inclusion_resolves_relative_imports_and_packages() -> None:
    sources = [
        ("app/items.py", "from fastapi import APIRouter\nrouter = APIRouter()\n"),
        (
            "app/admin/__init__.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n",
        ),
        (
            "app/main.py",
            (
                "from .items import router as items_router\n"
                "from .admin import router as admin_router\n"
                "app.include_router(items_router)\napp.include_router(admin_router)\n"
            ),
        ),
    ]
    assert _WIRING["check_sources"](sources) == []
    package_import = (
        "app/main.py",
        "from . import admin\napp.include_router(admin.router)\n",
    )
    findings = _WIRING["check_sources"]([*sources[:2], package_import])
    assert findings == [
        (
            "app/items.py:2: [router-not-included] router 'router' is never "
            "passed to include_router"
        )
    ]


def test_blocking_call_ignores_local_names_that_shadow_modules() -> None:
    local = (
        "async def pending(repo):\n"
        "    requests = await repo.pending()\n"
        "    requests.append(1)\n"
        "    time = repo.clock\n"
        "    time.sleep(1)\n"
    )
    assert _WIRING["check_sources"]([("app/jobs.py", local)]) == []
    imported = "import requests\nasync def fetch():\n    requests.get('u')\n"
    findings = _WIRING["check_sources"]([("app/jobs.py", imported)])
    assert findings == [
        (
            "app/jobs.py:3: [blocking-call] blocking call 'requests.get' in async def "
            "'fetch'; use an async client, a sync handler, or a worker thread"
        )
    ]


def test_wiring_checker_cli_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = tmp_path / "good.py"
    good.write_text("async def h():\n    return 1\n", encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text("import time\nasync def h():\n    time.sleep(1)\n", encoding="utf-8")
    assert _WIRING["main"]([str(good)]) == 0
    assert _WIRING["main"]([str(tmp_path)]) == 1
    assert "[blocking-call]" in capsys.readouterr().out
    assert _WIRING["main"]([str(bad), "--rule", "on-event"]) == 0
    assert _WIRING["main"]([str(tmp_path / "missing")]) == 2
    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n", encoding="utf-8")
    assert _WIRING["main"]([str(broken)]) == 2
    assert "input error" in capsys.readouterr().err
    with pytest.raises(SystemExit) as usage:
        _WIRING["main"]([])
    assert usage.value.code == 2


def test_wiring_checker_self_test_runs_as_a_script() -> None:
    result = subprocess.run(  # noqa: S603 - first-party checker, no shell
        [
            sys.executable,
            str(_FASTAPI / "assets/check_fastapi_wiring.py"),
            "--self-test",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "self-test passed" in result.stdout


def test_fastapi_templates_pass_their_own_wiring_checker(tmp_path: Path) -> None:
    for template in (_FASTAPI / "assets").glob("*.py.template"):
        shutil.copyfile(template, tmp_path / template.name.removesuffix(".template"))
    assert _WIRING["main"]([str(tmp_path)]) == 0


# kit-fastapi-service templates


def test_app_factory_installs_middleware_in_documented_order() -> None:
    tree = _tree(_FASTAPI / "assets/app.py.template")
    added = [
        call.args[0].id
        for call in sorted(_calls(tree, "add_middleware"), key=lambda item: item.lineno)
        if isinstance(call.args[0], ast.Name)
    ]
    assert list(reversed(added)) == [
        "RequestIdMiddleware",
        "AccessLogMiddleware",
        "SecurityHeadersMiddleware",
        "TrustedHostMiddleware",
        "CORSMiddleware",
        "RateLimitMiddleware",
        "BodySizeLimitMiddleware",
        "GZipMiddleware",
    ]
    factory = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    assert not factory.args.args
    assert {arg.arg for arg in factory.args.kwonlyargs} == {
        "settings",
        "container_factory",
        "rate_limit_store",
    }
    assert any(
        keyword.arg == "lifespan"
        for call in ast.walk(factory)
        if isinstance(call, ast.Call)
        for keyword in call.keywords
    )


def test_middleware_is_pure_asgi_and_handlers_cover_all_errors() -> None:
    middleware = _FASTAPI / "assets/middleware.py.template"
    text = middleware.read_text(encoding="utf-8")
    assert "BaseHTTPMiddleware(" not in text
    assert "class BaseHTTPMiddleware" not in text
    classes = [
        node for node in _tree(middleware).body if isinstance(node, ast.ClassDef)
    ]
    asgi = [
        node.name
        for node in classes
        if any(
            isinstance(item, ast.AsyncFunctionDef) and item.name == "__call__"
            for item in node.body
        )
    ]
    assert set(asgi) == {
        "RequestIdMiddleware",
        "AccessLogMiddleware",
        "SecurityHeadersMiddleware",
        "BodySizeLimitMiddleware",
    }
    errors = _tree(_FASTAPI / "assets/errors.py.template")
    registered = {
        ast.unparse(call.args[0]) for call in _calls(errors, "add_exception_handler")
    }
    assert registered == {
        "ServiceError",
        "RequestValidationError",
        "StarletteHTTPException",
        "Exception",
    }


def test_http_settings_reject_wildcards_and_malformed_origins(tmp_path: Path) -> None:
    pytest.importorskip("pydantic")
    target = tmp_path / "http_settings.py"
    shutil.copyfile(_FASTAPI / "assets/settings.py.template", target)
    namespace = runpy.run_path(str(target))
    settings_type = namespace["HttpSettings"]
    defaults = settings_type()
    assert defaults.cors_origins == ()
    assert "*" not in defaults.trusted_hosts
    assert not defaults.docs_enabled
    accepted = settings_type(cors_origins=("https://app.example.test:8443",))
    assert accepted.cors_origins == ("https://app.example.test:8443",)
    for overrides in (
        {"trusted_hosts": ("*",)},
        {"trusted_hosts": ()},
        {"cors_origins": ("*",)},
        {"cors_origins": ("https://app.example.test/",)},
        {"cors_origins": ("app.example.test",)},
        {"api_prefix": "/v1"},
        {"max_body_bytes": 0},
        {"unknown": 1},
    ):
        with pytest.raises(ValueError, match="validation error"):
            settings_type(**overrides)


# kit-auth templates


def test_policy_is_closed_and_scopes_only_narrow(tmp_path: Path) -> None:
    target = tmp_path / "policy.py"
    shutil.copyfile(_AUTH / "assets/policy.py.template", target)
    policy = runpy.run_path(str(target))
    permission = policy["Permission"]
    build = policy["principal_from_claims"]
    allowed = policy["is_allowed"]
    editor = build({"sub": "u-1", "roles": ["editor", "root"], "scope": "items.read x"})
    assert {role.value for role in editor.roles} == {"editor"}
    assert editor.scopes == frozenset({"items.read"})
    assert allowed(editor, permission.ITEMS_READ)
    assert not allowed(editor, permission.ITEMS_WRITE)
    service = build({"sub": "svc", "roles": ["editor"], "client_id": "worker"})
    assert service.scopes is None
    assert allowed(service, permission.ITEMS_WRITE)
    assert not allowed(service, permission.ITEMS_DELETE)
    assert not allowed(
        build({"sub": "u", "roles": ["superuser"]}), permission.ITEMS_READ
    )
    assert not allowed(
        build({"sub": "u", "roles": ["admin"], "scope": ""}), permission.ITEMS_READ
    )
    assert "u-1" not in repr(editor)
    assert policy["scopes_granting"](permission.ITEMS_DELETE) == ("items.admin",)
    for claims in (
        {},
        {"sub": ""},
        {"sub": "u", "roles": "admin"},
        {"sub": "u", "scope": 1},
    ):
        with pytest.raises(policy["ClaimsError"]):
            build(claims)


def test_token_adapter_pins_asymmetric_algorithms_and_claims() -> None:
    tree = _tree(_AUTH / "assets/tokens.py.template")
    algorithms = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "ASYMMETRIC_ALGORITHMS"
            for target in node.targets
        )
    )
    values = {
        node.value
        for node in ast.walk(algorithms)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert values
    assert not any(value.upper().startswith(("HS", "NONE")) for value in values)
    decode = next(
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and ast.unparse(call.func) == "jwt.decode"
    )
    assert {keyword.arg for keyword in decode.keywords} >= {
        "key",
        "algorithms",
        "audience",
        "issuer",
        "leeway",
        "options",
    }
    text = (_AUTH / "assets/tokens.py.template").read_text(encoding="utf-8")
    assert "verify_signature" not in text
    assert "get_unverified_header" in text
    assert "def __post_init__" in text


def test_security_dependencies_follow_rfc_6750() -> None:
    path = _AUTH / "assets/security.py.template"
    tree = _tree(path)
    text = path.read_text(encoding="utf-8")
    authenticate = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name == "authenticate"
    )
    assert isinstance(authenticate, ast.FunctionDef)
    bearer = next(
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and ast.unparse(call.func) == "HTTPBearer"
    )
    assert "auto_error=False" in ast.unparse(bearer)
    assert 'error="invalid_token"' in text
    assert 'error="insufficient_scope"' in text
    assert "HTTPStatus.UNAUTHORIZED" in text
    assert "HTTPStatus.FORBIDDEN" in text
    assert "credentials.credentials)" in text
    assert 'logger.info("bearer token rejected: %s", error.reason)' in text


def test_auth_test_template_covers_attack_cases() -> None:
    text = (_AUTH / "assets/test_auth.py.template").read_text(encoding="utf-8")
    for case in (
        "EXPIRED",
        "NOT_YET_VALID",
        "WRONG_AUDIENCE",
        "WRONG_ISSUER",
        "MISSING_CLAIM",
        "UNKNOWN_KEY",
        "BAD_SIGNATURE",
        "WRONG_TYPE",
        '"alg": "none"',
        '"alg": "HS256"',
        "insufficient_scope",
        "caplog",
    ):
        assert case in text, case
    assert "rsa.generate_private_key" in text


# kit-api-testing templates


def test_postman_collection_is_v21_with_tests_and_no_secrets() -> None:
    collection = json.loads(
        (_API_TESTING / "assets/shop.postman_collection.json.template").read_text(
            encoding="utf-8"
        )
    )
    assert collection["info"]["schema"] == _POSTMAN_SCHEMA
    assert collection["auth"]["bearer"][0]["value"] == "{{accessToken}}"
    requests = [
        request
        for folder in collection["item"]
        for request in folder["item"]
        if "request" in request
    ]
    assert len(requests) >= 5
    for request in requests:
        listens = {event["listen"] for event in request.get("event", [])}
        assert "test" in listens, request["name"]
        assert str(request["request"]["url"]).startswith("{{baseUrl}}")
    statuses = json.dumps(collection)
    for status in ("401", "404", "413", "422"):
        assert f"have.status({status})" in statuses


def test_postman_environment_holds_placeholders_only() -> None:
    environment = json.loads(
        (_API_TESTING / "assets/local.postman_environment.json.template").read_text(
            encoding="utf-8"
        )
    )
    assert environment["_postman_variable_scope"] == "environment"
    values = {item["key"]: item for item in environment["values"]}
    assert values["accessToken"] == {
        "key": "accessToken",
        "value": "",
        "type": "secret",
        "enabled": True,
    }
    assert values["baseUrl"]["value"].startswith("http://localhost")


def test_http_file_and_schemathesis_template_contracts() -> None:
    http = (_API_TESTING / "assets/shop.http.template").read_text(encoding="utf-8")
    assert "Authorization: Bearer {{accessToken}}" in http
    assert not re.search(r"Bearer\s+ey", http)
    assert http.count("###") >= 5
    tree = _tree(_API_TESTING / "assets/test_openapi_contract.py.template")
    text = ast.unparse(tree)
    assert "schemathesis.openapi.from_asgi('/openapi.json'" in text
    assert "@schema.parametrize()" in text
    assert "case.call_and_validate(" in text
    fixture = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "auth_headers"
    )
    assert "scope='session'" in ast.unparse(fixture.decorator_list[0])


# kit-cli-tool templates


@pytest.fixture
def cli_package(tmp_path: Path) -> Path:
    package = tmp_path / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(_CLI / "assets/cli.py.template", package / "cli.py")
    shutil.copyfile(_CLI / "assets/__main__.py.template", package / "__main__.py")
    return package


def test_cli_template_main_returns_codes_and_separates_streams(
    cli_package: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = runpy.run_path(str(cli_package / "cli.py"))
    main = cli["main"]
    order = tmp_path / "order.json"
    order.write_text(
        json.dumps({"lines": [{"unit_price": "0.10", "quantity": 3}]}), encoding="utf-8"
    )
    assert main(["--json", "total", str(order)], env={}) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"currency": "EUR", "lines": 1, "total": "0.30"}
    assert captured.err == ""
    assert main(["total", str(tmp_path / "missing.json")], env={}) == 66
    assert "not found" in capsys.readouterr().err
    assert main(["total"], env={}) == 2
    assert main(["config"], env={"SHOP_PRECISION": "9"}) == 78
    assert main(["config"], env={"SHOP_API_TOKEN": "s3cr3t-value"}) == 0
    captured = capsys.readouterr()
    assert "api_token = set" in captured.out
    assert "s3cr3t-value" not in captured.out + captured.err


def test_cli_test_template_passes_against_the_cli_template(
    cli_package: Path, tmp_path: Path
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    shutil.copyfile(_CLI / "assets/test_cli.py.template", tests / "test_cli.py")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter on copied templates
        [
            sys.executable,
            "-m",
            "pytest",
            str(tests),
            "-q",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(cli_package.parent)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout
