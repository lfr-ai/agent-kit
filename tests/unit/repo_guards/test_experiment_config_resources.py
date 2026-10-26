"""Experiment templates validate data without importing or executing Hydra."""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest

_SKILL = Path(__file__).resolve().parents[3] / "packages/backend/.apm/skills/kit-config"
_ASSETS = _SKILL / "assets"
_PRIVATE_VALUE = "synthetic-private-value"


@pytest.fixture
def experiment(tmp_path: Path) -> SimpleNamespace:
    copied = tmp_path / "experiment_config.py"
    copied.write_text(
        (_ASSETS / "experiment_config.py.template").read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    return SimpleNamespace(**runpy.run_path(str(copied)))


def test_template_imports_only_stdlib() -> None:
    tree = ast.parse(
        (_ASSETS / "experiment_config.py.template").read_text(encoding="utf-8")
    )
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports <= sys.stdlib_module_names


@pytest.fixture
def document() -> dict[str, object]:
    value: object = json.loads(
        (_ASSETS / "experiment.json.template").read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


def test_precedence_and_immutable_typed_result(
    experiment: SimpleNamespace, document: dict[str, object]
) -> None:
    document.pop("temperature")
    config = experiment.parse_experiment(document=document, overrides={"seed": 17})

    assert config.temperature == 1.0
    assert config.seed == 17
    assert document["seed"] == 7
    with pytest.raises(FrozenInstanceError):
        config.seed = 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", True),
        ("seed", -1),
        ("seed", 4_294_967_296),
        ("seed", "7"),
        ("temperature", -0.1),
        ("temperature", 2.01),
        ("temperature", float("nan")),
        ("temperature", float("inf")),
        ("temperature", True),
        ("eval_dataset_version", ""),
        ("model", "${unsafe:input}"),
        ("prompt_version", "Prompt-V1"),
        ("config_version", "v2"),
        ("run_id", "../escape"),
        ("run_id", "C:\\escape"),
        ("run_id", "CON"),
        ("run_id", "run-1.2"),
        ("seed", _PRIVATE_VALUE),
        ("model", {"_target_": _PRIVATE_VALUE}),
    ],
)
def test_invalid_configuration_never_echoes_values(
    experiment: SimpleNamespace,
    document: dict[str, object],
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match=field) as caught:
        experiment.parse_experiment(document=document, overrides={field: value})

    assert _PRIVATE_VALUE not in str(caught.value)


@pytest.mark.parametrize(
    "field", ["api_token", "_target_", "_recursive_", _PRIVATE_VALUE]
)
def test_unknown_keys_rejected_in_every_layer_without_echoing_input(
    experiment: SimpleNamespace, document: dict[str, object], field: str
) -> None:
    for base, overrides in (
        ({**document, field: _PRIVATE_VALUE}, {}),
        (document, {field: _PRIVATE_VALUE}),
    ):
        with pytest.raises(ValueError, match="unknown experiment field") as caught:
            experiment.parse_experiment(document=base, overrides=overrides)
        assert _PRIVATE_VALUE not in str(caught.value)


@pytest.mark.parametrize(
    "field", ["run_id", "eval_dataset_version", "model", "prompt_version"]
)
def test_missing_provenance_fails(
    experiment: SimpleNamespace, document: dict[str, object], field: str
) -> None:
    document.pop(field)
    with pytest.raises(ValueError, match=field):
        experiment.parse_experiment(document=document, overrides={})


@pytest.mark.parametrize(
    ("seeds", "temperatures", "limit"),
    [
        ((), (0.2,), 4),
        ((1,), (), 4),
        ((1, 2, 3), (0.0, 1.0), 5),
        (tuple(range(17)), (0.2,), 16),
        ((1,), (0.2,), 17),
        ((1,), (0.2,), 0),
        ((1,), (0.2,), True),
        ((False,), (0.2,), 4),
        ((1,), (float("nan"),), 4),
        ((1, 1), (0.2,), 4),
        ((1,), (0.2, 0.2), 4),
    ],
)
def test_sweep_rejected_before_artifacts(
    experiment: SimpleNamespace,
    document: dict[str, object],
    tmp_path: Path,
    seeds: tuple[int, ...],
    temperatures: tuple[float, ...],
    limit: int,
) -> None:
    config = experiment.parse_experiment(document=document, overrides={})
    with pytest.raises(ValueError, match=r"(sweep|max_jobs|seed|temperature):"):
        experiment.plan_runs(
            config=config,
            seeds=seeds,
            temperatures=temperatures,
            max_jobs=limit,
            launch_directory=tmp_path,
            output_root=Path("outputs"),
        )
    assert not (tmp_path / "outputs").exists()


def test_cartesian_plan_is_isolated_and_manifest_is_public_only(
    experiment: SimpleNamespace,
    document: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("EXPERIMENT_TOKEN", _PRIVATE_VALUE)
    monkeypatch.setenv("SEED", _PRIVATE_VALUE)
    config = experiment.parse_experiment(document=document, overrides={})
    arguments = {
        "seeds": (7, 11),
        "temperatures": (0.0, 1.0),
        "max_jobs": 4,
        "launch_directory": tmp_path,
        "output_root": Path("outputs"),
    }
    runs = experiment.plan_runs(config=config, **arguments)
    assert len(runs) == 4
    assert len({run.output_directory for run in runs}) == 4
    assert [(run.config.seed, run.config.temperature) for run in runs] == [
        (7, 0.0),
        (7, 1.0),
        (11, 0.0),
        (11, 1.0),
    ]
    monkeypatch.chdir(tmp_path)
    for run in runs:
        path = experiment.write_manifest(run=run)
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        assert payload["config"]["eval_dataset_version"] == "eval-v1"
        assert payload["config"]["model"] == "gpt-4.1-mini"
        assert payload["config"]["prompt_version"] == "prompt-v1"
        assert payload["config"]["config_version"] == "v1"
        assert payload["config"]["run_id"] == document["run_id"]
        assert payload["job_index"] == run.job_index
        assert payload["launch_directory"] == str(tmp_path.resolve())
        assert payload["output_directory"] == str(run.output_directory)
        assert set(payload["config"]) == set(document)
        assert _PRIVATE_VALUE not in text
        assert path.is_relative_to(tmp_path / "outputs")
        with pytest.raises(FileExistsError):
            experiment.write_manifest(run=run)
        assert path.read_text(encoding="utf-8") == text
    assert Path.cwd() == tmp_path
    assert config.seed == 7
    assert config.temperature == 0.2
    assert capsys.readouterr() == ("", "")

    other = experiment.parse_experiment(
        document=document, overrides={"run_id": "run-other"}
    )
    assert {run.output_directory for run in runs}.isdisjoint(
        run.output_directory for run in experiment.plan_runs(config=other, **arguments)
    )
