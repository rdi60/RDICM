"""Synthetic v1.2 tests: limited financial reads and validated migration export."""
import os,sys,tempfile,importlib.util
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'synthetic.sqlite3')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'documents')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app
 from fastapi.testclient import TestClient
 spec=importlib.util.spec_from_file_location('export_sqlite',str(Path(__file__).resolve().parent.parent/'migration'/'export_sqlite.py'))
 export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
 app.seed_admin('adminv12','SecureSyntheticPassword!')
 with TestClient(app.app) as c:
  def req(method,path,headers=None,payload=None,status=200):
   r=c.request(method,path,headers=headers,json=payload)
   assert r.status_code==status,(method,path,status,r.status_code,r.text)
   return r.json()
  def login(user,pw):return {'Authorization':'Bearer '+req('POST','/api/login',payload={'username':user,'password':pw})['token']}
  admin=login('adminv12','SecureSyntheticPassword!')
  cl,tr=[e['id'] for e in req('GET','/api/entities',admin)]
  for role in ('reception','doctor','billing','viewer'):
   req('POST',f'/api/entities/{cl}/staff-accounts',admin,{'username':role+'12','password':'TestPassword12345!','role':role})
  rh=login('reception12','TestPassword12345!');dh=login('doctor12','TestPassword12345!');bh=login('billing12','TestPassword12345!');vh=login('viewer12','TestPassword12345!')
  reg=req('POST',f'/api/entities/{cl}/registrations',admin,{'name':'Synthetic Subject','phone':'9000000000'})
  patient=req('POST',f'/api/entities/{cl}/check-in',admin,{'registration_id':reg['id']})['patient']
  req('POST',f'/api/entities/{cl}/invoices',admin,{'patient_id':patient['id'],'description':'Synthetic invoice','amount':'500.25'})
  for h in (rh,dh,vh):
   assert 'invoices_paise' not in req('GET',f'/api/entities/{cl}/dashboard',h)
   for suffix in ('invoices','receipts','estimates','finance-summary'):
    req('GET',f'/api/entities/{cl}/{suffix}',h,status=403)
  assert req('GET',f'/api/entities/{cl}/invoices',bh)[0]['total_paise']==50025
  assert req('GET',f'/api/entities/{tr}/invoices',bh,status=403)
  assert req('GET',f'/api/entities/{cl}/dashboard',admin)['invoices_paise']==50025
  target=Path(tmp)/'export'
  manifest=export.export(Path(os.environ['DENTAL_DB']),target)
  result=export.verify(target)
  assert result['verified_tables']==len(manifest['tables'])
  assert manifest['tables']['invoices']['money_per_entity'][str(cl)]==50025
  try:export.export(Path(os.environ['DENTAL_DB']),target);raise AssertionError('Overwriting should be blocked')
  except ValueError:pass
  with (target/'invoices.jsonl').open('a') as f:f.write('{}\n')
  try:export.verify(target);raise AssertionError('Tamper was not detected')
  except ValueError as e:assert 'Hash mismatch' in str(e)
  print('PASS v1.2: finance role scoping, entity access, export parity, tamper detection')
