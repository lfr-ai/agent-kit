"""Shared quality skills ship runnable checkers and parseable templates."""

import ast
import configparser
import json
import runpy
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SKILLS = _ROOT / "packages/shared/.apm/skills"
_HEXAGONAL = _SKILLS / "kit-hexagonal-architecture/assets"
_CONSISTENCY = _SKILLS / "kit-consistency/assets"
_TEST_FIRST = _SKILLS / "kit-test-first/assets"
_VERIFY = _SKILLS / "kit-verify-change/assets"
_OWNED = (
    "kit-hexagonal-architecture",
    "kit-consistency",
    "kit-test-first",
    "kit-verify-change",
)
_CHECKERS = (
    _HEXAGONAL / "check_ports_adapters.py",
    _CONSISTENCY / "check_naming.py",
    _CONSISTENCY / "check_class_file_naming.py",
    _TEST_FIRST / "check_test_hygiene.py",
    _TEST_FIRST / "check_test_naming.py",
)

type Namespace = dict[str, object]


def _load(path: Path) -> Namespace:
    return runpy.run_path(str(path))


def _function(namespace: Namespace, name: str) -> Callable[..., object]:
    value = namespace[name]
    assert callable(value)
    return value


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _templates(suffix: str) -> list[Path]:
    return sorted(
        path
        for skill in _OWNED
        for path in (_SKILLS / skill / "assets").glob(f"*{suffix}.template")
    )


@pytest.mark.parametrize("checker", _CHECKERS, ids=lambda path: path.stem)
def test_checker_self_test_reports_no_unmet_expectations(checker: Path) -> None:
    assert _function(_load(checker), "self_test")() == []


@pytest.mark.parametrize("checker", _CHECKERS, ids=lambda path: path.stem)
def test_checker_self_test_flag_exits_zero_and_says_passed(
    checker: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _function(_load(checker), "main")(["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


_PORT = """
from typing import Protocol

class InvoiceStore(Protocol):
    async def get(self, invoice_id: str) -> bytes: ...
    def put(self, invoice_id: str, *, overwrite: bool = False) -> None: ...
"""
_GOOD_ADAPTER = """
from ports import InvoiceStore

class FileInvoiceStore(InvoiceStore):
    async def get(self, invoice_id: str) -> bytes: return b""
    def put(self, invoice_id: str, *, overwrite: bool = False) -> None: pass
"""
_BAD_ADAPTER = """
from ports import InvoiceStore

class FileInvoiceStore(InvoiceStore):
    def get(self, invoice_id: str) -> bytes: return b""
    def put(self, key: str, *, overwrite: bool = False) -> None: pass
    def purge(self) -> None: pass
"""


def test_ports_checker_accepts_adapter_with_matching_signatures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ports = _write(tmp_path, "ports/store.py", _PORT)
    adapters = _write(tmp_path, "adapters/file_store.py", _GOOD_ADAPTER)
    main = _function(_load(_HEXAGONAL / "check_ports_adapters.py"), "main")
    assert main([str(adapters.parent), "--ports", str(ports.parent)]) == 0
    assert "agree" in capsys.readouterr().out


def test_ports_checker_reports_async_rename_and_extra_method_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ports = _write(tmp_path, "ports/store.py", _PORT)
    adapters = _write(tmp_path, "adapters/file_store.py", _BAD_ADAPTER)
    main = _function(_load(_HEXAGONAL / "check_ports_adapters.py"), "main")
    assert main([str(adapters.parent), "--ports", str(ports.parent)]) == 1
    lines = capsys.readouterr().out.splitlines()
    location = f"{adapters.as_posix()}:"
    assert any(
        line.startswith(location) and "is a method but port" in line for line in lines
    )
    assert any("'FileInvoiceStore.put'(key" in line for line in lines)
    assert any("'FileInvoiceStore.purge' is a public method" in line for line in lines)


def test_ports_checker_allow_extra_silences_only_the_named_method() -> None:
    namespace = _load(_HEXAGONAL / "check_ports_adapters.py")
    options = _function(namespace, "Options")(allow_extra=frozenset({"purge"}))
    findings = _function(namespace, "analyze")(
        [("ports.py", _PORT)], [("adapter.py", _BAD_ADAPTER)], options=options
    )
    assert isinstance(findings, list)
    messages: list[str] = []
    for finding in findings:
        message = getattr(finding, "message", None)
        assert isinstance(message, str)
        messages.append(message)
    assert not any("purge" in message for message in messages)
    assert any("is a method but port" in message for message in messages)


def test_ports_checker_requires_a_ports_path() -> None:
    main = _function(_load(_HEXAGONAL / "check_ports_adapters.py"), "main")
    with pytest.raises(SystemExit) as raised:
        main(["."])
    assert raised.value.code == 2


def test_ports_checker_reports_port_without_any_implementation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ports = _write(tmp_path, "ports/store.py", _PORT)
    main = _function(_load(_HEXAGONAL / "check_ports_adapters.py"), "main")
    assert main([str(ports.parent), "--ports", str(ports.parent)]) == 1
    assert "has no implementation" in capsys.readouterr().out
    assert (
        main([str(ports.parent), "--ports", str(ports.parent), "--allow-unimplemented"])
        == 0
    )


def test_naming_checker_accepts_snake_modules_and_kebab_docs(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/app/__init__.py", "")
    _write(tmp_path, "src/app/invoice_repository.py", "")
    _write(tmp_path, "docs/getting-started/index.md", "# Start\n")
    main = _function(_load(_CONSISTENCY / "check_naming.py"), "main")
    assert main([str(tmp_path), "--kebab-root", "docs"]) == 0


def test_naming_checker_reports_camel_module_and_snake_docs_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "src/app/InvoiceRepository.py", "")
    _write(tmp_path, "docs/release_notes/index.md", "# Notes\n")
    main = _function(_load(_CONSISTENCY / "check_naming.py"), "main")
    assert main([str(tmp_path), "--kebab-root", "docs"]) == 1
    output = capsys.readouterr().out
    assert "src/app/InvoiceRepository.py:1: module" in output
    assert (
        "docs/release_notes/:1: directory 'release_notes' is not kebab-case" in output
    )


def test_naming_checker_ignores_excluded_virtual_environment(tmp_path: Path) -> None:
    _write(tmp_path, ".venv/lib/Bad-Name.py", "")
    _write(tmp_path, "src/ok_module.py", "")
    main = _function(_load(_CONSISTENCY / "check_naming.py"), "main")
    assert main([str(tmp_path)]) == 0


def test_class_file_checker_accepts_module_named_after_its_class(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/http_client.py", "class HTTPClient: ...\nclass _Retry: ...\n")
    main = _function(_load(_CONSISTENCY / "check_class_file_naming.py"), "main")
    assert main([str(tmp_path)]) == 0


def test_class_file_checker_reports_mismatch_and_extra_public_class(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _write(
        tmp_path, "pkg/orders.py", "class OrderService: ...\nclass Ledger: ...\n"
    )
    main = _function(_load(_CONSISTENCY / "check_class_file_naming.py"), "main")
    assert main([str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert f"{module.as_posix()}:1: module 'orders.py' defines public classes" in output
    assert f"{module.as_posix()}:2: extra public class 'Ledger'" in output


def test_class_file_checker_affix_mode_and_exemptions_are_configurable(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path, "pkg/invoice_repository.py", "class SqliteInvoiceRepository: ...\n"
    )
    _write(tmp_path, "pkg/models.py", "class Invoice: ...\nclass Customer: ...\n")
    main = _function(_load(_CONSISTENCY / "check_class_file_naming.py"), "main")
    assert main([str(tmp_path)]) == 1
    assert main([str(tmp_path), "--match", "affix", "--exempt", "*/models.py"]) == 0


def test_snake_case_conversion_treats_acronyms_as_words() -> None:
    snake_case = _function(
        _load(_CONSISTENCY / "check_class_file_naming.py"), "snake_case"
    )
    assert snake_case("HTTPClient") == "http_client"
    assert snake_case("InvoicePDFExport") == "invoice_pdf_export"
    assert snake_case("Invoice") == "invoice"


def test_hygiene_checker_accepts_lazy_heavy_import_and_event_waits(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "tests/unit/test_report.py",
        "import asyncio\n"
        "async def test_report_waits_for_flush_event() -> None:\n"
        "    import pandas\n"
        "    await asyncio.sleep(0)\n",
    )
    main = _function(_load(_TEST_FIRST / "check_test_hygiene.py"), "main")
    assert main([str(tmp_path / "tests")]) == 0


def test_hygiene_checker_reports_heavy_import_sleep_and_duplicate_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _write(
        tmp_path,
        "tests/a/test_export.py",
        "import numpy\nimport time\ndef test_export_retries() -> None:\n"
        "    time.sleep(1)\n",
    )
    second = _write(tmp_path, "tests/b/test_export.py", "")
    main = _function(_load(_TEST_FIRST / "check_test_hygiene.py"), "main")
    assert main([str(tmp_path / "tests")]) == 1
    output = capsys.readouterr().out
    assert (
        f"{first.as_posix()}:1: module-level import of heavy module 'numpy'" in output
    )
    assert f"{first.as_posix()}:4: time.sleep" in output
    assert f"{second.as_posix()}:1: test module name 'test_export.py'" in output


def test_hygiene_checker_flags_can_disable_each_rule(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/a/test_export.py",
        "import numpy\nimport time\ndef test_export_retries() -> None:\n"
        "    time.sleep(1)\n",
    )
    _write(tmp_path, "tests/b/test_export.py", "")
    main = _function(_load(_TEST_FIRST / "check_test_hygiene.py"), "main")
    arguments = [
        str(tmp_path / "tests"),
        "--no-default-heavy",
        "--allow-sleep",
        "--allow-duplicate-basenames",
    ]
    assert main(arguments) == 0
    assert main([*arguments, "--heavy-module", "numpy"]) == 1


def test_naming_test_checker_accepts_descriptive_names(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_invoice.py",
        "def test_paid_invoice_cannot_be_voided() -> None: ...\n"
        "class TestSettlement:\n"
        "    def test_second_settlement_charges_once(self) -> None: ...\n",
    )
    main = _function(_load(_TEST_FIRST / "check_test_naming.py"), "main")
    assert main([str(tmp_path / "tests")]) == 0


def test_naming_test_checker_reports_generic_short_and_redefined_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _write(
        tmp_path,
        "tests/test_invoice.py",
        "def test_it() -> None: ...\n"
        "def test_1() -> None: ...\n"
        "def test_settle() -> None: ...\n"
        "def test_settle_twice_charges_once() -> None: ...\n"
        "def test_settle_twice_charges_once() -> None: ...\n",
    )
    main = _function(_load(_TEST_FIRST / "check_test_naming.py"), "main")
    assert main([str(tmp_path / "tests")]) == 1
    output = capsys.readouterr().out
    location = module.as_posix()
    assert f"{location}:1: test name 'test_it' is generic" in output
    assert f"{location}:2: test name 'test_1' is numbered" in output
    assert f"{location}:3: test name 'test_settle' has 1 word(s)" in output
    assert f"{location}:5: 'test_settle_twice_charges_once' redefines" in output


def test_naming_test_checker_min_words_and_allow_list_are_configurable(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "tests/test_invoice.py", "def test_settle() -> None: ...\n")
    main = _function(_load(_TEST_FIRST / "check_test_naming.py"), "main")
    assert main([str(tmp_path / "tests"), "--min-words", "1"]) == 0
    assert main([str(tmp_path / "tests"), "--allow", "test_settle"]) == 0


@pytest.mark.parametrize("template", _templates(".py"), ids=lambda path: path.name)
def test_python_template_is_valid_syntax(template: Path) -> None:
    ast.parse(template.read_text(encoding="utf-8"), filename=str(template))


@pytest.mark.parametrize("template", _templates(".json"), ids=lambda path: path.name)
def test_json_template_parses_as_an_object(template: Path) -> None:
    assert isinstance(json.loads(template.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize(
    "template",
    [*_templates(".yml"), *_templates(".yaml")],
    ids=lambda path: path.name,
)
def test_yaml_template_parses_as_a_mapping(template: Path) -> None:
    assert isinstance(yaml.safe_load(template.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize("template", _templates(".ini"), ids=lambda path: path.name)
def test_ini_template_parses_with_named_sections(template: Path) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(template.read_text(encoding="utf-8"))
    assert parser.sections()


def test_every_expected_template_kind_is_present() -> None:
    names = {
        path.name
        for suffix in (".py", ".json", ".yml", ".yaml", ".ini")
        for path in _templates(suffix)
    }
    assert {
        "importlinter.ini.template",
        "test_repository_contract.py.template",
        "conftest.py.template",
        "test_property.py.template",
        "pytest.ini.template",
        "run_gate.py.template",
        "pre-commit-config.yaml.template",
        "cspell.json.template",
        "ci-gate.yml.template",
    } <= names


def test_gate_template_selection_keeps_order_and_rejects_unknown_steps() -> None:
    namespace = _load(_VERIFY / "run_gate.py.template")
    select = _function(namespace, "select")
    steps = namespace["STEPS"]
    assert isinstance(steps, tuple)
    selected = select(steps, only=[], skip=[], include_slow=False)
    assert isinstance(selected, list)
    default = [getattr(step, "name", None) for step in selected]
    assert default[:3] == ["lock", "format", "lint"]
    assert "links" not in default
    chosen = select(steps, only=["links", "lint"], skip=[], include_slow=False)
    assert isinstance(chosen, list)
    assert [getattr(step, "name", None) for step in chosen] == ["lint", "links"]
    with pytest.raises(ValueError, match="unknown"):
        select(steps, only=["missing"], skip=[], include_slow=False)
