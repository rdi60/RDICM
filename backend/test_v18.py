"""Synthetic-only PostgreSQL pilot visit unit tests; no live PostgreSQL server."""
import sys,os,tempfile
from pathlib import Path
from contextlib import contextmanager
from fastapi.testclient import TestClient
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'migration'))
sys.path.insert(0,str(root/'backend'))
from pg_patient_pilot import create_registration,check_in,create_visit,list_visits,PilotError
from test_v17 import PilotCursor

class VisitsCursor(PilotCursor):
    def __init__(self):
        super().__init__();self.visits={};self.ids['visit']=0
    def execute(self,sql,params=()):
        if 'INSERT INTO rajan_pilot.visits' in sql:
            eid,pid,num,complaint=params
            assert self.patients[pid][1]==eid
            self.ids['visit']+=1
            vid=self.ids['visit']
            self.visits[vid]=(vid,eid,pid,num,complaint,'2026-01-01T00:00:00Z')
            self.last=[(vid,)]
        elif 'SELECT id,visit_number,chief_complaint,created_at FROM rajan_pilot.visits' in sql:
            eid,pid=params
            self.last=[(v[0],v[3],v[4],v[5]) for v in reversed(list(self.visits.values())) if v[1]==eid and v[2]==pid]
        else:
            super().execute(sql,params)

cur=VisitsCursor()
@contextmanager
def fake_scope(eid,read_only=False):
    assert eid in (1,2)
    yield cur

r=create_registration(1,'CL','Synthetic Patient A',scope=fake_scope)
p=check_in(1,'CL',r['id'],scope=fake_scope)['patient']
r2=create_registration(2,'TR','Synthetic Patient B',scope=fake_scope)
p2=check_in(2,'TR',r2['id'],scope=fake_scope)['patient']
v=create_visit(1,'CL',p['id'],'Tooth sensitivity',scope=fake_scope)
assert v['visit_number']=='CL-VIS-000001'
assert len(list_visits(1,'CL',p['id'],scope=fake_scope)['visits'])==1
assert list_visits(2,'TR',p2['id'],scope=fake_scope)['visits']==[]
for args in [(2,'TR',p['id']), (1,'CL',p2['id']), (1,'CL',-1)]:
    try:create_visit(*args,scope=fake_scope)
    except PilotError:pass
    else:raise AssertionError('Accepted invalid/cross-entity patient')
try:list_visits(2,'TR',p['id'],scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Exposed another entity visits')
try:create_visit(1,'CL',p['id'],'x'*2001,scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Accepted excessive complaint')
assert 'FOREIGN KEY(entity_id,patient_id)' in (root/'migration/pg_patient_pilot.sql').read_text()
assert "'visits'" in (root/'migration/pg_patient_pilot.sql').read_text()

with tempfile.TemporaryDirectory() as td:
    os.environ['DENTAL_DB']=str(Path(td)/'test.sqlite')
    import app
    app.DB=Path(os.environ['DENTAL_DB'])
    app.init();app.seed_admin('v18admin','SyntheticStrongPassword18!')
    client=TestClient(app.app)
    token=client.post('/api/login',json={'username':'v18admin','password':'SyntheticStrongPassword18!'}).json()['token']
    h={'Authorization':f'Bearer {token}'}
    assert client.post('/api/entities/1/pg-pilot/visits',headers=h,json={'patient_id':1}).status_code==503
    assert client.get('/api/entities/1/pg-pilot/patients/1/visits',headers=h).status_code==503
    assert client.get('/api/entities/1/pg-pilot/patients/1/visits').status_code==401
    assert client.post('/api/entities/1/pg-pilot/visits',headers=h,json={'patient_id':-1}).status_code==422
print('PASS v1.8: pilot visits, patient ownership, separate entities, fail-closed HTTP')
