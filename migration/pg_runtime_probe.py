"""Read-only PostgreSQL runtime canary, not a completed database cutover.

Uses authenticated entity membership from the existing backend. The runtime schema
must be independently provisioned and RLS-reviewed; the staging import schema is
explicitly forbidden. Returns only aggregate counts, never identifiable records.
"""
import os
import re
from pg_scope import scoped_cursor

IDENT = re.compile(r'^[a-z][a-z0-9_]*$')
REQUIRED = ('patients', 'appointments', 'visits', 'invoices', 'receipts')


def checked_schema(schema):
    if not isinstance(schema, str) or not IDENT.fullmatch(schema):
        raise ValueError('Invalid PostgreSQL runtime schema name')
    if schema in ('public', 'rajan_stage', 'information_schema', 'pg_catalog') or schema.startswith('pg_'):
        raise ValueError('Runtime schema must be dedicated, not staging/public/system')
    return schema


def check_rls(cur, schema):
    """Fail closed if any required table is missing, weakly protected or has extra policies."""
    cur.execute('''SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname=%s AND c.relkind IN ('r','p') AND c.relname = ANY(%s)''',
          (schema, list(REQUIRED)))
    records = {name:(bool(enabled),bool(forced)) for name,enabled,forced in cur.fetchall()}
    if set(records) != set(REQUIRED) or not all(a and b for a,b in records.values()):
        raise ValueError('PostgreSQL runtime tables require ENABLE and FORCE RLS')
    cur.execute('''SELECT tablename,policyname,permissive,roles,cmd,qual,with_check
          FROM pg_policies WHERE schemaname=%s AND tablename = ANY(%s)''',
          (schema, list(REQUIRED)))
    policies = cur.fetchall()
    by_table = {}
    for row in policies:
        by_table.setdefault(row[0],[]).append(row)
    for table in REQUIRED:
        entries = by_table.get(table, [])
        if len(entries) != 1:
            raise ValueError('Expected exactly one reviewed policy for each required runtime table')
        _,name,mode,roles,cmd,qual,check = entries[0]
        # Text-based policy verification is only a safety preflight, not a proof of RLS.
        # Require an exact installed policy definition marker and reject policy changes.
        if (name != 'scoped_entity' or mode != 'PERMISSIVE' or cmd != 'ALL'
                or roles != ['public'] or not isinstance(qual,str) or not isinstance(check,str)
                or 'app.entity_id' not in qual or 'app.entity_id' not in check
                or 'entity_id' not in qual or 'entity_id' not in check):
            raise ValueError('Unreviewed PostgreSQL runtime RLS policy')
    return True


def count_only(entity_id, schema=None, dsn=None, cursor_factory=scoped_cursor):
    """Read-only aggregate query; caller MUST authenticate + authorize membership."""
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError('Invalid authorized entity ID')
    schema = checked_schema(schema or os.environ.get('RAJAN_RUNTIME_SCHEMA', 'rajan_runtime'))
    with cursor_factory(entity_id, dsn=dsn, read_only=True) as cur:
        check_rls(cur, schema)
        out={}
        for table in REQUIRED:
            # Identifier is a trusted static whitelist; count also filters by entity.
            cur.execute('SELECT COUNT(*) FROM "'+schema+'"."'+table+'" WHERE entity_id=%s',(entity_id,))
            out[table] = int(cur.fetchone()[0])
        return {'entity_id':entity_id, 'schema':schema,'counts':out,
                'mode':'read_only_canary', 'cutover_completed':False}
