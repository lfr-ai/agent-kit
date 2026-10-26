"""AI package skill resources: checkers behave, templates parse and agree."""

import ast
from collections.abc import Mapping
import configparser
import json
from pathlib import Path
import re
import runpy

import pytest
import yaml

_SKILLS = Path(__file__).resolve().parents[3] / "packages/ai/.apm/skills"
_NAMES = (
    "kit-retrieval",
    "kit-langgraph",
    "kit-llm-client",
    "kit-server-streaming",
    "kit-task-queue",
)
_STREAM = _SKILLS / "kit-server-streaming/assets"
_QUEUE = _SKILLS / "kit-task-queue/assets"
_STREAM_CHECKER = runpy.run_path(str(_STREAM / "verify_stream_events.py"))
_QUEUE_CHECKER = runpy.run_path(str(_QUEUE / "verify_queue_messages.py"))
_COPY_TARGET = re.compile(r"Copy to (?P<quote>'|``)(?P<path>[\w/]+)\.py(?P=quote)")
_LINK = re.compile(r"\]\(([^)#\s]+)")


def _templates(suffix: str) -> list[Path]:
    return sorted(
        path
        for name in _NAMES
        for path in (_SKILLS / name / "assets").glob(f"*{suffix}")
    )


def _write(tmp_path: Path, name: str, value: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


# verify_stream_events.py


@pytest.mark.parametrize("defect", ["leading", "duplicate", "trailing", "non-finite"])
def test_stream_checker_rejects_invalid_json_grammar(
    tmp_path: Path, defect: str
) -> None:
    text = json.dumps(
        [
            {"seq": 1, "event": "start", "data": {}},
            {"seq": 2, "event": "end", "data": {"status": "completed"}},
        ]
    )
    if defect == "leading":
        text = text.replace("[", "[,", 1)
    elif defect == "duplicate":
        text = text.replace("}, {", "},, {", 1)
    elif defect == "trailing":
        text = text[:-1] + ",]"
    else:
        text = text.replace('"data": {}', '"data": {"value": NaN}', 1)
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")
    assert _STREAM_CHECKER["main"]([str(path)]) == 2


def _stream(*events: tuple[int, str, Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {"seq": seq, "event": event, "data": dict(data)} for seq, event, data in events
    ]


_COMPLETE = (
    (1, "start", {}),
    (2, "delta", {"text": "hi"}),
    (3, "end", {"status": "completed"}),
)


def test_stream_checker_accepts_the_shipped_manifest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _STREAM_CHECKER["main"]([str(_STREAM / "stream_template.json.template")])

    assert code == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("events", "message"),
    [
        (_stream((1, "start", {}), (2, "delta", {})), "no terminal 'end'"),
        (
            _stream((1, "start", {}), (3, "end", {"status": "completed"})),
            "expected seq 2",
        ),
        (
            _stream((1, "delta", {}), (2, "end", {"status": "completed"})),
            "begin with 'start'",
        ),
        (
            _stream(
                (1, "start", {}), (2, "tick", {}), (3, "end", {"status": "completed"})
            ),
            "unknown event",
        ),
        (_stream((1, "start", {}), (2, "end", {"status": "done"})), "needs status"),
        (
            _stream(
                (1, "start", {}), (2, "end", {"status": "completed"}), (3, "delta", {})
            ),
            "must be the last event",
        ),
        (
            _stream(
                (1, "start", {}),
                (2, "end", {"status": "completed"}),
                (3, "end", {"status": "completed"}),
            ),
            "duplicate 'end'",
        ),
        ([], "no events"),
        ([{"seq": 0, "event": "start", "data": []}], "positive integer"),
    ],
)
def test_stream_checker_reports_contract_violations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    events: list[dict[str, object]],
    message: str,
) -> None:
    path = _write(tmp_path, "stream.json", events)

    assert _STREAM_CHECKER["main"]([str(path)]) == 1
    output = capsys.readouterr().out
    assert message in output
    assert output.startswith(f"{path}:")


def test_stream_checker_reports_the_line_of_the_offending_event(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "stream.json",
        _stream(*_COMPLETE[:1], (2, "tick", {}), *_COMPLETE[2:]),
    )
    items = _STREAM_CHECKER["items_with_lines"](path.read_text(encoding="utf-8"))

    findings = _STREAM_CHECKER["check_events"](
        items,
        path="stream.json",
        allowed=_STREAM_CHECKER["DEFAULT_EVENTS"],
        max_event_bytes=1024,
        allow_open=False,
    )

    assert findings == ["stream.json:7: unknown event 'tick'"]


def test_stream_checker_flags_oversized_payloads_and_honors_options(
    tmp_path: Path,
) -> None:
    big = _write(
        tmp_path, "big.json", _stream((1, "start", {"text": "x" * 100}), *_COMPLETE[2:])
    )
    open_stream = _write(tmp_path, "open.json", _stream(*_COMPLETE[:2]))
    custom = _write(
        tmp_path,
        "custom.json",
        _stream((1, "start", {}), (2, "tick", {}), *_COMPLETE[2:]),
    )

    assert _STREAM_CHECKER["main"]([str(big), "--max-event-bytes", "50"]) == 1
    assert _STREAM_CHECKER["main"]([str(open_stream), "--allow-open"]) == 0
    assert _STREAM_CHECKER["main"]([str(custom), "--allow-event", "tick"]) == 0


def test_stream_checker_rejects_unreadable_input(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"seq": 1}\n', encoding="utf-8")

    assert _STREAM_CHECKER["main"]([str(path)]) == 2
    assert _STREAM_CHECKER["main"]([str(tmp_path / "missing.json")]) == 2


# verify_queue_messages.py


def _envelope(**overrides: object) -> dict[str, object]:
    envelope: dict[str, object] = {
        "task_id": "t-1",
        "task_type": "invoice.render",
        "version": 1,
        "idempotency_key": "invoice.render:INV-1",
        "payload": {"invoice_id": "INV-1"},
        "created_at": "2026-01-01T00:00:00+00:00",
        "correlation_id": "req-1",
    }
    envelope.update(overrides)
    return envelope


def test_queue_checker_accepts_the_shipped_samples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _QUEUE_CHECKER["main"](
        [
            str(_QUEUE / "queue_template.json.template"),
            "--supported",
            "invoice.render:1",
            "--supported",
            "document.index:2",
        ]
    )

    assert code == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("envelope", "message"),
    [
        (_envelope(task_id=""), "'task_id' must be a non-empty string"),
        (_envelope(version=0), "'version' must be an integer >= 1"),
        (_envelope(version=True), "'version' must be an integer >= 1"),
        (_envelope(payload=[]), "'payload' must be an object"),
        (_envelope(payload={"Token": "x"}), "secret-like keys"),
        (_envelope(created_at="2026-01-01T00:00:00"), "timezone offset"),
        (_envelope(created_at="yesterday"), "ISO 8601"),
        (_envelope(version=3), "unsupported version 3"),
        (_envelope(task_type="report.build"), "unsupported task type"),
        ("not an object", "envelope must be an object"),
    ],
)
def test_queue_checker_reports_invalid_envelopes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    envelope: object,
    message: str,
) -> None:
    path = _write(tmp_path, "queue.json", [envelope])

    assert _QUEUE_CHECKER["main"]([str(path), "--supported", "invoice.render:1"]) == 1
    output = capsys.readouterr().out
    assert message in output
    assert output.startswith(f"{path}:2:")


def test_queue_checker_detects_duplicates_across_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _write(tmp_path, "a.json", [_envelope()])
    second = _write(tmp_path, "b.json", [_envelope(task_id="t-2"), _envelope()])

    assert _QUEUE_CHECKER["main"]([str(first), str(second)]) == 1
    output = capsys.readouterr().out
    assert "duplicate idempotency_key" in output
    assert "duplicate task_id" in output
    assert (
        _QUEUE_CHECKER["main"]([str(first), str(second), "--allow-duplicate-keys"]) == 1
    )
    assert "duplicate idempotency_key" not in capsys.readouterr().out


def test_queue_checker_enforces_size_and_argument_errors(tmp_path: Path) -> None:
    path = _write(tmp_path, "queue.json", [_envelope(payload={"blob": "x" * 200})])

    assert _QUEUE_CHECKER["main"]([str(path), "--max-bytes", "100"]) == 1
    assert _QUEUE_CHECKER["main"]([str(path), "--supported", "nonsense"]) == 2
    assert _QUEUE_CHECKER["main"]([str(tmp_path / "missing.json")]) == 2
    empty = _write(tmp_path, "empty.json", [])
    assert _QUEUE_CHECKER["main"]([str(empty)]) == 1


# Templates


def test_structured_templates_parse() -> None:
    json_templates = _templates(".json.template")
    yaml_templates = _templates(".yaml.template") + _templates(".yml.template")
    ini_templates = _templates(".ini.template")

    assert len(json_templates) == 5
    for path in json_templates:
        json.loads(path.read_text(encoding="utf-8"))
    assert yaml_templates
    for path in yaml_templates:
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)
    assert ini_templates
    for path in ini_templates:
        parser = configparser.ConfigParser()
        parser.read_string(path.read_text(encoding="utf-8"))
        assert parser["importlinter"]["root_package"] == "retrieval"


def test_python_templates_parse_and_have_tests() -> None:
    for name in _NAMES:
        templates = sorted((_SKILLS / name / "assets").glob("*.py.template"))
        assert any(path.name.startswith("test_") for path in templates), name
        for path in templates:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _copy_targets(name: str) -> dict[str, ast.Module]:
    modules: dict[str, ast.Module] = {}
    for path in sorted((_SKILLS / name / "assets").glob("*.py.template")):
        text = path.read_text(encoding="utf-8")
        match = _COPY_TARGET.search(text)
        if match and not path.name.startswith("test_"):
            modules[match.group("path").replace("/", ".")] = ast.parse(text)
    return modules


@pytest.mark.parametrize("quote", ["'", "``"])
def test_copy_target_accepts_matched_docstring_code_delimiters(quote: str) -> None:
    match = _COPY_TARGET.search(f"Copy to {quote}llm/managed_prompts.py{quote}.")
    assert match is not None
    assert match.group("path") == "llm/managed_prompts"


def test_copy_target_rejects_mismatched_docstring_delimiters() -> None:
    assert _COPY_TARGET.search("Copy to 'llm/managed_prompts.py``.") is None


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


@pytest.mark.parametrize("name", _NAMES)
def test_templates_import_only_names_their_siblings_define(name: str) -> None:
    modules = _copy_targets(name)
    roots = {module.split(".", 1)[0] for module in modules}
    assert modules, name
    for path in sorted((_SKILLS / name / "assets").glob("*.py.template")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if node.module.split(".", 1)[0] not in roots:
                continue
            assert node.module in modules, f"{path.name} imports unknown {node.module}"
            defined = _top_level_names(modules[node.module])
            missing = {alias.name for alias in node.names} - defined
            assert not missing, (
                f"{path.name} imports {sorted(missing)} from {node.module}"
            )


def test_import_linter_contract_names_existing_retrieval_modules() -> None:
    modules = set(_copy_targets("kit-retrieval"))
    parser = configparser.ConfigParser()
    parser.read_string(
        (_SKILLS / "kit-retrieval/assets/importlinter.ini.template").read_text(
            encoding="utf-8"
        )
    )
    named = {
        line.strip()
        for section in parser.sections()
        for key in ("source_modules", "modules")
        for line in parser[section].get(key, "").splitlines()
        if line.strip()
    }

    assert named
    assert named <= modules


@pytest.mark.parametrize("name", _NAMES)
def test_every_resource_is_reachable_from_the_skill(name: str) -> None:
    home = _SKILLS / name
    pending = [home / "SKILL.md"]
    reached: set[Path] = set()
    while pending:
        path = pending.pop().resolve()
        if path in reached:
            continue
        reached.add(path)
        if path.suffix != ".md":
            continue
        for target in _LINK.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), f"{path.name} links missing {target}"
            assert resolved.is_relative_to(home.resolve()), (
                f"{path.name} escapes via {target}"
            )
            pending.append(resolved)
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (home / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }

    assert resources - reached == set()
