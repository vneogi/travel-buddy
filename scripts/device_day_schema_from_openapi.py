"""Build the venues_rag column TSV for device-day Step 3 without psql.

Reads the PostgREST OpenAPI dump from export_live_snapshot.py
(_live_schema.json) and writes column_name\\tdata_type\\tudt_name lines
compatible with device_day_name_column_decision.py.

Usage:

    python scripts/device_day_schema_from_openapi.py data/live_snapshot/STAMP
    python scripts/device_day_schema_from_openapi.py data/live_snapshot/STAMP --out %TEMP%\\tb_venues_rag_columns.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write venues_rag columns TSV from a live_snapshot OpenAPI dump"
    )
    parser.add_argument(
        "snapshot_dir",
        help="Path to data/live_snapshot/<stamp> containing _live_schema.json",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output TSV path (default: <snapshot>/venues_rag_columns.tsv)",
    )
    parser.add_argument(
        "--table",
        default="venues_rag",
        help="Table to extract (default: venues_rag)",
    )
    args = parser.parse_args(argv)

    snap = Path(args.snapshot_dir)
    schema_path = snap / "_live_schema.json"
    if not schema_path.is_file():
        print("ERROR: missing %s" % schema_path, file=sys.stderr)
        print(
            "Re-run: python scripts/export_live_snapshot.py",
            file=sys.stderr,
        )
        return 2

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    table = schema.get(args.table)
    if not isinstance(table, dict) or not table:
        print(
            "ERROR: table %r absent from OpenAPI dump (keys=%s)"
            % (args.table, sorted(schema.keys())[:20]),
            file=sys.stderr,
        )
        return 2

    out = Path(args.out) if args.out else snap / ("%s_columns.tsv" % args.table)
    lines = ["column_name\tdata_type\tudt_name"]
    for name, meta in sorted(table.items()):
        typ = ""
        fmt = ""
        if isinstance(meta, dict):
            typ = meta.get("type") or ""
            fmt = meta.get("format") or ""
        # decision script only needs column_name in column 0
        lines.append("%s\t%s\t%s" % (name, typ, fmt))

    out.write_text("\n".join(lines) + "\n", encoding="ascii")
    print("wrote %s (%d columns for %s)" % (out, len(table), args.table))
    print("NEXT: python scripts/device_day_name_column_decision.py %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
