# Rajan Dental — Current Development Release v2.4

**Latest change set:** See [V24_IMPLEMENTATION.md](V24_IMPLEMENTATION.md) for the approved 11-request UI/navigation/clinical-note update, upgrade safety steps, tests and known limitations. This supersedes older feature/status summaries below.

---

# Rajan Dental — Development Build v1.0 (Option 2)

**Theme:** Cream workspace, light peach sidebar, orange buttons/icons, lavender KPI accents. Responsive React interface for desktop, tablets and mobile browsers.

## What's implemented

- Separate login and entity-scoped access; **super administrator can create unlimited new clinic/trust entities** via **Entities > Add a separate entity**.
- Each new entity gets independent code, temporary IDs, UHIDs, visit numbers, invoice/receipt sequences, chair and OT resources, patients, financial records.
- Temporary registration -> first check-in -> permanent UHID (or explicit match with an existing patient **within the same entity**).
- Patient directory and search, doctor directory, appointments with entity-level resource/doctor conflict checks, clinical visits, planned/performed-by treatment records.
- Basic direct invoicing, partial payment receipts and allocations to outstanding invoices; unused portion remains unallocated patient credit.
- Dashboard, responsive sidebar and mobile bottom navigation.

## Run locally

Requirements: Python 3.10+, Node.js 20+.

**Terminal 1 — backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
ADMIN_PASSWORD='Choose-A-Long-Unique-Secret!' python bootstrap.py
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

On Windows PowerShell: `$env:ADMIN_PASSWORD='Choose-A-Long-Unique-Secret!'; python bootstrap.py`.

**Terminal 2 — frontend**

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`; sign in as `admin` with the password you set.

`http://localhost:8000/docs` lists the FastAPI endpoints. The React frontend assumes an API at localhost:8000; set `VITE_API_URL` in a frontend `.env` if different. Backend CORS uses `FRONTEND_ORIGIN` (defaults to http://localhost:5173).

## Adding a new independent entity

1. Sign in as super administrator; open **Entities**.
2. Enter entity name, unique code (e.g. `BR2`), type, chair count and OT count.
3. The backend creates that entity's resources and an administrator membership.
4. Switch the entity in the header. All visible patient/appointment/clinical/billing records are scoped to it.
5. To grant an existing user entity access, use the documented admin endpoint `POST /api/entities/{id}/members` (UI for user creation/assignment is not yet implemented).

## Very important limitations — not for production use

This is a **development MVP**, not a certified or security-audited healthcare system. It uses SQLite for easy setup, bearer tokens held in browser sessionStorage, and simple user roles; it has no MFA, session revocation UI, clinical signatures, file uploads, backup/restore automation, approved consent flows, full patient deduplication, tax accounting, lab/OT workflows, estimates, credit notes/refunds, audit review UI, or data retention automation. The day/week/month control currently changes its selected tab but **does not yet render a full calendar grid**. Doctor scheduling supports manually entered appointments but not recurring opening slots. Doctor conflict prevention applies within one entity; shared staff across entities need an additional global scheduling safeguard.

Invoices are simplified direct invoices, not yet treatment-plan → estimate → invoice conversions. Payment allocations are transactionally bounded within a patient/entity, but refunds, reversals, idempotency keys and patient credit adjustment are still needed. Cross-entity authorization should additionally be hardened with PostgreSQL row-level security in a real deployment. Appointments use ISO timezone-aware times; do not reuse this SQLite overlap algorithm unchanged for production scheduling.

**No real patient data should be entered** until security hardening, audits, regulatory review and backups are completed. Do not expose the development backend or SQLite database to the public internet.

## Recommended next engineering milestones

1. PostgreSQL migrations and row-level security; hardened authentication, user invitation and entity membership UI.
2. Full calendar grid, recurring doctor slots, cross-entity doctor conflict prevention, appointment status changes.
3. Treatment estimate ↔ invoice-line conversion, prescription, tooth odontogram, consent, document storage.
4. Financial ledger/idempotency/refunds and accounting validation, exports and print PDFs.
5. Integration tests, penetration testing, recovery drills, deployment pipeline and clinical/privacy signoff.

## Version 0.2 — Doctor scheduling + estimates (previous update)

Added to the existing React/FastAPI application:

- **Doctor Slots** screen: set weekly opening hours, appointment duration, and dated doctor unavailability. Overlapping recurring time blocks and leave intersecting already-booked appointments are rejected. The appointment API also rejects a booking that overlaps saved leave. **Opening slot enforcement during booking is not yet implemented**: the recurring slots currently document availability but do not prevent booking outside those hours.
- **Appointments**: real Day/Week/Month calendar grids, doctor filter, date navigation, List view and appointment-status updates. Rescheduling via drag-and-drop and multi-resource timelines remain future work.
- **Estimates**: choose existing treatment procedures belonging to one patient, generate entity-scoped estimate, approve it, convert the **entire estimate** to one invoice, and reject a second conversion. Estimate items preserve their procedure names and amount at creation time.
- **Finance bug fix**: duplicate invoice allocations in one receipt are now rejected.
- **Entity-isolation tests** for slots, procedures, and estimates.

To run the backend regression checks (install backend dependencies first):

```bash
cd backend
python test_next.py
```

The development database remains SQLite, and the design is not a healthcare production release. **Do not enter real patient data**. Further work remains: recurring-slot booking enforcement, cross-entity shared-doctor conflict detection, estimate revisions and partial conversion, taxes/discounts, comprehensive ledger controls, user-role management, consent, media storage, PostgreSQL migration and security audit.

### API additions

- `GET/POST /api/entities/{eid}/doctor-slots`
- `DELETE /api/entities/{eid}/doctor-slots/{slot_id}`
- `GET/POST /api/entities/{eid}/doctor-time-off`
- `PATCH /api/entities/{eid}/appointments/{appointment_id}/status`
- `GET/POST /api/entities/{eid}/estimates`
- `POST /api/entities/{eid}/estimates/{estimate_id}/approve`
- `POST /api/entities/{eid}/estimates/{estimate_id}/invoice`

**Frontend verification:** The new screens are authored but the npm dependency install was unavailable in this execution environment; a Vite production build has not been verified. Run `npm install && npm run build` before using the frontend.

## Version 0.3 — Clinical charting and treatment sessions

This release extends v0.2; it does not reset existing records. On first start, `init()` creates new tables in the existing SQLite database (back up your development database before upgrading).

**New responsive screens:**
- **Patient Overview:** choose a patient within the active entity; see visit history, treatment progress, dental findings, completed session history, and invoice balances.
- **Dental Chart:** select FDI-numbered permanent or primary teeth, record tooth surface, finding, and visit-linked clinical note. Existing chart findings remain visible as history rather than being overwritten.
- **Treatment Sessions:** record a separate session for an existing planned treatment, associate a visit of the same patient, record the performing doctor, clinical note and progress. Recording completion locks further sessions on that treatment.

**New API endpoints:**
- `GET /api/entities/{eid}/patients/{pid}/clinical-summary`
- `GET/POST /api/entities/{eid}/tooth-findings` (GET requires `patient_id` query argument)
- `GET/POST /api/entities/{eid}/treatment-sessions` (GET can filter by `treatment_id`)

Doctor/admin role required for the new detailed clinical data API. All new data are constrained to the selected entity and checked against patient/visit/treatment ownership. Creation of findings and sessions writes an audit entry. Responses are demonstration-grade, not legal medical record finalization.

**Regression verification:** from `backend/` run `python test_next.py` and `python test_clinical_v03.py`. These create isolated throwaway SQLite databases. The JSX source was parsed successfully with TypeScript's JSX parser. A full Vite browser build was **not** run because npm dependencies could not be fetched (`EAI_AGAIN`, network resolution unavailable).

**Not yet implemented / production gaps:** file uploads and consent, clinical signatures and append-only amendments, fine-grained per-field permissions, verified patient duplication checks, partial estimate conversion, full financial ledger/refunds, database-backed cross-entity identity of doctors, booking enforcement inside opening slots, centralized backups, PostgreSQL row-level security, production authentication and compliance testing. Avoid real patient data.

## Version 0.4 — Partial estimate billing, consent register, staff accounts

This is an **incremental update to v0.3**, retaining its desktop/tablet/mobile responsive peach-and-orange design and all existing modules. When first imported, SQLite creates new tables for estimate line conversions and patient consent records. **Back up any existing development database before upgrading.**

### Added in Version 0.4

- **Partial estimate invoicing:** After approval, select individual estimate lines for invoice conversion. Each estimate item can be billed at most once and the operation runs in a single write transaction. Other lines remain available; the estimate becomes `invoiced` once all lines are converted. Legacy full-invoice conversion rejects estimates with any partial invoicing history. The legacy whole-estimate conversion route remains for untouched approved estimates. *This is procedure-line selection, not partial quantity/amount billing of an individual line.*
- **Staff Accounts:** Entity admin can create a *new* user with a strong initial password and assign access **only to that entity**. It does not link an existing username to another entity. Existing superadmin membership API remains available; password reset, invitation, MFA, account deactivation and finer permissions remain pending.
- **Consent register:** A doctor/admin can record patient acknowledgment with procedure name, text version, exact wording, acknowledging person and timestamp. Records are scoped to an entity and optionally linked to a visit of the same patient. Records are append-only through the exposed API. **This is not a secure electronic signature workflow**; it does not authenticate the signer, capture a witnessed signature, or verify actual informed consent.
- **Screens:** Responsive `Staff Accounts` and `Consents` pages plus procedure selection controls inside `Estimates`.

### New API endpoints

- `POST /api/entities/{eid}/estimates/{estimate_id}/invoice-selected` with `{ "item_ids": [12, 13] }`
- `GET /api/entities/{eid}/staff-accounts` and `POST /api/entities/{eid}/staff-accounts`
- `GET /api/entities/{eid}/consents?patient_id=<id>` and `POST /api/entities/{eid}/consents`

### Run regression tests

```bash
cd backend
python test_next.py
python test_clinical_v03.py
python test_v04.py
```

All three test suites passed using isolated synthetic databases. Python compilation and JSX syntax parsing passed. A full npm/Vite production build was **not verified** because frontend dependencies were not installed in this environment.

### Outstanding production blockers

No real patient data should be entered. A production rollout still needs secure file uploads/private storage, verified consent with identity and signature, hardened session management and MFA, staff invitations and per-action permissions, formal financial document workflows, tax/discount logic, receipt idempotency and refunds, strict shared-doctor cross-entity scheduling, PostgreSQL isolation policies, clinical signoff, backup/restore and penetration testing. Existing SQLite is for local development only.

## Version 0.5 — Private patient document handling (development)

This incremental version retains all v0.4 functions and the approved light-peach sidebar, cream background, and muted orange buttons across desktop, tablet and mobile.

### New capabilities
- **Documents screen:** choose an existing patient in the active entity, optionally choose one of their visits, select category, upload a document, view document history, and download an authorized file.
- **Protected API:** `GET/POST /api/entities/{eid}/patients/{pid}/documents` and `GET /api/entities/{eid}/patients/{pid}/documents/{did}/download`.
- **Allowed files:** JPEG, PNG or PDF, maximum 10 MiB. Basic file-signature checks, limited rejection of active PDF patterns, unique random stored filenames, SHA-256 file digest, no public URLs, and audit records on upload/download.
- **Isolation:** entity-specific metadata and private storage subdirectories, verified patient ownership and optional visit ownership, role checks for access. Admin, doctor, receptionist may upload; viewer may list/download. Billing-only role has no document access.
- **Local data directory:** environment variable `DENTAL_DOCUMENT_ROOT` can override default `backend/private_documents/`. Keep it private and outside any public web server root. Add directory to backup routines, never commit it to Git.

### Dependencies and startup

Run `pip install -r backend/requirements.txt` again; this release adds `python-multipart` for uploads and `httpx` for local API testing. Back up development data before upgrading: on startup the new metadata table is created in the existing SQLite database. Restart the API after installing dependencies.

### Test

```bash
cd backend
python test_next.py
python test_clinical_v03.py
python test_v04.py
python test_v05.py
```

### Limitations — not production ready

**Do not upload real medical data.** The storage backend is development-only local disk, without encryption-at-rest guarantees or malware scanning. File signature checks are not a malware scanner. Video upload is intentionally not enabled (requires a separate streaming/transcoding/security pipeline). There is no secure document deletion, retention scheduler, backup verification, patient consent for sharing, file thumbnails or object-store migration. Audit logs are database rows, not tamper-proof. The broader application still requires role-policy hardening, MFA, privacy/compliance review, PostgreSQL migration, and end-to-end build/security testing.


## Version 0.6 — signed clinical notes (development)

- Adds the **Clinical Notes** screen with patient + visit selection, draft entry, author-only signing, and timestamped append-only addenda with mandatory reasons.
- New `clinical_notes` and `clinical_note_addenda` tables. Existing v0.5 tables and data remain in place when the same development SQLite database is reused. **Back up the database first**.
- API endpoints: `GET/POST /api/entities/{eid}/clinical-notes`, `POST /api/entities/{eid}/clinical-notes/{note_id}/sign`, and `POST /api/entities/{eid}/clinical-notes/{note_id}/addenda`.
- The API checks entity and patient/visit ownership, restricts note creation and signing to doctor/admin roles, and allows only the original author to sign a draft.
- Signed originals have no edit/delete route; corrections are append-only and audit logged.
- Run `python test_v06.py` in `backend` to verify note signing and entity access tests.

**Still needed before real clinic deployment:** full clinician identity verification, sign-off protocol, MFA, immutable database-level enforcement, trusted timestamps, stronger role-to-doctor binding, audit-log tamper protection, PostgreSQL migration with RLS, and external security review. This is *not* a legally certified electronic signature or clinical EHR platform. Recurring opening-slot booking restrictions, global doctor identity for cross-entity scheduling, and financial reversal controls remain pending.

## Version 0.7 — booking controls and receipt reversal (development)

This version preserves all Version 0.6 functionality and the approved Rajan Dental **Option 2** design (peach sidebar, cream workspace, muted orange actions) across responsive desktop/tablet/mobile layouts. SQLite remains a local development database.

### Doctor appointment opening-hour enforcement

- New `doctor_booking_rules` table and `GET /api/entities/{eid}/doctor-booking-rules` + `PUT /api/entities/{eid}/doctors/{doctor_id}/booking-rules` endpoints.
- In **Doctor Slots**, administrators can enable **strict mode for each doctor** after creating at least one recurring slot. This is opt-in: existing doctors remain in *legacy advisory mode* until enabled, so old demonstration appointments are not silently invalidated. Enable it for every doctor before testing real booking workflows.
- With strict mode enabled, an appointment must occur on a scheduled India-local weekday, fully fit within one weekly opening interval, align to the slot's starting grid, and use a duration divisible by that slot duration. Scheduling uses timezone-aware request timestamps and `Asia/Kolkata` when interpreting weekly hours. Doctor time-off and chair/OT overlaps are still rejected.
- Existing appointments outside newly enabled strict rules are **not retroactively migrated or cancelled**.

### Shared doctors without shared patients

- A super administrator can visit **Doctor Identity Links** and select two profiles representing the **same doctor** across two entities. The new `clinician_links` table records this identity solely for scheduling; patient UHIDs, histories, receipts and invoices remain completely independent.
- `POST /api/clinician-links` creates the identity link after checking existing booking collisions and time-off collisions. `GET /api/clinician-links` lists links to super administrators.
- New appointments and doctor time-off check collisions with linked doctor profiles in other entities. This includes trust-to-clinic booking attempts in both directions.
- No automatic name matching: explicit linking is required; doctor profiles not linked are treated as different clinicians. This development version supports *creation* of two-profile links but not unlink/merge/edit workflows.

### Auditable receipt reversals

- Admins can reverse a receipt using the **Payments** screen. The original receipt and allocation rows are retained, and a new `receipt_reversals` record saves the reason, user and timestamp. This release requires a reason of at least five characters.
- Endpoint `POST /api/entities/{eid}/receipts/{receipt_id}/reverse`. Duplicate reversals return HTTP 409. Cross-entity reversal requests cannot affect another entity's records.
- Invoice outstanding balances and allocation validation exclude allocations belonging to reversed receipts. The original receipt remains visible with a `reversed` status. This does **not** send money back, create a credit note or act as a bank/UPI refund.
- The dashboard's basic collections counter now excludes reversed receipts. This is still **not** a reconciled cash ledger or a completed refund system; other exports/reporting may require separate reconciliation logic.

### Upgrade and verification

Back up `backend/development.db` and private files before upgrading. Starting this version on the same development database creates the new tables via `CREATE TABLE IF NOT EXISTS` without intentionally deleting earlier data. The development server still uses Python's SQLite connection layer; PostgreSQL migration is pending.

```bash
cd backend
pip install -r requirements.txt
python test_next.py
python test_clinical_v03.py
python test_v04.py
python test_v05.py
python test_v06.py
python test_v07.py
uvicorn app:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The six backend suites passed on clean synthetic databases, Python compiled, and the JSX file parsed with the TypeScript compiler. **Full npm install / Vite production build and in-browser visual behavior were not verified in the creation environment.**

### Remaining production blockers

**Do not use real patient data.** The app still needs reliable identity verification for doctor-profile linking, appropriate session/MFA security, granular staff permissions, prevention of race conditions across production workers, PostgreSQL plus row-level security, reconciled financial ledger and net revenue logic, formal credit notes/refunds, verified digital consent/signatures, audited backup/restore, clinical content policy, penetration testing, and privacy/compliance validation. Reversal alone is not a refund. Use isolated demo data and perform a security review prior to deploying to clinics.


## Version 0.8 — Unpaid credit notes and staff deactivation

- Adds **Credit Notes** screen and `GET/POST /api/entities/{eid}/credit-notes`. The admin can issue a nonrefundable credit against the **unpaid remainder** of a single entity-specific invoice, with a mandatory reason and separate `CRN` numbering. The original invoice remains unchanged. Invoice balances and subsequent receipt allocation validation account for issued credit notes. Fully paid portions cannot be credited this way. **No refund or tax correction is generated.**
- Adds global staff-account deactivation by entity admin (for a non-superadmin user with membership in their entity) using `PATCH /api/entities/{eid}/staff-accounts/{staff_id}/deactivate`. It disables that account **in every entity**, revokes all its active sessions, and writes an audit event. It cannot deactivate the requesting user or a super administrator. Multi-entity access removal without global account deactivation is a future milestone.
- Adds `POST /api/logout` to invalidate the current token server-side. The frontend logout button now also calls this server endpoint before clearing browser session storage.
- Adds `backend/test_v08.py` as a regression suite; run all `python test_*.py` tests.

**Limitations:** SQLite development-only, financial statements are not legally audited, no GST credit note document output or external refund processing, no MFA or PostgreSQL RLS. Use synthetic data only.

## Version 0.9 — entity-specific staff permissions and verified offline development backup

This release continues Option 2 UI (light peach / orange / cream). It preserves the SQLite development database and all previous API endpoints and data relationships.

### Entity-specific staff administration

- **Staff Accounts** screen now allows an entity administrator to change an existing staff member's role *within the selected entity*, or remove that user's membership in that entity alone. Both actions invalidate the affected user's sessions so their permissions cannot remain cached in an existing login.
- `PATCH /api/entities/{eid}/staff-accounts/{staff_id}/role` accepts `{"role":"doctor"}` (or `admin`, `reception`, `billing`, `viewer`).
- `DELETE /api/entities/{eid}/staff-accounts/{staff_id}/membership` removes membership only from `{eid}` and preserves access to other assigned entities. The underlying user account remains active.
- Self-removal/self-role changes and modification of super administrator memberships are blocked. Cross-entity membership edits are blocked.
- **Global deactivation** remains a distinct action; it disables a user across every entity. The UI now differentiates the two actions.
- These are basic per-entity *roles*, not yet fine-grained per-action permission policies. Several legacy endpoints still require permissions review.

### Offline backup and verification (development only)

From `backend`, stop writes and ensure you have a safe destination on an independent volume. Run:

```bash
python backup_dev.py create /path/to/private-backups
python backup_dev.py verify /path/to/private-backups/backup_YYYYMMDDTHHMMSS...Z
```

The utility uses SQLite's online backup API to export a consistent database copy, copies local `DENTAL_DOCUMENT_ROOT` files, and writes a manifest containing SHA-256 hashes. `verify` checks file inventory, hash integrity, and `PRAGMA integrity_check` of the backup database. Set environment variables `DENTAL_DB` and `DENTAL_DOCUMENT_ROOT` to the intended environment before running. Ensure backup files are secured, encrypted, and retained according to policy by the operator. **The app does not provide automatic restore.** For consistent database+document snapshots, stop writes and document uploads while creating the archive; the backup does not make those two stores jointly atomic. No cloud storage, offsite replication, encrypted archive, automated scheduling, key management, or disaster recovery is included.

### Tests

```bash
cd backend
python test_next.py
python test_clinical_v03.py
python test_v04.py
python test_v05.py
python test_v06.py
python test_v07.py
python test_v08.py
python test_v09.py
```

Tests use disposable, synthetic SQLite databases. Full frontend build and production security validation remain pending. Production must use PostgreSQL with audited migration strategy, secure row-level isolation, MFA, operational backup/restore drills, financial controls, and privacy/compliance review. **Do not use real patient information.**


## Version 1.0 — account security and entity audit (current)

This version extends v0.9 without changing patient, visit, treatment or financial tables.

**Added endpoints**
- `POST /api/me/change-password` — current and new password; new password at least 12 characters with a letter and a digit. On success all sessions for the account are revoked, including the requesting session.
- `POST /api/me/logout-all` — revokes every active session belonging to the caller.
- `GET /api/entities/{eid}/audit-events?limit=50&offset=0` — available only to administrators assigned to the requested entity, paginated at a maximum of 100 records. Events for other entities are never returned.

**Added React screens**
- **Account Security:** change own password and log out all devices.
- **Activity Log:** entity-isolated administrative activity listing.

**Login throttling** — five failed sign-in attempts for a username within the last 15 minutes temporarily block further attempts for that username. This is an application-level *username* throttle; not a substitute for per-IP / gateway controls and MFA. A determined adversary could deny login to a specific username. No password reset / account recovery flow exists yet.

**Tests:** `python test_v10.py` verifies account password rotation, rejection of old sessions, log-out-all, login throttling, and audit permissions. Existing v0.2–v0.9 regression tests were also run successfully in this build environment.

**Frontend verification:** `npm run build` could not run here because Vite / node_modules were not installed (`vite: not found`). Install dependencies using `npm install` before building. Do not treat unverified JSX as a production-tested frontend.

**Security boundaries:** This build still uses SQLite, bearer tokens in sessionStorage, development file storage, and an incomplete permission model. A PostgreSQL migration, RLS, hardened authentication/MFA, immutable and comprehensive audit logging, full recovery drills, medical privacy review, and a successful browser build are required before any real patient data.

---

## Consolidated development update — v1.1 (24 November 2026)

This increment adds **optional authenticator MFA** (TOTP, encrypted secrets with external Fernet key), a **refund register** for previously reversed receipts, and a **per-entity finance summary**, together with a disposable **restore-test** command. It retains the earlier React/FastAPI/SQLite stack and separate CL/TR patient and financial records.

### MFA development setup

Set a persistent random Fernet key **outside source control**:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Export DENTAL_MFA_FERNET_KEY in the backend process environment securely.
```

Existing accounts can sign in with just their password until an authenticator is enrolled. The Account Security screen reveals an enrollment secret once and prompts for a six-digit OTP. Activating MFA revokes existing sessions. Keep the encryption key consistent: loss of the key makes existing enrolled MFA secrets unusable. Authentication recovery and key rotation are not yet built.

### Refunds

Refunds are *recorded* only after an administrator reverses the source receipt; the API prevents recorded refunds from exceeding the reversed receipt amount. It does **not** initiate or verify bank, UPI, card or cash repayment. Use synthetic data only.

### Backup restore simulation

```bash
cd backend
python backup_dev.py create /secure/dev-backups
python backup_dev.py restore-test /secure/dev-backups/backup_YYYYMMDDTHHMMSS...
```

The restore test copies backed-up files into a temporary folder, checks SQLite integrity, foreign keys, and referenced document availability, then discards the restoration. This is not a production recovery solution.

### Tests

```bash
cd backend
python test_v11.py
```

### PostgreSQL

**Not migrated.** See `migration/README.md` and `migration/postgres_rls_template.sql` for prerequisites and a policy design template. PostgreSQL is necessary for a production migration, and the application still uses SQLite until the persistence layer is ported and tested.

### Deployment

**Not production ready.** See `operations/production_readiness.md` for the release gates.

### CI validation workflow

`.github/workflows/validation.yml` runs all ten Python regression scripts and attempts a Vite frontend build on GitHub Actions when this application folder is used as the repository root. The workflow is **provided but has not been executed on GitHub Actions** here.


## Version 1.2 — verified migration export and financial privacy

- New `migration/export_sqlite.py` exports an **offline** SQLite snapshot to private,
  deterministic JSON Lines and a checksum + per-entity financial-parity manifest.
- `python migration/export_sqlite.py verify OUTPUT_DIR` confirms integrity and parity.
- Reception, doctor and viewer roles are now blocked from listing invoices, receipts,
  and estimates; non-billing dashboard responses omit monetary totals.
- Billing and administrators retain those finance views. Server-side membership checks apply.
- Run `python backend/test_v12.py` to test finance permissions, entity denial,
  and migration-file tamper detection.
- **This release still runs on SQLite.** PostgreSQL DDL, importer, application adapter,
  RLS enforcement, and actual PostgreSQL tests have not been completed.
- The responsive UI may show finance navigation to unauthorized roles until the frontend
  is updated to hide inaccessible actions. The server correctly denies those requests.


## Version 1.3 — migration integrity preflight and defense-in-depth (2026-11-24)

This update adds database-level validation triggers to reject inserts and updates to
`allocations` when the receipt and invoice belong to different patients or allocations
exceed the receipt amount. The API checks remain in place.

A read-only synthetic/offline snapshot preflight tool detects inconsistencies that
SQLite foreign keys alone cannot catch, such as a treatment session referring to
a visit for another patient or an invalid receipt allocation.

```bash
python migration/audit_integrity.py /private/offline/synthetic.sqlite3
python backend/test_v13.py
```

Exit status 0 means all implemented checks passed, and exit status 2 means
a check failed. Run the audit on an offline/checkpointed snapshot, not a live
SQLite database being modified. The audit outputs aggregate counts only.

**Limitations:** This does not migrate the application to PostgreSQL, enforce
PostgreSQL RLS, validate documents against storage, establish complete immutable
clinical/financial ledgers, or constitute an independent production security review.
Existing bad rows are not auto-corrected. The audit is a preflight check rather
than an assurance of complete data validity. This application is for synthetic
development data only.


## Version 1.4 — PostgreSQL staging migration tools
- `migration/postgres_stage.py`: generates reviewable staging SQL and can import a verified SQLite export into a **new isolated PostgreSQL staging schema**. Does not change live API database.
- `backend/test_v14.py`: offline synthetic staging-plan validation, composite-FK check and export integrity rejection.
- Details and limitations in `migration/README.md`; live PostgreSQL tests are still pending.

## Version 1.5 staging-migration safety milestone

Adds `migration/postgres_validate.py` (read-only PostgreSQL staging parity +
semantic validation), strengthens `migration/postgres_stage.py` with semantic
checks before commit, and adds `migration/pg_scope.py`, a reusable PostgreSQL
transaction-scoped entity context helper for a *future* runtime port. New
`backend/test_v15.py` covers the portable checks and fail-closed inputs.

**Application runtime remains SQLite.** The new PostgreSQL utilities require a
separately provisioned secured PostgreSQL instance and psycopg, neither of which
was used for live integration verification in this release. Refer to
`migration/README.md` for commands and limitations. **Do not use real patient
records or treat this as production-ready.**

## Version 1.6 – PostgreSQL runtime read-only canary (development only)

Adds `GET /api/entities/{eid}/postgres-readiness` for administrators only. It is
**disabled by default** and uses the authorized entity context from the current
SQLite-backed session. Before enabling it, see `migration/PG_RUNTIME_V16.md`.
Requires the optional PostgreSQL driver `pip install 'psycopg[binary]>=3.2,<4'`,
a separately secured PostgreSQL runtime database (NOT the staging schema),
`RAJAN_PG_DSN`, and `RAJAN_ENABLE_PG_PROBE=1`. It rejects incomplete RLS, an
unsafe database role or unavailable PostgreSQL. This is NOT a production
PostgreSQL migration. All existing API writes still use SQLite.

Test with `python backend/test_v16.py` and run all earlier `test_*.py` scripts
from the backend directory. Only synthetic data is authorized for the probe.

## Version 1.7 – PostgreSQL patient runtime pilot

Introduces an **isolated, admin-only, disabled-by-default** PostgreSQL test
write path for temporary patient registration, transaction-safe UHID creation
at check-in, and patient searching. The regular application remains SQLite.
See `migration/PG_PATIENT_PILOT_V17.md` for the provisioning and testing guide.
Do not enable for real patient data or normal clinical workflows.

## Version 1.8 – isolated PostgreSQL visit pilot

Added RLS-scoped PostgreSQL **synthetic visit creation/history** in `migration/pg_patient_pilot.py` and two guarded FastAPI endpoints. The full pilot schema is `migration/pg_patient_pilot.sql`; an upgrade path for disposable v1.7 pilot databases is `migration/pg_patient_pilot_v18_upgrade.sql`. See `migration/PG_VISITS_PILOT_V18.md` for limitations and access controls. The normal clinical application **still uses SQLite**, and these visits must not be used with its appointment, treatment or billing APIs. Run `backend/test_v18.py` for the new tests.

## Version 1.9 — PostgreSQL appointment scheduling pilot

Added separate PostgreSQL pilot scheduling tables with doctor/chair/OT exclusion constraints, entity-scoped foreign keys, weekly doctor opening-hours validation, appointment booking/listing and cancel/no-show APIs. The pilot remains **synthetic-only**, administrator-only and disabled by default. It does not replace the normal SQLite calendar or handle live clinic records. See `migration/PG_APPOINTMENTS_PILOT_V19.md` for setup, current limitations and testing requirements. The existing version 1.8 pilot schema can be upgraded with `migration/pg_patient_pilot_v19_upgrade.sql` after review and backup.

Verified locally: all 18 backend regression test scripts and Python compilation. Frontend production build unverified because npm offline dependencies are unavailable. Real PostgreSQL execution and concurrent transaction verification remain pending.

## Version 2.0 — PostgreSQL clinical-to-payment synthetic pilot

Introduces a single PostgreSQL pilot workflow across registration, check-in, visits, treatment entry, invoices, and receipts, using composite patient/visit/entity foreign keys, decimal INR payments, invoice locking and a deferred allocation-validation trigger. Adds a strictly isolated admin diagnostic screen. The operational SQLite application, its UI, and all existing clinical/financial records remain unchanged.

- New service: `migration/pg_finance_pilot.py`
- New pilot upgrade: `migration/pg_patient_pilot_v20_upgrade.sql` (existing v1.9 disposable pilot only)
- Fresh disposable schema updated: `migration/pg_patient_pilot.sql`
- Development UI: `PostgreSQL Pilot`, restricted to superadmin navigation, with backend admin membership checks
- Tests: `backend/test_v20.py`, plus previous regression scripts
- Instructions and required production safeguards: `migration/PG_CLINICAL_FINANCE_PILOT_V20.md`

**Verification:** 19 backend script files passed with synthetic fixtures (including v2.0); Python compilation and TypeScript JSX parsing were successful. The frontend Vite production bundle and live PostgreSQL connection tests could not be executed because the required components were not available. **Not production ready; do not use real patient records.**

## Version 2.1 — Synthetic PostgreSQL receipt retry protection

The isolated PostgreSQL pilot now adds a per-entity payment idempotency key, a canonical request hash, database uniqueness, and transaction-scoped advisory locking. `POST /api/entities/{eid}/pg-pilot/receipts` requires a stable `idempotency_key` for a payment attempt; sending the same key with unchanged details returns the original receipt instead of double-posting it. The pilot UI reuses the key for retries until the payment details change.

**Schema:** new disposable installs use `migration/pg_patient_pilot.sql`; v2.0 installs with an **empty** receipt table can apply `migration/pg_patient_pilot_v21_upgrade.sql`. The upgrade rejects populated receipts. See `migration/PG_CLINICAL_FINANCE_PILOT_V20.md`.

**Verification:** run `python backend/test_v21.py`. These are simulated-cursor tests, not live PostgreSQL or concurrent-transaction verification. The operational app still uses SQLite; do not use real clinical/financial data.

## Version 2.2 — optional real PostgreSQL smoke-test harness

Added `migration/pg_live_smoke_v22.py` and `migration/PG_LIVE_SMOKE_V22.md`.
The new script is **disabled without explicit environment opt-in** and only accepts a fresh disposable database whose name includes `smoke`. It checks the pilot's patient-to-payment path, restricted-role RLS behavior, doctor/chair overlaps, and concurrent duplicate receipt retries. It does not switch operational APIs to PostgreSQL.

`backend/test_v22.py` checks the script's safety gates offline; it is **not a substitute for a live PostgreSQL run**. The operational application remains SQLite-based and synthetic-data-only.

## Version 2.3: Patient-centered navigation

Patient-specific functions are now grouped in a selected patient's dashboard. See `PATIENT_WORKSPACE_V23.md` for entry points, included tabs, and manual verification steps. No schema or endpoint changes were required for this frontend update.
