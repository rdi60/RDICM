# PostgreSQL transition — NOT EXECUTED

The current `backend/app.py` continues to use `sqlite3`, SQLite-specific `?` placeholders, `INSERT OR ...` behaviors, `lastrowid`, PRAGMAs and a SQLite initialization script. Simply changing `DENTAL_DB` to a PostgreSQL URL **does not work**.

## Safe staged migration

1. Freeze writes and create a verified, restorable backup of the live/synthetic source.
2. Create a PostgreSQL 16+ environment, separate migration/admin role and non-superuser application role. Use private networking, TLS and encrypted backups.
3. Port the DDL to PostgreSQL using a reviewed migration tool (Alembic), replacing SQLite-only expressions and defining all composite `entity_id` foreign keys, constraints, unique sequences and indexes.
4. Use a reviewed ETL/import for patients, visits, clinical records, invoices, receipt allocations and uploaded files. Preserve IDs and enforce referential integrity; no patient data may cross legal entities.
5. Rewrite the backend persistence layer to use PostgreSQL transactions and a connection pool. Set a verified entity ID on every transaction before reading entity-scoped data. Review `postgres_rls_template.sql` as a starting point, not as a deployable one-click solution.
6. Run parity checks comparing row counts, per-entity totals, UHID uniqueness, financial balances, document hashes, appointment collisions, staff roles and clinical-note immutability.
7. Run all backend suites in a PostgreSQL-specific integration environment, including direct SQL negative tests for inter-entity leakage. Exercise backup restores, load tests, retries and concurrency.
8. Only then switch production, with a documented rollback and reconciliation plan.

## Blocking criteria

No live PostgreSQL service, DB credentials, PostgreSQL-native backend or migration test rig was available in this coding environment. The migration remains **NOT IMPLEMENTED** in this release. The RLS script is a design artifact and must not be presented as an enforced security control.


## Version 1.2: audited SQLite export (IMPLEMENTED; PostgreSQL import NOT IMPLEMENTED)

Create an offline SQLite snapshot with the development backup utility first. **Do not run this
against a live database while it is being written.** The `immutable=1` export reader
requires a fully checkpointed, consistent, read-only database file.

```bash
python migration/export_sqlite.py export /private/offline/database.sqlite3 /private/export-v12
python migration/export_sqlite.py verify /private/export-v12
```

- Every user table is exported as typed UTF-8 JSON Lines (NULLs and Unicode preserved).
- Manifest includes source database SHA-256, export file SHA-256, column names, table counts,
  per-entity counts and sums of selected financial fields.
- `PRAGMA integrity_check` and `PRAGMA foreign_key_check` are required to pass before export.
- Export files and folder are created with owner-only POSIX permissions (0600/0700).
- The verifier rejects missing/extra files, corrupted data, mismatched entity totals or totals.
- The manifest hashes are **not cryptographically signed** and are not a replacement for independent backup verification.
- Export **does not migrate user-uploaded documents**. Copy private media separately with
  integrity checks and verify document pointers and authorization before cutover.
- Do not send exports to ChatGPT, public storage or unencrypted email if they contain real patient data.

### Next gates for an actual migration

Implement a PostgreSQL DDL and adapter replacing SQLite `?` placeholders and `lastrowid`,
wire all transactions to PostgreSQL, import staged rows in foreign-key order, compare counts
and balances, enforce RLS using a non-bypass application role, then conduct restore and
cross-entity leakage tests against a running PostgreSQL 16+ instance. No PostgreSQL service
was available for such verification here.


## Version 1.3 — semantic integrity preflight

```bash
python migration/audit_integrity.py /private/offline/snapshot.sqlite3
```

Run on an offline SQLite snapshot. The audit checks relational patient consistency,
receipt allocation amounts, over-credited invoices, refund/reversal relationships,
and duplicate UHIDs. It prints only aggregate results; a nonzero result blocks the
migration review. It does **not** migrate data or repair anomalies. The SQLite
write-side triggers in `backend/app.py` prevent two important new allocation errors.


## Version 1.4 — PostgreSQL **staging importer** (implemented, live PG not verified)

The new `postgres_stage.py` prepares and imports a **verified, offline SQLite export** into
an isolated `rajan_stage` PostgreSQL schema. This is **NOT a port of the running app**.
It intentionally does not change `backend/app.py` or `DENTAL_DB`. It is useful for
reviewing column layouts, composite foreign keys and historical data parity before
rewriting the runtime persistence layer.

1. Create a **consistent offline** SQLite snapshot and run `audit_integrity.py`; resolve
   all reported problems before proceeding.
2. Export using `export_sqlite.py export SOURCE.sqlite PRIVATE_EXPORT` and verify it.
3. Generate the reviewable DDL without needing a running PostgreSQL instance:

   ```bash
   python migration/postgres_stage.py plan SOURCE.sqlite PRIVATE_EXPORT /private/staging.sql
   ```

4. On a **disposable, secured PostgreSQL 16+ instance** install `psycopg[binary]>=3.2,<4`
   and use an isolated migration role. Set `RAJAN_STAGE_DSN` through the environment,
   not a command argument or checked-in file. Then run:

   ```bash
   RAJAN_STAGE_DSN='postgresql://...' python migration/postgres_stage.py apply SOURCE.sqlite PRIVATE_EXPORT
   ```

   The importer refuses an existing `rajan_stage` schema, writes all tables in a single
   transaction, adds composite foreign keys, compares table counts, entity counts and
   financial totals, and revokes public access to the staging schema and tables.
   A failure rolls back the transaction. No automatic schema drop or overwrite occurs.

**Limitations / mandatory gates:** Schema is a **staging representation only**: SQLite
CHECK constraints, defaults, partial indexes, triggers, row-level security policies,
sequences/identity generation and application compatibility are NOT ported. Sensitive
patient/staff data must not be used without a private encrypted environment and
independent review. Uploaded patient documents are not imported. The PG driver and
PostgreSQL server are not available in this development environment, so **live staging
import, runtime cutover, and PG-backed regression tests have NOT been completed**.
The generated staging SQL is for review, not a production migration script. After
staging parity, implement and test an explicit PostgreSQL-native backend, including
entity isolation under a non-bypass role, financial write protections, concurrency
and full backup/restore tests.

## Version 1.5 — PostgreSQL staging semantic verification and scoped transaction scaffold

**Added** `postgres_validate.py`. This is a separate, **read-only staging verification**
command that checks a PostgreSQL staging import against the same verified SQLite
snapshot/export used to create it. It checks column layouts, total and per-entity
row counts, selected financial totals, and 12 cross-patient/financial semantic
relationship checks from the offline integrity audit. It prints only aggregate
results. A failed check exits nonzero. It does not grant production approval.

With the PostgreSQL 16+ server and `psycopg[binary]>=3.2,<4` installed:

```bash
# Use a private, least-privilege database connection; supply credentials via
# environment variables or a secure secret manager, never in source control.
RAJAN_STAGE_DSN='postgresql://...' python migration/postgres_validate.py \
   /private/offline/snapshot.sqlite3 /private/export-v12
```

The staging importer in `postgres_stage.py` also runs these semantic checks *in
its loading transaction*, before committing and revoking public access. A failing
check causes rollback.

`pg_scope.py` is a **future PostgreSQL API integration scaffold**. Its
`scoped_cursor(entity_id, dsn, read_only)` helper verifies that the database role
is neither superuser nor `BYPASSRLS` and sets `app.entity_id` using a transaction-
local parameter. The existing FastAPI application is **not connected to it**.
The server must authenticate the user, authorize the requested entity, use
prepared SQL, enable/test RLS on every sensitive table, and avoid a DB role that
owns or bypasses the policies before this helper can safely handle requests.

**Not completed or verified:** live PostgreSQL staging import, PostgreSQL-backed
FastAPI endpoints, production schema with RLS/constraints/triggers, media import,
financial concurrency testing, frontend production build, and operational
security review. The staging schema is not production-safe. This milestone does
not change SQLite runtime behavior.
