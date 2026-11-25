"""Rajan Dental development API. SQLite MVP; harden and migrate before production."""
import os, sqlite3, secrets, hashlib, hmac, json, re, uuid, base64, struct, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse

BASE=Path(__file__).parent
DB=Path(os.getenv('DENTAL_DB', str(BASE/'development.db')))
app=FastAPI(title='Rajan Dental API',version='2.4.0-dev')
DOCUMENT_ROOT=Path(os.getenv('DENTAL_DOCUMENT_ROOT',str(BASE/'private_documents'))).resolve()
MAX_UPLOAD_BYTES=10*1024*1024
app.add_middleware(CORSMiddleware,allow_origins=[os.getenv('FRONTEND_ORIGIN','http://localhost:5173')],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

def utc():return datetime.now(timezone.utc).isoformat()
def fail(msg,status=400):raise HTTPException(status_code=status,detail=msg)
@contextmanager
def db(write=False):
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(DB),timeout=15,isolation_level=None)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=15000')
    try:
        if write:c.execute('BEGIN IMMEDIATE')
        yield c
        if write:c.execute('COMMIT')
    except Exception:
        if write:c.execute('ROLLBACK')
        raise
    finally:c.close()
def rows(c,q,p=()):return [dict(r) for r in c.execute(q,p).fetchall()]
def one(c,q,p=()):
    x=c.execute(q,p).fetchone();return dict(x) if x else None

def init():
 with db() as c:
  c.executescript('''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,is_superadmin INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures(username TEXT NOT NULL,attempted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_mfa(user_id INTEGER PRIMARY KEY REFERENCES users(id),encrypted_secret TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),last_step INTEGER NOT NULL DEFAULT -1);
CREATE TABLE IF NOT EXISTS recorded_refunds(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,receipt_id INTEGER NOT NULL,refund_no TEXT NOT NULL,amount_paise INTEGER NOT NULL CHECK(amount_paise>0),method TEXT NOT NULL,reference TEXT NOT NULL,reason TEXT NOT NULL,recorded_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,UNIQUE(entity_id,refund_no),FOREIGN KEY(entity_id,receipt_id) REFERENCES receipts(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_refunds_receipt ON recorded_refunds(entity_id,receipt_id);
CREATE INDEX IF NOT EXISTS idx_login_failures ON login_failures(username,attempted_at);
CREATE TABLE IF NOT EXISTS entities(id INTEGER PRIMARY KEY,name TEXT NOT NULL,code TEXT UNIQUE NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('clinic','trust','other')),chairs INTEGER NOT NULL CHECK(chairs>=0),ots INTEGER NOT NULL CHECK(ots>=0),active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memberships(user_id INTEGER NOT NULL REFERENCES users(id),entity_id INTEGER NOT NULL REFERENCES entities(id),role TEXT NOT NULL CHECK(role IN ('admin','reception','doctor','billing','viewer')),PRIMARY KEY(user_id,entity_id));
CREATE TABLE IF NOT EXISTS counters(entity_id INTEGER NOT NULL REFERENCES entities(id),category TEXT NOT NULL,value INTEGER NOT NULL,PRIMARY KEY(entity_id,category));
CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),uhid TEXT NOT NULL,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',dob TEXT,notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(entity_id,uhid),UNIQUE(entity_id,id));
CREATE TABLE IF NOT EXISTS registrations(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),temp_id TEXT NOT NULL,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',dob TEXT,notes TEXT NOT NULL DEFAULT '',patient_id INTEGER,created_at TEXT NOT NULL,UNIQUE(entity_id,temp_id),UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id));
CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(entity_id,id));
CREATE TABLE IF NOT EXISTS resources(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),name TEXT NOT NULL,type TEXT NOT NULL CHECK(type IN ('chair','ot')),active INTEGER NOT NULL DEFAULT 1,UNIQUE(entity_id,id),UNIQUE(entity_id,name));
CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),patient_id INTEGER,registration_id INTEGER,doctor_id INTEGER NOT NULL,resource_id INTEGER,start_time TEXT NOT NULL,end_time TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'booked',reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id),FOREIGN KEY(entity_id,registration_id) REFERENCES registrations(entity_id,id),FOREIGN KEY(entity_id,doctor_id) REFERENCES doctors(entity_id,id),FOREIGN KEY(entity_id,resource_id) REFERENCES resources(entity_id,id),CHECK(start_time<end_time),CHECK(patient_id IS NOT NULL OR registration_id IS NOT NULL));
CREATE INDEX IF NOT EXISTS idx_appointments_slot ON appointments(entity_id,start_time,end_time);
CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),visit_no TEXT NOT NULL,patient_id INTEGER NOT NULL,appointment_id INTEGER,doctor_id INTEGER,complaint TEXT NOT NULL DEFAULT '',diagnosis TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(entity_id,visit_no),UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id),FOREIGN KEY(entity_id,appointment_id) REFERENCES appointments(entity_id,id),FOREIGN KEY(entity_id,doctor_id) REFERENCES doctors(entity_id,id));
CREATE TABLE IF NOT EXISTS treatments(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),visit_id INTEGER NOT NULL,description TEXT NOT NULL,tooth TEXT NOT NULL DEFAULT '',planned_by INTEGER,performed_by INTEGER,status TEXT NOT NULL DEFAULT 'planned',amount_paise INTEGER NOT NULL DEFAULT 0,UNIQUE(entity_id,id),FOREIGN KEY(entity_id,visit_id) REFERENCES visits(entity_id,id),FOREIGN KEY(entity_id,planned_by) REFERENCES doctors(entity_id,id),FOREIGN KEY(entity_id,performed_by) REFERENCES doctors(entity_id,id));
CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),invoice_no TEXT NOT NULL,patient_id INTEGER NOT NULL,total_paise INTEGER NOT NULL CHECK(total_paise>=0),description TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(entity_id,invoice_no),UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id));
CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),receipt_no TEXT NOT NULL,patient_id INTEGER NOT NULL,amount_paise INTEGER NOT NULL CHECK(amount_paise>0),method TEXT NOT NULL,reference TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(entity_id,receipt_no),UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id));
CREATE TABLE IF NOT EXISTS allocations(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),receipt_id INTEGER NOT NULL,invoice_id INTEGER NOT NULL,amount_paise INTEGER NOT NULL CHECK(amount_paise>0),FOREIGN KEY(entity_id,receipt_id) REFERENCES receipts(entity_id,id),FOREIGN KEY(entity_id,invoice_id) REFERENCES invoices(entity_id,id));
-- Defense in depth: reject invalid direct SQL allocations as well as API requests.
CREATE TRIGGER IF NOT EXISTS allocations_validate_insert BEFORE INSERT ON allocations
BEGIN
 SELECT CASE WHEN NOT EXISTS(
  SELECT 1 FROM receipts r JOIN invoices i
   ON i.entity_id=r.entity_id AND i.entity_id=NEW.entity_id
  WHERE r.id=NEW.receipt_id AND i.id=NEW.invoice_id AND r.patient_id=i.patient_id
 ) THEN RAISE(ABORT,'Receipt/invoice patient mismatch') END;
 SELECT CASE WHEN (SELECT COALESCE(SUM(amount_paise),0) FROM allocations
   WHERE entity_id=NEW.entity_id AND receipt_id=NEW.receipt_id)+NEW.amount_paise >
   (SELECT amount_paise FROM receipts WHERE entity_id=NEW.entity_id AND id=NEW.receipt_id)
 THEN RAISE(ABORT,'Receipt overallocation') END;
END;
CREATE TRIGGER IF NOT EXISTS allocations_validate_update BEFORE UPDATE ON allocations
BEGIN
 SELECT CASE WHEN NOT EXISTS(
  SELECT 1 FROM receipts r JOIN invoices i
   ON i.entity_id=r.entity_id AND i.entity_id=NEW.entity_id
  WHERE r.id=NEW.receipt_id AND i.id=NEW.invoice_id AND r.patient_id=i.patient_id
 ) THEN RAISE(ABORT,'Receipt/invoice patient mismatch') END;
 SELECT CASE WHEN (SELECT COALESCE(SUM(amount_paise),0) FROM allocations
   WHERE entity_id=NEW.entity_id AND receipt_id=NEW.receipt_id AND id<>OLD.id)+NEW.amount_paise >
   (SELECT amount_paise FROM receipts WHERE entity_id=NEW.entity_id AND id=NEW.receipt_id)
 THEN RAISE(ABORT,'Receipt overallocation') END;
END;
CREATE TABLE IF NOT EXISTS doctor_slots(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),doctor_id INTEGER NOT NULL,weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),start_minute INTEGER NOT NULL CHECK(start_minute BETWEEN 0 AND 1439),end_minute INTEGER NOT NULL CHECK(end_minute BETWEEN 1 AND 1440),slot_minutes INTEGER NOT NULL CHECK(slot_minutes BETWEEN 5 AND 240),active INTEGER NOT NULL DEFAULT 1,CHECK(end_minute>start_minute),FOREIGN KEY(entity_id,doctor_id) REFERENCES doctors(entity_id,id));
CREATE TABLE IF NOT EXISTS doctor_time_off(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),doctor_id INTEGER NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',FOREIGN KEY(entity_id,doctor_id) REFERENCES doctors(entity_id,id),CHECK(start_time<end_time));
CREATE TABLE IF NOT EXISTS estimates(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),estimate_no TEXT NOT NULL,patient_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','invoiced')),total_paise INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(entity_id,estimate_no),UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id));
CREATE TABLE IF NOT EXISTS estimate_items(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),estimate_id INTEGER NOT NULL,treatment_id INTEGER NOT NULL,description TEXT NOT NULL,amount_paise INTEGER NOT NULL CHECK(amount_paise>=0),FOREIGN KEY(entity_id,estimate_id) REFERENCES estimates(entity_id,id),FOREIGN KEY(entity_id,treatment_id) REFERENCES treatments(entity_id,id),UNIQUE(entity_id,estimate_id,treatment_id));
CREATE UNIQUE INDEX IF NOT EXISTS idx_treatment_entity_pk ON treatments(entity_id,id);
CREATE TABLE IF NOT EXISTS estimate_conversions(estimate_id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),invoice_id INTEGER NOT NULL,FOREIGN KEY(entity_id,estimate_id) REFERENCES estimates(entity_id,id),FOREIGN KEY(entity_id,invoice_id) REFERENCES invoices(entity_id,id));
CREATE TABLE IF NOT EXISTS tooth_findings(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),patient_id INTEGER NOT NULL,visit_id INTEGER NOT NULL,tooth_code TEXT NOT NULL,surface TEXT NOT NULL DEFAULT 'whole',condition TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',recorded_by INTEGER REFERENCES users(id),created_at TEXT NOT NULL,UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id),FOREIGN KEY(entity_id,visit_id) REFERENCES visits(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_tooth_patient ON tooth_findings(entity_id,patient_id,tooth_code);
CREATE TABLE IF NOT EXISTS treatment_sessions(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),treatment_id INTEGER NOT NULL,visit_id INTEGER NOT NULL,performed_by INTEGER NOT NULL,performed_at TEXT NOT NULL,procedure_notes TEXT NOT NULL,progress TEXT NOT NULL CHECK(progress IN ('in_progress','completed')),created_at TEXT NOT NULL,UNIQUE(entity_id,id),FOREIGN KEY(entity_id,treatment_id) REFERENCES treatments(entity_id,id),FOREIGN KEY(entity_id,visit_id) REFERENCES visits(entity_id,id),FOREIGN KEY(entity_id,performed_by) REFERENCES doctors(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_sessions_treatment ON treatment_sessions(entity_id,treatment_id);
CREATE TABLE IF NOT EXISTS estimate_item_invoices(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),estimate_id INTEGER NOT NULL,estimate_item_id INTEGER NOT NULL UNIQUE,invoice_id INTEGER NOT NULL,amount_paise INTEGER NOT NULL CHECK(amount_paise>=0),FOREIGN KEY(entity_id,estimate_id) REFERENCES estimates(entity_id,id),FOREIGN KEY(entity_id,invoice_id) REFERENCES invoices(entity_id,id),FOREIGN KEY(estimate_item_id) REFERENCES estimate_items(id));
CREATE INDEX IF NOT EXISTS idx_item_invoices_estimate ON estimate_item_invoices(entity_id,estimate_id);
CREATE TABLE IF NOT EXISTS patient_consents(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),patient_id INTEGER NOT NULL,visit_id INTEGER,procedure_description TEXT NOT NULL,consent_version TEXT NOT NULL,consent_text TEXT NOT NULL,acknowledged_by TEXT NOT NULL,acknowledged_at TEXT NOT NULL,recorded_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id),FOREIGN KEY(entity_id,visit_id) REFERENCES visits(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_patient_consents ON patient_consents(entity_id,patient_id);
CREATE TABLE IF NOT EXISTS patient_documents(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),patient_id INTEGER NOT NULL,visit_id INTEGER,category TEXT NOT NULL,original_name TEXT NOT NULL,stored_name TEXT NOT NULL UNIQUE,mime_type TEXT NOT NULL,size_bytes INTEGER NOT NULL CHECK(size_bytes>0),sha256 TEXT NOT NULL,uploaded_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id),FOREIGN KEY(entity_id,visit_id) REFERENCES visits(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_documents_patient ON patient_documents(entity_id,patient_id,created_at);
CREATE TABLE IF NOT EXISTS clinical_notes(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),patient_id INTEGER NOT NULL,visit_id INTEGER NOT NULL,author_user_id INTEGER NOT NULL REFERENCES users(id),body TEXT NOT NULL CHECK(length(trim(body))>0),status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','signed')),signed_at TEXT,created_at TEXT NOT NULL,UNIQUE(entity_id,id),FOREIGN KEY(entity_id,patient_id) REFERENCES patients(entity_id,id),FOREIGN KEY(entity_id,visit_id) REFERENCES visits(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_clinical_notes_visit ON clinical_notes(entity_id,patient_id,visit_id);
CREATE TABLE IF NOT EXISTS clinical_note_addenda(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES entities(id),note_id INTEGER NOT NULL,author_user_id INTEGER NOT NULL REFERENCES users(id),body TEXT NOT NULL CHECK(length(trim(body))>0),reason TEXT NOT NULL CHECK(length(trim(reason))>0),created_at TEXT NOT NULL,FOREIGN KEY(entity_id,note_id) REFERENCES clinical_notes(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_addenda_note ON clinical_note_addenda(entity_id,note_id);
CREATE TABLE IF NOT EXISTS doctor_booking_rules(entity_id INTEGER NOT NULL,doctor_id INTEGER NOT NULL,enforce_slots INTEGER NOT NULL DEFAULT 0 CHECK(enforce_slots IN (0,1)),PRIMARY KEY(entity_id,doctor_id),FOREIGN KEY(entity_id,doctor_id) REFERENCES doctors(entity_id,id));
CREATE TABLE IF NOT EXISTS clinician_links(entity_id INTEGER NOT NULL,doctor_id INTEGER NOT NULL,clinician_key TEXT NOT NULL,PRIMARY KEY(entity_id,doctor_id),FOREIGN KEY(entity_id,doctor_id) REFERENCES doctors(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_clinician_links_key ON clinician_links(clinician_key);
CREATE TABLE IF NOT EXISTS receipt_reversals(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,receipt_id INTEGER NOT NULL,reason TEXT NOT NULL,performed_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,UNIQUE(entity_id,receipt_id),FOREIGN KEY(entity_id,receipt_id) REFERENCES receipts(entity_id,id));
CREATE TABLE IF NOT EXISTS credit_notes(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,invoice_id INTEGER NOT NULL,credit_no TEXT NOT NULL,amount_paise INTEGER NOT NULL CHECK(amount_paise>0),reason TEXT NOT NULL CHECK(length(trim(reason))>=5),issued_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,UNIQUE(entity_id,id),UNIQUE(entity_id,credit_no),FOREIGN KEY(entity_id,invoice_id) REFERENCES invoices(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_credit_invoice ON credit_notes(entity_id,invoice_id);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,user_id INTEGER,entity_id INTEGER,action TEXT NOT NULL,object_type TEXT NOT NULL,object_id INTEGER,at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entity_features(entity_id INTEGER PRIMARY KEY REFERENCES entities(id),chair_ot_enabled INTEGER NOT NULL DEFAULT 0 CHECK(chair_ot_enabled IN (0,1)));
CREATE TABLE IF NOT EXISTS clinical_note_revisions(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL, note_id INTEGER NOT NULL, version INTEGER NOT NULL, doctor_id INTEGER, body TEXT NOT NULL, previous_body TEXT NOT NULL, edited_by INTEGER NOT NULL REFERENCES users(id), save_method TEXT NOT NULL CHECK(save_method IN ('auto','manual','edit')), created_at TEXT NOT NULL,UNIQUE(entity_id,note_id,version),FOREIGN KEY(entity_id,note_id) REFERENCES clinical_notes(entity_id,id), FOREIGN KEY(entity_id,doctor_id) REFERENCES doctors(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_note_revision ON clinical_note_revisions(entity_id,note_id,version);
CREATE TABLE IF NOT EXISTS visit_clinical_revisions(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL,visit_id INTEGER NOT NULL,version INTEGER NOT NULL,previous_complaint TEXT NOT NULL,previous_diagnosis TEXT NOT NULL,previous_notes TEXT NOT NULL,complaint TEXT NOT NULL,diagnosis TEXT NOT NULL,notes TEXT NOT NULL,edited_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,UNIQUE(entity_id,visit_id,version),FOREIGN KEY(entity_id,visit_id) REFERENCES visits(entity_id,id));
CREATE INDEX IF NOT EXISTS idx_visit_clinical_revisions ON visit_clinical_revisions(entity_id,visit_id,version);
''')

def password_hash(password):
 salt=secrets.token_bytes(16); val=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,310000)
 return salt.hex()+':'+val.hex()
def verify_password(password,stored):
 try:
  salt,expected=stored.split(':');got=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),310000)
  return hmac.compare_digest(got,bytes.fromhex(expected))
 except Exception:return False

def mfa_cipher():
 # An externally managed stable key is required. Rotate through a controlled migration.
 from cryptography.fernet import Fernet
 key=os.environ.get('DENTAL_MFA_FERNET_KEY')
 if not key:fail('MFA encryption key is not configured on server',503)
 try:return Fernet(key.encode())
 except Exception:fail('MFA encryption configuration is invalid',503)

def totp_at(secret,epoch=None):
 epoch=int(time.time() if epoch is None else epoch)
 counter=epoch//30
 raw=base64.b32decode(secret.upper()+'='*((-len(secret))%8))
 hashed=hmac.new(raw,struct.pack('>Q',counter),hashlib.sha1).digest()
 pos=hashed[-1]&15
 return str((int.from_bytes(hashed[pos:pos+4],'big')&0x7fffffff)%1000000).zfill(6)

def totp_step(secret,code,epoch=None):
 if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):return None
 epoch=int(time.time() if epoch is None else epoch)
 for step in (epoch//30-1,epoch//30,epoch//30+1):
  if hmac.compare_digest(totp_at(secret,step*30),code):return step
 return None

def seed_admin(username,password):
 import advanced_v02
 advanced_v02.install(db,utc)
 if len(password)<12:fail('Initial admin password must be at least 12 characters')
 with db(True) as c:
  if one(c,'SELECT id FROM users LIMIT 1'):return False
  c.execute('INSERT INTO users(username,password_hash,is_superadmin) VALUES(?,?,1)',(username,password_hash(password)))
  for name,code,kind,chairs,ots in [('Rajan Dental – Main Clinic','CL','clinic',10,2),('Charity Trust','TR','trust',3,0)]:
   cur=c.execute('INSERT INTO entities(name,code,kind,chairs,ots,created_at) VALUES(?,?,?,?,?,?)',(name,code,kind,chairs,ots,utc()))
   eid=cur.lastrowid
   for code,name in advanced_v02.DEFAULT_CATEGORIES:
    c.execute('INSERT INTO pricing_categories(entity_id,code,name,is_default) VALUES(?,?,?,?)',(eid,code,name,int(code=='regular')))
   admin_id=c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()[0]
   c.execute('INSERT INTO memberships(user_id,entity_id,role) VALUES(?,?,?)',(admin_id,eid,'admin'))
   for typ,count in [('chair',chairs),('ot',ots)]:
    for i in range(1,count+1):c.execute('INSERT INTO resources(entity_id,name,type) VALUES(?,?,?)',(eid,f'{typ.upper()} {i:02}',typ))
  return True

class Login(BaseModel):
 username:str
 password:str
 otp:Optional[str]=None
class MFAEnableIn(BaseModel):
 otp:str=Field(min_length=6,max_length=8)
class MFADisableIn(BaseModel):
 password:str
 otp:str=Field(min_length=6,max_length=8)
class RefundIn(BaseModel):
 receipt_id:int
 amount:str
 method:str
 reference:str=Field(min_length=3,max_length=200)
 reason:str=Field(min_length=5,max_length=500)
class PasswordChangeIn(BaseModel):
 current_password:str
 new_password:str=Field(min_length=12,max_length=256)
class EntityIn(BaseModel):name:str=Field(min_length=2,max_length=120);code:str=Field(min_length=2,max_length=12);kind:str='clinic';chairs:int=Field(default=0,ge=0,le=100);ots:int=Field(default=0,ge=0,le=30)
class MembershipIn(BaseModel):username:str;role:str
class MembershipRoleUpdate(BaseModel):role:str
class RegistrationIn(BaseModel):name:str=Field(min_length=2,max_length=120);phone:str='';dob:Optional[str]=None;notes:str=''
class CheckIn(BaseModel):registration_id:int;existing_patient_id:Optional[int]=None
class AppointmentIn(BaseModel):patient_id:Optional[int]=None;registration_id:Optional[int]=None;doctor_id:int;resource_id:Optional[int]=None;start_time:str;end_time:str;reason:str=''
class VisitIn(BaseModel):patient_id:int;appointment_id:Optional[int]=None;doctor_id:Optional[int]=None;complaint:str='';diagnosis:str='';notes:str=''
class VisitClinicalEditIn(BaseModel):
 complaint:str=Field(max_length=10000)
 diagnosis:str=Field(max_length=10000)
 notes:str=Field(max_length=20000)
 expected_version:int=Field(ge=0)

class TreatmentIn(BaseModel):visit_id:int;description:str;tooth:str='';planned_by:Optional[int]=None;performed_by:Optional[int]=None;status:str='planned';amount:str='0'
class InvoiceIn(BaseModel):patient_id:int;description:str;amount:str
class AllocIn(BaseModel):invoice_id:int;amount:str
class ReceiptIn(BaseModel):patient_id:int;amount:str;method:str='cash';reference:str='';allocations:list[AllocIn]=[]
class SlotIn(BaseModel):doctor_id:int;weekday:int=Field(ge=0,le=6);start_time:str;end_time:str;slot_minutes:int=Field(default=30,ge=5,le=240)
class TimeOffIn(BaseModel):doctor_id:int;start_time:str;end_time:str;reason:str=''
class EstimateIn(BaseModel):patient_id:int;treatment_ids:list[int]=Field(min_length=1)
class AppointmentStatusIn(BaseModel):status:str
class InvoiceSelectedIn(BaseModel):item_ids:list[int]=Field(min_length=1)
class StaffCreateIn(BaseModel):username:str=Field(min_length=3,max_length=60);password:str=Field(min_length=12,max_length=256);role:str='reception'
class ConsentIn(BaseModel):patient_id:int;visit_id:Optional[int]=None;procedure_description:str=Field(min_length=2,max_length=300);consent_version:str=Field(min_length=1,max_length=50);consent_text:str=Field(min_length=10,max_length=10000);acknowledged_by:str=Field(min_length=2,max_length=120);acknowledged_at:str

class BookingRulesIn(BaseModel):
 enforce_slots:bool
class ClinicianLinkIn(BaseModel):
 profiles:list[dict]=Field(min_length=2,max_length=20)
class ReceiptReverseIn(BaseModel):
 reason:str=Field(min_length=5,max_length=500)
class CreditNoteIn(BaseModel):
 invoice_id:int
 amount:str
 reason:str=Field(min_length=5,max_length=500)

class ClinicalNoteIn(BaseModel):
 patient_id:int
 visit_id:int
 body:str=Field(min_length=1,max_length=20000)
class NoteEditV24(BaseModel):
 body:str=Field(min_length=1,max_length=20000)
 doctor_id:Optional[int]=None
 expected_version:int=Field(ge=0)
 save_method:str='manual'

class NoteCreateV24(BaseModel):
 patient_id:int
 visit_id:int
 doctor_id:Optional[int]=None
 body:str=Field(min_length=1,max_length=20000)
 save_method:str='auto'

class EntityFeaturesV24(BaseModel):
 chair_ot_enabled:bool

class NoteAmendIn(BaseModel):
 body:str=Field(min_length=1,max_length=20000)
 reason:str=Field(min_length=3,max_length=500)

def cents(s):
 try:
  d=Decimal(str(s));v=d*100
  if not d.is_finite() or v!=v.to_integral_value() or v<0 or v>10**12:raise ValueError()
  return int(v)
 except (InvalidOperation,ValueError):fail('Invalid monetary amount (max two decimal places)')

def nextnum(c,eid,category):
 c.execute('INSERT INTO counters(entity_id,category,value) VALUES(?,?,1) ON CONFLICT(entity_id,category) DO UPDATE SET value=value+1',(eid,category))
 n=c.execute('SELECT value FROM counters WHERE entity_id=? AND category=?',(eid,category)).fetchone()[0]
 code=c.execute('SELECT code FROM entities WHERE id=?',(eid,)).fetchone()[0]
 return f'{code}-{category}-{n:06d}'
def audit(c,user,eid,action,obj,oid):c.execute('INSERT INTO audit(user_id,entity_id,action,object_type,object_id,at) VALUES(?,?,?,?,?,?)',(user['id'],eid,action,obj,oid,utc()))

def current(authorization:Optional[str]=Header(default=None)):
 token=(authorization or '').removeprefix('Bearer ').strip()
 if not token:fail('Login required',401)
 th=hashlib.sha256(token.encode()).hexdigest()
 with db() as c:
  u=one(c,'SELECT u.id,u.username,u.is_superadmin FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',(th,utc()))
 if not u:fail('Invalid or expired session',401)
 return u

def access(eid:int,u,allowed=('admin','reception','doctor','billing','viewer')):
 with db() as c:
  if not one(c,'SELECT id FROM entities WHERE id=? AND active=1',(eid,)):fail('Entity not found',404)
  role=one(c,'SELECT role FROM memberships WHERE entity_id=? AND user_id=?',(eid,u['id']))
  try: assigned=[r['role'] for r in rows(c,'SELECT role FROM membership_roles_v2 WHERE entity_id=? AND user_id=?',(eid,u['id']))]
  except sqlite3.OperationalError as exc:
   if 'no such table: membership_roles_v2' not in str(exc): raise
   assigned=[]
 if not role or not any(r in allowed for r in ([role['role']]+assigned)):fail('Entity access denied',403)
 return next((r for r in ([role['role']]+assigned) if r in allowed),role['role'])

def entity_user(eid:int,u=Depends(current)):access(eid,u);return u

@app.get('/api/entities/{eid}/postgres-readiness')
def postgres_readiness(eid:int,u=Depends(current)):
    """ADMIN-ONLY, READ-ONLY canary; does not expose clinical or patient records.

    Authentication and entity membership still use SQLite in this transitional build.
    This endpoint MUST NOT be used to claim PostgreSQL API cutover.
    """
    access(eid,u,('admin',))
    if os.getenv('RAJAN_ENABLE_PG_PROBE')!='1':
        fail('PostgreSQL runtime probe is disabled',503)
    try:
        import sys
        migration_path=str(BASE.parent/'migration')
        if migration_path not in sys.path:sys.path.insert(0,migration_path)
        from pg_runtime_probe import count_only
        return count_only(eid)
    except (ValueError,RuntimeError,ImportError) as exc:
        # No database credentials, raw SQL or patient details in HTTP error responses.
        fail('PostgreSQL runtime probe unavailable or security check failed',503)


# Synthetic-data PostgreSQL pilot endpoints. These NEVER replace the SQLite
# patient APIs, and they deliberately cannot feed SQLite visits or billing.
def pg_pilot_authorize(eid,u):
    access(eid,u,('admin',))
    if (os.getenv('RAJAN_ENABLE_PG_PATIENT_PILOT')!='1' or
        os.getenv('RAJAN_PG_PILOT_SYNTHETIC_ONLY')!='YES'):
        fail('PostgreSQL patient pilot disabled',503)
    with db() as c:
        entity=one(c,'SELECT code FROM entities WHERE id=? AND active=1',(eid,))
    if not entity:fail('Entity not found',404)
    return entity['code']

def pg_pilot_service():
    import sys
    path=str(BASE.parent/'migration')
    if path not in sys.path:sys.path.insert(0,path)
    from pg_patient_pilot import create_registration,check_in,list_patients,PilotError
    return create_registration,check_in,list_patients,PilotError

@app.post('/api/entities/{eid}/pg-pilot/registrations')
def pg_pilot_register(eid:int,data:RegistrationIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        create,_,_,_=pg_pilot_service()
        return create(eid,code,data.name,data.phone,data.dob,data.notes)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL pilot unavailable or rejected request',503)

@app.post('/api/entities/{eid}/pg-pilot/check-in')
def pg_pilot_checkin(eid:int,data:CheckIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        _,check,_,_=pg_pilot_service()
        return check(eid,code,data.registration_id,data.existing_patient_id)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL pilot unavailable or rejected request',503)

@app.get('/api/entities/{eid}/pg-pilot/patients')
def pg_pilot_patients(eid:int,q:str='',u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        _,_,search,_=pg_pilot_service()
        return search(eid,code,q)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL pilot unavailable or rejected request',503)

# Version 1.8: isolated synthetic pilot visit APIs; not linked to the SQLite
# appointment, invoice, or clinical modules.
class PilotVisitIn(BaseModel):
    patient_id:int=Field(gt=0)
    chief_complaint:str=Field(default='',max_length=2000)

@app.post('/api/entities/{eid}/pg-pilot/visits')
def pg_pilot_create_visit(eid:int,data:PilotVisitIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        import sys
        path=str(BASE.parent/'migration')
        if path not in sys.path:sys.path.insert(0,path)
        from pg_patient_pilot import create_visit
        return create_visit(eid,code,data.patient_id,data.chief_complaint)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL pilot unavailable or rejected request',503)

@app.get('/api/entities/{eid}/pg-pilot/patients/{patient_id}/visits')
def pg_pilot_list_visits(eid:int,patient_id:int,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        import sys
        path=str(BASE.parent/'migration')
        if path not in sys.path:sys.path.insert(0,path)
        from pg_patient_pilot import list_visits
        return list_visits(eid,code,patient_id)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL pilot unavailable or rejected request',503)

# v1.9: synthetic-only PostgreSQL appointments. The existing operational SQLite
# calendar is unchanged; these IDs must never be passed into SQLite workflows.
class PgPilotAppointmentIn(BaseModel):
    patient_id:int=Field(gt=0)
    doctor_id:int=Field(gt=0)
    resource_id:int=Field(gt=0)
    start_local:str=Field(min_length=16,max_length=16)
    duration_minutes:int=Field(default=30,ge=15,le=240)
    reason:str=Field(default='',max_length=500)

class PgPilotAppointmentStatusIn(BaseModel):
    status:str

@app.get('/api/entities/{eid}/pg-pilot/scheduling-resources')
def pg_pilot_scheduling_resources(eid:int,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        from pg_appointments_pilot import list_resources
        return list_resources(eid,code)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL scheduling pilot unavailable or rejected request',503)

@app.post('/api/entities/{eid}/pg-pilot/appointments')
def pg_pilot_book_appointment(eid:int,data:PgPilotAppointmentIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        from pg_appointments_pilot import create_appointment
        return create_appointment(eid,code,data.patient_id,data.doctor_id,data.resource_id,
                                  data.start_local,data.duration_minutes,data.reason)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL scheduling pilot unavailable or rejected request',503)
    except Exception as exc:
        # PostgreSQL exclusion violation (23P01): overlapping doctor or chair/OT.
        if getattr(exc,'sqlstate',None)=='23P01':
            fail('Doctor or chair/OT is already booked at this time',409)
        raise

@app.get('/api/entities/{eid}/pg-pilot/appointments')
def pg_pilot_get_appointments(eid:int,day:str,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        from pg_appointments_pilot import list_appointments
        return list_appointments(eid,code,day)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL scheduling pilot unavailable or rejected request',503)

@app.patch('/api/entities/{eid}/pg-pilot/appointments/{appointment_id}/status')
def pg_pilot_set_appointment_status(eid:int,appointment_id:int,data:PgPilotAppointmentStatusIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        from pg_appointments_pilot import change_appointment_status
        return change_appointment_status(eid,code,appointment_id,data.status)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL scheduling pilot unavailable or rejected request',503)


# v2.0: single synthetic PostgreSQL clinical-to-payment pilot. These endpoints
# deliberately do not use or update the operational SQLite patient workflows.
class PgPilotTreatmentIn(BaseModel):
    patient_id:int=Field(gt=0)
    visit_id:int=Field(gt=0)
    planned_by:int=Field(gt=0)
    description:str=Field(min_length=2,max_length=500)
    tooth_number:Optional[int]=None

class PgPilotInvoiceLine(BaseModel):
    treatment_id:int=Field(gt=0)
    amount:str

class PgPilotInvoiceIn(BaseModel):
    patient_id:int=Field(gt=0)
    items:list[PgPilotInvoiceLine]=Field(min_length=1,max_length=30)

class PgPilotAllocation(BaseModel):
    invoice_id:int=Field(gt=0)
    amount:str

class PgPilotReceiptIn(BaseModel):
    idempotency_key:str=Field(min_length=8,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    patient_id:int=Field(gt=0)
    amount:str
    payment_mode:str='CASH'
    reference:str=Field(default='',max_length=120)
    allocations:list[PgPilotAllocation]=Field(default_factory=list,max_length=30)

def finance_pilot_service():
    import sys
    path=str(BASE.parent/'migration')
    if path not in sys.path:sys.path.insert(0,path)
    import pg_finance_pilot
    return pg_finance_pilot

@app.post('/api/entities/{eid}/pg-pilot/treatments',status_code=201)
def pg_pilot_treatment(eid:int,data:PgPilotTreatmentIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        return finance_pilot_service().treatment(eid,code,data.patient_id,data.visit_id,
                                                 data.planned_by,data.description,data.tooth_number)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL clinical pilot unavailable or rejected request',503)

@app.post('/api/entities/{eid}/pg-pilot/invoices',status_code=201)
def pg_pilot_invoice(eid:int,data:PgPilotInvoiceIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        return finance_pilot_service().invoice(eid,code,data.patient_id,
                                               [i.model_dump() for i in data.items])
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL billing pilot unavailable or rejected request',503)
    except Exception as exc:
        if getattr(exc,'sqlstate',None)=='23505':
            fail('Treatment already invoiced',409)
        raise

@app.post('/api/entities/{eid}/pg-pilot/receipts',status_code=201)
def pg_pilot_receipt(eid:int,data:PgPilotReceiptIn,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        return finance_pilot_service().receipt(eid,code,data.patient_id,data.amount,
             [i.model_dump() for i in data.allocations],data.payment_mode,data.reference,
             idempotency_key=data.idempotency_key)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL payment pilot unavailable or rejected request',503)
    except Exception as exc:
        if getattr(exc,'sqlstate',None)=='23514':
            fail('Receipt allocation exceeds available balance',409)
        raise

@app.get('/api/entities/{eid}/pg-pilot/patients/{patient_id}/ledger')
def pg_pilot_ledger(eid:int,patient_id:int,u=Depends(current)):
    code=pg_pilot_authorize(eid,u)
    try:
        return finance_pilot_service().ledger(eid,code,patient_id)
    except (ValueError,RuntimeError,ImportError):
        fail('PostgreSQL pilot ledger unavailable',503)

def must(c,table,eid,record_id):
 if record_id is None:return
 if table not in ('patients','registrations','doctors','resources','appointments','visits','invoices','receipts','treatments','estimates'):fail('Internal invalid table')
 if not one(c,f'SELECT id FROM {table} WHERE id=? AND entity_id=?',(record_id,eid)):fail(f'{table} record not found in this entity',404)

def ensure_entity_admin(u):
 if not u['is_superadmin']:fail('Super administrator required',403)

@app.post('/api/login')
def login(payload:Login):
 # This is an account-name throttle for development; production also needs
 # network-level limits and a distributed security event monitor.
 username=payload.username.strip()
 key=username.casefold()
 cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
 with db(True) as c:
  c.execute('DELETE FROM login_failures WHERE attempted_at<?',(cutoff,))
  attempts=c.execute('SELECT count(*) FROM login_failures WHERE username=?',(key,)).fetchone()[0]
  if attempts>=5:fail('Too many attempts. Try again after 15 minutes.',429)
  u=one(c,'SELECT * FROM users WHERE username=? AND active=1',(username,))
  if not u or not verify_password(payload.password,u['password_hash']):
   c.execute('INSERT INTO login_failures(username,attempted_at) VALUES(?,?)',(key,utc()))
   # Failure is committed before reporting unsuccessful authentication.
   invalid=True
  else:
   mfa=one(c,'SELECT * FROM user_mfa WHERE user_id=? AND enabled=1',(u['id'],))
   if mfa:
    secret=mfa_cipher().decrypt(mfa['encrypted_secret'].encode()).decode()
    step=totp_step(secret,payload.otp)
    if step is None or step<=mfa['last_step']:
     c.execute('INSERT INTO login_failures(username,attempted_at) VALUES(?,?)',(key,utc()))
     invalid=True
    else:
     c.execute('UPDATE user_mfa SET last_step=? WHERE user_id=?',(step,u['id']))
     invalid=False
   else:invalid=False
   if not invalid:
    c.execute('DELETE FROM login_failures WHERE username=?',(key,))
    token=secrets.token_urlsafe(40)
    c.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
 if invalid:fail('Invalid credentials',401)
 return {'token':token,'user':{'username':u['username'],'is_superadmin':bool(u['is_superadmin'])}}

@app.get('/api/me/mfa')
def mfa_status(u=Depends(current)):
 with db() as c:
  record=one(c,'SELECT enabled FROM user_mfa WHERE user_id=?',(u['id'],))
 return {'enabled':bool(record and record['enabled'])}

@app.post('/api/me/mfa/enroll')
def mfa_enroll(u=Depends(current)):
 # Secret is returned once; do not log, persist in plaintext, or send in URLs to third parties.
 secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
 enc=mfa_cipher().encrypt(secret.encode()).decode()
 with db(True) as c:
  mfa=one(c,'SELECT enabled FROM user_mfa WHERE user_id=?',(u['id'],))
  if mfa and mfa['enabled']:fail('MFA already active',409)
  c.execute('INSERT INTO user_mfa(user_id,encrypted_secret,enabled,last_step) VALUES(?,?,0,-1) ON CONFLICT(user_id) DO UPDATE SET encrypted_secret=excluded.encrypted_secret,enabled=0,last_step=-1',(u['id'],enc))
  audit(c,u,None,'mfa_enrollment_started','user',u['id'])
 return {'secret':secret,'issuer':'Rajan Dental','account':u['username']}

@app.post('/api/me/mfa/enable')
def mfa_enable(data:MFAEnableIn,u=Depends(current)):
 with db(True) as c:
  mfa=one(c,'SELECT * FROM user_mfa WHERE user_id=?',(u['id'],))
  if not mfa or mfa['enabled']:fail('Start MFA enrollment first',409)
  secret=mfa_cipher().decrypt(mfa['encrypted_secret'].encode()).decode()
  step=totp_step(secret,data.otp)
  if step is None:fail('Invalid authenticator code',403)
  c.execute('UPDATE user_mfa SET enabled=1,last_step=-1 WHERE user_id=?',(u['id'],))
  c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
  audit(c,u,None,'mfa_enabled','user',u['id'])
 return {'enabled':True,'sessions_revoked':True}

@app.post('/api/me/mfa/disable')
def mfa_disable(data:MFADisableIn,u=Depends(current)):
 with db(True) as c:
  account=one(c,'SELECT password_hash FROM users WHERE id=?',(u['id'],))
  mfa=one(c,'SELECT * FROM user_mfa WHERE user_id=? AND enabled=1',(u['id'],))
  if not mfa or not verify_password(data.password,account['password_hash']):fail('Invalid verification',403)
  secret=mfa_cipher().decrypt(mfa['encrypted_secret'].encode()).decode()
  step=totp_step(secret,data.otp)
  if step is None or step<=mfa['last_step']:fail('Invalid verification',403)
  c.execute('DELETE FROM user_mfa WHERE user_id=?',(u['id'],))
  c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
  audit(c,u,None,'mfa_disabled','user',u['id'])
 return {'enabled':False,'sessions_revoked':True}

@app.post('/api/me/change-password')
def change_own_password(data:PasswordChangeIn,u=Depends(current)):
 if data.current_password==data.new_password:fail('New password must differ from current password')
 if not any(ch.isalpha() for ch in data.new_password) or not any(ch.isdigit() for ch in data.new_password):
  fail('New password must include letters and numbers')
 with db(True) as c:
  user=one(c,'SELECT password_hash FROM users WHERE id=? AND active=1',(u['id'],))
  if not user or not verify_password(data.current_password,user['password_hash']):fail('Current password is incorrect',403)
  c.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(data.new_password),u['id']))
  c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
  audit(c,u,None,'password_changed','user',u['id'])
 return {'password_changed':True,'sessions_revoked':True}

@app.post('/api/me/logout-all')
def logout_all_sessions(u=Depends(current)):
 with db(True) as c:
  c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
  audit(c,u,None,'logout_all','user',u['id'])
 return {'sessions_revoked':True}

@app.get('/api/entities/{eid}/audit-events')
def list_audit_events(eid:int,limit:int=50,offset:int=0,u=Depends(current)):
 access(eid,u,('admin',))
 if limit<1 or limit>100 or offset<0:fail('Pagination out of range')
 with db() as c:
  events=rows(c,"""SELECT a.id,a.at,a.action,a.object_type,a.object_id,
                        COALESCE(usr.username,'System') AS actor
                     FROM audit a LEFT JOIN users usr ON usr.id=a.user_id
                     WHERE a.entity_id=? ORDER BY a.id DESC LIMIT ? OFFSET ?""",(eid,limit,offset))
  count=c.execute('SELECT COUNT(*) FROM audit WHERE entity_id=?',(eid,)).fetchone()[0]
 return {'events':events,'total':count,'limit':limit,'offset':offset}

@app.get('/api/me')
def me(u=Depends(current)):return u

@app.post('/api/logout')
def logout_session(authorization:Optional[str]=Header(default=None),u=Depends(current)):
 token=(authorization or '').removeprefix('Bearer ').strip()
 with db(True) as c:
  c.execute('DELETE FROM sessions WHERE token_hash=? AND user_id=?',(hashlib.sha256(token.encode()).hexdigest(),u['id']))
 return {'logged_out':True}
@app.get('/api/entities')
def entities(u=Depends(current)):
 with db() as c:
  return rows(c,'SELECT e.* FROM entities e JOIN memberships m ON e.id=m.entity_id WHERE m.user_id=? AND e.active=1 ORDER BY e.id',(u['id'],))
@app.post('/api/entities')
def create_entity(data:EntityIn,u=Depends(current)):
 ensure_entity_admin(u)
 code=data.code.upper().strip()
 if not re.fullmatch(r'[A-Z][A-Z0-9]{1,11}',code):fail('Code must be 2–12 uppercase letters/numbers, starting with a letter')
 if data.kind not in ('clinic','trust','other'):fail('Invalid entity kind')
 with db(True) as c:
  if one(c,'SELECT id FROM entities WHERE code=?',(code,)):fail('Entity code already exists',409)
  cur=c.execute('INSERT INTO entities(name,code,kind,chairs,ots,created_at) VALUES(?,?,?,?,?,?)',(data.name,code,data.kind,data.chairs,data.ots,utc()))
  eid=cur.lastrowid
  for code,name in advanced_v02.DEFAULT_CATEGORIES:
   c.execute('INSERT INTO pricing_categories(entity_id,code,name,is_default) VALUES(?,?,?,?)',(eid,code,name,int(code=='regular')))
  c.execute('INSERT INTO memberships(user_id,entity_id,role) VALUES(?,?,?)',(u['id'],eid,'admin'))
  for typ,count in [('chair',data.chairs),('ot',data.ots)]:
   for i in range(1,count+1):c.execute('INSERT INTO resources(entity_id,name,type) VALUES(?,?,?)',(eid,f'{typ.upper()} {i:02}',typ))
  audit(c,u,eid,'created','entity',eid)
 return {'id':eid,'code':code,'message':'Entity created with independent numbering, resources, and records'}
@app.post('/api/entities/{eid}/members')
def grant(eid:int,data:MembershipIn,u=Depends(current)):
 ensure_entity_admin(u);access(eid,u)
 if data.role not in ('admin','reception','doctor','billing','viewer'):fail('Invalid role')
 with db(True) as c:
  target=one(c,'SELECT id FROM users WHERE username=?',(data.username,))
  if not target:fail('User not found',404)
  c.execute('INSERT INTO memberships(user_id,entity_id,role) VALUES(?,?,?) ON CONFLICT(user_id,entity_id) DO UPDATE SET role=excluded.role',(target['id'],eid,data.role))
  audit(c,u,eid,'granted','membership',target['id'])
 return {'ok':True}
@app.patch('/api/entities/{eid}/staff-accounts/{staff_id}/role')
def change_entity_role(eid:int,staff_id:int,data:MembershipRoleUpdate,u=Depends(current)):
 access(eid,u,('admin',))
 if data.role not in ('admin','reception','doctor','billing','viewer'):fail('Invalid role')
 if staff_id==u['id']:fail('Cannot change your own role',409)
 with db(True) as c:
  target=one(c,'SELECT u.id,u.active,u.is_superadmin,m.role FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.entity_id=? AND u.id=?',(eid,staff_id))
  if not target:fail('Staff membership not found in this entity',404)
  if target['is_superadmin']:fail('Super administrator role cannot be changed',403)
  if not target['active']:fail('Inactive account role cannot be changed',409)
  if target['role']==data.role:fail('Role already assigned',409)
  c.execute('UPDATE memberships SET role=? WHERE entity_id=? AND user_id=?',(data.role,eid,staff_id))
  c.execute('DELETE FROM sessions WHERE user_id=?',(staff_id,))
  audit(c,u,eid,'changed_role_'+target['role']+'_to_'+data.role,'membership',staff_id)
 return {'id':staff_id,'entity_id':eid,'role':data.role,'sessions_revoked':True}

@app.delete('/api/entities/{eid}/staff-accounts/{staff_id}/membership')
def remove_entity_membership(eid:int,staff_id:int,u=Depends(current)):
 access(eid,u,('admin',))
 if staff_id==u['id']:fail('Cannot remove your own entity access',409)
 with db(True) as c:
  target=one(c,'SELECT u.id,u.is_superadmin FROM users u JOIN memberships m ON u.id=m.user_id WHERE m.entity_id=? AND u.id=?',(eid,staff_id))
  if not target:fail('Staff membership not found in this entity',404)
  if target['is_superadmin']:fail('Cannot remove super administrator membership',403)
  c.execute('DELETE FROM memberships WHERE user_id=? AND entity_id=?',(staff_id,eid))
  c.execute('DELETE FROM sessions WHERE user_id=?',(staff_id,))
  audit(c,u,eid,'removed_entity_access','membership',staff_id)
 return {'id':staff_id,'entity_id':eid,'membership_removed':True,'account_active':True,'sessions_revoked':True}

@app.get('/api/entities/{eid}/dashboard')
def dashboard(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:
  x={}
  for key,q in {'patients':'SELECT count(*) FROM patients WHERE entity_id=?','registrations':'SELECT count(*) FROM registrations WHERE entity_id=? AND patient_id IS NULL','appointments':'SELECT count(*) FROM appointments WHERE entity_id=? AND status!=\'cancelled\'','visits':'SELECT count(*) FROM visits WHERE entity_id=?','chairs':'SELECT count(*) FROM resources WHERE entity_id=? AND type=\'chair\'','ots':'SELECT count(*) FROM resources WHERE entity_id=? AND type=\'ot\'','invoices_paise':'SELECT COALESCE(sum(total_paise),0) FROM invoices WHERE entity_id=?','receipts_paise':'SELECT COALESCE(sum(r.amount_paise),0) FROM receipts r WHERE r.entity_id=? AND NOT EXISTS(SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=r.entity_id AND rr.receipt_id=r.id) AND NOT EXISTS(SELECT 1 FROM advance_transfers_v2 t WHERE t.dest_entity_id=r.entity_id AND t.dest_receipt_id=r.id)'}.items():x[key]=c.execute(q,(eid,)).fetchone()[0]
  x['credit_notes_paise']=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM credit_notes WHERE entity_id=?',(eid,)).fetchone()[0]
  x['net_invoices_paise']=x['invoices_paise']-x['credit_notes_paise']
  role=access(eid,u)
  if role not in ('admin','billing'):
   for financial_key in ('invoices_paise','receipts_paise','credit_notes_paise','net_invoices_paise'):
    x.pop(financial_key,None)
  return x
@app.get('/api/entities/{eid}/patients')
def patients(eid:int,q:str='',u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT * FROM patients WHERE entity_id=? AND (name LIKE ? OR phone LIKE ? OR uhid LIKE ?) ORDER BY id DESC LIMIT 100',(eid,*['%'+q+'%']*3))
@app.get('/api/entities/{eid}/registrations')
def registrations(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT * FROM registrations WHERE entity_id=? ORDER BY id DESC LIMIT 100',(eid,))
@app.post('/api/entities/{eid}/registrations')
def register(eid:int,data:RegistrationIn,u=Depends(current)):
 access(eid,u,('admin','reception'))
 with db(True) as c:
  tmp=nextnum(c,eid,'TMP')
  cur=c.execute('INSERT INTO registrations(entity_id,temp_id,name,phone,dob,notes,created_at) VALUES(?,?,?,?,?,?,?)',(eid,tmp,data.name,data.phone,data.dob,data.notes,utc()))
  audit(c,u,eid,'created','registration',cur.lastrowid)
 return {'id':cur.lastrowid,'temp_id':tmp}
@app.post('/api/entities/{eid}/check-in')
def check_in(eid:int,data:CheckIn,u=Depends(current)):
 access(eid,u,('admin','reception'))
 with db(True) as c:
  r=one(c,'SELECT * FROM registrations WHERE id=? AND entity_id=?',(data.registration_id,eid))
  if not r:fail('Registration not found',404)
  if r['patient_id']:
   p=one(c,'SELECT * FROM patients WHERE id=? AND entity_id=?',(r['patient_id'],eid));return {'patient':p,'reused':True}
  if data.existing_patient_id:
   must(c,'patients',eid,data.existing_patient_id);pid=data.existing_patient_id;reused=True
  else:
   uhid=nextnum(c,eid,'UHID');cur=c.execute('INSERT INTO patients(entity_id,uhid,name,phone,dob,notes,created_at) VALUES(?,?,?,?,?,?,?)',(eid,uhid,r['name'],r['phone'],r['dob'],r['notes'],utc()));pid=cur.lastrowid;reused=False
  c.execute('UPDATE registrations SET patient_id=? WHERE id=? AND entity_id=?',(pid,r['id'],eid))
  audit(c,u,eid,'checked_in','patient',pid)
  return {'patient':one(c,'SELECT * FROM patients WHERE id=?',(pid,)),'reused':reused}
@app.get('/api/entities/{eid}/doctors')
def doctors(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT * FROM doctors WHERE entity_id=? AND active=1',(eid,))
@app.post('/api/entities/{eid}/doctors')
def add_doctor(eid:int,data:dict,u=Depends(current)):
 access(eid,u,('admin',))
 name=str(data.get('name','')).strip()
 if len(name)<2:fail('Doctor name required')
 with db(True) as c:
  cur=c.execute('INSERT INTO doctors(entity_id,name) VALUES(?,?)',(eid,name));audit(c,u,eid,'created','doctor',cur.lastrowid)
 return {'id':cur.lastrowid}
@app.get('/api/entities/{eid}/resources')
def resources(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT * FROM resources WHERE entity_id=?',(eid,))
@app.get('/api/entities/{eid}/appointments')
def appointments(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'''SELECT a.*,d.name doctor_name,r.name resource_name,COALESCE(p.name,t.name) patient_name FROM appointments a JOIN doctors d ON d.id=a.doctor_id LEFT JOIN resources r ON r.id=a.resource_id LEFT JOIN patients p ON p.id=a.patient_id LEFT JOIN registrations t ON t.id=a.registration_id WHERE a.entity_id=? ORDER BY a.start_time DESC LIMIT 200''',(eid,))
@app.post('/api/entities/{eid}/appointments')
def appointment(eid:int,data:AppointmentIn,u=Depends(current)):
 access(eid,u,('admin','reception','doctor'))
 if bool(data.patient_id)==bool(data.registration_id):fail('Choose either a registered patient or a temporary registration')
 try:
  st=datetime.fromisoformat(data.start_time);en=datetime.fromisoformat(data.end_time)
  if st.tzinfo is None or en.tzinfo is None or en<=st:raise ValueError()
 except ValueError:fail('Use valid timezone-aware start and end timestamps')
 with db(True) as c:
  for t,id in [('patients',data.patient_id),('registrations',data.registration_id),('doctors',data.doctor_id),('resources',data.resource_id)]:must(c,t,eid,id)
  # Opt-in strict slot enforcement preserves older test/demo workflows until configured.
  rule=one(c,'SELECT enforce_slots FROM doctor_booking_rules WHERE entity_id=? AND doctor_id=?',(eid,data.doctor_id))
  if rule and rule['enforce_slots']:
   local_start=st.astimezone(ZoneInfo('Asia/Kolkata'))
   local_end=en.astimezone(ZoneInfo('Asia/Kolkata'))
   if local_start.date()!=local_end.date():fail('Appointment must remain within one India-local calendar day',409)
   start_min=local_start.hour*60+local_start.minute
   end_min=local_end.hour*60+local_end.minute
   matches=rows(c,'SELECT * FROM doctor_slots WHERE entity_id=? AND doctor_id=? AND weekday=? AND active=1 AND start_minute<=? AND end_minute>=?',(eid,data.doctor_id,local_start.weekday(),start_min,end_min))
   if not any(start_min >= slot['start_minute'] and (start_min-slot['start_minute'])%slot['slot_minutes']==0 and (end_min-start_min)%slot['slot_minutes']==0 for slot in matches):
    fail('Appointment must align with an active doctor opening slot in Asia/Kolkata',409)
  # Shared clinician identity only links doctor accounts; patients and finances never link.
  link=one(c,'SELECT clinician_key FROM clinician_links WHERE entity_id=? AND doctor_id=?',(eid,data.doctor_id))
  if link:
   conflict_link=one(c,"""SELECT a.id FROM appointments a JOIN clinician_links l ON l.entity_id=a.entity_id AND l.doctor_id=a.doctor_id
        WHERE l.clinician_key=? AND a.entity_id!=? AND a.status NOT IN ('cancelled','no_show') AND a.start_time<? AND a.end_time>?""",(link['clinician_key'],eid,en.astimezone(timezone.utc).isoformat(),st.astimezone(timezone.utc).isoformat()))
   if conflict_link:fail('Shared doctor is booked at another entity',409)
   time_off_link=one(c,"""SELECT t.id FROM doctor_time_off t JOIN clinician_links l ON l.entity_id=t.entity_id AND l.doctor_id=t.doctor_id
       WHERE l.clinician_key=? AND t.entity_id!=? AND t.start_time<? AND t.end_time>?""",(link['clinician_key'],eid,en.astimezone(timezone.utc).isoformat(),st.astimezone(timezone.utc).isoformat()))
   if time_off_link:fail('Shared doctor is unavailable at another entity',409)
  conflict=one(c,'''SELECT id FROM appointments WHERE status NOT IN ('cancelled','no_show') AND start_time < ? AND end_time > ? AND (doctor_id=? OR (resource_id IS NOT NULL AND resource_id=?)) AND entity_id=?''',(en.astimezone(timezone.utc).isoformat(),st.astimezone(timezone.utc).isoformat(),data.doctor_id,data.resource_id,eid))
  if conflict:fail('Doctor or chair/OT already booked in this entity',409)
  # Time-off is enforced even when the appointment is manually created.
  timeoff=one(c,'SELECT id FROM doctor_time_off WHERE entity_id=? AND doctor_id=? AND start_time<? AND end_time>?',(eid,data.doctor_id,en.astimezone(timezone.utc).isoformat(),st.astimezone(timezone.utc).isoformat()))
  if timeoff:fail('Doctor unavailable during requested time',409)
  cur=c.execute('INSERT INTO appointments(entity_id,patient_id,registration_id,doctor_id,resource_id,start_time,end_time,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(eid,data.patient_id,data.registration_id,data.doctor_id,data.resource_id,st.astimezone(timezone.utc).isoformat(),en.astimezone(timezone.utc).isoformat(),data.reason,utc()));audit(c,u,eid,'created','appointment',cur.lastrowid)
 return {'id':cur.lastrowid}
@app.get('/api/entities/{eid}/visits')
def visits(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT v.*,p.name patient_name FROM visits v JOIN patients p ON p.id=v.patient_id WHERE v.entity_id=? ORDER BY v.id DESC LIMIT 100',(eid,))
@app.post('/api/entities/{eid}/visits')
def visit(eid:int,data:VisitIn,u=Depends(current)):
 access(eid,u,('admin','doctor','reception'))
 with db(True) as c:
  for t,id in [('patients',data.patient_id),('appointments',data.appointment_id),('doctors',data.doctor_id)]:must(c,t,eid,id)
  if data.appointment_id:
   ap=one(c,'SELECT patient_id,registration_id FROM appointments WHERE id=? AND entity_id=?',(data.appointment_id,eid))
   if ap['patient_id']!=data.patient_id and (not ap['registration_id'] or one(c,'SELECT patient_id FROM registrations WHERE id=?',(ap['registration_id'],))['patient_id']!=data.patient_id):fail('Appointment does not belong to this patient')
  num=nextnum(c,eid,'VIS');cur=c.execute('INSERT INTO visits(entity_id,visit_no,patient_id,appointment_id,doctor_id,complaint,diagnosis,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(eid,num,data.patient_id,data.appointment_id,data.doctor_id,data.complaint,data.diagnosis,data.notes,utc()));audit(c,u,eid,'created','visit',cur.lastrowid)
 return {'id':cur.lastrowid,'visit_no':num}
@app.get('/api/entities/{eid}/visits/{visit_id}/clinical-history')
def visit_clinical_history(eid:int,visit_id:int,u=Depends(current)):
 access(eid,u,('admin','doctor','viewer'))
 with db() as c:
  must(c,'visits',eid,visit_id)
  return rows(c,'''SELECT r.*,usr.username edited_by_name FROM visit_clinical_revisions r JOIN users usr ON usr.id=r.edited_by WHERE r.entity_id=? AND r.visit_id=? ORDER BY r.version DESC''',(eid,visit_id))

@app.put('/api/entities/{eid}/visits/{visit_id}/clinical-content')
def update_visit_clinical_content(eid:int,visit_id:int,data:VisitClinicalEditIn,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 with db(True) as c:
  v=one(c,'SELECT * FROM visits WHERE entity_id=? AND id=?',(eid,visit_id))
  if not v:fail('Visit not found',404)
  prev=one(c,'SELECT MAX(version) AS version FROM visit_clinical_revisions WHERE entity_id=? AND visit_id=?',(eid,visit_id))
  version=prev['version'] or 0
  if version!=data.expected_version:fail('Visit changed in another session. Reload before editing.',409)
  if all((v[k] or '')==getattr(data,k) for k in ('complaint','diagnosis','notes')):
   return {'id':visit_id,'version':version,'unchanged':True}
  at=utc()
  c.execute('''INSERT INTO visit_clinical_revisions(entity_id,visit_id,version,previous_complaint,previous_diagnosis,previous_notes,complaint,diagnosis,notes,edited_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
   (eid,visit_id,version+1,v['complaint'] or '',v['diagnosis'] or '',v['notes'] or '',data.complaint,data.diagnosis,data.notes,u['id'],at))
  c.execute('UPDATE visits SET complaint=?,diagnosis=?,notes=? WHERE entity_id=? AND id=?',(data.complaint,data.diagnosis,data.notes,eid,visit_id))
  audit(c,u,eid,'visit_clinical_edited','visit',visit_id)
  return {'id':visit_id,'version':version+1,'saved_at':at}

@app.get('/api/entities/{eid}/treatments')
def treatments(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT t.*,v.visit_no FROM treatments t JOIN visits v ON v.id=t.visit_id WHERE t.entity_id=? ORDER BY t.id DESC',(eid,))
@app.post('/api/entities/{eid}/treatments')
def treatment(eid:int,data:TreatmentIn,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 with db(True) as c:
  for t,id in [('visits',data.visit_id),('doctors',data.planned_by),('doctors',data.performed_by)]:must(c,t,eid,id)
  cur=c.execute('INSERT INTO treatments(entity_id,visit_id,description,tooth,planned_by,performed_by,status,amount_paise) VALUES(?,?,?,?,?,?,?,?)',(eid,data.visit_id,data.description,data.tooth,data.planned_by,data.performed_by,data.status,cents(data.amount)));audit(c,u,eid,'created','treatment',cur.lastrowid)
 return {'id':cur.lastrowid}
@app.get('/api/entities/{eid}/invoices')
def invoices(eid:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db() as c:return rows(c,'''SELECT i.*,p.name patient_name, i.total_paise-COALESCE((SELECT SUM(cn.amount_paise) FROM credit_notes cn WHERE cn.invoice_id=i.id AND cn.entity_id=i.entity_id),0)-COALESCE((SELECT SUM(w.amount_paise) FROM financial_writeoffs w WHERE w.invoice_id=i.id AND w.entity_id=i.entity_id),0)-COALESCE((SELECT SUM(a.amount_paise) FROM allocations a WHERE a.invoice_id=i.id AND a.entity_id=i.entity_id AND NOT EXISTS(SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=a.entity_id AND rr.receipt_id=a.receipt_id)),0) balance_paise FROM invoices i JOIN patients p ON p.id=i.patient_id WHERE i.entity_id=? ORDER BY i.id DESC''',(eid,))
@app.post('/api/entities/{eid}/invoices')
def invoice(eid:int,data:InvoiceIn,u=Depends(current)):
 access(eid,u,('admin','billing'))
 amount=cents(data.amount)
 if amount<=0:fail('Amount must be greater than zero')
 with db(True) as c:
  must(c,'patients',eid,data.patient_id);no=nextnum(c,eid,'INV');cur=c.execute('INSERT INTO invoices(entity_id,invoice_no,patient_id,total_paise,description,created_at) VALUES(?,?,?,?,?,?)',(eid,no,data.patient_id,amount,data.description,utc()));audit(c,u,eid,'created','invoice',cur.lastrowid)
 return {'id':cur.lastrowid,'invoice_no':no}
@app.get('/api/entities/{eid}/receipts')
def receipts(eid:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db() as c:return rows(c,'''SELECT r.*,rr.id IS NOT NULL AS reversed,rr.reason AS reversal_reason,rr.created_at AS reversed_at FROM receipts r LEFT JOIN receipt_reversals rr ON rr.receipt_id=r.id AND rr.entity_id=r.entity_id WHERE r.entity_id=? ORDER BY r.id DESC''',(eid,))
@app.post('/api/entities/{eid}/receipts')
def receipt(eid:int,data:ReceiptIn,u=Depends(current)):
 access(eid,u,('admin','billing'))
 total=cents(data.amount)
 if total<=0:fail('Receipt amount must be greater than zero')
 if data.method not in ('cash','upi','card','bank','other'):fail('Invalid payment mode')
 with db(True) as c:
  must(c,'patients',eid,data.patient_id)
  allocated=0;seen=set()
  for a in data.allocations:
   if a.invoice_id in seen:fail('Duplicate invoice allocation')
   seen.add(a.invoice_id)
   i=one(c,'SELECT * FROM invoices WHERE id=? AND entity_id=? AND patient_id=?',(a.invoice_id,eid,data.patient_id))
   if not i:fail('Invoice is not for the selected patient/entity',409)
   draft_v2=one(c,'SELECT status FROM invoice_headers_v2 WHERE entity_id=? AND invoice_id=?',(eid,i['id']))
   if draft_v2 and draft_v2['status']!='issued':fail('Issue the invoice before payment allocation',409)
   value=cents(a.amount)
   credited=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM credit_notes WHERE invoice_id=? AND entity_id=?',(i['id'],eid)).fetchone()[0]
   written_off=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM financial_writeoffs WHERE entity_id=? AND invoice_id=?',(eid,i['id'])).fetchone()[0]
   already=c.execute('SELECT COALESCE(SUM(a.amount_paise),0) FROM allocations a WHERE a.invoice_id=? AND a.entity_id=? AND NOT EXISTS(SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=a.entity_id AND rr.receipt_id=a.receipt_id)',(i['id'],eid)).fetchone()[0]
   if value<=0 or value>i['total_paise']-credited-written_off-already:fail('Allocation exceeds invoice outstanding balance',409)
   allocated+=value
  if allocated>total:fail('Allocations exceed receipt amount',409)
  no=nextnum(c,eid,'RCP');cur=c.execute('INSERT INTO receipts(entity_id,receipt_no,patient_id,amount_paise,method,reference,created_at) VALUES(?,?,?,?,?,?,?)',(eid,no,data.patient_id,total,data.method,data.reference,utc()));rid=cur.lastrowid
  for a in data.allocations:c.execute('INSERT INTO allocations(entity_id,receipt_id,invoice_id,amount_paise) VALUES(?,?,?,?)',(eid,rid,a.invoice_id,cents(a.amount)))
  audit(c,u,eid,'created','receipt',rid)
 return {'id':rid,'receipt_no':no,'unallocated_paise':total-allocated}

class ToothFindingIn(BaseModel):
 patient_id:int
 visit_id:int
 tooth_code:str=Field(min_length=2,max_length=2)
 surface:str='whole'
 condition:str=Field(min_length=2,max_length=100)
 notes:str=Field(default='',max_length=3000)

class TreatmentSessionIn(BaseModel):
 treatment_id:int
 visit_id:int
 performed_by:int
 performed_at:str
 procedure_notes:str=Field(min_length=1,max_length=5000)
 progress:str='in_progress'


# Clinical Phase 3 — patient summary, odontogram findings, treatment sessions.
FDI_CODES={f'{q}{n}' for q in (1,2,3,4) for n in range(1,9)} | {f'{q}{n}' for q in (5,6,7,8) for n in range(1,6)}

@app.get('/api/entities/{eid}/patients/{pid}/clinical-summary')
def clinical_summary(eid:int,pid:int,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 with db() as c:
  patient=one(c,'SELECT * FROM patients WHERE entity_id=? AND id=?',(eid,pid))
  if not patient:fail('Patient not found in this entity',404)
  visits=rows(c,'SELECT v.*,d.name doctor_name FROM visits v LEFT JOIN doctors d ON d.id=v.doctor_id AND d.entity_id=v.entity_id WHERE v.entity_id=? AND v.patient_id=? ORDER BY v.id DESC',(eid,pid))
  treatments=rows(c,'SELECT t.*,v.visit_no FROM treatments t JOIN visits v ON v.id=t.visit_id AND v.entity_id=t.entity_id WHERE t.entity_id=? AND v.patient_id=? ORDER BY t.id DESC',(eid,pid))
  findings=rows(c,'SELECT f.* FROM tooth_findings f WHERE f.entity_id=? AND f.patient_id=? ORDER BY f.id DESC',(eid,pid))
  sessions=rows(c,"""SELECT s.*,d.name performed_by_name,t.description treatment_name FROM treatment_sessions s JOIN treatments t ON t.id=s.treatment_id AND t.entity_id=s.entity_id JOIN visits v ON v.id=t.visit_id AND v.entity_id=t.entity_id JOIN doctors d ON d.id=s.performed_by AND d.entity_id=s.entity_id WHERE s.entity_id=? AND v.patient_id=? ORDER BY s.performed_at DESC""",(eid,pid))
  invoices=rows(c,"""SELECT i.id,i.invoice_no,i.total_paise,i.created_at,i.total_paise-COALESCE((SELECT SUM(cn.amount_paise) FROM credit_notes cn WHERE cn.invoice_id=i.id AND cn.entity_id=i.entity_id),0)-COALESCE((SELECT SUM(w.amount_paise) FROM financial_writeoffs w WHERE w.invoice_id=i.id AND w.entity_id=i.entity_id),0)-COALESCE((SELECT SUM(a.amount_paise) FROM allocations a WHERE a.entity_id=i.entity_id AND a.invoice_id=i.id AND NOT EXISTS(SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=a.entity_id AND rr.receipt_id=a.receipt_id)),0) balance_paise FROM invoices i WHERE i.entity_id=? AND i.patient_id=? ORDER BY i.id DESC""",(eid,pid))
  return {'patient':patient,'visits':visits,'treatments':treatments,'findings':findings,'sessions':sessions,'invoices':invoices}

@app.get('/api/entities/{eid}/tooth-findings')
def get_findings(eid:int,patient_id:int,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 with db() as c:
  must(c,'patients',eid,patient_id)
  return rows(c,'SELECT * FROM tooth_findings WHERE entity_id=? AND patient_id=? ORDER BY id DESC',(eid,patient_id))

@app.post('/api/entities/{eid}/tooth-findings')
def add_finding(eid:int,data:ToothFindingIn,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 if data.tooth_code not in FDI_CODES:fail('Invalid FDI tooth code')
 if data.surface not in ('whole','mesial','distal','occlusal','buccal','lingual','palatal','incisal'):fail('Invalid tooth surface')
 with db(True) as c:
  must(c,'patients',eid,data.patient_id)
  v=one(c,'SELECT patient_id FROM visits WHERE entity_id=? AND id=?',(eid,data.visit_id))
  if not v or v['patient_id']!=data.patient_id:fail('Visit does not belong to the selected patient and entity',409)
  cur=c.execute('INSERT INTO tooth_findings(entity_id,patient_id,visit_id,tooth_code,surface,condition,notes,recorded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(eid,data.patient_id,data.visit_id,data.tooth_code,data.surface,data.condition,data.notes,u['id'],utc()))
  audit(c,u,eid,'created','tooth_finding',cur.lastrowid)
  return {'id':cur.lastrowid,'tooth_code':data.tooth_code}

@app.get('/api/entities/{eid}/treatment-sessions')
def get_sessions(eid:int,treatment_id:Optional[int]=None,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 with db() as c:
  if treatment_id is not None:must(c,'treatments',eid,treatment_id)
  return rows(c,"""SELECT s.*,d.name performed_by_name,t.description treatment_name FROM treatment_sessions s JOIN doctors d ON d.id=s.performed_by AND d.entity_id=s.entity_id JOIN treatments t ON t.id=s.treatment_id AND t.entity_id=s.entity_id WHERE s.entity_id=? AND (? IS NULL OR s.treatment_id=?) ORDER BY s.performed_at DESC""",(eid,treatment_id,treatment_id))

@app.post('/api/entities/{eid}/treatment-sessions')
def add_session(eid:int,data:TreatmentSessionIn,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 when=instant(data.performed_at)
 if data.progress not in ('in_progress','completed'):fail('Invalid progress')
 with db(True) as c:
  t=one(c,'SELECT * FROM treatments WHERE id=? AND entity_id=?',(data.treatment_id,eid))
  if not t:fail('Treatment not found',404)
  v=one(c,'SELECT * FROM visits WHERE id=? AND entity_id=?',(data.visit_id,eid))
  if not v or v['patient_id']!=one(c,'SELECT patient_id FROM visits WHERE id=? AND entity_id=?',(t['visit_id'],eid))['patient_id']:
   fail('Session visit must belong to the same patient and entity as the treatment',409)
  must(c,'doctors',eid,data.performed_by)
  if t['status']=='completed':fail('Completed treatment cannot accept further sessions',409)
  cur=c.execute('INSERT INTO treatment_sessions(entity_id,treatment_id,visit_id,performed_by,performed_at,procedure_notes,progress,created_at) VALUES(?,?,?,?,?,?,?,?)',(eid,data.treatment_id,data.visit_id,data.performed_by,when,data.procedure_notes,data.progress,utc()))
  c.execute('UPDATE treatments SET status=?,performed_by=? WHERE id=? AND entity_id=?',(data.progress,data.performed_by,data.treatment_id,eid))
  audit(c,u,eid,'created','treatment_session',cur.lastrowid)
  return {'id':cur.lastrowid,'progress':data.progress}

def minutes(t):
 try:
  h,m=map(int,t.split(':'))
  if not (0<=h<=23 and 0<=m<=59):raise ValueError()
  return h*60+m
 except Exception:fail('Time must be HH:MM in 24-hour format')

def instant(t):
 try:
  d=datetime.fromisoformat(t)
  if d.tzinfo is None:raise ValueError()
  return d.astimezone(timezone.utc).isoformat()
 except ValueError:fail('A timezone-aware datetime is required')

@app.get('/api/entities/{eid}/doctor-slots')
def get_slots(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT s.*,d.name doctor_name FROM doctor_slots s JOIN doctors d ON d.id=s.doctor_id AND d.entity_id=s.entity_id WHERE s.entity_id=? AND s.active=1 ORDER BY doctor_id,weekday,start_minute',(eid,))

@app.post('/api/entities/{eid}/doctor-slots')
def set_slot(eid:int,data:SlotIn,u=Depends(current)):
 access(eid,u,('admin',))
 a,b=minutes(data.start_time),minutes(data.end_time)
 if b<=a:fail('Closing time must follow opening time')
 with db(True) as c:
  must(c,'doctors',eid,data.doctor_id)
  if one(c,'SELECT id FROM doctor_slots WHERE entity_id=? AND doctor_id=? AND weekday=? AND active=1 AND start_minute<? AND end_minute>?',(eid,data.doctor_id,data.weekday,b,a)):fail('Opening slots overlap',409)
  cur=c.execute('INSERT INTO doctor_slots(entity_id,doctor_id,weekday,start_minute,end_minute,slot_minutes) VALUES(?,?,?,?,?,?)',(eid,data.doctor_id,data.weekday,a,b,data.slot_minutes))
  audit(c,u,eid,'created','doctor_slot',cur.lastrowid)
 return {'id':cur.lastrowid}

@app.delete('/api/entities/{eid}/doctor-slots/{sid}')
def delete_slot(eid:int,sid:int,u=Depends(current)):
 access(eid,u,('admin',))
 with db(True) as c:
  cur=c.execute('UPDATE doctor_slots SET active=0 WHERE entity_id=? AND id=? AND active=1',(eid,sid))
  if not cur.rowcount:fail('Slot not found',404)
  audit(c,u,eid,'disabled','doctor_slot',sid)
 return {'ok':True}

@app.get('/api/entities/{eid}/doctor-time-off')
def list_timeoff(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT * FROM doctor_time_off WHERE entity_id=? ORDER BY start_time',(eid,))

@app.post('/api/entities/{eid}/doctor-time-off')
def add_timeoff(eid:int,data:TimeOffIn,u=Depends(current)):
 access(eid,u,('admin',))
 a,b=instant(data.start_time),instant(data.end_time)
 if b<=a:fail('Invalid unavailable interval')
 with db(True) as c:
  must(c,'doctors',eid,data.doctor_id)
  if one(c,"SELECT id FROM appointments WHERE entity_id=? AND doctor_id=? AND status NOT IN ('cancelled','no_show') AND start_time<? AND end_time>?",(eid,data.doctor_id,b,a)):fail('Existing appointments overlap requested time off',409)
  link=one(c,'SELECT clinician_key FROM clinician_links WHERE entity_id=? AND doctor_id=?',(eid,data.doctor_id))
  if link:
   other=one(c,"""SELECT a.id FROM appointments a JOIN clinician_links l ON l.entity_id=a.entity_id AND l.doctor_id=a.doctor_id
      WHERE l.clinician_key=? AND a.entity_id!=? AND a.status NOT IN ('cancelled','no_show') AND a.start_time<? AND a.end_time>?""",(link['clinician_key'],eid,b,a))
   if other:fail('Shared doctor has appointments at another entity',409)
  cur=c.execute('INSERT INTO doctor_time_off(entity_id,doctor_id,start_time,end_time,reason) VALUES(?,?,?,?,?)',(eid,data.doctor_id,a,b,data.reason))
  audit(c,u,eid,'created','doctor_time_off',cur.lastrowid)
 return {'id':cur.lastrowid}

@app.patch('/api/entities/{eid}/appointments/{aid}/status')
def update_appointment_status(eid:int,aid:int,data:AppointmentStatusIn,u=Depends(current)):
 access(eid,u,('admin','reception','doctor'))
 statuses={'booked','confirmed','arrived','checked_in','waiting','in_treatment','completed','cancelled','no_show'}
 if data.status not in statuses:fail('Invalid appointment status')
 with db(True) as c:
  must(c,'appointments',eid,aid)
  c.execute('UPDATE appointments SET status=? WHERE id=? AND entity_id=?',(data.status,aid,eid))
  audit(c,u,eid,'status_'+data.status,'appointment',aid)
 return {'ok':True}

@app.get('/api/entities/{eid}/estimates')
def list_estimates(eid:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db() as c:
  results=rows(c,'SELECT e.*,p.name patient_name FROM estimates e JOIN patients p ON p.id=e.patient_id AND p.entity_id=e.entity_id WHERE e.entity_id=? ORDER BY e.id DESC',(eid,))
  for e in results:
   e['items']=rows(c,'''SELECT ei.*,li.invoice_id FROM estimate_items ei LEFT JOIN estimate_item_invoices li ON li.estimate_item_id=ei.id AND li.entity_id=ei.entity_id WHERE ei.entity_id=? AND ei.estimate_id=? ORDER BY ei.id''',(eid,e['id']))
   e['invoiced_paise']=sum(x['amount_paise'] for x in e['items'] if x['invoice_id'] is not None)
  return results

@app.post('/api/entities/{eid}/estimates')
def create_estimate(eid:int,data:EstimateIn,u=Depends(current)):
 access(eid,u,('admin','billing','doctor'))
 if len(data.treatment_ids)!=len(set(data.treatment_ids)):fail('Duplicate treatment item')
 with db(True) as c:
  must(c,'patients',eid,data.patient_id)
  placeholders=','.join('?' for _ in data.treatment_ids)
  ts=rows(c,f"SELECT t.*,v.patient_id FROM treatments t JOIN visits v ON v.id=t.visit_id AND v.entity_id=t.entity_id WHERE t.entity_id=? AND t.id IN ({placeholders})",(eid,*data.treatment_ids))
  if len(ts)!=len(data.treatment_ids) or any(t['patient_id']!=data.patient_id for t in ts):fail('All procedures must belong to this patient and entity',409)
  total=sum(t['amount_paise'] for t in ts)
  if total<=0:fail('Estimate total must be positive')
  number=nextnum(c,eid,'EST')
  cur=c.execute('INSERT INTO estimates(entity_id,estimate_no,patient_id,total_paise,created_at) VALUES(?,?,?,?,?)',(eid,number,data.patient_id,total,utc()))
  for t in ts:c.execute('INSERT INTO estimate_items(entity_id,estimate_id,treatment_id,description,amount_paise) VALUES(?,?,?,?,?)',(eid,cur.lastrowid,t['id'],t['description'],t['amount_paise']))
  audit(c,u,eid,'created','estimate',cur.lastrowid)
 return {'id':cur.lastrowid,'estimate_no':number,'total_paise':total}

@app.post('/api/entities/{eid}/estimates/{estimate_id}/approve')
def approve_estimate(eid:int,estimate_id:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db(True) as c:
  x=one(c,'SELECT * FROM estimates WHERE entity_id=? AND id=?',(eid,estimate_id))
  if not x:fail('Estimate not found',404)
  if x['status']!='draft':fail('Only draft estimates can be approved',409)
  c.execute("UPDATE estimates SET status='approved' WHERE entity_id=? AND id=?",(eid,estimate_id))
  audit(c,u,eid,'approved','estimate',estimate_id)
 return {'ok':True}

@app.post('/api/entities/{eid}/estimates/{estimate_id}/invoice')
def convert_estimate(eid:int,estimate_id:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db(True) as c:
  x=one(c,'SELECT * FROM estimates WHERE entity_id=? AND id=?',(eid,estimate_id))
  if not x:fail('Estimate not found',404)
  if x['status']!='approved':fail('Estimate must be approved and not already invoiced',409)
  if one(c,'SELECT id FROM estimate_item_invoices WHERE estimate_id=? AND entity_id=? LIMIT 1',(estimate_id,eid)):fail('Use line selection to invoice remaining estimate items',409)
  number=nextnum(c,eid,'INV')
  lines=rows(c,'SELECT description FROM estimate_items WHERE estimate_id=? AND entity_id=?',(estimate_id,eid))
  cur=c.execute('INSERT INTO invoices(entity_id,invoice_no,patient_id,total_paise,description,created_at) VALUES(?,?,?,?,?,?)',(eid,number,x['patient_id'],x['total_paise'],'; '.join(z['description'] for z in lines),utc()))
  c.execute('INSERT INTO estimate_conversions(entity_id,estimate_id,invoice_id) VALUES(?,?,?)',(eid,estimate_id,cur.lastrowid))
  c.execute("UPDATE estimates SET status='invoiced' WHERE id=? AND entity_id=?",(estimate_id,eid))
  audit(c,u,eid,'invoiced','estimate',estimate_id)
 return {'id':cur.lastrowid,'invoice_no':number,'amount_paise':x['total_paise']}

# Version 0.4: line-level partial estimate invoicing; all selected rows post atomically.
@app.post('/api/entities/{eid}/estimates/{estimate_id}/invoice-selected')
def invoice_selected(eid:int,estimate_id:int,data:InvoiceSelectedIn,u=Depends(current)):
 access(eid,u,('admin','billing'))
 if len(set(data.item_ids))!=len(data.item_ids):fail('Duplicate estimate line selection')
 with db(True) as c:
  est=one(c,'SELECT * FROM estimates WHERE entity_id=? AND id=?',(eid,estimate_id))
  if not est:fail('Estimate not found',404)
  if est['status'] not in ('approved','invoiced'):fail('Estimate must first be approved',409)
  all_items=rows(c,'SELECT * FROM estimate_items WHERE entity_id=? AND estimate_id=?',(eid,estimate_id))
  if len(all_items)==0:fail('Estimate is empty',409)
  chosen=[x for x in all_items if x['id'] in data.item_ids]
  if len(chosen)!=len(data.item_ids):fail('Selected lines do not belong to the estimate and entity',409)
  already=rows(c,'SELECT estimate_item_id FROM estimate_item_invoices WHERE entity_id=? AND estimate_id=?',(eid,estimate_id))
  used={r['estimate_item_id'] for r in already}
  # Older full conversions are tracked in the historical table.
  if one(c,'SELECT invoice_id FROM estimate_conversions WHERE estimate_id=? AND entity_id=?',(estimate_id,eid)):fail('Estimate was fully converted previously',409)
  if any(x['id'] in used for x in chosen):fail('Estimate line has already been invoiced',409)
  total=sum(x['amount_paise'] for x in chosen)
  if total<=0:fail('Selected invoice amount must be positive')
  number=nextnum(c,eid,'INV')
  cur=c.execute('INSERT INTO invoices(entity_id,invoice_no,patient_id,total_paise,description,created_at) VALUES(?,?,?,?,?,?)',(eid,number,est['patient_id'],total,'; '.join(x['description'] for x in chosen),utc()))
  for x in chosen:c.execute('INSERT INTO estimate_item_invoices(entity_id,estimate_id,estimate_item_id,invoice_id,amount_paise) VALUES(?,?,?,?,?)',(eid,estimate_id,x['id'],cur.lastrowid,x['amount_paise']))
  if len(used)+len(chosen)==len(all_items):c.execute("UPDATE estimates SET status='invoiced' WHERE entity_id=? AND id=?",(eid,estimate_id))
  audit(c,u,eid,'partially_invoiced' if len(used)+len(chosen)<len(all_items) else 'invoiced','estimate',estimate_id)
  return {'id':cur.lastrowid,'invoice_no':number,'amount_paise':total,'remaining_lines':len(all_items)-len(used)-len(chosen)}

@app.get('/api/entities/{eid}/staff-accounts')
def staff_accounts(eid:int,u=Depends(current)):
 access(eid,u,('admin',))
 with db() as c:return rows(c,'SELECT u.id,u.username,u.active,m.role FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.entity_id=? ORDER BY u.username',(eid,))

@app.post('/api/entities/{eid}/staff-accounts')
def create_staff(eid:int,data:StaffCreateIn,u=Depends(current)):
 access(eid,u,('admin',))
 if data.role not in ('admin','reception','doctor','billing','viewer'):fail('Invalid staff role')
 name=data.username.strip().lower()
 if not re.fullmatch(r'[a-z0-9_.-]{3,60}',name):fail('Username can contain lowercase letters, numbers, dot, underscore or dash')
 with db(True) as c:
  if one(c,'SELECT id FROM users WHERE username=?',(name,)):fail('Username already exists; use entity membership instead',409)
  cur=c.execute('INSERT INTO users(username,password_hash) VALUES(?,?)',(name,password_hash(data.password)))
  c.execute('INSERT INTO memberships(user_id,entity_id,role) VALUES(?,?,?)',(cur.lastrowid,eid,data.role))
  audit(c,u,eid,'created','staff_account',cur.lastrowid)
  return {'id':cur.lastrowid,'username':name,'role':data.role}

@app.patch('/api/entities/{eid}/staff-accounts/{staff_id}/deactivate')
def deactivate_staff(eid:int,staff_id:int,u=Depends(current)):
 access(eid,u,('admin',))
 if staff_id==u['id']:fail('Cannot deactivate your own account',409)
 with db(True) as c:
  target=one(c,'SELECT u.id,u.active,u.is_superadmin FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.entity_id=? AND u.id=?',(eid,staff_id))
  if not target:fail('Staff account not found in selected entity',404)
  if target['is_superadmin']:fail('Cannot deactivate super administrator',403)
  if not target['active']:fail('Account already inactive',409)
  # This is global account deactivation, including other entity memberships.
  c.execute('UPDATE users SET active=0 WHERE id=?',(staff_id,))
  c.execute('DELETE FROM sessions WHERE user_id=?',(staff_id,))
  audit(c,u,eid,'globally_deactivated','staff_account',staff_id)
 return {'id':staff_id,'active':False,'sessions_revoked':True}

@app.get('/api/entities/{eid}/credit-notes')
def list_credit_notes(eid:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db() as c:
  return rows(c,'''SELECT cn.*,i.invoice_no,i.patient_id FROM credit_notes cn JOIN invoices i ON i.id=cn.invoice_id AND i.entity_id=cn.entity_id WHERE cn.entity_id=? ORDER BY cn.id DESC''',(eid,))

@app.post('/api/entities/{eid}/credit-notes',status_code=201)
def create_credit_note(eid:int,data:CreditNoteIn,u=Depends(current)):
 access(eid,u,('admin',))
 value=cents(data.amount)
 if value<=0:fail('Credit amount must be positive')
 if len(data.reason.strip())<5:fail('Reason must contain at least 5 characters')
 with db(True) as c:
  inv=one(c,'SELECT * FROM invoices WHERE entity_id=? AND id=?',(eid,data.invoice_id))
  if not inv:fail('Invoice not found in entity',404)
  credits=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM credit_notes WHERE entity_id=? AND invoice_id=?',(eid,inv['id'])).fetchone()[0]
  paid=c.execute('''SELECT COALESCE(SUM(a.amount_paise),0) FROM allocations a WHERE a.entity_id=? AND a.invoice_id=? AND NOT EXISTS(SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=a.entity_id AND rr.receipt_id=a.receipt_id)''',(eid,inv['id'])).fetchone()[0]
  if value>inv['total_paise']-credits-paid:fail('Credit exceeds unpaid invoice balance; paid amounts require separate refund workflow',409)
  number=nextnum(c,eid,'CRN')
  cur=c.execute('INSERT INTO credit_notes(entity_id,invoice_id,credit_no,amount_paise,reason,issued_by,created_at) VALUES(?,?,?,?,?,?,?)',(eid,inv['id'],number,value,data.reason.strip(),u['id'],utc()))
  audit(c,u,eid,'issued','credit_note',cur.lastrowid)
  return {'id':cur.lastrowid,'credit_no':number,'remaining_paise':inv['total_paise']-credits-paid-value}

@app.get('/api/entities/{eid}/refunds')
def refund_history(eid:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db() as c:
  return rows(c,'''SELECT rf.*,r.receipt_no,r.patient_id FROM recorded_refunds rf
     JOIN receipts r ON r.id=rf.receipt_id AND r.entity_id=rf.entity_id
     WHERE rf.entity_id=? ORDER BY rf.id DESC''',(eid,))

@app.post('/api/entities/{eid}/refunds',status_code=201)
def record_refund(eid:int,data:RefundIn,u=Depends(current)):
 access(eid,u,('admin',))
 amount=cents(data.amount)
 if amount<=0:fail('Refund amount must be greater than zero')
 if data.method not in ('cash','upi','card','bank','other'):fail('Invalid refund method')
 with db(True) as c:
  original=one(c,'''SELECT r.* FROM receipts r JOIN receipt_reversals rev
     ON rev.entity_id=r.entity_id AND rev.receipt_id=r.id
     WHERE r.entity_id=? AND r.id=?''',(eid,data.receipt_id))
  if not original:fail('A receipt must be reversed before refund recording',409)
  prior=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM recorded_refunds WHERE entity_id=? AND receipt_id=?',(eid,data.receipt_id)).fetchone()[0]
  if amount>original['amount_paise']-prior:fail('Refund exceeds remaining reversed receipt amount',409)
  number=nextnum(c,eid,'RFD')
  cur=c.execute('INSERT INTO recorded_refunds(entity_id,receipt_id,refund_no,amount_paise,method,reference,reason,recorded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
   (eid,data.receipt_id,number,amount,data.method,data.reference.strip(),data.reason.strip(),u['id'],utc()))
  audit(c,u,eid,'recorded','refund',cur.lastrowid)
 return {'id':cur.lastrowid,'refund_no':number,'remaining_refundable_paise':original['amount_paise']-prior-amount,'money_transferred':False}

@app.get('/api/entities/{eid}/finance-summary')
def finance_summary(eid:int,u=Depends(current)):
 access(eid,u,('admin','billing'))
 with db() as c:
  billed=c.execute('SELECT COALESCE(SUM(total_paise),0) FROM invoices WHERE entity_id=?',(eid,)).fetchone()[0]
  credited=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM credit_notes WHERE entity_id=?',(eid,)).fetchone()[0]
  written_off=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM financial_writeoffs WHERE entity_id=?',(eid,)).fetchone()[0]
  collected=c.execute('''SELECT COALESCE(SUM(amount_paise),0) FROM receipts r WHERE entity_id=? AND NOT EXISTS
     (SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=r.entity_id AND rr.receipt_id=r.id) AND NOT EXISTS(SELECT 1 FROM advance_transfers_v2 t WHERE t.dest_entity_id=r.entity_id AND t.dest_receipt_id=r.id)''',(eid,)).fetchone()[0]
  allocated=c.execute('''SELECT COALESCE(SUM(a.amount_paise),0) FROM allocations a JOIN receipts r
     ON r.id=a.receipt_id AND r.entity_id=a.entity_id WHERE a.entity_id=? AND NOT EXISTS
     (SELECT 1 FROM receipt_reversals rr WHERE rr.entity_id=r.entity_id AND rr.receipt_id=r.id)''',(eid,)).fetchone()[0]
  refunds=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM recorded_refunds WHERE entity_id=?',(eid,)).fetchone()[0]
  advance_refunds=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM advance_refunds_v2 WHERE entity_id=?',(eid,)).fetchone()[0]
  transfer_out=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM advance_transfers_v2 WHERE source_entity_id=?',(eid,)).fetchone()[0]
  transfer_in=c.execute('SELECT COALESCE(SUM(amount_paise),0) FROM advance_transfers_v2 WHERE dest_entity_id=?',(eid,)).fetchone()[0]
 return {'entity_id':eid,'invoiced_paise':billed,'credited_paise':credited,
  'net_invoiced_paise':billed-credited-written_off,'writeoffs_paise':written_off,'allocated_paise':allocated,
  'outstanding_paise':billed-credited-written_off-allocated,'active_receipts_paise':collected,
  'unallocated_receipts_paise':collected+transfer_in-allocated-advance_refunds-transfer_out,'recorded_refunds_paise':refunds,'advance_refunds_paise':advance_refunds,'transfers_in_paise':transfer_in,'transfers_out_paise':transfer_out,
  'note':'Amounts are operational aggregates; refunds are recorded separately after receipt reversal, not bank-confirmed settlements.'}

@app.get('/api/entities/{eid}/consents')
def list_consents(eid:int,patient_id:int,u=Depends(current)):
 access(eid,u,('admin','doctor','reception'))
 with db() as c:
  must(c,'patients',eid,patient_id)
  return rows(c,'SELECT id,entity_id,patient_id,visit_id,procedure_description,consent_version,consent_text,acknowledged_by,acknowledged_at,recorded_by,created_at FROM patient_consents WHERE entity_id=? AND patient_id=? ORDER BY id DESC',(eid,patient_id))

@app.post('/api/entities/{eid}/consents')
def create_consent(eid:int,data:ConsentIn,u=Depends(current)):
 access(eid,u,('admin','doctor'))
 at=instant(data.acknowledged_at)
 with db(True) as c:
  must(c,'patients',eid,data.patient_id)
  if data.visit_id:
   visit=one(c,'SELECT patient_id FROM visits WHERE entity_id=? AND id=?',(eid,data.visit_id))
   if not visit or visit['patient_id']!=data.patient_id:fail('Consent visit must belong to patient and entity',409)
  cur=c.execute('INSERT INTO patient_consents(entity_id,patient_id,visit_id,procedure_description,consent_version,consent_text,acknowledged_by,acknowledged_at,recorded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(eid,data.patient_id,data.visit_id,data.procedure_description,data.consent_version,data.consent_text,data.acknowledged_by,at,u['id'],utc()))
  audit(c,u,eid,'recorded','patient_consent',cur.lastrowid)
  return {'id':cur.lastrowid}

# Version 0.7 — explicit booking rules and shared staff identity (no shared patient identity).
@app.get('/api/entities/{eid}/doctor-booking-rules')
def list_booking_rules(eid:int,u=Depends(current)):
 access(eid,u)
 with db() as c:return rows(c,'SELECT d.id doctor_id,d.name,COALESCE(r.enforce_slots,0) enforce_slots FROM doctors d LEFT JOIN doctor_booking_rules r ON r.entity_id=d.entity_id AND r.doctor_id=d.id WHERE d.entity_id=? ORDER BY d.name',(eid,))

@app.put('/api/entities/{eid}/doctors/{doctor_id}/booking-rules')
def change_booking_rules(eid:int,doctor_id:int,payload:BookingRulesIn,u=Depends(current)):
 access(eid,u,('admin',))
 with db(True) as c:
  must(c,'doctors',eid,doctor_id)
  if payload.enforce_slots and not one(c,'SELECT id FROM doctor_slots WHERE entity_id=? AND doctor_id=? AND active=1',(eid,doctor_id)):
   fail('Configure at least one recurring opening slot before enabling enforcement',409)
  c.execute('INSERT INTO doctor_booking_rules(entity_id,doctor_id,enforce_slots) VALUES(?,?,?) ON CONFLICT(entity_id,doctor_id) DO UPDATE SET enforce_slots=excluded.enforce_slots',(eid,doctor_id,int(payload.enforce_slots)))
  audit(c,u,eid,'booking_rules_updated','doctor',doctor_id)
 return {'doctor_id':doctor_id,'enforce_slots':payload.enforce_slots}

@app.get('/api/clinician-links')
def list_clinician_links(u=Depends(current)):
 ensure_entity_admin(u)
 with db() as c:return rows(c,'SELECT l.entity_id,l.doctor_id,l.clinician_key,d.name,e.name entity_name FROM clinician_links l JOIN doctors d ON d.entity_id=l.entity_id AND d.id=l.doctor_id JOIN entities e ON e.id=l.entity_id ORDER BY l.clinician_key,e.id')

@app.post('/api/clinician-links',status_code=201)
def link_clinicians(payload:ClinicianLinkIn,u=Depends(current)):
 ensure_entity_admin(u)
 profiles=[]
 for p in payload.profiles:
  if not isinstance(p,dict) or type(p.get('entity_id'))!=int or type(p.get('doctor_id'))!=int:fail('Each profile must provide integer entity_id and doctor_id')
  profiles.append((p['entity_id'],p['doctor_id']))
 if len(set(profiles))!=len(profiles):fail('Duplicate doctor profile')
 if len({x[0] for x in profiles})!=len(profiles):fail('Choose at most one doctor profile per entity')
 with db(True) as c:
  for eid,did in profiles:
   must(c,'doctors',eid,did)
   if one(c,'SELECT clinician_key FROM clinician_links WHERE entity_id=? AND doctor_id=?',(eid,did)):
    fail('A selected doctor profile is already linked',409)
  placeholders=','.join('(?,?)' for _ in profiles)
  # Detect existing overlapping appointments or time off before establishing identity links.
  for i,(e1,d1) in enumerate(profiles):
   for e2,d2 in profiles[i+1:]:
    colliding=one(c,"""SELECT a.id FROM appointments a JOIN appointments b ON a.start_time<b.end_time AND a.end_time>b.start_time
        WHERE a.entity_id=? AND a.doctor_id=? AND b.entity_id=? AND b.doctor_id=?
        AND a.status NOT IN ('cancelled','no_show') AND b.status NOT IN ('cancelled','no_show') LIMIT 1""",(e1,d1,e2,d2))
    if colliding:fail('Resolve existing cross-entity bookings before linking doctors',409)
    for (ae,ad,te,td) in ((e1,d1,e2,d2),(e2,d2,e1,d1)):
     leave_overlap=one(c,"""SELECT a.id FROM appointments a JOIN doctor_time_off t ON a.start_time<t.end_time AND a.end_time>t.start_time
         WHERE a.entity_id=? AND a.doctor_id=? AND t.entity_id=? AND t.doctor_id=?
         AND a.status NOT IN ('cancelled','no_show') LIMIT 1""",(ae,ad,te,td))
     if leave_overlap:fail('Resolve conflicting time off and appointments before linking doctors',409)
  key=str(uuid.uuid4())
  for eid,did in profiles:
   c.execute('INSERT INTO clinician_links(entity_id,doctor_id,clinician_key) VALUES(?,?,?)',(eid,did,key))
   audit(c,u,eid,'doctor_identity_linked','doctor',did)
 return {'clinician_key':key,'linked_count':len(profiles)}

@app.post('/api/entities/{eid}/receipts/{rid}/reverse',status_code=201)
def reverse_receipt(eid:int,rid:int,payload:ReceiptReverseIn,u=Depends(current)):
 access(eid,u,('admin',))
 with db(True) as c:
  receipt=one(c,'SELECT id FROM receipts WHERE entity_id=? AND id=?',(eid,rid))
  if not receipt:fail('Receipt not found in entity',404)
  if one(c,'SELECT id FROM receipt_reversals WHERE entity_id=? AND receipt_id=?',(eid,rid)):
   fail('Receipt already reversed',409)
  c.execute('INSERT INTO receipt_reversals(entity_id,receipt_id,reason,performed_by,created_at) VALUES(?,?,?,?,?)',(eid,rid,payload.reason.strip(),u['id'],utc()))
  audit(c,u,eid,'reversed','receipt',rid)
 return {'receipt_id':rid,'reversed':True,'message':'Receipt reversed; historical record retained'}

@app.get('/api/health')
def health():return {'status':'ok'}
init()
import advanced_v02
advanced_v02.install(db,utc)
advanced_v02.register(app,globals())
import bulk_templates_v04
bulk_templates_v04.register(app,globals())


# Version 0.5 clinical document module. Development file backend: private on-disk directory.
# Never place DOCUMENT_ROOT under frontend/public, nginx static directories, or shared mounts.
ALLOWED_CATEGORIES={'xray','clinical_photo','consent','report','other'}
def file_signature(data: bytes, name: str):
    ext=Path(name).suffix.lower()
    if ext in ('.jpg','.jpeg') and data.startswith(bytes.fromhex('ffd8ff')):return 'image/jpeg'
    if ext=='.png' and data.startswith(bytes.fromhex('89504e470d0a1a0a')):return 'image/png'
    if ext=='.pdf' and data.startswith(b'%PDF-'):return 'application/pdf'
    return None

def check_visit_patient(c,eid,patient_id,visit_id):
    must(c,'patients',eid,patient_id)
    if visit_id is not None:
        visit=one(c,'SELECT patient_id FROM visits WHERE id=? AND entity_id=?',(visit_id,eid))
        if not visit or visit['patient_id']!=patient_id:fail('Visit does not belong to this patient',409)

@app.get('/api/entities/{eid}/patients/{pid}/documents')
def list_documents(eid:int,pid:int,u=Depends(current)):
    access(eid,u,('admin','reception','doctor','viewer'))
    with db() as c:
        must(c,'patients',eid,pid)
        return rows(c,'''SELECT id,patient_id,visit_id,category,original_name,mime_type,size_bytes,sha256,created_at
        FROM patient_documents WHERE entity_id=? AND patient_id=? ORDER BY id DESC''',(eid,pid))

@app.post('/api/entities/{eid}/patients/{pid}/documents',status_code=201)
async def upload_document(eid:int,pid:int,uploaded:UploadFile=File(...),category:str=Form('other'),visit_id:Optional[int]=Form(None),u=Depends(current)):
    access(eid,u,('admin','reception','doctor'))
    if category not in ALLOWED_CATEGORIES:fail('Invalid document category')
    raw_name=(uploaded.filename or '').replace('\\','/').split('/')[-1].strip()
    if not raw_name or len(raw_name)>180 or any(ord(ch)<32 for ch in raw_name):fail('Invalid file name')
    with db() as c:check_visit_patient(c,eid,pid,visit_id)
    # Read one byte beyond the limit; rejects oversized uploads even if Content-Length is misleading.
    data=await uploaded.read(MAX_UPLOAD_BYTES+1)
    if not data or len(data)>MAX_UPLOAD_BYTES:fail('File empty or larger than 10 MB',413)
    mime=file_signature(data,raw_name)
    if not mime:fail('Only JPEG, PNG, and PDF with valid file signatures are accepted',415)
    # Refuse PDF active content as a precaution; robust malware scanning is still required for production.
    if mime=='application/pdf' and (b'/JavaScript' in data or b'/JS ' in data or b'/Launch' in data):fail('Active PDF content not supported',415)
    stored=uuid.uuid4().hex+Path(raw_name).suffix.lower()
    # Create a new random filename exclusively, with owner-only file permissions.
    entity_dir=DOCUMENT_ROOT/str(eid)
    entity_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    target=entity_dir/stored
    with target.open('xb') as fp:
        os.chmod(target,0o600)
        fp.write(data)
    try:
        with db(True) as c:
            check_visit_patient(c,eid,pid,visit_id)
            cur=c.execute('''INSERT INTO patient_documents(entity_id,patient_id,visit_id,category,original_name,stored_name,mime_type,size_bytes,sha256,uploaded_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(eid,pid,visit_id,category,raw_name,stored,mime,len(data),hashlib.sha256(data).hexdigest(),u['id'],utc()))
            audit(c,u,eid,'upload','patient_document',cur.lastrowid)
            result={'id':cur.lastrowid,'patient_id':pid,'category':category,'original_name':raw_name,'mime_type':mime,'size_bytes':len(data)}
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return result

@app.get('/api/entities/{eid}/patients/{pid}/documents/{did}/preview')
def preview_document_v24(eid:int,pid:int,did:int,u=Depends(current)):
    access(eid,u,('admin','reception','doctor','viewer'))
    with db(True) as c:
        must(c,'patients',eid,pid)
        record=one(c,'SELECT * FROM patient_documents WHERE id=? AND entity_id=? AND patient_id=?',(did,eid,pid))
        if not record:fail('Document not found',404)
        audit(c,u,eid,'preview','patient_document',did)
    target=DOCUMENT_ROOT/str(eid)/record['stored_name']
    if not target.is_file():fail('Document unavailable',404)
    return FileResponse(target,media_type=record['mime_type'],content_disposition_type='inline',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; sandbox"})

@app.get('/api/entities/{eid}/patients/{pid}/documents/{did}/download')
def download_document(eid:int,pid:int,did:int,u=Depends(current)):
    access(eid,u,('admin','reception','doctor','viewer'))
    with db(True) as c:
        must(c,'patients',eid,pid)
        record=one(c,'SELECT * FROM patient_documents WHERE id=? AND entity_id=? AND patient_id=?',(did,eid,pid))
        if not record:fail('Document not found',404)
        audit(c,u,eid,'download','patient_document',did)
    target=DOCUMENT_ROOT/str(eid)/record['stored_name']
    if not target.is_file():fail('Document storage object unavailable',404)
    return FileResponse(target,media_type=record['mime_type'],filename=record['original_name'],content_disposition_type='attachment',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


# v0.6 – signed clinical notes and append-only addenda
# V2.4: opt-in entity resource visibility, never deletes stored resources.
@app.get('/api/entities/{eid}/features')
def entity_features_v24(eid:int,u=Depends(current)):
    access(eid,u)
    with db() as c:
        row=one(c,'SELECT chair_ot_enabled FROM entity_features WHERE entity_id=?',(eid,))
        return {'chair_ot_enabled':bool(row['chair_ot_enabled']) if row else False}

@app.put('/api/entities/{eid}/features')
def update_entity_features_v24(eid:int,data:EntityFeaturesV24,u=Depends(current)):
    if not u['is_superadmin']:fail('Super administrator required',403)
    access(eid,u)
    with db(True) as c:
        c.execute('INSERT INTO entity_features(entity_id,chair_ot_enabled) VALUES(?,?) ON CONFLICT(entity_id) DO UPDATE SET chair_ot_enabled=excluded.chair_ot_enabled',(eid,int(data.chair_ot_enabled)))
        audit(c,u,eid,'feature_visibility_updated','entity',eid)
    return {'chair_ot_enabled':data.chair_ot_enabled}

@app.post('/api/entities/{eid}/clinical-notes/v24',status_code=201)
def create_note_v24(eid:int,data:NoteCreateV24,u=Depends(current)):
    access(eid,u,('admin','doctor'))
    if not data.body.strip():fail('Empty clinical note')
    if data.save_method not in ('auto','manual','edit'):fail('Invalid save method')
    with db(True) as c:
        check_visit_patient(c,eid,data.patient_id,data.visit_id)
        if data.doctor_id is not None:must(c,'doctors',eid,data.doctor_id)
        cur=c.execute('INSERT INTO clinical_notes(entity_id,patient_id,visit_id,author_user_id,body,created_at) VALUES(?,?,?,?,?,?)',(eid,data.patient_id,data.visit_id,u['id'],data.body.strip(),utc()))
        note_id=cur.lastrowid
        at=utc()
        c.execute('INSERT INTO clinical_note_revisions(entity_id,note_id,version,doctor_id,body,previous_body,edited_by,save_method,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(eid,note_id,1,data.doctor_id,data.body.strip(),'',u['id'],data.save_method,at))
        audit(c,u,eid,'clinical_note_'+data.save_method+'_created','clinical_note',note_id)
        return {'id':note_id,'version':1,'saved_at':at}

@app.put('/api/entities/{eid}/clinical-notes/{note_id}/content')
def update_note_v24(eid:int,note_id:int,data:NoteEditV24,u=Depends(current)):
    access(eid,u,('admin','doctor'))
    if data.save_method not in ('auto','manual','edit'):fail('Invalid save method')
    if not data.body.strip():fail('Empty clinical note')
    with db(True) as c:
        n=one(c,'SELECT * FROM clinical_notes WHERE id=? AND entity_id=?',(note_id,eid))
        if not n:fail('Clinical note not found',404)
        # Edits to other users' notes require entity admin permission.
        with_role=one(c,'SELECT role FROM memberships WHERE entity_id=? AND user_id=?',(eid,u['id']))
        if n['author_user_id']!=u['id'] and not u['is_superadmin'] and (not with_role or with_role['role']!='admin'):fail('Only note author or administrator may edit',403)
        if data.doctor_id is not None:must(c,'doctors',eid,data.doctor_id)
        latest=one(c,'SELECT version,body,doctor_id FROM clinical_note_revisions WHERE entity_id=? AND note_id=? ORDER BY version DESC LIMIT 1',(eid,note_id))
        current_version=latest['version'] if latest else 0
        old_body=latest['body'] if latest else n['body']
        old_doctor=latest['doctor_id'] if latest else None
        if data.expected_version!=current_version:fail('Note changed in another session. Refresh before saving.',409)
        if old_body==data.body.strip() and old_doctor==data.doctor_id:return {'id':note_id,'version':current_version,'unchanged':True}
        at=utc()
        c.execute('INSERT INTO clinical_note_revisions(entity_id,note_id,version,doctor_id,body,previous_body,edited_by,save_method,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(eid,note_id,current_version+1,data.doctor_id,data.body.strip(),old_body,u['id'],data.save_method,at))
        # Original signed notes and their signed_at remain unchanged.
        if n['status']=='draft':c.execute('UPDATE clinical_notes SET body=? WHERE entity_id=? AND id=?',(data.body.strip(),eid,note_id))
        audit(c,u,eid,'clinical_note_'+data.save_method+'_revision','clinical_note',note_id)
        return {'id':note_id,'version':current_version+1,'saved_at':at}

@app.get('/api/entities/{eid}/clinical-notes/{note_id}/revisions')
def revisions_v24(eid:int,note_id:int,u=Depends(current)):
    access(eid,u,('admin','doctor'))
    with db() as c:
        if not one(c,'SELECT id FROM clinical_notes WHERE entity_id=? AND id=?',(eid,note_id)):fail('Clinical note not found',404)
        return rows(c,'''SELECT r.version,r.body,r.previous_body,r.doctor_id,r.edited_by,r.save_method,r.created_at,u.username editor_name
        FROM clinical_note_revisions r JOIN users u ON u.id=r.edited_by WHERE r.entity_id=? AND r.note_id=? ORDER BY r.version DESC''',(eid,note_id))

@app.get('/api/entities/{eid}/clinical-notes')
def list_clinical_notes(eid:int,patient_id:int,u=Depends(current)):
    role=access(eid,u,('admin','doctor','viewer'))
    with db() as c:
        must(c,'patients',eid,patient_id)
        # Drafts remain private to their author; administrators may see them for workflow review.
        notes=rows(c,'''SELECT n.*,au.username author_name FROM clinical_notes n JOIN users au ON au.id=n.author_user_id
          WHERE n.entity_id=? AND n.patient_id=? AND (n.status='signed' OR n.author_user_id=? OR ?='admin') ORDER BY n.id DESC''',(eid,patient_id,u['id'],role))
        for n in notes:
            history=rows(c,'''SELECT r.version,r.body,r.previous_body,r.doctor_id,r.edited_by,r.save_method,r.created_at,u.username editor_name,d.name doctor_name
              FROM clinical_note_revisions r JOIN users u ON u.id=r.edited_by LEFT JOIN doctors d ON d.id=r.doctor_id AND d.entity_id=r.entity_id
              WHERE r.entity_id=? AND r.note_id=? ORDER BY r.version''',(eid,n['id']))
            n['current_body']=history[-1]['body'] if history else n['body']
            n['version']=history[-1]['version'] if history else 0
            n['doctor_id']=history[-1]['doctor_id'] if history else None
            n['doctor_name']=history[-1]['doctor_name'] if history else None
            n['edited_by_name']=history[-1]['editor_name'] if history else n['author_name']
            n['last_edited_at']=history[-1]['created_at'] if history else n['created_at']
            n['revisions']=history
            n['addenda']=rows(c,'''SELECT a.id,a.body,a.reason,a.created_at,au.username author_name FROM clinical_note_addenda a JOIN users au ON au.id=a.author_user_id
              WHERE a.entity_id=? AND a.note_id=? ORDER BY a.id''',(eid,n['id']))
        return notes

@app.post('/api/entities/{eid}/clinical-notes',status_code=201)
def create_clinical_note(eid:int,data:ClinicalNoteIn,u=Depends(current)):
    access(eid,u,('admin','doctor'))
    if not data.body.strip():fail('Clinical note cannot be empty')
    with db(True) as c:
        must(c,'patients',eid,data.patient_id)
        v=one(c,'SELECT patient_id FROM visits WHERE id=? AND entity_id=?',(data.visit_id,eid))
        if not v or v['patient_id']!=data.patient_id:fail('Visit must belong to the selected patient and entity',409)
        cur=c.execute('INSERT INTO clinical_notes(entity_id,patient_id,visit_id,author_user_id,body,created_at) VALUES(?,?,?,?,?,?)',(eid,data.patient_id,data.visit_id,u['id'],data.body.strip(),utc()))
        audit(c,u,eid,'created','clinical_note',cur.lastrowid)
        return {'id':cur.lastrowid,'status':'draft'}

@app.post('/api/entities/{eid}/clinical-notes/{note_id}/sign')
def sign_clinical_note(eid:int,note_id:int,u=Depends(current)):
    access(eid,u,('admin','doctor'))
    with db(True) as c:
        n=one(c,'SELECT * FROM clinical_notes WHERE entity_id=? AND id=?',(eid,note_id))
        if not n:fail('Clinical note not found',404)
        if n['author_user_id']!=u['id']:fail('Only the author can sign their note',403)
        if n['status']!='draft':fail('Note already signed',409)
        at=utc()
        c.execute('UPDATE clinical_notes SET status=?,signed_at=? WHERE entity_id=? AND id=? AND status=?',('signed',at,eid,note_id,'draft'))
        audit(c,u,eid,'signed','clinical_note',note_id)
        return {'id':note_id,'status':'signed','signed_at':at}

@app.post('/api/entities/{eid}/clinical-notes/{note_id}/addenda',status_code=201)
def add_clinical_addendum(eid:int,note_id:int,data:NoteAmendIn,u=Depends(current)):
    access(eid,u,('admin','doctor'))
    if not data.body.strip() or not data.reason.strip():fail('Addendum and reason required')
    with db(True) as c:
        n=one(c,'SELECT * FROM clinical_notes WHERE entity_id=? AND id=?',(eid,note_id))
        if not n:fail('Clinical note not found',404)
        if n['status']!='signed':fail('Sign the original note before adding an addendum',409)
        cur=c.execute('INSERT INTO clinical_note_addenda(entity_id,note_id,author_user_id,body,reason,created_at) VALUES(?,?,?,?,?,?)',(eid,note_id,u['id'],data.body.strip(),data.reason.strip(),utc()))
        audit(c,u,eid,'addendum_created','clinical_note',note_id)
        return {'id':cur.lastrowid,'note_id':note_id}
