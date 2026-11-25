# Rajan Dental — production-readiness gates

Status: **NOT READY FOR REAL PATIENT DATA**.

## Security
- [ ] PostgreSQL-native persistence + reviewed RLS; cross-entity SQL leakage tests (v1.2 adds offline migration export/parity only)
- [ ] External authentication/session review; MFA recovery, key rotation, device loss and phishing-resistant factors
- [ ] Role-specific permissions audited for every endpoint and data field (v1.2 restricts finance list reads and dashboard finance totals)
- [ ] CSRF and XSS assessment; secure HTTP-only cookies rather than browser sessionStorage bearer tokens
- [ ] Rate limiting at network/edge level; security event alerting; intrusion monitoring
- [ ] Secure secrets management and encrypted private object storage
- [ ] Immutable/signed audit ledger and application/server access logs
- [ ] Clinical file malware scanning, media processing, retention policy and access logging

## Clinical
- [ ] Clinical chart validation, terminology and patient/visit linkage review
- [ ] Signed note integrity verified at database level; addendum workflow reviewed
- [ ] Clinical consent/signatures validated for legal requirements
- [ ] Doctor-slot and shared-doctor concurrency tested with real parallel traffic

## Finance
- [ ] Tax configuration confirmed with accountant
- [ ] Tax-compliant invoice/credit note layout and numbering
- [ ] Refund settlement/provider reconciliation and evidence of actual payment
- [ ] Cashier shift close, patient advances and credits reconciliation
- [ ] Idempotency keys for receipts, invoices and refunds
- [ ] Concurrency tests and month-end ledger reconciliation

## Deployment
- [ ] `npm ci` and `npm run build` complete successfully in clean CI
- [ ] Responsive manual browser testing on desktop/tablet/mobile
- [ ] Automated E2E workflows and accessibility tests
- [ ] PostgreSQL backup+restore drills, encrypted off-site retention, tested RPO/RTO
- [ ] Staging/pilot release using synthetic data only
- [ ] Privacy/compliance review for applicable Indian healthcare and personal data requirements
- [ ] Independent security audit with critical/high issues closed
- [ ] Owner signs off documented operational release criteria


### Version 1.3 migration gate
- [x] Read-only semantic relationship audit available for offline SQLite snapshots
- [x] New SQLite allocation insert/update triggers block patient mismatch and receipt overallocation
- [x] Regression tests for migration preflight and legacy bad-data detection
- [ ] Run audit against a verified, checkpointed cutover snapshot
- [ ] Build a PostgreSQL-native persistence layer and reviewed schema
- [ ] Import and reconcile in a real PostgreSQL environment
- [ ] Test RLS with a non-bypass application role
- [ ] Complete the frontend production build and cross-device browser verification
- [ ] Conduct external security and operational readiness reviews


### Version 1.4 checkpoint
- PostgreSQL staging planner and importer added; PostgreSQL live execution is **unverified**.
- SQLite runtime is unchanged. No PostgreSQL production schema or app cutover has occurred.
- Staging schema intentionally has no production-grade RLS, CHECK constraints or runtime safeguards.
- Require independent DBA review, private PG instance and end-to-end parity/security tests before advancing.

### Version 1.5 checkpoint
- [x] Offline portable semantic checks integrated into PostgreSQL staging import.
- [x] Separate read-only PostgreSQL staging verifier compares schema, table counts, entity counts, selected financial totals, and semantic relationships.
- [x] PostgreSQL transaction-scoped entity context helper, rejecting superuser/BYPASSRLS roles (NOT wired to API).
- [x] Version 1.5 unit/regression checks with synthetic SQLite data and simulated catalog rows.
- [ ] Run staging importer and verifier against a real PostgreSQL 16+ service.
- [ ] Rewrite and integrate all FastAPI database calls for PostgreSQL; create reviewed constraints and RLS policies.
- [ ] Test role isolation, patient ownership, concurrent billing/booking, media, frontend production build, and real restore procedure.

## Version 2.2 status (2026-11-24)
- Added guarded synthetic-only `migration/pg_live_smoke_v22.py` runner for a real PostgreSQL test server; **not executed in this environment** because a PostgreSQL server and psycopg driver are not installed.
- 21 backend regression scripts passed, including offline smoke-runner guard tests.
- Frontend `npm run build` was attempted and failed because Vite is missing (`vite: not found`). Production build unverified.
- Pilot remains separate from operational SQLite workflows. PostgreSQL cutover, real data migration, complete RLS/permission review, backup restore, web/mobile/tablet UI validation and security review are outstanding.
