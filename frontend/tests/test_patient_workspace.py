"""Static guardrails: v2.4 patient-centric navigation and approved UI."""
from pathlib import Path
source = Path(__file__).resolve().parents[1].joinpath('src/main.jsx').read_text(encoding='utf-8')
css = Path(__file__).resolve().parents[1].joinpath('src/style.css').read_text(encoding='utf-8')
assert 'function PatientWorkspace(' in source
assert 'patientMenu.map' in source
assert "page==='Patient Dashboard'?<PatientWorkspace" in source
assert 'openPatient={openPatient}' in source
assert 'clickable-patient-row' in source
assert 'onKeyDown={e=>{if(e.key==="Enter")openPatient(p.id)}}' in source
assert 'function Appointments(' in source
assert "setPatientId(null);setPage('Dashboard')" in source
assert '.patient-workspace-body' in css
assert '.patient-menu-link.active' in css
assert 'NewAction' in source and 'function Drawer(' in source
assert "title=\"Today's doctor schedule\"" in source
assert 'entity_features' not in source  # frontend only talks to documented API
assert '/features' in source
assert 'function SecureThumbnail(' in source
assert "document-grid" in source and 'preview-canvas' in source
assert 'function ClinicalNotes(' in source and "saveNote('auto')" in source
assert 'onClose={close}' in source
assert "Select patient from current entity" not in source
print('PASS v2.4 frontend patient navigation, feature gating, drawer forms, document viewer and autosave source checks')
