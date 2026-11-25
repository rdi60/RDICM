# Rajan Dental v0.2 – Development release

This release builds on the approved v0.1 source. It preserves the existing SQLite database and APIs and introduces additive tables and routes; it does not import, delete, or rewrite patient records.

## Approved change requests 12–17

- **Staff:** Multi-entity role assignment, group definitions/permissions, per-entity role/group checkbox-dropdown selectors, and session revocation after reassignment. The new Super Admin Staff Access screen can create a staff user with multiple assignments.
- **Treatment:** Stage-wise treatment plans, editable procedure rows, procedure-vs-stage billing modes, multi-selection to create an estimate or draft invoice.
- **Procedure & pricing master:** Entity-specific procedure codes and category tariffs (Regular, Premium, Corporate, Priority, Charity), plus new custom categories. Tariff overrides for catalog procedures are restricted to entity administrators. Line-item only Discount/Premium, using rupees or percent.
- **Estimates:** From plan selection or multiple direct procedure lines, with approval and selective invoicing via the Billing screen.
- **Invoices:** Create from treatment plans, approved estimate lines or multiple direct lines. Draft invoice lines can be edited. Issued invoice financial lines are locked; use existing credit notes or approved write-offs for corrections.
- **Financial adjustments:** Write-offs and advance refunds on top of existing credit notes and receipt-reversal workflows.
- **Advances:** Collect without an invoice; allocate to later invoices; see per-patient balance and ledger; Super Admin can transfer funds between two separately verified patients in different entities. Transfer does not merge patient identities. Incoming transfers are excluded from cash-collection KPI.
- **Patient Dashboard:** Clickable Amount to Collect and Available Advance cards. Both belong strictly to the selected patient and entity; draft invoices are excluded from amount to collect.

## What is implemented, and limitations

All backend API operations described above are implemented and covered by a synthetic integration test. Existing APIs and data relationships remain available. Entity-specific roles are enforced through membership-role union, and role/assignment changes revoke the user's sessions. Group definitions/permissions and group membership are persisted, but the complete per-permission authorization matrix for *legacy endpoints* has **not** been migrated; do not assume group permissions are enforced uniformly throughout the old application.

Direct estimates/invoices can contain multiple procedure lines, but a full nested **stage editor for direct-only items** remains to be completed (for that structure use a Treatment Plan). Complete invoice tax/legal formatting, bank-integrated refunds, production accounting reconciliation, and hardening remain pending. SQLite is still the operational backend; PostgreSQL remains a pilot, not production.

Frontend JSX source parsing passes, but a full Vite build/browser acceptance test has not been completed in this environment because the npm dependencies were unavailable. This is not suitable for real patient data.

## Upgrade on a Windows local test PC

1. **Stop both backend and frontend.** Back up the entire existing application and its `backend/development.db`, `private_documents` folder, and environment variables.
2. Extract the new release to a **separate directory**; do not overwrite the running installation.
3. When ready to test your existing synthetic dataset, copy your backed-up `development.db` and private documents to the equivalent locations in the new directory. Keep originals intact.
4. From `backend`, activate the virtual environment, install `requirements.txt` if necessary, and run `python -m uvicorn app:app --reload --port 8000`. The additive schema creates new v0.2 tables on first startup.
5. From `frontend`, run `npm install`, then `npm run dev`; open http://localhost:5173.
6. First visit **Procedure & Pricing** (Super Admin), set prices, then create a stage-wise plan from a patient dashboard. Verify estimate and invoice flows using fictional patients.
7. Test `backend/test_v02_approved.py` using Python. For legacy regressions, run `backend/test_*.py` in isolation (each script uses its own fixture).

## Safe GitHub publishing

The `.gitignore` excludes local development databases, uploaded documents, secrets, virtual environments and Node packages. Review `git status` before every push. Use the accompanying Git bundle (or the source ZIP) for the first upload to the linked `rdi60/RDICM` repository, which was empty when checked. This response does not assert that GitHub has received a push.

### From the Git bundle

```powershell
# Adapt file names/paths on your PC.
git clone C:\Downloads\rajan_dental_v0_2.bundle C:\RajanDentalSource
cd C:\RajanDentalSource
git remote set-url origin https://github.com/rdi60/RDICM.git
git push -u origin main
```

After the first upload, use `git pull` to retrieve committed updates.
