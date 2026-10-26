# Python versions and features to adopt

Support status from the Python developer guide, reviewed 2026-10-23. Re-check
the [status page](https://devguide.python.org/versions/) before choosing a
target; dates move.

## Status

| Version | Status on 2026-10-23 | First release | End of life |
| --- | --- | --- | --- |
| 3.15 | bugfix | 2026-10 | 2031-10 |
| 3.14 | bugfix | 2025-10 | 2030-10 |
| 3.13 | security | 2024-10 | 2029-10 |
| 3.12 | security | 2023-10 | 2028-10 |
| 3.11 | security | 2022-10 | 2027-10 |
| 3.10 | end of life | 2021-10 | 2026-10 |

Choosing a target:

- Applications: the newest version that every runtime image, dependency and
  deployment platform supports; at least one release still in bugfix.
- Libraries: the oldest version still receiving security fixes as the minimum,
  and every supported version in the CI matrix.
- Never target an end-of-life version for new work; plan the exit for one in
  use with the ledger.

## Features by version and when to adopt them

| Feature | Since | Adopt when | Leave alone when |
| --- | --- | --- | --- |
| Builtin generics `list[int]` (PEP 585) | 3.9 | always for the minimum 3.9+; Ruff `UP006`, `UP035` | never |
| `X \| Y`, `X \| None` (PEP 604) | 3.10 | always for the minimum 3.10+; Ruff `UP007`, `UP045` | runtime annotation readers on older versions |
| Structural pattern matching `match` (PEP 634) | 3.10 | dispatch on the shape of tagged data or ASTs with several cases | a two-branch `if`, or plain value lookup that a dict expresses better |
| `enum.StrEnum` | 3.11 | closed string sets that cross a wire or a database; Ruff `UP042` | members whose `str()` output is relied on in its old `Class.MEMBER` form |
| `ExceptionGroup`, `except*` (PEP 654) | 3.11 | concurrent work that can fail in several places at once | single failures; do not wrap one error in a group |
| `asyncio.TaskGroup`, `asyncio.timeout` | 3.11 | replacing `gather` plus manual cancellation, or `wait_for` | fire-and-forget tasks that must outlive the caller |
| `tomllib` (PEP 680) | 3.11 | replacing `toml` or `tomli` for reading | writing TOML (needs a third-party writer) |
| `typing.Self` (PEP 673) | 3.11 | methods returning their own class | never |
| Type parameter syntax and `type` aliases (PEP 695) | 3.12 | generic classes, functions and aliases; Ruff `UP040`, `UP046`, `UP047` | code that must still run on 3.11 or earlier |
| `typing.override` (PEP 698) | 3.12 | overriding methods in class hierarchies checked by a type checker | flat code without inheritance |
| Type parameter defaults (PEP 696), `warnings.deprecated` (PEP 702) | 3.13 | public APIs that deprecate names with a type-checker-visible marker | private code |
| Deferred evaluation of annotations (PEP 649, PEP 749) | 3.14 | dropping `from __future__ import annotations` once the minimum is 3.14 and policy agrees | a minimum of 3.13 or earlier: removal changes evaluation time |
| Template string literals (PEP 750) | 3.14 | building safe SQL, HTML or shell fragments with a processor | ordinary formatting, where f-strings stay |
| Explicit `lazy` imports (PEP 810) | 3.15 | measured startup cost from heavy imports | modules whose import has required side effects |
| UTF-8 mode by default (PEP 686) | 3.15 | already passing `encoding="utf-8"` everywhere; verify file I/O on Windows | code that relied on the locale encoding |

## Removals that break upgrades

- Python 3.12 removed `distutils` (PEP 632); use setuptools or `packaging`.
- Python 3.13 removed the PEP 594 "dead batteries" (`cgi`, `cgitb`, `crypt`,
  `telnetlib`, `nntplib`, `imghdr`, `sndhdr`, `pipes` and others) and
  `lib2to3`.
- `datetime.datetime.utcnow()` and `utcfromtimestamp()` are deprecated since
  3.12; use aware datetimes with `datetime.UTC` (Ruff `DTZ`, `UP017`).

Read the "Removed" and "Deprecated" sections of each What's New document
between the current and target versions; they are the authoritative list.

## Primary sources

- [Status of Python versions](https://devguide.python.org/versions/)
- [What's New in Python 3.15](https://docs.python.org/3.15/whatsnew/3.15.html)
- [What's New in Python 3.14](https://docs.python.org/3/whatsnew/3.14.html)
- [What's New in Python 3.13](https://docs.python.org/3/whatsnew/3.13.html)
- [What's New in Python 3.12](https://docs.python.org/3/whatsnew/3.12.html)
- [What's New in Python 3.11](https://docs.python.org/3/whatsnew/3.11.html)
- [PEP 585](https://peps.python.org/pep-0585/), [PEP 604](https://peps.python.org/pep-0604/),
  [PEP 634](https://peps.python.org/pep-0634/), [PEP 654](https://peps.python.org/pep-0654/),
  [PEP 695](https://peps.python.org/pep-0695/), [PEP 749](https://peps.python.org/pep-0749/),
  [PEP 594](https://peps.python.org/pep-0594/)
- [asyncio task groups](https://docs.python.org/3/library/asyncio-task.html#task-groups)
- [enum.StrEnum](https://docs.python.org/3/library/enum.html#enum.StrEnum)
