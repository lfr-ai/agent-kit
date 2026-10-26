# CLI and SDK guide: framework choice, failure modes, verification

Reviewed 2026-10-23. Detail: [CLI conventions](conventions.md) and
[packaging, SDKs, and tests](packaging-and-testing.md). Package metadata and
builds belong to the `kit-python-package` skill.

## Choosing a parser

| Situation | Choose | Why |
| --- | --- | --- |
| Few commands, no extra dependency allowed, library or toolkit code | `argparse` | Standard library, stable, subcommands and help built in |
| Many commands, type-hint driven options, rich help | Typer | Builds on Click; signatures become options |
| Composable command groups, plugins, fine control of parsing | Click | Mature decorators, context objects, testing runner |
| Shell-completion and colored output are product requirements | Typer or Click | Built-in completion and styling |

Whichever you choose, keep the contract in this skill: `main(argv) -> int`,
stdout for data, stderr for diagnostics, documented exit codes, `--json`, and
layered configuration. Framework objects stay in the presentation module;
commands call application services.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Pipelines break on warnings | Diagnostics or logs written to stdout | Logs and errors to stderr only |
| Scripts cannot detect failure | Exit 0 on error, or `sys.exit` inside library code | Return documented codes from `main`; raise in libraries |
| Secrets visible in `ps` output or shell history | Token passed as an argument | Environment variable or `--token-file` |
| Different behavior on CI and laptops | Hidden reads of personal config files or environment | Explicit `--config` and `PREFIX_*` variables; `config` command shows sources |
| Duplicate or missing log lines | Logging configured in library modules or per call | Configure once in `main`; libraries only `getLogger(__name__)` |
| Traceback when piped to `head` | `BrokenPipeError` not handled | Redirect stdout to the null device and exit non-zero |
| Tests pollute each other | `main` reads `os.environ` directly | Inject an environment mapping |

## Verification

- In-process tests call `main([...], env={...})` and assert exit code,
  stdout, and stderr separately ([test template](../assets/test_cli.py.template)).
- One subprocess smoke test runs `python -m <package> --help` to prove the
  entry point is wired after installation.
- Error paths: missing input file, malformed data, invalid configuration,
  usage error, and help return the documented codes.
- `--json` output parses as one JSON document and is stable (sorted keys).

## Primary sources

- [Python: argparse](https://docs.python.org/3/library/argparse.html)
- [Python: `__main__` and `python -m`](https://docs.python.org/3/library/__main__.html)
- [Typer documentation](https://typer.tiangolo.com/)
- [Click documentation](https://click.palletsprojects.com/)
- [Command Line Interface Guidelines](https://clig.dev/)
