"""Version 1.6 synthetic tests: fail-closed runtime canary and API authorization."""
import sys, os, tempfile
from pathlib import Path
from contextlib import contextmanager
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'migration'))
sys.path.insert(0,str(ROOT/'backend'))
from pg_runtime_probe import checked_schema,check_rls,count_only,REQUIRED

for name in ('public','rajan_stage','pg_catalog','pg_too','bad-name','A;DROP'):
 try:checked_schema(name)
 except ValueError:pass
 else:raise AssertionError('Accepted unsafe schema '+name)
assert checked_schema('rajan_runtime')=='rajan_runtime'

class FakeCursor:
 def __init__(self, missing=False, extra_policy=False, bad_rls=False):
  self.sql='';self.params=None
  self.missing=missing;self.extra_policy=extra_policy;self.bad_rls=bad_rls
  self.counts=[]
 def execute(self,sql,params=()):
  self.sql=sql;self.params=params
  if 'COUNT(*)' in sql:self.counts.append(params[0])
 def fetchall(self):
  if 'FROM pg_class' in self.sql:
   return [(t,not (self.bad_rls and t=='patients'),True) for t in REQUIRED if not (self.missing and t=='patients')]
  if 'FROM pg_policies' in self.sql:
   records=[(t,'scoped_entity','PERMISSIVE',['public'],'ALL',"entity_id = current_setting('app.entity_id')::bigint", "entity_id = current_setting('app.entity_id')::bigint") for t in REQUIRED]
   if self.extra_policy:records.append(('patients','allow_everything','PERMISSIVE',['public'],'ALL','true','true'))
   return records
  raise AssertionError('Unexpected metadata query')
 def fetchone(self):
  if 'COUNT(*)' in self.sql:return (5,)
  raise AssertionError('Unexpected fetchone')

for opts in ({'missing':True},{'extra_policy':True},{'bad_rls':True}):
 try:check_rls(FakeCursor(**opts),'rajan_runtime')
 except ValueError:pass
 else:raise AssertionError('Unsafe RLS metadata accepted')

@contextmanager
def fake_scope(entity_id,dsn=None,read_only=False):
 assert entity_id==1 and read_only is True
 cur=FakeCursor()
 yield cur
 assert cur.counts==[1]*len(REQUIRED)
result=count_only(1,cursor_factory=fake_scope)
assert result['mode']=='read_only_canary' and result['counts']['patients']==5
assert result['cutover_completed'] is False

with tempfile.TemporaryDirectory() as td:
 os.environ['DENTAL_DB']=str(Path(td)/'synthetic.sqlite')
 import app
 app.DB=Path(os.environ['DENTAL_DB'])
 app.init()
 app.seed_admin('v16admin','LongSyntheticPassword16!')
 client=TestClient(app.app)
 res=client.post('/api/login',json={'username':'v16admin','password':'LongSyntheticPassword16!'})
 assert res.status_code==200,res.text
 token=res.json()['token']
 headers={'Authorization':'Bearer '+token}
 r=client.get('/api/entities/1/postgres-readiness',headers=headers)
 assert r.status_code==503
 os.environ['RAJAN_ENABLE_PG_PROBE']='1'
 r=client.get('/api/entities/1/postgres-readiness',headers=headers)
 assert r.status_code==503 # no DSN/psycopg available
 r=client.get('/api/entities/1/postgres-readiness')
 assert r.status_code==401
 r=client.get('/api/entities/999/postgres-readiness',headers=headers)
 assert r.status_code in (403,404)
 del os.environ['RAJAN_ENABLE_PG_PROBE']
print('PASS v1.6: scoped canary, RLS checks, disabled/missing-DB behavior and auth')
