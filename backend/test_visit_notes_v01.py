"""Synthetic tests: New Visit clinical fields appear, edits retain before/after values."""
import os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as td:
 os.environ['DENTAL_DB']=str(Path(td)/'clinic.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(td)/'docs')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 app.seed_admin('admin','SyntheticVisitNotePassword!')
 with TestClient(app.app) as client:
  login=client.post('/api/login',json={'username':'admin','password':'SyntheticVisitNotePassword!'})
  assert login.status_code==200,login.text
  h={'Authorization':'Bearer '+login.json()['token']}
  a,b=[x['id'] for x in client.get('/api/entities',headers=h).json()][:2]
  r=client.post(f'/api/entities/{a}/registrations',headers=h,json={'name':'Synthetic Visit Note Patient'})
  assert r.status_code==200,r.text
  pid=client.post(f'/api/entities/{a}/check-in',headers=h,json={'registration_id':r.json()['id']}).json()['patient']['id']
  v=client.post(f'/api/entities/{a}/visits',headers=h,json={'patient_id':pid,'complaint':'Pain on chewing','diagnosis':'Dental caries','notes':'Review after 7 days'})
  assert v.status_code==200,v.text
  vid=v.json()['id']
  url=f'/api/entities/{a}/visits/{vid}/clinical-content'
  history=f'/api/entities/{a}/visits/{vid}/clinical-history'
  assert client.get(history,headers=h).json()==[]
  assert client.put(url,headers=h,json={'complaint':'Updated pain','diagnosis':'Dental caries','notes':'Follow up after 3 days','expected_version':0}).json()['version']==1
  r=client.put(url,headers=h,json={'complaint':'Stale','diagnosis':'X','notes':'X','expected_version':0})
  assert r.status_code==409,r.text
  versions=client.get(history,headers=h).json()
  assert len(versions)==1 and versions[0]['previous_complaint']=='Pain on chewing'
  assert versions[0]['previous_notes']=='Review after 7 days'
  assert versions[0]['notes']=='Follow up after 3 days'
  assert client.get(f'/api/entities/{b}/visits/{vid}/clinical-history',headers=h).status_code==404
  assert client.put(f'/api/entities/{b}/visits/{vid}/clinical-content',headers=h,json={'complaint':'Wrong','diagnosis':'Wrong','notes':'Wrong','expected_version':0}).status_code==404
  r=client.post(f'/api/entities/{a}/staff-accounts',headers=h,json={'username':'visitreception','password':'SyntheticReceptionPassword!','role':'reception'})
  assert r.status_code==200,r.text
  rh={'Authorization':'Bearer '+client.post('/api/login',json={'username':'visitreception','password':'SyntheticReceptionPassword!'}).json()['token']}
  assert client.put(url,headers=rh,json={'complaint':'Wrong','diagnosis':'Wrong','notes':'Wrong','expected_version':1}).status_code==403
  assert any(x['id']==vid and x['notes']=='Follow up after 3 days' for x in client.get(f'/api/entities/{a}/visits',headers=h).json())
  print('PASS: visit clinical details editing, revisions, optimistic locking, staff permissions and entity isolation')
