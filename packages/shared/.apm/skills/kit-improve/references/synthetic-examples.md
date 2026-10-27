# Synthetic examples

The kit is shared source. A report that proves a defect must not carry anything
from the project where it was found.

## Rewrite, do not redact

Redacting a real snippet leaves structure that still identifies its owner.
Write a new minimal example that triggers the same behavior.

| Found in the project | Replace with |
| --- | --- |
| Company, product, team or person names | Neutral words such as `Acme`, `service-a`, `user` |
| Internal hosts, URLs, tenant or subscription IDs | `example.com`, `00000000-0000-0000-0000-000000000000` |
| Absolute or user-specific paths | Relative paths in a throwaway project |
| Domain terms and table or field names | Generic names with the same shape |
| Real data, tokens, keys, connection strings | Obvious fakes; never a real value with a few characters changed |
| Long transcripts | The one prompt and the one response that show the defect |

## Minimal reproduction

1. Start from the smallest project that triggers the behavior.
2. Write the prompt exactly as given, then the observed response summary.
3. State the expected behavior in one sentence a reviewer can check.
4. Remove everything that is not needed to see the difference.

## Check before sharing

- Search the text for company words, host names, emails, paths and UUIDs.
- Confirm the example runs or reads correctly without this project.
- Ask the user to read it once; they own what leaves their project.
- If the defect cannot be shown without private material, describe the
  behavior in words and say so; do not attach the material.
