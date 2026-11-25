# Rajan Dental v1.9 PostgreSQL appointment scheduling pilot

**Development and synthetic data only.** This pilot is separate from the operational SQLite calendar, billing, patients and visits. The normal app remains on SQLite. Do not load real patient information.

## What is new

- PostgreSQL tables: `doctors`, `resources`, `doctor_hours`, `appointments` within `rajan_pilot`.
- Strict entity-scoped composite foreign keys and PostgreSQL `ENABLE/FORCE ROW LEVEL SECURITY` for each table.
- Database exclusion constraints for overlapping active bookings, per entity and doctor; and per entity and chair/OT.
- Booking service checks patient, doctor and chair/OT belong to the selected entity, have active status, and the appointment lies fully inside a configured doctor weekly opening slot (Asia/Kolkata).
- An appointment number counter per entity (`CL-APT-000001`, `TR-APT-000001` etc.).
- Administrator-only pilot APIs behind both `RAJAN_ENABLE_PG_PATIENT_PILOT=1` and `RAJAN_PG_PILOT_SYNTHETIC_ONLY=YES`.

## Setup in a disposable PostgreSQL database

1. Review `/migration/pg_patient_pilot.sql` and provision a fresh disposable database using a trusted migration/owner role. For existing v1.8 disposable instances, review and run `/migration/pg_patient_pilot_v19_upgrade.sql` **once** instead. Do not run both against the same schema.
2. Verify `btree_gist` extension can be created by the provisioning role. Do not give CREATE/ALTER, table ownership, SUPERUSER or BYPASSRLS to the API role.
3. Provision entity IDs/codes to match the test SQLite entities. Provision **synthetic** doctors, chairs/OTs, and weekly opening hours using a trusted administration role. Use `weekday=0` for Monday through `6` for Sunday. Do not grant the API role write access to doctor/resource/hours provisioning tables.
4. Review all explicit SQL GRANT examples in the DDL, configure `RAJAN_PG_DSN` for the restricted API role, and separately verify PostgreSQL RLS behavior with a real connection.
5. Start the existing FastAPI backend, enable the two pilot flags, authenticate as an entity administrator and use:
   - `GET /api/entities/{eid}/pg-pilot/scheduling-resources`
   - `POST /api/entities/{eid}/pg-pilot/appointments` with `patient_id`, `doctor_id`, `resource_id`, `start_local: "2026-11-30T09:00"`, `duration_minutes:30`, `reason`
   - `GET /api/entities/{eid}/pg-pilot/appointments?day=2026-11-30`
   - `PATCH /api/entities/{eid}/pg-pilot/appointments/{id}/status` with `{"status":"CANCELLED"}` or `{"status":"NO_SHOW"}`
6. Test concurrent overlapping bookings from separate client connections: exactly one should commit for the same doctor or same resource. Test cancellation then rebooking. Test a different entity's patient/doctor/resource ID cannot be used. Exercise restrictions and grants as the real non-owner API role.

## Limitations / next milestones

- **Not a live PostgreSQL end-to-end test.** The v1.9 unit tests simulate PostgreSQL cursors and inspect SQL constraints; PostgreSQL binaries/drivers were not available in the development environment.
- Doctor availability is a simple weekly interval. Holiday exceptions, leave, roster variations, chair setup/turnover time and break handling are not supported by this pilot.
- Cross-entity shared-doctor conflicts are not enforced in this pilot. The operational SQLite system retains its own unrelated doctor linkage logic; this PostgreSQL pilot must not replace it without equivalent global-doctor controls.
- These are pilot-only appointments, not linked to existing SQLite calendar, visits, treatments, invoices or receipts.
- No live database migration or production cutover, no frontend integration into the usual calendar, and no production security audit.
- Conflict handling maps PostgreSQL exclusion violation SQLSTATE `23P01` to HTTP 409; other PostgreSQL errors are not intentionally converted into conflict messages.

## Test

`cd backend && python test_v19.py` and run the earlier regression scripts. Never use real patient data in the test suite.
