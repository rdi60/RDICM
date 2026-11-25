"""Validated, deterministic, PRIVATE SQLite migration export for a separately reviewed PG importer.

This does NOT write to PostgreSQL or implement a PostgreSQL schema.
Exports every user table, verifies all SQLite foreign keys and stores a cryptographic
file manifest plus per-entity row counts and accounting aggregates.
Usage: python migration/export_sqlite.py export BACKUP.sqlite3 PRIVATE_OUTPUT_DIR
       python migration/export_sqlite.py verify PRIVATE_OUTPUT_DIR
Only run on synthetic/offline snapshots; output contains sensitive data.
"""
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def private_path(path):
    path = Path(path).expanduser().resolve()
    if path.exists():
        if not path.is_dir() or list(path.iterdir()):
            raise ValueError('Export destination must be a new or empty directory')
    else:
        path.mkdir(parents=True,mode=0o700)
    os.chmod(path,0o700)
    return path

def tables(c):
    return [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

def query_row(c, statement):
    return tuple(c.execute(statement).fetchone())

def snapshot(c):
    result = {}
    for tbl in tables(c):
        quoted = '"'+tbl.replace('"','""')+'"'
        columns = [r[1] for r in c.execute('PRAGMA table_info('+quoted+')')]
        result[tbl] = {'columns': columns, 'rows': c.execute('SELECT COUNT(*) FROM '+quoted).fetchone()[0]}
        if 'entity_id' in columns:
            result[tbl]['per_entity'] = {str(e): n for e,n in c.execute('SELECT entity_id,COUNT(*) FROM '+quoted+' GROUP BY entity_id ORDER BY entity_id')}
    for tbl,col in [('invoices','total_paise'),('receipts','amount_paise'),('credit_notes','amount_paise'),('recorded_refunds','amount_paise'),('allocations','amount_paise')]:
        if tbl in result:
            result[tbl]['money_per_entity'] = {str(e): n for e,n in c.execute(f'SELECT entity_id,COALESCE(SUM({col}),0) FROM "{tbl}" GROUP BY entity_id ORDER BY entity_id')}
    return result

def write_private(path, writer):
    with os.fdopen(os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w',newline='',encoding='utf-8') as f:
        writer(f)

def export(dbfile,destination):
    dbfile=Path(dbfile).resolve()
    if not dbfile.is_file(): raise ValueError('Database backup does not exist')
    destination = private_path(destination)
    # immutable read-only snapshot avoids accidentally modifying the source.
    c=sqlite3.connect(dbfile.as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('SQLite integrity check failed')
        violations=list(c.execute('PRAGMA foreign_key_check'))
        if violations: raise ValueError(f'SQLite foreign-key violations: {violations[:5]}')
        if 'entities' not in tables(c):raise ValueError('Not a recognized application database')
        meta=snapshot(c)
        hashes={}
        for tbl in tables(c):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',tbl):raise ValueError('Unsafe table name')
            quoted='"'+tbl+'"'
            # Explicit values are exported as UTF-8 JSONL to preserve null, types, and newlines.
            cols=meta[tbl]['columns']
            primary=[(r[5],r[1]) for r in c.execute('PRAGMA table_info('+quoted+')') if r[5]]
            order=','.join('"'+p[1]+'"' for p in sorted(primary)) if primary else 'rowid'
            out=destination/(tbl+'.jsonl')
            def write(f):
                for record in c.execute('SELECT * FROM '+quoted+' ORDER BY '+order):
                    f.write(json.dumps(dict(zip(cols,record)),ensure_ascii=False,separators=(',',':'))+'\n')
            write_private(out,write)
            hashes[out.name]=sha(out)
        manifest={'format':'RajanDentalSqliteExport','version':VERSION,'created_utc':datetime.now(timezone.utc).isoformat(),
                  'sqlite_sha256':sha(dbfile),'tables':meta,'files_sha256':hashes,
                  'warning':'CONTAINS PATIENT AND STAFF DATA. Keep encrypted, access controlled, and private. Not a PostgreSQL migration.'}
        write_private(destination/'manifest.json',lambda f:json.dump(manifest,f,indent=2,ensure_ascii=False,sort_keys=True))
        return manifest
    finally:c.close()

def verify(destination):
    destination=Path(destination).resolve()
    manifest=json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format')!='RajanDentalSqliteExport' or manifest.get('version')!=VERSION:raise ValueError('Unsupported export manifest')
    files=manifest['files_sha256']
    if set(p.name for p in destination.iterdir()) != set(files)|{'manifest.json'}:raise ValueError('Missing or unexpected export files')
    for name,expected in files.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*\.jsonl',name):raise ValueError('Invalid export file name')
        if sha(destination/name)!=expected:raise ValueError('Hash mismatch: '+name)
        table=name[:-6]
        expected_columns=set(manifest['tables'][table]['columns'])
        count=0;entity_counts={};money={}
        amount_col={'invoices':'total_paise','receipts':'amount_paise','credit_notes':'amount_paise','recorded_refunds':'amount_paise','allocations':'amount_paise'}.get(table)
        with (destination/name).open(encoding='utf-8') as f:
            for line in f:
                record=json.loads(line)
                if set(record)!=expected_columns:raise ValueError('Column mismatch: '+name)
                count+=1
                if 'entity_id' in record:
                    k=str(record['entity_id']);entity_counts[k]=entity_counts.get(k,0)+1
                    if amount_col:money[k]=money.get(k,0)+(record[amount_col] or 0)
        info=manifest['tables'][table]
        if count!=info['rows'] or ('per_entity' in info and entity_counts!=info['per_entity']):raise ValueError('Count mismatch: '+name)
        if 'money_per_entity' in info and money!=info['money_per_entity']:raise ValueError('Amount mismatch: '+name)
    return {'verified_tables':len(files),'verified_rows':sum(v['rows'] for v in manifest['tables'].values()),'files':len(files)}

if __name__=='__main__':
    try:
        if len(sys.argv)==4 and sys.argv[1]=='export':
            manifest=export(sys.argv[2],sys.argv[3]);print(json.dumps({'tables':len(manifest['tables']),'destination':sys.argv[3]},indent=2))
        elif len(sys.argv)==3 and sys.argv[1]=='verify':print(json.dumps(verify(sys.argv[2]),indent=2))
        else:raise ValueError('Usage: export DB BACKUP_DIR | verify BACKUP_DIR')
    except (ValueError,OSError,sqlite3.Error,KeyError) as exc:
        print('FAILED:',exc,file=sys.stderr);sys.exit(1)
