"""The harness-evaluation bridge renders a valid paired experiment."""

from pathlib import Path
import tomllib

from scripts.eval_harness import experiment_toml


def test_experiment_pairs_baseline_with_candidate_under_a_spend_cap(
    tmp_path: Path,
) -> None:
    lab = tmp_path / "lab"
    harness = tmp_path / "run" / "harness"

    document = tomllib.loads(
        experiment_toml(lab=lab, harness=harness, output=tmp_path / "run", trials=2)
    )

    assert document["experiment"]["suite"] == str(lab / "tasks")
    assert document["experiment"]["trials"] == 2
    assert [arm["name"] for arm in document["arms"]] == ["baseline", "agent-kit"]
    assert document["arms"][1]["harness"] == str(harness)
    assert 0 < document["budget"]["max_cost_usd"] <= 0.01
