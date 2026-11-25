"""Version 2.1 idempotent payment posting regression tests (simulated cursor only)."""
import sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(root/'migration'),str(root/'backend')]
from test_v20 import FinancialCursor, fake_scope, cur, p, inv, ledger, PilotError
from pg_finance_pilot import receipt

key='synthetic-payment-attempt-0001'
a=[{'invoice_id':inv['id'],'amount':'500.00'}]
first=receipt(1,'CL',p['id'],'500.00',a,'UPI','dummy',scope=fake_scope,idempotency_key=key)
second=receipt(1,'CL',p['id'],'500.00',a,'UPI','dummy',scope=fake_scope,idempotency_key=key)
assert first['id']==second['id'] and first['replayed'] is False and second['replayed'] is True
assert second['unallocated']=='0.00'
assert sum(1 for r in cur.receipts.values() if r['idempotency_key']==key)==1
before=len(cur.receipts)
for amount,mode,items in [('550.00','UPI',a),('500.00','CASH',a),('500.00','UPI',[{'invoice_id':inv['id'],'amount':'300.00'}])]:
    try:receipt(1,'CL',p['id'],amount,items,mode,'dummy',scope=fake_scope,idempotency_key=key)
    except PilotError as err:assert 'already used' in str(err)
    else:raise AssertionError('Idempotency key collision changed payment')
assert len(cur.receipts)==before
for bad in ('x','bad key','<script>',True,'z'*101):
    try:receipt(1,'CL',p['id'],'100.00',[],scope=fake_scope,idempotency_key=bad)
    except PilotError:pass
    else:raise AssertionError('Invalid key accepted')
# Schema and upgrade both enforce the same scoped uniqueness.
for filename in ['pg_patient_pilot.sql','pg_patient_pilot_v21_upgrade.sql']:
    content=(root/'migration'/filename).read_text()
    assert 'idempotency_key' in content and 'request_hash' in content
    assert 'UNIQUE(entity_id,idempotency_key)' in content or 'UNIQUE(entity_id,idempotency_key)' in content.replace(' ','')
assert 'pg_advisory_xact_lock' in (root/'migration/pg_finance_pilot.py').read_text()
assert 'idempotency_key:data.idempotency_key' not in (root/'backend/app.py').read_text() # uses keyword forwarding
print('PASS v2.1: duplicate receipt retries, key collisions, financial replay and schema')
