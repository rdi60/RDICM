# Rajan Dental v0.4 – Development status

This is an incremental source-code update on `main`, **not a validated clinical production release**.
No ZIP package was generated.

## Implemented and committed

- Removed generic Back to previous screen button from main page headings; existing navigation and breadcrumbs retained.
- Visit Clinical Records show a highlighted date/time band without visit ID; empty complaint, diagnosis, and notes are suppressed.
- Audit Log pagination uses compact bottom-right buttons.
- Procedure & Pricing Master is organized into compact Pricing / Procedures / Treatment Categories tabs and row actions.
- Staff Admin is organized into Accounts / Permission Groups / Access Assignments tabs with compact forms, correctly aligned checkboxes, and per-entity collapsed multiselects.
- Staff Access editor reads existing roles/groups before editing to reduce accidental permission replacement.
- Clinical note autocomplete uses entity-scoped admin-maintained text shortcuts. Suggestions require explicit selection.
- Existing server autosave remains. Added encrypted device-local draft recovery and manual restore; encrypted recovery secret can be rederived on login from the same credentials and local salt. Explicit logout removes local copies.
- Downloadable Excel (.xlsx) and CSV example templates for: Procedures & Pricing, Pricing & Treatment Categories, Staff & Doctor Directory, Roles & Groups, Patient Master, Opening Balances & Advances, Clinical Text Templates. Procedure Name is column one; Treatment Category is column two.
- Added GitHub Actions workflow for frontend build and backend synthetic regressions.

## Important incomplete items

- **Actual bulk import posting is not yet available.** Live ingestion requires row validation, duplicate handling, preview/approval, transactional imports, entity isolation, and financial/role safeguards. Do not treat a downloadable template as an enabled import.
- The compact clickable/expandable record standard has not yet been individually reviewed and implemented across every legacy module.
- The complete application-wide pagination rollout remains pending for screens that currently lack a pager.
- Browser-based UX testing on desktop, tablet and mobile remains pending.
- A power failure may still lose the most recent characters after the last local save, and recovery is limited to the same browser/device and same login credentials. Signed/final notes still require clinician review.
- Auto-correct is browser spellcheck with phrase suggestions, not autonomous rewriting of clinical diagnoses.
- Future production adoption requires security/privacy assessment, verified database backup and migration strategy, and clinician-led acceptance tests.

## Automated validation

The GitHub Actions workflow runs:
- `npm run build` for the React frontend
- `python test_v02_approved.py`
- `python test_v03_ui_finance.py`
- `python test_v04_admin_templates.py`

Review the latest workflow status at https://github.com/rdi60/RDICM/actions.

## Production-data caution

Do not commit patient data, clinical documents, database files, or environment secrets. Test development changes on a backed-up or synthetic database.
