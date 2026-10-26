# Naming rules

These rules are enforced by `check_registry.py` (value patterns, reserved
names) and the registry schema (name patterns). Adjust a pattern only in the
checker's `KIND_PATTERNS` and record the reason in review.

## Names

| Element | Pattern | Example | Reason |
| --- | --- | --- | --- |
| Group | `PascalCase`, `^[A-Z][A-Za-z0-9]*$` | `OrderStatus` | Valid class and type name in both languages |
| Entry | `UPPER_SNAKE_CASE`, `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$` | `ORDER_NOT_FOUND` | Constant convention in both languages |
| Reserved groups | `StrEnum`, `Final`, `True`, `False`, `None` | | Would shadow imports or keywords in the generated module |

Name groups by meaning (`OrderStatus`, `PaymentErrorCode`), not by kind alone,
once more than one group of a kind exists.

## Values by kind

| Kind | Pattern | Examples | Uniqueness |
| --- | --- | --- | --- |
| `route` | `/` then lower-case kebab segments or `{snake_param}` | `/api/v1/orders/{order_id}` | Across all route groups |
| `query_key` | Dot-separated snake segments | `orders.list` | Across all query key groups |
| `event` | `entity.past_tense_verb`, at least two segments | `order.cancelled` | Across all event groups |
| `enum` | `snake_case` | `pending`, `partially_paid` | Within the group |
| `error_code` | `snake_case` | `order_not_found` | Across all error code groups |
| `field` | `snake_case` wire name | `created_at` | Within the group |

- Wire values are canonical. If a client uses camelCase internally, map at
  the transport boundary; do not register both spellings.
- Events use past tense because they record something that happened; commands
  belong in route or job names.
- Error codes describe the condition (`order_already_paid`), not the HTTP
  status or the user message.
- Route parameters use `{snake_case}` so both server routers and client path
  builders can substitute them.

## Text fields

- `description` and `reason`: one line, at most 160 characters, no double
  quotes, backslashes, control characters, or `*/`. They appear in generated
  comments and docstrings.

## Anti-patterns

| Anti-pattern | Problem | Instead |
| --- | --- | --- |
| Reusing a value with new meaning | Old clients and stored data misinterpret it | New entry, deprecate old |
| Abbreviations (`ORD_NF`) | Hard to search, ambiguous | Full words |
| Encoding version in values (`order.created.v2`) without policy | Silent forks | Version the event schema in the contract |
| Generic groups (`Constants`) | Unclear ownership and kind | One group per concept and kind |
| Display text as enum values | Translations change values | Stable code values, translated labels |

## Primary sources

- Python identifiers and keywords: <https://docs.python.org/3/reference/lexical_analysis.html#identifiers>
- PEP 8 naming conventions: <https://peps.python.org/pep-0008/#naming-conventions>
- TypeScript enums and const objects: <https://www.typescriptlang.org/docs/handbook/enums.html#objects-vs-enums>
- RFC 3986, URI path segments: <https://www.rfc-editor.org/rfc/rfc3986#section-3.3>
- CloudEvents type attribute naming: <https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md#type>
- RFC 9457, problem type identifiers: <https://www.rfc-editor.org/rfc/rfc9457#section-3.1.1>
