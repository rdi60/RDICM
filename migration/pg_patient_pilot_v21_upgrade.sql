-- v2.1: Apply once to a dedicated synthetic PostgreSQL pilot with the v2.0 schema.
-- No posted production financial records should exist in this pilot.
-- In a populated staging pilot, an explicit data-backfill review is required.
BEGIN;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM rajan_pilot.receipts LIMIT 1) THEN
  RAISE EXCEPTION 'v2.1 schema upgrade requires empty pilot receipts; export/review data before upgrade';
 END IF;
END $$;
ALTER TABLE rajan_pilot.receipts
 ADD COLUMN idempotency_key TEXT NOT NULL CHECK(length(idempotency_key) BETWEEN 8 AND 100),
 ADD COLUMN request_hash CHAR(64) NOT NULL,
 ADD CONSTRAINT receipts_entity_idempotency_unique UNIQUE(entity_id,idempotency_key);
COMMIT;
