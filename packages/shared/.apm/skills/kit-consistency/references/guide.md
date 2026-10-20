# Compare contracts, not matching words

## Trace one concept

Find its definition, validators, serializers, persistence, client consumers,
examples and generated derivatives. Write down casing, units, timezone,
nullability, allowed values, defaults, error meaning and version ownership.
Two fields with the same spelling may represent different concepts; do not
merge them without evidence.

For a naming change, search string-based dispatch and configuration as well as
symbol references. For a persisted value or public field, define compatibility
and migration rather than mass-renaming bytes.

## Quality gates

- The canonical owner is unique and generated derivatives are reproducible.
- One boundary test demonstrates the same meaning on both sides.
- Missing/null/empty and unknown enumeration cases have deliberate outcomes.
- Unit conversions and timezone normalization have explicit tests.
- Documentation examples match the accepted wire shape and error behavior.

## Failure and recovery

A matching-name lint cannot prove semantic consistency. Do not introduce a
global registry for unrelated domain concepts. If consumers cannot migrate
atomically, keep an explicit versioned adapter and a removal condition.
Retain intentional differences in the matrix instead of hiding them behind
silent defaults. Restore the prior wire contract if rollout validation fails.

## Deeper references

- [Naming conventions across files, classes, modules and tests](naming-conventions.md)
- [Module layout, one-class-per-module rules and private exports](module-layout.md)
- [Contract matrices](contract-matrices.md)

## Sources

- JSON Schema, [Understanding JSON Schema reference](https://json-schema.org/understanding-json-schema/reference)
