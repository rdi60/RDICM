# Rajan Dental v0.2 – Test report

- **24 / 24 backend regression scripts passed** in isolated Python processes, including the new `backend/test_v02_approved.py` synthetic workflow.
- New test exercises: entity pricing categories; category tariffs; item-level percentage discount and fixed amount discount; package stage charge protection; estimate approval; duplicate estimate invoice blocking; draft invoice line editing and issued invoice lock; advance receipt without invoice; advance allocation and balance; write-off and revised outstanding; advance refund; cross-entity unauthorized access; Super Admin transfer; multi-entity role assignment and session revocation.
- Previous `frontend/tests/test_patient_workspace.py`: passed (source-level checks).
- `main.jsx` and `AdvancedUI.jsx` parse with TypeScript JSX parser: passed.
- Python compilation: passed.
- Frontend production Vite build: **NOT VERIFIED** (npm dependencies unavailable).
- Live PostgreSQL: **NOT VERIFIED** (SQLite operational database).
- Full interactive browser test: **NOT VERIFIED**.
- Independent security and accounting audit: **NOT PERFORMED**.

Results are for development/synthetic data only, not clinical or production certification.
