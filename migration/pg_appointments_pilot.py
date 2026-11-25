"""Synthetic-only PostgreSQL scheduling pilot. Not the SQLite runtime.

Provision doctors, chairs/OTs and weekday hours with trusted SQL. Exclusion
constraints in PostgreSQL (not this Python precheck) prevent concurrent overlaps.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pg_scope import scoped_cursor
from pg_patient_pilot import check_pilot_security, _entity, _num, PilotError

IST = ZoneInfo('Asia/Kolkata')
STATUSES = ('BOOKED','CONFIRMED','CHECKED_IN','IN_TREATMENT','COMPLETED','CANCELLED','NO_SHOW')

def _positive(value, label):
    if type(value) is not int or value <= 0:
        raise PilotError(f'Invalid {label}')

def _parse_local_start(start):
    if not isinstance(start,str): raise PilotError('Invalid appointment datetime')
    try:
        parsed=datetime.strptime(start,'%Y-%m-%dT%H:%M')
    except ValueError as exc:
        raise PilotError('Use YYYY-MM-DDTHH:MM in India Standard Time') from exc
    return parsed.replace(tzinfo=IST)

def _scope_entity(cur,entity_id,code):
    check_pilot_security(cur)
    _entity(cur,entity_id,code)

def list_resources(entity_id,entity_code,scope=scoped_cursor):
    with scope(entity_id,read_only=True) as cur:
        _scope_entity(cur,entity_id,entity_code)
        cur.execute('''SELECT id,display_name FROM rajan_pilot.doctors
                       WHERE entity_id=%s AND active=TRUE ORDER BY id''',(entity_id,))
        doctors=[dict(zip(('id','name'),r)) for r in cur.fetchall()]
        cur.execute('''SELECT id,label,kind FROM rajan_pilot.resources
                       WHERE entity_id=%s AND active=TRUE ORDER BY kind,id''',(entity_id,))
        resources=[dict(zip(('id','label','kind'),r)) for r in cur.fetchall()]
        return {'doctors':doctors,'resources':resources,'mode':'postgres_pilot'}

def create_appointment(entity_id,entity_code,patient_id,doctor_id,resource_id,start_local,
                       duration_minutes=30,reason='',scope=scoped_cursor):
    for value,label in ((patient_id,'patient'),(doctor_id,'doctor'),(resource_id,'resource')):
        _positive(value,label)
    if type(duration_minutes) is not int or not 15 <= duration_minutes <= 240:
        raise PilotError('Duration must be between 15 and 240 minutes')
    if not isinstance(reason,str) or len(reason)>500:
        raise PilotError('Invalid reason')
    start=_parse_local_start(start_local)
    end=start+timedelta(minutes=duration_minutes)
    if end.date()!=start.date():
        raise PilotError('Appointments cannot cross local midnight')
    with scope(entity_id,read_only=False) as cur:
        _scope_entity(cur,entity_id,entity_code)
        cur.execute('SELECT id FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s',(entity_id,patient_id))
        if not cur.fetchone():raise PilotError('Patient does not belong to this entity')
        cur.execute('SELECT id FROM rajan_pilot.doctors WHERE entity_id=%s AND id=%s AND active=TRUE',(entity_id,doctor_id))
        if not cur.fetchone():raise PilotError('Doctor is not active in this entity')
        cur.execute('SELECT id FROM rajan_pilot.resources WHERE entity_id=%s AND id=%s AND active=TRUE',(entity_id,resource_id))
        if not cur.fetchone():raise PilotError('Chair or OT is not active in this entity')
        # PostgreSQL weekday: Python Monday=0. Hours must cover the entire session.
        cur.execute('''SELECT 1 FROM rajan_pilot.doctor_hours
                 WHERE entity_id=%s AND doctor_id=%s AND weekday=%s
                 AND opens<=%s AND closes>=%s LIMIT 1''',
                 (entity_id,doctor_id,start.weekday(),start.time().replace(tzinfo=None),end.time().replace(tzinfo=None)))
        if not cur.fetchone():raise PilotError('Appointment falls outside the doctor opening hours')
        number=_num(cur,entity_id,entity_code,'APT')
        # Exclusion constraints enforce conflicts atomically even under concurrent requests.
        cur.execute('''INSERT INTO rajan_pilot.appointments
              (entity_id,patient_id,doctor_id,resource_id,appointment_number,starts_at,ends_at,reason)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
              (entity_id,patient_id,doctor_id,resource_id,number,start.astimezone(timezone.utc),end.astimezone(timezone.utc),reason.strip()))
        return {'id':cur.fetchone()[0],'appointment_number':number,'starts_at':start.isoformat(),
                'ends_at':end.isoformat(),'status':'BOOKED','mode':'postgres_pilot'}

def list_appointments(entity_id,entity_code,day,scope=scoped_cursor):
    start=_parse_local_start(f'{day}T00:00')
    end=start+timedelta(days=1)
    with scope(entity_id,read_only=True) as cur:
        _scope_entity(cur,entity_id,entity_code)
        cur.execute('''SELECT id,appointment_number,patient_id,doctor_id,resource_id,starts_at,ends_at,status,reason
           FROM rajan_pilot.appointments WHERE entity_id=%s AND starts_at >= %s AND starts_at < %s
           ORDER BY starts_at,id LIMIT 300''',(entity_id,start.astimezone(timezone.utc),end.astimezone(timezone.utc)))
        fields=('id','appointment_number','patient_id','doctor_id','resource_id','starts_at','ends_at','status','reason')
        return {'appointments':[dict(zip(fields,r)) for r in cur.fetchall()],'mode':'postgres_pilot'}

def change_appointment_status(entity_id,entity_code,appointment_id,status,scope=scoped_cursor):
    _positive(appointment_id,'appointment')
    if status not in ('CANCELLED','NO_SHOW'):
        raise PilotError('This pilot only supports cancellation/no-show')
    with scope(entity_id,read_only=False) as cur:
        _scope_entity(cur,entity_id,entity_code)
        cur.execute('''UPDATE rajan_pilot.appointments SET status=%s
                     WHERE entity_id=%s AND id=%s AND status IN ('BOOKED','CONFIRMED')
                     RETURNING id,appointment_number,status''',(status,entity_id,appointment_id))
        row=cur.fetchone()
        if not row:raise PilotError('Appointment not found or status cannot be changed')
        return {'id':row[0],'appointment_number':row[1],'status':row[2],'mode':'postgres_pilot'}
