---
description: Centralize repeated cross-cutting code (error mapping, logging, retries, validation) in typed decorators or helpers only where it pays off.
argument-hint: Python package, module, or path to review
agent: agent
---

# Centralize cross-cutting behavior

Replace copy-pasted wrappers with one tested owner, and nothing more.

## Input

- The user-supplied argument names the package, module, or path. When it is
  empty, review the whole Python source tree.

## Procedure

1. Load [kit-python-decorators](../skills/kit-python-decorators/SKILL.md) and
   the [callable decision guide](../skills/kit-python-service/references/callables-and-decorators.md).
2. Search for repeated shapes: `try/except` that maps errors to exit codes or
   responses, timing or logging around calls, retries, input validation,
   caching, atomic file writes, and resource setup and teardown.
3. List each candidate with every occurrence (`path:line`). Keep only those with
   three or more real uses or a clear correctness gain.
4. Pick the smallest tool: a plain helper first, then `functools.cache`,
   `contextlib.contextmanager`, or a decorator typed with `ParamSpec` and
   `functools.wraps`. Never hide control flow the caller must see.
5. Place it in the layer that owns the concern; inner layers never import outer
   ones. Respect stdlib-only or pre-install scripts.
6. Write tests for the wrapper first: binding, metadata, error propagation, and
   async behavior where relevant. Then replace call sites one group at a time.
7. Run the linter, type checker, and focused tests after each group.

## Acceptance gates

- [ ] Each new wrapper has three or more call sites and its own tests.
- [ ] Signatures and metadata survive wrapping; the type checker is clean.
- [ ] Behavior and error types are unchanged at every call site.

## Output

Candidates found and rejected with reasons, wrappers added with their home
module, call sites replaced, and the commands run with results.
