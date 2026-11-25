"""Version 0.4 integration checks with isolated synthetic database."""
import os,tempfile,sys
f=tempfile.NamedTemporaryFile(suffix='.sqlite',delete=False);f.close();os.environ['DENTAL_DB']=f.name
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import app
from fastapi.testclient import TestClient
app.seed_admin('admin','DevelopmentPassword2345!')
with TestClient(app.app) as c:
 key=c.post('/api/login',json={'username':'admin','password':'DevelopmentPassword2345!'}).json()['token']
 headers={'Authorization':'Bearer '+key}
 def req(method,url,data=None,status=200):
  r=c.request(method,url,json=data,headers=headers)
  assert r.status_code==status,(method,url,status,r.status_code,r.text)
  return r.json()
 entities=req('GET','/api/entities'); cl,tr=[r['id'] for r in entities]
 d=req('POST',f'/api/entities/{cl}/doctors',{'name':'Dr Synthetic'})['id']
 reg=req('POST',f'/api/entities/{cl}/registrations',{'name':'Synthetic Case'})['id']
 pt=req('POST',f'/api/entities/{cl}/check-in',{'registration_id':reg})['patient']['id']
 visit=req('POST',f'/api/entities/{cl}/visits',{'patient_id':pt,'doctor_id':d})['id']
 treatments=[req('POST',f'/api/entities/{cl}/treatments',{'visit_id':visit,'description':name,'amount':cost})['id'] for name,cost in [('Root Canal','4000'),('Crown','6000'),('Consultation','500')]]
 est=req('POST',f'/api/entities/{cl}/estimates',{'patient_id':pt,'treatment_ids':treatments})
 req('POST',f'/api/entities/{cl}/estimates/{est["id"]}/approve',{})
 items=req('GET',f'/api/entities/{cl}/estimates')[0]['items']
 first=req('POST',f'/api/entities/{cl}/estimates/{est["id"]}/invoice-selected',{'item_ids':[items[0]['id']]})
 assert first['amount_paise']==400000 and first['remaining_lines']==2
 req('POST',f'/api/entities/{cl}/estimates/{est["id"]}/invoice-selected',{'item_ids':[items[0]['id']]},409)
 req('POST',f'/api/entities/{cl}/estimates/{est["id"]}/invoice',{},409)
 req('POST',f'/api/entities/{tr}/estimates/{est["id"]}/invoice-selected',{'item_ids':[items[1]['id']]},404)
 req('POST',f'/api/entities/{cl}/estimates/{est["id"]}/invoice-selected',{'item_ids':[items[1]['id'],items[1]['id']]},400)
 remaining=req('POST',f'/api/entities/{cl}/estimates/{est["id"]}/invoice-selected',{'item_ids':[items[1]['id'],items[2]['id']]})
 assert remaining['amount_paise']==650000 and remaining['remaining_lines']==0
 final=req('GET',f'/api/entities/{cl}/estimates')[0]
 assert final['status']=='invoiced' and final['invoiced_paise']==1050000
 assert len(req('GET',f'/api/entities/{cl}/invoices'))==2
 req('POST',f'/api/entities/{tr}/consents',{'patient_id':pt,'procedure_description':'RCT','consent_version':'1','consent_text':'I acknowledge the procedure.','acknowledged_by':'Synthetic Case','acknowledged_at':'2026-11-24T12:00:00+05:30'},404)
 consent=req('POST',f'/api/entities/{cl}/consents',{'patient_id':pt,'visit_id':visit,'procedure_description':'RCT','consent_version':'v1','consent_text':'I acknowledge the proposed treatment and its risks.','acknowledged_by':'Synthetic Case','acknowledged_at':'2026-11-24T12:00:00+05:30'})
 assert len(req('GET',f'/api/entities/{cl}/consents?patient_id={pt}'))==1
 req('POST',f'/api/entities/{cl}/consents',{'patient_id':pt,'visit_id':99999,'procedure_description':'RCT','consent_version':'v1','consent_text':'I acknowledge the proposed treatment.','acknowledged_by':'Synthetic Case','acknowledged_at':'2026-11-24T12:00:00+05:30'},409)
 staff=req('POST',f'/api/entities/{cl}/staff-accounts',{'username':'reception.demo','password':'Synthetic123456!','role':'reception'})
 assert staff['role']=='reception'
 assert any(x['username']=='reception.demo' for x in req('GET',f'/api/entities/{cl}/staff-accounts'))
 assert not any(x['username']=='reception.demo' for x in req('GET',f'/api/entities/{tr}/staff-accounts'))
 req('POST',f'/api/entities/{tr}/staff-accounts',{'username':'reception.demo','password':'Synthetic123456!','role':'reception'},409)
 print('PASS v0.4: line-level invoices; duplicate protection; old converter blocked; entity isolation; consents; staff membership')
os.unlink(f.name)
