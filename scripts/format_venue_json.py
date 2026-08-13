#!/usr/bin/env python3
"""Curation round-trip helper for venue/glossary JSON files.

Two directions:

  python scripts/format_venue_json.py --to-readable data/laos_vientiane.json
      -> writes curation/laos_vientiane.json as UTF-8 with real Lao text,
         for editing in an editor or pasting into Gemini

  python scripts/format_venue_json.py --to-repo curation/laos_vientiane.json
      -> writes back to data/laos_vientiane.json, ASCII-escaped

Guarantees:
- Byte-identical round trip: to_repo(to_readable(f)) == f
- --to-repo refuses to write unless output is pure ASCII and re-parses equal
- Reports deltas (record count changes, key additions/removals)
- Idempotent both ways
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CURATION_DIR = PROJECT_ROOT / "curation"


def _load_json(path: Path) -> tuple:
    """Load and parse a JSON file. Returns (data, raw_bytes)."""
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    return data, raw


def _serialize_ascii(data) -> bytes:
    """Serialize to ASCII-escaped JSON matching repo formatting."""
    return (json.dumps(data, ensure_ascii=True, indent=2) + "\n").encode("ascii")


def _serialize_readable(data) -> bytes:
    """Serialize to human-readable UTF-8 JSON for curation."""
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _report_deltas(original, modified, label: str):
    """Print prominent warnings if structure changed."""
    deltas = []

    # Record count (venues or dishes array)
    for key in ("venues", "dishes", "glossary", "data", "items"):
        if key in original and key in modified:
            orig_count = len(original[key])
            mod_count = len(modified[key])
            if orig_count != mod_count:
                deltas.append(
                    f"  RECORD COUNT CHANGED: {key} {orig_count} -> {mod_count}"
                )

    # Top-level keys
    if isinstance(original, dict) and isinstance(modified, dict):
        orig_keys = set(original.keys())
        mod_keys = set(modified.keys())
        added = mod_keys - orig_keys
        removed = orig_keys - mod_keys
        if added:
            deltas.append(f"  KEYS ADDED: {sorted(added)}")
        if removed:
            deltas.append(f"  KEYS REMOVED: {sorted(removed)}")

    if deltas:
        print(f"\n{'='*60}")
        print(f"DELTAS DETECTED in {label}:")
        for d in deltas:
            print(d)
        print(f"{'='*60}\n")


def to_readable(input_path: Path):
    """Convert a data/ file to a readable curation/ file."""
    data, raw = _load_json(input_path)

    # Output goes to curation/ with the same filename
    CURATION_DIR.mkdir(exist_ok=True)
    output_path = CURATION_DIR / input_path.name

    readable_bytes = _serialize_readable(data)

    # Idempotent: if output already exists and matches, skip
    if output_path.exists():
        existing = output_path.read_bytes()
        if existing == readable_bytes:
            print(f"IDEMPOTENT: {output_path} already up to date.")
            return

    output_path.write_bytes(readable_bytes)
    print(f"WROTE: {output_path} ({len(readable_bytes)} bytes, UTF-8 readable)")


def to_repo(input_path: Path):
    """Convert a curation/ file back to its data/ counterpart, ASCII-escaped."""
    data, _raw = _load_json(input_path)

    # Output goes to data/ with the same filename
    output_path = DATA_DIR / input_path.name

    # Serialize as ASCII
    ascii_bytes = _serialize_ascii(data)

    # SAFETY: verify pure ASCII
    if not all(b < 128 for b in ascii_bytes):
        print("ERROR: Output is not pure ASCII. Refusing to write.", file=sys.stderr)
        sys.exit(1)

    # SAFETY: verify re-parse equals input
    reparsed = json.loads(ascii_bytes.decode("ascii"))
    if reparsed != data:
        print("ERROR: Re-parsed output does not equal input. Refusing to write.",
              file=sys.stderr)
        sys.exit(1)

    # Idempotent: if output already matches, skip
    if output_path.exists():
        existing = output_path.read_bytes()
        if existing == ascii_bytes:
            print(f"IDEMPOTENT: {output_path} already up to date.")
            return
        # Report deltas against existing data/ file
        existing_data = json.loads(existing.decode("utf-8"))
        _report_deltas(existing_data, data, input_path.name)

    output_path.write_bytes(ascii_bytes)
    print(f"WROTE: {output_path} ({len(ascii_bytes)} bytes, ASCII-escaped)")


def main():
    parser = argparse.ArgumentParser(
        description="Convert venue/glossary JSON between ASCII-escaped (repo) "
                    "and human-readable (curation) forms."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--to-readable",
        action="store_true",
        help="Convert data/ file to curation/ (UTF-8 with real Lao text)",
    )
    group.add_argument(
        "--to-repo",
        action="store_true",
        help="Convert curation/ file back to data/ (ASCII-escaped)",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Input JSON files to convert",
    )
    args = parser.parse_args()

    for filepath in args.files:
        path = Path(filepath)
        if not path.exists():
            print(f"ERROR: {path} does not exist", file=sys.stderr)
            sys.exit(1)

        if args.to_readable:
            to_readable(path)
        else:
            to_repo(path)


if __name__ == "__main__":
    main()
