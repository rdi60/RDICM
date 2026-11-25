"""Synthetic-only PostgreSQL scheduling checks; fake cursor, NOT a live server."""
import sys,os,tempfile
from datetime import datetime, time, timezone
from pathlib import Path
from contextlib import contextmanager
from fastapi.testclient import TestClient
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'migration'))
sys.path.insert(0,str(root/'backend'))
from test_v18 import VisitsCursor
from pg_appointments_pilot import (create_appointment,list_appointments,list_resources,
                                   change_appointment_status,PilotError)

class AppointmentCursor(VisitsCursor):
    def __init__(self):
        super().__init__();self.appts={};self.ids['apt']=0
        self.doctors={11:(1,'Doctor Clinic'),22:(2,'Doctor Trust')}
        self.resources={101:(1,'Chair 1','CHAIR'),202:(2,'Chair T','CHAIR')}
        self.hours={(1,11):[(0,time(9),time(17))],(2,22):[(0,time(9),time(17))]}
    def execute(self,sql,params=()):
        self.last=[]
        if 'SELECT id,display_name FROM rajan_pilot.doctors' in sql:
            eid,=params
            self.last=[(i,row[1]) for i,row in self.doctors.items() if row[0]==eid]
        elif 'SELECT id,label,kind FROM rajan_pilot.resources' in sql:
            eid,=params
            self.last=[(i,row[1],row[2]) for i,row in self.resources.items() if row[0]==eid]
        elif 'SELECT id FROM rajan_pilot.doctors' in sql:
            eid,doc=params
            self.last=[(doc,)] if doc in self.doctors and self.doctors[doc][0]==eid else []
        elif 'SELECT id FROM rajan_pilot.resources' in sql:
            eid,rid=params
            self.last=[(rid,)] if rid in self.resources and self.resources[rid][0]==eid else []
        elif 'SELECT 1 FROM rajan_pilot.doctor_hours' in sql:
            eid,doc,weekday,opens,closes=params
            self.last=[(1,)] if any(weekday==d and a<=opens and closes<=b for d,a,b in self.hours.get((eid,doc),[])) else []
        elif 'INSERT INTO rajan_pilot.appointments' in sql:
            eid,patient,doc,resource,num,starts,ends,reason=params
            for r in self.appts.values():
                if r[1]==eid and r[7] not in ('CANCELLED','NO_SHOW') and starts<r[6] and ends>r[5]:
                    if doc==r[3] or resource==r[4]:
                        raise RuntimeError('Would violate PostgreSQL exclusion constraint')
            self.ids['apt']+=1;rid=self.ids['apt']
            self.appts[rid]=(rid,eid,patient,doc,resource,starts,ends,'BOOKED',reason,num)
            self.last=[(rid,)]
        elif 'SELECT id,appointment_number,patient_id,doctor_id,resource_id,starts_at' in sql:
            eid,start,end=params
            self.last=[(r[0],r[9],r[2],r[3],r[4],r[5],r[6],r[7],r[8]) for r in self.appts.values()
                       if r[1]==eid and start<=r[5]<end]
        elif 'UPDATE rajan_pilot.appointments SET status=' in sql:
            status,eid,aid=params
            r=self.appts.get(aid)
            if r and r[1]==eid and r[7] in ('BOOKED','CONFIRMED'):
                self.appts[aid]=r[:7]+(status,)+r[8:]
                self.last=[(aid,r[9],status)]
        else:
            super().execute(sql,params)

cur=AppointmentCursor()
@contextmanager
def fake_scope(eid,read_only=False):
    assert type(eid) is int and eid in (1,2)
    yield cur

from pg_patient_pilot import create_registration,check_in
r=create_registration(1,'CL','Synthetic Clinic Patient',scope=fake_scope)
p=check_in(1,'CL',r['id'],scope=fake_scope)['patient']
r2=create_registration(2,'TR','Synthetic Trust Patient',scope=fake_scope)
p2=check_in(2,'TR',r2['id'],scope=fake_scope)['patient']
assert len(list_resources(1,'CL',scope=fake_scope)['doctors'])==1
appt=create_appointment(1,'CL',p['id'],11,101,'2026-11-30T09:00',30,'Consult',scope=fake_scope)
assert appt['appointment_number']=='CL-APT-000001'
assert len(list_appointments(1,'CL','2026-11-30',scope=fake_scope)['appointments'])==1
assert not list_appointments(2,'TR','2026-11-30',scope=fake_scope)['appointments']
# Test entity mismatches, missing opening hours, and unreasonable session lengths.
for args in [(1,'CL',p2['id'],11,101,'2026-11-30T10:00'),
             (1,'CL',p['id'],22,101,'2026-11-30T10:00'),
             (1,'CL',p['id'],11,202,'2026-11-30T10:00'),
             (1,'CL',p['id'],11,101,'2026-11-30T18:00')]:
    try:create_appointment(*args,scope=fake_scope)
    except PilotError:pass
    else:raise AssertionError('Allowed invalid patient/doctor/resource/hours')
for bad in (0,5,241,True):
    try:create_appointment(1,'CL',p['id'],11,101,'2026-11-30T11:00',bad,scope=fake_scope)
    except PilotError:pass
    else:raise AssertionError('Allowed invalid duration')
# Simulated overlap rejection mirrors the actual PostgreSQL exclusion constraint.
try:create_appointment(1,'CL',p['id'],11,101,'2026-11-30T09:15',30,scope=fake_scope)
except RuntimeError:pass
else:raise AssertionError('Allowed overlapping doctor or chair')
assert change_appointment_status(1,'CL',appt['id'],'CANCELLED',scope=fake_scope)['status']=='CANCELLED'
assert create_appointment(1,'CL',p['id'],11,101,'2026-11-30T09:15',30,scope=fake_scope)['id']!=appt['id']
try:change_appointment_status(2,'TR',appt['id'],'CANCELLED',scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Allowed cross-entity cancellation')
try:change_appointment_status(1,'CL',appt['id'],'COMPLETED',scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Allowed unsupported status change')

sql=(root/'migration/pg_patient_pilot.sql').read_text()
upgrade=(root/'migration/pg_patient_pilot_v19_upgrade.sql').read_text()
for schema in (sql,upgrade):
    assert 'appointment_doctor_conflict' in schema and 'appointment_resource_conflict' in schema
    assert 'EXCLUDE USING gist' in schema and 'FOREIGN KEY(entity_id,patient_id)' in schema
    assert 'doctor_hours' in schema and 'FORCE ROW LEVEL SECURITY' in schema

with tempfile.TemporaryDirectory() as td:
    os.environ['DENTAL_DB']=str(Path(td)/'synthetic.sqlite')
    import app
    app.DB=Path(os.environ['DENTAL_DB']);app.init();app.seed_admin('v19admin','SecureSyntheticPassword19!')
    client=TestClient(app.app)
    token=client.post('/api/login',json={'username':'v19admin','password':'SecureSyntheticPassword19!'}).json()['token']
    headers={'Authorization':'Bearer '+token}
    base='/api/entities/1/pg-pilot'
    assert client.get(base+'/scheduling-resources',headers=headers).status_code==503
    assert client.get(base+'/appointments',params={'day':'2026-11-30'},headers=headers).status_code==503
    assert client.get(base+'/appointments',params={'day':'2026-11-30'}).status_code==401
    data={'patient_id':1,'doctor_id':11,'resource_id':101,'start_local':'2026-11-30T09:00'}
    assert client.post(base+'/appointments',json=data,headers=headers).status_code==503
    assert client.patch(base+'/appointments/1/status',json={'status':'CANCELLED'},headers=headers).status_code==503
    assert client.post(base+'/appointments',json={**data,'duration_minutes':500},headers=headers).status_code==422
print('PASS v1.9: synthetic PostgreSQL scheduling, opening hours, entities, conflicts and fail-closed APIs')
