# Rajan Dental v0.3 – development source

## Source base
Built from `rajan_dental_v0_2_estimate_direct_entry_fix.zip` (v0.2 hotfix). The original v0.1 clinical APIs, entity isolation, clinical notes UI, and Option 2 palette remain in the source. New functionality uses additive SQLite migrations in `advanced_v02.install`.

## Changes implemented in this development package
- Procedure and pricing master: single procedure editor with category-wise prices; automatically generated internal codes; editable category names, tariff defaults, and active/inactive status; treatment categories for MIS (not printed or displayed on bills).
- Exactly one active default tariff per entity; defaults for new entities and new treatment estimate/invoice workflows.
- No visible Unit field in the new procedure, treatment plan, estimate, or invoice forms. Legacy database columns remain for backward compatibility.
- Compact single-expanded-line treatment plans, direct estimates, and invoices; each line shows procedure, doctors, quantity, per-line discount/premium, and calculated amount. Master procedures are selected from a searchable list; arbitrary procedure names are not accepted in the new direct-entry workflow.
- Direct draft estimate creation, detail viewing and editable draft lines; approved estimates are locked for modification.
- Clickable new and legacy invoice rows and read-only report API with patient, receipt allocations, credit notes, write-offs, invoice balance. Print action opens browser printing.
- Compact advance ledger/outstanding invoice rows and a category-wise MIS summary.
- Application navigation history preserves the selected patient across module changes and provides a Back action. Clinical Notes UI is unchanged.
- Added synthetic `backend/test_v03_ui_finance.py` covering default tariff isolation, procedure/category administration, direct draft estimates and invoice reporting.

## Verifications performed
- `python backend/test_v03_ui_finance.py`: PASS.
- `python backend/test_v02_approved.py`: PASS.
- TypeScript parser: `frontend/src/AdvancedUI.jsx` and `frontend/src/main.jsx` JSX parse without errors.
- Additional previous test scripts through v19 and v21, v22, v24 completed during regression exploration. Comprehensive suite was not completed: older pilot v20 caused a timeout in sequential run.

## NOT fully verified / limitations
- Full Vite/React production compilation and interactive desktop/tablet/mobile browser testing were NOT performed: npm dependencies are unavailable in this offline execution environment.
- The new compact/clickable style is applied to the principal v0.3 flows and the legacy invoice ledger, but a full audit of every historic module's clickable actions and back-navigation remains pending.
- Doctor display in the printable legacy invoice report uses the available historical data; older simple invoices may not have v2 procedure-level details.
- MIS currently shows category-wise planned and invoiced values/counts, not all requested cash-collection, doctor-performance, discounts, or date-filter reports.
- Editing/deactivating pricing and treatment categories is supported; permanently deleting unused records is NOT exposed, deliberately preserving financial history.
- Unsaved form state/scroll restoration is NOT fully guaranteed on every module, and browser history needs live browser QA.
- This is NOT production-authorized healthcare/accounting software. Verify a backup of existing data, security, multi-user controls, accounting/tax handling and browser UI before live use.

## Install / upgrade
1. Back up the existing app, database (`DENTAL_DB`) and uploaded documents (`DENTAL_DOCUMENT_ROOT`).
2. Extract into a separate test folder. Do not overwrite a production working installation in place.
3. Start backend per README and launch frontend with `npm install && npm run dev` on an internet-connected development PC.
4. Tables and columns are added at application startup. Do not roll back new databases using an older source build without a recovery plan.
5. Test first with synthetic patient and billing data.

## Git
A local Git commit and `.bundle` are shipped. The connected GitHub repository was NOT updated by this package creation, because a complete remote push of the source tree was not available from this environment. A developer can push the local commit using the bundle instructions in the accompanying delivery notes.
