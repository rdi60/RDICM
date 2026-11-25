"""Additive v0.2 development modules. Existing v0.1 APIs/tables remain untouched.

Financial posting is recorded in paise and checked inside SQLite BEGIN IMMEDIATE
transactions. This is NOT a substitute for PostgreSQL production accounting.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional
from fastapi import Depends
from pydantic import BaseModel, Field

SQL = '''
CREATE TABLE IF NOT EXISTS clinical_text_templates_v4 (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),
 shortcut TEXT NOT NULL,phrase TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
 created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 UNIQUE(entity_id,shortcut),UNIQUE(entity_id,id));
CREATE TABLE IF NOT EXISTS pricing_categories (
 id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id),
 code TEXT NOT NULL, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 UNIQUE(entity_id,code), UNIQUE(entity_id,id));
CREATE TABLE IF NOT EXISTS treatment_categories_v3 (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),
 name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
 UNIQUE(entity_id,name),UNIQUE(entity_id,id));
CREATE TABLE IF NOT EXISTS procedure_master (
 id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id),
 code TEXT NOT NULL, name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT 'procedure',
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
 UNIQUE(entity_id,code), UNIQUE(entity_id,id));
CREATE TABLE IF NOT EXISTS procedure_prices (
 entity_id INTEGER NOT NULL, procedure_id INTEGER NOT NULL,
 category_id INTEGER NOT NULL, unit_price_paise INTEGER NOT NULL CHECK(unit_price_paise>=0),
 PRIMARY KEY(entity_id,procedure_id,category_id),
 FOREIGN KEY(entity_id,procedure_id) REFERENCES procedure_master(entity_id,id),
 FOREIGN KEY(entity_id,category_id) REFERENCES pricing_categories(entity_id,id));
CREATE TABLE IF NOT EXISTS plan_headers (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,patient_id INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','completed','cancelled')),
 created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id));
CREATE TABLE IF NOT EXISTS plan_lines (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,plan_id INTEGER NOT NULL,
 procedure_id INTEGER,description TEXT NOT NULL,tooth TEXT NOT NULL DEFAULT '',
 planned_by INTEGER,performed_by INTEGER,unit TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),
 unit_price_paise INTEGER NOT NULL CHECK(unit_price_paise>=0),category_id INTEGER,
 adjust_kind TEXT NOT NULL DEFAULT 'none' CHECK(adjust_kind IN ('none','discount','premium')),
 adjust_mode TEXT NOT NULL DEFAULT 'rs' CHECK(adjust_mode IN ('rs','pct')),
 adjust_value TEXT NOT NULL DEFAULT '0',net_paise INTEGER NOT NULL CHECK(net_paise>=0),
 billing_mode TEXT NOT NULL DEFAULT 'package' CHECK(billing_mode IN ('package','stage')),
 stage_state TEXT NOT NULL DEFAULT 'planned',created_at TEXT NOT NULL,
 UNIQUE(entity_id,id),FOREIGN KEY(entity_id,plan_id) REFERENCES plan_headers(entity_id,id),
 FOREIGN KEY(entity_id,procedure_id) REFERENCES procedure_master(entity_id,id),
 FOREIGN KEY(entity_id,category_id) REFERENCES pricing_categories(entity_id,id),
 FOREIGN KEY(entity_id,planned_by) REFERENCES doctors(entity_id,id),
 FOREIGN KEY(entity_id,performed_by) REFERENCES doctors(entity_id,id));
CREATE TABLE IF NOT EXISTS plan_stages (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,line_id INTEGER NOT NULL,
 name TEXT NOT NULL,sequence INTEGER NOT NULL CHECK(sequence>0),
 amount_paise INTEGER NOT NULL DEFAULT 0 CHECK(amount_paise>=0),
 status TEXT NOT NULL DEFAULT 'planned',
 UNIQUE(entity_id,id),UNIQUE(entity_id,line_id,sequence),
 FOREIGN KEY(entity_id,line_id) REFERENCES plan_lines(entity_id,id));
CREATE TABLE IF NOT EXISTS estimate_headers_v2 (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,patient_id INTEGER NOT NULL,
 estimate_no TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','cancelled')),
 category_id INTEGER,created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 UNIQUE(entity_id,id),UNIQUE(entity_id,estimate_no),
 FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id),
 FOREIGN KEY(entity_id,category_id) REFERENCES pricing_categories(entity_id,id));
CREATE TABLE IF NOT EXISTS estimate_lines_v2 (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,estimate_id INTEGER NOT NULL,
 plan_line_id INTEGER,plan_stage_id INTEGER,description TEXT NOT NULL,
 planned_by INTEGER,performed_by INTEGER,unit TEXT NOT NULL,quantity INTEGER NOT NULL,
 unit_price_paise INTEGER NOT NULL,adjust_kind TEXT NOT NULL,adjust_mode TEXT NOT NULL,
 adjust_value TEXT NOT NULL,net_paise INTEGER NOT NULL,
 UNIQUE(entity_id,id),FOREIGN KEY(entity_id,estimate_id) REFERENCES estimate_headers_v2(entity_id,id),
 FOREIGN KEY(entity_id,plan_line_id) REFERENCES plan_lines(entity_id,id),
 FOREIGN KEY(entity_id,plan_stage_id) REFERENCES plan_stages(entity_id,id));
CREATE TABLE IF NOT EXISTS invoice_headers_v2 (
 entity_id INTEGER NOT NULL,invoice_id INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','issued')),
 category_id INTEGER,created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 PRIMARY KEY(entity_id,invoice_id),
 FOREIGN KEY(entity_id,invoice_id) REFERENCES invoices(entity_id,id));
CREATE TABLE IF NOT EXISTS invoice_lines_v2 (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,invoice_id INTEGER NOT NULL,
 estimate_line_id INTEGER,plan_line_id INTEGER,plan_stage_id INTEGER,
 description TEXT NOT NULL,planned_by INTEGER,performed_by INTEGER,unit TEXT NOT NULL,
 quantity INTEGER NOT NULL,unit_price_paise INTEGER NOT NULL,
 adjust_kind TEXT NOT NULL,adjust_mode TEXT NOT NULL,adjust_value TEXT NOT NULL,
 net_paise INTEGER NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(entity_id,id),FOREIGN KEY(entity_id,invoice_id) REFERENCES invoices(entity_id,id),
 FOREIGN KEY(entity_id,estimate_line_id) REFERENCES estimate_lines_v2(entity_id,id),
 FOREIGN KEY(entity_id,plan_line_id) REFERENCES plan_lines(entity_id,id),
 FOREIGN KEY(entity_id,plan_stage_id) REFERENCES plan_stages(entity_id,id));
CREATE UNIQUE INDEX IF NOT EXISTS unq_invoice_est_line ON invoice_lines_v2(entity_id,estimate_line_id) WHERE estimate_line_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS unq_invoice_plan_line ON invoice_lines_v2(entity_id,plan_line_id) WHERE plan_line_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS unq_invoice_plan_stage ON invoice_lines_v2(entity_id,plan_stage_id) WHERE plan_stage_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS financial_writeoffs (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,invoice_id INTEGER NOT NULL,
 amount_paise INTEGER NOT NULL CHECK(amount_paise>0),reason TEXT NOT NULL,
 performed_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 FOREIGN KEY(entity_id,invoice_id) REFERENCES invoices(entity_id,id));
CREATE TABLE IF NOT EXISTS advance_refunds_v2 (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,receipt_id INTEGER NOT NULL,
 amount_paise INTEGER NOT NULL CHECK(amount_paise>0),reason TEXT NOT NULL,
 method TEXT NOT NULL,performed_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 FOREIGN KEY(entity_id,receipt_id) REFERENCES receipts(entity_id,id));
CREATE TABLE IF NOT EXISTS advance_transfers_v2 (
 id INTEGER PRIMARY KEY,source_entity_id INTEGER NOT NULL,source_receipt_id INTEGER NOT NULL,
 dest_entity_id INTEGER NOT NULL,dest_patient_id INTEGER NOT NULL,dest_receipt_id INTEGER NOT NULL,
 amount_paise INTEGER NOT NULL CHECK(amount_paise>0),reason TEXT NOT NULL,
 performed_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 FOREIGN KEY(source_entity_id,source_receipt_id) REFERENCES receipts(entity_id,id),
 FOREIGN KEY(dest_entity_id,dest_receipt_id) REFERENCES receipts(entity_id,id),
 FOREIGN KEY(dest_entity_id,dest_patient_id) REFERENCES patients(entity_id,id),
 CHECK(source_entity_id!=dest_entity_id));
CREATE TABLE IF NOT EXISTS permission_groups_v2 (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
 UNIQUE(entity_id,name),UNIQUE(entity_id,id));
CREATE TABLE IF NOT EXISTS group_permissions_v2 (
 entity_id INTEGER NOT NULL,group_id INTEGER NOT NULL,permission TEXT NOT NULL,
 PRIMARY KEY(entity_id,group_id,permission),
 FOREIGN KEY(entity_id,group_id) REFERENCES permission_groups_v2(entity_id,id));
CREATE TABLE IF NOT EXISTS membership_roles_v2 (
 entity_id INTEGER NOT NULL,user_id INTEGER NOT NULL,role TEXT NOT NULL,
 PRIMARY KEY(entity_id,user_id,role),
 FOREIGN KEY(user_id,entity_id) REFERENCES memberships(user_id,entity_id));
CREATE TABLE IF NOT EXISTS membership_groups_v2 (
 entity_id INTEGER NOT NULL,user_id INTEGER NOT NULL,group_id INTEGER NOT NULL,
 PRIMARY KEY(entity_id,user_id,group_id),
 FOREIGN KEY(user_id,entity_id) REFERENCES memberships(user_id,entity_id),
 FOREIGN KEY(entity_id,group_id) REFERENCES permission_groups_v2(entity_id,id));
CREATE TABLE IF NOT EXISTS v02_audit (
 id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,
 action TEXT NOT NULL,object_type TEXT NOT NULL,object_id INTEGER,
 details TEXT NOT NULL DEFAULT '{}',at TEXT NOT NULL);
'''

DEFAULT_CATEGORIES = [('regular','Regular Price'),('premium','Premium'),('corporate','Corporate'),('priority','Priority'),('charity','Charity')]
ALLOWED_ROLES={'admin','reception','doctor','billing','viewer'}
ALLOWED_PERMISSIONS={'patients.read','patients.write','clinical.read','clinical.write','billing.read','billing.write','billing.adjust','staff.read','staff.manage','reports.read','documents.read','documents.write'}


def install(db,utc):
    # executescript is deliberately outside a managed write context.
    with db() as c:
        c.executescript(SQL)
        # v0.3 additive columns; legacy records and invoice price snapshots are retained.
        for table,col,spec in [('pricing_categories','is_default','INTEGER NOT NULL DEFAULT 0'),('procedure_master','treatment_category_id','INTEGER'),('estimate_lines_v2','procedure_id','INTEGER'),('plan_lines','treatment_category_id','INTEGER'),('estimate_lines_v2','treatment_category_id','INTEGER'),('invoice_lines_v2','treatment_category_id','INTEGER'),('invoice_lines_v2','procedure_id','INTEGER')]:
            if col not in [r[1] for r in c.execute(f'PRAGMA table_info({table})')]:
                c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {spec}')
        for eid, in c.execute('SELECT id FROM entities').fetchall():
            for code,name in DEFAULT_CATEGORIES:
                c.execute('INSERT OR IGNORE INTO pricing_categories(entity_id,code,name) VALUES(?,?,?)',(eid,code,name))
            if not c.execute('SELECT 1 FROM pricing_categories WHERE entity_id=? AND is_default=1',(eid,)).fetchone():
                c.execute("UPDATE pricing_categories SET is_default=1 WHERE entity_id=? AND code='regular'",(eid,))


def money(v):
    try:
        d=Decimal(str(v))
        if not d.is_finite() or d < 0 or d > Decimal('10000000000') or d.as_tuple().exponent < -2:
            raise ValueError
        return int(d*100)
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError('Invalid monetary value; use at most two decimals')


def priced(quantity,unit_price_paise,kind='none',mode='rs',value='0'):
    if kind not in ('none','discount','premium') or mode not in ('rs','pct'):raise ValueError('Invalid adjustment')
    if not isinstance(quantity,int) or quantity<1 or quantity>10000:raise ValueError('Invalid quantity')
    gross=quantity*unit_price_paise
    d=Decimal(str(value))
    if not d.is_finite() or d<0:raise ValueError('Invalid adjustment value')
    if kind=='none' and d!=0:raise ValueError('Choose an adjustment type')
    if mode=='pct':
        if d>100:raise ValueError('Percentage cannot exceed 100')
        adjustment=int((Decimal(gross)*d/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    else:adjustment=money(value)
    if kind=='discount' and adjustment>gross:raise ValueError('Discount exceeds line gross')
    return gross+(adjustment if kind=='premium' else -adjustment if kind=='discount' else 0)


def register(app,helpers):
    import json
    from fastapi import HTTPException
    db,access,current,one,rows,fail,cents,nextnum,audit,utc=[helpers[k] for k in ('db','access','current','one','rows','fail','cents','nextnum','audit','utc')]

    def check(eid,u,roles=('admin','billing')):return access(eid,u,roles)
    def get_patient(c,eid,pid):
        p=one(c,'SELECT * FROM patients WHERE entity_id=? AND id=?',(eid,pid))
        if not p:fail('Patient not found in this entity',404)
        return p
    def require(c,table,eid,id):
        x=one(c,f'SELECT * FROM {table} WHERE entity_id=? AND id=?',(eid,id))
        if not x:fail('Record not found in this entity',404)
        return x
    def log(c,u,eid,action,kind,id,details=None):
        c.execute('INSERT INTO v02_audit(entity_id,actor_id,action,object_type,object_id,details,at) VALUES(?,?,?,?,?,?,?)',(eid,u['id'],action,kind,id,json.dumps(details or {},default=str),utc()))
        audit(c,u,eid,action,kind,id)
    def to_paise(s):
        try:return money(s)
        except ValueError as e:fail(str(e))
    def price_line(d):
        try:
            price=to_paise(d.unit_price)
            return price,priced(d.quantity,price,d.adjust_kind,d.adjust_mode,d.adjust_value)
        except (ValueError,InvalidOperation) as e:fail(str(e))
    def price_in(c,eid,procedure_id,category_id,custom_unit_price):
        require(c,'procedure_master',eid,procedure_id)
        if category_id is None:fail('Pricing category required')
        require(c,'pricing_categories',eid,category_id)
        p=one(c,'SELECT unit_price_paise FROM procedure_prices WHERE entity_id=? AND procedure_id=? AND category_id=?',(eid,procedure_id,category_id))
        if not p and custom_unit_price is None:fail('Price not configured for this category')
        return to_paise(custom_unit_price) if custom_unit_price is not None else p['unit_price_paise']
    def billed(c,eid,invoice_id):
        i=one(c,'SELECT * FROM invoices WHERE entity_id=? AND id=?',(eid,invoice_id))
        if not i:fail('Invoice not found in entity',404)
        credits=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM credit_notes WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)).fetchone()[0]
        writeoffs=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM financial_writeoffs WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)).fetchone()[0]
        paid=c.execute('''SELECT COALESCE(SUM(a.amount_paise),0) FROM allocations a WHERE a.entity_id=? AND a.invoice_id=? AND NOT EXISTS (SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=a.entity_id AND rr.receipt_id=a.receipt_id)''',(eid,invoice_id)).fetchone()[0]
        return i,max(0,i['total_paise']-credits-writeoffs-paid)
    def available(c,eid,rid):
        r=require(c,'receipts',eid,rid)
        if one(c,'SELECT 1 FROM receipt_reversals WHERE entity_id=? AND receipt_id=?',(eid,rid)):return 0
        allocated=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM allocations WHERE entity_id=? AND receipt_id=?',(eid,rid)).fetchone()[0]
        refunded=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM advance_refunds_v2 WHERE entity_id=? AND receipt_id=?',(eid,rid)).fetchone()[0]
        transferred=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM advance_transfers_v2 WHERE source_entity_id=? AND source_receipt_id=?',(eid,rid)).fetchone()[0]
        return max(0,r['amount_paise']-allocated-refunded-transferred)

    class CategoryIn(BaseModel):code:str=Field(min_length=2,max_length=30);name:str=Field(min_length=2,max_length=100)
    class ProcedureIn(BaseModel):code:str='';name:str=Field(min_length=2,max_length=200);unit:str='procedure';treatment_category_id:Optional[int]=None
    class TariffIn(BaseModel):category_id:int;unit_price:str
    class PriceWithProcedure(BaseModel):name:str=Field(min_length=2,max_length=200);treatment_category_id:Optional[int]=None;prices:dict[int,str]={}
    class RenameCategory(BaseModel):name:str=Field(min_length=2,max_length=100);active:bool=True
    class TreatmentCategoryIn(BaseModel):name:str=Field(min_length=2,max_length=100)
    class ClinicalTemplateIn(BaseModel):shortcut:str=Field(min_length=2,max_length=30);phrase:str=Field(min_length=2,max_length=500);active:bool=True
    class LineIn(BaseModel):
        procedure_id:Optional[int]=None
        description:str=Field(min_length=2,max_length=300)
        tooth:str=''
        planned_by:Optional[int]=None
        performed_by:Optional[int]=None
        unit:str='procedure'
        quantity:int=Field(default=1,ge=1,le=10000)
        unit_price:str='0'
        category_id:Optional[int]=None
        adjust_kind:str='none'
        adjust_mode:str='rs'
        adjust_value:str='0'
        billing_mode:str='package'
    class PlanCreate(BaseModel):patient_id:int
    class StageIn(BaseModel):name:str=Field(min_length=2,max_length=200);sequence:int=Field(ge=1);amount:str='0'
    class EstimateCreate(BaseModel):patient_id:int;category_id:Optional[int]=None;plan_line_ids:list[int]=[];stage_ids:list[int]=[];direct_lines:list[LineIn]=[]
    class InvoiceCreate(BaseModel):patient_id:int;category_id:Optional[int]=None;plan_line_ids:list[int]=[];stage_ids:list[int]=[];estimate_line_ids:list[int]=[];direct_lines:list[LineIn]=[]
    class AdvanceIn(BaseModel):patient_id:int;amount:str;method:str='upi';reference:str=''
    class AdvanceAllocate(BaseModel):receipt_id:int;invoice_id:int;amount:str
    class AdvanceRefund(BaseModel):receipt_id:int;amount:str;reason:str=Field(min_length=5);method:str='bank'
    class AdvanceTransfer(BaseModel):source_entity_id:int;source_receipt_id:int;dest_entity_id:int;dest_patient_id:int;amount:str;reason:str=Field(min_length=5)
    class WriteoffIn(BaseModel):invoice_id:int;amount:str;reason:str=Field(min_length=5)
    class GroupIn(BaseModel):name:str=Field(min_length=2,max_length=100);permissions:list[str]=[]
    class AssignIn(BaseModel):entity_roles:dict[int,list[str]];entity_groups:dict[int,list[int]]={}
    # Pydantic nested route models must be resolvable by FastAPI's type-hint evaluation.
    globals().update({c.__name__:c for c in (CategoryIn,ProcedureIn,TariffIn,PriceWithProcedure,RenameCategory,TreatmentCategoryIn,ClinicalTemplateIn,LineIn,PlanCreate,StageIn,EstimateCreate,InvoiceCreate,AdvanceIn,AdvanceAllocate,AdvanceRefund,AdvanceTransfer,WriteoffIn,GroupIn,AssignIn)})

    @app.get('/api/entities/{eid}/v2/pricing-categories')
    def categories(eid:int,u=Depends(current)):
        check(eid,u,('admin','billing','doctor','viewer'))
        with db() as c:return rows(c,'SELECT * FROM pricing_categories WHERE entity_id=? ORDER BY id',(eid,))

    @app.post('/api/entities/{eid}/v2/pricing-categories')
    def add_category(eid:int,data:CategoryIn,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            cur=c.execute('INSERT INTO pricing_categories(entity_id,code,name) VALUES(?,?,?)',(eid,data.code.strip().lower(),data.name.strip()))
            log(c,u,eid,'pricing_category_created','pricing_category',cur.lastrowid)
            return {'id':cur.lastrowid}


    @app.put('/api/entities/{eid}/v3/pricing-categories/{category_id}')
    def update_category_v3(eid:int,category_id:int,data:RenameCategory,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            old=require(c,'pricing_categories',eid,category_id)
            if not data.active and old['is_default']:fail('Choose another default before deactivating',409)
            c.execute('UPDATE pricing_categories SET name=?,active=? WHERE entity_id=? AND id=?',(data.name.strip(),int(data.active),eid,category_id))
            log(c,u,eid,'pricing_category_updated','pricing_category',category_id,{'before':old,'name':data.name,'active':data.active})
            return {'id':category_id}

    @app.put('/api/entities/{eid}/v3/pricing-categories/{category_id}/default')
    def default_category_v3(eid:int,category_id:int,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            category=require(c,'pricing_categories',eid,category_id)
            if not category['active']:fail('Cannot default inactive pricing category',409)
            c.execute('UPDATE pricing_categories SET is_default=0 WHERE entity_id=?',(eid,))
            c.execute('UPDATE pricing_categories SET is_default=1 WHERE entity_id=? AND id=?',(eid,category_id))
            log(c,u,eid,'pricing_default_changed','pricing_category',category_id)
            return {'id':category_id,'is_default':True}

    @app.get('/api/entities/{eid}/v4/clinical-text-templates')
    def clinical_text_templates_v4(eid:int,u=Depends(current)):
        check(eid,u,('admin','doctor'))
        with db() as c:
            return rows(c,'SELECT id,shortcut,phrase,active FROM clinical_text_templates_v4 WHERE entity_id=? AND active=1 ORDER BY shortcut',(eid,))

    @app.post('/api/entities/{eid}/v4/clinical-text-templates')
    def add_clinical_template_v4(eid:int,data:ClinicalTemplateIn,u=Depends(current)):
        check(eid,u,('admin',))
        shortcut=data.shortcut.strip().lower()
        if not shortcut.replace('_','').isalnum():fail('Shortcut must use letters, digits or underscores')
        with db(True) as c:
            if one(c,'SELECT id FROM clinical_text_templates_v4 WHERE entity_id=? AND shortcut=?',(eid,shortcut)):fail('Shortcut already exists',409)
            id=c.execute('INSERT INTO clinical_text_templates_v4(entity_id,shortcut,phrase,active,created_by,created_at) VALUES(?,?,?,?,?,?)',(eid,shortcut,data.phrase.strip(),int(data.active),u['id'],utc())).lastrowid
            log(c,u,eid,'clinical_shortcut_created','clinical_text_template',id)
            return {'id':id}

    @app.put('/api/entities/{eid}/v4/clinical-text-templates/{tid}')
    def update_clinical_template_v4(eid:int,tid:int,data:ClinicalTemplateIn,u=Depends(current)):
        check(eid,u,('admin',))
        shortcut=data.shortcut.strip().lower()
        if not shortcut.replace('_','').isalnum():fail('Shortcut must use letters, digits or underscores')
        with db(True) as c:
            require(c,'clinical_text_templates_v4',eid,tid)
            if one(c,'SELECT id FROM clinical_text_templates_v4 WHERE entity_id=? AND shortcut=? AND id<>?',(eid,shortcut,tid)):fail('Shortcut already exists',409)
            c.execute('UPDATE clinical_text_templates_v4 SET shortcut=?,phrase=?,active=? WHERE entity_id=? AND id=?',(shortcut,data.phrase.strip(),int(data.active),eid,tid))
            log(c,u,eid,'clinical_shortcut_updated','clinical_text_template',tid)
            return {'id':tid}

    @app.get('/api/entities/{eid}/v3/treatment-categories')
    def treatment_categories_v3(eid:int,u=Depends(current)):
        check(eid,u,('admin','billing','doctor','viewer'))
        with db() as c:return rows(c,'SELECT * FROM treatment_categories_v3 WHERE entity_id=? ORDER BY name',(eid,))

    @app.post('/api/entities/{eid}/v3/treatment-categories')
    def add_treatment_category_v3(eid:int,data:TreatmentCategoryIn,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            id=c.execute('INSERT INTO treatment_categories_v3(entity_id,name) VALUES(?,?)',(eid,data.name.strip())).lastrowid
            log(c,u,eid,'treatment_category_created','treatment_category',id)
            return {'id':id}

    @app.put('/api/entities/{eid}/v3/treatment-categories/{catid}')
    def update_treatment_category_v3(eid:int,catid:int,data:RenameCategory,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            old=require(c,'treatment_categories_v3',eid,catid)
            c.execute('UPDATE treatment_categories_v3 SET name=?,active=? WHERE entity_id=? AND id=?',(data.name.strip(),int(data.active),eid,catid))
            log(c,u,eid,'treatment_category_updated','treatment_category',catid,{'before':old})
            return {'id':catid}

    def save_procedure_and_prices(c,eid,u,data,pid=None):
        if data.treatment_category_id is not None:
            cat=require(c,'treatment_categories_v3',eid,data.treatment_category_id)
            if not cat['active']:fail('Treatment category is inactive',409)
        if pid is None:
            nextid=c.execute('SELECT COALESCE(MAX(id),0)+1 FROM procedure_master').fetchone()[0]
            code=f'PRC{nextid:05d}'
            pid=c.execute('INSERT INTO procedure_master(entity_id,code,name,unit,created_at,treatment_category_id) VALUES(?,?,?,?,?,?)',(eid,code,data.name.strip(),'procedure',utc(),data.treatment_category_id)).lastrowid
        else:
            require(c,'procedure_master',eid,pid)
            c.execute('UPDATE procedure_master SET name=?,treatment_category_id=? WHERE entity_id=? AND id=?',(data.name.strip(),data.treatment_category_id,eid,pid))
        for catid,amount in data.prices.items():
            category=require(c,'pricing_categories',eid,catid)
            if not category['active']:fail('Cannot set inactive pricing category',409)
            cents_amount=to_paise(amount)
            c.execute('INSERT INTO procedure_prices(entity_id,procedure_id,category_id,unit_price_paise) VALUES(?,?,?,?) ON CONFLICT(entity_id,procedure_id,category_id) DO UPDATE SET unit_price_paise=excluded.unit_price_paise',(eid,pid,catid,cents_amount))
        log(c,u,eid,'procedure_and_prices_saved','procedure',pid)
        return {'id':pid}

    @app.post('/api/entities/{eid}/v3/procedures')
    def create_procedure_prices_v3(eid:int,data:PriceWithProcedure,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:return save_procedure_and_prices(c,eid,u,data)

    @app.put('/api/entities/{eid}/v3/procedures/{pid}')
    def update_procedure_prices_v3(eid:int,pid:int,data:PriceWithProcedure,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:return save_procedure_and_prices(c,eid,u,data,pid)

    @app.put('/api/entities/{eid}/v3/procedures/{pid}/active')
    def toggle_procedure_v3(eid:int,pid:int,active:bool,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            require(c,'procedure_master',eid,pid)
            c.execute('UPDATE procedure_master SET active=? WHERE entity_id=? AND id=?',(int(active),eid,pid))
            log(c,u,eid,'procedure_status_changed','procedure',pid,{'active':active})
            return {'id':pid,'active':active}

    @app.get('/api/entities/{eid}/v3/reports/treatment-categories')
    def treatment_category_report_v3(eid:int,u=Depends(current)):
        check(eid,u,('admin','billing'))
        with db() as c:
            return rows(c,"""SELECT tc.id,tc.name,
               (SELECT COUNT(*) FROM plan_lines pl WHERE pl.entity_id=tc.entity_id AND pl.treatment_category_id=tc.id) planned_procedure_count,
               (SELECT COALESCE(SUM(pl.net_paise),0) FROM plan_lines pl WHERE pl.entity_id=tc.entity_id AND pl.treatment_category_id=tc.id) planned_value_paise,
               (SELECT COUNT(*) FROM invoice_lines_v2 il WHERE il.entity_id=tc.entity_id AND il.treatment_category_id=tc.id) invoiced_line_count,
               (SELECT COALESCE(SUM(il.net_paise),0) FROM invoice_lines_v2 il WHERE il.entity_id=tc.entity_id AND il.treatment_category_id=tc.id) invoiced_value_paise
               FROM treatment_categories_v3 tc WHERE tc.entity_id=? ORDER BY tc.name""",(eid,))

    @app.get('/api/entities/{eid}/v2/procedures')
    def procedures(eid:int,u=Depends(current)):
        check(eid,u,('admin','billing','doctor','viewer'))
        with db() as c:
            return rows(c,'''SELECT p.*,c.name category_name,c.id category_id,pr.unit_price_paise FROM procedure_master p LEFT JOIN procedure_prices pr ON pr.entity_id=p.entity_id AND pr.procedure_id=p.id LEFT JOIN pricing_categories c ON c.entity_id=p.entity_id AND c.id=pr.category_id WHERE p.entity_id=? ORDER BY p.name,c.id''',(eid,))

    @app.post('/api/entities/{eid}/v2/procedures')
    def add_procedure(eid:int,data:ProcedureIn,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            cur=c.execute('INSERT INTO procedure_master(entity_id,code,name,unit,created_at) VALUES(?,?,?,?,?)',(eid,data.code.strip().upper(),data.name.strip(),data.unit.strip(),utc()))
            log(c,u,eid,'procedure_created','procedure',cur.lastrowid)
            return {'id':cur.lastrowid}

    @app.put('/api/entities/{eid}/v2/procedures/{pid}/price')
    def set_price(eid:int,pid:int,data:TariffIn,u=Depends(current)):
        check(eid,u,('admin',))
        with db(True) as c:
            require(c,'procedure_master',eid,pid);require(c,'pricing_categories',eid,data.category_id)
            previous=one(c,'SELECT * FROM procedure_prices WHERE entity_id=? AND procedure_id=? AND category_id=?',(eid,pid,data.category_id))
            amount=to_paise(data.unit_price)
            c.execute('INSERT INTO procedure_prices(entity_id,procedure_id,category_id,unit_price_paise) VALUES(?,?,?,?) ON CONFLICT(entity_id,procedure_id,category_id) DO UPDATE SET unit_price_paise=excluded.unit_price_paise',(eid,pid,data.category_id,amount))
            log(c,u,eid,'procedure_price_updated','procedure',pid,{'category_id':data.category_id,'before':previous,'after':amount})
            return {'procedure_id':pid,'category_id':data.category_id,'unit_price_paise':amount}

    def enforce_tariff(c,eid,u,d):
        if not d.procedure_id:return
        proc=require(c,'procedure_master',eid,d.procedure_id)
        if not proc['active']:fail('Procedure is inactive',409)
        if not d.category_id:fail('Pricing category required when selecting a procedure')
        category=require(c,'pricing_categories',eid,d.category_id)
        tariff=one(c,'SELECT unit_price_paise FROM procedure_prices WHERE entity_id=? AND procedure_id=? AND category_id=?',(eid,d.procedure_id,d.category_id))
        actual=to_paise(d.unit_price)
        is_admin=bool(one(c,"SELECT 1 FROM memberships WHERE entity_id=? AND user_id=? AND role='admin' UNION SELECT 1 FROM membership_roles_v2 WHERE entity_id=? AND user_id=? AND role='admin'",(eid,u['id'],eid,u['id'])))
        if (not tariff or actual!=tariff['unit_price_paise']) and not is_admin:
            fail('Tariff override is restricted to administrators',403)

    def add_plan_line(c,eid,plan_id,d,u):
        require(c,'plan_headers',eid,plan_id)
        for doctor in (d.planned_by,d.performed_by):
            if doctor is not None:require(c,'doctors',eid,doctor)
        enforce_tariff(c,eid,u,d)
        price,net=price_line(d)
        if d.billing_mode not in ('package','stage'):fail('Invalid billing mode')
        if d.procedure_id:require(c,'procedure_master',eid,d.procedure_id)
        if d.category_id:require(c,'pricing_categories',eid,d.category_id)
        id=c.execute('''INSERT INTO plan_lines(entity_id,plan_id,procedure_id,description,tooth,planned_by,performed_by,unit,quantity,unit_price_paise,category_id,adjust_kind,adjust_mode,adjust_value,net_paise,billing_mode,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(eid,plan_id,d.procedure_id,d.description,d.tooth,d.planned_by,d.performed_by,d.unit,d.quantity,price,d.category_id,d.adjust_kind,d.adjust_mode,d.adjust_value,net,d.billing_mode,utc())).lastrowid
        cat=one(c,'SELECT treatment_category_id FROM procedure_master WHERE entity_id=? AND id=?',(eid,d.procedure_id)) if d.procedure_id else None
        c.execute('UPDATE plan_lines SET treatment_category_id=? WHERE entity_id=? AND id=?',(cat['treatment_category_id'] if cat else None,eid,id))
        return id

    @app.get('/api/entities/{eid}/v2/plans')
    def plans(eid:int,patient_id:Optional[int]=None,u=Depends(current)):
        check(eid,u,('admin','doctor','billing','viewer'))
        with db() as c:
            return rows(c,'SELECT * FROM plan_headers WHERE entity_id=? AND (? IS NULL OR patient_id=?) ORDER BY id DESC',(eid,patient_id,patient_id))

    @app.post('/api/entities/{eid}/v2/plans')
    def create_plan(eid:int,data:PlanCreate,u=Depends(current)):
        check(eid,u,('admin','doctor'))
        with db(True) as c:
            get_patient(c,eid,data.patient_id)
            id=c.execute('INSERT INTO plan_headers(entity_id,patient_id,created_by,created_at) VALUES(?,?,?,?)',(eid,data.patient_id,u['id'],utc())).lastrowid
            log(c,u,eid,'treatment_plan_created','plan',id)
            return {'id':id}

    @app.get('/api/entities/{eid}/v2/plans/{plan_id}')
    def plan_detail(eid:int,plan_id:int,u=Depends(current)):
        check(eid,u,('admin','doctor','billing','viewer'))
        with db() as c:
            plan=require(c,'plan_headers',eid,plan_id)
            lines=rows(c,'SELECT * FROM plan_lines WHERE entity_id=? AND plan_id=? ORDER BY id',(eid,plan_id))
            for line in lines:line['stages']=rows(c,'SELECT * FROM plan_stages WHERE entity_id=? AND line_id=? ORDER BY sequence',(eid,line['id']))
            return {'plan':plan,'lines':lines}

    @app.post('/api/entities/{eid}/v2/plans/{plan_id}/lines')
    def plan_add_line(eid:int,plan_id:int,data:LineIn,u=Depends(current)):
        check(eid,u,('admin','doctor'))
        with db(True) as c:
            plan=require(c,'plan_headers',eid,plan_id)
            if plan['status']!='draft':fail('Plan is not editable',409)
            id=add_plan_line(c,eid,plan_id,data,u)
            log(c,u,eid,'plan_line_added','plan_line',id)
            return {'id':id}

    @app.put('/api/entities/{eid}/v2/plans/{plan_id}/lines/{line_id}')
    def plan_update_line(eid:int,plan_id:int,line_id:int,data:LineIn,u=Depends(current)):
        check(eid,u,('admin','doctor'))
        with db(True) as c:
            plan=require(c,'plan_headers',eid,plan_id)
            line=require(c,'plan_lines',eid,line_id)
            if line['plan_id']!=plan_id:fail('Plan mismatch',409)
            if one(c,'SELECT id FROM invoice_lines_v2 WHERE entity_id=? AND plan_line_id=?',(eid,line_id)):fail('Already invoiced',409)
            if plan['status']!='draft':fail('Plan is not editable',409)
            enforce_tariff(c,eid,u,data)
            price,net=price_line(data)
            for doctor in (data.planned_by,data.performed_by):
                if doctor is not None:require(c,'doctors',eid,doctor)
            before=dict(line)
            c.execute('''UPDATE plan_lines SET description=?,tooth=?,planned_by=?,performed_by=?,unit=?,quantity=?,unit_price_paise=?,adjust_kind=?,adjust_mode=?,adjust_value=?,net_paise=?,billing_mode=? WHERE entity_id=? AND id=?''',(data.description,data.tooth,data.planned_by,data.performed_by,data.unit,data.quantity,price,data.adjust_kind,data.adjust_mode,data.adjust_value,net,data.billing_mode,eid,line_id))
            log(c,u,eid,'plan_line_updated','plan_line',line_id,{'before':before,'new':data.model_dump()})
            return {'id':line_id,'net_paise':net}

    @app.post('/api/entities/{eid}/v2/plans/{plan_id}/lines/{line_id}/stages')
    def add_stage(eid:int,plan_id:int,line_id:int,data:StageIn,u=Depends(current)):
        check(eid,u,('admin','doctor'))
        with db(True) as c:
            line=require(c,'plan_lines',eid,line_id)
            if line['plan_id']!=plan_id:fail('Plan mismatch',409)
            if line['billing_mode']=='package' and to_paise(data.amount)>0:fail('Package stages cannot carry extra charges',409)
            id=c.execute('INSERT INTO plan_stages(entity_id,line_id,name,sequence,amount_paise) VALUES(?,?,?,?,?)',(eid,line_id,data.name,data.sequence,to_paise(data.amount))).lastrowid
            log(c,u,eid,'plan_stage_added','stage',id)
            return {'id':id}

    def source_line(c,eid,patient_id,line_id=None,stage_id=None,estimate_line_id=None):
        if estimate_line_id:
            row=require(c,'estimate_lines_v2',eid,estimate_line_id)
            header=require(c,'estimate_headers_v2',eid,row['estimate_id'])
            if header['patient_id']!=patient_id or header['status']!='approved':fail('Estimate must be approved for this patient',409)
            if one(c,'SELECT 1 FROM invoice_lines_v2 WHERE entity_id=? AND estimate_line_id=?',(eid,estimate_line_id)):fail('Already invoiced estimate line',409)
            if row['plan_line_id'] and one(c,'SELECT 1 FROM invoice_lines_v2 WHERE entity_id=? AND plan_line_id=?',(eid,row['plan_line_id'])):fail('Plan procedure already invoiced',409)
            if row['plan_stage_id'] and one(c,'SELECT 1 FROM invoice_lines_v2 WHERE entity_id=? AND plan_stage_id=?',(eid,row['plan_stage_id'])):fail('Treatment stage already invoiced',409)
            line_id,stage_id=row['plan_line_id'],row['plan_stage_id']
            return dict(row)
        if stage_id:
            stage=require(c,'plan_stages',eid,stage_id)
            line=require(c,'plan_lines',eid,stage['line_id'])
            plan=require(c,'plan_headers',eid,line['plan_id'])
            if plan['patient_id']!=patient_id or line['billing_mode']!='stage':fail('Stage is not billable for patient',409)
            if one(c,'SELECT 1 FROM invoice_lines_v2 WHERE entity_id=? AND plan_stage_id=?',(eid,stage_id)):fail('Stage already invoiced',409)
            return {'plan_line_id':None,'plan_stage_id':stage_id,'procedure_id':line['procedure_id'],'treatment_category_id':line['treatment_category_id'],'description':line['description']+' – '+stage['name'],'planned_by':line['planned_by'],'performed_by':line['performed_by'],'unit':'stage','quantity':1,'unit_price_paise':stage['amount_paise'],'adjust_kind':'none','adjust_mode':'rs','adjust_value':'0','net_paise':stage['amount_paise']}
        line=require(c,'plan_lines',eid,line_id)
        plan=require(c,'plan_headers',eid,line['plan_id'])
        if plan['patient_id']!=patient_id or line['billing_mode']!='package':fail('Line is not package-billable for this patient',409)
        if one(c,'SELECT 1 FROM invoice_lines_v2 WHERE entity_id=? AND plan_line_id=?',(eid,line_id)):fail('Plan line already invoiced',409)
        return {'plan_line_id':line_id,'plan_stage_id':None,'procedure_id':line['procedure_id'],'treatment_category_id':line['treatment_category_id'],**{k:line[k] for k in ('description','planned_by','performed_by','unit','quantity','unit_price_paise','adjust_kind','adjust_mode','adjust_value','net_paise')}}

    def create_direct(c,eid,d,u):
        for doctor in (d.planned_by,d.performed_by):
            if doctor is not None:require(c,'doctors',eid,doctor)
        enforce_tariff(c,eid,u,d)
        price,net=price_line(d)
        category=one(c,'SELECT treatment_category_id FROM procedure_master WHERE entity_id=? AND id=?',(eid,d.procedure_id)) if d.procedure_id else None
        return {'plan_line_id':None,'plan_stage_id':None,'procedure_id':d.procedure_id,'treatment_category_id':category['treatment_category_id'] if category else None,'description':d.description,'planned_by':d.planned_by,'performed_by':d.performed_by,'unit':d.unit,'quantity':d.quantity,'unit_price_paise':price,'adjust_kind':d.adjust_kind,'adjust_mode':d.adjust_mode,'adjust_value':d.adjust_value,'net_paise':net}

    @app.get('/api/entities/{eid}/v2/estimates')
    def estimate_list(eid:int,patient_id:Optional[int]=None,u=Depends(current)):
        check(eid,u,('admin','billing','doctor'))
        with db() as c:return rows(c,'SELECT * FROM estimate_headers_v2 WHERE entity_id=? AND (? IS NULL OR patient_id=?) ORDER BY id DESC',(eid,patient_id,patient_id))

    @app.post('/api/entities/{eid}/v2/estimates')
    def make_estimate(eid:int,data:EstimateCreate,u=Depends(current)):
        check(eid,u,('admin','billing','doctor'))
        if not(data.plan_line_ids or data.stage_ids or data.direct_lines):fail('Select at least one procedure')
        if len(data.plan_line_ids)!=len(set(data.plan_line_ids)) or len(data.stage_ids)!=len(set(data.stage_ids)):fail('Duplicate source items')
        with db(True) as c:
            get_patient(c,eid,data.patient_id)
            if data.category_id:require(c,'pricing_categories',eid,data.category_id)
            no=nextnum(c,eid,'EST2')
            id=c.execute('INSERT INTO estimate_headers_v2(entity_id,patient_id,estimate_no,category_id,created_by,created_at) VALUES(?,?,?,?,?,?)',(eid,data.patient_id,no,data.category_id,u['id'],utc())).lastrowid
            lines=[source_line(c,eid,data.patient_id,line_id=x) for x in data.plan_line_ids]+[source_line(c,eid,data.patient_id,stage_id=x) for x in data.stage_ids]+[create_direct(c,eid,d,u) for d in data.direct_lines]
            for line in lines:
                lineid=c.execute('''INSERT INTO estimate_lines_v2(entity_id,estimate_id,plan_line_id,plan_stage_id,procedure_id,description,planned_by,performed_by,unit,quantity,unit_price_paise,adjust_kind,adjust_mode,adjust_value,net_paise) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(eid,id,line.get('plan_line_id'),line.get('plan_stage_id'),line.get('procedure_id'),*[line[k] for k in ('description','planned_by','performed_by','unit','quantity','unit_price_paise','adjust_kind','adjust_mode','adjust_value','net_paise')])).lastrowid
                c.execute('UPDATE estimate_lines_v2 SET treatment_category_id=? WHERE entity_id=? AND id=?',(line.get('treatment_category_id'),eid,lineid))
            log(c,u,eid,'estimate_created','estimate',id)
            return {'id':id,'estimate_no':no,'total_paise':sum(l['net_paise'] for l in lines)}

    @app.post('/api/entities/{eid}/v2/estimates/{estimate_id}/approve')
    def approve_estimate(eid:int,estimate_id:int,u=Depends(current)):
        check(eid,u,('admin','billing'))
        with db(True) as c:
            header=require(c,'estimate_headers_v2',eid,estimate_id)
            if header['status']!='draft':fail('Estimate is not draft',409)
            c.execute("UPDATE estimate_headers_v2 SET status='approved' WHERE entity_id=? AND id=?",(eid,estimate_id))
            log(c,u,eid,'estimate_approved','estimate',estimate_id)
            return {'id':estimate_id,'status':'approved'}

    @app.get('/api/entities/{eid}/v2/estimates/{estimate_id}')
    def estimate_detail(eid:int,estimate_id:int,u=Depends(current)):
        check(eid,u,('admin','billing','doctor'))
        with db() as c:
            return {'estimate':require(c,'estimate_headers_v2',eid,estimate_id),'lines':rows(c,'SELECT * FROM estimate_lines_v2 WHERE entity_id=? AND estimate_id=?',(eid,estimate_id))}

    @app.put('/api/entities/{eid}/v3/estimates/{estimate_id}/lines/{line_id}')
    def edit_estimate_line_v3(eid:int,estimate_id:int,line_id:int,data:LineIn,u=Depends(current)):
        check(eid,u,('admin','billing','doctor'))
        with db(True) as c:
            header=require(c,'estimate_headers_v2',eid,estimate_id)
            if header['status']!='draft':fail('Only draft estimates can be edited',409)
            line=require(c,'estimate_lines_v2',eid,line_id)
            if line['estimate_id']!=estimate_id:fail('Estimate line mismatch',409)
            if data.procedure_id:enforce_tariff(c,eid,u,data)
            for doctor in (data.planned_by,data.performed_by):
                if doctor is not None:require(c,'doctors',eid,doctor)
            price,net=price_line(data)
            c.execute('''UPDATE estimate_lines_v2 SET procedure_id=?,description=?,planned_by=?,performed_by=?,quantity=?,unit_price_paise=?,adjust_kind=?,adjust_mode=?,adjust_value=?,net_paise=? WHERE entity_id=? AND id=?''',(data.procedure_id,data.description,data.planned_by,data.performed_by,data.quantity,price,data.adjust_kind,data.adjust_mode,data.adjust_value,net,eid,line_id))
            cat=one(c,'SELECT treatment_category_id FROM procedure_master WHERE entity_id=? AND id=?',(eid,data.procedure_id)) if data.procedure_id else None
            c.execute('UPDATE estimate_lines_v2 SET treatment_category_id=? WHERE entity_id=? AND id=?',(cat['treatment_category_id'] if cat else None,eid,line_id))
            log(c,u,eid,'draft_estimate_line_updated','estimate_line',line_id,{'before':line,'after':data.model_dump()})
            return {'id':line_id,'net_paise':net}

    @app.post('/api/entities/{eid}/v3/estimates/{estimate_id}/lines')
    def add_estimate_line_v3(eid:int,estimate_id:int,data:LineIn,u=Depends(current)):
        check(eid,u,('admin','billing','doctor'))
        with db(True) as c:
            h=require(c,'estimate_headers_v2',eid,estimate_id)
            if h['status']!='draft':fail('Only draft estimates can be edited',409)
            if not data.procedure_id:fail('Select a procedure from master')
            line=create_direct(c,eid,data,u)
            id=c.execute('''INSERT INTO estimate_lines_v2(entity_id,estimate_id,procedure_id,description,planned_by,performed_by,unit,quantity,unit_price_paise,adjust_kind,adjust_mode,adjust_value,net_paise) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(eid,estimate_id,line.get('procedure_id'),*[line[k] for k in ('description','planned_by','performed_by','unit','quantity','unit_price_paise','adjust_kind','adjust_mode','adjust_value','net_paise')])).lastrowid
            c.execute('UPDATE estimate_lines_v2 SET treatment_category_id=? WHERE entity_id=? AND id=?',(line.get('treatment_category_id'),eid,id))
            log(c,u,eid,'draft_estimate_line_added','estimate_line',id)
            return {'id':id}

    @app.delete('/api/entities/{eid}/v3/estimates/{estimate_id}/lines/{line_id}')
    def delete_estimate_line_v3(eid:int,estimate_id:int,line_id:int,u=Depends(current)):
        check(eid,u,('admin','billing','doctor'))
        with db(True) as c:
            h=require(c,'estimate_headers_v2',eid,estimate_id)
            if h['status']!='draft':fail('Only draft estimates can be edited',409)
            row=require(c,'estimate_lines_v2',eid,line_id)
            if row['estimate_id']!=estimate_id:fail('Estimate line mismatch',409)
            if c.execute('SELECT COUNT(*) FROM estimate_lines_v2 WHERE entity_id=? AND estimate_id=?',(eid,estimate_id)).fetchone()[0]<=1:fail('Estimate must have at least one line',409)
            c.execute('DELETE FROM estimate_lines_v2 WHERE entity_id=? AND id=?',(eid,line_id))
            log(c,u,eid,'draft_estimate_line_removed','estimate_line',line_id,{'before':row})
            return {'removed':line_id}

    @app.get('/api/entities/{eid}/v3/invoices/{invoice_id}/report')
    def invoice_report_v3(eid:int,invoice_id:int,u=Depends(current)):
        check(eid,u,('admin','billing','doctor','viewer'))
        with db() as c:
            i,balance=billed(c,eid,invoice_id)
            patient=require(c,'patients',eid,i['patient_id'])
            entity=one(c,'SELECT * FROM entities WHERE id=?',(eid,))
            receipts=rows(c,"""SELECT a.id,a.amount_paise,r.receipt_no,r.created_at,r.method,r.id receipt_id
             FROM allocations a JOIN receipts r ON a.entity_id=r.entity_id AND a.receipt_id=r.id
             WHERE a.entity_id=? AND a.invoice_id=? AND NOT EXISTS (SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=r.entity_id AND rr.receipt_id=r.id)
             ORDER BY a.id""",(eid,invoice_id))
            return {'invoice':i,'entity':{'id':entity['id'],'name':entity['name']},'patient':{'id':patient['id'],'name':patient['name'],'uhid':patient['uhid']},
             'lines':rows(c,'SELECT * FROM invoice_lines_v2 WHERE entity_id=? AND invoice_id=? ORDER BY id',(eid,invoice_id)),
             'receipts':receipts,'writeoffs':rows(c,'SELECT * FROM financial_writeoffs WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)),
             'credits':rows(c,'SELECT * FROM credit_notes WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)),
             'balance_paise':balance,'status':(one(c,'SELECT status FROM invoice_headers_v2 WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)) or {}).get('status','legacy')}

    @app.get('/api/entities/{eid}/v2/invoices')
    def invoices_v2(eid:int,patient_id:Optional[int]=None,u=Depends(current)):
        check(eid,u)
        with db() as c:return rows(c,'''SELECT i.*,m.status FROM invoice_headers_v2 m JOIN invoices i ON i.entity_id=m.entity_id AND i.id=m.invoice_id WHERE m.entity_id=? AND (? IS NULL OR i.patient_id=?) ORDER BY i.id DESC''',(eid,patient_id,patient_id))

    @app.get('/api/entities/{eid}/v2/invoices/{invoice_id}')
    def invoice_detail(eid:int,invoice_id:int,u=Depends(current)):
        check(eid,u)
        with db() as c:
            i,bal=billed(c,eid,invoice_id)
            return {'invoice':i,'meta':one(c,'SELECT * FROM invoice_headers_v2 WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)),'lines':rows(c,'SELECT * FROM invoice_lines_v2 WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)),'balance_paise':bal}

    @app.post('/api/entities/{eid}/v2/invoices')
    def new_invoice(eid:int,data:InvoiceCreate,u=Depends(current)):
        check(eid,u)
        if not(data.plan_line_ids or data.stage_ids or data.estimate_line_ids or data.direct_lines):fail('Select one or more invoice items')
        if any(len(x)!=len(set(x)) for x in (data.plan_line_ids,data.stage_ids,data.estimate_line_ids)):fail('Duplicate item selection')
        with db(True) as c:
            get_patient(c,eid,data.patient_id)
            if data.category_id:require(c,'pricing_categories',eid,data.category_id)
            # Avoid direct source and estimate source of the same planned procedure in a single invoice.
            lines=[(source_line(c,eid,data.patient_id,line_id=x),None) for x in data.plan_line_ids]+[(source_line(c,eid,data.patient_id,stage_id=x),None) for x in data.stage_ids]+[(source_line(c,eid,data.patient_id,estimate_line_id=x),x) for x in data.estimate_line_ids]+[(create_direct(c,eid,d,u),None) for d in data.direct_lines]
            used=set()
            for line,estimate_line in lines:
                key=('stage',line.get('plan_stage_id')) if line.get('plan_stage_id') else ('line',line.get('plan_line_id')) if line.get('plan_line_id') else None
                if key and key in used:fail('Procedure selected twice',409)
                if key:used.add(key)
            no=nextnum(c,eid,'INV')
            total=sum(line['net_paise'] for line,_ in lines)
            iid=c.execute('INSERT INTO invoices(entity_id,invoice_no,patient_id,total_paise,description,created_at) VALUES(?,?,?,?,?,?)',(eid,no,data.patient_id,total,'Procedure invoice',utc())).lastrowid
            c.execute('INSERT INTO invoice_headers_v2(entity_id,invoice_id,category_id,created_by,created_at) VALUES(?,?,?,?,?)',(eid,iid,data.category_id,u['id'],utc()))
            for line,est_line in lines:
                invoice_line_id=c.execute('''INSERT INTO invoice_lines_v2(entity_id,invoice_id,estimate_line_id,plan_line_id,plan_stage_id,description,planned_by,performed_by,unit,quantity,unit_price_paise,adjust_kind,adjust_mode,adjust_value,net_paise,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(eid,iid,est_line,line.get('plan_line_id'),line.get('plan_stage_id'),*[line[k] for k in ('description','planned_by','performed_by','unit','quantity','unit_price_paise','adjust_kind','adjust_mode','adjust_value','net_paise')],utc())).lastrowid
                c.execute('UPDATE invoice_lines_v2 SET treatment_category_id=?,procedure_id=? WHERE entity_id=? AND id=?',(line.get('treatment_category_id'),line.get('procedure_id'),eid,invoice_line_id))
            log(c,u,eid,'invoice_draft_created','invoice',iid)
            return {'id':iid,'invoice_no':no,'total_paise':total,'status':'draft'}

    @app.post('/api/entities/{eid}/v2/invoices/{invoice_id}/issue')
    def issue_invoice(eid:int,invoice_id:int,u=Depends(current)):
        check(eid,u)
        with db(True) as c:
            m=one(c,'SELECT * FROM invoice_headers_v2 WHERE entity_id=? AND invoice_id=?',(eid,invoice_id))
            if not m or m['status']!='draft':fail('Invoice is not an editable draft',409)
            i,b=billed(c,eid,invoice_id)
            if i['total_paise']<=0:fail('Cannot issue zero-value invoice',409)
            c.execute("UPDATE invoice_headers_v2 SET status='issued' WHERE entity_id=? AND invoice_id=?",(eid,invoice_id))
            log(c,u,eid,'invoice_issued','invoice',invoice_id)
            return {'id':invoice_id,'status':'issued'}

    @app.put('/api/entities/{eid}/v2/invoices/{invoice_id}/lines/{line_id}')
    def edit_invoice_line(eid:int,invoice_id:int,line_id:int,data:LineIn,u=Depends(current)):
        check(eid,u)
        with db(True) as c:
            m=one(c,'SELECT * FROM invoice_headers_v2 WHERE entity_id=? AND invoice_id=?',(eid,invoice_id))
            if not m or m['status']!='draft':fail('Issued invoices require credit/correction',409)
            line=require(c,'invoice_lines_v2',eid,line_id)
            if line['invoice_id']!=invoice_id:fail('Invoice item mismatch',409)
            enforce_tariff(c,eid,u,data)
            price,net=price_line(data)
            c.execute('''UPDATE invoice_lines_v2 SET procedure_id=?,description=?,planned_by=?,performed_by=?,unit=?,quantity=?,unit_price_paise=?,adjust_kind=?,adjust_mode=?,adjust_value=?,net_paise=? WHERE entity_id=? AND id=?''',(data.procedure_id,data.description,data.planned_by,data.performed_by,data.unit,data.quantity,price,data.adjust_kind,data.adjust_mode,data.adjust_value,net,eid,line_id))
            total=c.execute('SELECT SUM(net_paise) FROM invoice_lines_v2 WHERE entity_id=? AND invoice_id=?',(eid,invoice_id)).fetchone()[0]
            c.execute('UPDATE invoices SET total_paise=? WHERE entity_id=? AND id=?',(total,eid,invoice_id))
            log(c,u,eid,'draft_invoice_line_edited','invoice_line',line_id,{'before':line,'after':data.model_dump()})
            return {'id':line_id,'invoice_total_paise':total}

    @app.post('/api/entities/{eid}/v2/advances')
    def collect_advance(eid:int,data:AdvanceIn,u=Depends(current)):
        check(eid,u)
        if data.method not in ('cash','upi','card','bank','other'):fail('Invalid payment method')
        amount=to_paise(data.amount)
        if amount<=0:fail('Positive amount required')
        with db(True) as c:
            get_patient(c,eid,data.patient_id)
            no=nextnum(c,eid,'ADV')
            rid=c.execute('INSERT INTO receipts(entity_id,receipt_no,patient_id,amount_paise,method,reference,created_at) VALUES(?,?,?,?,?,?,?)',(eid,no,data.patient_id,amount,data.method,data.reference,utc())).lastrowid
            log(c,u,eid,'advance_collected','receipt',rid)
            return {'id':rid,'receipt_no':no,'available_paise':amount}

    @app.post('/api/entities/{eid}/v2/advances/allocate')
    def apply_advance(eid:int,data:AdvanceAllocate,u=Depends(current)):
        check(eid,u)
        amount=to_paise(data.amount)
        if amount<=0:fail('Positive allocation required')
        with db(True) as c:
            r=require(c,'receipts',eid,data.receipt_id)
            i,balance=billed(c,eid,data.invoice_id)
            if r['patient_id']!=i['patient_id']:fail('Patient mismatch',409)
            if amount>balance or amount>available(c,eid,data.receipt_id):fail('Exceeds invoice or advance balance',409)
            # Draft v2 invoice is not an eligible receivable.
            meta=one(c,'SELECT status FROM invoice_headers_v2 WHERE entity_id=? AND invoice_id=?',(eid,data.invoice_id))
            if meta and meta['status']!='issued':fail('Issue the invoice first',409)
            aid=c.execute('INSERT INTO allocations(entity_id,receipt_id,invoice_id,amount_paise) VALUES(?,?,?,?)',(eid,r['id'],i['id'],amount)).lastrowid
            log(c,u,eid,'advance_allocated','allocation',aid)
            return {'id':aid,'remaining_advance_paise':available(c,eid,r['id'])}

    @app.post('/api/entities/{eid}/v2/advances/refund')
    def refund_advance(eid:int,data:AdvanceRefund,u=Depends(current)):
        check(eid,u,('admin',))
        amount=to_paise(data.amount)
        if amount<=0:fail('Positive refund required')
        with db(True) as c:
            require(c,'receipts',eid,data.receipt_id)
            if amount>available(c,eid,data.receipt_id):fail('Refund exceeds available advance',409)
            id=c.execute('INSERT INTO advance_refunds_v2(entity_id,receipt_id,amount_paise,reason,method,performed_by,created_at) VALUES(?,?,?,?,?,?,?)',(eid,data.receipt_id,amount,data.reason,data.method,u['id'],utc())).lastrowid
            log(c,u,eid,'advance_refund_recorded','refund',id)
            return {'id':id,'remaining_paise':available(c,eid,data.receipt_id)}

    @app.post('/api/v2/superadmin/advance-transfer')
    def transfer_advance(data:AdvanceTransfer,u=Depends(current)):
        if not u['is_superadmin']:fail('Super Admin access required',403)
        if data.source_entity_id==data.dest_entity_id:fail('Use allocation for transfers within same entity')
        amount=to_paise(data.amount)
        if amount<=0:fail('Positive transfer required')
        with db(True) as c:
            r=require(c,'receipts',data.source_entity_id,data.source_receipt_id)
            get_patient(c,data.dest_entity_id,data.dest_patient_id)
            if amount>available(c,data.source_entity_id,r['id']):fail('Insufficient available advance',409)
            no=nextnum(c,data.dest_entity_id,'ADV')
            drid=c.execute('INSERT INTO receipts(entity_id,receipt_no,patient_id,amount_paise,method,reference,created_at) VALUES(?,?,?,?,?,?,?)',(data.dest_entity_id,no,data.dest_patient_id,amount,'other',f'Inter-entity transfer from {data.source_entity_id}/{r["id"]}',utc())).lastrowid
            id=c.execute('''INSERT INTO advance_transfers_v2(source_entity_id,source_receipt_id,dest_entity_id,dest_patient_id,dest_receipt_id,amount_paise,reason,performed_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)''',(data.source_entity_id,r['id'],data.dest_entity_id,data.dest_patient_id,drid,amount,data.reason,u['id'],utc())).lastrowid
            log(c,u,data.source_entity_id,'advance_transfer_out','transfer',id)
            log(c,u,data.dest_entity_id,'advance_transfer_in','transfer',id)
            return {'id':id,'dest_receipt_id':drid,'remaining_source_paise':available(c,data.source_entity_id,r['id'])}

    @app.post('/api/entities/{eid}/v2/writeoffs')
    def writeoff(eid:int,data:WriteoffIn,u=Depends(current)):
        check(eid,u,('admin',))
        amount=to_paise(data.amount)
        if amount<=0:fail('Positive write-off required')
        with db(True) as c:
            invoice,balance=billed(c,eid,data.invoice_id)
            meta=one(c,'SELECT status FROM invoice_headers_v2 WHERE entity_id=? AND invoice_id=?',(eid,data.invoice_id))
            if meta and meta['status']!='issued':fail('Issue invoice before write-off',409)
            if amount>balance:fail('Write-off exceeds outstanding',409)
            id=c.execute('INSERT INTO financial_writeoffs(entity_id,invoice_id,amount_paise,reason,performed_by,created_at) VALUES(?,?,?,?,?,?)',(eid,data.invoice_id,amount,data.reason,u['id'],utc())).lastrowid
            log(c,u,eid,'writeoff_posted','writeoff',id)
            return {'id':id,'balance_paise':billed(c,eid,data.invoice_id)[1]}

    @app.get('/api/entities/{eid}/v2/patients/{pid}/finances')
    def patient_finances(eid:int,pid:int,u=Depends(current)):
        check(eid,u)
        with db() as c:
            get_patient(c,eid,pid)
            invoices=rows(c,"""SELECT i.id,i.invoice_no FROM invoices i LEFT JOIN invoice_headers_v2 m ON m.entity_id=i.entity_id AND m.invoice_id=i.id WHERE i.entity_id=? AND i.patient_id=? AND (m.status IS NULL OR m.status='issued')""",(eid,pid))
            balances=[{**i,'balance_paise':billed(c,eid,i['id'])[1]} for i in invoices]
            receipts=rows(c,'SELECT id,receipt_no FROM receipts WHERE entity_id=? AND patient_id=?',(eid,pid))
            advances=[{**r,'available_paise':available(c,eid,r['id'])} for r in receipts]
            return {'amount_to_collect_paise':sum(i['balance_paise'] for i in balances),'available_advance_paise':sum(r['available_paise'] for r in advances),'invoices':balances,'advance_ledger':advances}

    @app.get('/api/entities/{eid}/v2/groups')
    def list_groups(eid:int,u=Depends(current)):
        check(eid,u,('admin',))
        with db() as c:
            result=rows(c,'SELECT * FROM permission_groups_v2 WHERE entity_id=? AND active=1',(eid,))
            for x in result:x['permissions']=[r['permission'] for r in rows(c,'SELECT permission FROM group_permissions_v2 WHERE entity_id=? AND group_id=?',(eid,x['id']))]
            return result

    @app.post('/api/entities/{eid}/v2/groups')
    def add_group(eid:int,data:GroupIn,u=Depends(current)):
        check(eid,u,('admin',))
        if not set(data.permissions).issubset(ALLOWED_PERMISSIONS):fail('Unknown permission')
        with db(True) as c:
            id=c.execute('INSERT INTO permission_groups_v2(entity_id,name) VALUES(?,?)',(eid,data.name)).lastrowid
            for perm in set(data.permissions):c.execute('INSERT INTO group_permissions_v2(entity_id,group_id,permission) VALUES(?,?,?)',(eid,id,perm))
            log(c,u,eid,'group_created','group',id)
            return {'id':id}

    @app.get('/api/v2/superadmin/users/{user_id}/assignments')
    def get_assignments(user_id:int,u=Depends(current)):
        if not u['is_superadmin']:fail('Super Admin required',403)
        with db() as c:
            user=one(c,'SELECT id,is_superadmin FROM users WHERE id=? AND active=1',(user_id,))
            if not user or user['is_superadmin']:fail('User is not eligible',404)
            members=rows(c,'SELECT entity_id,role FROM memberships WHERE user_id=?',(user_id,))
            entity_roles={}
            entity_groups={}
            for member in members:
                eid=member['entity_id']
                roles=rows(c,'SELECT role FROM membership_roles_v2 WHERE user_id=? AND entity_id=?',(user_id,eid))
                entity_roles[eid]=[r['role'] for r in roles] or [member['role']]
                entity_groups[eid]=[r['group_id'] for r in rows(c,'SELECT group_id FROM membership_groups_v2 WHERE user_id=? AND entity_id=?',(user_id,eid))]
            return {'user_id':user_id,'entity_roles':entity_roles,'entity_groups':entity_groups}

    @app.put('/api/v2/superadmin/users/{user_id}/assignments')
    def update_assignments(user_id:int,data:AssignIn,u=Depends(current)):
        if not u['is_superadmin']:fail('Super Admin required',403)
        if u['id']==user_id:fail('Cannot change own access using this screen',409)
        if not data.entity_roles:fail('Choose at least one entity')
        with db(True) as c:
            user=one(c,'SELECT id,is_superadmin FROM users WHERE id=? AND active=1',(user_id,))
            if not user or user['is_superadmin']:fail('User is not eligible',409)
            for eid,roles in data.entity_roles.items():
                if not roles or not set(roles).issubset(ALLOWED_ROLES):fail('Invalid roles')
                if not one(c,'SELECT id FROM entities WHERE id=? AND active=1',(eid,)):fail('Unknown entity')
                for gid in data.entity_groups.get(eid,[]):require(c,'permission_groups_v2',eid,gid)
            previous=rows(c,'SELECT * FROM memberships WHERE user_id=?',(user_id,))
            c.execute('DELETE FROM membership_groups_v2 WHERE user_id=?',(user_id,))
            c.execute('DELETE FROM membership_roles_v2 WHERE user_id=?',(user_id,))
            c.execute('DELETE FROM memberships WHERE user_id=?',(user_id,))
            for eid,roles in data.entity_roles.items():
                c.execute('INSERT INTO memberships(user_id,entity_id,role) VALUES(?,?,?)',(user_id,eid,roles[0]))
                for role in set(roles):c.execute('INSERT INTO membership_roles_v2(entity_id,user_id,role) VALUES(?,?,?)',(eid,user_id,role))
                for gid in set(data.entity_groups.get(eid,[])):c.execute('INSERT INTO membership_groups_v2(entity_id,user_id,group_id) VALUES(?,?,?)',(eid,user_id,gid))
            c.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            for eid in set([p['entity_id'] for p in previous]+list(data.entity_roles)):
                log(c,u,eid,'staff_assignments_changed','user',user_id,{'old':previous,'new_roles':data.entity_roles.get(eid,[]),'groups':data.entity_groups.get(eid,[])})
            return {'user_id':user_id,'entities':list(data.entity_roles),'sessions_revoked':True}

    @app.get('/api/v2/superadmin/users')
    def eligible_users(u=Depends(current)):
        if not u['is_superadmin']:fail('Super Admin required',403)
        with db() as c:return rows(c,'SELECT id,username,active FROM users WHERE is_superadmin=0 ORDER BY username')

    @app.get('/api/v2/superadmin/entities')
    def super_entities(u=Depends(current)):
        if not u['is_superadmin']:fail('Super Admin required',403)
        with db() as c:return rows(c,'SELECT id,name,code FROM entities WHERE active=1 ORDER BY name')
