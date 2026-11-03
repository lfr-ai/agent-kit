# Decorator review

Reviewed against Python 3.13 documentation. Start with two real consumers and
one stable policy; no decorator is needed just because a function can be wrapped.

## Transparent does not mean merely copied metadata

- Use `functools.wraps` on function wrappers. It copies metadata and exposes
  `__wrapped__`; it does not validate inputs or preserve execution semantics.
- Forward `*args: P.args` and `**kwargs: P.kwargs` with `ParamSpec`, preserving
  the result type. A wrapper accepting `Callable[..., object]` has erased the
  parameter contract even if an overload advertises a precise public type.
- A coroutine wrapper needs `async def` and must await within the policy scope.
  A sync function returning an awaitable is not necessarily a coroutine function.
- Generator scopes must remain active during iteration, with close and cleanup
  behavior tested. Reject unsupported callable kinds rather than silently
  changing them.
- `@outer` above `@inner` means `outer(inner(function))`; construction can run
  during import. Never hide I/O, secret reads, or client creation there.
- Test instance/class descriptor binding where applicable. Metadata cannot
  repair an incorrectly bound method.

## Effects belong in an explicit owner

Do not centralize unrelated policies just because they share wrapper syntax.
Translate errors only at the responsible adapter boundary and preserve
`__cause__`. Log once without arguments, results, or captured secrets. Retries
and caching change behavior; introduce them only as explicit features with
idempotency, invalidation, cancellation, and deadline contracts.

The [policy template](../assets/typed_decorators.py.template) and its
[test template](../assets/test_typed_decorators.py.template) are examples, not
mandatory infrastructure. Review copied code with the consumer's lint and
type gates and remove unused policies.

## Verification

Compare calls before and after, not only `inspect.signature`: positional-only
and keyword-only arguments, returns, exception identity/chaining, side-effect
order, `__name__`, `__doc__`, `__wrapped__`, coroutine detection, cancellation,
and bound methods. Check static argument rejection and inferred result types
with the supported type checker; runtime `assert_type` alone proves nothing.

## Primary sources

- [Python 3.13: functools.wraps](https://docs.python.org/3.13/library/functools.html#functools.wraps)
- [Python 3.13: update_wrapper](https://docs.python.org/3.13/library/functools.html#functools.update_wrapper)
- [Python 3.13: ParamSpec](https://docs.python.org/3.13/library/typing.html#typing.ParamSpec)
- [PEP 612: parameter specification variables](https://peps.python.org/pep-0612/)
- [Python 3.13: function definitions and decorator order](https://docs.python.org/3.13/reference/compound_stmts.html#function-definitions)
- [Python 3.13: inspect.signature](https://docs.python.org/3.13/library/inspect.html#inspect.signature)
