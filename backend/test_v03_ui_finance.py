"""Synthetic regression for v0.3 pricing master and default category controls."""
import os,tempfile,sys
from pathlib import Path
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'v03.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).parent))
 import app
 app.seed_admin('admin','SyntheticV03Password123!')
 with TestClient(app.app) as client:
  token=client.post('/api/login',json={'username':'admin','password':'SyntheticV03Password123!'}).json()['token']
  h={'Authorization':'Bearer '+token}
  def req(method,path,data=None,expect=200):
   r=client.request(method,'/api'+path,json=data,headers=h)
   assert r.status_code==expect,(method,path,r.status_code,r.text)
   return r.json()
  a,b=[x['id'] for x in req('GET','/entities')][:2]
  cats=req('GET',f'/entities/{a}/v2/pricing-categories');assert sum(x['is_default'] for x in cats)==1
  regular=next(x for x in cats if x['code']=='regular');premium=next(x for x in cats if x['code']=='premium')
  assert regular['is_default']==1
  req('PUT',f'/entities/{a}/v3/pricing-categories/{premium["id"]}/default',{})
  cats=req('GET',f'/entities/{a}/v2/pricing-categories');assert next(x for x in cats if x['is_default'])['id']==premium['id']
  req('PUT',f'/entities/{a}/v3/pricing-categories/{premium["id"]}',{'name':'Premium Updated','active':False},409)
  req('PUT',f'/entities/{a}/v3/pricing-categories/{regular["id"]}/default',{})
  req('PUT',f'/entities/{a}/v3/pricing-categories/{premium["id"]}',{'name':'Premium Updated','active':False})
  spec=req('POST',f'/entities/{a}/v3/treatment-categories',{'name':'Orthodontics'})['id']
  proc=req('POST',f'/entities/{a}/v3/procedures',{'name':'Aligners','treatment_category_id':spec,'prices':{str(regular['id']):'22000.50'}})['id']
  all_proc=req('GET',f'/entities/{a}/v2/procedures')
  entry=next(x for x in all_proc if x['id']==proc)
  assert entry['code'].startswith('PRC') and entry['unit_price_paise']==2200050 and entry['treatment_category_id']==spec
  req('PUT',f'/entities/{a}/v3/procedures/{proc}',{'name':'Transparent Aligners','treatment_category_id':spec,'prices':{str(regular['id']):'20000'}})
  req('PUT',f'/entities/{b}/v3/procedures/{proc}',{'name':'Cross Entity Mutation'},404)
  req('PUT',f'/entities/{a}/v3/treatment-categories/{spec}',{'name':'Ortho','active':True})
  req('PUT',f'/entities/{a}/v3/procedures/{proc}/active?active=false',{})
  assert next(x for x in req('GET',f'/entities/{a}/v2/procedures') if x['id']==proc)['active']==0
  report=req('GET',f'/entities/{a}/v3/reports/treatment-categories')
  assert next(x for x in report if x['id']==spec)['name']=='Ortho'
  assert next(x for x in req('GET',f'/entities/{b}/v2/pricing-categories') if x['code']=='regular')['is_default']==1
  # End-to-end: direct save draft estimate, reopen and edit, then invoice report.
  pid=req('POST',f'/entities/{a}/check-in',{'registration_id':req('POST',f'/entities/{a}/registrations',{'name':'Synthetic Direct Estimate Patient'})['id']})['patient']['id']
  newproc=req('POST',f'/entities/{a}/v3/procedures',{'name':'Scaling','prices':{str(regular['id']):'1500'}})['id']
  line={'procedure_id':newproc,'description':'Scaling','category_id':regular['id'],'quantity':1,'unit_price':'1500','adjust_kind':'discount','adjust_mode':'pct','adjust_value':'10'}
  estimate=req('POST',f'/entities/{a}/v2/estimates',{'patient_id':pid,'category_id':regular['id'],'direct_lines':[line]})
  assert estimate['total_paise']==135000
  details=req('GET',f'/entities/{a}/v2/estimates/{estimate["id"]}')
  lid=details['lines'][0]['id']
  req('PUT',f'/entities/{a}/v3/estimates/{estimate["id"]}/lines/{lid}',{**line,'unit_price':'1400','adjust_kind':'none','adjust_value':'0'})
  assert req('GET',f'/entities/{a}/v2/estimates/{estimate["id"]}')['lines'][0]['net_paise']==140000
  req('POST',f'/entities/{a}/v2/estimates/{estimate["id"]}/approve',{})
  req('PUT',f'/entities/{a}/v3/estimates/{estimate["id"]}/lines/{lid}',line,409)
  invoice=req('POST',f'/entities/{a}/v2/invoices',{'patient_id':pid,'estimate_line_ids':[lid]})
  report=req('GET',f'/entities/{a}/v3/invoices/{invoice["id"]}/report')
  assert report['patient']['id']==pid and report['balance_paise']==140000 and report['lines'][0]['net_paise']==140000
  req('GET',f'/entities/{b}/v3/invoices/{invoice["id"]}/report',expect=404)
  print('PASS v0.3: default tariff entity isolation, safe category deactivation, combined procedure prices, treatment categorization and MIS query')
