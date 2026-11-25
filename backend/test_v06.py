"""Synthetic clinical signoff and entity-isolation integration checks."""
import os, tempfile, sys
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 from fastapi.testclient import TestClient
 app.seed_admin('admin','SyntheticAdminPassword123!')
 with TestClient(app.app) as c:
  h={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin','password':'SyntheticAdminPassword123!'}).json()['token']}
  cl,tr=[x['id'] for x in c.get('/api/entities',headers=h).json()]
  def create(e):
   r=c.post(f'/api/entities/{e}/registrations',headers=h,json={'name':'Test Patient'});assert r.status_code==200,r.text
   p=c.post(f'/api/entities/{e}/check-in',headers=h,json={'registration_id':r.json()['id']});assert p.status_code==200,p.text
   patient=p.json()['patient']['id']
   v=c.post(f'/api/entities/{e}/visits',headers=h,json={'patient_id':patient});assert v.status_code==200,v.text
   return patient,v.json()['id']
  pid,vid=create(cl); tp,tv=create(tr)
  url=f'/api/entities/{cl}/clinical-notes'
  assert c.post(url,headers=h,json={'patient_id':pid,'visit_id':tv,'body':'Cross-entity visit'}).status_code==409
  assert c.post(url,headers=h,json={'patient_id':tp,'visit_id':vid,'body':'Cross-entity patient'}).status_code==404
  result=c.post(url,headers=h,json={'patient_id':pid,'visit_id':vid,'body':'Original dental findings'});assert result.status_code==201,result.text
  nid=result.json()['id']; assert result.json()['status']=='draft'
  assert c.post(f'{url}/{nid}/addenda',headers=h,json={'body':'Change','reason':'Clinical review'}).status_code==409
  signed=c.post(f'{url}/{nid}/sign',headers=h);assert signed.status_code==200,signed.text
  assert c.post(f'{url}/{nid}/sign',headers=h).status_code==409
  amendment=c.post(f'{url}/{nid}/addenda',headers=h,json={'body':'Clarified finding','reason':'Follow-up review'});assert amendment.status_code==201,amendment.text
  notes=c.get(url,headers=h,params={'patient_id':pid});assert notes.status_code==200
  assert notes.json()[0]['body']=='Original dental findings'
  assert notes.json()[0]['addenda'][0]['body']=='Clarified finding'
  assert c.get(f'/api/entities/{tr}/clinical-notes',headers=h,params={'patient_id':pid}).status_code in (200,404)
  # A trust note must never appear in the clinic patient note list, even if numeric IDs overlap.
  assert len(notes.json())==1
  # Reception should not receive clinical note content.
  c.post(f'/api/entities/{cl}/staff-accounts',headers=h,json={'username':'reception6','password':'ReceptionPass123!','role':'reception'})
  rtoken=c.post('/api/login',json={'username':'reception6','password':'ReceptionPass123!'}).json()['token'];rh={'Authorization':'Bearer '+rtoken}
  assert c.get(url,headers=rh,params={'patient_id':pid}).status_code==403
  assert c.post(url,headers=rh,json={'patient_id':pid,'visit_id':vid,'body':'Not allowed'}).status_code==403
  print('PASS v0.6 clinical note creation, signing, addenda, permission and ownership checks')
