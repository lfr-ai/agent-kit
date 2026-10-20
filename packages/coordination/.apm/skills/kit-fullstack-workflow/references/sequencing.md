# Sequencing across layers

Layers deploy at different times, so for a while old and new versions run side
by side. Order the work so every intermediate combination works, and so each
step can be undone without undoing the ones before it.

## Default order

1. **Contract** reviewed and merged (no runtime effect yet).
2. **Infrastructure prerequisites**: resources, configuration keys, secret
   references, permissions, network rules, feature switches defaulting off.
3. **Data expand**: additive schema changes (new nullable columns, new
   tables, new indexes built online). Old code ignores them.
4. **Backend accepts and produces the new shape** while still serving the old
   one. Writes go to both shapes if data moves (dual write) or the new shape
   is derived on read.
5. **Data migrate**: backfill existing rows in batches, idempotent and
   resumable, with progress observable.
6. **Frontend adopts the new shape**, behind a switch if behavior is visible.
7. **Enable** the switch progressively and watch the health signals.
8. **Contract**: remove the old shape from the frontend, then the backend,
   then the data, then the infrastructure, each as its own step after the
   compatibility window closes.

Skip steps that do not apply, but keep the order of those that do.

## Compatibility matrix

Check each pair that can exist during rollout:

| Frontend | Backend | Must work because |
| --- | --- | --- |
| old | old | Baseline |
| old | new | Backend deploys first; old clients keep working |
| new | new | Target state |
| new | old | Frontend deploys early, rollback of backend, or cached clients; required unless the frontend is gated by a switch that stays off until the backend is live |

Also consider stale clients: browser tabs, mobile apps and integrations that
upgrade on their own schedule. For them the old contract lives until the
deprecation window ends.

## Breaking changes with expand-migrate-contract

Example: renaming `customerName` to `billingName` on an order.

1. Expand: add `billingName` to the contract as optional in responses and
   accepted in requests; keep `customerName`, marked deprecated.
2. Backend writes both fields and reads `billingName` falling back to
   `customerName`.
3. Migrate existing data to fill `billingName`.
4. Frontend switches to `billingName`.
5. After the deprecation window and telemetry showing no reads of the old
   field, remove `customerName` from the frontend, backend, contract and
   data, in that order.

## Rollback rules

- Every forward step has a rollback written before it runs.
- Roll back in reverse order. Never restore a frontend that requires a field
  the restored backend no longer sends.
- Data migrations that destroy information (dropping a column, lossy
  conversions) happen only in the contract phase, after the window closes and
  a backup or export exists.
- Feature switches are the fastest rollback for visible behavior; keep them
  until the switch has been fully on for an agreed period, then remove them as
  a cleanup step.

## Parallel work

Once the contract is merged, backend, frontend and infrastructure work can
proceed in parallel against it. Integration points:

- Frontend uses contract-validated fixtures or a mock server generated from
  the specification until the backend slice is deployed to a shared
  environment.
- Backend contract tests run in its own pipeline; a contract change reopens
  step 1 for everyone.

Record the plan and each step's status in the
[rollout plan](../assets/rollout-plan.md.template).

## Sources

- [RFC 9745: The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745)
- [RFC 8594: The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594)
- [OpenAPI Specification 3.1: deprecated](https://spec.openapis.org/oas/v3.1.0#operation-object)
