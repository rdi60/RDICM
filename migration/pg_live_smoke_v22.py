"""Destructive synthetic-only PostgreSQL 16+ integration smoke test.

Requires a fresh, disposable database whose name contains 'smoke' and two DSNs:
RAJAN_PG_SMOKE_OWNER_DSN (schema owner), RAJAN_PG_SMOKE_API_DSN
(restricted, nonowner API role). Explicit opt-in RAJAN_PG_SMOKE_DISPOSABLE=YES.
Never point this test at production, staging with real records, or a shared DB.
"""
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pg_scope import scoped_cursor
from pg_patient_pilot import create_registration, check_in, create_visit, list_patients, PilotError
from pg_appointments_pilot import create_appointment
from pg_finance_pilot import treatment, invoice, receipt, ledger


def require_environment():
    if os.environ.get('RAJAN_PG_SMOKE_DISPOSABLE') != 'YES':
        raise RuntimeError('Set RAJAN_PG_SMOKE_DISPOSABLE=YES for a disposable *synthetic-only* DB')
    owner = os.environ.get('RAJAN_PG_SMOKE_OWNER_DSN')
    api = os.environ.get('RAJAN_PG_SMOKE_API_DSN')
    if not owner or not api or owner == api:
        raise RuntimeError('Set distinct OWNER and restricted API DSNs')
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError('Install migration/requirements-pg-optional.txt first') from exc
    for dsn in (owner, api):
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute('SELECT current_database(), current_user')
            database, role = cur.fetchone()
            if 'smoke' not in database.lower():
                raise RuntimeError('Database name must contain smoke, not a production name')
            if dsn == api:
                cur.execute('SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user')
                a, b = cur.fetchone()
                if a or b:
                    raise RuntimeError('API role must not have SUPERUSER or BYPASSRLS')
    with psycopg.connect(owner) as conn, conn.cursor() as cur:
        cur.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='rajan_pilot')")
        if cur.fetchone()[0]:
            raise RuntimeError('Test refuses pre-existing rajan_pilot schema; use a new disposable database')
    return psycopg, sql, owner, api


def provision(psycopg, sql, owner, api):
    with psycopg.connect(api) as conn, conn.cursor() as cur:
        cur.execute('SELECT current_user')
        api_role = cur.fetchone()[0]
    ddl = (HERE/'pg_patient_pilot.sql').read_text(encoding='utf-8')
    with psycopg.connect(owner) as conn, conn.cursor() as cur:
        cur.execute(ddl)
        cur.execute(sql.SQL('GRANT USAGE ON SCHEMA rajan_pilot TO {}').format(sql.Identifier(api_role)))
        for tables, privileges in (
            ('entities', 'SELECT'),
            ('counters', 'SELECT, INSERT, UPDATE'),
            ('registrations', 'SELECT, INSERT, UPDATE'),
            ('patients', 'SELECT, INSERT'),
            ('visits', 'SELECT, INSERT'),
            ('doctors, rajan_pilot.resources, rajan_pilot.doctor_hours', 'SELECT'),
            ('appointments', 'SELECT, INSERT, UPDATE(status)'),
            ('treatments, rajan_pilot.invoices, rajan_pilot.invoice_items, rajan_pilot.receipts, rajan_pilot.receipt_allocations', 'SELECT, INSERT'),
        ):
            cur.execute(sql.SQL('GRANT '+privileges+' ON rajan_pilot.'+tables+' TO {}').format(sql.Identifier(api_role)))
        cur.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rajan_pilot TO {}').format(sql.Identifier(api_role)))
        # In a real deployment, entity and resource provisioning is trusted admin functionality.
        for eid,code in [(99101,'SMOKEA'),(99102,'SMOKEB')]:
            cur.execute('INSERT INTO rajan_pilot.entities(id,code) VALUES(%s,%s)',(eid,code))
            cur.execute("SELECT set_config('app.entity_id',%s,true)",(str(eid),))
            cur.execute('INSERT INTO rajan_pilot.doctors(entity_id,display_name) VALUES(%s,%s) RETURNING id',(eid,'Synthetic Dentist'))
            doctor=cur.fetchone()[0]
            cur.execute("INSERT INTO rajan_pilot.resources(entity_id,label,kind) VALUES(%s,'Synthetic Chair','CHAIR') RETURNING id",(eid,))
            chair=cur.fetchone()[0]
            for day in range(7):
                cur.execute("INSERT INTO rajan_pilot.doctor_hours(entity_id,doctor_id,weekday,opens,closes) VALUES(%s,%s,%s,'08:00','20:00')",(eid,doctor,day))
            if eid==99101: ids=(doctor,chair)
        return ids


def run():
    psycopg,sql,owner,api=require_environment()
    doctor,chair=provision(psycopg,sql,owner,api)
    def scope(entity_id,read_only=False):
        return scoped_cursor(entity_id,dsn=api,read_only=read_only)
    a=create_registration(99101,'SMOKEA','Synthetic Patient A',scope=scope)
    b=create_registration(99102,'SMOKEB','Synthetic Patient B',scope=scope)
    pa=check_in(99101,'SMOKEA',a['id'],scope=scope)['patient']
    pb=check_in(99102,'SMOKEB',b['id'],scope=scope)['patient']
    assert pa['uhid'].startswith('SMOKEA-') and pb['uhid'].startswith('SMOKEB-')
    assert check_in(99101,'SMOKEA',a['id'],scope=scope)['patient']['id']==pa['id']
    assert len(list_patients(99101,'SMOKEA','Synthetic',scope=scope)['patients'])==1
    try: create_visit(99102,'SMOKEB',pa['id'],'cross entity',scope=scope)
    except PilotError: pass
    else: raise AssertionError('Cross-entity visit was allowed')
    visit=create_visit(99101,'SMOKEA',pa['id'],'Synthetic pain',scope=scope)
    day=(datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=5)).date()
    when=f'{day}T10:00'
    apt=create_appointment(99101,'SMOKEA',pa['id'],doctor,chair,when,scope=scope)
    try: create_appointment(99101,'SMOKEA',pa['id'],doctor,chair,when,scope=scope)
    except psycopg.errors.ExclusionViolation: pass
    else: raise AssertionError('Double booked doctor/chair')
    tr=treatment(99101,'SMOKEA',pa['id'],visit['id'],doctor,'Synthetic dental procedure',16,scope=scope)
    inv=invoice(99101,'SMOKEA',pa['id'],[{'treatment_id':tr['id'],'amount':'3000.00'}],scope=scope)
    alloc=[{'invoice_id':inv['id'],'amount':'1200.00'}]
    key='smoke-'+uuid.uuid4().hex
    r1=receipt(99101,'SMOKEA',pa['id'],'1200.00',alloc,'UPI','SYNTHETIC',scope=scope,idempotency_key=key)
    r2=receipt(99101,'SMOKEA',pa['id'],'1200.00',alloc,'UPI','SYNTHETIC',scope=scope,idempotency_key=key)
    assert r1['id']==r2['id'] and r2['replayed']
    assert Decimal(ledger(99101,'SMOKEA',pa['id'],scope=scope)['invoices'][0]['balance'])==Decimal('1800.00')
    try: receipt(99101,'SMOKEA',pa['id'],'1900.00',[{'invoice_id':inv['id'],'amount':'1900.00'}],scope=scope,idempotency_key='smoke-'+uuid.uuid4().hex)
    except PilotError: pass
    else: raise AssertionError('Overpayment allowed')
    # Concurrent retries: exactly one receipt must be inserted for this request key.
    key2='smoke-'+uuid.uuid4().hex
    def same_payment(_):
        return receipt(99101,'SMOKEA',pa['id'],'100.00',[{'invoice_id':inv['id'],'amount':'100.00'}],
                       'CASH','SYNTHETIC',scope=scope,idempotency_key=key2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        both=list(pool.map(same_payment,range(2)))
    assert both[0]['id']==both[1]['id']
    # Row-level security must fail closed when entity context is absent or wrong.
    with psycopg.connect(api) as conn, conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM rajan_pilot.patients')
        assert cur.fetchone()[0]==0, 'RLS exposed patients without transaction scope'
        cur.execute("SELECT set_config('app.entity_id','99102',true)")
        cur.execute('SELECT count(*) FROM rajan_pilot.patients WHERE id=%s',(pa['id'],))
        assert cur.fetchone()[0]==0, 'RLS exposed a patient from another entity'
    print('PASS live PostgreSQL v2.2: registration, check-in, visits, entity RLS, appointment exclusion, treatment, invoice, receipt, concurrent idempotency, ledger')


if __name__=='__main__':
    try:run()
    except Exception as err:
        print('FAIL live PostgreSQL v2.2:',type(err).__name__,str(err),file=sys.stderr)
        sys.exit(1)
