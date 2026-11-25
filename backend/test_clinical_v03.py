"""Run with: python test_clinical_v03.py; uses a throwaway SQLite database."""
import os,tempfile,sys
from pathlib import Path
f=tempfile.NamedTemporaryFile(suffix='.sqlite',delete=False);f.close()
os.environ['DENTAL_DB']=f.name
sys.path.insert(0,str(Path(__file__).parent))
import app
from fastapi.testclient import TestClient
app.seed_admin('admin','VerySecurePassword123')
try:
 with TestClient(app.app) as client:
  login=client.post('/api/login',json={'username':'admin','password':'VerySecurePassword123'});assert login.status_code==200
  key=login.json()['token'];heads={'Authorization':'Bearer '+key}
  def request(method,endpoint,payload=None,expected=200):
   r=client.request(method,endpoint,json=payload,headers=heads)
   assert r.status_code==expected,(method,endpoint,r.status_code,r.text)
   return r.json()
  cl,tr=[e['id'] for e in request('GET','/api/entities')]
  def patient(eid,name):
   r=request('POST',f'/api/entities/{eid}/registrations',{'name':name})
   return request('POST',f'/api/entities/{eid}/check-in',{'registration_id':r['id']})['patient']['id']
  pc=patient(cl,'Clinical Demo');pt=patient(tr,'Trust Demo')
  dc=request('POST',f'/api/entities/{cl}/doctors',{'name':'Dr. Clinical'})['id']
  dt=request('POST',f'/api/entities/{tr}/doctors',{'name':'Dr. Trust'})['id']
  vc=request('POST',f'/api/entities/{cl}/visits',{'patient_id':pc,'doctor_id':dc})['id']
  vt=request('POST',f'/api/entities/{tr}/visits',{'patient_id':pt,'doctor_id':dt})['id']
  tc=request('POST',f'/api/entities/{cl}/treatments',{'visit_id':vc,'description':'RCT 16','tooth':'16','amount':'4500'})['id']
  base=f'/api/entities/{cl}'
  finding={'patient_id':pc,'visit_id':vc,'tooth_code':'16','surface':'occlusal','condition':'caries','notes':'Clinical finding'}
  request('POST',base+'/tooth-findings',finding)
  assert len(request('GET',base+f'/tooth-findings?patient_id={pc}'))==1
  request('POST',base+'/tooth-findings',{**finding,'tooth_code':'99'},422 if False else 400)
  request('POST',base+'/tooth-findings',{**finding,'visit_id':vt},409)
  request('POST',f'/api/entities/{tr}/tooth-findings',finding,404)
  assert request('GET',f'/api/entities/{tr}/tooth-findings?patient_id={pt}')==[]
  session={'treatment_id':tc,'visit_id':vc,'performed_by':dc,'performed_at':'2026-11-20T10:00:00+05:30','procedure_notes':'Canal preparation','progress':'in_progress'}
  s1=request('POST',base+'/treatment-sessions',session)
  assert s1['progress']=='in_progress'
  request('POST',base+'/treatment-sessions',{**session,'visit_id':vt},409)
  request('POST',f'/api/entities/{tr}/treatment-sessions',{**session,'performed_by':dt},404)
  request('POST',base+'/treatment-sessions',{**session,'performed_by':dt},404)
  request('POST',base+'/treatment-sessions',{**session,'progress':'completed','procedure_notes':'Obturation completed'})
  request('POST',base+'/treatment-sessions',session,409)
  summary=request('GET',base+f'/patients/{pc}/clinical-summary')
  assert len(summary['findings'])==1 and len(summary['sessions'])==2 and len(summary['treatments'])==1
  request('GET',f'/api/entities/{tr}/patients/{pc}/clinical-summary',expected=404)
  assert len(request('GET',base+f'/treatment-sessions?treatment_id={tc}'))==2
  print('PASS: FDI validation, patient/visit ownership, entity isolation, multi-session progress, completion lock, summary')
finally:
 try:os.unlink(f.name)
 except OSError:pass
