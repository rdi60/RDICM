"""Offline safety checks for the optional destructive PostgreSQL live smoke runner.
These are NOT evidence of live PostgreSQL integration.
"""
import os
import sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'migration'))
import pg_live_smoke_v22 as smoke

original={key:os.environ.get(key) for key in ('RAJAN_PG_SMOKE_DISPOSABLE','RAJAN_PG_SMOKE_OWNER_DSN','RAJAN_PG_SMOKE_API_DSN')}
try:
    for key in original:os.environ.pop(key,None)
    try:smoke.require_environment()
    except RuntimeError as e:assert 'DISPOSABLE' in str(e)
    else:raise AssertionError('Smoke runner allowed operation without explicit opt-in')
    os.environ['RAJAN_PG_SMOKE_DISPOSABLE']='YES'
    try:smoke.require_environment()
    except RuntimeError as e:assert 'distinct' in str(e)
    else:raise AssertionError('Smoke runner allowed operation without separate DB roles')
finally:
    for key,value in original.items():
        if value is None:os.environ.pop(key,None)
        else:os.environ[key]=value

text=(root/'migration/pg_live_smoke_v22.py').read_text()
for marker in ['smoke','ExclusionViolation','ThreadPoolExecutor','BYPASSRLS','overpayment','RLS exposed','same_payment','psycopg.connect']:
    assert marker.lower() in text.lower(),marker
assert 'RAJAN_PG_SMOKE_DISPOSABLE' in text
print('PASS v2.2: offline smoke-runner gating and coverage checks; LIVE DB TEST NOT RUN')
