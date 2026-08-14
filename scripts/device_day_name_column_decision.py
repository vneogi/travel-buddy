"""Decide whether migration 0011 is safe to apply as written.

Reads a TSV of venues_rag columns (column_name\\tdata_type\\tudt_name),
usually produced by:

    psql ... -A -F \"`t\" -c \"SELECT column_name, data_type, udt_name ...\"

Exits 0 with DECISION: safe, exits 2 when apply must stop.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Usage: python scripts/device_day_name_column_decision.py <columns.tsv>")
        return 2
    path = Path(args[0])
    cols = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("column_name") or line.startswith("("):
            continue
        cols.add(line.split("\t")[0].strip())
    print("venues_rag columns:", sorted(cols))
    print("has name_local:", "name_local" in cols)
    print("has names_local:", "names_local" in cols)
    print("has nearest_landmark_local:", "nearest_landmark_local" in cols)
    print("has landmarks_local:", "landmarks_local" in cols)
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
