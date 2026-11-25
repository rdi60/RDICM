# Version 1.7 – Isolated PostgreSQL patient runtime pilot

**Not a production migration.** The normal registration, check-in, appointments,
visits, finance, authentication, and audit APIs are still SQLite-backed. This
module is a **separate synthetic-data PostgreSQL pilot**. It must not be used
for real patients or connected to the normal clinical workflow.

## What is implemented

- Isolated PostgreSQL provisioning DDL in `pg_patient_pilot.sql` for entity
  metadata, counters, registrations and patients.
- A `pg_patient_pilot.py` runtime service uses `pg_scope.scoped_cursor`
  (transaction-local entity context, unsafe DB-role rejection), checks RLS
  metadata and entity-code mapping, and inserts registrations atomically.
- Check-in locks the source registration with `FOR UPDATE` and creates a UHID
  exactly once; retries reuse the same patient. Existing patient references
  must belong to the same entity.
- Separate **admin-only** endpoints:
  `POST /api/entities/{eid}/pg-pilot/registrations`,
  `POST /api/entities/{eid}/pg-pilot/check-in`,
  `GET /api/entities/{eid}/pg-pilot/patients?q=...`.
- All pilot endpoints are disabled unless **both**
  `RAJAN_ENABLE_PG_PATIENT_PILOT=1` and
  `RAJAN_PG_PILOT_SYNTHETIC_ONLY=YES` are configured on a testing server.

## Testing setup (synthetic data ONLY)

1. Provision a disposable PostgreSQL 16+ server using a privileged **provisioning
   role**, not the API role. Run `pg_patient_pilot.sql` against that disposable DB.
2. Provision trusted `rajan_pilot.entities` rows **with the same numeric entity ID
   and code** as your disposable SQLite test database. This is a manual alignment
   for development, not an acceptable final identity sync strategy.
3. Create a **separate**, non-owner, `NOSUPERUSER NOBYPASSRLS` PostgreSQL role;
   grant limited permissions shown in the SQL file. Make sure it cannot create
   objects in the pilot schema or modify `entities`.
4. Install optional driver `pip install 'psycopg[binary]>=3.2,<4'`; configure
   the API role's TLS-protected DSN as `RAJAN_PG_DSN` using secret storage.
5. Run the dedicated `backend/test_v17.py`. Live database integration tests
   (`backend/test_pg_live_v17.py`) are opt-in and require an isolated database.
6. After independent review, use the two feature flags above on a test server.
   Never enable on a live environment or use with real records.

## Security and limitations

RLS metadata checks are preliminary, **not proof** of isolation. The pilot
schema does not implement the complete clinic database, financial transactions,
clinical records, audit trail or production security. This pilot uses the
SQLite user sessions to authorize the PostgreSQL calls; a production port must
move authentication and membership to the reviewed PostgreSQL architecture.

A full runtime cutover requires converting every API query, foreign key,
transaction and clinical/financial workflow, testing concurrency and RLS on a
real PostgreSQL server, frontend build tests, recovery testing and security
review. The pilot's data is NOT mirrored into SQLite and vice versa.
