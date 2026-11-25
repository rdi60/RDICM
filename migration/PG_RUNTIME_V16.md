# Version 1.6 – PostgreSQL runtime read-only probe

## Scope and actual state

The application still uses SQLite for authentication and all clinical/financial operations.
This version adds a **disabled-by-default, administrator-only, read-only PostgreSQL
runtime canary endpoint** (`GET /api/entities/{entity_id}/postgres-readiness`). It
is **not** a PostgreSQL application port. Never connect it to the `rajan_stage`
schema, which is an untrusted staging area without complete production constraints.

The canary uses `RAJAN_PG_DSN` (psycopg 3), optionally `RAJAN_RUNTIME_SCHEMA`
(default `rajan_runtime`), and is enabled with `RAJAN_ENABLE_PG_PROBE=1`.
It requires an authorized entity membership from the existing SQLite session.
The PostgreSQL role must not be superuser or have BYPASSRLS; the transaction is
READ ONLY and sets transaction-local `app.entity_id`.

## Prerequisites before enabling

1. Create an independently reviewed `rajan_runtime` schema on a disposable
   PostgreSQL 16+ instance with synthetic patient data only. Do NOT simply rename
   `rajan_stage`: the staging schema omits important production defaults, triggers,
   indexes, data types, audit constraints and RLS.
2. Install and validate a single `scoped_entity` ALL policy on each of five
   canary tables (patients, appointments, visits, invoices and receipts), with
   `ENABLE ROW LEVEL SECURITY` AND `FORCE ROW LEVEL SECURITY` applied.
3. Create a least-privilege read-only PostgreSQL application role, grant only
   the required tables, and validate that SQL GRANT permissions and RLS are
   both enforcing isolation. Do not use an admin, schema owner or BYPASSRLS role.
4. Use a TLS-protected PostgreSQL connection string and secret management.
   Do not store credentials in git or browser/client bundles.
5. Run live tests proving an entity-1 query cannot read entity-2 records,
   including under connection reuse, incorrect/missing context, and
   concurrent requests. Check the whole application, not just these five tables.
6. Only then enable the probe temporarily for an authorized administrator.

## Canary output

Returns **aggregate counts only** for five entity-scoped tables. It rejects
missing or altered RLS configuration and untrusted schema names. The canary's
policy text verification is only a preliminary guard and is not formal evidence
of RLS safety. No actual data migration or backend switch occurs.

## Remaining full PostgreSQL runtime integration

- Rewrite the application's SQLite-specific SQL, transactions, auto-increment,
  PRAGMAs and row conversion for PostgreSQL; use proper migrations.
- Audit every table and foreign key for entity and patient ownership.
- Migrate sessions and membership authorization to PostgreSQL, not just records.
- Add concurrency tests for check-in/UHID, appointment conflicts, estimate
  conversion, credit notes and receipt allocation.
- Test backup/restore, failure rollback, encrypted file storage and independent
  security review before any real patient data or production cutover.
