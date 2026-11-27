# Rajan Dental – New Patient Registration + Appointment Booking

**Development/testing source – fictional patient data only**

## What's new

- In **Patients → New Patient**, an optional **Book Appointment Along With Registration** checkbox reveals doctor, appointment date, available time, flexible duration and reason fields.
- Unticking the checkbox retains the original **Register Temporary Patient** workflow.
- The booking form uses doctor opening schedules, existing bookings and blocked periods to suggest times. The backend is authoritative and also checks cross-entity linked-doctor conflicts and resource conflicts.
- The API creates both the temporary registration and appointment in **one database transaction**. If the booking fails (invalid time, blocked doctor, duplicate identity, conflict), neither a new registration nor an appointment is saved.
- When the temporary patient receives a permanent UHID, the existing appointment now displays the permanent UHID without duplicating the appointment.
- Existing temporary registration editing, duplicate warnings, entity separation and MIS workflows are retained.

## Windows local setup

Requirements: Python 3.10 or newer, Node.js 20 or newer.

**Backend (PowerShell terminal 1)**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ADMIN_PASSWORD='Choose-A-Unique-Long-Test-Password!'
python bootstrap.py
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

**Frontend (PowerShell terminal 2)**

```powershell
cd frontend
npm install
npm run dev
```

Go to `http://localhost:5173`. Log in as `admin` with the password configured for a *new* test database. On an existing database, `bootstrap.py` will not reset the administrator password.

## Test checklist

1. Open **Patients → New Patient**. With the new checkbox unticked, register a fictional patient normally.
2. Register another fictional patient with **Book Appointment Along With Registration** ticked. Choose doctor, date, available time, duration and reason. Verify one appointment appears under Appointments and the temporary patient appears in Patients.
3. Attempt an overlapping booking while **Allow Multiple Appointments** is disabled. Confirm an error and verify **no orphan temporary patient** was created.
4. Try a time outside the doctor's schedule or during a doctor block. Confirm the save is rejected.
5. Enter a duplicate phone/email and verify the duplicate warning appears before the save.
6. Check in a booked temporary patient and verify the same appointment now displays the permanent UHID.
7. Verify no clinical/billing records changed unexpectedly.

## Validation and limitations

- Nine backend tests passed, including the new atomic registration/appointment regression.
- React JSX parsing passed using the TypeScript compiler's syntax parser; CSS parsing succeeded.
- **Full Vite build and live browser visual verification were not performed**, because npm package download was unavailable in the preparation environment.
- Available times in the form are suggestions based on cached records; the backend revalidates every booking and may reject a time that became unavailable.
- Booking an appointment against an existing patient with a matching phone/email still uses the existing patient workflow; the combined form creates *new temporary registrations only*.
- This is not approved for real patient data or public deployment.

## Publication

This package contains a **local Git commit**. It has **not been pushed to GitHub**; GitHub `main` remains unchanged. Explicit confirmation is required before pushing.

