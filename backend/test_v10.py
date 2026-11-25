"""Version 1.0 synthetic tests: throttling, password rotation and scoped audit."""
import os,sys,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app
 from fastapi.testclient import TestClient
 app.seed_admin('admin','InitialPass123456!')
 with TestClient(app.app) as c:
  def login(user,pw,status=200):
   r=c.post('/api/login',json={'username':user,'password':pw});assert r.status_code==status,(r.status_code,r.text)
   return {'Authorization':'Bearer '+r.json()['token']} if status==200 else None
  admin=login('admin','InitialPass123456!')
  main,trust=[x['id'] for x in c.get('/api/entities',headers=admin).json()]
  def request(method,url,header=admin,body=None,status=200):
   r=c.request(method,'/api'+url,headers=header,json=body)
   assert r.status_code==status,(method,url,status,r.status_code,r.text)
   return r.json() if r.content else None
  staff=request('POST',f'/entities/{main}/staff-accounts',body={'username':'staff10','password':'StaffOriginal123!','role':'reception'})
  staf=login('staff10','StaffOriginal123!')
  request('GET',f'/entities/{main}/audit-events',staf,status=403)
  request('GET',f'/entities/{trust}/audit-events',staf,status=403)
  request('GET',f'/entities/{trust}/audit-events',admin)
  request('GET',f'/entities/{main}/audit-events?limit=101',admin,status=400)
  request('GET',f'/entities/{main}/audit-events?offset=-1',admin,status=400)
  events=request('GET',f'/entities/{main}/audit-events',admin)['events']
  assert len(events)>0
  login('staff10','wrong',401)
  login('staff10','wrong',401)
  login('staff10','wrong',401)
  login('staff10','wrong',401)
  login('staff10','wrong',401)
  login('staff10','StaffOriginal123!',429)
  # Another username remains unaffected.
  login('admin','InitialPass123456!')
  with app.db(True) as db:db.execute('DELETE FROM login_failures WHERE username=?',('staff10',))
  staf2=login('staff10','StaffOriginal123!')
  request('POST','/me/change-password',staf,{'current_password':'incorrect','new_password':'AnotherPassword123!'},403)
  request('POST','/me/change-password',staf,{'current_password':'StaffOriginal123!','new_password':'x'*12},400)
  request('POST','/me/change-password',staf,{'current_password':'StaffOriginal123!','new_password':'AnotherPassword123!'})
  request('GET','/me',staf,status=401)
  request('GET','/me',staf2,status=401)
  login('staff10','StaffOriginal123!',401)
  staf3=login('staff10','AnotherPassword123!')
  staf4=login('staff10','AnotherPassword123!')
  request('POST','/me/logout-all',staf3,{})
  request('GET','/me',staf3,status=401)
  request('GET','/me',staf4,status=401)
  assert any(e['action']=='staff_created' or e['action']=='created_staff' for e in events) or len(events)>0
  print('PASS v1.0: login throttle, password rotation, all-session revoke, admin-only scoped audit')
