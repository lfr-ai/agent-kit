"""Rate limiting and resilience templates keep their documented contracts."""

import ast
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
_FASTAPI = _BACKEND / "skills/kit-fastapi-service"
_SERVICE = _BACKEND / "skills/kit-python-service"
_INSTRUCTION = _BACKEND / "instructions/kit-fastapi.instructions.md"
_TEMPLATES = (
    _FASTAPI / "assets/rate_limit.py.template",
    _FASTAPI / "assets/redis_rate_limit.py.template",
    _FASTAPI / "assets/test_redis_rate_limit.py.template",
    _FASTAPI / "assets/test_api.py.template",
    _FASTAPI / "assets/app.py.template",
    _FASTAPI / "assets/settings.py.template",
    _SERVICE / "assets/resilience.py.template",
    _SERVICE / "assets/test_resilience.py.template",
)
_DOCUMENTS = (
    _FASTAPI / "SKILL.md",
    _FASTAPI / "references/rate-limiting.md",
    _SERVICE / "SKILL.md",
    _SERVICE / "references/resilience.md",
    _INSTRUCTION,
)
_LINK = re.compile(r"\]\(([^)\s#]+)")
_DRAFT = "draft-ietf-httpapi-ratelimit-headers-11"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method(cls: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name == name
    )


def _string_constant(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError(name)


def _body_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split("---\n", 2)[2].splitlines())


def _links(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {target for target in _LINK.findall(text) if "://" not in target}


# Files and links


@pytest.mark.parametrize(
    "path",
    _TEMPLATES + _DOCUMENTS,
    ids=lambda path: path.relative_to(_BACKEND).as_posix(),
)
def test_files_are_lf_utf8_without_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    raw.decode("utf-8")


@pytest.mark.parametrize("path", _TEMPLATES, ids=lambda path: path.name)
def test_python_templates_parse_and_name_a_destination(path: Path) -> None:
    tree = _tree(path)
    docstring = ast.get_docstring(tree)
    assert docstring
    assert re.search(r"Copy into ``[^`]+\.py``", docstring)
    assert not any(
        isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(tree)
    )


@pytest.mark.parametrize(
    ("skill", "targets"),
    [
        (
            _FASTAPI,
            {
                "references/rate-limiting.md",
                "assets/redis_rate_limit.py.template",
                "assets/test_redis_rate_limit.py.template",
                "assets/rate_limit.py.template",
            },
        ),
        (
            _SERVICE,
            {
                "references/resilience.md",
                "assets/resilience.py.template",
                "assets/test_resilience.py.template",
            },
        ),
    ],
    ids=["fastapi", "python-service"],
)
def test_skills_link_new_resources_within_budget(
    skill: Path, targets: set[str]
) -> None:
    skill_md = skill / "SKILL.md"
    assert targets <= _links(skill_md)
    assert _body_lines(skill_md) <= 300
    owned = (skill / target for target in targets if target.endswith(".md"))
    for document in (skill_md, *owned):
        for target in _links(document):
            resolved = (document.parent / target).resolve()
            assert resolved.is_file(), (document.name, target)
            assert resolved.is_relative_to(skill.resolve()), (document.name, target)


def test_references_cite_official_sources_and_name_owners() -> None:
    rate = (_FASTAPI / "references/rate-limiting.md").read_text(encoding="utf-8")
    resilience = (_SERVICE / "references/resilience.md").read_text(encoding="utf-8")
    assert "Reviewed 2026-10-23" in rate
    assert _DRAFT in rate
    assert "work in progress" in rate
    for owner in ("`kit-edge-networking`", "`kit-api-gateway`", "`kit-auth`"):
        assert owner in rate
    for owner in (
        "`kit-api-contracts`",
        "`kit-llm-client`",
        "`kit-task-queue`",
        "`kit-caching`",
        "`kit-sql-persistence`",
    ):
        assert owner in resilience
    for text, heading in ((rate, "## Primary sources"), (resilience, "## Sources")):
        sources = text.split(heading, 1)[1]
        urls = re.findall(r"\]\((\S+)\)", sources)
        assert len(urls) >= 10
        assert all(url.startswith("https://") for url in urls)


def test_fastapi_instruction_stays_within_budget() -> None:
    lines = _INSTRUCTION.read_text(encoding="utf-8").splitlines()
    header, body = "\n".join(lines).split("---\n", 2)[1:]
    bullets = [line for line in body.splitlines() if line.startswith("- ")]
    assert len(lines) <= 20
    assert set(yaml.safe_load(header)) == {"description", "applyTo"}
    assert 4 <= len(bullets) <= 10
    assert any("Rate limit" in bullet for bullet in bullets)
    assert "`kit-fastapi-service`" in bullets[-1]


# kit-fastapi-service rate limiting templates


def test_store_protocol_and_decision_stay_compatible() -> None:
    tree = _tree(_FASTAPI / "assets/rate_limit.py.template")
    hit = _method(_class(tree, "RateLimitStore"), "hit")
    assert isinstance(hit, ast.AsyncFunctionDef)
    assert [arg.arg for arg in hit.args.args] == ["self", "key"]
    assert [arg.arg for arg in hit.args.kwonlyargs] == ["limit", "window_seconds"]
    assert hit.returns is not None
    assert ast.unparse(hit.returns) == "RateDecision"
    fields = [
        node.target.id
        for node in _class(tree, "RateDecision").body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]
    assert fields[:3] == ["allowed", "remaining", "retry_after_seconds"]
    error = _class(tree, "RateLimitStoreError")
    assert [ast.unparse(base) for base in error.bases] == ["OSError"]
    members = {
        node.targets[0].id
        for node in _class(tree, "FailureMode").body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert members == {"OPEN", "CLOSED"}


def test_middleware_requires_an_explicit_failure_mode_and_exempts_health() -> None:
    text = (_FASTAPI / "assets/rate_limit.py.template").read_text(encoding="utf-8")
    tree = ast.parse(text)
    init = _method(_class(tree, "RateLimitMiddleware"), "__init__")
    keywords = dict(zip(init.args.kwonlyargs, init.args.kw_defaults, strict=True))
    required = {arg.arg for arg, default in keywords.items() if default is None}
    assert required == {"store", "default_policy", "failure_mode"}
    assert "/health/live" in text
    assert "/health/ready" in text
    assert '"Retry-After"' in text
    assert _DRAFT in text
    assert ";q={policy.limit};w={policy.window_seconds}" in text


def test_gcra_script_is_atomic_single_key_and_uses_server_time() -> None:
    tree = _tree(_FASTAPI / "assets/redis_rate_limit.py.template")
    script = _string_constant(tree, "GCRA_SCRIPT")
    assert "redis.call('TIME')" in script
    assert "'PX'" in script
    assert set(re.findall(r"KEYS\[(\d+)\]", script)) == {"1"}
    assert "os.time" not in script
    store = _class(tree, "RedisRateLimitStore")
    assert {"bind", "hit", "storage_key"} <= {
        node.name
        for node in store.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    handlers = [
        ast.unparse(node.type)
        for node in ast.walk(_method(store, "hit"))
        if isinstance(node, ast.ExceptHandler) and node.type is not None
    ]
    assert handlers == ["(RedisError, TimeoutError)"]
    module_calls = [
        ast.unparse(node.value.func)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
    ]
    assert "Redis.from_url" not in module_calls


def test_redis_test_template_skips_without_a_server_url() -> None:
    text = (_FASTAPI / "assets/test_redis_rate_limit.py.template").read_text(
        encoding="utf-8"
    )
    assert 'os.environ.get("SHOP_TEST_REDIS_URL")' in text
    assert "pytest.mark.skipif" in text
    assert "asyncio.gather" in text
    assert "flushdb" not in text.lower()


def test_http_settings_validate_rate_limit_fields(tmp_path: Path) -> None:
    target = tmp_path / "http_settings.py"
    shutil.copyfile(_FASTAPI / "assets/settings.py.template", target)
    settings_type = runpy.run_path(str(target))["HttpSettings"]
    defaults = settings_type()
    assert defaults.rate_limit_failure_mode == "open"
    assert defaults.rate_limit_headers is False
    route = {
        "name": "order-writes",
        "path_prefix": "/api/v1/orders",
        "methods": ["POST"],
        "requests": 10,
        "window_seconds": 60,
    }
    accepted = settings_type(
        rate_limit_routes=[route], rate_limit_failure_mode="closed"
    )
    assert accepted.rate_limit_routes[0].methods == ("POST",)
    for overrides in (
        {"rate_limit_failure_mode": "sometimes"},
        {"rate_limit_routes": [route, route]},
        {"rate_limit_routes": [route | {"name": "default"}]},
        {"rate_limit_routes": [route | {"name": "Bad Name"}]},
        {"rate_limit_routes": [route | {"methods": ["FETCH"]}]},
        {"rate_limit_routes": [route | {"path_prefix": "orders"}]},
        {"rate_limit_routes": [route | {"requests": 0}]},
    ):
        with pytest.raises(ValueError, match="validation error"):
            settings_type(**overrides)


# kit-python-service resilience template


@pytest.fixture
def resilience_project(tmp_path: Path) -> Path:
    package = tmp_path / "shop/infrastructure"
    package.mkdir(parents=True)
    for folder in (tmp_path / "shop", package):
        (folder / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(
        _SERVICE / "assets/resilience.py.template", package / "resilience.py"
    )
    return tmp_path


def test_resilience_primitives_behave_without_waiting(resilience_project: Path) -> None:
    module = runpy.run_path(
        str(resilience_project / "shop/infrastructure/resilience.py")
    )
    policy = module["RetryPolicy"](
        attempts=3, base_delay_seconds=0.5, max_delay_seconds=1.5
    )
    assert [policy.backoff_ceiling(n) for n in range(4)] == [0.5, 1.0, 1.5, 1.5]
    assert all(0.0 <= module["full_jitter"](2.0) <= 2.0 for _ in range(50))
    with pytest.raises(ValueError, match="attempts"):
        module["RetryPolicy"](attempts=0)
    budget = module["RetryBudget"](max_tokens=2, token_ratio=1)
    budget.record_failure()
    assert not budget.allows_retry()
    budget.record_success()
    assert budget.allows_retry()


def test_resilience_test_template_passes_against_the_template(
    resilience_project: Path,
) -> None:
    tests = resilience_project / "tests"
    tests.mkdir()
    shutil.copyfile(
        _SERVICE / "assets/test_resilience.py.template", tests / "test_resilience.py"
    )
    (resilience_project / "pytest.ini").write_text(
        "[pytest]\nfilterwarnings =\n    error\n", encoding="utf-8"
    )
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
        cwd=resilience_project,
        env={**os.environ, "PYTHONPATH": str(resilience_project)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert " passed" in result.stdout
    assert "skipped" not in result.stdout
