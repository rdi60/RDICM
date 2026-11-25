import os,tempfile,sys
f=tempfile.NamedTemporaryFile(suffix='.sqlite',delete=False);f.close();os.environ['DENTAL_DB']=f.name
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import app
from fastapi.testclient import TestClient
app.seed_admin('admin','VerySecurePassword123')
with TestClient(app.app) as client:
 def call(method,url,p=None,token=None):
  r=client.request(method,url,json=p,headers={'Authorization':'Bearer '+(token or key)});assert r.status_code<400,(method,url,r.status_code,r.text);return r.json()
 key=client.post('/api/login',json={'username':'admin','password':'VerySecurePassword123'}).json()['token']
 entities=call('GET','/api/entities');cl,tr=[e['id'] for e in entities]
 d=call('POST',f'/api/entities/{cl}/doctors',{'name':'Dr. Test'})['id']
 slot=call('POST',f'/api/entities/{cl}/doctor-slots',{'doctor_id':d,'weekday':0,'start_time':'09:00','end_time':'12:00','slot_minutes':30})
 assert len(call('GET',f'/api/entities/{cl}/doctor-slots'))==1
 bad=client.post(f'/api/entities/{tr}/doctor-slots',json={'doctor_id':d,'weekday':0,'start_time':'09:00','end_time':'12:00','slot_minutes':30},headers={'Authorization':'Bearer '+key});assert bad.status_code==404
 reg=call('POST',f'/api/entities/{cl}/registrations',{'name':'Demo Patient'})
 patient=call('POST',f'/api/entities/{cl}/check-in',{'registration_id':reg['id']})['patient']['id']
 visit=call('POST',f'/api/entities/{cl}/visits',{'patient_id':patient,'doctor_id':d,'diagnosis':'Test'})
 t=call('POST',f'/api/entities/{cl}/treatments',{'visit_id':visit['id'],'description':'RCT','amount':'4500.00'})
 e=call('POST',f'/api/entities/{cl}/estimates',{'patient_id':patient,'treatment_ids':[t['id']]})
 assert e['total_paise']==450000
 assert client.post(f'/api/entities/{tr}/estimates',json={'patient_id':patient,'treatment_ids':[t['id']]},headers={'Authorization':'Bearer '+key}).status_code==404
 call('POST',f'/api/entities/{cl}/estimates/{e["id"]}/approve',{})
 invoice=call('POST',f'/api/entities/{cl}/estimates/{e["id"]}/invoice',{})
 assert client.post(f'/api/entities/{cl}/estimates/{e["id"]}/invoice',json={},headers={'Authorization':'Bearer '+key}).status_code==409
 call('POST',f'/api/entities/{cl}/receipts',{'patient_id':patient,'amount':'2000','allocations':[{'invoice_id':invoice['id'],'amount':'2000'}]})
 dupe=client.post(f'/api/entities/{cl}/receipts',json={'patient_id':patient,'amount':'100','allocations':[{'invoice_id':invoice['id'],'amount':'50'},{'invoice_id':invoice['id'],'amount':'50'}]},headers={'Authorization':'Bearer '+key});assert dupe.status_code==400
 ap=call('POST',f'/api/entities/{cl}/appointments',{'patient_id':patient,'doctor_id':d,'start_time':'2026-12-01T09:00:00+05:30','end_time':'2026-12-01T09:30:00+05:30'})
 call('PATCH',f'/api/entities/{cl}/appointments/{ap["id"]}/status',{'status':'confirmed'})
 assert client.post(f'/api/entities/{cl}/doctor-time-off',json={'doctor_id':d,'start_time':'2026-12-01T09:10:00+05:30','end_time':'2026-12-01T10:00:00+05:30'},headers={'Authorization':'Bearer '+key}).status_code==409
 call('POST',f'/api/entities/{cl}/doctor-time-off',{'doctor_id':d,'start_time':'2026-12-02T09:10:00+05:30','end_time':'2026-12-02T10:00:00+05:30'})
 assert client.post(f'/api/entities/{cl}/appointments',json={'patient_id':patient,'doctor_id':d,'start_time':'2026-12-02T09:15:00+05:30','end_time':'2026-12-02T09:30:00+05:30'},headers={'Authorization':'Bearer '+key}).status_code==409
 print('PASS: entity isolation, slots, estimate conversion, duplicate allocation, appointment status and doctor leave')
