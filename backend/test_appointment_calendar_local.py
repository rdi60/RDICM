"""Synthetic appointment contact, blocked period and MIS reschedule regression."""
import os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as td:
 os.environ['DENTAL_DB']=str(Path(td)/'test.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(td)/'docs')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 app.seed_admin('admin','SyntheticValidationPassword123!')
 with TestClient(app.app) as c:
  login=c.post('/api/login',json={'username':'admin','password':'SyntheticValidationPassword123!'})
  auth={'Authorization':'Bearer '+login.json()['token']}
  def req(method,p,data=None):return c.request(method,'/api'+p,json=data,headers=auth)
  eid=req('GET','/entities').json()[0]['id']
  did=req('POST',f'/entities/{eid}/doctors',{'name':'Dr. Example'}).json()['id']
  reg=req('POST',f'/entities/{eid}/registrations',{'name':'Synthetic Patient','phone':'9000000000','dob':'1990-06-15'})
  pid=req('POST',f'/entities/{eid}/check-in',{'registration_id':reg.json()['id']}).json()['patient']['id']
  start='2026-12-02T04:00:00+00:00';end='2026-12-02T04:30:00+00:00'
  a=req('POST',f'/entities/{eid}/appointments',{'patient_id':pid,'doctor_id':did,'start_time':start,'end_time':end,'reason':'Consultation'})
  assert a.status_code==200,a.text
  aid=a.json()['id']
  row=next(x for x in req('GET',f'/entities/{eid}/appointments').json() if x['id']==aid)
  assert row['patient_phone']=='9000000000' and row['patient_uhid'] and row['patient_dob']=='1990-06-15'
  assert req('POST',f'/entities/{eid}/appointments/{aid}/reschedule',{'doctor_id':did,'start_time':'2026-12-02T05:30:00+00:00','end_time':'2026-12-02T06:00:00+00:00','reason':''}).status_code==422
  leave=req('POST',f'/entities/{eid}/doctor-time-off',{'doctor_id':did,'start_time':'2026-12-02T06:00:00+00:00','end_time':'2026-12-02T08:00:00+00:00','reason':'Conference'})
  assert leave.status_code==200,leave.text
  assert req('POST',f'/entities/{eid}/appointments/{aid}/reschedule',{'doctor_id':did,'start_time':'2026-12-02T06:30:00+00:00','end_time':'2026-12-02T07:00:00+00:00','reason':'Patient request'}).status_code==409
  result=req('POST',f'/entities/{eid}/appointments/{aid}/reschedule',{'doctor_id':did,'start_time':'2026-12-02T08:30:00+00:00','end_time':'2026-12-02T09:00:00+00:00','reason':'Patient request'})
  assert result.status_code==200,result.text
  history=req('GET',f'/entities/{eid}/mis/appointment-reschedules')
  assert history.status_code==200 and len(history.json())==1 and history.json()[0]['reason']=='Patient request'
  print('PASS patient contact fields, blocked rescheduling and MIS history')
