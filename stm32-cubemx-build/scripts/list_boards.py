#!/usr/bin/env python3
"""List community STM32 board packages bundled with this Skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import validate_boards


BOARDS_ROOT = Path(__file__).resolve().parents[1] / "boards"


def board_records(boards_root: Path = BOARDS_ROOT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not boards_root.is_dir():
        return records
    for manifest_path in sorted(boards_root.glob("*/manifest.json")):
        try:
            manifest = validate_boards.validate_board_package(manifest_path.parent)
        except validate_boards.BoardPackageValidationError:
            records.append(
                {
                    "id": manifest_path.parent.name,
                    "status": "invalid",
                    "path": str(manifest_path.parent),
                }
            )
            continue
        records.append(
            {
                "id": manifest.get("id", manifest_path.parent.name),
                "vendor": manifest.get("vendor", ""),
                "name": manifest.get("name", ""),
                "mcu": manifest.get("mcu", ""),
                "result_level": manifest.get("result_level", ""),
                "summary": manifest.get("summary", ""),
                "status": "validated",
                "path": str(manifest_path.parent),
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a readable list.")
    parser.add_argument("--boards-root", help="Override the community boards directory.")
    args = parser.parse_args()
    root = Path(args.boards_root).expanduser().resolve() if args.boards_root else BOARDS_ROOT
    records = board_records(root)
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    elif records:
        for record in records:
            identity = " / ".join(
                value for value in (record.get("vendor"), record.get("name"), record.get("mcu")) if value
            )
            level = f", {record['result_level']}" if record.get("result_level") else ""
            summary = f": {record['summary']}" if record.get("summary") else ""
            print(f"{record['id']} ({record['status']}{level}) {identity}{summary}".rstrip())
    else:
        print("No community board packages are installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
