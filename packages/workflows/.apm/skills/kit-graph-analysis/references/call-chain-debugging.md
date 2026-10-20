# Call-chain debugging

When a failure appears far from its cause, reconstruct the path from the entry
point to the symptom, then test hypotheses along that path. The graph narrows
where to look; runtime evidence decides.

## Procedure

1. **Pin the symptom.** Capture the exact error, stack trace, request or job
   identifier, revision and environment. Reproduce locally if possible; if
   not, collect enough logs to identify the entry point.
2. **Identify the entry point.** Route handler, command, job, message
   consumer or test. Record its module.
3. **Identify the symptom site.** The frame that raised, logged or produced
   the wrong value. Record its module and function.
4. **Find candidate chains.** Query the shortest module chain between entry
   and symptom, then list alternative routes:

   ```text
   python assets/import_graph.py src/shop --chain shop.api.views shop.storage.db
   python assets/import_graph.py src/shop --forward shop.api.views --depth 3
   ```

   The stack trace, when available, is the authoritative chain for this
   failure; use the graph to see what else the chain could have passed
   through (other implementations, middleware, fallbacks).
5. **Descend to calls.** Within each module on the chain, follow the call with
   editor call hierarchy or a word-bounded search for the function name.
   Note branches, configuration checks and data transformations on the way.
6. **Mark state changes.** For each hop, write down what the data looks like on
   entry and exit (types, nullability, units, encoding, time zone). Most
   distant failures come from a silent transformation in the middle.
7. **Form one hypothesis at a time.** Choose the hop where the observed data
   first deviates from the expected data. Predict what a log line, assertion
   or breakpoint at that hop will show.
8. **Test the hypothesis** with the smallest probe: a focused unit test that
   reproduces the hop, a temporary log line, a debugger breakpoint. Remove
   temporary probes before committing.
9. **Fix at the cause, not the symptom.** Add a regression test at the hop
   that introduced the deviation, and, if the symptom site should have
   rejected the bad data, an assertion or validation there too.
10. **Record the chain** in the [stage worksheet](../assets/templates/graph-stages-template.md)
    so the next person sees the path and the evidence.

## Patterns to check along a chain

| Pattern | What to look for |
| --- | --- |
| Silent defaulting | `get(key, default)`, `or` fallbacks, optional fields becoming empty strings |
| Unit or format drift | cents versus currency units, naive versus timezone-aware values, encodings |
| Shadowed implementation | two classes or functions with the same name in different modules |
| Middleware and decorators | wrappers that catch, retry, cache or transform before the visible call |
| Configuration branch | different code paths per environment or feature flag |
| Lazy import | function-local imports that load a different module than expected |
| Cache staleness | memoized results computed under old inputs |

## When the graph and the stack trace disagree

- A frame appears that the graph says is unreachable: look for dynamic
  dispatch, plugin registration or a decorator that wraps the call.
- The graph shows an edge the trace never uses: a branch was not taken; check
  the condition that selects it.
- Neither explains the symptom: the failing code may live outside the scanned
  package (a dependency, generated code or another service).

## Sources

- [Python traceback module](https://docs.python.org/3/library/traceback.html)
- [Python debugger (pdb)](https://docs.python.org/3/library/pdb.html)
- [Python logging HOWTO](https://docs.python.org/3/howto/logging.html)
