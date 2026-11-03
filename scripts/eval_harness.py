"""Measure this repository's agent harness in pi-harness-lab with its free scripted model.

Imports ``AGENTS.md`` plus the selected skills as a harness, validates it against
the lab's budgets and Harness² contract, and runs a paired baseline comparison.
The scripted model replays identical actions, so the report measures context
cost (token ratio) and contract health, not model quality: run the lab's paid
provider experiment for pass-rate claims.
"""

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys

_ROOT = Path(__file__).resolve().parents[1]
_LAB_ENV = "HARNESS_LAB"
_DEFAULT_LAB = _ROOT.parent / "pi-harness-lab"
_OUTPUT = _ROOT / "build" / "eval"
_SCRIPTED_SUITE = "scenarios/solve-suite.json"
# The scripted model is free; the lab still requires a positive spend ceiling.
_MAX_COST_USD = 0.01
_ARMS = 2
_RUNS_PER_ARM = 50


def experiment_toml(*, lab: Path, harness: Path, output: Path, trials: int) -> str:
    """Render a baseline-versus-candidate experiment with absolute paths.

    Args:
        lab (Path): pi-harness-lab checkout that owns tasks and the baseline.
        harness (Path): Imported candidate harness.
        output (Path): Directory for run records and reports.
        trials (int): Runs per task and arm.

    Returns:
        str: Experiment TOML accepted by ``harness-lab eval``.
    """
    return f"""[experiment]
name = "agent-kit-harness"
suite = '{lab / "tasks"}'
trials = {trials}
output = '{output}'

[budget]
max_runs = {_RUNS_PER_ARM * _ARMS * trials}
max_cost_usd = {_MAX_COST_USD}

[provider]
base_url = "http://127.0.0.1:9/v1"
model = "scripted-model"

[[arms]]
name = "baseline"
executor = "pi"
harness = '{lab / "harnesses" / "baseline"}'

[[arms]]
name = "agent-kit"
executor = "pi"
harness = '{harness}'
"""


def _toolkit_skills() -> list[str]:
    """Return the repository's own toolkit skills from ``.apm/skills``."""
    return sorted(path.parent.name for path in _ROOT.glob(".apm/skills/*/SKILL.md"))


def _lab(lab: Path, *arguments: str) -> None:
    """Run one ``harness-lab`` command inside the lab's locked environment."""
    command = ["uv", "run", "--locked", "harness-lab", *arguments]
    subprocess.run(command, cwd=lab, check=True)  # noqa: S603 -- fixed argv


def main() -> int:
    """Import, validate and measure the harness; ``1`` when the lab is unavailable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lab", type=Path, default=Path(os.environ.get(_LAB_ENV, _DEFAULT_LAB))
    )
    parser.add_argument("--skill", action="append", help="repeat; default: toolkit")
    parser.add_argument("--trials", type=int, default=1)
    args = parser.parse_args()
    lab = args.lab.resolve()
    if shutil.which("uv") is None or not (lab / "tasks").is_dir():
        sys.stderr.write(f"Set {_LAB_ENV} or --lab to a pi-harness-lab checkout.\n")
        return 1
    run = _OUTPUT / datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    harness = run / "harness"
    skills = args.skill or _toolkit_skills()
    skill_args = [item for name in skills for item in ("--skill", name)]
    try:
        _lab(
            lab,
            "harness",
            "import-agent-kit",
            "--source",
            str(_ROOT),
            *skill_args,
            "--agents",
            str(_ROOT / "AGENTS.md"),
            "--output",
            str(harness),
        )
        _lab(lab, "harness", "validate", "--for-refinement", str(harness))
        experiment = run / "experiment.toml"
        experiment.write_text(
            experiment_toml(lab=lab, harness=harness, output=run, trials=args.trials),
            encoding="utf-8",
        )
        _lab(lab, "eval", str(experiment), "--scripted-provider", _SCRIPTED_SUITE)
    except subprocess.CalledProcessError as error:
        sys.stderr.write(f"harness-lab failed with exit code {error.returncode}\n")
        return 1
    sys.stdout.write(f"Harness evaluation evidence: {run}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
