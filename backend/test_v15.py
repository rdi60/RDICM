"""V1.5 portable semantic auditing and fail-closed staging validation (offline)."""
import os,sys,tempfile,sqlite3,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'migration'))
sys.path.insert(0,str(ROOT/'backend'))
from postgres_validate import check_semantics,check_columns,verify_staging
from audit_integrity import CHECKS

with tempfile.TemporaryDirectory() as td:
 os.environ['DENTAL_DB']=str(Path(td)/'synthetic.sqlite')
 import app
 app.init()
 app.seed_admin('v15synth','LongSyntheticPassword15!')
 with sqlite3.connect(os.environ['DENTAL_DB']) as c:
  assert check_semantics(c.cursor())==len(CHECKS)
  c.execute('INSERT INTO patients(entity_id,uhid,name,created_at) VALUES(?,?,?,?)', (1,'CL-V15-1','Fake Patient',app.utc()))
  c.execute('INSERT INTO patients(entity_id,uhid,name,created_at) VALUES(?,?,?,?)', (1,'CL-V15-2','Another Fake Patient',app.utc()))
  c.execute('INSERT INTO visits(entity_id,visit_no,patient_id,created_at) VALUES(?,?,?,?)',(1,'CL-V15-VIS',1,app.utc()))
  c.execute('INSERT INTO patient_consents(entity_id,patient_id,visit_id,procedure_description,consent_version,consent_text,acknowledged_by,acknowledged_at,recorded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)', (1,2,1,'Synthetic','v1','Synthetic consent','Fake',app.utc(),1,app.utc()))
  try:check_semantics(c.cursor())
  except ValueError as exc:
   assert 'consent_patient_mismatch' in str(exc)
   assert 'Fake Patient' not in str(exc)
  else:raise AssertionError('Semantic check should reject mismatched clinical owner')
  c.rollback()
 from export_sqlite import export
 exp=Path(td)/'private-export'
 export(os.environ['DENTAL_DB'],exp)
 try:verify_staging(os.environ['DENTAL_DB'],exp)
 except ValueError as exc:assert 'RAJAN_STAGE_DSN' in str(exc)
 else:raise AssertionError('Missing DSN should fail closed')
 # Rejected before connection is attempted, even with a supplied DSN.
 with (exp/'patients.jsonl').open('a') as f:f.write('{}\n')
 try:verify_staging(os.environ['DENTAL_DB'],exp,dsn='postgresql://synthetic')
 except ValueError as exc:assert 'Hash mismatch' in str(exc)
 else:raise AssertionError('Tampered export should fail before connection')

# Review-only catalog structural comparison, using a simulated cursor.
class FakeCursor:
 def __init__(self, records):self.records=records
 def execute(self,sql,params=()):self.sql=sql;self.params=params
 def fetchall(self):return self.records

f=FakeCursor([('patients','id',1),('patients','entity_id',2)])
assert check_columns(f,{'patients':{'columns':[{'name':'id'},{'name':'entity_id'}]}})==1
try:check_columns(f,{'patients':{'columns':[{'name':'id'}]}})
except ValueError:pass
else:raise AssertionError('Schema mismatch not detected')
from pg_scope import scoped_cursor
for bad in (0,-1,True,'1',None):
 try:
  with scoped_cursor(bad,dsn='postgresql://synthetic'):pass
 except ValueError:pass
 else:raise AssertionError('Unsafe entity id accepted')
try:
 with scoped_cursor(1,dsn=None):pass
except ValueError as exc:assert 'RAJAN_PG_DSN' in str(exc)
else:raise AssertionError('Missing PG DSN accepted')
print('PASS v1.5: portable semantic checks, source tamper rejection, missing DSN and schema mismatch')
