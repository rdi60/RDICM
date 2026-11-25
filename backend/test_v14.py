"""Offline PostgreSQL staging plan + export source integrity checks (synthetic only)."""
import os,sys,tempfile,json,sqlite3
from pathlib import Path
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    os.environ['DENTAL_DB']=str(root/'fixture.sqlite')
    sys.path.insert(0,str(Path(__file__).parent))
    import app
    app.init()
    app.seed_admin('syntheticv14','LongSyntheticAdminPassword!')
    sys.path.insert(0,str(Path(__file__).parent.parent/'migration'))
    from export_sqlite import export
    from postgres_stage import get_plan,build_ddl,output_plan
    db=Path(os.environ['DENTAL_DB']);exp=root/'export'
    with app.db(True) as c:
        eid=c.execute("SELECT id FROM entities WHERE code='CL'").fetchone()[0]
        p=c.execute('INSERT INTO patients(entity_id,uhid,name,created_at) VALUES(?,?,?,?)',
          (eid,'CL-TEST-14','Synthetic Patient',app.utc())).lastrowid
        c.execute('INSERT INTO invoices(entity_id,invoice_no,patient_id,total_paise,description,created_at) VALUES(?,?,?,?,?,?)',
          (eid,'CL-TEST-INV14',p,10500,'Synthetic invoice',app.utc()))
    export(db,exp)
    catalog,manifest,check=get_plan(db,exp)
    assert check['verified_tables']>=28
    assert manifest['tables']['invoices']['money_per_entity'][str(eid)]==10500
    create,foreign_keys=build_ddl(catalog)
    assert len(create)==len(catalog)+1
    assert any('FOREIGN KEY ("entity_id", "patient_id")' in x for x in foreign_keys), 'Composite FK missing'
    sql=root/'staging.sql'
    info=output_plan(db,exp,sql)
    assert info['foreign_keys']==len(foreign_keys)
    s=sql.read_text()
    assert 'CREATE SCHEMA "rajan_stage"' in s
    assert '"invoices"' in s and 'BIGINT' in s
    assert 'REFERENCES "rajan_stage"."patients"' in s
    assert 'STAGING ONLY' in s
    # Tampered export must be rejected before any DB connection.
    with (exp/'invoices.jsonl').open('a') as f:f.write('{}\n')
    try:get_plan(db,exp)
    except ValueError:pass
    else:raise AssertionError('Tampered export was accepted')
    print('PASS v1.4: staging DDL planning, FK transcription, verified export and tamper guard')
