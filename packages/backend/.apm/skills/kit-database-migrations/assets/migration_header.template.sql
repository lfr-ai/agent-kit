-- Raw SQL migration header for teams that apply reviewed SQL files directly.
-- Alembic users should prefer alembic_revision.py.template instead.
--
-- id: 20260115_add_customer_note_to_orders
-- description: add nullable customer_note to orders (expand phase)
-- phase: expand
-- rollback: reversible (drop the new column)
-- point_of_no_return: none
-- backup: confirmed for destructive phases only
-- measured_duration: < 1 s on production-sized snapshot

SET lock_timeout = '3s';
SET statement_timeout = '60s';

BEGIN;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_note TEXT NULL;
COMMIT;

-- Concurrent index builds must run outside a transaction block.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_customer_note_present
    ON orders (id) WHERE customer_note IS NOT NULL;
