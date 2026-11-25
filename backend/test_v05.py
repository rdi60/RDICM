"""Synthetic isolated clinical documents integration tests."""
import os,tempfile,sys
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'testing.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'clinical_files')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app
 from fastapi.testclient import TestClient
 app.seed_admin('admin','SyntheticAdminPassword123!')
 with TestClient(app.app) as c:
  token=c.post('/api/login',json={'username':'admin','password':'SyntheticAdminPassword123!'}).json()['token']; h={'Authorization':'Bearer '+token}
  cl,tr=[x['id'] for x in c.get('/api/entities',headers=h).json()]
  reg=c.post(f'/api/entities/{cl}/registrations',headers=h,json={'name':'Synthetic Patient'}).json()['id']
  pt=c.post(f'/api/entities/{cl}/check-in',headers=h,json={'registration_id':reg}).json()['patient']['id']
  visit=c.post(f'/api/entities/{cl}/visits',headers=h,json={'patient_id':pt}).json()['id']
  pdf=b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF'
  url=f'/api/entities/{cl}/patients/{pt}/documents'
  bad=c.post(url,headers=h,data={'category':'xray'},files={'uploaded':('bad.jpg',b'not actually a picture','image/jpeg')});assert bad.status_code==415,bad.text
  bad=c.post(url,headers=h,data={'visit_id':9999},files={'uploaded':('report.pdf',pdf,'application/pdf')});assert bad.status_code==409,bad.text
  bad=c.post(url,headers=h,files={'uploaded':('virus.pdf',b'%PDF-1.4 /JavaScript test','application/pdf')});assert bad.status_code==415
  ok=c.post(url,headers=h,data={'category':'report','visit_id':visit},files={'uploaded':('report.pdf',pdf,'application/pdf')});assert ok.status_code==201,ok.text
  doc=ok.json();assert doc['size_bytes']==len(pdf)
  listed=c.get(url,headers=h);assert listed.status_code==200 and len(listed.json())==1
  downloaded=c.get(url+f'/{doc["id"]}/download',headers=h);assert downloaded.status_code==200 and downloaded.content==pdf
  assert c.get(url+f'/{doc["id"]}/download').status_code==401
  assert c.get(f'/api/entities/{tr}/patients/{pt}/documents',headers=h).status_code==404
  assert c.get(f'/api/entities/{tr}/patients/{pt}/documents/{doc["id"]}/download',headers=h).status_code==404
  reg2=c.post(f'/api/entities/{cl}/registrations',headers=h,json={'name':'Another Synthetic Patient'}).json()['id']
  pt2=c.post(f'/api/entities/{cl}/check-in',headers=h,json={'registration_id':reg2}).json()['patient']['id']
  assert c.get(f'/api/entities/{cl}/patients/{pt2}/documents/{doc["id"]}/download',headers=h).status_code==404
  assert len(c.get(f'/api/entities/{cl}/patients/{pt2}/documents',headers=h).json())==0
  print('PASS v0.5 document upload, download, access, patient isolation, entity isolation and validation')
