# Rajan Dental v0.1 – Visit Notes & Sidebar Update

- Visit creation continues to save chief complaint, diagnosis and notes in the `visits` table.
- Clinical Notes now presents these visit-level details together with standalone notes.
- Authorized doctors/admins can edit visit clinical fields; each committed edit is saved with before/after content and editor in `visit_clinical_revisions`.
- Concurrent edits are rejected using a version check; visit history stays entity-scoped.
- Sidebar label WORKSPACE removed, logo reduced and moved to the top, navigation scrolls independently and footer stays in normal flex layout.
- No existing data tables were deleted or renamed.

Development use only with synthetic patient data; clinical security/production build must still be validated.
