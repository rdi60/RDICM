# Rajan Dental v0.1 — Entire-row patient navigation

Updated frontend files: `frontend/src/main.jsx`, `frontend/src/style.css`.

- Dashboard appointments: clicking anywhere in a patient row opens their Patient Dashboard.
- Dashboard doctor schedule: clicking a schedule item opens the patient.
- Appointment table: clicking the full row opens the patient.
- Calendar day/week/month events and list view: clicking the full event opens the patient.
- Patient directory: full-row navigation is retained; orange, inline patient-name link styling was removed.
- Temporary registrations without a permanent patient ID open the Patients screen instead.
- Appointment status selectors do not trigger parent-row navigation.
- Mouse and keyboard (Enter/Space) activation, focus ring, and hover are added.

No backend, database, or API changes. Version stays v0.1.

Installation: Back up existing code, copy only `frontend/src/main.jsx` and `frontend/src/style.css` from this package, restart Vite, then hard-refresh the browser.

Verification: source checks for all affected surfaces. Full Vite/Firefox UI build is not verified in this environment.
