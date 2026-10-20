# Signature design

A signature is the cheapest documentation a caller reads. Design it so that a
call site is unambiguous without opening the implementation.

## Rules

1. Annotate every parameter and the return type, including `-> None`.
2. Accept the narrowest abstract input that the body needs and return the most
   concrete type the caller can use: take `Iterable[Order]` or
   `Sequence[Order]`, return `list[Order]` or a frozen record.
3. Put options after a bare `*` so they must be passed by name. Callers then
   write `export(report, include_drafts=True)` instead of `export(report, True)`.
4. Use positional-only parameters (`/`) for one obvious subject whose name is an
   implementation detail, such as `normalize(text, /)`. Renaming it later is
   then not a breaking change.
5. Never accept a positional `bool` (the "boolean trap"). Prefer, in order:
   - two clearly named functions (`publish()` and `publish_draft()`),
   - a keyword-only flag with a default,
   - a `StrEnum` when a third state is plausible (`mode=ExportMode.FULL`).
6. Keep the positional parameter count small. Three positional parameters is a
   practical ceiling; beyond that, group related values in a frozen dataclass.
7. Do not use mutable defaults. Use `None` plus an explicit branch, or
   `dataclasses.field(default_factory=...)` in records.
8. Represent "absent" with `X | None` only when absence is a real state. Never
   use `""`, `0`, or `-1` as sentinel values.
9. Units belong in the name or the type: `timeout_seconds: float`,
   `amount: Money`, never a bare `timeout: int`.
10. Return one shape. A function that returns `Order | list[Order] | None`
    depending on input pushes branching into every caller.

## Bool trap examples

Avoid:

```python
def archive(document: Document, force: bool) -> None: ...


archive(document, True)  # What does True mean at this call site?
```

Prefer:

```python
def archive(document: Document, *, force: bool = False) -> None: ...


archive(document, force=True)
```

or, when the flag selects between two behaviors with different contracts:

```python
class ArchiveMode(StrEnum):
    SOFT = "soft"
    HARD = "hard"


def archive(document: Document, *, mode: ArchiveMode = ArchiveMode.SOFT) -> None: ...
```

## Constructor signatures

- Services receive collaborators through `__init__`, keyword-only, typed against
  a `Protocol` port rather than a concrete adapter.
- Do not construct collaborators inside `__init__`; the composition root does it.
- Document each initializer argument in an `Args:` section.

```python
class InvoiceService:
    """Issue invoices for confirmed orders."""

    def __init__(self, *, repository: InvoiceRepository, clock: Clock) -> None:
        """Bind the service to its ports.

        Args:
            repository: Port that persists issued invoices.
            clock: Source of the issue timestamp; injected for deterministic tests.
        """
        self._repository = repository
        self._clock = clock
```

## Named constructors

Use `@classmethod` factories when there is more than one way to build a value,
for example `Money.from_minor_units(...)` and `Money.parse("12.50 EUR")`. Keep
`__init__` (or the dataclass fields) as the single canonical form so that
validation lives in one place.

## Variadic parameters

- `*args` and `**kwargs` hide the contract from type checkers and readers. Use
  them only for true forwarding wrappers, and type them with `ParamSpec`.
- Never use `**kwargs: object` to accept "options"; declare the options.

## Overloads

Use `typing.overload` only when the return type genuinely depends on an
argument's type. If the overloads differ in behavior, write two functions.

## Review checklist

- [ ] Every parameter and return is annotated; no `Any` or `cast`.
- [ ] No positional `bool`; options are keyword-only.
- [ ] No mutable default; no sentinel primitives.
- [ ] Units are explicit; return type is a single shape.
- [ ] Injected collaborators are typed as ports and documented.

## Sources

- [PEP 3102 - Keyword-only arguments](https://peps.python.org/pep-3102/)
- [PEP 570 - Positional-only parameters](https://peps.python.org/pep-0570/)
- [PEP 484 - Type hints](https://peps.python.org/pep-0484/)
- [PEP 612 - Parameter specification variables](https://peps.python.org/pep-0612/)
- [Python tutorial: special parameters](https://docs.python.org/3/tutorial/controlflow.html#special-parameters)
- [typing.overload](https://docs.python.org/3/library/typing.html#typing.overload)
- [Ruff FBT rules](https://docs.astral.sh/ruff/rules/#flake8-boolean-trap-fbt)
