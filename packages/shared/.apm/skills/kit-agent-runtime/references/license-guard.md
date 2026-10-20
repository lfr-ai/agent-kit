# License guard

[license_guard.py](../assets/license_guard.py) checks the licenses declared by
installed Python distributions against a reviewed allowlist. It reads metadata
only through the standard library, performs no network access, and does not
interpret license texts. It is an early warning for dependency review, not a legal
opinion.

## Evidence order

1. `License-Expression`: an SPDX expression in core metadata 2.4 (PEP 639).
2. `Classifier` values that start with `License ::`, mapped to SPDX identifiers.
   Ambiguous classifiers map to explicit `LicenseRef-` names, for example
   `LicenseRef-BSD-unspecified` for the generic BSD classifier. Several license
   classifiers on one distribution are combined with `AND`.
3. `License`: used only when it is a single short line; it must parse as an SPDX
   expression to pass.

Distributions with no usable evidence are reported as `unknown`.

## Evaluation

- Identifiers compare case-insensitively.
- `A OR B` passes when either side is allowed.
- `A AND B` passes only when both sides are allowed; any denied side denies it.
- `A WITH E` passes only when the full `A WITH E` string is allowed, and is denied
  when `A` is denied.
- A per-distribution exception passes only when its `license` equals the observed
  expression (compared case-insensitively) and it has not expired. An expired
  exception is a finding of its own, so stale approvals surface.

Statuses: `allowed`, `excepted`, `denied`, `unknown`, and `expired-exception`.
Anything other than `allowed` or `excepted` is a finding and makes the exit code `1`.
An unusable allowlist exits `2`.

## Allowlist

Start from [license_allowlist.json.template](../assets/license_allowlist.json.template).
Fields are closed: `schema_version`, `description`, `allowed`, `denied`, and
`exceptions`. Exception keys are distribution names normalized by lowercasing and
replacing runs of `-`, `_`, and `.` with `-`. Each exception needs `license`,
`reason`, and optionally `expires` as an ISO date.

The template's lists are examples. The consumer's license policy owner decides
which licenses are acceptable for the product and distribution model.

## Running

```text
python license_guard.py --allowlist license_allowlist.json
python license_guard.py --allowlist license_allowlist.json --path .venv/Lib/site-packages
python license_guard.py --allowlist license_allowlist.json --format json --today 2026-01-31
python license_guard.py --self-test
```

Text output prints one `path:1: message` line per finding, where the path is the
distribution's `METADATA` file when it is listed, then a summary line. Pass
`--today` in tests so expiry is deterministic.

## Limits

- Only installed Python distributions are checked; vendored code, system packages,
  container base images, and other ecosystems need their own tools.
- Metadata can be wrong or incomplete. Unknown results need human review of the
  project's license files.
- The guard does not decide compatibility between licenses or obligations such as
  attribution; it only enforces the reviewed lists.

## Sources

- [Python core metadata specification](https://packaging.python.org/en/latest/specifications/core-metadata/)
- [PEP 639: license expressions in metadata](https://peps.python.org/pep-0639/)
- [importlib.metadata](https://docs.python.org/3/library/importlib.metadata.html)
- [SPDX license expressions](https://spdx.github.io/spdx-spec/v3.0.1/annexes/spdx-license-expressions/)
