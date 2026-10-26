"""AI engineering assets: evaluation harness, gateway checker, agent templates."""

import ast
import io
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest
import yaml

_AI = Path(__file__).resolve().parents[3] / "packages/ai/.apm"
_EVAL = _AI / "skills/kit-llm-evaluation"
_GATEWAY = _AI / "skills/kit-llm-gateway"
_AGENTS = _AI / "skills/kit-agent-systems"
_CHECKER = runpy.run_path(str(_GATEWAY / "assets/check_gateway_config.py"))
_FAKE_KEY = "sk-" + "synthetic" * 3
_STDLIB_TEMPLATES = (
    _EVAL / "assets/eval_harness.py.template",
    _GATEWAY / "assets/gateway_client.py.template",
    _GATEWAY / "assets/check_gateway_config.py",
    _AGENTS / "assets/agent_tool_contract.py.template",
    _AGENTS / "assets/supervisor_loop.py.template",
)


def _load(template: Path, tmp_path: Path, name: str) -> SimpleNamespace:
    copied = tmp_path / name
    copied.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    return SimpleNamespace(**runpy.run_path(str(copied)))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }


@pytest.mark.parametrize("path", _STDLIB_TEMPLATES, ids=lambda path: path.name)
def test_executable_assets_import_only_stdlib(path: Path) -> None:
    assert _imports(path) <= sys.stdlib_module_names


@pytest.mark.parametrize("skill", [_EVAL, _GATEWAY, _AGENTS], ids=lambda p: p.name)
def test_skill_frontmatter_matches_contract(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    _, header, body = text.split("---", 2)
    metadata = yaml.safe_load(header)
    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == skill.name
    assert metadata["license"] == "MIT"
    assert metadata["description"].startswith("Use when")
    assert len(metadata["description"]) <= 110
    assert "## Acceptance gates" in body
    assert len(body.splitlines()) < 300


# eval_harness.py.template


@pytest.fixture
def harness(tmp_path: Path) -> SimpleNamespace:
    return _load(_EVAL / "assets/eval_harness.py.template", tmp_path, "harness.py")


def _dataset(tmp_path: Path) -> Path:
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        (_EVAL / "assets/golden_dataset.jsonl.template").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return path


def _outputs(tmp_path: Path, rows: list[tuple[str, int, str]]) -> Path:
    path = tmp_path / "outputs.jsonl"
    path.write_text(
        "".join(
            json.dumps({"id": case_id, "repeat": repeat, "output": output}) + "\n"
            for case_id, repeat, output in rows
        ),
        encoding="utf-8",
    )
    return path


def _baseline_document(harness: SimpleNamespace, dataset: Path) -> dict[str, object]:
    return {
        "dataset_fingerprint": harness.dataset_fingerprint(path=dataset),
        "scorer_versions": {
            "exact_match": "normalized-exact-match-v1",
            "token_f1": "casefold-word-overlap-f1-v1",
        },
        "metrics": {"exact_match": 0.9, "token_f1": 0.8},
    }


def _cli_arguments(dataset: Path, outputs: Path) -> list[str]:
    return [
        str(dataset),
        "--outputs",
        str(outputs),
        "--dataset-version",
        "v1",
    ]


def test_dataset_template_loads_with_provenance_and_slices(
    harness: SimpleNamespace, tmp_path: Path
) -> None:
    cases = harness.load_dataset(path=_dataset(tmp_path))
    assert len(cases) == 6
    assert all(case.source == "synthetic" for case in cases)
    tags = {tag for case in cases for tag in case.tags}
    assert {"adversarial", "must-refuse", "no-answer"} <= tags
    assert harness.dataset_fingerprint(path=_dataset(tmp_path)).startswith("sha256:")


@pytest.mark.parametrize(
    "line",
    [
        '{"id": "a", "input": "x", "expected": "y", "secret": "z"}',
        '{"id": "a", "input": "x"}',
        '{"id": "a", "input": "", "expected": "y"}',
        '{"id": "a", "input": "x", "expected": "y", "tags": "one"}',
        "[1, 2]",
        "{not json",
    ],
)
def test_dataset_rejects_invalid_records(
    harness: SimpleNamespace, tmp_path: Path, line: str
) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(harness.EvalInputError):
        harness.load_dataset(path=path)


def test_dataset_rejects_duplicate_ids(
    harness: SimpleNamespace, tmp_path: Path
) -> None:
    path = tmp_path / "dup.jsonl"
    record = json.dumps({"id": "a", "input": "x", "expected": "y"})
    path.write_text(f"{record}\n{record}\n", encoding="utf-8")
    with pytest.raises(harness.EvalInputError, match="unique"):
        harness.load_dataset(path=path)


def test_scorers_normalize_and_bound(harness: SimpleNamespace) -> None:
    case = harness.EvalCase(case_id="c", input="q", expected="Paris  France")
    assert harness.ExactMatch().score(case=case, output="paris france") == 1.0
    assert harness.ExactMatch().score(case=case, output="Paris") == 0.0
    assert harness.TokenF1().score(case=case, output="Paris") == pytest.approx(2 / 3)
    assert harness.TokenF1().score(case=case, output="Berlin") == 0.0


def test_bootstrap_is_seeded_and_brackets_the_mean(harness: SimpleNamespace) -> None:
    values = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0]
    first = harness.bootstrap_interval(values=values, seed=7)
    assert first == harness.bootstrap_interval(values=values, seed=7)
    assert first.low <= first.mean <= first.high
    assert first.mean == pytest.approx(0.75)
    with pytest.raises(harness.EvalInputError):
        harness.bootstrap_interval(values=[])
    with pytest.raises(harness.EvalInputError):
        harness.bootstrap_interval(values=values, confidence=1.0)


def test_minimum_detectable_difference_needs_two_cases(
    harness: SimpleNamespace,
) -> None:
    assert harness.minimum_detectable_difference(values=[1.0]) is None
    assert harness.minimum_detectable_difference(values=[1.0, 1.0]) == 0.0
    small = harness.minimum_detectable_difference(values=[0.0, 1.0] * 10)
    large = harness.minimum_detectable_difference(values=[0.0, 1.0] * 100)
    assert small > large > 0


def test_repeats_are_averaged_per_case_with_fake_task(
    harness: SimpleNamespace,
) -> None:
    cases = (
        harness.EvalCase(case_id="a", input="q", expected="yes"),
        harness.EvalCase(case_id="b", input="q", expected="no"),
    )
    answers = iter(["yes", "no", "yes", "yes"])
    outputs = harness.run_task(cases=cases, task=lambda _case: next(answers), repeats=2)
    assert outputs == {"a": ("yes", "no"), "b": ("yes", "yes")}
    (summary,) = harness.summarize(
        cases=cases, outputs=outputs, scorers=(harness.ExactMatch(),)
    )
    assert summary.cases == 2
    assert summary.interval.mean == pytest.approx(0.25)
    assert summary.repeat_spread == pytest.approx(0.5)
    with pytest.raises(harness.EvalInputError):
        harness.run_task(cases=cases, task=lambda _case: "", repeats=0)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        -0.01,
        1.01,
        True,
        False,
        "0.5",
        None,
    ],
)
def test_invalid_scorer_value_is_rejected(
    harness: SimpleNamespace, value: object
) -> None:
    class Broken:
        name = "broken"
        version = "broken-v1"

        def score(self, *, case: object, output: str) -> object:
            del case, output
            return value

    cases = (harness.EvalCase(case_id="a", input="q", expected="y"),)
    with pytest.raises(harness.EvalInputError, match="broken: score"):
        harness.summarize(cases=cases, outputs={"a": ("y",)}, scorers=(Broken(),))


def test_gates_check_floor_baseline_and_missing_metrics(
    harness: SimpleNamespace,
) -> None:
    summary = harness.MetricSummary(
        name="exact_match",
        cases=10,
        interval=harness.Interval(mean=0.7, low=0.5, high=0.9),
        repeat_spread=0.0,
        minimum_detectable_difference=0.2,
    )
    assert (
        harness.gate_failures(
            summaries=(summary,),
            minimums={"exact_match": 0.6},
            baseline={"exact_match": 0.71},
            max_regression=0.02,
        )
        == []
    )
    failures = harness.gate_failures(
        summaries=(summary,),
        minimums={"exact_match": 0.8, "judge": 0.5},
        baseline={"exact_match": 0.75},
        max_regression=0.02,
    )
    assert failures == [
        "judge: missing metric",
        "exact_match: mean 0.7000 below floor 0.8",
        "exact_match: mean 0.7000 regressed from baseline 0.75",
    ]


def test_cli_passes_writes_content_free_deterministic_report(
    harness: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    outputs = _outputs(tmp_path, [(case.case_id, 0, case.expected) for case in cases])
    report = tmp_path / "report.json"
    arguments = [
        str(dataset),
        "--outputs",
        str(outputs),
        "--dataset-version",
        "eval-v1",
        "--min",
        "exact_match=1.0",
        "--report",
        str(report),
    ]
    assert harness.main(arguments) == 0
    first = report.read_text(encoding="utf-8")
    assert harness.main(arguments) == 0
    assert report.read_text(encoding="utf-8") == first
    document = json.loads(first)
    assert document["passed"] is True
    assert document["metrics"] == {"exact_match": 1.0, "token_f1": 1.0}
    assert document["scorer_versions"] == {
        "exact_match": harness.ExactMatch().version,
        "token_f1": harness.TokenF1().version,
    }
    assert document["dataset_fingerprint"].startswith("sha256:")
    assert all(case.input not in first for case in cases)
    assert capsys.readouterr().out.count('"passed": true') == 2


def test_cli_gate_failure_and_baseline_regression(
    harness: SimpleNamespace, tmp_path: Path
) -> None:
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    rows = [(case.case_id, 0, "wrong") for case in cases]
    outputs = _outputs(tmp_path, rows)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(_baseline_document(harness, dataset)), encoding="utf-8"
    )
    common = [str(dataset), "--outputs", str(outputs), "--dataset-version", "v1"]
    assert harness.main([*common, "--baseline", str(baseline)]) == 1
    assert harness.main([*common, "--min", "exact_match=0.5"]) == 1
    assert harness.main(common) == 0


def test_report_roundtrips_as_baseline_without_changing_metric_details(
    harness: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    outputs = _outputs(tmp_path, [(case.case_id, 0, case.expected) for case in cases])
    scorers = (harness.ExactMatch(), harness.TokenF1())
    versions = {scorer.name: scorer.version for scorer in scorers}
    summaries = harness.summarize(
        cases=cases,
        outputs=harness.load_outputs(path=outputs, cases=cases),
        scorers=scorers,
    )
    report = harness.build_report(
        dataset_version="v1",
        fingerprint=harness.dataset_fingerprint(path=dataset),
        scorer_versions=versions,
        summaries=summaries,
        failures=[],
    )
    assert report == {
        "dataset_version": "v1",
        "dataset_fingerprint": harness.dataset_fingerprint(path=dataset),
        "scorer_versions": versions,
        "passed": True,
        "failures": [],
        "metrics": {"exact_match": 1.0, "token_f1": 1.0},
        "details": {
            name: {
                "cases": 6,
                "ci_low": 1.0,
                "ci_high": 1.0,
                "repeat_spread": 0.0,
                "minimum_detectable_difference": 0.0,
            }
            for name in versions
        },
    }
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(report), encoding="utf-8")
    arguments = [*_cli_arguments(dataset, outputs), "--baseline", str(baseline)]
    assert harness.main(arguments) == 0
    assert json.loads(capsys.readouterr().out) == report


@pytest.mark.parametrize(
    "changes",
    [
        {"dataset_fingerprint": None},
        {"dataset_fingerprint": ""},
        {"dataset_fingerprint": 42},
        {"dataset_fingerprint": "sha256:" + "0" * 64},
        {"scorer_versions": None},
        {"scorer_versions": []},
        {"scorer_versions": {}},
        {"scorer_versions": {"exact_match": "normalized-exact-match-v1"}},
        {"scorer_versions": {"exact_match": "old", "token_f1": "old"}},
        {"scorer_versions": {"exact_match": 1, "token_f1": "old"}},
        {"scorer_versions": {"exact_match": "", "token_f1": "old"}},
        {"metrics": {}},
        {"metrics": []},
        {"metrics": {"unknown": 0.9}},
        {"metrics": {"exact_match": -0.01}},
        {"metrics": {"exact_match": 1.01}},
        {"metrics": {"exact_match": float("nan")}},
        {"metrics": {"exact_match": float("inf")}},
        {"metrics": {"exact_match": -float("inf")}},
        {"metrics": {"exact_match": True}},
        {"metrics": {"exact_match": "0.9"}},
        {"metrics": {"exact_match": None}},
    ],
)
def test_cli_rejects_invalid_baseline_with_actionable_error(
    harness: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    changes: dict[str, object],
) -> None:
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    outputs = _outputs(tmp_path, [(case.case_id, 0, "wrong") for case in cases])
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({**_baseline_document(harness, dataset), **changes}),
        encoding="utf-8",
    )
    arguments = [*_cli_arguments(dataset, outputs), "--baseline", str(baseline)]
    assert harness.main(arguments) == 2
    captured = capsys.readouterr()
    assert "baseline" in captured.err
    assert "regenerate" in captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "document",
    [
        {"metrics": {"exact_match": 0.9}},
        {},
        [],
        None,
    ],
)
def test_cli_rejects_legacy_or_missing_baseline_identity(
    harness: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    document: object,
) -> None:
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    outputs = _outputs(tmp_path, [(case.case_id, 0, "wrong") for case in cases])
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(document), encoding="utf-8")
    arguments = [*_cli_arguments(dataset, outputs), "--baseline", str(baseline)]
    assert harness.main(arguments) == 2
    assert "regenerate" in capsys.readouterr().err


@pytest.mark.parametrize("raw_text", [None, "{"])
def test_cli_rejects_unreadable_or_unparseable_baseline(
    harness: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw_text: str | None,
) -> None:
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    outputs = _outputs(tmp_path, [(case.case_id, 0, "wrong") for case in cases])
    baseline = tmp_path / "baseline.json"
    if raw_text is not None:
        baseline.write_text(raw_text, encoding="utf-8")
    arguments = [*_cli_arguments(dataset, outputs), "--baseline", str(baseline)]
    assert harness.main(arguments) == 2
    captured = capsys.readouterr()
    assert "invalid input" in captured.err
    assert "baseline" in captured.err
    assert not captured.out


def test_baseline_compares_only_declared_metrics(
    harness: SimpleNamespace, tmp_path: Path
) -> None:
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    outputs = _outputs(tmp_path, [(case.case_id, 0, "wrong") for case in cases])
    document = _baseline_document(harness, dataset)
    document["metrics"] = {"exact_match": 0.0}
    document["scorer_versions"] = {"exact_match": "normalized-exact-match-v1"}
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(document), encoding="utf-8")
    arguments = [*_cli_arguments(dataset, outputs), "--baseline", str(baseline)]
    assert harness.main(arguments) == 0


@pytest.mark.parametrize("tolerance", ["-0.01", "nan", "inf", "-inf"])
def test_regression_tolerance_must_be_finite_and_nonnegative(
    harness: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    tolerance: str,
) -> None:
    with pytest.raises(harness.EvalInputError, match=r"finite.*non-negative"):
        harness.gate_failures(
            summaries=(), minimums={}, baseline={}, max_regression=float(tolerance)
        )
    dataset = _dataset(tmp_path)
    cases = harness.load_dataset(path=dataset)
    outputs = _outputs(tmp_path, [(case.case_id, 0, "wrong") for case in cases])
    arguments = [*_cli_arguments(dataset, outputs), f"--max-regression={tolerance}"]
    assert harness.main(arguments) == 2
    assert "max_regression" in capsys.readouterr().err


@pytest.mark.parametrize(
    "rows",
    [
        [("extract-001", 0, "x")],
        [("unknown", 0, "x")],
        [("extract-001", -1, "x")],
    ],
)
def test_cli_rejects_incomplete_or_invalid_outputs(
    harness: SimpleNamespace,
    tmp_path: Path,
    rows: list[tuple[str, int, str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = [
        str(_dataset(tmp_path)),
        "--outputs",
        str(_outputs(tmp_path, rows)),
        "--dataset-version",
        "v1",
    ]
    assert harness.main(arguments) == 2
    assert "invalid input" in capsys.readouterr().err


def test_cli_rejects_bad_arguments(harness: SimpleNamespace, tmp_path: Path) -> None:
    dataset = str(_dataset(tmp_path))
    assert harness.main([dataset]) == 2
    assert (
        harness.main(
            [dataset, "--outputs", "o", "--dataset-version", "v", "--min", "x=2"]
        )
        == 2
    )


def test_langfuse_adapter_is_facade_only_and_requires_export_approval() -> None:
    path = _EVAL / "assets/langfuse_experiment.py.template"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert _imports(path) - sys.stdlib_module_names == {"evals"}
    names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert {
        "ExperimentSdk",
        "ExperimentIdentity",
        "LangfuseExperimentRunner",
        "ExportNotApprovedError",
    } <= names
    assert "raise ExportNotApprovedError" in source
    assert "prompt_version" in source
    assert "langfuse" not in _imports(path)


# agents.json


def test_roles_follow_least_privilege_schema() -> None:
    document = json.loads((_EVAL / "assets/agents.json").read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    roles = {role["id"]: role for role in document["roles"]}
    assert set(roles) == {"kit-ai-engineer", "kit-eval-reviewer"}
    assert roles["kit-ai-engineer"]["kind"] == "primary"
    assert roles["kit-ai-engineer"]["tier"] == "implementer"
    assert roles["kit-eval-reviewer"]["kind"] == "worker"
    assert roles["kit-eval-reviewer"]["tier"] == "readonly"
    for role in roles.values():
        assert set(role) == {"id", "kind", "tier", "description", "body", "workers"}
        assert role["workers"] == []
        assert len(role["description"]) <= 180
        assert len(role["body"].splitlines()) <= 125
        assert "Do not delegate" in role["body"]


# check_gateway_config.py


def _gateway_template() -> dict[str, object]:
    text = (_GATEWAY / "assets/litellm_config.yaml.template").read_text("utf-8")
    document = yaml.safe_load(text)
    assert isinstance(document, dict)
    return document


def test_litellm_template_is_clean() -> None:
    assert _CHECKER["check"](_gateway_template(), production=["chat-default"]) == []


def _minimal(**params: object) -> dict[str, object]:
    return {
        "model_list": [
            {
                "model_name": "chat-default",
                "litellm_params": {"model": "openai/model-2026-01-01", **params},
            }
        ]
    }


@pytest.mark.parametrize(
    ("document", "production", "expected"),
    [
        (
            _minimal(api_key=_FAKE_KEY, timeout=10),
            [],
            "model_list[0].litellm_params.api_key: credential must be",
        ),
        (
            {**_minimal(timeout=10), "general_settings": {"note": _FAKE_KEY}},
            [],
            "general_settings.note: value looks like a literal provider key",
        ),
        (_minimal(), [], "model_list[0].litellm_params.timeout: no timeout"),
        (_minimal(timeout=0), [], "timeout: must be positive"),
        (
            _minimal(timeout=10, model="ollama/model:latest"),
            [],
            "floating latest tag",
        ),
        (
            _minimal(timeout=10, model="ollama_chat/model"),
            [],
            "local model needs a tag",
        ),
        (
            {
                **_minimal(timeout=10),
                "router_settings": {"fallbacks": [{"chat-default": ["missing"]}]},
            },
            [],
            "target is undefined",
        ),
        (_minimal(timeout=10), ["chat-default"], "production alias has no fallback"),
        (_minimal(timeout=10), ["other"], "--production other: alias is not defined"),
    ],
)
def test_gateway_checker_flags_litellm_defects(
    document: dict[str, object], production: list[str], expected: str
) -> None:
    findings = _CHECKER["check"](document, production=production)
    assert any(expected in finding for finding in findings), findings
    assert all(_FAKE_KEY not in finding for finding in findings)


def test_gateway_checker_accepts_global_timeout_and_default_fallbacks() -> None:
    document = {
        # pragma: allowlist nextline secret: environment-variable reference
        **_minimal(api_key="os.environ/PROVIDER_KEY"),
        "litellm_settings": {"request_timeout": 30},
        "router_settings": {"default_fallbacks": ["chat-default"]},
    }
    assert _CHECKER["check"](document, production=["chat-default"]) == []


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("ghcr.io/berriai/litellm@sha256:" + "a" * 64, None),
        ("ollama/ollama:0.12.0@sha256:" + "b" * 64, None),
        ("ollama/ollama", "no tag or digest"),
        ("ollama/ollama:latest", "floating tag"),
        ("ghcr.io/berriai/litellm:main-stable", "floating tag"),
        ("registry:5000/team/gateway:1.2.3", "tag without digest"),
        ("${LITELLM_IMAGE}", "unresolved variable"),
    ],
)
def test_gateway_checker_flags_compose_images(image: str, expected: str | None) -> None:
    document = {"services": {"gateway": {"image": image}}}
    findings = _CHECKER["check"](document, production=[])
    if expected is None:
        assert findings == []
    else:
        assert len(findings) == 1
        assert findings[0].startswith("services.gateway.image: ")
        assert expected in findings[0]


def test_gateway_checker_main_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps(_gateway_template()), encoding="utf-8")
    assert _CHECKER["main"]([str(clean), "--production", "chat-default"]) == 0
    dirty = tmp_path / "dirty.json"
    dirty.write_text(json.dumps(_minimal(api_key=_FAKE_KEY)), encoding="utf-8")
    assert _CHECKER["main"]([str(dirty)]) == 1
    output = capsys.readouterr().out
    assert "api_key" in output
    assert _FAKE_KEY not in output
    other = tmp_path / "other.json"
    other.write_text('{"name": "x"}', encoding="utf-8")
    assert _CHECKER["main"]([str(other)]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert _CHECKER["main"]([str(broken)]) == 2
    assert _CHECKER["main"]([str(tmp_path / "missing.json")]) == 2
    assert _CHECKER["main"]([]) == 2
    compose = json.dumps({"services": {"db": {"image": "postgres:17"}}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(compose))
    assert _CHECKER["main"](["-"]) == 1


def test_gateway_checker_self_test_passes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _CHECKER["self_test"]() == []
    assert _CHECKER["main"](["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


def test_compose_template_requires_pinned_images_and_loopback_ports() -> None:
    text = (_GATEWAY / "assets/compose.gateway.yaml.template").read_text("utf-8")
    document = yaml.safe_load(text)
    services = document["services"]
    for service in services.values():
        assert service["image"].startswith("${")
        assert ":?" in service["image"]
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:")
    assert "OLLAMA_NO_CLOUD" in services["ollama"]["environment"]


# gateway_client.py.template


@pytest.fixture
def gateway_client(tmp_path: Path) -> SimpleNamespace:
    template = _GATEWAY / "assets/gateway_client.py.template"
    return _load(template, tmp_path, "gateway_settings.py")


def _environ(**overrides: str) -> dict[str, str]:
    values = {
        "LLM_GATEWAY_URL": "https://gateway.internal/",
        "LLM_GATEWAY_KEY": _FAKE_KEY,
        "LLM_GATEWAY_ALIAS": "chat-default",
        "LLM_GATEWAY_TIMEOUT_SECONDS": "30",
    }
    return {**values, **overrides}


def test_gateway_settings_build_client_arguments_without_leaking_key(
    gateway_client: SimpleNamespace,
) -> None:
    settings = gateway_client.load_gateway_settings(environ=_environ())
    assert _FAKE_KEY not in repr(settings)
    assert settings.litellm_kwargs() == {
        "model": "litellm_proxy/chat-default",
        "api_base": "https://gateway.internal",
        "api_key": _FAKE_KEY,
        "timeout": 30.0,
        "num_retries": 0,
    }
    assert settings.openai_client_kwargs()["base_url"] == "https://gateway.internal/v1"
    local = gateway_client.load_gateway_settings(
        environ=_environ(LLM_GATEWAY_URL="http://127.0.0.1:4000")
    )
    assert local.base_url == "http://127.0.0.1:4000"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"LLM_GATEWAY_KEY": ""}, "missing gateway settings: LLM_GATEWAY_KEY"),
        ({"LLM_GATEWAY_URL": "http://gateway.internal"}, "https"),
        # pragma: allowlist nextline secret: synthetic rejected URL
        ({"LLM_GATEWAY_URL": "https://user:pw@gateway.internal"}, "credentials"),
        ({"LLM_GATEWAY_ALIAS": "GPT 4"}, "alias"),
        ({"LLM_GATEWAY_TIMEOUT_SECONDS": "0"}, "timeout"),
        ({"LLM_GATEWAY_TIMEOUT_SECONDS": "nan"}, "timeout"),
        ({"LLM_GATEWAY_TIMEOUT_SECONDS": "soon"}, "timeout"),
    ],
)
def test_gateway_settings_reject_invalid_values(
    gateway_client: SimpleNamespace, overrides: dict[str, str], message: str
) -> None:
    with pytest.raises(gateway_client.GatewaySettingsError, match=message) as error:
        gateway_client.load_gateway_settings(environ=_environ(**overrides))
    assert _FAKE_KEY not in str(error.value)


# agent_tool_contract.py.template


@pytest.fixture
def tools(tmp_path: Path) -> SimpleNamespace:
    template = _AGENTS / "assets/agent_tool_contract.py.template"
    return _load(template, tmp_path, "tools.py")


def _write_tool(tools: SimpleNamespace, calls: list[str]) -> object:
    class Refund:
        @property
        def spec(self) -> object:
            return tools.ToolSpec(
                name="issue_refund",
                description="Refund an order.",
                parameters=(
                    tools.Parameter(name="order_id", kind=str, description="Order."),
                    tools.Parameter(name="cents", kind=int, description="Amount."),
                ),
                side_effect=tools.SideEffect.EXTERNAL,
                errors=(tools.ToolErrorCode.APPROVAL_REQUIRED,),
            )

        def invoke(self, *, arguments: dict[str, object], idempotency_key: str) -> str:
            calls.append(idempotency_key)
            if arguments["order_id"] == "down":
                message = "provider said: internal detail"
                raise tools.ToolUnavailableError(message)
            return "refunded"

    return Refund()


def test_registry_validates_and_reports_stable_codes(tools: SimpleNamespace) -> None:
    lookup = tools.OrderStatusTool(statuses={"o-1": "shipped"})
    registry = tools.ToolRegistry(tools=(lookup,), approver=tools.deny_all)
    codes = tools.ToolErrorCode
    assert registry.call(
        name="get_order_status", arguments={"order_id": "o-1"}, idempotency_key="k"
    ) == tools.ToolResult(ok=True, content="shipped")
    cases = [
        ("delete_everything", {"order_id": "o-1"}, codes.UNKNOWN_TOOL),
        ("get_order_status", {}, codes.INVALID_ARGUMENTS),
        ("get_order_status", {"order_id": 1}, codes.INVALID_ARGUMENTS),
        ("get_order_status", {"order_id": ""}, codes.INVALID_ARGUMENTS),
        ("get_order_status", {"order_id": "o", "x": 1}, codes.INVALID_ARGUMENTS),
        ("get_order_status", {"order_id": "o-9"}, codes.NOT_FOUND),
    ]
    for name, arguments, code in cases:
        result = registry.call(name=name, arguments=arguments, idempotency_key="k")
        assert result == tools.ToolResult(ok=False, error=code)
    schema = registry.definitions()[0]["parameters"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["order_id"]


def test_registry_requires_approval_and_runs_side_effects_once(
    tools: SimpleNamespace,
) -> None:
    calls: list[str] = []
    refund = _write_tool(tools, calls)
    denied = tools.ToolRegistry(tools=(refund,), approver=tools.deny_all)
    arguments = {"order_id": "o-1", "cents": 500}
    result = denied.call(
        name="issue_refund", arguments=arguments, idempotency_key="r:1"
    )
    assert result.error == tools.ToolErrorCode.APPROVAL_REQUIRED
    assert calls == []
    approved = tools.ToolRegistry(tools=(refund,), approver=lambda _spec, _args: True)
    first = approved.call(
        name="issue_refund", arguments=arguments, idempotency_key="r:1"
    )
    again = approved.call(
        name="issue_refund", arguments=arguments, idempotency_key="r:1"
    )
    assert first == again == tools.ToolResult(ok=True, content="refunded")
    assert calls == ["r:1"]
    bool_amount = {"order_id": "o-1", "cents": True}
    assert (
        approved.call(
            name="issue_refund", arguments=bool_amount, idempotency_key="r:2"
        ).error
        == tools.ToolErrorCode.INVALID_ARGUMENTS
    )
    down = approved.call(
        name="issue_refund",
        arguments={"order_id": "down", "cents": 1},
        idempotency_key="r:3",
    )
    assert down == tools.ToolResult(ok=False, error=tools.ToolErrorCode.UNAVAILABLE)
    assert "internal detail" not in repr(down)


def test_registry_rejects_duplicate_or_invalid_names(tools: SimpleNamespace) -> None:
    lookup = tools.OrderStatusTool(statuses={})
    with pytest.raises(ValueError, match="unique"):
        tools.ToolRegistry(tools=(lookup, lookup), approver=tools.deny_all)


# supervisor_loop.py.template


@pytest.fixture
def supervisor(tmp_path: Path) -> SimpleNamespace:
    template = _AGENTS / "assets/supervisor_loop.py.template"
    return _load(template, tmp_path, "supervisor.py")


class _Gateway:
    def __init__(self, module: SimpleNamespace) -> None:
        self.module = module
        self.keys: list[str] = []

    def run(self, *, name: str, arguments: dict[str, object], key: str) -> object:
        self.keys.append(key)
        action = self.module.CallTool(name=name, arguments=arguments)
        return self.module.Observation(action=action, ok=True, content="shipped")


def _budget(module: SimpleNamespace, **overrides: object) -> object:
    values: dict[str, object] = {
        "max_steps": 5,
        "max_cost_micros": 1000,
        "deadline_seconds": 60.0,
    }
    return module.Budget(**{**values, **overrides})


def test_supervisor_completes_with_content_free_trajectory(
    supervisor: SimpleNamespace,
) -> None:
    turns = [
        supervisor.ModelTurn(
            action=supervisor.CallTool(
                name="get_order_status", arguments={"order_id": "private-123"}
            ),
            cost_micros=100,
        ),
        supervisor.ModelTurn(
            action=supervisor.Delegate(worker="writer", task="draft reply"),
            cost_micros=100,
        ),
        supervisor.ModelTurn(
            action=supervisor.Finish(answer="Your order shipped."), cost_micros=50
        ),
    ]
    gateway = _Gateway(supervisor)
    result = supervisor.Supervisor(
        model=supervisor.ScriptedModel(turns=turns),
        tools=gateway,
        workers={"writer": lambda task: f"draft for {task}"},
    ).run(goal="Where is my order?", budget=_budget(supervisor), run_id="run-1")
    assert result.outcome == supervisor.Outcome.COMPLETED
    assert result.answer == "Your order shipped."
    assert result.cost_micros == 250
    assert [step.kind for step in result.trajectory] == ["tool", "delegate", "finish"]
    assert gateway.keys == ["run-1:0"]
    assert "private-123" not in repr(result.trajectory)


@pytest.mark.parametrize(
    ("turn_cost", "overrides", "outcome"),
    [
        (10, {"max_steps": 3, "max_repeats": 10}, "STEP_BUDGET"),
        (600, {}, "COST_BUDGET"),
        (10, {"max_repeats": 2}, "REPEATED_ACTION"),
    ],
)
def test_supervisor_stops_on_each_budget(
    supervisor: SimpleNamespace,
    turn_cost: int,
    overrides: dict[str, object],
    outcome: str,
) -> None:
    turn = supervisor.ModelTurn(
        action=supervisor.CallTool(name="get_order_status", arguments={"id": "1"}),
        cost_micros=turn_cost,
    )
    result = supervisor.Supervisor(
        model=supervisor.ScriptedModel(turns=[turn]),
        tools=_Gateway(supervisor),
        workers={},
    ).run(goal="loop", budget=_budget(supervisor, **overrides), run_id="run-2")
    assert result.outcome == supervisor.Outcome[outcome]
    assert result.answer is None


def test_supervisor_enforces_deadline_and_reports_unknown_worker(
    supervisor: SimpleNamespace,
) -> None:
    ticks = iter([0.0, 0.0, 100.0])
    delegate = supervisor.ModelTurn(
        action=supervisor.Delegate(worker="missing", task="x"), cost_micros=1
    )
    result = supervisor.Supervisor(
        model=supervisor.ScriptedModel(turns=[delegate]),
        tools=_Gateway(supervisor),
        workers={},
        clock=lambda: next(ticks),
    ).run(goal="g", budget=_budget(supervisor, deadline_seconds=10.0), run_id="r")
    assert result.outcome == supervisor.Outcome.DEADLINE
    assert [step.ok for step in result.trajectory] == [False]
