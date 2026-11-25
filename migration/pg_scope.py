"""PostgreSQL transaction helper for the FUTURE runtime port (not wired to API).

Must be used only after authenticating a user and checking membership to the entity
in a trusted server-side authorization layer. Setting a custom PostgreSQL GUC alone
is not authentication: RLS must also be reviewed/enabled, application SQL restricted,
and the DB role must not bypass RLS. Never accept entity IDs from an unauthenticated
request or pass raw untrusted SQL through this helper.
"""
import os
from contextlib import contextmanager

@contextmanager
def scoped_cursor(entity_id, dsn=None, read_only=False):
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError('A valid, authorized positive integer entity ID is required')
    if type(read_only) is not bool:
        raise ValueError('read_only must be a boolean')
    dsn=dsn or os.environ.get('RAJAN_PG_DSN')
    if not dsn:
        raise ValueError('RAJAN_PG_DSN is required')
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Install psycopg[binary]>=3.2,<4 for the PostgreSQL runtime') from exc
    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user')
            role=cur.fetchone()
            if not role or role[0] or role[1]:
                raise ValueError('Unsafe PostgreSQL application role: superuser/BYPASSRLS is forbidden')
            if read_only:
                cur.execute('SET TRANSACTION READ ONLY')
            # Transaction-local setting. NEVER use session-level SET in pooled connections.
            cur.execute("SELECT set_config('app.entity_id', %s, true)",(str(entity_id),))
            try:
                yield cur
            except BaseException:
                conn.rollback()
                raise
            else:
                if read_only:
                    conn.rollback()
                else:
                    conn.commit()
