"""Version 0.8 financial controls and account deactivation regression (synthetic records)."""
import os, tempfile, sys
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app
 from fastapi.testclient import TestClient
 app.seed_admin('admin','VerySecureSynthetic123!')
 with TestClient(app.app) as c:
  def login(user='admin',pwd='VerySecureSynthetic123!'):
   resp=c.post('/api/login',json={'username':user,'password':pwd})
   assert resp.status_code==200,resp.text
   return {'Authorization':'Bearer '+resp.json()['token']}
  h=login()
  main,trust=[e['id'] for e in c.get('/api/entities',headers=h).json()]
  def req(method,path,body=None,status=200,headers=None):
   r=c.request(method,'/api'+path,headers=headers or h,json=body)
   assert r.status_code==status,(method,path,status,r.status_code,r.text)
   return r.json()
  reg=req('POST',f'/entities/{main}/registrations',{'name':'Synthetic Test Patient'})
  patient=req('POST',f'/entities/{main}/check-in',{'registration_id':reg['id']})['patient']
  inv=req('POST',f'/entities/{main}/invoices',{'patient_id':patient['id'],'description':'Synthetic dental service','amount':'1000.00'})
  rid=req('POST',f'/entities/{main}/receipts',{'patient_id':patient['id'],'amount':'200.00','allocations':[{'invoice_id':inv['id'],'amount':'200.00'}]})['id']
  assert req('GET',f'/entities/{main}/invoices')[0]['balance_paise']==80000
  req('POST',f'/entities/{trust}/credit-notes',{'invoice_id':inv['id'],'amount':'100','reason':'Wrong entity'},404)
  credit=req('POST',f'/entities/{main}/credit-notes',{'invoice_id':inv['id'],'amount':'500.00','reason':'Service partially cancelled'},201)
  assert credit['credit_no'].startswith('CL-CRN-') and credit['remaining_paise']==30000
  assert req('GET',f'/entities/{main}/invoices')[0]['balance_paise']==30000
  assert len(req('GET',f'/entities/{main}/credit-notes'))==1
  req('POST',f'/entities/{main}/credit-notes',{'invoice_id':inv['id'],'amount':'300.01','reason':'Excess over balance'},409)
  req('POST',f'/entities/{main}/receipts',{'patient_id':patient['id'],'amount':'300.01','allocations':[{'invoice_id':inv['id'],'amount':'300.01'}]},409)
  req('POST',f'/entities/{main}/receipts',{'patient_id':patient['id'],'amount':'300','allocations':[{'invoice_id':inv['id'],'amount':'300'}]})
  assert req('GET',f'/entities/{main}/invoices')[0]['balance_paise']==0
  req('POST',f'/entities/{main}/credit-notes',{'invoice_id':inv['id'],'amount':'1','reason':'Already fully settled'},409)
  # Reversing receipt re-opens that portion, but never changes the issued credit.
  req('POST',f'/entities/{main}/receipts/{rid}/reverse',{'reason':'Synthetic mistaken collection'},201)
  assert req('GET',f'/entities/{main}/invoices')[0]['balance_paise']==20000
  metrics=req('GET',f'/entities/{main}/dashboard')
  assert metrics['credit_notes_paise']==50000 and metrics['net_invoices_paise']==50000
  staff=req('POST',f'/entities/{main}/staff-accounts',{'username':'demo08','password':'SecureStaffDemo123!','role':'billing'})
  staffh=login('demo08','SecureStaffDemo123!')
  req('GET',f'/entities/{main}/credit-notes',headers=staffh)
  req('POST',f'/entities/{main}/credit-notes',{'invoice_id':inv['id'],'amount':'10','reason':'Unauthorized write'},403,headers=staffh)
  req('PATCH',f'/entities/{trust}/staff-accounts/{staff["id"]}/deactivate',{},404)
  req('PATCH',f'/entities/{main}/staff-accounts/{staff["id"]}/deactivate',{})
  req('GET','/me',status=401,headers=staffh)
  req('POST','/login',{'username':'demo08','password':'SecureStaffDemo123!'},401)
  req('PATCH',f'/entities/{main}/staff-accounts/{staff["id"]}/deactivate',{},409)
  req('PATCH',f'/entities/{main}/staff-accounts/1/deactivate',{},409)
  req('POST','/logout',{},headers=h)
  req('GET','/me',status=401,headers=h)
  print('PASS v0.8: unpaid credits, balanced receipt allocations, entity scope, staff deactivation, and logout')
