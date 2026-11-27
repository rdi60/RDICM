"""Synthetic regression for daily, weekly and monthly doctor opening windows."""
import os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 app.seed_admin('admin','SyntheticSecurePassword123!')
 with TestClient(app.app) as t:
  login=t.post('/api/login',json={'username':'admin','password':'SyntheticSecurePassword123!'})
  assert login.status_code==200,login.text
  auth={'Authorization':'Bearer '+login.json()['token']}
  def req(method,path,body=None):return t.request(method,'/api'+path,headers=auth,json=body)
  eid=req('GET','/entities').json()[0]['id']
  doctor=req('POST',f'/entities/{eid}/doctors',{'name':'Synthetic Doctor'}).json()['id']
  weekly={'doctor_id':doctor,'recurrence':'weekly','weekdays':[0,2,4],'windows':[{'start_time':'09:00','end_time':'12:00'},{'start_time':'14:00','end_time':'16:00'}]}
  r=req('POST',f'/entities/{eid}/doctor-slots/batch',weekly)
  assert r.status_code==200 and r.json()['created']==6,r.text
  assert req('POST',f'/entities/{eid}/doctor-slots/batch',{**weekly,'weekdays':[1,2]}).status_code==409
  assert len(req('GET',f'/entities/{eid}/doctor-slots').json())==6
  monthly={'doctor_id':doctor,'recurrence':'monthly','month_days':[15,31],'windows':[{'start_time':'08:00','end_time':'10:00'}]}
  r=req('POST',f'/entities/{eid}/doctor-slots/batch',monthly)
  assert r.status_code==200,r.text
  assert len(req('GET',f'/entities/{eid}/doctor-slots/monthly').json())==2
  reg=req('POST',f'/entities/{eid}/registrations',{'name':'Synthetic Patient','phone':'9000000011'})
  pid=req('POST',f'/entities/{eid}/check-in',{'registration_id':reg.json()['id']}).json()['patient']['id']
  def appt(a,b):return req('POST',f'/entities/{eid}/appointments',{'patient_id':pid,'doctor_id':doctor,'start_time':a,'end_time':b})
  assert appt('2026-12-15T08:07:00+05:30','2026-12-15T08:28:00+05:30').status_code==200
  assert appt('2026-12-16T08:00:00+05:30','2026-12-16T08:30:00+05:30').status_code==409
  print('PASS recurring monthly and weekly windows, conflicts and flexible start times')
