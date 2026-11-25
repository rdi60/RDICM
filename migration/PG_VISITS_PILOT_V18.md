# Version 1.8 – PostgreSQL patient visit pilot

**Synthetic data and isolated staging only.** The normal application still uses SQLite for all patient, appointment, visit, treatment, invoice and receipt workflows. Pilot patient and visit IDs are never interchangeable with SQLite IDs.

## New pilot operations

- `POST /api/entities/{eid}/pg-pilot/visits` with `{"patient_id":123,"chief_complaint":"..."}` creates a pilot visit with an entity-scoped `CL-VIS-000001`-style number. An entity-scoped patient lookup is required before insertion.
- `GET /api/entities/{eid}/pg-pilot/patients/{patient_id}/visits` returns up to 100 visits for an entity-owned patient.
- Both endpoints require an authenticated entity administrator and the pre-existing test-only flags `RAJAN_ENABLE_PG_PATIENT_PILOT=1` and `RAJAN_PG_PILOT_SYNTHETIC_ONLY=YES`.
- The PostgreSQL schema requires a composite foreign key `(entity_id,patient_id)`, unique visit numbering, ENABLE + FORCE RLS and an entity policy. The API must connect as a non-owner non-BYPASSRLS role.

## Applying the pilot schema

For a **new disposable database**, apply `pg_patient_pilot.sql` using a provisioning role. For an existing disposable Version 1.7 pilot, review and run `pg_patient_pilot_v18_upgrade.sql`; review and apply the limited `visits` table and sequence grants shown there. A new/updated API role must not own the pilot tables.

Do not enable these endpoints for production. The SQL schema and fake-cursor tests do not prove enforcement on a live PostgreSQL server; run the actual integration tests there before using the pilot even for trial operations. PostgreSQL is not the application's main database yet. The pilot has no doctor assignment, signed clinical notes, appointment resources, or billing.

## Tests

`python backend/test_v18.py` (from the project root) runs simulated database tests and disabled-endpoint authorization checks. It does not connect to PostgreSQL. All earlier backend scripts should also pass. A live PostgreSQL server and frontend dependency environment are required for separate integration and browser verification.
