"""V2.4 regression: entity flags, auditable note editing, safe preview, permissions."""
import os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as td:
 os.environ['DENTAL_DB']=str(Path(td)/'clinic.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(td)/'docs')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 app.seed_admin('admin','V24SyntheticTestPassword!')
 with TestClient(app.app) as client:
  login=client.post('/api/login',json={'username':'admin','password':'V24SyntheticTestPassword!'});assert login.status_code==200,login.text
  h={'Authorization':'Bearer '+login.json()['token']}
  ids=[e['id'] for e in client.get('/api/entities',headers=h).json()]
  a,b=ids[:2]
  get=lambda e:client.get(f'/api/entities/{e}/features',headers=h)
  assert get(a).json()=={'chair_ot_enabled':False}
  assert get(b).json()=={'chair_ot_enabled':False}
  assert client.put(f'/api/entities/{a}/features',headers=h,json={'chair_ot_enabled':True}).json()['chair_ot_enabled'] is True
  assert get(a).json()['chair_ot_enabled'] is True
  assert get(b).json()['chair_ot_enabled'] is False
  r=client.post(f'/api/entities/{a}/registrations',headers=h,json={'name':'Synthetic V24 Patient'});assert r.status_code==200,r.text
  pid=client.post(f'/api/entities/{a}/check-in',headers=h,json={'registration_id':r.json()['id']}).json()['patient']['id']
  vid=client.post(f'/api/entities/{a}/visits',headers=h,json={'patient_id':pid}).json()['id']
  doctor=client.post(f'/api/entities/{a}/doctors',headers=h,json={'name':'Dr Synthetic'})
  assert doctor.status_code==200,doctor.text
  did=doctor.json()['id']
  url=f'/api/entities/{a}/clinical-notes'
  r=client.post(url+'/v24',headers=h,json={'patient_id':pid,'visit_id':vid,'body':'Original examination note','doctor_id':did,'save_method':'auto'})
  assert r.status_code==201,r.text
  nid=r.json()['id'];assert r.json()['version']==1
  r=client.put(f'{url}/{nid}/content',headers=h,json={'body':'Revised examination note','doctor_id':did,'expected_version':1,'save_method':'auto'})
  assert r.status_code==200,r.text
  assert r.json()['version']==2
  conflict=client.put(f'{url}/{nid}/content',headers=h,json={'body':'Stale revision','doctor_id':did,'expected_version':1,'save_method':'edit'})
  assert conflict.status_code==409,conflict.text
  revision=client.get(f'{url}/{nid}/revisions',headers=h)
  assert revision.status_code==200 and len(revision.json())==2
  assert revision.json()[0]['previous_body']=='Original examination note'
  items=client.get(url,headers=h,params={'patient_id':pid}).json()
  assert items[0]['current_body']=='Revised examination note'
  assert items[0]['doctor_name']=='Dr Synthetic'
  assert items[0]['version']==2
  # Protect signed original while still allowing auditable correction in effective display.
  assert client.post(f'{url}/{nid}/sign',headers=h).status_code==200
  r=client.put(f'{url}/{nid}/content',headers=h,json={'body':'Later correction','doctor_id':did,'expected_version':2,'save_method':'edit'})
  assert r.status_code==200,r.text
  with app.db() as c:
   row=app.one(c,'SELECT body,status FROM clinical_notes WHERE entity_id=? AND id=?',(a,nid))
   assert row['body']=='Revised examination note' and row['status']=='signed'
   rev=app.rows(c,'SELECT body,previous_body FROM clinical_note_revisions WHERE entity_id=? AND note_id=? ORDER BY version',(a,nid))
   assert len(rev)==3 and rev[-1]['previous_body']=='Revised examination note'
  # Authenticated image/PDF previews are inline, entity- and patient-scoped.
  import base64
  png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8jAAAAABJRU5ErkJggg==')
  result=client.post(f'/api/entities/{a}/patients/{pid}/documents',headers=h,
                     data={'category':'xray'},files={'uploaded':('synthetic.png',png,'image/png')})
  assert result.status_code==201,result.text
  doc=result.json()['id']
  preview=client.get(f'/api/entities/{a}/patients/{pid}/documents/{doc}/preview',headers=h)
  assert preview.status_code==200,preview.text
  assert preview.headers['content-type'].startswith('image/png')
  assert preview.content.startswith(bytes.fromhex('89504e470d0a1a0a'))
  assert client.get(f'/api/entities/{b}/patients/{pid}/documents/{doc}/preview',headers=h).status_code==404
  assert client.get(f'/api/entities/{a}/patients/{pid}/documents/{doc}/preview').status_code==401
  # Wrong entity cannot see a note; no clinical write from reception.
  assert client.get(f'/api/entities/{b}/clinical-notes/{nid}/revisions',headers=h).status_code==404
  assert client.put(f'/api/entities/{b}/features',headers=h,json={'chair_ot_enabled':False}).status_code==200
  assert client.post(f'/api/entities/{b}/clinical-notes/v24',headers=h,json={'patient_id':pid,'visit_id':vid,'body':'Wrong entity'}).status_code in (404,409)
  staff=client.post(f'/api/entities/{a}/staff-accounts',headers=h,json={'username':'v24reception','password':'V24ReceptionPassword!','role':'reception'})
  assert staff.status_code==200,staff.text
  rh={'Authorization':'Bearer '+client.post('/api/login',json={'username':'v24reception','password':'V24ReceptionPassword!'}).json()['token']}
  assert client.put(f'/api/entities/{a}/features',headers=rh,json={'chair_ot_enabled':False}).status_code==403
  assert client.put(f'{url}/{nid}/content',headers=rh,json={'body':'Unauthorized edit','expected_version':3}).status_code==403
  assert client.get(f'{url}/{nid}/revisions',headers=rh).status_code==403
  assert get(a).json()['chair_ot_enabled'] is True
  print('PASS V2.4: entity flags, clinical note revisions, optimistic locking, signed originals, cross-entity and role restrictions')
