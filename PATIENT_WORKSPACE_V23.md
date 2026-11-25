# Version 2.3 – Patient workspace navigation

## What changed

The clinic-wide left navigation now shows operational and administrative areas only. Patient-specific modules are opened in a **Patient Workspace** rather than cluttering the global sidebar.

### Enter a patient's workspace

- **Dashboard:** click a registered patient's name in Today's Appointments.
- **Appointments:** click a registered patient's name in Day/Week/Month/List views or the schedule table.
- **Patients:** search by UHID, name or phone and click the patient's name.
- For an appointment booked against a **temporary registration**, check in the patient first to generate/reuse a permanent UHID. An unregistered temporary appointment does not open a permanent patient dashboard.

### Tabs inside each patient

Patient Overview, Appointments, Visits & Diagnosis, Clinical Notes, Dental Chart, Treatment Sessions, Treatment Plan, Estimates, Consents, Documents, Billing, Payments.

The patient banner displays the currently selected patient, UHID, phone, entity, number of visits and outstanding balance. The patient-menu stays visible on desktop and changes to horizontally scrollable tabs on smaller tablets/phones. Use **All Patients** to return to the directory.

All patient modules use the existing backend APIs and receive a patient-filtered data cache for the current entity. Patient selectors are initialized to the current patient and only offer that patient in the workspace. No database changes are introduced.

Administrative areas such as **Staff Accounts**, **Entities**, **Credit Notes**, **Finance Summary**, and global entity Billing remain clinic-wide rather than being nested under a patient.

## Manual acceptance checks

1. Log into Main Clinic and register + check in a synthetic patient.
2. Open Patients, search for the UHID, click the patient's name and verify the workspace header, tabs, and Overview summary.
3. Open Visits & Diagnosis and create a visit. Switch to Clinical Notes, Dental Chart, Treatment Plan, Treatment Sessions, and verify patient and visit scope.
4. Open Appointments, click the same patient's name in both calendar and appointment list; verify navigation to the **same** patient workspace.
5. Click a name in the Dashboard's appointment list and verify the correct workspace.
6. Open Estimates, Consents, Documents, Billing and Payments tabs; confirm the current patient is preselected and no other patients appear in the patient selector.
7. Switch entities: current patient workspace must close. Patients from Main Clinic must not appear within Charity Trust.
8. Test desktop (1440px), tablet (820px) and mobile (390px) widths. On tablet/mobile, the internal patient tabs must scroll horizontally.

## Caveats

- This release changes frontend navigation and patient UI context; it **does not** migrate SQLite to PostgreSQL or change server-side authorization.
- The application remains development-only; use synthetic data.
- Full Vite production build and browser E2E checks require npm dependencies on the user's machine.
