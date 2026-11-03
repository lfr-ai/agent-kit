---
name: kit-python-decorators
description: Use when repeated Python cross-cutting behavior warrants a typed decorator.
license: MIT
---

# Preserve decorated callable contracts

1. Identify at least two current consumers of the same stable behavior. Keep
   one-off logic as a plain function or explicit wrapper; do not manufacture
   reuse to justify a decorator.
2. Pin parameter kinds, results, errors, side effects, and invocation kind.
   Review the [decorator guide](references/decorators.md).
3. Prefer a standard-library or framework facility when it already owns the
   behavior. Keep domain rules and dependency construction explicit.
4. If a custom decorator is justified, use `functools.wraps` and preserve
   parameters/results with `ParamSpec`. The
   [policy template](assets/typed_decorators.py.template) illustrates shared
   sync/async behavior; copy only what actual consumers need, not a framework.
5. Adapt the [contract tests](assets/test_typed_decorators.py.template) to real
   consumers. Test order, failures, metadata, actual calls, and method binding;
   verify types with the project's checker.

Do not decorate generators with wrappers that close their scope before
iteration. Do not add retries, caching, authorization, or duplicate logging
under the guise of a behavior-preserving cleanup.
