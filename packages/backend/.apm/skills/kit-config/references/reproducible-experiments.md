# Reproducible experiment configuration

## Choose the smallest boundary

| Need | Use |
| --- | --- |
| One file, a few arguments, no config groups | Stdlib JSON/TOML, explicit merging, validated dataclasses |
| Deployment environment, secrets, provider layering | Existing [settings layering](settings-layering.md) and [secret delivery](secrets-providers.md); no Hydra required |
| Repeated evaluations composed from model/prompt/dataset groups, typed schemas, CLI overrides and finite sweeps | Consider Hydra after consumer compatibility review |

This is an optional experiment branch of kit-config for comparing ChatGPT/OpenAI
API model settings (model, prompt version, temperature, seed) against a fixed
evaluation dataset. The same boundary can support another approved provider;
it does not automate the ChatGPT website. Hydra composes experiment configuration,
not model training, inference serving, deployment, a service configuration
replacement, an installer, or an always-on execution tool.

## Compatibility is a consumer decision

Reviewed 2026-10-23: the [upstream README](https://github.com/hydra-ecosystem/hydra)
labels Hydra **1.4 release candidate**, supporting Python 3.10–3.14, and **1.3
legacy**. A release candidate is not stable. The versioned 1.3 structured-config
tutorial is conceptual prior art, not proof that 1.3 supports a consumer's current
Python. Unversioned advanced docs describe newer APIs.

Before adoption, review the exact Python, `hydra-core`, OmegaConf and
launcher/sweeper plugin versions, transitive dependencies, licenses and security
changes in the consumer. Pin an approved compatible set there and verify its
lockfile and runtime. Do not install Hydra here, silently select a prerelease,
or assume a `version_base` setting pins the installed distribution.

## Schema and precedence

The [stdlib template](../assets/experiment_config.py.template) and
[public JSON example](../assets/experiment.json.template) work without Hydra.
Copy the Python asset as `experiment_config.py`, load a JSON object, and call
`parse_experiment(document=..., overrides=...)`. Unknown keys fail in either
layer. Precedence is **safe numeric/schema defaults < document < explicit
overrides**; there is no implicit environment, dotenv, resolver or provider read.
Only the final values are type/bounds validated; unknown keys never disappear
behind an override. Error messages never include input values or unknown names.

`ExperimentConfig` is the frozen, keyword-only, slotted result; dataclass
annotations alone do not validate input. Construct it through the parser.
`config_version` selects the supported schema, not a code revision.
In a Hydra consumer, register a separate mutable composition schema rather than
using the frozen result as an overridable ConfigStore node:

```python
from dataclasses import dataclass

from hydra.core.config_store import ConfigStore
from omegaconf import MISSING

from experiment_config import CONFIG_VERSION, DEFAULT_SEED, DEFAULT_TEMPERATURE


@dataclass(kw_only=True, slots=True)
class ExperimentSchema:
    """Public fields composed by Hydra before application validation.

    Args:
        run_id (str): Unique public launch identifier.
        eval_dataset_version (str): Immutable public evaluation dataset label.
        model (str): Public provider model or deployment identifier.
        prompt_version (str): Immutable public prompt version or label.
        config_version (str): Experiment document schema version.
        seed (int): Sampling seed; providers may honor it on a best-effort basis.
        temperature (float): Sampling temperature validated by the application.
    """

    run_id: str = MISSING
    eval_dataset_version: str = MISSING
    model: str = MISSING
    prompt_version: str = MISSING
    config_version: str = CONFIG_VERSION
    seed: int = DEFAULT_SEED
    temperature: float = DEFAULT_TEMPERATURE


ConfigStore.instance().store(name="experiment_schema", node=ExperimentSchema)
```

An original minimal primary YAML, after that registration:

```yaml
defaults:
  - experiment_schema
  - _self_
run_id: run-example
eval_dataset_version: eval-v1
model: gpt-4.1-mini
prompt_version: prompt-v1
hydra:
  job:
    chdir: false
```

For larger experiments, insert approved config-group selections before `_self_`
and test their packages/namespaces. Declare the order explicitly: **schema <
selected groups in Defaults List order < primary YAML (`_self_` last) < CLI
overrides** for overlapping fields in the same package. Moving `_self_` changes
the winner. Do not silently add deployment environment settings to this order.
After trusted composition, convert public fields to plain values and pass them
through application validation; structured typing does not enforce business
bounds, public-data policy or reproducibility.

The example's `prompt-v1` is a public planning identifier, not proof of an exact
managed-prompt version. Before a billed run, resolve the identifier once, freeze
the resulting prompt and numeric version for that job, and record both alongside
the dataset fingerprint and scorer versions. Never resolve a mutable label again
between cases in a comparison. Record provider-supported parameters explicitly:
not every model accepts temperature or seed, and unsupported settings must fail
validation rather than be silently dropped.

## Bounded sweeps and isolated outputs

- Expand only explicit finite axes. `plan_runs` takes nonempty, unique seeds and
  temperatures, validates both, computes their Cartesian job count before
  expansion, and rejects counts above a caller budget or the hard **16-job** cap.
  Its order is seed-major. Axis values override the base seed/temperature per job.
  A single run uses singleton axes. It never executes the experiment.
- Native Hydra `--multirun`/`-m` uses combinations; two seeds by three
  temperatures means six jobs, each a billed model run over the whole evaluation
  set. CLI sweeps override `hydra.sweeper.params` for the same parameter.
  BasicSweeper is local/serial by default; a different plugin changes execution.
  Apply a pre-launch **total** job/cost/concurrency budget, not just batch size.
  Reject or explicitly bound ranges, globs, optimizer trials and plugin-specific
  adaptive searches; this template does not parse Hydra sweep grammar.
- Capture original launch directory before any `chdir`; resolve input paths
  against it and output paths against an explicit trusted root. Set
  `hydra.job.chdir` explicitly (false by default since 1.2). In native code use
  `get_original_cwd()`, `to_absolute_path()` and
  `HydraConfig.get().runtime.output_dir`, not an assumed current directory.
- The stdlib planner fixes absolute paths without changing cwd. Outputs are
  `<root>/<run_id>/job-<index>`. Lowercase `run-` labels prevent path traversal
  and Windows reserved basenames. `write_manifest` reserves each directory with
  `exist_ok=False`, writes `manifest.json` exclusively and refuses reuse. A write
  failure can leave an incomplete directory: inspect it; never silently resume.
  All directories/parents must be consumer-controlled, not adversarial symlinks.
- Hydra creates its own directories before the application body. Do **not** point
  this exclusive directory writer at an already-created Hydra job directory.
  A native adapter must reserve a unique launch namespace before Hydra starts,
  derive job-specific run/sweep paths and write manifests exclusively inside
  Hydra's actual output directory. Test collision refusal and `chdir` both ways.
  Timestamp-only directory names are not a uniqueness guarantee.
- Persist public run ID, job index, applied seed and temperature, model, prompt
  version, evaluation dataset version and config schema version, plus original/output locations. Freeze code/config
  for the sweep: Hydra composes jobs lazily. In the consumer also record code
  revision, dependency-lock/config digests and RNG/library/device determinism
  settings. Provider seeds are best effort: record the returned model snapshot
  or system fingerprint and repeat runs to measure variance instead of assuming
  identical outputs.

## Secrets and code-execution boundaries

Keep credentials entirely outside the experiment tree and CLI overrides. Inject
them separately at the trusted adapter using existing secret delivery. Do not
resolve secret environment variables into composed config. Hydra's automatic
`.hydra/config.yaml`, `hydra.yaml`, `overrides.yaml`, logs and `--cfg ... --resolve`
can expose inputs before application redaction runs. Disabling `hydra.output_subdir`
does not sanitize logs or overrides.

The JSON template accepts only public fields, never serializes deployment
settings, and does not read environment secrets. Public labels must genuinely be
public; no validator can detect a secret deliberately supplied as a valid label.
Manifests contain local paths: protect them and remove private locations before
publishing. Do not dump the original input or validation exception internals.

Untrusted `_target_`, nested targets, resolvers, plugins and logging factories can
execute Python. Validation after interpolation is too late to prevent resolver
execution. Accept only reviewed composition sources and resolver/plugin code;
do not resolve arbitrary third-party config in the application process. Prefer
a closed application-owned mapping from validated labels to reviewed factories,
not user-selected imports.

Current advanced instantiate docs describe `execution_whitelist()` and
`_execution_whitelist_`; `None` can preserve legacy behavior. Do not assume old
versions provide this API or that new versions enforce it automatically. If the
consumer uses instantiate, supply a trusted explicit exact-target whitelist
supported by its pinned version; review nested targets, context stacking/reset,
logging and call-site overrides too. Do not disable checks or accept a whitelist
from input. This is **not a sandbox** for arbitrary Python, imports, resolvers or
plugins. This capability never calls unchecked `instantiate`/`call` or enables an
execution tool.

## Verification and limits

The dedicated repository regressions execute the relocated stdlib asset, checking
precedence, validation, finite job bounds, per-job isolation, collision refusal,
provenance and absence of synthetic secrets in errors/files/output. They do not
import Hydra. Consumer verification must additionally run the pinned native
Hydra/OmegaConf schema and precedence cases, pre-launch budgets, resolver/target
restrictions, actual job directories and all automatic/logged artifacts with a
synthetic secret. No native Hydra runtime compatibility is certified here.

## Primary sources

- [Hydra repository and release status](https://github.com/hydra-ecosystem/hydra)
- [1.3 structured config introduction](https://hydra.cc/docs/1.3/tutorials/structured_config/intro/)
- [Current instantiate and execution whitelist contract](https://hydra.cc/docs/advanced/instantiate_objects/overview/)
- [Working directory and output artifacts](https://hydra.cc/docs/tutorials/basic/running_your_app/working_directory/)
- [Multirun, sweep precedence and lazy composition](https://hydra.cc/docs/tutorials/basic/running_your_app/multi-run/)
