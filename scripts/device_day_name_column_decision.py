"""Decide whether migration 0011 is safe to apply as written.

Reads a TSV of venues_rag columns (column_name\\tdata_type\\tudt_name),
usually produced by device_day_schema_from_openapi.py or psql.

Exits 0 with DECISION: safe, exits 2 when apply must stop.

An empty column set is NOT safe. That failure mode was observed on device
day when psql prompted for a password and wrote nothing useful to the TSV;
the old script treated empty as safe (R17).
"""

from __future__ import annotations

import sys
from pathlib import Path

# If these are absent, the dump is not a real venues_rag column list.
REQUIRED_CORE = frozenset({"venue_id", "name", "geo_region"})


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Usage: python scripts/device_day_name_column_decision.py <columns.tsv>")
        return 2
    path = Path(args[0])
    if not path.is_file():
        print("ERROR: missing file %s" % path)
        return 2

    raw = path.read_text(encoding="utf-8", errors="replace")
    if "Password for user" in raw or "FATAL:" in raw or "psql:" in raw:
        print("ERROR: column dump looks like a psql auth/error transcript, not a TSV.")
        print("Use: python scripts/device_day_schema_from_openapi.py <SNAP> --out <tsv>")
        return 2

    cols = set()
    for line in raw.splitlines():
        if not line or line.startswith("column_name") or line.startswith("("):
            continue
        name = line.split("\t")[0].strip()
        if not name or name.lower().startswith("password"):
            continue
        cols.add(name)

    print("venues_rag columns:", sorted(cols))
    print("column_count:", len(cols))
    print("has name_local:", "name_local" in cols)
    print("has names_local:", "names_local" in cols)
    print("has nearest_landmark_local:", "nearest_landmark_local" in cols)
    print("has landmarks_local:", "landmarks_local" in cols)

    if not cols:
        print("DECISION: REFUSE -- column dump is empty. Not evidence of a safe schema.")
        print("Do not apply 0011. Re-run the OpenAPI column dump (Step 3a).")
        return 2

    missing_core = sorted(REQUIRED_CORE - cols)
    if missing_core:
        print("DECISION: REFUSE -- dump is missing core venues_rag columns: %s" % missing_core)
        print("Do not apply 0011. The TSV is not a valid venues_rag column list.")
        return 2

    if "name_local" in cols and "names_local" not in cols:
        print("DECISION: write a backfill BEFORE 0011, or amend apply order.")
        print("DO NOT apply 0011 as-is: ADD COLUMN names_local would leave name_local unread.")
        return 2
    if "name_local" in cols and "names_local" in cols:
        print("DECISION: both exist -- inspect which is populated; do not blind-apply.")
        return 2
    print("DECISION: safe to apply 0011 as written for the names_local path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
