"""v1.7 unit tests with fake PostgreSQL cursor; NOT a live PostgreSQL test."""
import sys,os,tempfile
from pathlib import Path
from contextlib import contextmanager
from fastapi.testclient import TestClient
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'migration'))
sys.path.insert(0,str(root/'backend'))
from pg_patient_pilot import create_registration,check_in,list_patients,PilotError,check_pilot_security,TABLES

class PilotCursor:
    def __init__(self):
        self.entities={1:'CL',2:'TR'}
        self.counters={}
        self.registrations={}
        self.patients={}
        self.last=[]
        self.ids={'reg':0,'patient':0}
        self.invalid_rls=False
        self.excess_policy=False
    def execute(self,sql,params=()):
        self.last=[]
        if 'FROM pg_class' in sql:
            self.last=[(t,not (self.invalid_rls and t=='patients'),True) for t in TABLES]
        elif 'FROM pg_policies' in sql:
            self.last=[(t,'scoped_entity','PERMISSIVE',['public'],'ALL',"entity_id = current_setting('app.entity_id')::bigint","entity_id = current_setting('app.entity_id')::bigint") for t in TABLES]
            if self.excess_policy:self.last.append(('patients','extra','PERMISSIVE',['public'],'ALL','true','true'))
        elif 'SELECT code FROM rajan_pilot.entities' in sql:
            x=self.entities.get(params[0]);self.last=[(x,)] if x else []
        elif 'INSERT INTO rajan_pilot.counters' in sql:
            eid,category=params;key=(eid,category)
            self.counters[key]=self.counters.get(key,0)+1
            self.last=[(self.counters[key],)]
        elif 'INSERT INTO rajan_pilot.registrations' in sql:
            self.ids['reg']+=1;n=self.ids['reg']
            eid,tmp,name,phone,dob,notes=params
            self.registrations[n]=[n,eid,tmp,name,phone,dob,notes,None]
            self.last=[(n,)]
        elif 'SELECT id,name,phone,dob,notes,patient_id FROM rajan_pilot.registrations' in sql:
            eid,rid=params
            r=self.registrations.get(rid)
            self.last=[(r[0],r[3],r[4],r[5],r[6],r[7])] if r and r[1]==eid else []
        elif 'INSERT INTO rajan_pilot.patients' in sql:
            self.ids['patient']+=1;n=self.ids['patient']
            eid,uhid,name,phone,dob,notes=params
            self.patients[n]=(n,eid,uhid,name,phone,dob,notes)
            self.last=[(n,)]
        elif 'UPDATE rajan_pilot.registrations SET patient_id' in sql:
            pid,eid,rid=params
            assert self.registrations[rid][1]==eid
            self.registrations[rid][7]=pid
        elif 'SELECT id FROM rajan_pilot.patients' in sql:
            eid,pid=params
            p=self.patients.get(pid)
            self.last=[(pid,)] if p and p[1]==eid else []
        elif 'SELECT id,uhid,name,phone FROM rajan_pilot.patients' in sql:
            if len(params)==2:
                eid,pid=params
                p=self.patients.get(pid)
                self.last=[(p[0],p[2],p[3],p[4])] if p and p[1]==eid else []
            else:
                eid=params[0];q=params[1][1:-1].lower()
                self.last=[(p[0],p[2],p[3],p[4]) for p in self.patients.values()
                           if p[1]==eid and any(q in str(s).lower() for s in (p[2],p[3],p[4]))]
        else:raise AssertionError('Unexpected SQL: '+sql)
    def fetchall(self):return self.last
    def fetchone(self):return self.last[0] if self.last else None

cur=PilotCursor()
@contextmanager
def fake_scope(eid,read_only=False):
    assert eid in (1,2) and type(read_only) is bool
    yield cur

r=create_registration(1,'CL','Synthetic A',scope=fake_scope)
assert r['temp_id']=='CL-TMP-000001'
p=check_in(1,'CL',r['id'],scope=fake_scope)
assert p['patient']['uhid']=='CL-UHID-000001' and not p['reused']
p2=check_in(1,'CL',r['id'],scope=fake_scope)
assert p2['patient']==p['patient'] and p2['reused']
assert cur.counters[(1,'UHID')]==1
assert len(list_patients(1,'CL','Synthetic',scope=fake_scope)['patients'])==1
assert not list_patients(2,'TR','Synthetic',scope=fake_scope)['patients']
r2=create_registration(2,'TR','Synthetic B',scope=fake_scope)
assert r2['temp_id']=='TR-TMP-000001'
try:check_in(2,'TR',r2['id'],existing_patient_id=p['patient']['id'],scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Allowed cross-entity patient linkage')
try:check_in(2,'TR',r['id'],scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Allowed foreign registration')
assert check_in(2,'TR',r2['id'],scope=fake_scope)['patient']['uhid']=='TR-UHID-000001'
for bad in ({'invalid_rls':True},{'excess_policy':True}):
    f=PilotCursor()
    for k,v in bad.items():setattr(f,k,v)
    try:check_pilot_security(f)
    except PilotError:pass
    else:raise AssertionError('Missing RLS protection detected')
try:create_registration(1,'FAKE','Synthetic',scope=fake_scope)
except PilotError:pass
else:raise AssertionError('Allowed mismatched entity code')

with tempfile.TemporaryDirectory() as td:
 os.environ['DENTAL_DB']=str(Path(td)/'synthetic.sqlite')
 import app
 app.DB=Path(os.environ['DENTAL_DB'])
 app.init();app.seed_admin('v17admin','LongSyntheticPassword17!')
 client=TestClient(app.app)
 logged=client.post('/api/login',json={'username':'v17admin','password':'LongSyntheticPassword17!'})
 assert logged.status_code==200,logged.text
 headers={'Authorization':'Bearer '+logged.json()['token']}
 for method,path in [('post','/api/entities/1/pg-pilot/registrations'),('post','/api/entities/1/pg-pilot/check-in'),('get','/api/entities/1/pg-pilot/patients')]:
    kwargs={'json':{'name':'Synthetic'}} if method=='post' and 'registrations' in path else {'json':{'registration_id':1}} if method=='post' else {}
    response=getattr(client,method)(path,headers=headers,**kwargs)
    assert response.status_code==503,(path,response.status_code,response.text)
 assert client.get('/api/entities/1/pg-pilot/patients').status_code==401
 assert client.get('/api/entities/999/pg-pilot/patients',headers=headers).status_code in (403,404)
print('PASS v1.7: synthetic PostgreSQL pilot queries, isolation, UHID idempotency, fail-closed endpoints')
