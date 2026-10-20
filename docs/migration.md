# Adoption and rollback

## Adopt

1. Record existing repo/user/plugin capabilities, owners, and name conflicts.
2. Select a profile and optional features; compose into a new directory.
3. Check provenance before any installation refreshes output hashes.
4. Run pinned APM installation and compilation in that package, not the toolkit
   monorepo root.
5. Audit with an explicit policy path and inspect generated files.
6. Verify native discovery and behavior for each supported consumer surface.
7. Transfer ownership only after comparison; remove old copies deliberately.

Never overwrite an existing consumer. A composition directory is a candidate
delivery artifact, not an automatic migration.

New compositions keep skill source/delivery trees out of APM's application
placement scan while installing all selected skills normally. If an older compile
inserted AGENTS context inside skill assets, audit and preserve that evidence,
then compose a fresh candidate from trusted source. Do not hand-edit the manifest
or refresh hashes to legitimize unowned resource files.

## Drift ordering

For existing APM output, run provenance and explicit APM audit **before**
installation or regeneration. Reproduce frozen installation in a disposable copy.
A regeneration-first job can erase evidence of modified owned output.

## Updates

- Fix portable guidance once in the canonical source.
- Consumers adopt an immutable reviewed release through an update review.
- Keep project facts, application tests, private knowledge, and memory local.
- Do not auto-update every project to a moving branch.
- Preserve previous source, package, lock, and settings for rollback.

## Before publication

Operators choose the remote owner, initialize version control, set protected
required CI checks, verify legal ownership, and publish a release.
There is no claimed hosted package coordinate until that is done.
Copier integration is intentionally outside this implementation.
