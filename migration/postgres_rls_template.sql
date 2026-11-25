-- POSTGRESQL DESIGN TEMPLATE ONLY — DO NOT RUN AGAINST PRODUCTION UNREVIEWED.
-- Requires migrated PostgreSQL tables, least-privilege non-BYPASSRLS app role,
-- and explicit trusted per-transaction entity context established by the backend.
-- SET LOCAL app.entity_id = '123'; use only within a dedicated transaction.
-- A client must never be allowed to choose arbitrary entity context.
DO $plpgsql$
DECLARE t record;
BEGIN
 FOR t IN
  SELECT DISTINCT c.table_schema, c.table_name
  FROM information_schema.columns c
  JOIN information_schema.tables tb USING (table_schema,table_name)
  WHERE c.column_name='entity_id' AND c.table_schema='public' AND tb.table_type='BASE TABLE'
 LOOP
  EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',t.table_schema,t.table_name);
  EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',t.table_schema,t.table_name);
  EXECUTE format('DROP POLICY IF EXISTS scoped_entity ON %I.%I',t.table_schema,t.table_name);
  EXECUTE format($fmt$CREATE POLICY scoped_entity ON %I.%I FOR ALL
    USING (entity_id = NULLIF(current_setting('app.entity_id',true),'')::bigint)
    WITH CHECK (entity_id = NULLIF(current_setting('app.entity_id',true),'')::bigint)$fmt$,t.table_schema,t.table_name);
 END LOOP;
END
$plpgsql$;
-- IMPORTANT: this is one isolation layer, not full role permission enforcement.
-- Tables without entity_id (users/sessions/global configuration) need distinct policies.
-- Set/RESET context on every transaction; never use pooled session variables.
-- Run leakage tests for every role and every table before granting access.
