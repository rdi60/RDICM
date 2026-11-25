"""Read-only verification of a PostgreSQL STAGING import against its SQLite export.

This does NOT authorize production cutover, enable RLS, or switch the API to PG.
Usage:
 RAJAN_STAGE_DSN=... python migration/postgres_validate.py SQLITE_SNAPSHOT EXPORT_DIR

Requires psycopg 3 and a reachable private PostgreSQL server. Prints aggregate results
only, never rows, patient details or database credentials.
"""
import json
import os
import sys
from pathlib import Path

from audit_integrity import check_cursor_semantics as check_semantics
from postgres_stage import SCHEMA, check_parity, get_plan, quoted


def check_columns(cursor, catalog):
    """Reject missing/extra columns and tables in the staging schema."""
    cursor.execute('''SELECT table_name,column_name,ordinal_position
        FROM information_schema.columns WHERE table_schema=%s
        ORDER BY table_name,ordinal_position''', (SCHEMA,))
    actual = {}
    for table, col, _ in cursor.fetchall():
        actual.setdefault(table, []).append(col)
    expected = {name:[c['name'] for c in table['columns']] for name,table in catalog.items()}
    if actual != expected:
        raise ValueError('PostgreSQL staging schema differs from verified export catalog')
    return len(expected)


def verify_staging(sqlite_snapshot, export_dir, dsn=None):
    # Verify the entire source snapshot and all exported files BEFORE connecting.
    catalog, manifest, export_status = get_plan(sqlite_snapshot, export_dir)
    dsn = dsn or os.getenv('RAJAN_STAGE_DSN')
    if not dsn:
        raise ValueError('RAJAN_STAGE_DSN is required')
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Install psycopg[binary]>=3.2,<4 to verify PostgreSQL staging') from exc
    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            # No interpolation of user-supplied schema names.
            cursor.execute('SET LOCAL search_path TO '+quoted(SCHEMA)+', pg_catalog')
            schemas = check_columns(cursor, catalog)
            counts = check_parity(cursor, manifest)
            semantic_checks = check_semantics(cursor)
        # End the read-only transaction without writing.
        conn.rollback()
    return {'status':'PASS: STAGING parity and semantic checks (NOT a production cutover)',
            'tables':schemas,'rows':counts['rows_verified'],
            'semantic_checks':semantic_checks,'export_files':export_status['files'],
            'warning':'Does not verify RLS, source media, production constraints, app runtime, concurrency or backups'}


if __name__ == '__main__':
    try:
        if len(sys.argv)!=3:
            raise ValueError('Usage: postgres_validate.py SQLITE_SNAPSHOT EXPORT_DIR')
        print(json.dumps(verify_staging(sys.argv[1],sys.argv[2]),indent=2))
    except (ValueError,RuntimeError,OSError) as exc:
        print('STAGING VALIDATION FAILED:',str(exc),file=sys.stderr)
        sys.exit(2)
