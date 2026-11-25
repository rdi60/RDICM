"""Synthetic checks for v0.4 admin templates, clinical phrases and staff assignments."""
import os
import sys
import csv
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from fastapi.testclient import TestClient
from openpyxl import load_workbook

with tempfile.TemporaryDirectory() as tmp:
    os.environ['DENTAL_DB']=str(Path(tmp)/'test.sqlite')
    os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(tmp)/'docs')
    sys.path.insert(0,str(Path(__file__).parent))
    import app
    app.seed_admin('admin','SyntheticValidationPassword123!')
    with TestClient(app.app) as client:
        response=client.post('/api/login',json={'username':'admin','password':'SyntheticValidationPassword123!'})
        assert response.status_code==200,response.text
        token=response.json()['token']
        auth={'Authorization':'Bearer '+token}
        ids=[e['id'] for e in client.get('/api/entities',headers=auth).json()]
        a,b=ids[:2]

        for kind in ['procedures','categories','staff_doctors','roles_groups','patients','opening_balances','clinical_templates']:
            for fmt in ('csv','xlsx'):
                r=client.get(f'/api/entities/{a}/v4/bulk/template/{kind}?format={fmt}',headers=auth)
                assert r.status_code==200,(kind,fmt,r.text)
                if fmt=='csv':
                    values=list(csv.reader(StringIO(r.content.decode('utf-8-sig'))))
                    assert len(values)>1
                    if kind=='procedures':
                        assert values[0][:2]==['Procedure Name','Treatment Category']
                else:
                    wb=load_workbook(BytesIO(r.content),read_only=True)
                    assert 'Import Data' in wb.sheetnames and 'Instructions' in wb.sheetnames
                    if kind=='procedures':
                        assert [cell.value for cell in next(wb['Import Data'].rows)][:2]==['Procedure Name','Treatment Category']

        phrase={'shortcut':'adv1','phrase':'Advised review after one week.','active':True}
        r=client.post(f'/api/entities/{a}/v4/clinical-text-templates',headers=auth,json=phrase)
        assert r.status_code==200,r.text
        phrase_id=r.json()['id']
        aphrases=client.get(f'/api/entities/{a}/v4/clinical-text-templates',headers=auth).json()
        bphrases=client.get(f'/api/entities/{b}/v4/clinical-text-templates',headers=auth).json()
        assert any(p['id']==phrase_id for p in aphrases)
        assert not bphrases
        duplicate=client.post(f'/api/entities/{a}/v4/clinical-text-templates',headers=auth,json=phrase)
        assert duplicate.status_code==409,duplicate.text
        updated=client.put(f'/api/entities/{a}/v4/clinical-text-templates/{phrase_id}',headers=auth,json={**phrase,'phrase':'Advised review after two weeks.'})
        assert updated.status_code==200,updated.text

        # Existing access must be readable before an admin changes roles/groups.
        staff=client.post(f'/api/entities/{a}/staff-accounts',headers=auth,json={'username':'synthetic_staff','password':'SyntheticStaff123!','role':'viewer'})
        assert staff.status_code==200,staff.text
        uid=staff.json()['id']
        record=client.get(f'/api/v2/superadmin/users/{uid}/assignments',headers=auth)
        assert record.status_code==200,record.text
        assert 'viewer' in record.json()['entity_roles'][str(a)]
        print('PASS v0.4: Excel/CSV template download, clinical text phrases, staff access readback')
