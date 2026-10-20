# Native-first catalogue

Before keeping custom code or adding a dependency, check whether the runtime
already provides the capability. The tables list common reinventions and the
native facility that usually replaces them. Always confirm the facility exists
in the minimum runtime version the project supports, and that its edge-case
behavior matches what callers rely on.

## Python standard library

| Reinvented | Native facility | Watch for |
| --- | --- | --- |
| Command-line parsing by slicing `sys.argv` | `argparse` | Exit status 2 on usage errors |
| Path joining with string concatenation | `pathlib.Path` | Windows separators and drive letters |
| Hand-written CSV splitting | `csv` reader and writer | Quoting, embedded newlines, dialects |
| JSON via string formatting | `json.dumps` / `json.loads` | `ensure_ascii`, `sort_keys` for stable output |
| TOML configuration parsing | `tomllib` (read-only) | Writing TOML still needs another tool |
| Date parsing with regular expressions | `datetime.date.fromisoformat`, `datetime.datetime.fromisoformat` | Time zones; use timezone-aware values |
| Memoization dictionaries | `functools.cache`, `functools.lru_cache` | Unbounded growth with `cache` |
| Counting with dict bookkeeping | `collections.Counter` | Ordering of `most_common` ties |
| Grouping with nested ifs | `itertools.groupby` after sorting, or `collections.defaultdict` | `groupby` needs sorted input |
| Manual temporary files | `tempfile.TemporaryDirectory`, `tempfile.NamedTemporaryFile` | Windows file locking with `delete=True` |
| Ad hoc enums as string constants | `enum.Enum`, `enum.StrEnum` | Serialization of members |
| Hand-written record classes | `dataclasses.dataclass` with `frozen=True` and `slots=True` | Mutable default values |
| Retrying with loops and sleeps in threads | `asyncio` timeouts or a small explicit loop | Jitter and idempotency are still your job |
| Custom thread pools | `concurrent.futures.ThreadPoolExecutor` | Exceptions surface on `result()` |
| String templating for paths in URLs | `urllib.parse` (`urljoin`, `urlencode`, `quote`) | Double encoding |
| Hashing helpers | `hashlib`, `hmac.compare_digest` | Use constant-time comparison for secrets |
| Logging wrappers | `logging` with module loggers | Configure handlers once at the entry point |
| Shelling out to `grep` or `find` | `pathlib.Path.rglob`, `re` | Large trees: stream instead of listing |

## JavaScript, TypeScript and the web platform

| Reinvented | Native facility | Watch for |
| --- | --- | --- |
| Deep clone via JSON round trip | `structuredClone` | Functions and class instances are not cloned |
| Query string building | `URL` and `URLSearchParams` | Repeated keys |
| Date formatting libraries for simple display | `Intl.DateTimeFormat`, `Intl.RelativeTimeFormat` | Locale data availability |
| Number and currency formatting | `Intl.NumberFormat` | Rounding mode defaults |
| HTTP client wrappers for simple calls | `fetch` with `AbortController` | No rejection on HTTP error status |
| Unique identifiers | `crypto.randomUUID` | Requires a secure context in browsers |
| Array helpers for grouping | `Object.groupBy`, `Map.groupBy` | Runtime version support |
| Utility flatten and includes helpers | `Array.prototype.flat`, `includes`, `at` | Sparse arrays |
| Event emitter classes in the browser | `EventTarget` and `CustomEvent` | Listener cleanup |
| Custom test runners for small Node packages | `node:test` and `node:assert` | Reporter differences in CI |
| Reading files with callbacks wrapped manually | `node:fs/promises` | Error codes on missing files |

## Platform, build and delivery

| Reinvented | Native facility | Watch for |
| --- | --- | --- |
| Shell scripts that pin tool versions | The package manager's lockfile | Commit the lockfile |
| Custom pre-commit runners | The repository's existing hook framework or task runner | One source of truth for commands |
| Bespoke CI caching scripts | The CI provider's cache action or setting | Cache keys tied to lockfile hashes |
| Hand-rolled environment loading | The runtime or framework settings mechanism | Never commit secret values |
| Copying configuration between services | Shared configuration in the infrastructure tool | Ownership of the shared value |
| Hand-written HTML form validation | Native constraint validation attributes | Accessible error messages still need wiring |

## How to present a native replacement

1. Name the native API and link its official documentation.
2. Show the custom code's tested edge cases and the native behavior for each.
3. If behavior differs on a case a caller relies on, either keep a thin,
   documented adapter for that case only, or change the caller with the owner's
   agreement.
4. Delete the custom implementation and its tests in the same change; keep or
   add tests at the call sites that pin the behavior.

## Sources

- [Python standard library](https://docs.python.org/3/library/index.html)
- [Python functools](https://docs.python.org/3/library/functools.html)
- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Node.js API documentation](https://nodejs.org/api/)
- [Node.js test runner](https://nodejs.org/api/test.html)
- [MDN structuredClone](https://developer.mozilla.org/en-US/docs/Web/API/Window/structuredClone)
- [MDN Intl](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl)
- [MDN URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams)
- [MDN constraint validation](https://developer.mozilla.org/en-US/docs/Web/HTML/Constraint_validation)
