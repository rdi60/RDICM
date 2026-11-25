"""Synthetic migration preflight regression, including financially inconsistent FK-valid data."""
import os,sys,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as d:
    os.environ['DENTAL_DB']=str(Path(d)/'fixture.db')
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import app
    app.init();app.seed_admin('syntheticv13','LongSyntheticAdminPassword!')
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'migration'))
    from audit_integrity import audit
    dbfile=Path(os.environ['DENTAL_DB'])
    result=audit(dbfile)
    assert result['passed'],result
    with app.db(True) as c:
        e1=c.execute("SELECT id FROM entities WHERE code='CL'").fetchone()[0]
        e2=c.execute("SELECT id FROM entities WHERE code='TR'").fetchone()[0]
        # Create two patients, one invoice and one receipt in a single entity.
        p1=c.execute('INSERT INTO patients(entity_id,uhid,name,created_at) VALUES(?,?,?,?)',(e1,'CL-TEST1','Synthetic A',app.utc())).lastrowid
        p2=c.execute('INSERT INTO patients(entity_id,uhid,name,created_at) VALUES(?,?,?,?)',(e1,'CL-TEST2','Synthetic B',app.utc())).lastrowid
        i=c.execute('INSERT INTO invoices(entity_id,invoice_no,patient_id,total_paise,description,created_at) VALUES(?,?,?,?,?,?)',(e1,'CL-I-TEST',p1,50000,'Synthetic',app.utc())).lastrowid
        r=c.execute('INSERT INTO receipts(entity_id,receipt_no,patient_id,amount_paise,method,created_at) VALUES(?,?,?,?,?,?)',(e1,'CL-R-TEST',p2,20000,'cash',app.utc())).lastrowid
        try:
            c.execute('INSERT INTO allocations(entity_id,receipt_id,invoice_id,amount_paise) VALUES(?,?,?,?)',(e1,r,i,25000))
            raise AssertionError('Database trigger must reject mismatched patient')
        except app.sqlite3.IntegrityError:pass
        # Simulate a legacy corrupted database created before the new triggers existed.
        c.execute('DROP TRIGGER allocations_validate_insert')
        a=c.execute('INSERT INTO allocations(entity_id,receipt_id,invoice_id,amount_paise) VALUES(?,?,?,?)',(e1,r,i,25000)).lastrowid
    result=audit(dbfile)
    assert not result['passed'],result
    assert result['checks']['receipt_invoice_patient_mismatch']==1,result
    assert result['checks']['receipt_overallocated']==1,result
    with app.db(True) as c:
        c.execute('DELETE FROM allocations WHERE id=?',(a,))
    app.init()  # Recreate missing trigger during a normal application initialization.
    assert audit(dbfile)['passed']
    print('PASS v1.3: allocation write guard and detection of legacy patient/payment mismatches')
