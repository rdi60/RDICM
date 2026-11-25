"""v2.0 isolated PostgreSQL workflow test using a fake SQL cursor.

This is NOT a live PostgreSQL concurrency or RLS verification.
"""
import os,sys,tempfile
from pathlib import Path
from contextlib import contextmanager
from decimal import Decimal
from fastapi.testclient import TestClient
root=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(root/'migration'),str(root/'backend')]
from test_v19 import AppointmentCursor
from pg_finance_pilot import treatment,invoice,receipt,ledger,money,PilotError,VALID_TEETH

class FinancialCursor(AppointmentCursor):
    def __init__(self):
        super().__init__();self.treatments={};self.invoices={};self.items={};self.receipts={};self.allocations=[]
        self.ids.update(trt=0,inv=0,rcp=0)
    def execute(self,sql,params=()):
        self.last=[]
        if "c.relname,c.relrowsecurity,c.relforcerowsecurity" in sql and 'rajan_pilot' in params and 'treatments' in str(params):
            tables=params[1];self.last=[(x,True,True) for x in tables]
        elif 'FROM pg_policies' in sql and 'treatments' in str(params):
            self.last=[(x,'scoped_entity','PERMISSIVE',['public'],'ALL',
                        "(entity_id = current_setting('app.entity_id')::bigint)",
                        "(entity_id = current_setting('app.entity_id')::bigint)") for x in params[1]]
        elif 'SELECT id FROM rajan_pilot.visits WHERE entity_id=' in sql:
            eid,vid,pid=params
            self.last=[(vid,)] if (vid in self.visits and self.visits[vid][1]==eid and self.visits[vid][2]==pid) else []
        elif 'SELECT id FROM rajan_pilot.treatments WHERE entity_id=' in sql:
            eid,pid,tid=params
            t=self.treatments.get(tid)
            self.last=[(tid,)] if t and t['entity_id']==eid and t['patient_id']==pid and t['status']!='CANCELLED' else []
        elif 'INSERT INTO rajan_pilot.treatments' in sql:
            eid,pid,vid,num,tooth,desc,doc=params
            self.ids['trt']+=1;tid=self.ids['trt']
            self.treatments[tid]=dict(entity_id=eid,patient_id=pid,visit_id=vid,number=num,status='PLANNED')
            self.last=[(tid,)]
        elif 'INSERT INTO rajan_pilot.invoices(' in sql:
            eid,pid,num,total=params
            self.ids['inv']+=1;iid=self.ids['inv']
            self.invoices[iid]=dict(entity_id=eid,patient_id=pid,number=num,total=total)
            self.last=[(iid,)]
        elif 'INSERT INTO rajan_pilot.invoice_items' in sql:
            eid,pid,iid,tid,amount=params
            if tid in self.items:raise RuntimeError('Treatment unique constraint')
            self.items[tid]=(eid,pid,iid,amount)
        elif 'pg_advisory_xact_lock' in sql:
            self.last=[(None,)]
        elif 'SELECT id,receipt_number,amount,request_hash FROM rajan_pilot.receipts' in sql:
            eid,key=params
            self.last=[(rid,r['number'],r['amount'],r['request_hash']) for rid,r in self.receipts.items()
                       if r['entity_id']==eid and r['idempotency_key']==key]
        elif 'SELECT total FROM rajan_pilot.invoices' in sql:
            eid,pid,iid=params
            i=self.invoices.get(iid)
            self.last=[(i['total'],)] if i and (i['entity_id'],i['patient_id'])==(eid,pid) else []
        elif 'SELECT COALESCE(SUM(amount),0) FROM rajan_pilot.receipt_allocations' in sql:
            eid,record_id=params
            if 'receipt_id=%s' in sql:
                self.last=[(sum((x[4] for x in self.allocations if x[0]==eid and x[2]==record_id),Decimal('0')),)]
            else:
                self.last=[(sum((x[4] for x in self.allocations if x[0]==eid and x[3]==record_id),Decimal('0')),)]
        elif 'INSERT INTO rajan_pilot.receipts' in sql:
            eid,pid,num,amount,mode,ref,key,rhash=params
            self.ids['rcp']+=1;rid=self.ids['rcp']
            self.receipts[rid]=dict(entity_id=eid,patient_id=pid,number=num,amount=amount,idempotency_key=key,request_hash=rhash)
            self.last=[(rid,)]
        elif 'INSERT INTO rajan_pilot.receipt_allocations' in sql:
            self.allocations.append(params)
        elif 'SELECT i.id,i.invoice_number,i.total,COALESCE(SUM(a.amount),0)' in sql:
            eid,pid=params
            self.last=[(iid,i['number'],i['total'],sum((a[4] for a in self.allocations
                  if a[0]==eid and a[3]==iid),Decimal(0))) for iid,i in self.invoices.items()
                  if i['entity_id']==eid and i['patient_id']==pid]
        else:
            super().execute(sql,params)

cur=FinancialCursor()
@contextmanager
def fake_scope(eid,read_only=False):
    assert type(eid) is int and eid in (1,2)
    yield cur

from pg_patient_pilot import create_registration,check_in,create_visit
r=create_registration(1,'CL','Synthetic Clinical Patient',scope=fake_scope)
p=check_in(1,'CL',r['id'],scope=fake_scope)['patient']
v=create_visit(1,'CL',p['id'],'Dental pain',scope=fake_scope)
r2=create_registration(2,'TR','Independent Trust Patient',scope=fake_scope)
p2=check_in(2,'TR',r2['id'],scope=fake_scope)['patient']
v2=create_visit(2,'TR',p2['id'],'Routine review',scope=fake_scope)
assert 16 in VALID_TEETH and 85 in VALID_TEETH and 49 not in VALID_TEETH
for invalid in ('NaN','Infinity','-2','0','0.001',True):
    try:money(invalid)
    except PilotError:pass
    else:raise AssertionError('Allowed invalid monetary value')
t=treatment(1,'CL',p['id'],v['id'],11,'Root canal therapy',16,scope=fake_scope)
assert t['number']=='CL-TRT-000001'
for args in [(1,'CL',p['id'],v2['id'],11,'Bad visit'),(1,'CL',p['id'],v['id'],22,'Bad doctor'),
             (1,'CL',p2['id'],v['id'],11,'Bad patient')]:
    try:treatment(*args,scope=fake_scope)
    except PilotError:pass
    else:raise AssertionError('Allowed cross-entity clinical reference')
inv=invoice(1,'CL',p['id'],[{'treatment_id':t['id'],'amount':'4500.50'}],scope=fake_scope)
assert inv['total']=='4500.50'
try:invoice(2,'TR',p2['id'],[{'treatment_id':t['id'],'amount':'100'}],scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Allowed cross-entity invoicing')
try:invoice(1,'CL',p['id'],[{'treatment_id':t['id'],'amount':'100'},
                                   {'treatment_id':t['id'],'amount':'100'}],scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Allowed repeated invoice treatment')
first=receipt(1,'CL',p['id'],'3000.00',[{'invoice_id':inv['id'],'amount':'2000.50'}],
              'UPI','synthetic-trx',scope=fake_scope)
assert first['unallocated']=='999.50'
assert ledger(1,'CL',p['id'],scope=fake_scope)['invoices'][0]['balance']=='2500.00'
for args in [
    (1,'CL',p['id'],'3000',[{'invoice_id':inv['id'],'amount':'3001'}]),
    (1,'CL',p['id'],'3000',[{'invoice_id':inv['id'],'amount':'2600'}]),
    (2,'TR',p2['id'],'100',[{'invoice_id':inv['id'],'amount':'100'}]),
]:
    try:receipt(*args,scope=fake_scope)
    except PilotError:pass
    else:raise AssertionError('Allowed overpayment or cross-entity allocation')
assert not ledger(2,'TR',p2['id'],scope=fake_scope)['invoices']
upgrade=(root/'migration/pg_patient_pilot_v20_upgrade.sql').read_text()
fresh=(root/'migration/pg_patient_pilot.sql').read_text()
for schema in (upgrade,fresh):
    for clause in ('treatments_visit_patient_fk','FOREIGN KEY(entity_id,invoice_id,patient_id)',
                   'FOREIGN KEY(entity_id,receipt_id,patient_id)','FORCE ROW LEVEL SECURITY',
                   'allocation_limit_guard','NUMERIC(13,2)'):
        assert clause in schema,clause
with tempfile.TemporaryDirectory() as td:
    os.environ['DENTAL_DB']=str(Path(td)/'v20-synthetic.sqlite')
    import app
    app.DB=Path(os.environ['DENTAL_DB']);app.init();app.seed_admin('v20admin','SecureSyntheticPassword20!')
    api=TestClient(app.app)
    token=api.post('/api/login',json={'username':'v20admin','password':'SecureSyntheticPassword20!'}).json()['token']
    headers={'Authorization':'Bearer '+token}
    url='/api/entities/1/pg-pilot'
    assert api.post(url+'/treatments',json={'patient_id':1,'visit_id':1,'planned_by':11,
                    'description':'Root canal'},headers=headers).status_code==503
    assert api.post(url+'/invoices',json={'patient_id':1,'items':[{'treatment_id':1,'amount':'100.00'}]},
                    headers=headers).status_code==503
    assert api.post(url+'/receipts',json={'patient_id':1,'amount':'50','allocations':[],'idempotency_key':'synthetic-v20-receipt'},
                    headers=headers).status_code==503
    assert api.get(url+'/patients/1/ledger',headers=headers).status_code==503
    assert api.get(url+'/patients/1/ledger').status_code==401
print('PASS v2.0: PostgreSQL clinical-to-payment pilot fake-cursor, permissions, money and entity checks')
