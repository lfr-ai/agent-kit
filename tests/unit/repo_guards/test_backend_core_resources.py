"""Executable backend-core assets behave as documented on synthetic sources."""

import ast
import json
from pathlib import Path
import runpy

import pytest
import yaml

_SKILLS = Path(__file__).resolve().parents[3] / "packages/backend/.apm/skills"
_SERVICE = _SKILLS / "kit-python-service"
_DOMAIN = _SKILLS / "kit-domain-model"
_API = _SKILLS / "kit-api-contracts"
_PYTHON = runpy.run_path(str(_SERVICE / "assets/check_python.py"))
_ORDERING = runpy.run_path(str(_SERVICE / "assets/check_method_ordering.py"))
_WIRING = runpy.run_path(str(_SERVICE / "assets/check_backend_wiring.py"))
_BINDING = runpy.run_path(str(_DOMAIN / "assets/check_port_adapter_binding.py"))
_OPENAPI = runpy.run_path(str(_API / "assets/compare_openapi.py"))
_REDUNDANCY = runpy.run_path(str(_API / "assets/check_response_model_redundancy.py"))
_TOOL_WORDS = ("read", "search", "edit", "execute", "write", "bash", "grep", "glob")


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# check_python.py


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("import typing\nvalue: typing.Any = 1\n", "typing.Any"),
        ("import typing\ntyping.cast(int, 1)\n", "typing.cast"),
        (
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, kw_only=True)\nclass Value:\n    x: int\n"
            ),
            "slots=True",
        ),
        ("try:\n    pass\nexcept:\n    pass\n", "bare 'except:'"),
    ],
)
def test_python_checker_rejects_new_violations(source: str, message: str) -> None:
    findings = _PYTHON["violations"](source, "mod.py")
    assert any(message in finding for finding in findings)
    assert all(finding.startswith("mod.py:") for finding in findings)


def test_python_checker_bool_trap_is_opt_in_and_exempts_tests() -> None:
    source = (
        "def run(force: bool) -> None: ...\n"
        "def run_ok(*, force: bool) -> None: ...\n"
        "def test_case(flag: bool) -> None: ...\n"
    )
    assert _PYTHON["violations"](source, "m.py") == []
    rules = _PYTHON["ALL_RULES"]
    findings = _PYTHON["violations"](source, "m.py", rules=rules)
    assert findings == [
        "m.py:1: positional bool parameter 'force'; make it keyword-only"
    ]


def test_python_checker_magic_numbers_are_opt_in_and_allow_named_constants() -> None:
    source = (
        "from typing import Final, Literal\n"
        "_RETRIES = 3\n"
        "LIMITS: Final = {'size': 64 * 1024}\n"
        "WIDTH, HEIGHT = 80, 24\n"
        "class Policy:\n"
        "    TIMEOUT = 2.5\n"
        "def mode() -> Literal[2]: ...\n"
        "def run(items: list[int], timeout: float = 30.0) -> int:\n"
        "    if len(items) > 10 or items[-1] or items[0] == 1:\n"
        "        return -2\n"
        "    width = 7\n"
        "    return _RETRIES + width\n"
    )
    assert _PYTHON["violations"](source, "m.py") == []
    findings = _PYTHON["violations"](source, "m.py", rules=frozenset({"magic-number"}))
    assert findings == [
        "m.py:8: magic number 30.0; name it as an UPPER_CASE constant",
        "m.py:9: magic number 10; name it as an UPPER_CASE constant",
        "m.py:10: magic number -2; name it as an UPPER_CASE constant",
        "m.py:11: magic number 7; name it as an UPPER_CASE constant",
    ]


def test_python_checker_main_enables_magic_numbers_by_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "m.py", "def f() -> int:\n    return 42\n")
    assert _PYTHON["main"]([str(path)]) == 0
    assert _PYTHON["main"]([str(path), "--magic-numbers"]) == 1
    assert "m.py:2: magic number 42" in capsys.readouterr().err


def test_python_checker_checks_production_templates_but_not_fixture_literals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = _write(tmp_path, "settings.py.template", "timeout = 30\n")
    _write(tmp_path, "test_settings.py.template", "expected = 30\n")
    _write(tmp_path, "conftest.py.template", "fixture = 30\n")
    _write(tmp_path, ".venv/ignored.py.template", "value = 30\n")
    assert _PYTHON["main"]([str(tmp_path), "--only", "magic-number"]) == 0
    options = [str(tmp_path), "--templates", "--only", "magic-number"]
    assert _PYTHON["main"](options) == 1
    assert capsys.readouterr().err.splitlines() == [
        f"{bad}:1: magic number 30; name it as an UPPER_CASE constant"
    ]
    bad.write_text(
        "_TIMEOUT_SECONDS = 30\ntimeout = _TIMEOUT_SECONDS\n", encoding="utf-8"
    )
    assert _PYTHON["main"](options) == 0


def test_python_checker_main_reports_and_respects_disable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = _write(tmp_path, "pkg/good.py", '"""Module ``name``."""\n')
    bad = _write(tmp_path, "pkg/bad.py", "try:\n    pass\nexcept:\n    pass\n")
    assert _PYTHON["main"]([str(good)]) == 0
    assert _PYTHON["main"]([str(tmp_path / "pkg")]) == 1
    assert f"{bad}:3:" in capsys.readouterr().err
    assert _PYTHON["main"]([str(bad), "--disable", "bare-except"]) == 0


def test_python_checker_excludes_relative_directories_only(tmp_path: Path) -> None:
    root = tmp_path / "build" / "project"
    _write(root, "src/bad.py", "from typing import Any\n")
    _write(root, ".venv/lib/skipped.py", "from typing import Any\n")
    files, problems = _PYTHON["collect"]([root], excluded=frozenset({".venv", "build"}))
    assert problems == []
    assert [path.name for path in files] == ["bad.py"]


# check_method_ordering.py


def test_ordering_reports_helper_defined_before_sole_caller() -> None:
    source = "def _helper():\n    return 1\n\n\ndef run():\n    return _helper()\n"
    assert _ORDERING["check_source"](source, "m.py") == [
        (
            "m.py:1: private helper '_helper' is defined before its sole caller "
            "'run' (line 5); move it after the caller"
        )
    ]


def test_ordering_accepts_stepdown_and_ambiguous_helpers() -> None:
    source = (
        "def run():\n    return _helper() + _shared()\n\n"
        "def other():\n    return _shared()\n\n"
        "def _helper():\n    return 1\n\n"
        "def _shared():\n    return 2\n"
    )
    assert _ORDERING["check_source"](source, "m.py") == []


def test_ordering_ignores_definition_time_references() -> None:
    source = (
        "def _decorate(function):\n    return function\n\n"
        "@_decorate\ndef run():\n    return _decorate\n"
    )
    assert _ORDERING["check_source"](source, "m.py") == []


def test_ordering_checks_class_scope_and_inverse_order() -> None:
    source = (
        "class Service:\n"
        "    def _load(self):\n        return 1\n\n"
        "    def run(self):\n        return self._load()\n"
    )
    findings = _ORDERING["check_source"](source, "m.py")
    assert findings
    assert "'_load'" in findings[0]
    assert _ORDERING["check_source"](source, "m.py", scopes=frozenset({"module"})) == []
    assert _ORDERING["check_source"](source, "m.py", order="before") == []


def test_ordering_rejects_unknown_order_and_supports_ignore(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown order"):
        _ORDERING["check_source"]("", "m.py", order="sideways")
    path = _write(tmp_path, "m.py", "def _a():\n    pass\n\ndef run():\n    _a()\n")
    assert _ORDERING["main"]([str(path)]) == 1
    assert _ORDERING["main"]([str(path), "--ignore", "^_a$"]) == 0
    assert _ORDERING["main"]([str(path), "--ignore", "("]) == 2


# check_backend_wiring.py


def _wiring_tree(root: Path, presentation_import: str) -> Path:
    src = root / "src"
    for package in ("shop", "shop/presentation", "shop/infrastructure"):
        _write(src, f"{package}/__init__.py", "")
    _write(src, "shop/infrastructure/db.py", "class Database: ...\n")
    _write(src, "shop/presentation/api.py", f"{presentation_import}\n")
    _write(src, "shop/composition.py", "from shop.infrastructure.db import Database\n")
    return src


@pytest.mark.parametrize(
    "statement",
    [
        "from shop.infrastructure.db import Database",
        "from ..infrastructure import db",
        "import shop.infrastructure.db",
    ],
)
def test_wiring_rejects_presentation_importing_infrastructure(
    tmp_path: Path, statement: str, capsys: pytest.CaptureFixture[str]
) -> None:
    src = _wiring_tree(tmp_path, statement)
    assert _WIRING["main"]([str(src), "--package", "shop"]) == 1
    output = capsys.readouterr().out
    assert (
        "shop/presentation/api.py:1: presentation module 'shop.presentation.api'"
        in output
    )
    assert "composition.py" not in output


def test_wiring_accepts_clean_layers_and_type_checking_option(tmp_path: Path) -> None:
    clean = _wiring_tree(tmp_path / "clean", "import json")
    assert _WIRING["main"]([str(clean), "--package", "shop"]) == 0
    guarded = _wiring_tree(
        tmp_path / "guarded",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from shop.infrastructure.db import Database",
    )
    assert _WIRING["main"]([str(guarded), "--package", "shop"]) == 1
    assert (
        _WIRING["main"]([str(guarded), "--package", "shop", "--ignore-type-checking"])
        == 0
    )


def test_wiring_supports_module_rules_and_rejects_bad_rules(tmp_path: Path) -> None:
    src = _wiring_tree(tmp_path, "import sqlalchemy.orm")
    assert _WIRING["main"]([str(src), "--package", "shop"]) == 0
    arguments = [
        str(src),
        "--package",
        "shop",
        "--forbid-module",
        "presentation:sqlalchemy",
    ]
    assert _WIRING["main"](arguments) == 1
    assert (
        _WIRING["main"](
            [str(src), "--package", "shop", "--forbid", "missing-separator"]
        )
        == 2
    )
    rule = _WIRING["parse_rule"]("core: application , infrastructure")
    assert rule.targets == ("application", "infrastructure")


# check_port_adapter_binding.py

_PORTS = """
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...


class Store(Protocol):
    @property
    def name(self) -> str: ...

    def get(self, key: str) -> str | None: ...

    async def put(self, key: str, value: str) -> None: ...
"""


def test_binding_accepts_structural_and_inherited_adapters(tmp_path: Path) -> None:
    core = _write(tmp_path, "core/ports.py", _PORTS)
    adapters = _write(
        tmp_path,
        "infra/adapters.py",
        "class Base:\n    def get(self, key): return None\n\n"
        "class MemoryStore(Base):\n"
        "    def __init__(self):\n        self.name = 'memory'\n"
        "    async def put(self, key, value): return None\n\n"
        "class SystemClock:\n    def now(self): return 0.0\n",
    )
    assert (
        _BINDING["main"](["--core", str(core.parent), "--adapters", str(adapters)]) == 0
    )


def test_binding_reports_missing_and_async_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    core = _write(tmp_path, "core/ports.py", _PORTS)
    adapters = _write(
        tmp_path,
        "infra/adapters.py",
        "class PartialStore:\n    name = 'x'\n"
        "    def get(self, key): return None\n"
        "    def put(self, key, value): return None\n",
    )
    assert _BINDING["main"](["--core", str(core), "--adapters", str(adapters)]) == 1
    output = capsys.readouterr().out
    assert "port 'Clock' has no adapter implementing all of: now" in output
    assert "closest 'PartialStore'" in output
    assert "put (async mismatch)" in output
    arguments = ["--core", str(core), "--adapters", str(adapters), "--ignore", "."]
    assert _BINDING["main"](arguments) == 0


def test_binding_includes_members_of_parent_ports() -> None:
    core = _BINDING["classes_in_source"](
        "from typing import Protocol\n"
        "class Reader(Protocol):\n    def get(self): ...\n"
        "class Writer(Reader, Protocol):\n    def put(self): ...\n",
        "ports.py",
    )
    adapters = _BINDING["classes_in_source"](
        "class OnlyPut:\n    def put(self): ...\n", "infra.py"
    )
    findings = _BINDING["unbound_ports"](core, adapters)
    assert any(
        "'Writer'" in finding and "lacks: get" in finding for finding in findings
    )


# compare_openapi.py


def _spec() -> dict[str, object]:
    return {
        "openapi": "3.1.1",
        "paths": {
            "/orders": {
                "get": {
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}}
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Order"}
                                }
                            }
                        }
                    },
                },
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OrderIn"}
                            }
                        }
                    },
                    "responses": {"201": {"description": "created"}},
                },
            }
        },
        "components": {
            "schemas": {
                "Order": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "note": {"type": "string"},
                    },
                },
                "OrderIn": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["draft", "confirmed"]},
                        "sku": {"type": "string", "maxLength": 20},
                    },
                },
            }
        },
    }


def _messages(old: dict[str, object], new: dict[str, object]) -> list[str]:
    return [
        f"{change.severity}: {change.location}: {change.message}"
        for change in _OPENAPI["compare"](old, new)
    ]


def test_openapi_identical_descriptions_have_no_changes() -> None:
    assert _messages(_spec(), _spec()) == []


def test_openapi_reports_breaking_request_and_response_changes() -> None:
    new = json.loads(json.dumps(_spec()))
    operation = new["paths"]["/orders"]["get"]
    operation["parameters"][0]["required"] = True
    operation["security"] = [{"bearer": []}]
    schemas = new["components"]["schemas"]
    del schemas["Order"]["properties"]["note"]
    schemas["Order"]["properties"]["id"]["type"] = ["string", "null"]
    schemas["OrderIn"]["properties"]["status"]["enum"] = ["draft"]
    schemas["OrderIn"]["properties"]["sku"]["maxLength"] = 10
    schemas["OrderIn"]["required"] = ["sku"]
    del new["paths"]["/orders"]["post"]["responses"]["201"]
    messages = "\n".join(_messages(_spec(), new))
    for expected in (
        "query parameter 'limit' became required",
        "security requirement added",
        "/note: response property removed",
        "/id: type changed",
        'enum values no longer accepted: "confirmed"',
        "maxLength tightened from 20 to 10",
        "/sku: property became required",
        "response 201 removed",
    ):
        assert expected in messages


def test_openapi_reports_removed_operations_and_warnings() -> None:
    new = json.loads(json.dumps(_spec()))
    del new["paths"]["/orders"]["post"]
    new["components"]["schemas"]["Order"]["properties"]["id"]["enum"] = ["a"]
    new["paths"]["/orders"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] = {"$ref": "https://example.com/order.json"}
    messages = _messages(_spec(), new)
    assert "breaking: POST /orders: operation removed" in messages
    assert any("remote reference" in message for message in messages)


def test_openapi_main_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = _write(tmp_path, "old.json", json.dumps(_spec()))
    same = _write(tmp_path, "same.json", json.dumps(_spec()))
    changed = json.loads(json.dumps(_spec()))
    del changed["paths"]["/orders"]["get"]["parameters"]
    removed_param = _write(tmp_path, "warn.json", json.dumps(changed))
    assert _OPENAPI["main"]([str(old), str(same)]) == 0
    assert _OPENAPI["main"]([str(old), str(removed_param)]) == 0
    assert "warning" in capsys.readouterr().out
    assert _OPENAPI["main"]([str(old), str(removed_param), "--strict"]) == 1
    arguments = [str(old), str(removed_param), "--strict", "--ignore-path", "GET"]
    assert _OPENAPI["main"](arguments) == 0
    broken = _write(tmp_path, "broken.json", "[]")
    assert _OPENAPI["main"]([str(old), str(broken)]) == 2


# check_response_model_redundancy.py

_ROUTES = """
from typing import List, Optional

@router.get("/a", response_model=Item)
def same() -> Item: ...

@router.get("/b", response_model=Optional[Item])
async def normalized() -> Item | None: ...

@router.get("/c", response_model=List[Item])
def builtin() -> list[Item]: ...

@router.get("/d", response_model=PublicItem)
def filtered() -> Item: ...

@router.get("/e", response_model=None)
def disabled() -> Response: ...

@router.get("/f")
def untyped(): ...
"""


def test_redundancy_flags_only_identical_models() -> None:
    findings = _REDUNDANCY["check_source"](_ROUTES, "api.py")
    assert [finding.split("'")[1] for finding in findings] == [
        "same",
        "normalized",
        "builtin",
    ]
    assert findings[0].startswith("api.py:4: route 'same' passes response_model=Item")


def test_redundancy_require_type_and_main(tmp_path: Path) -> None:
    findings = _REDUNDANCY["check_source"](_ROUTES, "api.py", require_type=True)
    assert any("'untyped' declares no return annotation" in item for item in findings)
    clean = _write(tmp_path, "clean.py", '@app.post("/x")\ndef create() -> Item: ...\n')
    noisy = _write(tmp_path, "noisy.py", _ROUTES)
    assert _REDUNDANCY["main"]([str(clean)]) == 0
    assert _REDUNDANCY["main"]([str(noisy)]) == 1
    assert _REDUNDANCY["main"]([str(noisy), "--method", "post"]) == 0


# Templates and native roles


@pytest.mark.parametrize(
    "path",
    sorted(
        path
        for skill in (_SERVICE, _DOMAIN, _API)
        for path in (skill / "assets").glob("*.template")
    ),
    ids=lambda path: path.name,
)
def test_templates_parse(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    name = path.name.removesuffix(".template")
    if name.endswith(".py"):
        ast.parse(text, filename=str(path))
    elif name.endswith(".json"):
        assert isinstance(json.loads(text), dict)
    elif name.endswith((".yml", ".yaml")):
        assert isinstance(yaml.safe_load(text), dict)
    else:
        assert text.strip()


def test_native_roles_are_structured_procedures() -> None:
    asset = json.loads((_SERVICE / "assets/agents.json").read_text(encoding="utf-8"))
    roles = {role["id"]: role for role in asset["roles"]}
    assert set(roles) == {
        "kit-ddd",
        "kit-sdd",
        "kit-tdd",
        "kit-testing",
        "kit-backend-implementer",
        "kit-contract-iac-lint",
    }
    for role in roles.values():
        body = role["body"]
        assert 15 <= len(body.splitlines()) <= 125
        assert "\n" not in role["description"]
        assert len(role["description"]) <= 180
        for heading in (
            "# Mission",
            "# Method",
            "# Quality gates",
            "# Stop conditions",
        ):
            assert heading in body
        words = set(body.lower().replace(".", " ").replace(",", " ").split())
        assert not words.intersection(_TOOL_WORDS)
