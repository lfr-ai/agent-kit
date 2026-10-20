# Property-based testing with Hypothesis

An example test checks one input. A property test states a rule for *all*
inputs in a space and lets Hypothesis search for a counterexample, then shrink
it to the smallest failing input. Use both: examples document intent, properties
find the cases nobody thought of.

## Properties that pay off

| Pattern | Statement | Example |
| --- | --- | --- |
| Round trip | decode(encode(x)) == x | storage mapping `_from_row(_to_row(invoice)) == invoice` |
| Invariant | a rule holds after any valid operation | a paid invoice always has a reference |
| Rejection | every input in an invalid region is refused | every non-positive amount raises |
| Idempotence | f(f(x)) == f(x) | normalizing an address twice |
| Oracle / model | fast simple model agrees with the real thing | in-memory dict vs repository |
| Metamorphic | changing input in a known way changes output in a known way | adding an invoice never shrinks `list_open` |
| Bounds | results stay inside limits | `len(list_open(limit=n)) <= n` |

[`test_property.py.template`](../assets/test_property.py.template) implements
several of these, plus a stateful model comparison.

## Writing strategies

- Start from the real input domain, not the type: an invoice amount is a
  positive decimal with two places, not any `Decimal`.
  `st.decimals(min_value=..., max_value=..., places=2, allow_nan=False, allow_infinity=False)`.
- Build objects through their constructors with `st.builds(Invoice, ...)` so
  invariants run on every example.
- Use `@st.composite` when one drawn value constrains another (an invoice in a
  later state is derived from an open one).
- Prefer constructing valid data over filtering. `assume()` and `.filter()`
  discard examples; heavy filtering triggers a health-check failure and wastes
  the example budget.
- Keep alphabets and sizes realistic (`st.text(alphabet=..., max_size=16)`);
  unbounded text and lists slow tests without finding more bugs.
- Use `st.sampled_from` for closed sets (currencies, enum members) and
  `st.from_type` only when the type's full range is truly valid.

## Pin known cases

Add `@example(...)` for regressions and boundaries you always want checked
(zero, empty, maximum). Hypothesis also stores failing examples in its local
database and replays them first; in CI set `print_blob=True` so a failure can be
reproduced with `@reproduce_failure` locally.

## Profiles and determinism

Register profiles once in `conftest.py` and select with an environment
variable ([`conftest.py.template`](../assets/conftest.py.template)):

```python
settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", max_examples=300, derandomize=True, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
```

`derandomize=True` makes CI runs repeatable; nightly or scheduled runs can use
a randomized profile with more examples to keep exploring.

## Stateful testing

`RuleBasedStateMachine` generates *sequences* of operations. Define rules
(add, pay, abandon a transaction) and invariants (store equals model), and
Hypothesis finds the shortest sequence that breaks them. Use `Bundle` and
`consumes` to pass generated identifiers between rules. This is the most
effective way to test repositories, caches and anything with a lifecycle.

## When a property fails

1. Read the shrunk example; it is usually the clearest bug report you will get.
2. Decide whether the code or the property is wrong. A property that encodes a
   wrong assumption should be narrowed deliberately, with an `@example` of the
   case that taught you.
3. Add the shrunk input as an `@example` or an ordinary unit test so the
   regression is permanent even if strategies change.

## Health checks and deadlines

Health checks flag slow data generation, excessive filtering and large base
examples. Fix the strategy rather than suppressing the check; suppress a
specific check only with a comment explaining why. Hypothesis' per-example
deadline guards against accidental slowness; raise it for a test that is
legitimately slow instead of disabling it everywhere.

## Sources

- Hypothesis, [documentation](https://hypothesis.readthedocs.io/en/latest/)
- Hypothesis, [Strategies reference](https://hypothesis.readthedocs.io/en/latest/reference/strategies.html)
- Hypothesis, [Configuring test settings](https://hypothesis.readthedocs.io/en/latest/tutorial/settings.html)
- Hypothesis, [Replaying failed tests](https://hypothesis.readthedocs.io/en/latest/tutorial/replaying-failures.html)
- Hypothesis, [Stateful tests](https://hypothesis.readthedocs.io/en/latest/stateful.html)
