# Version 2.2: Live PostgreSQL integration smoke test (optional)

**Status:** Runnable test harness added. It has not been run against PostgreSQL in this build environment. The operational application **still uses SQLite**. Only synthetic data is permitted.

## Preconditions

1. Provision a **new empty disposable PostgreSQL 16+ database**, with a database name containing `smoke`. The script refuses a database that already contains the `rajan_pilot` schema; it does not delete existing objects.
2. Create a trusted schema-owner role and a separate **restricted, nonowner, non-superuser, NOBYPASSRLS** API role. Do not use these roles for any real patient environment. The owner DSN should have permission to create the `btree_gist` extension and tables in the disposable database. Review and grant extension privileges as needed.
3. Install `psycopg[binary]` using `pip install -r migration/requirements-pg-optional.txt`.
4. Set the two DSNs in your environment and explicitly opt in:

```bash
export RAJAN_PG_SMOKE_OWNER_DSN='postgresql://owner:...@localhost:5432/rajan_smoke_test'
export RAJAN_PG_SMOKE_API_DSN='postgresql://app:...@localhost:5432/rajan_smoke_test'
export RAJAN_PG_SMOKE_DISPOSABLE=YES
python migration/pg_live_smoke_v22.py
```

Never commit DSNs, passwords, or real patient identifiers. The smoke test creates a new synthetic pilot schema and rows. Use a one-time database and destroy it after inspection. Avoid public networking; use TLS when remotely connecting.

## What the test verifies against a real database

- Schema DDL applies to a clean PostgreSQL instance, and a distinct restricted API role can use scoped transactions.
- Separate temporary registration, UHID, repeat check-in, and visit creation workflows for two entities.
- Database RLS hides patient records when the request has no entity context or the wrong entity context.
- Doctor opening hours, doctor/chair exclusion constraints, and rejected double booking.
- Patient-owned treatment, invoice and receipt creation, ledger math and over-allocation rejection.
- Repeated receipts with the same idempotency key reuse the posted receipt, including two concurrent requests.

**Limitations:** This smoke test does not migrate historical SQLite data, switch operational endpoints, test full UI workflows, verify shared doctors across entities, verify clinical documents or consent, test credits/refunds, or constitute a full security audit. It is explicitly destructive in a disposable schema and makes no production-readiness claim. The test requires owner and API database roles and will fail fast without prerequisites.

If the test fails, inspect SQL privileges, migration/schema compatibility and RLS policy behavior before considering any cutover. Never use this test against production or shared staging databases containing actual patient information.
