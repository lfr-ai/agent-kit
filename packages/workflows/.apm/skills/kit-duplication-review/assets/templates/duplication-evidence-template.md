# Duplication evidence worksheet

## Scan

- Scope scanned: `<paths>`
- Exclusions: `<globs and reasons>`
- Tool and version: `jscpd <version>`
- Configuration: `<path to .jscpd.json or inline flags>`
- Command: `<command>`
- Summary command: `python assets/summarize_jscpd_report.py <report> --min-lines <n>`

## Before

- Clone pairs reported: `<n>`
- Total duplication: `<percentage>`

## Decisions

One row per clone pair at or above the agreed size.

| First | Second | Knowledge encoded | Deciding question | Decision | Owner |
| --- | --- | --- | --- | --- | --- |
| `<path:start-end>` | `<path:start-end>` | `<rule or fact>` | same reason to change / owner / contract mirror / rule of three / test code | extract / generate / parameterize / keep / defer | `<handle>` |

## Changes made

- Pattern used per extracted pair: `<extract function, parameterize, generate, fixture, module>`
- New shared code location and owner: `<path, handle>`
- Suppressions added with reasons: `<path, reason>`

## Verification

- Tests pinning former copies: `<test ids>`
- Test command and result: `<command>` - `<result>`
- Import cycle check after extraction: `<command>` - `<result>`

## After (identical configuration)

- Clone pairs reported: `<n>`
- Total duplication: `<percentage>`

## Follow-ups

- Deferred pairs with owner and revisit trigger: `<list>`
