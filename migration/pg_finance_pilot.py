"""Synthetic-data PostgreSQL clinical/billing pilot.

Not part of the operational SQLite API. All writes use scoped transactions,
composite ownership checks, Decimal INR amounts, and database constraints.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import uuid
from pg_scope import scoped_cursor
from pg_patient_pilot import PilotError, _entity, _num, check_pilot_security

VALID_TEETH={q*10+t for q in (1,2,3,4) for t in range(1,9)} | {q*10+t for q in (5,6,7,8) for t in range(1,6)}
CURRENCIES=('CASH','UPI','CARD','BANK')

# Existing pilot RLS checker covers original eight tables; new tables are
# checked here as a separate reviewable list.
def _security(cur):
    check_pilot_security(cur)
    tables=['treatments','invoices','invoice_items','receipts','receipt_allocations']
    cur.execute('''SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND c.relname=ANY(%s) AND c.relkind='r' ''',('rajan_pilot',tables))
    rows=cur.fetchall()
    if len(rows)!=len(tables) or {r[0] for r in rows}!=set(tables) or not all(r[1] and r[2] for r in rows):
        raise PilotError('Financial pilot RLS not configured')
    cur.execute('''SELECT tablename,policyname,permissive,roles,cmd,qual,with_check
       FROM pg_policies WHERE schemaname=%s AND tablename=ANY(%s)''',('rajan_pilot',tables))
    pol=cur.fetchall()
    if len(pol)!=len(tables) or {p[0] for p in pol}!=set(tables) or any(p[1]!='scoped_entity' or p[2]!='PERMISSIVE' or p[3]!=['public']
        or p[4]!='ALL' or 'app.entity_id' not in str(p[5]) or 'app.entity_id' not in str(p[6])
        for p in pol):
        raise PilotError('Financial pilot RLS policy not reviewed')

def _scope(cur,eid,code):
    _security(cur)
    _entity(cur,eid,code)

def money(value):
    if isinstance(value,bool):raise PilotError('Invalid money amount')
    try:amount=Decimal(str(value))
    except (InvalidOperation,ValueError):raise PilotError('Invalid money amount')
    if not amount.is_finite() or amount<=0 or amount>Decimal('99999999999.99') or amount.as_tuple().exponent < -2:
        raise PilotError('Amount must be positive INR with at most two decimals')
    return amount.quantize(Decimal('.01'))

def positive(value,label):
    if type(value) is not int or value<=0:raise PilotError(f'Invalid {label}')

def treatment(entity_id,code,patient_id,visit_id,planned_by,description,tooth_number=None,scope=scoped_cursor):
    for n,label in [(patient_id,'patient'),(visit_id,'visit'),(planned_by,'doctor')]:positive(n,label)
    if not 2<=len(description.strip())<=500:raise PilotError('Invalid procedure')
    if tooth_number is not None and tooth_number not in VALID_TEETH:raise PilotError('Invalid FDI tooth number')
    with scope(entity_id,read_only=False) as cur:
        _scope(cur,entity_id,code)
        cur.execute('''SELECT id FROM rajan_pilot.visits WHERE entity_id=%s AND id=%s AND patient_id=%s''',
                    (entity_id,visit_id,patient_id))
        if not cur.fetchone():raise PilotError('Visit is not owned by patient')
        cur.execute('''SELECT id FROM rajan_pilot.doctors WHERE entity_id=%s AND id=%s AND active=TRUE''',
                    (entity_id,planned_by))
        if not cur.fetchone():raise PilotError('Doctor is not available in this entity')
        number=_num(cur,entity_id,code,'TRT')
        cur.execute('''INSERT INTO rajan_pilot.treatments
          (entity_id,patient_id,visit_id,treatment_number,tooth_number,description,planned_by)
          VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
          (entity_id,patient_id,visit_id,number,tooth_number,description.strip(),planned_by))
        return {'id':cur.fetchone()[0],'number':number,'patient_id':patient_id,'mode':'postgres_pilot'}

def invoice(entity_id,code,patient_id,items,scope=scoped_cursor):
    positive(patient_id,'patient')
    if not isinstance(items,list) or not 1<=len(items)<=30:raise PilotError('Expected 1–30 invoice lines')
    if any(not isinstance(i,dict) or type(i.get('treatment_id')) is not int for i in items):
        raise PilotError('Invalid invoice item')
    ids=[i['treatment_id'] for i in items]
    if len(set(ids))!=len(ids):raise PilotError('Repeated treatment on invoice')
    amounts=[money(i.get('amount')) for i in items]
    total=sum(amounts,Decimal('0'))
    with scope(entity_id,read_only=False) as cur:
        _scope(cur,entity_id,code)
        cur.execute('''SELECT id FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s''',(entity_id,patient_id))
        if not cur.fetchone():raise PilotError('Patient not found')
        # Treatment ownership is constrained again by the composite invoice-item FK.
        for tid in ids:
            cur.execute('''SELECT id FROM rajan_pilot.treatments WHERE entity_id=%s AND patient_id=%s
                           AND id=%s AND status<>'CANCELLED' ''',(entity_id,patient_id,tid))
            if not cur.fetchone():raise PilotError('Treatment not available for this patient')
        number=_num(cur,entity_id,code,'INV')
        cur.execute('''INSERT INTO rajan_pilot.invoices(entity_id,patient_id,invoice_number,total)
          VALUES(%s,%s,%s,%s) RETURNING id''',(entity_id,patient_id,number,total))
        iid=cur.fetchone()[0]
        for tid,amount in zip(ids,amounts):
            cur.execute('''INSERT INTO rajan_pilot.invoice_items
              (entity_id,patient_id,invoice_id,treatment_id,amount) VALUES(%s,%s,%s,%s,%s)''',
              (entity_id,patient_id,iid,tid,amount))
        return {'id':iid,'invoice_number':number,'total':str(total),'mode':'postgres_pilot'}

def receipt(entity_id,code,patient_id,amount,allocations,payment_mode='CASH',reference='',scope=scoped_cursor,idempotency_key=None):
    positive(patient_id,'patient')
    paid=money(amount)
    if payment_mode not in CURRENCIES or not isinstance(reference,str) or len(reference)>120:
        raise PilotError('Invalid payment details')
    if not isinstance(allocations,list) or len(allocations)>30:
        raise PilotError('Invalid allocations')
    if any(not isinstance(a,dict) or type(a.get('invoice_id')) is not int for a in allocations):
        raise PilotError('Invalid invoice allocation')
    ids=[a['invoice_id'] for a in allocations]
    if len(set(ids))!=len(ids):raise PilotError('Duplicate invoice allocation')
    pieces=[money(a.get('amount')) for a in allocations]
    if sum(pieces,Decimal('0'))>paid:raise PilotError('Allocations exceed receipt amount')
    # A retry must carry the SAME key. A missing key is tolerated for legacy pilot
    # clients, but it cannot protect retries; updated clients always send one.
    if idempotency_key is None:
        idempotency_key=str(uuid.uuid4())
    if not isinstance(idempotency_key,str) or not 8<=len(idempotency_key)<=100 or not all(
        c.isascii() and (c.isalnum() or c in '-_') for c in idempotency_key):
        raise PilotError('Invalid payment idempotency key')
    canonical={'patient_id':patient_id,'amount':str(paid),'payment_mode':payment_mode,
               'reference':reference,'allocations':sorted([(iid,str(piece)) for iid,piece in zip(ids,pieces)])}
    request_hash=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with scope(entity_id,read_only=False) as cur:
        _scope(cur,entity_id,code)
        # Serialize retries even when they arrive concurrently on separate API workers.
        # Lock is transaction-local and keyed to entity + request token.
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',
                    (f'rajan_pilot_receipt:{entity_id}:{idempotency_key}',))
        cur.execute('''SELECT id,receipt_number,amount,request_hash FROM rajan_pilot.receipts
                       WHERE entity_id=%s AND idempotency_key=%s''',(entity_id,idempotency_key))
        existing=cur.fetchone()
        if existing:
            if existing[3]!=request_hash:
                raise PilotError('Idempotency key was already used for different payment details')
            cur.execute('''SELECT COALESCE(SUM(amount),0) FROM rajan_pilot.receipt_allocations
                           WHERE entity_id=%s AND receipt_id=%s''',(entity_id,existing[0]))
            allocated=Decimal(str(cur.fetchone()[0]))
            return {'id':existing[0],'receipt_number':existing[1],
                    'amount':str(existing[2]),'unallocated':str(Decimal(str(existing[2]))-allocated),
                    'mode':'postgres_pilot','replayed':True}
        cur.execute('''SELECT id FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s''',(entity_id,patient_id))
        if not cur.fetchone():raise PilotError('Patient not found')
        # Canonical invoice locking order prevents deadlocks between payments.
        requested=dict(zip(ids,pieces))
        for iid in sorted(ids):
            cur.execute('''SELECT total FROM rajan_pilot.invoices
              WHERE entity_id=%s AND patient_id=%s AND id=%s FOR UPDATE''',(entity_id,patient_id,iid))
            row=cur.fetchone()
            if not row:raise PilotError('Invoice not owned by patient')
            cur.execute('''SELECT COALESCE(SUM(amount),0) FROM rajan_pilot.receipt_allocations
              WHERE entity_id=%s AND invoice_id=%s''',(entity_id,iid))
            already=Decimal(str(cur.fetchone()[0]))
            if already+requested[iid]>Decimal(str(row[0])):raise PilotError('Invoice has insufficient balance')
        number=_num(cur,entity_id,code,'RCP')
        cur.execute('''INSERT INTO rajan_pilot.receipts
          (entity_id,patient_id,receipt_number,amount,payment_mode,reference,idempotency_key,request_hash)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
          (entity_id,patient_id,number,paid,payment_mode,reference,idempotency_key,request_hash))
        rid=cur.fetchone()[0]
        for iid,part in zip(ids,pieces):
            cur.execute('''INSERT INTO rajan_pilot.receipt_allocations
              (entity_id,patient_id,receipt_id,invoice_id,amount)
              VALUES(%s,%s,%s,%s,%s)''',(entity_id,patient_id,rid,iid,part))
        return {'id':rid,'receipt_number':number,'amount':str(paid),
                'unallocated':str(paid-sum(pieces,Decimal('0'))),'mode':'postgres_pilot','replayed':False}

def ledger(entity_id,code,patient_id,scope=scoped_cursor):
    positive(patient_id,'patient')
    with scope(entity_id,read_only=True) as cur:
        _scope(cur,entity_id,code)
        cur.execute('SELECT id FROM rajan_pilot.patients WHERE entity_id=%s AND id=%s',(entity_id,patient_id))
        if not cur.fetchone():raise PilotError('Patient not found')
        cur.execute('''SELECT i.id,i.invoice_number,i.total,COALESCE(SUM(a.amount),0)
          FROM rajan_pilot.invoices i LEFT JOIN rajan_pilot.receipt_allocations a
          ON a.entity_id=i.entity_id AND a.invoice_id=i.id
          WHERE i.entity_id=%s AND i.patient_id=%s
          GROUP BY i.id,i.invoice_number,i.total ORDER BY i.id DESC LIMIT 100''',(entity_id,patient_id))
        return {'invoices':[{'id':r[0],'number':r[1],'total':str(r[2]),
                  'paid':str(r[3]),'balance':str(Decimal(str(r[2]))-Decimal(str(r[3])))} for r in cur.fetchall()],
                'mode':'postgres_pilot'}
