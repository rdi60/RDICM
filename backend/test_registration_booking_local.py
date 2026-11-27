"""Synthetic checks for atomic registration + optional appointment booking."""
import os, sys, tempfile
from pathlib import Path
from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory() as temp:
    os.environ['DENTAL_DB']=str(Path(temp)/'synthetic.sqlite')
    os.environ['DENTAL_DOCUMENT_ROOT']=str(Path(temp)/'docs')
    sys.path.insert(0,str(Path(__file__).parent))
    import app
    app.seed_admin('admin','SyntheticBookPassword123!')
    with TestClient(app.app) as client:
        login=client.post('/api/login',json={'username':'admin','password':'SyntheticBookPassword123!'})
        assert login.status_code==200,login.text
        auth={'Authorization':'Bearer '+login.json()['token']}
        def req(method,path,data=None):return client.request(method,'/api'+path,headers=auth,json=data)
        entities=req('GET','/entities').json()
        eid=entities[0]['id'];other=entities[1]['id']
        doc=req('POST',f'/entities/{eid}/doctors',{'name':'Dr. Synthetic Appointment'})
        assert doc.status_code==200,doc.text
        did=doc.json()['id']
        # Friday 27 November 2026, 9:00AM–1:00PM IST
        schedule=req('POST',f'/entities/{eid}/doctor-slots/batch',{'doctor_id':did,'recurrence':'weekly','weekdays':[4],'windows':[{'start_time':'09:00','end_time':'13:00'}]})
        assert schedule.status_code==200,schedule.text
        def payload(name,phone,st='2026-11-27T09:15:00+05:30',en='2026-11-27T09:45:00+05:30',doctor=None,ack=False):
            return {'registration':{'name':name,'phone':phone,'email':name.lower().replace(' ','')+'@example.test','duplicate_acknowledged':ack},'appointment':{'doctor_id':doctor or did,'start_time':st,'end_time':en,'reason':'Initial consultation'}}
        path=f'/entities/{eid}/registrations/book-appointment'
        first=req('POST',path,payload('Patient One','9876543001'))
        assert first.status_code==200,first.text
        regid=first.json()['registration']['id'];aid=first.json()['appointment']['id']
        linked=next(x for x in req('GET',f'/entities/{eid}/appointments').json() if x['id']==aid)
        assert linked['registration_id']==regid and linked['patient_uhid'].endswith('TMP-000001')
        # An overlapping appointment must not create an orphan registration.
        conflicting=req('POST',path,payload('Patient Two','9876543002'))
        assert conflicting.status_code==409,conflicting.text
        pending=req('GET',f'/entities/{eid}/registrations').json()
        assert len(pending)==1 and pending[0]['name']=='Patient One'
        # Invalid doctor must also roll back.
        invalid=req('POST',path,payload('Patient Three','9876543003',doctor=9999999))
        assert invalid.status_code in (400,404),invalid.text
        assert len(req('GET',f'/entities/{eid}/registrations').json())==1
        # Booking with an identifier submitted by caller is forbidden.
        forged=payload('Patient Forged','9876543004');forged['appointment']['patient_id']=88
        assert req('POST',path,forged).status_code==400
        assert len(req('GET',f'/entities/{eid}/registrations').json())==1
        # Doctor block makes appointment unavailable.
        timeoff=req('POST',f'/entities/{eid}/doctor-time-off',{'doctor_id':did,'start_time':'2026-11-27T05:30:00+00:00','end_time':'2026-11-27T06:30:00+00:00','reason':'Conference'})
        assert timeoff.status_code==200,timeoff.text
        blocked=req('POST',path,payload('Patient Blocked','9876543005','2026-11-27T11:15:00+05:30','2026-11-27T11:45:00+05:30'))
        assert blocked.status_code==409,blocked.text
        assert len(req('GET',f'/entities/{eid}/registrations').json())==1
        # Duplicate phone must be checked before creating any appointment.
        duplicate=req('POST',path,payload('Patient Duplicate','9876543001','2026-11-27T12:00:00+05:30','2026-11-27T12:30:00+05:30'))
        assert duplicate.status_code==409 and duplicate.json()['detail']['code']=='POSSIBLE_DUPLICATE',duplicate.text
        assert len(req('GET',f'/entities/{eid}/registrations').json())==1
        # Entity isolation: no cross-entity doctor bookings.
        foreign=req('POST',f'/entities/{other}/registrations/book-appointment',payload('Other Entity Patient','9876543009'))
        assert foreign.status_code in (400,404),foreign.text
        assert not req('GET',f'/entities/{other}/registrations').json()
        # Existing check-in creates permanent UHID without deleting appointment.
        checkin=req('POST',f'/entities/{eid}/check-in',{'registration_id':regid})
        assert checkin.status_code==200,checkin.text
        original=next(x for x in req('GET',f'/entities/{eid}/appointments').json() if x['id']==aid)
        assert original['id']==aid and original['patient_uhid']==checkin.json()['patient']['uhid']
        # Registration-only route is unchanged.
        simple=req('POST',f'/entities/{eid}/registrations',{'name':'Registration Only','phone':'9876543006'})
        assert simple.status_code==200,simple.text
        print('PASS: combined registration/bookings atomic, conflicts and duplicates rollback, entity isolation, UHID preservation')

