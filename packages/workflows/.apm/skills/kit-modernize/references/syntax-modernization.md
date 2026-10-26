# Syntax, typing and async modernization

Mechanical rewrites are safe only when the tool and the reviewer agree they do
not change behavior. Apply one rule family per batch with Ruff, review unsafe
fixes by hand, and keep tests unchanged.

## Typing

| Legacy | Modern | Minimum Python | Ruff rule |
| --- | --- | --- | --- |
| `List[int]`, `Dict[str, int]`, `Type[X]` | `list[int]`, `dict[str, int]`, `type[X]` | 3.9 | `UP006` |
| `from typing import List, Callable` | builtins and `collections.abc` imports | 3.9 | `UP035` |
| `Optional[X]` | `X \| None` | 3.10 | `UP045` |
| `Union[X, Y]` | `X \| Y` | 3.10 | `UP007` |
| `"Quoted"` annotations | unquoted, with lazy annotations or reordering | 3.14 or `__future__` | `UP037` |
| `T = TypeVar("T")` plus `Generic[T]` | `class Box[T]:` | 3.12 | `UP046` |
| generic function with module-level `TypeVar` | `def first[T]` with parameters typed `list[T]` | 3.12 | `UP047` |
| `Alias: TypeAlias = ...` | `type Alias = ...` | 3.12 | `UP040` |
| `class Color(str, Enum)` | `class Color(StrEnum)` | 3.11 | `UP042` |

Runtime annotation readers need care:

- Pydantic, dataclasses, FastAPI, attrs and dependency-injection containers
  evaluate annotations. `X | None` at runtime needs 3.10; with
  `from __future__ import annotations` the strings are resolved later, which
  fails for names imported only under `TYPE_CHECKING`.
- A PEP 695 `type` alias is a `TypeAliasType`, not the aliased class; code that
  calls `isinstance` with an alias or passes it where a class is expected
  breaks.
- Ruff's `lint.pyupgrade.keep-runtime-typing` keeps old spellings for files that
  use the future import while targeting versions before 3.10.

## Strings

| Legacy | Modern | Ruff rule |
| --- | --- | --- |
| `template % value` | f-string or `str.format` | `UP031` |
| `"{}".format(value)` with simple arguments | f-string | `UP032` |
| logger calls with f-strings | lazy `%s` arguments | `G004` |

Keep `%`-style placeholders in logging calls; that is the logging API, not
legacy formatting.

## Async

| Legacy | Modern | Since |
| --- | --- | --- |
| `loop = asyncio.get_event_loop(); loop.run_until_complete(main())` | `asyncio.run(main())` | 3.7 |
| `asyncio.gather` plus manual cancellation on failure | `async with asyncio.TaskGroup() as group:` | 3.11 |
| `asyncio.wait_for(coro, timeout)` | `async with asyncio.timeout(seconds):` | 3.11 |
| `loop.run_in_executor(None, blocking)` | `await asyncio.to_thread(blocking)` | 3.9 |
| `get_event_loop()` inside coroutines | `asyncio.get_running_loop()` | 3.7 |

`TaskGroup` cancels sibling tasks on the first failure and raises an
`ExceptionGroup`; callers that caught one exception type need `except*`. Test
the failure path, not only the happy path, before swapping `gather`.

## Paths

Where `pathlib` is the policy, replace `os.path` calls file by file (Ruff
`PTH` rules flag them; the bundled checker's `--pathlib` option counts them).
`Path.read_text` and `write_text` need an explicit `encoding`.

## Compatibility shims to remove

| Shim | Remove when |
| --- | --- |
| `if sys.version_info >= (3, N):` branches | the minimum version is at least `3.N` (Ruff `UP036`) |
| `try: import tomllib except ImportError: import tomli` | the minimum is 3.11 |
| `from typing_extensions import Self, override, ...` | the name is in `typing` at the minimum version |
| `six` helpers, `__future__` imports other than `annotations` | always on Python 3 (Ruff `UP010` and friends) |
| backport packages in dependencies | the stdlib module covers the used API |

## Anti-patterns

- Running `ruff check --select UP --fix --unsafe-fixes` across the repository
  in one commit.
- Converting every `if`/`elif` to `match`; pattern matching is for shape-based
  dispatch.
- Introducing `ExceptionGroup` where only one error can happen.
- Removing `from __future__ import annotations` while the minimum Python is
  3.13 or earlier and annotations reference names defined later.

## Primary sources

- [Ruff pyupgrade rules](https://docs.astral.sh/ruff/rules/#pyupgrade-up)
- [Ruff flake8-future-annotations rules](https://docs.astral.sh/ruff/rules/#flake8-future-annotations-fa)
- [Ruff setting lint.pyupgrade.keep-runtime-typing](https://docs.astral.sh/ruff/settings/#lint_pyupgrade_keep-runtime-typing)
- [typing: type aliases and generics](https://docs.python.org/3/library/typing.html)
- [asyncio task groups and timeouts](https://docs.python.org/3/library/asyncio-task.html)
- [Annotations best practices](https://docs.python.org/3/howto/annotations.html)
- [pathlib](https://docs.python.org/3/library/pathlib.html)
