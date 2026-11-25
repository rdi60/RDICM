"""Development-only, PostgreSQL-backed patient registration/check-in pilot.

Runs alongside (never replaces) the SQLite API, on synthetic data only.
The calling API must authenticate and authorize the entity on the SQLite side;
PostgreSQL enforces transaction-scoped isolation independently. Entity identity
is provisioned outside this module. Do not expose for live patient operations.
"""
from pg_scope import scoped_cursor

TABLES=('counters','patients','registrations','visits','doctors','resources','doctor_hours','appointments')
SCHEMA='rajan_pilot'

class PilotError(ValueError): pass

def check_pilot_security(cur):
    cur.execute('''SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND c.relname=ANY(%s) AND c.relkind='r' ''',(SCHEMA,list(TABLES)))
    rows=cur.fetchall()
    if set(t for t,_,_ in rows)!=set(TABLES) or any(not a or not b for _,a,b in rows):
        raise PilotError('Pilot tables must ENABLE and FORCE row level security')
    cur.execute('''SELECT tablename,policyname,permissive,roles,cmd,qual,with_check
        FROM pg_policies WHERE schemaname=%s AND tablename=ANY(%s)''',(SCHEMA,list(TABLES)))
    policies=cur.fetchall()
    if len(policies)!=len(TABLES):raise PilotError('Unreviewed pilot row policies')
    for table,name,mode,roles,cmd,qual,check in policies:
        if (table not in TABLES or name!='scoped_entity' or mode!='PERMISSIVE'
            or roles!=['public'] or cmd!='ALL' or not isinstance(qual,str)
            or not isinstance(check,str) or 'app.entity_id' not in qual or 'app.entity_id' not in check
            or 'entity_id' not in qual or 'entity_id' not in check):
            raise PilotError('Unreviewed pilot row policy')
    # This preliminary metadata check is NOT proof of RLS correctness.

def _entity(cur,eid,code):
    cur.execute('SELECT code FROM rajan_pilot.entities WHERE id=%s',(eid,))
    record=cur.fetchone()
    if not record or record[0]!=code:
        raise PilotError('PostgreSQL pilot entity not provisioned or identity mismatch')

def _num(cur,eid,code,category):
    cur.execute('''INSERT INTO rajan_pilot.counters(entity_id,category,value)
        VALUES(%s,%s,1) ON CONFLICT(entity_id,category) DO UPDATE
        SET value=rajan_pilot.counters.value+1 RETURNING value''',(eid,category))
    value=cur.fetchone()[0]
    return f'{code}-{category}-{value:06d}'

def create_registration(entity_id,entity_code,name,phone='',dob=None,notes='',scope=scoped_cursor):
    if not 2<=len(name.strip())<=120:raise PilotError('Patient name length invalid')
    if len(phone)>40 or len(notes)>5000:raise PilotError('Registration fields too long')
    with scope(entity_id,read_only=False) as cur:
        check_pilot_security(cur)
        _entity(cur,entity_id,entity_code)
        temporary=_num(cur,entity_id,entity_code,'TMP')
        cur.execute('''INSERT INTO rajan_pilot.registrations
            (entity_id,temp_id,name,phone,dob,notes) VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id''',(entity_id,temporary,name.strip(),phone,dob,notes))
        return {'id':cur.fetchone()[0],'temp_id':temporary,'mode':'postgres_pilot'}

def check_in(entity_id,entity_code,registration_id,existing_patient_id=None,scope=scoped_cursor):
    if type(registration_id) is not int or registration_id<=0:raise PilotError('Invalid registration ID')
    if existing_patient_id is not None and (type(existing_patient_id) is not int or existing_patient_id<=0):
        raise PilotError('Invalid existing patient ID')
    with scope(entity_id,read_only=False) as cur:
        check_pilot_security(cur)
        _entity(cur,entity_id,entity_code)
        # Lock registration for competing check-ins; the loser reuses the UHID.
        cur.execute('''SELECT id,name,phone,dob,notes,patient_id FROM rajan_pilot.registrations
                       WHERE entity_id=%s AND id=%s FOR UPDATE''',(entity_id,registration_id))
        record=cur.fetchone()
        if not record:raise PilotError('Registration not found for this entity')
        _,name,phone,dob,notes,linked=record
        if linked:
            if existing_patient_id is not None and existing_patient_id!=linked:
                raise PilotError('Registration already linked to a different patient')
            pid=linked;reused=True
        elif existing_patient_id is not None:
            cur.execute('SELECT id FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s',(entity_id,existing_patient_id))
            if not cur.fetchone():raise PilotError('Existing patient not found in this entity')
            pid=existing_patient_id;reused=True
        else:
            uhid=_num(cur,entity_id,entity_code,'UHID')
            cur.execute('''INSERT INTO rajan_pilot.patients
              (entity_id,uhid,name,phone,dob,notes) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id''',
              (entity_id,uhid,name,phone,dob,notes))
            pid=cur.fetchone()[0];reused=False
        if not linked:
            cur.execute('UPDATE rajan_pilot.registrations SET patient_id=%s WHERE entity_id=%s AND id=%s',
                        (pid,entity_id,registration_id))
        cur.execute('SELECT id,uhid,name,phone FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s',(entity_id,pid))
        person=cur.fetchone()
        if not person:raise PilotError('Patient linkage integrity error')
        return {'patient':dict(zip(('id','uhid','name','phone'),person)),'reused':reused,
                'mode':'postgres_pilot'}

def list_patients(entity_id,entity_code,query='',scope=scoped_cursor):
    if len(query)>120:raise PilotError('Search query too long')
    with scope(entity_id,read_only=True) as cur:
        check_pilot_security(cur)
        _entity(cur,entity_id,entity_code)
        cur.execute('''SELECT id,uhid,name,phone FROM rajan_pilot.patients
            WHERE entity_id=%s AND (uhid ILIKE %s OR name ILIKE %s OR phone ILIKE %s)
            ORDER BY id DESC LIMIT 50''',(entity_id,*([f'%{query}%']*3)))
        return {'patients':[dict(zip(('id','uhid','name','phone'),r)) for r in cur.fetchall()],
                'mode':'postgres_pilot'}


def create_visit(entity_id,entity_code,patient_id,complaint='',scope=scoped_cursor):
    # The composite FK enforces same-entity patient ownership.
    if type(patient_id) is not int or patient_id<=0:raise PilotError('Invalid patient ID')
    if not isinstance(complaint,str) or len(complaint)>2000:raise PilotError('Invalid complaint')
    with scope(entity_id,read_only=False) as cur:
        check_pilot_security(cur)
        _entity(cur,entity_id,entity_code)
        cur.execute('SELECT id FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s',(entity_id,patient_id))
        if not cur.fetchone():raise PilotError('Patient not found in this entity')
        visit_id=_num(cur,entity_id,entity_code,'VIS')
        cur.execute('''INSERT INTO rajan_pilot.visits(entity_id,patient_id,visit_number,chief_complaint)
            VALUES (%s,%s,%s,%s) RETURNING id''',(entity_id,patient_id,visit_id,complaint.strip()))
        return {'id':cur.fetchone()[0],'visit_number':visit_id,'patient_id':patient_id,'mode':'postgres_pilot'}


def list_visits(entity_id,entity_code,patient_id,scope=scoped_cursor):
    if type(patient_id) is not int or patient_id<=0:raise PilotError('Invalid patient ID')
    with scope(entity_id,read_only=True) as cur:
        check_pilot_security(cur)
        _entity(cur,entity_id,entity_code)
        cur.execute('SELECT id FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s',(entity_id,patient_id))
        if not cur.fetchone():raise PilotError('Patient not found in this entity')
        cur.execute('''SELECT id,visit_number,chief_complaint,created_at FROM rajan_pilot.visits
            WHERE entity_id=%s AND patient_id=%s ORDER BY id DESC LIMIT 100''',(entity_id,patient_id))
        return {'visits':[dict(zip(('id','visit_number','chief_complaint','created_at'),r)) for r in cur.fetchall()],
                'mode':'postgres_pilot'}
