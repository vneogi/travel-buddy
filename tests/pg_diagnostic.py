"""Standalone diagnostic: verify JWT GUC and RPC on ephemeral Postgres."""

import json
import os
import sys

dsn = os.environ.get("TB_SPEC44_PG_DSN")
if not dsn:
    print("TB_SPEC44_PG_DSN not set, skipping diagnostic")
    sys.exit(0)

import psycopg2
import psycopg2.extras

conn = psycopg2.connect(dsn)
conn.autocommit = False
psycopg2.extras.register_default_jsonb(conn)
cur = conn.cursor()

# Set both JWT GUCs
cur.execute(
    "SELECT set_config('request.jwt.claims', %s, true)",
    ('{"role":"service_role"}',),
)
print("jwt.claims SET OK")

try:
    cur.execute("SELECT set_config('request.jwt.claim.role', 'service_role', true)")
    print("jwt.claim.role SET OK (4-part GUC accepted)")
except Exception as e:
    print(f"jwt.claim.role FAILED: {e}")
    conn.rollback()
    cur = conn.cursor()
    cur.execute(
        "SELECT set_config('request.jwt.claims', %s, true)",
        ('{"role":"service_role"}',),
    )
    print("jwt.claims RE-SET after rollback")

# Read back
cur.execute("SELECT current_setting('request.jwt.claim.role', true)")
print(f"jwt.claim.role = {cur.fetchone()[0]!r}")
cur.execute("SELECT current_setting('request.jwt.claims', true)")
print(f"jwt.claims = {cur.fetchone()[0]!r}")

# Test the COALESCE logic
cur.execute("""
    SELECT COALESCE(
        NULLIF(current_setting('request.jwt.claim.role', true), ''),
        NULLIF(current_setting('request.jwt.claims', true), '')::JSONB->>'role'
    )
""")
resolved = cur.fetchone()[0]
print(f"resolved role = {resolved!r}")

if resolved != "service_role":
    print("ERROR: role did not resolve to service_role!")
    sys.exit(1)

# Try a minimal RPC call
cur.execute("""
    SELECT commit_trip_command(
        '00000000-0000-0000-0000-000000000001'::UUID,
        '00000000-0000-0000-0000-000000000002'::UUID,
        'diag-test', 'create_trip',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        NULL,
        '{"trip_id":"00000000-0000-0000-0000-000000000001","user_id":"00000000-0000-0000-0000-000000000002","version":1}'::JSONB,
        '[]'::JSONB, '[]'::JSONB,
        NULL, NULL, FALSE
    )
""")
result = cur.fetchone()[0]
print(f"RPC result type: {type(result).__name__}")
print(f"RPC result: {json.dumps(result, indent=2, default=str)[:500]}")

if isinstance(result, dict):
    print(f"status = {result.get('status')}")
else:
    print(f"WARNING: result is {type(result).__name__}, not dict!")
    print(f"Value: {result!r}")

conn.commit()
conn.close()
print("Diagnostic OK")
