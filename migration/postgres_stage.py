"""PostgreSQL 16+ STAGING import of a verified SQLite export.

NOT a runtime migration or production schema. Requires psycopg 3 and a disposable
PostgreSQL database. Run only with synthetic data unless approved secure controls exist.

Commands:
  python postgres_stage.py plan SQLITE_SNAPSHOT EXPORT_DIR OUTPUT_SQL
  RAJAN_STAGE_DSN=... python postgres_stage.py apply SQLITE_SNAPSHOT EXPORT_DIR

All writes happen in a single PostgreSQL transaction. Existing target schemas
are refused. Compares full table counts, entity counts and financial totals.
"""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

from export_sqlite import verify

SCHEMA = 'rajan_stage'
IDENT = re.compile(r'^[A-Za-z_][A-Za-z_0-9]*$')
MONEY = {'invoices':'total_paise','receipts':'amount_paise',
         'credit_notes':'amount_paise','recorded_refunds':'amount_paise',
         'allocations':'amount_paise'}

def quoted(value):
    if not IDENT.fullmatch(value): raise ValueError('Unsafe schema identifier')
    return '"'+value+'"'

def read_catalog(sqlite_path):
    """Inspect exact SQLite snapshot used to create the hashed export."""
    path = Path(sqlite_path).resolve()
    if not path.is_file(): raise ValueError('SQLite source snapshot not found')
    with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True) as c:
        names = [x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        catalog = {}
        for table in names:
            quoted(table)
            cols = [dict(zip(('cid','name','type','notnull','dflt_value','pk'),r)) for r in c.execute('PRAGMA table_info('+quoted(table)+')')]
            indexes=[]
            for r in c.execute('PRAGMA index_list('+quoted(table)+')'):
                # PRAGMA index_list: seq, name, unique, origin, partial
                if not r[2] or r[3]=='pk' or r[4]: continue
                column_rows=list(c.execute('PRAGMA index_info('+quoted(r[1])+')'))
                if any(cr[2] is None for cr in column_rows): continue
                indexes.append([cr[2] for cr in column_rows])
            fks={}
            for fk in c.execute('PRAGMA foreign_key_list('+quoted(table)+')'):
                fks.setdefault(fk[0],[]).append((fk[1],fk[2],fk[3],fk[4]))
            catalog[table] = {'columns':cols,'uniques':indexes,
                'foreign_keys':[[[x[2] for x in sorted(group)], group[0][1], [x[3] for x in sorted(group)]] for group in fks.values()]}
        return catalog

def sql_type(sqlite_type):
    typ=sqlite_type.upper()
    if 'INT' in typ: return 'BIGINT'
    if any(x in typ for x in ('CHAR','CLOB','TEXT','DATE','TIME')): return 'TEXT'
    if any(x in typ for x in ('REAL','FLOA','DOUB')):return 'DOUBLE PRECISION'
    if 'BLOB' in typ:return 'BYTEA'
    if any(x in typ for x in ('NUM','DEC')):return 'NUMERIC'
    return 'TEXT'

def get_plan(sqlite_path, export_dir):
    verified=verify(export_dir)
    manifest=json.loads((Path(export_dir)/'manifest.json').read_text(encoding='utf-8'))
    from export_sqlite import sha
    if sha(Path(sqlite_path))!=manifest['sqlite_sha256']:
        raise ValueError('SQLite snapshot differs from verified exported source')
    catalog=read_catalog(sqlite_path)
    if set(catalog)!=set(manifest['tables']):raise ValueError('Catalog tables do not match export')
    for table, data in catalog.items():
        if [c['name'] for c in data['columns']]!=manifest['tables'][table]['columns']:
            raise ValueError('Catalog columns do not match exported source: '+table)
    return catalog,manifest,verified

def build_ddl(catalog):
    statements=['CREATE SCHEMA '+quoted(SCHEMA)]
    pending=[]
    for table,data in catalog.items():
        columns=[]
        for c in data['columns']:
            col=quoted(c['name'])+' '+sql_type(c['type'])
            if c['notnull'] or c['pk']: col+=' NOT NULL'
            columns.append(col)
        primary=[c['name'] for c in sorted(data['columns'],key=lambda x:x['pk']) if c['pk']]
        if primary:columns.append('PRIMARY KEY ('+', '.join(map(quoted,primary))+')')
        for unique in data['uniques']:
            if unique!=primary: columns.append('UNIQUE ('+', '.join(map(quoted,unique))+')')
        statements.append('CREATE TABLE '+quoted(SCHEMA)+'.'+quoted(table)+' (\n  '+',\n  '.join(columns)+'\n)')
        for from_cols,ref,to_cols in data['foreign_keys']:
            pending.append('ALTER TABLE '+quoted(SCHEMA)+'.'+quoted(table)+
                ' ADD FOREIGN KEY ('+', '.join(map(quoted,from_cols))+') REFERENCES '+
                quoted(SCHEMA)+'.'+quoted(ref)+' ('+', '.join(map(quoted,to_cols))+')')
    return statements,pending

def output_plan(sqlite_path,export_dir,out):
    catalog,manifest,verified=get_plan(sqlite_path,export_dir)
    tables,foreign_keys=build_ddl(catalog)
    p=Path(out)
    if p.exists():raise ValueError('Refusing to overwrite SQL plan')
    # DDL only: constraints added after importer loads all rows
    p.write_text('-- STAGING ONLY. No RLS, triggers, defaults, app compatibility, or production authorization.\n'
                 '-- Apply with postgres_stage.py apply, not manually, to verify all rows.\n'+
                 ';\n\n'.join(tables+foreign_keys)+';\n',encoding='utf-8')
    return {'tables':len(catalog),'rows':verified['verified_rows'],'staging_sql':str(p), 'foreign_keys':len(foreign_keys)}

def check_parity(cur,manifest):
    errors=[]
    for table,expected in manifest['tables'].items():
        tbl=quoted(SCHEMA)+'.'+quoted(table)
        cur.execute('SELECT COUNT(*) FROM '+tbl)
        actual=cur.fetchone()[0]
        if actual!=expected['rows']:errors.append((table,'rows',actual,expected['rows']))
        if 'per_entity' in expected:
            cur.execute('SELECT entity_id,COUNT(*) FROM '+tbl+' GROUP BY entity_id')
            actual={str(e):v for e,v in cur.fetchall()}
            if actual!=expected['per_entity']:errors.append((table,'per_entity',actual,expected['per_entity']))
        if 'money_per_entity' in expected:
            col=MONEY[table]
            cur.execute('SELECT entity_id,COALESCE(SUM('+quoted(col)+'),0) FROM '+tbl+' GROUP BY entity_id')
            actual={str(e):int(v) for e,v in cur.fetchall()}
            if actual!=expected['money_per_entity']:errors.append((table,'amounts',actual,expected['money_per_entity']))
    if errors:raise ValueError('PostgreSQL parity mismatch (first five): '+repr(errors[:5]))
    return {'tables_verified':len(manifest['tables']), 'rows_verified':sum(v['rows'] for v in manifest['tables'].values())}

def apply(sqlite_path,export_dir,dsn=None):
    catalog,manifest,_=get_plan(sqlite_path,export_dir)
    dsn=dsn or os.environ.get('RAJAN_STAGE_DSN')
    if not dsn: raise ValueError('RAJAN_STAGE_DSN is required')
    try:import psycopg
    except ImportError as exc:raise RuntimeError('Install psycopg[binary]>=3.2,<4 for PostgreSQL staging import') from exc
    create_tables,fks=build_ddl(catalog)
    # Dedicated staging only. Target role must not be application or superuser role.
    with psycopg.connect(dsn,autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s",(SCHEMA,))
            if cur.fetchone():raise ValueError('Refusing existing staging schema')
            for stmt in create_tables:cur.execute(stmt)
            for table,columns in catalog.items():
                names=[c['name'] for c in columns['columns']]
                insert='INSERT INTO '+quoted(SCHEMA)+'.'+quoted(table)+' ('+', '.join(map(quoted,names))+') VALUES ('+', '.join(['%s']*len(names))+')'
                batch=[]
                with (Path(export_dir)/(table+'.jsonl')).open(encoding='utf-8') as f:
                    for line in f:
                        data=json.loads(line)
                        batch.append(tuple(data[name] for name in names))
                        if len(batch)>=250:
                            cur.executemany(insert,batch);batch=[]
                if batch:cur.executemany(insert,batch)
            for stmt in fks:cur.execute(stmt)
            results=check_parity(cur,manifest)
            # After verifying totals, also enforce the same semantic relationship
            # checks applied to the original SQLite snapshot. This catches
            # cross-patient clinical/financial links not covered by basic FKs.
            from audit_integrity import check_cursor_semantics as check_semantics
            cur.execute('SET LOCAL search_path TO '+quoted(SCHEMA)+', pg_catalog')
            results['semantic_checks']=check_semantics(cur)
            # Close off accidental use by PUBLIC. Still not suitable for app traffic.
            cur.execute('REVOKE ALL ON SCHEMA '+quoted(SCHEMA)+' FROM PUBLIC')
            cur.execute('REVOKE ALL ON ALL TABLES IN SCHEMA '+quoted(SCHEMA)+' FROM PUBLIC')
        conn.commit()
    return {'staging_schema':SCHEMA,**results,'status':'Staging import only; runtime cutover NOT performed'}

if __name__=='__main__':
    try:
        if len(sys.argv)==5 and sys.argv[1]=='plan':
            result=output_plan(sys.argv[2],sys.argv[3],sys.argv[4])
        elif len(sys.argv)==4 and sys.argv[1]=='apply':
            result=apply(sys.argv[2],sys.argv[3])
        else:raise ValueError('Usage: plan SQLITE EXPORT_DIR OUTPUT.sql | apply SQLITE EXPORT_DIR')
        print(json.dumps(result,indent=2))
    except (ValueError,RuntimeError,OSError,sqlite3.Error) as exc:
        print('FAILED:',str(exc),file=sys.stderr);sys.exit(1)
