# Rajan Dental 2.0 — isolated PostgreSQL clinical-to-payment workflow

**Status: code implemented, simulated cursor tests passed; real PostgreSQL execution unverified. Development/synthetic records only.** This is not an automatic replacement for SQLite or a production release.

## Added functionality

- New PostgreSQL tables: `treatments`, `invoices`, `invoice_items`, `receipts`, `receipt_allocations`.
- Dental treatment references a patient, its visit, and a doctor in the **same entity**, protected by composite foreign keys.
- Single treatment line may appear on at most one invoice; invoices store fixed-decimal INR amounts (`NUMERIC(13,2)`), not floating-point values.
- Receipts can be allocated to invoices of the **same patient and entity**, leaving unallocated credit. A receipt may pay several invoices in a transaction. Invoice rows are locked in ascending ID order to prevent concurrent over-allocation.
- Deferred database constraint trigger rechecks aggregate allocation totals before commit. The API role must not own these tables or have permission to edit triggers, alter RLS, or update/delete already-posted invoices or allocations.
- All five new tables use `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. Backend checks entity-specific RLS metadata and uses restricted per-transaction entity context.
- Administrator-only endpoints behind `RAJAN_ENABLE_PG_PATIENT_PILOT=1` and `RAJAN_PG_PILOT_SYNTHETIC_ONLY=YES`.
- A separated admin diagnostic UI called **PostgreSQL Pilot** provides a guided test of temporary registration, UHID, visit, treatment, invoice, receipt and ledger; pilot IDs must not be used in the normal application screens.

## Installation in an isolated disposable PostgreSQL database

1. For a brand-new synthetic database, provision `migration/pg_patient_pilot.sql` using a trusted database owner. For an **existing v1.9 pilot**, review and apply `migration/pg_patient_pilot_v20_upgrade.sql` **once**; do not apply the full schema over existing objects.
2. Provision sample entities, doctors, and other required resources using trusted scripts. Review privileges and explicitly grant the non-owner API database role only needed `SELECT`, `INSERT`, and necessary sequence usage.
3. Configure a restricted non-owner DSN in `RAJAN_PG_DSN`, then set `RAJAN_ENABLE_PG_PATIENT_PILOT=1` and `RAJAN_PG_PILOT_SYNTHETIC_ONLY=YES`. Never enable on a system containing real patient information.
4. Authenticate to the app as an administrator with the correct entity membership and open the PostgreSQL Pilot screen. Use synthetic data exclusively.
5. Run the full sequence: register -> check-in -> create visit -> create treatment -> invoice -> receive and allocate -> inspect ledger. Verify independent UHIDs and transactions for two different entities.

### New API routes

| Method | Relative to `/api/entities/{eid}/pg-pilot` | Payload / result |
|---|---|---|
| POST | `/treatments` | `patient_id, visit_id, planned_by, description, tooth_number` |
| POST | `/invoices` | `patient_id, items:[{treatment_id, amount:"4500.00"}]` |
| POST | `/receipts` | `patient_id, amount:"2000.00", payment_mode:"UPI", allocations:[{invoice_id, amount:"1500.00"}]` |
| GET | `/patients/{patient_id}/ledger` | Invoice totals, allocations, outstanding balances |

### Mandatory tests **before a cutover**

- Exercise each new endpoint with a *real* PostgreSQL 16+ instance and the actual restricted non-owner API role.
- Attempt cross-entity patient/visit/doctor/treatment/invoice/receipt references and verify denial by the database itself.
- Concurrently post two competing receipts to the same invoice using separate connections. Verify no over-allocation can commit.
- Test duplicate treatment billing, invalid FDI tooth numbers, invalid decimal amounts, orphan visits, privilege escalation, missing RLS policies and wrong database role.
- Verify failures roll back invoices, invoice items, receipt and allocation rows together. Test backup restoration and invoice reconciliation independently.
- Migrate and test the **full operational API**, including consent, X-rays, signed clinical notes, estimates, credit notes, refunds, all appointment states and access policies. These remain in SQLite at this milestone.
- Run complete frontend dependency install and production build; browser-test desktop/tablet/mobile.

## Known limitations

- PostgreSQL integration covers an isolated synthetic clinical-to-payment slice, not the operational API. Operational patient, appointment, clinical, document and billing screens **still use SQLite**.
- No live PostgreSQL binary/driver was available for this environment's integration tests. Test results use simulated SQL cursors and source/schema checks, not database isolation/concurrency proof.
- No credit notes, refunds, reversals, tax configuration, estimate conversion or doctor-performed treatment recording in the PostgreSQL pilot.
- The diagnostic UI is not the full production experience. Do not deploy it with live patient data.
- SQL upgrade DDL and grants require professional PostgreSQL review before use.

## Version 2.1: receipt retry safety (pilot only)

- New pilot receipt POST requests require `idempotency_key` (8–100 ASCII letters, digits, underscore or dash). Generate the key **once per payment attempt**, not once per HTTP retry. The diagnostic UI keeps the key while payment fields remain unchanged.
- Matching retries return the existing receipt with `replayed: true` and do not allocate a second payment. Reusing the same key with different patient, amount, method, reference, or allocation details is rejected.
- The database enforces a unique key **within each entity**, and transaction-level advisory locking serializes competing requests with the same key. The request's canonical SHA-256 hash detects payload changes.
- Existing v2.0 pilot databases must apply `pg_patient_pilot_v21_upgrade.sql` **only if the pilot receipt table is empty**. The upgrade refuses populated pilot receipts rather than modifying existing payment records. Recreate a disposable synthetic pilot or perform a separately reviewed migration.
- The production SQLite receipt route and normal app are unchanged. This feature has not been tested on a live PostgreSQL server or under real concurrency.
