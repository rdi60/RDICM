# Rajan Dental v0.2 – Direct estimate form hotfix

**Issue:** Selecting **New Estimate → Estimate source → Add procedure directly** caused a React render error and left the procedure-entry section blank.

**Root cause:** `EstimateEditor` referenced `queued` and `setQueued` without creating their React state. `InvoiceEditor` had the same defect and would fail when its direct-entry form opened.

**Correction:** Both editors now initialize their direct-procedure queues. The top-level tariff dropdown updates the current procedure's catalog price when the category changes. On successful save, the queue and entry form reset. Empty treatment-plan/estimate selections are rejected before submission.

**Checks:** `python frontend/tests/test_direct_estimate_regression.py` and `python backend/test_v02_approved.py` passed.

**Limit:** Live browser interaction and full Vite production build were not run in this environment. Use a test database and verify UI before deployment; no production database migration or existing patient record update is part of this hotfix.
