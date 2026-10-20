# Gate contract

## Owned output

- Source validation checks metadata, policy, links, and profile selection.
- Provenance checks all selected source bytes, manifest, and policy.
- APM audit checks the native entries APM owns.
- Native adapters need their own schema and behavior checks.

## Ordering

1. Validate source and existing owned output.
2. Run the explicit policy audit.
3. Reproduce installation in a separate disposable copy.
4. Compare outputs and run native smoke tests.

Regenerating the checkout first can destroy evidence of drift.
Missing locked dependencies or unsupported mandatory metadata must not become a pass.
