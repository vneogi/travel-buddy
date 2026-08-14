"""Export every row and the live schema from the hosted Supabase project.

Run this BEFORE applying any migration. The Dubai venues exist only in the
hosted database: they are in no file and no backup, and the live schema is
known to carry hand-made columns that no migration declares. A failed
migration without this snapshot is unrecoverable data loss.

Deliberately stdlib only. The virtualenv on the device is empty and the
package index is not reachable from every shell here, so a script that needs
supabase-py or httpx is a script that cannot be run when it is needed. urllib
is enough for PostgREST.

Two things are captured:

1. Every row of every known table, as JSON, one file per table.
2. The live schema, taken from the PostgREST OpenAPI document, which lists
   the columns and types the database actually has right now. That is the
   input to the schema diff, and it needs no psql client.

The OpenAPI document does not carry CHECK constraints or column comments.
Those need a SQL query, which is in the run instructions rather than here.

Usage:

    export TB_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
    export TB_SUPABASE_KEY=YOUR_SERVICE_ROLE_KEY
    python3 scripts/export_live_snapshot.py

Reads the service_role key because it must bypass RLS to see every row. The
key is never printed, never written to the snapshot, and never logged.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Every table any migration declares, including the ones from 0012 to 0014
# which are committed but unapplied. Those are expected to be missing, and a
# missing table is reported rather than treated as a failure.
KNOWN_TABLES = [
    "user_tiers",
    "trip_states",
    "cached_responses",
    "venues_rag",
    "event_log",
    "source",
    "signal_type",
    "signal",
    "trip_party",
    "party_member",
    "venue_dish",
    "dish_glossary",
    "venue_external_id",
    "taxonomy_term",
    "trip_node",
    "trip_edge",
]

PAGE_SIZE = 1000
TIMEOUT_SECONDS = 60


def _request(url, key, accept="application/json"):
    req = urllib.request.Request(url)
    req.add_header("apikey", key)
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_table(base_url, key, table):
    """Return (rows, error). Pages until a short page comes back."""
    rows = []
    offset = 0
    while True:
        url = "%s/rest/v1/%s?select=*&limit=%d&offset=%d" % (
            base_url, table, PAGE_SIZE, offset
        )
        try:
            page = _request(url, key)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            return rows, "HTTP %s: %s" % (exc.code, body)
        except Exception as exc:
            return rows, "%s: %s" % (type(exc).__name__, exc)
        if not isinstance(page, list):
            return rows, "unexpected response shape: %s" % type(page).__name__
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows, None
        offset += PAGE_SIZE


def fetch_schema(base_url, key):
    """Live column definitions from the PostgREST OpenAPI document."""
    try:
        spec = _request(base_url + "/rest/v1/", key, accept="application/openapi+json")
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)
    definitions = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
    schema = {}
    for table, body in sorted(definitions.items()):
        properties = body.get("properties", {})
        schema[table] = {
            name: {
                "type": prop.get("type"),
                "format": prop.get("format"),
                "description": prop.get("description"),
            }
            for name, prop in sorted(properties.items())
        }
    return schema, None


def main():
    base_url = (os.environ.get("TB_SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("TB_SUPABASE_KEY") or ""
    if not base_url or not key:
        print("ERROR: set TB_SUPABASE_URL and TB_SUPABASE_KEY first.")
        print("They are in your .env; this script does not read that file.")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parent.parent / "data" / "live_snapshot" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Snapshot directory: %s" % out_dir)
    print("")

    schema, schema_error = fetch_schema(base_url, key)
    if schema_error:
        print("SCHEMA   FAILED   %s" % schema_error)
    else:
        (out_dir / "_live_schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )
        print("SCHEMA   captured  %d tables visible to PostgREST" % len(schema))
    print("")

    summary = []
    total_rows = 0
    for table in KNOWN_TABLES:
        rows, error = fetch_table(base_url, key, table)
        if error:
            status = "MISSING or UNREADABLE"
            detail = error
        else:
            status = "ok"
            detail = ""
            total_rows += len(rows)
            (out_dir / ("%s.json" % table)).write_text(
                json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=True),
                encoding="utf-8",
            )
        summary.append((table, len(rows), status, detail))
        print("%-20s %6d rows  %s %s" % (table, len(rows), status, detail))

    # A per-region breakdown of venues_rag is the number that actually matters
    # here, because the Dubai rows are the ones that exist nowhere else.
    venues_path = out_dir / "venues_rag.json"
    if venues_path.is_file():
        venues = json.loads(venues_path.read_text(encoding="utf-8"))
        regions = {}
        for venue in venues:
            regions[venue.get("geo_region")] = regions.get(venue.get("geo_region"), 0) + 1
        print("")
        print("venues_rag by geo_region:")
        for region, count in sorted(regions.items(), key=lambda kv: (-kv[1], str(kv[0]))):
            print("    %-24s %d" % (region, count))

    (out_dir / "_summary.json").write_text(
        json.dumps(
            {
                "captured_at": stamp,
                "total_rows": total_rows,
                "tables": [
                    {"table": t, "rows": n, "status": s, "detail": d}
                    for t, n, s, d in summary
                ],
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    print("")
    print("Total rows captured: %d" % total_rows)
    print("Snapshot written to: %s" % out_dir)
    print("")
    print("Do not apply any migration until this directory has the expected")
    print("venue counts in it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
