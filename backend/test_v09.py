"""v0.9 synthetic tests for entity membership edits and backup verification."""
import os,sys,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app,backup_dev
 from fastapi.testclient import TestClient
 app.seed_admin('admin','VerySecureSynthetic123!')
 with TestClient(app.app) as c:
  def login(user,pw):
   r=c.post('/api/login',json={'username':user,'password':pw});assert r.status_code==200,r.text
   return {'Authorization':'Bearer '+r.json()['token']}
  admin=login('admin','VerySecureSynthetic123!')
  main,trust=[e['id'] for e in c.get('/api/entities',headers=admin).json()]
  def call(method,url,headers=admin,body=None,expected=200):
   r=c.request(method,'/api'+url,headers=headers,json=body)
   assert r.status_code==expected,(method,url,r.status_code,expected,r.text)
   return r.json()
  staff=call('POST',f'/entities/{main}/staff-accounts',body={'username':'demo09','password':'StrongStaffPassword09!','role':'reception'})
  sid=staff['id'];staffh=login('demo09','StrongStaffPassword09!')
  assert len(call('GET','/entities',staffh))==1
  call('PATCH',f'/entities/{trust}/staff-accounts/{sid}/role',body={'role':'billing'},expected=404)
  call('POST',f'/entities/{trust}/members',body={'username':'demo09','role':'viewer'})
  assert len(call('GET','/entities',staffh))==2
  call('PATCH',f'/entities/{main}/staff-accounts/{sid}/role',staffh,{'role':'admin'},403)
  call('PATCH',f'/entities/{main}/staff-accounts/{sid}/role',body={'role':'billing'})
  call('GET','/me',staffh,expected=401)
  staffh=login('demo09','StrongStaffPassword09!')
  assert [x['role'] for x in call('GET',f'/entities/{main}/staff-accounts',admin) if x['id']==sid]==['billing']
  call('DELETE',f'/entities/{main}/staff-accounts/{sid}/membership')
  call('GET','/me',staffh,expected=401)
  staffh=login('demo09','StrongStaffPassword09!')
  assert [e['id'] for e in call('GET','/entities',staffh)]==[trust]
  call('GET',f'/entities/{main}/patients',staffh,expected=403)
  call('DELETE',f'/entities/{trust}/staff-accounts/{sid}/membership',staffh,expected=403)
  call('PATCH',f'/entities/{main}/staff-accounts/1/role',body={'role':'viewer'},expected=409)
  call('DELETE',f'/entities/{main}/staff-accounts/1/membership',expected=409)
  reg=call('POST',f'/entities/{main}/registrations',body={'name':'Synthetic Patient Backup'})
  folder=backup_dev.create(Path(tmp)/'backup-output')
  assert backup_dev.verify(folder)
  manifest=folder/'manifest.json'
  assert manifest.is_file()
  dbfile=folder/'database.sqlite3'
  with open(dbfile,'ab') as f:f.write(b'tamper')
  try:backup_dev.verify(folder);raise AssertionError('Tamper undetected')
  except RuntimeError as exc:assert 'mismatch' in str(exc)
  print('PASS v0.9: entity role changes, access removal, revoked sessions, database backup integrity')
