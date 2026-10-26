# Packaging entry points, SDK design, and tests

Reviewed 2026-10-23. Build backends, metadata, and release artifacts belong to
the `kit-python-package` skill.

## Entry points

```toml
[project.scripts]
shop = "shop.cli:main"
```

- The console script calls `main()` and uses its return value as the exit
  status; `main` must therefore return an `int` rather than call `sys.exit`.
- [`__main__.py`](../assets/__main__.py.template) contains only
  `raise SystemExit(main())` under the `__name__` guard, so `python -m shop`
  and the script behave identically.
- Read the version with `importlib.metadata.version("<distribution>")`;
  never hard-code it in two places.
- Import time stays cheap: no network, no config loading, no heavy imports
  at module top level in the CLI module when start-up time matters.

## SDK design (when the CLI wraps a library)

| Rule | Reason |
| --- | --- |
| The library exposes typed functions and classes; the CLI is one thin client of them | Other programs reuse the library without parsing text |
| The library raises specific exceptions; only the CLI maps them to exit codes | `sys.exit` in a library kills the host program |
| The library never prints and never configures logging | The host owns its streams and handlers |
| Public API is listed in `__all__` and documented; private modules start with `_` | Callers know what is stable |
| Network clients accept injected sessions or transports and timeouts | Tests run offline; callers control resources |
| Version the SDK with semantic versioning and keep deprecations for one minor release | Callers can upgrade safely |

## Tests

- Unit: call `main([...], env={...})`; assert exit code, stdout, and stderr
  separately with `capsys`; write input files under `tmp_path`.
- Configuration: one test per precedence layer and one for the `config`
  command's sources.
- Secrets: a test proves the token never appears in stdout or stderr.
- Smoke: run `python -m shop --help` in a subprocess with a timeout once;
  more subprocess tests slow the suite without adding coverage.
- For Click or Typer, use their `CliRunner` for in-process tests and keep the
  same assertions.

[test_cli.py.template](../assets/test_cli.py.template) implements these cases.

## Primary sources

- [Python Packaging User Guide: Entry points](https://packaging.python.org/en/latest/specifications/entry-points/)
- [Python Packaging User Guide: Writing pyproject.toml, scripts](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#creating-executable-scripts)
- [Python: `__main__`](https://docs.python.org/3/library/__main__.html)
- [Python: importlib.metadata](https://docs.python.org/3/library/importlib.metadata.html)
- [pytest: capsys](https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html)
- [Click: Testing](https://click.palletsprojects.com/en/stable/testing/)
- [Semantic Versioning 2.0.0](https://semver.org/)
