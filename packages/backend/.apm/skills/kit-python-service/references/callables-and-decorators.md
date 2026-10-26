# Functions, partials, decorators and callable contracts

Choose the smallest callable form that makes inputs, dependencies and effects
obvious. Do not turn every callback into a class or every repeated line into a
decorator. Preserve the project's signature, typing, error and logging rules.

## Choose deliberately

| Need | Prefer | Review |
| --- | --- | --- |
| One operation with no argument adaptation | A plain named function | Is a wrapper doing anything useful? |
| Bind known arguments for a callback | `functools.partial` | Can the remaining signature and captured lifetime be understood? |
| Validate or translate inputs at a boundary | A small, explicitly typed named wrapper | Are policy and errors visible rather than hidden in binding? |
| Capture a small amount of per-instance context | A closure when its lifetime is clear | Late binding, retained mutable state and test isolation |
| Expose a meaningful stateful collaborator | A callable object or port with explicit dependencies | Is the extra object justified by real behavior? |
| Apply one stable cross-cutting behavior to several functions | A documented decorator | Order, metadata, invocation kind and side effects |
| Pre-bind a method at class definition | `functools.partialmethod` when needed | Descriptor binding; a plain `partial` is not a normal method |

## Partial application is binding, not enforcement

- `partial(function, option=value)` supplies arguments; later positional
  arguments are appended and later keyword arguments override bound keywords.
  Do not treat a bound keyword as an authorization, validation or configuration
  lock. Enforce an invariant explicitly where it belongs.
- Some argument errors appear only when the partial is called. Test the actual
  call shape, including positional-only and keyword-only parameters.
- Bound objects remain references, not deep copies. Mutable inputs can change,
  and bound clients/resources remain alive while referenced. Bind dependencies
  at the composition boundary with the correct lifecycle; do not create clients
  or read secrets at import time.
- Bind only intentional choices. Repeating every callee default hides the real
  configuration difference and pins old defaults unnecessarily.
- Prefer a named wrapper when transformation, error mapping, documentation or
  debugging would otherwise require explaining a chain of partials.
- A partial does not automatically acquire the original function's `__name__`
  or documentation. Do not rely on it being an ordinary function for handler
  registration, tracing or serialization. Avoid logging captured arguments or
  keyword dictionaries that may contain sensitive values.
- `inspect.signature` supports partials, but framework discovery and static
  typing still need their own checks. If the checker cannot prove the required
  callable shape, use a small typed wrapper rather than `Any` or a cast.
- Use `partialmethod` for descriptor-based method adaptation; test the bound
  instance/class behavior rather than assuming an ordinary partial inserts
  `self`.
- Python 3.14 adds `functools.Placeholder`. Do not use it in code required to
  run on the toolkit's Python 3.13 baseline. Interpreter support is a project
  compatibility decision, not a reason to copy the newest documentation blindly.

## Decorators must expose their real contract

For transparent function wrappers, use `functools.wraps` and preserve parameter
types with `ParamSpec` and the result type. The
[typed synchronous example](python-idioms.md#functions-and-decorators) is the
canonical example; do not maintain a second divergent copy.

`wraps`/`update_wrapper` copy metadata and add `__wrapped__`; they do not validate
arguments, make blocking code asynchronous or prove that behavior is preserved.
Do not add a wrapper or call `update_wrapper` merely to make introspection
appear correct. If the public signature intentionally changes, declare and type
the new interface and test its actual consumers.

Evaluate:

1. **Purpose and placement.** Keep domain rules and dependency construction
   explicit. Prefer framework-supported route/CLI decorators where appropriate;
   avoid custom registration machinery without a real need. Registration and
   decorator factories execute at definition time, often during import, so do
   not hide network access, configuration reads or resource acquisition there.
2. **Order.** `@outer` above `@inner` constructs `outer(inner(function))`.
   Test security checks, validation, caching, retries and transaction boundaries
   in the intended order. A cache or retry must not bypass authorization or
   repeat a non-idempotent effect accidentally.
3. **Invocation kind.** Preserve ordinary, coroutine, generator and async
   generator behavior where promised. Test `await`, iteration, cancellation,
   close/cleanup and failure propagation as applicable. A synchronous wrapper
   returning a coroutine may work when awaited but differ under framework
   discovery. Metadata alone cannot repair that mismatch.
4. **Results and errors.** Preserve return shape, exception types and required
   side-effect ordering. Do not swallow failures, fabricate defaults or add
   duplicate logs at multiple layers.
5. **Typing and inspection.** Preserve the callable signature without `Any` or
   casts. Inspect the public signature and `__wrapped__` chain where a framework
   relies on them; also invoke the callable. `inspect.signature` follows wrapped
   callables by default, which can conceal a wrapper's actual implementation
   signature. Introspection is not behavioral or permission enforcement.
6. **State and performance.** Add caching or instrumentation only for a measured
   need. Review cardinality, lifetime, invalidation, tenant boundaries and
   sensitive data. `lru_cache` keeps its data coherent across threads but can
   compute the same concurrent miss more than once; it is not single-flight.
   Do not use a synchronous cache decorator to cache coroutine or generator
   objects. Choose and test an appropriate value cache when the use case needs it.

## Verification and alignment

- Check binding, defaults and intended overrides at real call sites.
- Preserve documented public names, signatures, types and error behavior, or
  provide an approved migration. Keep one owned implementation of shared policy.
- Test observable behavior through the actual framework or port when decorators
  affect handler discovery, schemas, DI, serialization or registration.
- Cover ordinary and negative calls, wrapper order and applicable async/lifecycle
  cases; do not substitute a signature-name comparison for these tests.
- Run the project's naming, typing, import and convention gates. AST-only
  port/adapter checkers cannot infer arbitrary runtime decorator transformations.
- Leave a simpler plain function in place when the abstraction has no measurable
  maintenance, reuse or boundary benefit.

## Primary sources

- [Python 3.13 partial and partialmethod](https://docs.python.org/3.13/library/functools.html#functools.partial)
- [Python 3.13 update_wrapper and wraps](https://docs.python.org/3.13/library/functools.html#functools.update_wrapper)
- [Python 3.13 cache semantics](https://docs.python.org/3.13/library/functools.html#functools.lru_cache)
- [Python 3.14 Placeholder](https://docs.python.org/3.14/library/functools.html#functools.Placeholder)
- [Signature inspection](https://docs.python.org/3.13/library/inspect.html#inspect.signature)
- [PEP 612: parameter specification variables](https://peps.python.org/pep-0612/)
- [PEP 695: type parameter syntax](https://peps.python.org/pep-0695/)
