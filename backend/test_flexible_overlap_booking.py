"""Synthetic regression for flexible doctor booking and overlapping patients."""
import os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as td:
 os.environ['DENTAL_DB']=str(Path(td)/'synthetic.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(td)/'documents')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 app.seed_admin('admin','SecureSyntheticTestPass123!')
 with TestClient(app.app) as c:
  login=c.post('/api/login',json={'username':'admin','password':'SecureSyntheticTestPass123!'})
  assert login.status_code==200,login.text
  auth={'Authorization':'Bearer '+login.json()['token']}
  def req(method,url,data=None):return c.request(method,'/api'+url,json=data,headers=auth)
  eid=req('GET','/entities').json()[0]['id']
  doctor=req('POST',f'/entities/{eid}/doctors',{'name':'Dr. Synthetic'}).json()['id']
  patients=[]
  for i in (1,2):
   reg=req('POST',f'/entities/{eid}/registrations',{'name':f'Synthetic Patient {i}','phone':f'900000099{i}'})
   assert reg.status_code==200,reg.text
   patients.append(req('POST',f'/entities/{eid}/check-in',{'registration_id':reg.json()['id']}).json()['patient']['id'])
  schedule={'doctor_id':doctor,'recurrence':'weekly','weekdays':[4],'allow_multiple_appointments':False,'windows':[{'start_time':'09:00','end_time':'13:00'}]}
  result=req('POST',f'/entities/{eid}/doctor-slots/batch',schedule)
  assert result.status_code==200,result.text
  rule=next(x for x in req('GET',f'/entities/{eid}/doctor-booking-rules').json() if x['doctor_id']==doctor)
  assert rule['enforce_slots']==1 and rule['allow_multiple_appointments']==0
  def book(pid,start,end):return req('POST',f'/entities/{eid}/appointments',{'patient_id':pid,'doctor_id':doctor,'start_time':start,'end_time':end})
  start='2026-11-27T09:07:00+05:30';end='2026-11-27T09:24:00+05:30'
  assert book(patients[0],start,end).status_code==200
  assert book(patients[1],start,end).status_code==409
  toggle=req('PUT',f'/entities/{eid}/doctors/{doctor}/booking-rules',{'enforce_slots':True,'allow_multiple_appointments':True})
  assert toggle.status_code==200,toggle.text
  assert book(patients[1],start,end).status_code==200
  assert book(patients[1],'2026-11-27T13:02:00+05:30','2026-11-27T13:20:00+05:30').status_code==409
  block=req('POST',f'/entities/{eid}/doctor-time-off',{'doctor_id':doctor,'start_time':'2026-11-27T04:00:00+00:00','end_time':'2026-11-27T05:00:00+00:00','reason':'Conference'})
  assert block.status_code==200,block.text
  assert book(patients[1],'2026-11-27T09:35:00+05:30','2026-11-27T09:40:00+05:30').status_code==409
  print('PASS flexible durations, overlap checkbox, strict hours and blocks')
