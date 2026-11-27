# Rajan Dental – Appointment Scheduling Local Test Release

This incremental development package is for **local testing using fictional patient data**.

## Implemented
- Compact vertical appointment list sorted by time, with UHID, age, phone, doctor, reason, time, duration
- Colour-coded status menu with matching colours for each selectable option
- Doctor and status filtering, highlighted blocked periods
- Rescheduling requires a reason, validates availability, preserves history for MIS
- Daily/weekly/monthly doctor opening-hour recurrence with a calendar-style monthly selector
- Multiple opening windows (start and end times only)
- Doctor schedule checkbox: **Allow Multiple Appointments**; off by default
- Appointment duration is freely selected per appointment, subject to the opening window
- Saving a doctor schedule turns on opening-hour enforcement; doctor blocks still prevent appointments
- Existing chair/OT restrictions and linked clinician cross-entity restrictions remain enforced

## Known limitations and precautions
- The calendar-style monthly dates repeat each month; a month preview does not create a one-time appointment block.
- Legacy doctors with no configured opening schedules remain in advisory mode until a schedule is saved.
- A separate authorized override workflow with reason has not been added.
- Doctor resignation/deactivation with reassignment has not been implemented in this package.
- The monthly calendar interface and custom colour-coded dropdown still require hands-on browser review.
- Do not use real patient data or deploy publicly without security and migration review.

## Run locally
Backend: create a Python virtual environment, install backend/requirements.txt, set ADMIN_PASSWORD, run python bootstrap.py, then uvicorn app:app --reload --host 127.0.0.1 --port 8000.
Frontend: cd frontend, npm install, npm run dev. Open http://localhost:5173.
