# Rajan Dental — Version 2.4 Patient Dashboard & UI Refresh

Based directly on the Version 2.3 Patient Dashboard package. Existing SQLite tables, patient data IDs, legacy clinical-note sign/addenda APIs, finance APIs, authentication and entity isolation rules are retained. New changes are additive (two tables).

## Implemented change requests

1. **Chair & OT:** Resource-count panel removed from the main dashboard; optional resource controls hidden until the Super Administrator turns on **Entities → Feature settings → Enable Chair & OT** for the current entity. The default is disabled; resources and historical records are not deleted. Optional resource column and appointment resource selection are conditional.
2. **Patient-centric navigation:** Patient clinical and billing sections remain under a selected patient's dashboard. Switching entity closes the current patient context.
3. **Option 2 visual update:** Cream main workspace, peach sidebar, Rajan Dental brand asset, pastel KPI cards, orange controls, responsive schedule card and soft surfaces.
4. **Breadcrumbs:** Entity name navigates to the entity's dashboard; Patients navigates to directory; patient UHID breadcrumb navigates to Patient Overview. Implemented as buttons, without a full page reload.
5. **Form drawers:** Compact `+ New` actions replace permanently visible forms for appointments, new patient registration, adding doctor, clinical visits, treatments, treatment sessions, estimates, billing, receipts, consent, clinical notes, document upload, staff, doctor slots/time off, and entity creation. Form content is preserved.
6. **Patient directory:** Entire table row opens Patient Dashboard with keyboard Enter support. `Patient Workspace` terminology is replaced with `Patient Dashboard`.
7. **Documents:** Patient-specific category filters, search, grid/list switch, authenticated JPG/PNG thumbnail generation and in-app JPG/PNG/PDF previews; image zoom/rotation and PDF zoom via native PDF viewer. Existing private documents and download endpoints remain available. PDF page navigation depends on the browser's PDF viewer.
8. **Patient context:** Patient Overview no longer prompts for patient selection. Patient selectors inside patient-specific clinical, financial, and consent modules are hidden when the patient is already selected.
9. **Notes:** Patient and visit dropdowns removed. New notes use the selected patient's latest visit (must exist), an entity-specific doctor selector, and an editable history. The Sign button is not shown, but legacy signed notes remain unchanged and revisions of signed notes never overwrite the original.
10. **Auto-save:** Debounced two-second save after changes, manual Save, success/failure status, optimistic version conflict checking and reopen of last successfully saved note from backend.
11. **Audit:** Every successfully committed v2.4 note revision stores before/after text, doctor ID, actual editing user, save method, timestamp and revision number in `clinical_note_revisions` and writes an entry to the existing `audit` activity log. Other existing business action audit events are preserved. **Full old/new field snapshots for other modules are not added**; their existing audit logging remains at the prior action level.

## Database additions (automatically created by existing `init()` on backend startup)

- `entity_features`: entity-scoped optional resource visibility flag, default disabled.
- `clinical_note_revisions`: versioned note content with before/after, doctor, user, source and timestamps. Applies to both ordinary draft edits and changes to signed notes; original signed body remains immutable.

New API routes:

- `GET /api/entities/{eid}/features`
- `PUT /api/entities/{eid}/features` (super admin only)
- `POST /api/entities/{eid}/clinical-notes/v24` (doctor/admin)
- `PUT /api/entities/{eid}/clinical-notes/{note_id}/content` (author/entity admin, optimistic locking)
- `GET /api/entities/{eid}/clinical-notes/{note_id}/revisions` (doctor/admin)
- `GET /api/entities/{eid}/patients/{pid}/documents/{did}/preview` (entity-scoped and authenticated)

## Upgrading an existing local Version 2.3 installation (Windows)

**Back up your existing project and database before upgrading.** In particular, preserve:

- `backend/development.db` (or custom `DENTAL_DB` location)
- `backend/private_documents/` (or custom `DENTAL_DOCUMENT_ROOT`)
- Your environment variables, configured administrator credentials and MFA key

1. Stop the frontend and backend.
2. Make a full backup of the old application folder. Keep all existing database and document files.
3. Extract Version 2.4 into a **new folder**, rather than overwriting your running Version 2.3 installation.
4. Copy the backup of the database and private document folder into the matching paths in the new backend (or configure the same paths with environment variables). Do **not** run `bootstrap.py` on an existing populated database.
5. From the new `backend` directory, install `requirements.txt` into a virtual environment, then start `python -m uvicorn app:app --reload --port 8000`. Startup creates only the two new tables if they do not exist.
6. From `frontend`, run `npm install`, `npm run dev`, and open `http://localhost:5173`.
7. Verify both entities, previously entered patients, note history, document downloads, appointments, invoice balances, and backups before accepting the update.

When switching to the new installation, **never overwrite database files with packaged test fixtures**. This archive does not contain your clinic data.

## Verification and limitations

- 21 earlier backend scripts passed individually; the Version 2.4 focused API test passed.
- Static patient-navigation checks passed; JSX parser and TypeScript JSX transpilation reported zero syntax errors.
- An actual Vite production build and browser-based workflow test could **not** be completed in this environment: `npm install` failed because the npm registry was unreachable (`EAI_AGAIN`). Run `npm install && npm run build` and exercise the UI locally before accepting the update.
- Existing application remains SQLite-based and for synthetic-data development only. PostgreSQL pilot code remains isolated and unchanged. Security hardening, live deployment testing and independent clinical/data-privacy validation are still required.
- Autosave is backend-persisted and versioned; if a browser closes *before* a pending autosave completes, only the last successful save can be recovered.
- PDF preview/zoom follows browser support; thumbnails for PDF files display a PDF icon rather than a rendered first page.
- A browser's Cancel/close action warns about unsaved clinical notes. Other unsaved form drawers currently close without draft warning; this remains a UX follow-up.
