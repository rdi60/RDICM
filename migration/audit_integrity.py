"""Read-only migration preflight for OFFLINE synthetic SQLite snapshots.

Exits non-zero when semantic integrity problems are found. This is a migration gate,
not a replacement for application authorization, PostgreSQL RLS or financial audit.
The output intentionally avoids patient names and other identifiers.
"""
import json
import sqlite3
import sys
from pathlib import Path

CHECKS = {
    'appointment_patient_mismatch': '''
        SELECT COUNT(*) FROM appointments a JOIN registrations r
          ON r.entity_id=a.entity_id AND r.id=a.registration_id
        WHERE a.patient_id IS NOT NULL AND r.patient_id IS NOT NULL AND a.patient_id<>r.patient_id''',
    'visit_appointment_patient_mismatch': '''
        SELECT COUNT(*) FROM visits v JOIN appointments a ON a.id=v.appointment_id AND a.entity_id=v.entity_id
        WHERE a.patient_id IS NOT NULL AND a.patient_id<>v.patient_id''',
    'treatment_session_patient_mismatch': '''
        SELECT COUNT(*) FROM treatment_sessions s
        JOIN treatments t ON t.id=s.treatment_id AND t.entity_id=s.entity_id
        JOIN visits original ON original.id=t.visit_id AND original.entity_id=t.entity_id
        JOIN visits session ON session.id=s.visit_id AND session.entity_id=s.entity_id
        WHERE original.patient_id<>session.patient_id''',
    'tooth_finding_patient_mismatch': '''
        SELECT COUNT(*) FROM tooth_findings f JOIN visits v ON v.id=f.visit_id AND v.entity_id=f.entity_id
        WHERE f.patient_id<>v.patient_id''',
    'consent_patient_mismatch': '''
        SELECT COUNT(*) FROM patient_consents co JOIN visits v ON v.id=co.visit_id AND v.entity_id=co.entity_id
        WHERE co.patient_id<>v.patient_id''',
    'document_patient_mismatch': '''
        SELECT COUNT(*) FROM patient_documents d JOIN visits v ON v.id=d.visit_id AND v.entity_id=d.entity_id
        WHERE d.patient_id<>v.patient_id''',
    'estimate_treatment_patient_mismatch': '''
        SELECT COUNT(*) FROM estimate_items ei
        JOIN estimates e ON e.id=ei.estimate_id AND e.entity_id=ei.entity_id
        JOIN treatments t ON t.id=ei.treatment_id AND t.entity_id=ei.entity_id
        JOIN visits v ON v.id=t.visit_id AND v.entity_id=t.entity_id
        WHERE e.patient_id<>v.patient_id''',
    'receipt_invoice_patient_mismatch': '''
        SELECT COUNT(*) FROM allocations a
        JOIN receipts r ON r.id=a.receipt_id AND r.entity_id=a.entity_id
        JOIN invoices i ON i.id=a.invoice_id AND i.entity_id=a.entity_id
        WHERE r.patient_id<>i.patient_id''',
    'receipt_overallocated': '''
        SELECT COUNT(*) FROM receipts r WHERE
        (SELECT COALESCE(SUM(a.amount_paise),0) FROM allocations a
         WHERE a.entity_id=r.entity_id AND a.receipt_id=r.id)>r.amount_paise''',
    'invoice_overadjusted': '''
        SELECT COUNT(*) FROM invoices i WHERE
         COALESCE((SELECT SUM(cn.amount_paise) FROM credit_notes cn WHERE cn.entity_id=i.entity_id AND cn.invoice_id=i.id),0)
         +COALESCE((SELECT SUM(a.amount_paise) FROM allocations a WHERE a.entity_id=i.entity_id AND a.invoice_id=i.id AND NOT EXISTS
            (SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=a.entity_id AND rr.receipt_id=a.receipt_id)),0)>i.total_paise''',
    'refund_exceeds_reversed_receipt': '''
        SELECT COUNT(*) FROM receipts r WHERE
        (SELECT COALESCE(SUM(f.amount_paise),0) FROM recorded_refunds f WHERE f.entity_id=r.entity_id AND f.receipt_id=r.id)>r.amount_paise''',
    'refund_without_receipt_reversal': '''
        SELECT COUNT(*) FROM recorded_refunds f WHERE NOT EXISTS(
        SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=f.entity_id AND rr.receipt_id=f.receipt_id)''',
    'duplicate_uhid_within_entity': '''
        SELECT COUNT(*) FROM (SELECT entity_id,uhid FROM patients GROUP BY entity_id,uhid HAVING COUNT(*)>1)''',
}

def check_cursor_semantics(cursor):
    """Execute all portable semantic checks on a cursor scoped to one database schema.

    Raises on any positive count or SQL error. Returns the count of passed checks.
    Reports only aggregate error counts, never patient identifiers.
    """
    problems = {}
    for name, sql in CHECKS.items():
        cursor.execute(sql)
        count = int(cursor.fetchone()[0])
        if count != 0:
            problems[name] = count
    if problems:
        raise ValueError('Semantic integrity violations: '+json.dumps(problems, sort_keys=True))
    return len(CHECKS)


def audit(dbpath):
    dbpath=Path(dbpath).resolve()
    if not dbpath.is_file(): raise ValueError('Database does not exist')
    connection=sqlite3.connect(dbpath.as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        checks={}
        integrity=connection.execute('PRAGMA integrity_check').fetchone()[0]
        checks['sqlite_integrity_errors']=0 if integrity=='ok' else 1
        checks['foreign_key_errors']=len(connection.execute('PRAGMA foreign_key_check').fetchall())
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name,query in CHECKS.items():
            # Check the tables exist. Missing expected tables are a migration blocker, not success.
            try:
                checks[name]=int(connection.execute(query).fetchone()[0])
            except sqlite3.OperationalError as exc:
                if 'no such table' in str(exc) or 'no such column' in str(exc):
                    checks[name]='SCHEMA_MISSING_OR_INCOMPATIBLE'
                else:raise
        return {'schema_tables':len(tables-{'sqlite_sequence'}),'checks':checks,
                'passed':all(value==0 for value in checks.values()),
                'warning':'Offline snapshot inspection only; no PostgreSQL or production validation performed'}
    finally:connection.close()

if __name__=='__main__':
    try:
        if len(sys.argv)!=2:raise ValueError('Usage: python migration/audit_integrity.py OFFLINE.sqlite3')
        result=audit(sys.argv[1]);print(json.dumps(result,indent=2,sort_keys=True))
        sys.exit(0 if result['passed'] else 2)
    except (ValueError,sqlite3.Error,OSError) as exc:
        print('Preflight failed:',str(exc),file=sys.stderr);sys.exit(2)
