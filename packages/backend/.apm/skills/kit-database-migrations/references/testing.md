# Testing migrations

An upgrade against an empty database proves only that the DDL parses. A useful
migration test suite proves that the history is linear, that every revision
upgrades and downgrades, that models match the schema, and that data survives
conversion.

## Test layers

| Test | What it proves | How |
| --- | --- | --- |
| Single head | No unmerged branches | `ScriptDirectory.get_heads()` has length 1 |
| Upgrade to head | Every revision applies in order | `command.upgrade(config, "head")` on a fresh database |
| Stairway | Each revision upgrades, downgrades, and upgrades again | Loop over revisions from base to head |
| Model drift | Models and migrations agree | `command.check(config)` or `compare_metadata` |
| Data conversion | Representative rows convert correctly | Seed at revision N-1, upgrade to N, assert rows |
| Static safety | No unreviewed risky operations | [check_migration_safety.py](../assets/check_migration_safety.py) |
| Lock and duration | Real-volume timing | Staging rehearsal on a production-sized snapshot |

The [migration test template](../assets/test_migrations.py.template) implements
the first five layers with pytest.

## Use the production engine

Run migration tests against the same database engine and major version as
production, typically in a disposable container. SQLite accepts DDL that
PostgreSQL rejects and vice versa; type, default, and constraint behavior differ.

## The stairway test

For each revision in order: upgrade to it, downgrade one step, upgrade again.
This catches downgrades that leave objects behind, upgrades that are not
re-runnable after a downgrade, and forgotten `drop_index` calls. Skip revisions
documented as forward-only by catching their explicit error.

## Data conversion tests

1. Upgrade to the revision before the one under test.
2. Insert rows with lightweight `sa.table()` constructs, covering nulls, empty
   values, boundaries, and invalid legacy data.
3. Upgrade one revision.
4. Assert converted values and that no rows were lost.

## Rehearsal before production

- Restore a recent production-sized snapshot into staging (masked if it contains
  personal data).
- Apply the migration with the production pipeline and timeouts.
- Record duration, lock waits, replica lag, and table/index growth.
- Run the previous application version against the migrated schema to prove
  backward compatibility.

## CI integration

- Run static safety and single-head checks on every pull request that touches
  `versions/`.
- Run upgrade, stairway, and drift tests against a containerized database on
  every pull request.
- Run rehearsal before releases that include contract or data migrations.

## Sources

- <https://alembic.sqlalchemy.org/en/latest/api/commands.html>
- <https://alembic.sqlalchemy.org/en/latest/api/script.html>
- <https://alembic.sqlalchemy.org/en/latest/api/autogenerate.html>
- <https://docs.pytest.org/en/stable/how-to/fixtures.html>
