# CLI conventions

Reviewed 2026-10-23. Implemented by [cli.py.template](../assets/cli.py.template).

## Streams

- stdout carries the result only: text for people, or exactly one JSON
  document with `--json`. Nothing else is printed there.
- stderr carries diagnostics, progress, warnings, and error messages in the
  form `prog: error: message`.
- Do not color or decorate output when stdout is not a terminal, or when
  `NO_COLOR` is set.

## Exit codes

| Code | Meaning | Typical cause |
| --- | --- | --- |
| 0 | Success | |
| 1 | General failure | Unexpected condition, broken pipe |
| 2 | Usage error | Unknown option, missing argument (argparse default) |
| 65 | Data error | Input file exists but its content is invalid |
| 66 | No input | Input file missing or unreadable |
| 78 | Configuration error | Invalid config file or setting |
| 130 | Interrupted | Ctrl+C (128 plus SIGINT) |

Codes above 2 follow BSD `sysexits.h`; document them in `--help` epilogs or
the README. `os.EX_*` constants exist only on Unix, so define an `IntEnum`.

## Machine output

- `--json` is global, so every command supports it.
- Emit stable keys (`sort_keys=True`), strings for decimals and timestamps
  (ISO 8601 with offset), and no human formatting inside values.
- Treat the JSON shape as a public contract: add fields, never rename or
  remove them without a version note.

## Configuration precedence

Flags, then environment (`PREFIX_NAME`), then config file, then defaults.

- The config file path comes from `--config` or `PREFIX_CONFIG`; do not read
  files from the user's home directory implicitly in code paths tests reach.
- Validate the merged result once; report the setting name, not the secret.
- Provide a `config` command that prints each effective value and its source.
- TOML config files parse with `tomllib`; reject unknown keys.

## Secrets

- Never accept secrets as positional arguments or option values; they appear
  in process listings and shell history.
- Read them from an environment variable or `--token-file PATH`, or prompt
  with `getpass` for interactive use.
- Keep secrets out of `repr`, logs, `--json` output, and error messages;
  report only whether they are set.

## Logging

Configure logging once in `main` after parsing `-v`/`-q`, with a handler on
stderr for the package logger. Library modules call
`logging.getLogger(__name__)` and never configure handlers. See the logging
reference of `kit-python-service`.

## Primary sources

- [Python: argparse](https://docs.python.org/3/library/argparse.html)
- [Python: tomllib](https://docs.python.org/3/library/tomllib.html)
- [Python: logging HOWTO, configuring logging for a library](https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library)
- [Python: Note on SIGPIPE](https://docs.python.org/3/library/signal.html#note-on-sigpipe)
- [FreeBSD sysexits(3)](https://man.freebsd.org/cgi/man.cgi?query=sysexits&sektion=3)
- [NO_COLOR](https://no-color.org/)
- [Command Line Interface Guidelines](https://clig.dev/)
