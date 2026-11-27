"""Synthetic search and atomic multi-doctor booking checks."""
import os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'synthetic.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'documents')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 assert app.seed_admin('admin','SyntheticTesting123456')
 with TestClient(app.app) as c:
  auth={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin','password':'SyntheticTesting123456'}).json()['token']}
  def req(method,url,body=None):return c.request(method,'/api'+url,headers=auth,json=body)
  eid=req('GET','/entities').json()[0]['id']
  docs=[]
  for i in range(2):
   r=req('POST',f'/entities/{eid}/doctors',{'name':f'Dr. Example {i+1}'})
   assert r.status_code==200,r.text;docs.append(r.json()['id'])
  r=req('POST',f'/entities/{eid}/registrations',{'name':'Sample Patient','phone':'9000012121'})
  assert r.status_code==200,r.text
  registration=r.json()['id']
  for q in ('sample','900001','CL-TMP'):
   r=req('GET',f'/entities/{eid}/appointment-patient-search?q={q}')
   assert r.status_code==200,r.text
   assert r.json() and r.json()[0]['type']=='registration',r.text
  r=req('POST',f'/entities/{eid}/check-in',{'registration_id':registration})
  assert r.status_code==200,r.text; pid=r.json()['patient']['id']
  r=req('GET',f'/entities/{eid}/appointment-patient-search?q=sample')
  assert r.status_code==200 and r.json()[0]['type']=='patient',r.text
  def booking(d,start,end):return {'doctor_id':d,'start_time':f'2026-12-01T{start}:00+05:30','end_time':f'2026-12-01T{end}:00+05:30','reason':'Consultation'}
  entries=[booking(docs[0],'09:00','09:30'),booking(docs[1],'10:00','10:30')]
  r=req('POST',f'/entities/{eid}/appointments/batch',{'patient_id':pid,'appointments':entries})
  assert r.status_code==200 and r.json()['count']==2,r.text
  before=len(req('GET',f'/entities/{eid}/appointments').json())
  invalid=[booking(docs[0],'11:00','11:30'),booking(docs[1],'09:00','09:30')]
  r=req('POST',f'/entities/{eid}/appointments/batch',{'patient_id':pid,'appointments':invalid})
  assert r.status_code==409,r.text
  assert len(req('GET',f'/entities/{eid}/appointments').json())==before
  overlapping=[booking(docs[0],'14:00','14:30'),booking(docs[1],'14:15','14:45')]
  assert req('POST',f'/entities/{eid}/appointments/batch',{'patient_id':pid,'appointments':overlapping}).status_code==409
  print('PASS searchable patient, two-doctor atomic booking and conflict rollback')

