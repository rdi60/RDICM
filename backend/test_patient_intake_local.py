"""Synthetic patient profile and duplicate check regression. No real patient data."""
import os,tempfile,sys
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'demo.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 assert app.seed_admin('admin','SyntheticTesting123456')
 with TestClient(app.app) as t:
  def request(m,url,payload=None,auth=None):
   r=t.request(m,'/api'+url,json=payload,headers=auth)
   return r
  token=request('POST','/login',{'username':'admin','password':'SyntheticTesting123456'}).json()['token']
  auth={'Authorization':'Bearer '+token}
  e=request('GET','/entities',auth=auth).json()[0]['id']
  patient={'name':'Sample One','phone':'9000000001','email':'test@example.invalid','notes':'For testing only'}
  r=request('POST',f'/entities/{e}/registrations',patient,auth);assert r.status_code==200,r.text
  temp=r.json()['id']
  duplicates=request('GET',f'/entities/{e}/patient-duplicate-check?email=test@example.invalid',auth=auth).json()['matches']
  assert len(duplicates)==1 and duplicates[0]['record_type']=='Temporary Registration'
  r=request('PUT',f'/entities/{e}/registrations/{temp}',{**patient,'name':'Sample One Corrected'},auth);assert r.status_code==200,r.text
  r=request('POST',f'/entities/{e}/check-in',{'registration_id':temp},auth);assert r.status_code==200,r.text
  pid=r.json()['patient']['id']
  assert r.json()['patient']['email']=='test@example.invalid'
  r=request('POST',f'/entities/{e}/registrations',{'name':'Another Sample','phone':'9000000001'},auth)
  assert r.status_code==409 and r.json()['detail']['code']=='POSSIBLE_DUPLICATE',r.text
  r=request('POST',f'/entities/{e}/registrations',{'name':'Another Sample','phone':'9000000001','duplicate_acknowledged':True},auth)
  assert r.status_code==200,r.text
  other=r.json()['id']
  r=request('POST',f'/entities/{e}/check-in',{'registration_id':other},auth)
  assert r.status_code==409,r.text
  r=request('POST',f'/entities/{e}/check-in',{'registration_id':other,'existing_patient_id':pid},auth)
  assert r.status_code==200 and r.json()['patient']['id']==pid,r.text
  r=request('PUT',f'/entities/{e}/patients/{pid}/profile',{**patient,'name':'Corrected Name'},auth)
  assert r.status_code==200,r.text
  stored=request('GET',f'/entities/{e}/patients',auth=auth).json()
  assert any(x['name']=='Corrected Name' and x['email']=='test@example.invalid' for x in stored)
  print('PASS patient intake: temporary editing, duplicate match, explicit override, existing UHID reuse, permanent profile')

