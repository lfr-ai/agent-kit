# Backwards-compatibility rules

A change is compatible when every existing, correctly written client keeps
working without modification. Judge compatibility from the wire contract and
real consumers, not from internal Python types.

## Breaking changes

Requests:

- Removing or renaming a path, method, or operation.
- Adding a required parameter, header, or request body property.
- Making an optional parameter or property required.
- Narrowing accepted values: removing an enum value, lowering a maximum,
  raising a minimum, shortening `maxLength`, adding a `pattern`.
- Changing a parameter's location, name, type, or format.
- Adding or tightening authentication or authorization requirements.
- Starting to reject unknown fields that were previously ignored.

Responses:

- Removing a property, or making a required property optional or nullable.
- Changing a property's type, format, units, or meaning.
- Removing a documented status code or changing success status (200 to 201).
- Changing the error envelope or problem `type` URIs.
- Adding an enum value when clients were not told to tolerate unknown values.
- Changing pagination defaults, sort order, or cursor format.

Behavior:

- Changing idempotency, side effects, or rate limits in a way clients observe.
- Changing default values.

## Compatible changes

- Adding a new path, method, or optional parameter.
- Adding an optional request property.
- Adding a response property (clients must ignore unknown fields).
- Widening accepted input (adding a request enum value, relaxing a limit).
- Adding a new error status for a new condition, documented with the shared
  problem schema, when clients handle unknown statuses generically.
- Marking an element deprecated.

## Tolerant reader expectations

Document the rules clients must follow: ignore unknown response fields, treat
unknown enum values as a generic case, follow pagination cursors, and branch on
problem `type` rather than message text. Compatibility claims depend on
clients following them.

## Decision procedure

1. Produce the old and new descriptions from their owners.
2. Run the compatibility diff and list every reported difference.
3. Classify each difference with the lists above and record it in the
   [contract review](../assets/contract-review.md.template).
4. For each breaking change, choose: make it additive instead, version it, or
   accept it with consumer sign-off and a migration window.
5. Add or update provider contract tests for every changed operation.

## Sources

- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [Google AIP-180 - Backwards compatibility](https://google.aip.dev/180)
- [Martin Fowler: Tolerant Reader](https://martinfowler.com/bliki/TolerantReader.html)
- [Microsoft REST API guidelines](https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md)
