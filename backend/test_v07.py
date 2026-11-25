"""Version 0.7 regression: strict slot rules, cross-entity shared doctors, receipt reversal."""
import os,tempfile,sys
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'database.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app
 from fastapi.testclient import TestClient
 app.seed_admin('admin','VerySecureSynthetic123!')
 with TestClient(app.app) as c:
  token=c.post('/api/login',json={'username':'admin','password':'VerySecureSynthetic123!'}).json()['token']
  headers={'Authorization':'Bearer '+token}
  eid,tid=[e['id'] for e in c.get('/api/entities',headers=headers).json()]
  def request(method,path,body=None,expected=200):
   r=c.request(method,'/api'+path,headers=headers,json=body)
   assert r.status_code==expected,(method,path,r.status_code,r.text)
   return r.json()
  def setup(eid,name):
   doc=request('POST',f'/entities/{eid}/doctors',{'name':name})['id']
   reg=request('POST',f'/entities/{eid}/registrations',{'name':'Synthetic Patient'})['id']
   patient=request('POST',f'/entities/{eid}/check-in',{'registration_id':reg})['patient']['id']
   return doc,patient
  d,p=setup(eid,'Dr Shared')
  dt,pt=setup(tid,'Dr Shared Trust')
  # Enabling strict mode before any opening hours must fail.
  request('PUT',f'/entities/{eid}/doctors/{d}/booking-rules',{'enforce_slots':True},409)
  request('POST',f'/entities/{eid}/doctor-slots',{'doctor_id':d,'weekday':0,'start_time':'09:00','end_time':'12:00','slot_minutes':30})
  request('PUT',f'/entities/{eid}/doctors/{d}/booking-rules',{'enforce_slots':True})
  assert request('GET',f'/entities/{eid}/doctor-booking-rules')[0]['enforce_slots']==1
  # Monday Dec 7 2026, India time.
  def book(ent,patient,doctor,begin,end,expected=200):
   return request('POST',f'/entities/{ent}/appointments',{'patient_id':patient,'doctor_id':doctor,'start_time':begin,'end_time':end},expected)
  book(eid,p,d,'2026-12-07T08:30:00+05:30','2026-12-07T09:00:00+05:30',409)
  book(eid,p,d,'2026-12-07T09:15:00+05:30','2026-12-07T09:45:00+05:30',409)
  book(eid,p,d,'2026-12-08T09:00:00+05:30','2026-12-08T09:30:00+05:30',409)
  # Link the two independent doctor profiles, not their patients.
  link=request('POST','/clinician-links',{'profiles':[{'entity_id':eid,'doctor_id':d},{'entity_id':tid,'doctor_id':dt}]},201)
  assert link['linked_count']==2
  assert len(request('GET','/clinician-links'))==2
  book(tid,pt,dt,'2026-12-07T09:00:00+05:30','2026-12-07T09:30:00+05:30')
  book(eid,p,d,'2026-12-07T09:00:00+05:30','2026-12-07T09:30:00+05:30',409)
  book(eid,p,d,'2026-12-07T09:30:00+05:30','2026-12-07T10:00:00+05:30')
  request('POST',f'/entities/{tid}/doctor-time-off',{'doctor_id':dt,'start_time':'2026-12-07T09:45:00+05:30','end_time':'2026-12-07T10:15:00+05:30'},409)
  request('POST',f'/entities/{eid}/invoices',{'patient_id':p,'description':'Synthetic treatment','amount':'1000.00'})
  inv=request('GET',f'/entities/{eid}/invoices')[0]
  rec=request('POST',f'/entities/{eid}/receipts',{'patient_id':p,'amount':'300.00','allocations':[{'invoice_id':inv['id'],'amount':'300.00'}]})
  assert request('GET',f'/entities/{eid}/invoices')[0]['balance_paise']==70000
  request('POST',f'/entities/{tid}/receipts/{rec["id"]}/reverse',{'reason':'Wrong entity test'},404)
  request('POST',f'/entities/{eid}/receipts/{rec["id"]}/reverse',{'reason':'Incorrect payment entry'},201)
  request('POST',f'/entities/{eid}/receipts/{rec["id"]}/reverse',{'reason':'Duplicate reversal'},409)
  assert request('GET',f'/entities/{eid}/invoices')[0]['balance_paise']==100000
  assert request('GET',f'/entities/{eid}/receipts')[0]['reversed']==1
  request('POST',f'/entities/{eid}/receipts',{'patient_id':p,'amount':'1000.00','allocations':[{'invoice_id':inv['id'],'amount':'1000.00'}]})
  assert request('GET',f'/entities/{eid}/invoices')[0]['balance_paise']==0
  print('PASS v0.7 opening-hours enforcement, shared-doctor conflicts, atomic receipt reversals and isolation')
