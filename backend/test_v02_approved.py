"""Synthetic API regression for approved changes 12-17."""
import os,tempfile,sys
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'documents')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app
 app.seed_admin('admin','SyntheticBillingTest123!')
 with TestClient(app.app) as c:
  token=c.post('/api/login',json={'username':'admin','password':'SyntheticBillingTest123!'}).json()['token']
  h={'Authorization':'Bearer '+token}
  def call(method,path,payload=None,expected=200):
   r=c.request(method,'/api'+path,json=payload,headers=h)
   assert r.status_code==expected,(method,path,r.status_code,r.text)
   return r.json()
  a,b=[e['id'] for e in call('GET','/entities')][:2]
  patient=lambda e,name:call('POST',f'/entities/{e}/check-in',{'registration_id':call('POST',f'/entities/{e}/registrations',{'name':name})['id']})['patient']['id']
  p=patient(a,'Synthetic Main Patient');p2=patient(b,'Synthetic Trust Patient')
  d=call('POST',f'/entities/{a}/doctors',{'name':'Doctor Synthetic'})['id']
  cats=call('GET',f'/entities/{a}/v2/pricing-categories')
  assert len(cats)==5
  regular=next(x['id'] for x in cats if x['code']=='regular')
  corp=next(x['id'] for x in cats if x['code']=='corporate')
  proc=call('POST',f'/entities/{a}/v2/procedures',{'code':'RCT','name':'Root Canal Treatment'})['id']
  call('PUT',f'/entities/{a}/v2/procedures/{proc}/price',{'category_id':regular,'unit_price':'6000.00'})
  call('PUT',f'/entities/{a}/v2/procedures/{proc}/price',{'category_id':corp,'unit_price':'5000.00'})
  assert call('GET',f'/entities/{a}/v2/procedures')[0]['code']=='RCT'
  call('PUT',f'/entities/{b}/v2/procedures/{proc}/price',{'category_id':regular,'unit_price':'1'},404)
  plan=call('POST',f'/entities/{a}/v2/plans',{'patient_id':p})['id']
  line={'procedure_id':proc,'description':'RCT tooth 16','tooth':'16','planned_by':d,'unit':'procedure','quantity':1,'category_id':regular,'unit_price':'6000','adjust_kind':'discount','adjust_mode':'pct','adjust_value':'10','billing_mode':'package'}
  lid=call('POST',f'/entities/{a}/v2/plans/{plan}/lines',line)['id']
  assert call('GET',f'/entities/{a}/v2/plans/{plan}')['lines'][0]['net_paise']==540000
  call('POST',f'/entities/{a}/v2/plans/{plan}/lines/{lid}/stages',{'name':'Access opening','sequence':1,'amount':'0'})
  call('POST',f'/entities/{a}/v2/plans/{plan}/lines/{lid}/stages',{'name':'Invalid charge','sequence':2,'amount':'500'},409)
  est=call('POST',f'/entities/{a}/v2/estimates',{'patient_id':p,'category_id':regular,'plan_line_ids':[lid]})
  assert est['total_paise']==540000
  call('POST',f'/entities/{a}/v2/estimates/{est["id"]}/approve',{})
  estline=call('GET',f'/entities/{a}/v2/estimates/{est["id"]}')['lines'][0]['id']
  inv=call('POST',f'/entities/{a}/v2/invoices',{'patient_id':p,'category_id':regular,'estimate_line_ids':[estline]})
  assert inv['total_paise']==540000 and inv['status']=='draft'
  call('POST',f'/entities/{a}/v2/invoices',{'patient_id':p,'estimate_line_ids':[estline]},409)
  invline=call('GET',f'/entities/{a}/v2/invoices/{inv["id"]}')['lines'][0]['id']
  upd=dict(line);upd.update({'unit_price':'6500','adjust_kind':'discount','adjust_mode':'rs','adjust_value':'500'})
  edited=call('PUT',f'/entities/{a}/v2/invoices/{inv["id"]}/lines/{invline}',upd)
  assert edited['invoice_total_paise']==600000
  call('POST',f'/entities/{a}/v2/invoices/{inv["id"]}/issue',{})
  call('PUT',f'/entities/{a}/v2/invoices/{inv["id"]}/lines/{invline}',upd,409)
  adv=call('POST',f'/entities/{a}/v2/advances',{'patient_id':p,'amount':'10000','method':'upi'})
  assert adv['available_paise']==1000000
  call('POST',f'/entities/{a}/v2/advances/allocate',{'receipt_id':adv['id'],'invoice_id':inv['id'],'amount':'4000'})
  amounts=call('GET',f'/entities/{a}/v2/patients/{p}/finances')
  assert amounts['amount_to_collect_paise']==200000 and amounts['available_advance_paise']==600000
  call('POST',f'/entities/{a}/v2/writeoffs',{'invoice_id':inv['id'],'amount':'500','reason':'Management approval'})
  amounts=call('GET',f'/entities/{a}/v2/patients/{p}/finances')
  assert amounts['amount_to_collect_paise']==150000
  # Existing invoice endpoint also recognizes new write-offs.
  existing=call('GET',f'/entities/{a}/invoices')
  assert next(x['balance_paise'] for x in existing if x['id']==inv['id'])==150000
  call('POST',f'/entities/{a}/v2/advances/refund',{'receipt_id':adv['id'],'amount':'1000','method':'bank','reason':'Patient request'})
  amounts=call('GET',f'/entities/{a}/v2/patients/{p}/finances')
  assert amounts['available_advance_paise']==500000
  call('POST',f'/entities/{b}/v2/advances/allocate',{'receipt_id':adv['id'],'invoice_id':inv['id'],'amount':'100'},404)
  # Super Administrator can transfer only between verified independent patients.
  tx=call('POST','/v2/superadmin/advance-transfer',{'source_entity_id':a,'source_receipt_id':adv['id'],'dest_entity_id':b,'dest_patient_id':p2,'amount':'500','reason':'Approved inter-entity transfer'})
  assert tx['remaining_source_paise']==450000
  assert call('GET',f'/entities/{b}/v2/patients/{p2}/finances')['available_advance_paise']==50000
  # Staff multi-entity assignment and role union, session revoke.
  staff=call('POST',f'/entities/{a}/staff-accounts',{'username':'syntheticbilling','password':'SyntheticStaffPassword123!','role':'reception'})['id']
  grp=call('POST',f'/entities/{a}/v2/groups',{'name':'Finance Team','permissions':['billing.read','billing.write']})['id']
  call('PUT',f'/v2/superadmin/users/{staff}/assignments',{'entity_roles':{str(a):['reception','billing'],str(b):['viewer']},'entity_groups':{str(a):[grp],str(b):[]}})
  userkey=c.post('/api/login',json={'username':'syntheticbilling','password':'SyntheticStaffPassword123!'}).json()['token']
  uh={'Authorization':'Bearer '+userkey}
  assert c.get(f'/api/entities/{a}/invoices',headers=uh).status_code==200
  assert c.get(f'/api/entities/{b}/invoices',headers=uh).status_code==403
  call('PUT',f'/v2/superadmin/users/{staff}/assignments',{'entity_roles':{str(b):['viewer']},'entity_groups':{}})
  assert c.get(f'/api/entities/{a}/patients',headers=uh).status_code==401
  print('PASS approved v0.2: tariffs, price adjustment, treatment stages, estimates, editable draft invoice, advance/refund/transfer, write-off, roles/groups and isolation')
