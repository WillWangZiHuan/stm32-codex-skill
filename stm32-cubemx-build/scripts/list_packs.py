#!/usr/bin/env python3
"""List the STM32 capability packs bundled with this Skill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PACKS_ROOT = Path(__file__).resolve().parents[1] / "packs"


def pack_records(packs_root: Path = PACKS_ROOT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for manifest_path in sorted(packs_root.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            records.append({"id": manifest_path.parent.name, "status": "invalid", "path": str(manifest_path.parent)})
            continue
        records.append(
            {
                "id": manifest.get("id", manifest_path.parent.name),
                "summary": manifest.get("summary", ""),
                "status": "available",
                "path": str(manifest_path.parent),
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a readable list.")
    args = parser.parse_args()
    records = pack_records()
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    elif records:
        for record in records:
            suffix = f": {record['summary']}" if record.get("summary") else ""
            print(f"{record['id']} ({record['status']}){suffix}")
    else:
        print("No capability packs found.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
