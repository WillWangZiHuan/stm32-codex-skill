#!/usr/bin/env python3
"""Validate community STM32 board packages bundled with this Skill."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import board_profile


BOARDS_ROOT = Path(__file__).resolve().parents[1] / "boards"
BOARD_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RESULT_LEVELS = {"profile", "configuration", "compile", "hardware"}


class BoardPackageValidationError(ValueError):
    """Raised when a community board package is incomplete or inconsistent."""


def required(container: dict[str, Any], key: str, label: str) -> Any:
    if key not in container:
        raise BoardPackageValidationError(f"{label} is required.")
    return container[key]


def nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise BoardPackageValidationError(f"{label} must be a non-empty string.")
    return value


def string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        suffix = "a list" if allow_empty else "a non-empty list"
        raise BoardPackageValidationError(f"{label} must be {suffix}.")
    normalized: list[str] = []
    for index, item in enumerate(value):
        normalized.append(nonempty_string(item, f"{label}[{index}]"))
    if len(set(normalized)) != len(normalized):
        raise BoardPackageValidationError(f"{label} must not contain duplicates.")
    return normalized


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BoardPackageValidationError(f"{label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise BoardPackageValidationError(f"{label} is not valid UTF-8 JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise BoardPackageValidationError(f"{label} must contain a JSON object.")
    return value


def package_file(package_dir: Path, relative_path: str, label: str) -> Path:
    path = Path(nonempty_string(relative_path, label))
    if path.is_absolute() or ".." in path.parts:
        raise BoardPackageValidationError(f"{label} must stay inside its board package.")
    resolved = (package_dir / path).resolve()
    try:
        resolved.relative_to(package_dir.resolve())
    except ValueError as error:
        raise BoardPackageValidationError(f"{label} must stay inside its board package.") from error
    if not resolved.is_file():
        raise BoardPackageValidationError(f"{label} is missing: {resolved}")
    return resolved


def validate_source_url(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise BoardPackageValidationError(f"{label} must be an HTTPS source URL without credentials.")
    return value


def validate_board_package(package_dir: Path) -> dict[str, Any]:
    manifest = read_json(package_dir / "manifest.json", "board manifest")
    if manifest.get("schema_version") != 1:
        raise BoardPackageValidationError(f"{package_dir.name}: schema_version must be 1.")

    board_id = nonempty_string(required(manifest, "id", "id"), "id")
    if not BOARD_ID.fullmatch(board_id):
        raise BoardPackageValidationError(f"{package_dir.name}: id must use lowercase hyphen-case.")
    if package_dir.name != board_id:
        raise BoardPackageValidationError(
            f"{package_dir.name}: package directory must match manifest id {board_id!r}."
        )

    nonempty_string(required(manifest, "vendor", f"{board_id}.vendor"), f"{board_id}.vendor")
    board_name = nonempty_string(required(manifest, "name", f"{board_id}.name"), f"{board_id}.name")
    nonempty_string(required(manifest, "summary", f"{board_id}.summary"), f"{board_id}.summary")
    revisions = string_list(required(manifest, "revisions", f"{board_id}.revisions"), f"{board_id}.revisions")

    mcu = nonempty_string(required(manifest, "mcu", f"{board_id}.mcu"), f"{board_id}.mcu")
    if not board_profile.MCU_IDENTIFIER.fullmatch(mcu):
        raise BoardPackageValidationError(f"{board_id}.mcu contains unsupported characters.")

    profile_relative = nonempty_string(
        required(manifest, "profile", f"{board_id}.profile"),
        f"{board_id}.profile",
    )
    if profile_relative != "board-profile.json":
        raise BoardPackageValidationError(f"{board_id}.profile must be board-profile.json.")
    profile_path = package_file(package_dir, profile_relative, f"{board_id}.profile")
    profile = read_json(profile_path, f"{board_id} board profile")
    try:
        board_profile.validate_profile_data(profile)
    except board_profile.BoardProfileError as error:
        raise BoardPackageValidationError(f"{board_id}: invalid board profile: {error}") from error

    if not profile["pins"]:
        raise BoardPackageValidationError(f"{board_id}: board-profile.json must contain at least one cited pin.")
    if profile["board"]["name"] != board_name:
        raise BoardPackageValidationError(f"{board_id}: manifest name must match board-profile.json board.name.")
    if profile["mcu"]["part_number"] != mcu:
        raise BoardPackageValidationError(f"{board_id}: manifest mcu must match board-profile.json mcu.part_number.")

    manual = required(manifest, "manual", f"{board_id}.manual")
    if not isinstance(manual, dict):
        raise BoardPackageValidationError(f"{board_id}.manual must be an object.")
    nonempty_string(required(manual, "title", f"{board_id}.manual.title"), f"{board_id}.manual.title")
    validate_source_url(
        nonempty_string(required(manual, "url", f"{board_id}.manual.url"), f"{board_id}.manual.url"),
        f"{board_id}.manual.url",
    )
    manual_digest = nonempty_string(
        required(manual, "sha256", f"{board_id}.manual.sha256"),
        f"{board_id}.manual.sha256",
    )
    if not SHA256.fullmatch(manual_digest):
        raise BoardPackageValidationError(f"{board_id}.manual.sha256 must be a lowercase SHA-256 digest.")
    if profile["board"]["manual"]["sha256"] != manual_digest:
        raise BoardPackageValidationError(
            f"{board_id}: manifest manual SHA-256 must match board-profile.json."
        )

    result_level = nonempty_string(
        required(manifest, "result_level", f"{board_id}.result_level"),
        f"{board_id}.result_level",
    )
    if result_level not in RESULT_LEVELS:
        raise BoardPackageValidationError(
            f"{board_id}.result_level must be one of: {', '.join(sorted(RESULT_LEVELS))}."
        )

    examples = string_list(manifest.get("examples", []), f"{board_id}.examples", allow_empty=True)
    for index, example_relative in enumerate(examples):
        example_path = package_file(package_dir, example_relative, f"{board_id}.examples[{index}]")
        example = read_json(example_path, f"{board_id} example")
        if example.get("mcu") != mcu:
            raise BoardPackageValidationError(
                f"{board_id}.examples[{index}] mcu must match the board package."
            )

    return {
        **manifest,
        "revisions": revisions,
        "examples": examples,
        "path": str(package_dir),
    }


def validate_boards(boards_root: Path = BOARDS_ROOT) -> list[str]:
    if not boards_root.is_dir():
        raise BoardPackageValidationError(f"Boards directory is missing: {boards_root}")
    board_dirs = sorted(
        path
        for path in boards_root.iterdir()
        if path.is_dir() and not path.name.startswith((".", "_"))
    )
    seen_ids: set[str] = set()
    validated: list[str] = []
    for board_dir in board_dirs:
        manifest = validate_board_package(board_dir)
        board_id = manifest["id"]
        if board_id in seen_ids:
            raise BoardPackageValidationError(f"Duplicate board id: {board_id}")
        seen_ids.add(board_id)
        validated.append(board_id)
    return validated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boards-root", help="Override the community boards directory.")
    args = parser.parse_args()
    try:
        root = Path(args.boards_root).expanduser().resolve() if args.boards_root else BOARDS_ROOT
        identifiers = validate_boards(root)
    except BoardPackageValidationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    suffix = f": {', '.join(identifiers)}" if identifiers else ""
    print(f"Validated {len(identifiers)} board package(s){suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
