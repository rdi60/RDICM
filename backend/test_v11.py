"""Synthetic integration regression for MFA, refunds, and finance summary."""
import os,sys,tempfile
from pathlib import Path
from cryptography.fernet import Fernet
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite3')
 os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
 os.environ['DENTAL_MFA_FERNET_KEY']=Fernet.generate_key().decode()
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import app
 from fastapi.testclient import TestClient
 app.seed_admin('root','SafePass123456!')
 with TestClient(app.app) as client:
  def call(method,url,header=None,payload=None,status=200):
   r=client.request(method,'/api'+url,headers=header,json=payload)
   assert r.status_code==status,(method,url,r.status_code,status,r.text)
   return r.json()
  def sign_in(code=None,password='SafePass123456!',status=200):
   data=call('POST','/login',payload={'username':'root','password':password,'otp':code},status=status)
   return {'Authorization':'Bearer '+data['token']} if status==200 else None
  admin=sign_in()
  entity_ids=[x['id'] for x in call('GET','/entities',admin)]
  main,trust=entity_ids
  start=call('POST','/me/mfa/enroll',admin,{})
  secret=start['secret']
  assert len(secret)>20
  call('POST','/me/mfa/enable',admin,{'otp':'000000'},status=403)
  call('POST','/me/mfa/enable',admin,{'otp':app.totp_at(secret)})
  call('GET','/me',admin,status=401)
  sign_in(status=401)
  admin=sign_in(app.totp_at(secret))
  assert call('GET','/me/mfa',admin)['enabled'] is True
  # Reused OTP is rejected until a new time window.
  sign_in(app.totp_at(secret),status=401)
  reg=call('POST',f'/entities/{main}/registrations',admin,{'name':'Sample Patient','phone':'9000000000'})
  pat=call('POST',f'/entities/{main}/check-in',admin,{'registration_id':reg['id']})
  patient_id=pat['patient']['id']
  invoice=call('POST',f'/entities/{main}/invoices',admin,{'patient_id':patient_id,'description':'Sample treatment','amount':'1200'})
  receipt=call('POST',f'/entities/{main}/receipts',admin,{'patient_id':patient_id,'amount':'1000','method':'upi','reference':'test-123','allocations':[{'invoice_id':invoice['id'],'amount':'1000'}]})
  call('POST',f'/entities/{main}/refunds',admin,{'receipt_id':receipt['id'],'amount':'100','method':'upi','reference':'test123','reason':'Incorrect collection'},status=409)
  call('POST',f'/entities/{main}/receipts/{receipt["id"]}/reverse',admin,{'reason':'Incorrect recorded payment'},status=201)
  payload={'receipt_id':receipt['id'],'amount':'400','method':'upi','reference':'refund-abc','reason':'Correction after reversal'}
  call('POST',f'/entities/{trust}/refunds',admin,payload,status=409)
  refunded=call('POST',f'/entities/{main}/refunds',admin,payload,status=201)
  assert refunded['remaining_refundable_paise']==60000
  payload['amount']='700'
  call('POST',f'/entities/{main}/refunds',admin,payload,status=409)
  balance=call('GET',f'/entities/{main}/finance-summary',admin)
  assert balance['invoiced_paise']==120000 and balance['outstanding_paise']==120000
  assert balance['recorded_refunds_paise']==40000
  assert call('GET',f'/entities/{trust}/finance-summary',admin)['invoiced_paise']==0
  print('PASS v1.1: MFA enrollment, OTP replay blocking, refund reversal requirement, financial summary, entity isolation')
