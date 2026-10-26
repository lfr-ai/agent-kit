---
name: kit-cli-tool
description: Use when building or reviewing a Python CLI or SDK entry point, exit codes, JSON output, config, or CLI tests.
license: MIT
---

# Build a Python CLI with a stable contract

## Procedure

1. Read the existing entry points, `[project.scripts]`, and how commands reach
   application services. Choose the parser with the
   [guide](references/guide.md); default to `argparse` when no dependency is
   justified.
2. Start from the [CLI template](assets/cli.py.template): `main(argv, env=...)`
   returns an exit code, subcommands carry handlers, and a global `--json`
   switches stdout to one JSON document.
3. Apply the [conventions](references/conventions.md): data on stdout,
   diagnostics on stderr, documented exit codes, precedence of flags over
   environment over config file over defaults, and a `config` command that
   shows each value's source.
4. Read secrets from the environment or a file option, never from argv;
   report them only as set or unset.
5. Configure logging once in `main` from `-v` and `-q`; library modules only
   create loggers.
6. Wire `python -m` with the [`__main__` template](assets/__main__.py.template)
   and a console script per
   [packaging, SDKs, and tests](references/packaging-and-testing.md). Keep
   reusable logic in a library that raises exceptions instead of exiting.
7. Test through `main` with an injected environment and one subprocess smoke
   test ([test template](assets/test_cli.py.template)); cover usage, missing
   input, malformed data, configuration errors, precedence, and secret
   redaction.
8. Run the tests and the project gate; check `--help` output by hand once.

## Acceptance gates

- `main` returns an `int` for success, usage errors, `--help`, and every
  handled failure; library code never calls `sys.exit` or prints.
- stdout contains only the result; with `--json` it parses as one document
  with stable keys.
- Each documented exit code has a test; errors print one actionable stderr
  line without secrets.
- The precedence order is tested per layer and visible through `config`.
- `python -m <package>` and the console script call the same `main`.
