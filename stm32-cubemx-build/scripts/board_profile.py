#!/usr/bin/env python3
"""Create an index for, and validate, evidence-backed STM32 board profiles."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


MCU_IDENTIFIER = re.compile(r"^[A-Za-z0-9()_-]+$")
PIN_IDENTIFIER = re.compile(r"^P[A-Z][0-9]{1,2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PIN_STATUSES = {"available", "reserved", "used"}
MANUAL_INDEX_SUFFIX = ".manual-index.json"
BOARD_PROFILE_SCHEMA_VERSION = 2
MIN_EVIDENCE_ANCHOR_CHARACTERS = 8
MAX_EVIDENCE_ANCHOR_CHARACTERS = 240


class BoardProfileError(ValueError):
    """Raised when a board profile needs additional documented facts."""


def nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise BoardProfileError(f"{label} must be a non-empty string.")
    return value


def object_value(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BoardProfileError(f"{label} must be an object.")
    return value


def list_value(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise BoardProfileError(f"{label} must be a list.")
    return value


def required_value(container: dict[str, Any], key: str, label: str) -> Any:
    if key not in container:
        raise BoardProfileError(f"{label} is required.")
    return container[key]


def normalize_evidence_text(value: str) -> str:
    """Normalize a short source anchor and extracted PDF text for matching."""

    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def validate_evidence(value: Any, label: str) -> None:
    evidence = list_value(value, label)
    if not evidence:
        raise BoardProfileError(f"{label} must contain at least one manual citation.")
    for index, item in enumerate(evidence, start=1):
        citation = object_value(item, f"{label}[{index}]")
        page = required_value(citation, "page", f"{label}[{index}].page")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise BoardProfileError(f"{label}[{index}].page must be a positive integer.")
        nonempty_string(required_value(citation, "claim", f"{label}[{index}].claim"), f"{label}[{index}].claim")
        anchor = nonempty_string(
            required_value(citation, "anchor", f"{label}[{index}].anchor"),
            f"{label}[{index}].anchor",
        )
        normalized_anchor = normalize_evidence_text(anchor)
        if len(normalized_anchor) < MIN_EVIDENCE_ANCHOR_CHARACTERS:
            raise BoardProfileError(
                f"{label}[{index}].anchor must contain at least "
                f"{MIN_EVIDENCE_ANCHOR_CHARACTERS} normalized characters."
            )
        if len(anchor) > MAX_EVIDENCE_ANCHOR_CHARACTERS:
            raise BoardProfileError(
                f"{label}[{index}].anchor length must be at most {MAX_EVIDENCE_ANCHOR_CHARACTERS} characters."
            )


def evidence_collections(profile: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    """Return all validated evidence arrays with stable error labels."""

    collections: list[tuple[str, list[Any]]] = [("mcu.evidence", profile["mcu"]["evidence"])]
    collections.extend((f"pins[{index}].evidence", pin["evidence"]) for index, pin in enumerate(profile["pins"], start=1))
    collections.extend(
        (f"clocks[{index}].evidence", clock["evidence"])
        for index, clock in enumerate(profile.get("clocks", []), start=1)
    )
    collections.extend(
        (f"constraints[{index}].evidence", constraint["evidence"])
        for index, constraint in enumerate(profile.get("constraints", []), start=1)
    )
    return collections


def evidence_pages(profile: dict[str, Any]) -> list[int]:
    return [
        citation["page"]
        for _, citations in evidence_collections(profile)
        for citation in citations
    ]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manual_index_output(path: Path) -> None:
    if not path.name.endswith(MANUAL_INDEX_SUFFIX):
        raise BoardProfileError(
            f"Manual index output must end with {MANUAL_INDEX_SUFFIX}; it contains extracted manual text and is private."
        )


def read_json_bytes(raw_bytes: bytes, path: Path) -> dict[str, Any]:
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise BoardProfileError(f"Board profile is not UTF-8 JSON: {path}") from error
    except json.JSONDecodeError as error:
        raise BoardProfileError(f"Board profile is not valid JSON: {path}: {error.msg}") from error
    return object_value(data, "board profile")


def read_profile_snapshot(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as error:
        raise BoardProfileError(f"Board profile path is missing: {path}") from error
    except OSError as error:
        raise BoardProfileError(f"Could not read board profile: {path}: {error}") from error


def read_json(path: Path) -> dict[str, Any]:
    return read_json_bytes(read_profile_snapshot(path), path)


def validate_profile_data(profile: dict[str, Any]) -> None:
    version = required_value(profile, "schema_version", "schema_version")
    if version != BOARD_PROFILE_SCHEMA_VERSION:
        raise BoardProfileError(f"schema_version must be {BOARD_PROFILE_SCHEMA_VERSION}.")

    board = object_value(required_value(profile, "board", "board"), "board")
    nonempty_string(required_value(board, "name", "board.name"), "board.name")
    manual = object_value(required_value(board, "manual", "board.manual"), "board.manual")
    nonempty_string(required_value(manual, "path", "board.manual.path"), "board.manual.path")
    digest = nonempty_string(required_value(manual, "sha256", "board.manual.sha256"), "board.manual.sha256")
    if not SHA256.fullmatch(digest):
        raise BoardProfileError("board.manual.sha256 must be a lowercase SHA-256 digest.")

    mcu = object_value(required_value(profile, "mcu", "mcu"), "mcu")
    part_number = nonempty_string(required_value(mcu, "part_number", "mcu.part_number"), "mcu.part_number")
    if not MCU_IDENTIFIER.fullmatch(part_number):
        raise BoardProfileError("mcu.part_number contains unsupported characters.")
    validate_evidence(required_value(mcu, "evidence", "mcu.evidence"), "mcu.evidence")

    pins = list_value(required_value(profile, "pins", "pins"), "pins")
    seen_pins: set[str] = set()
    for index, item in enumerate(pins, start=1):
        pin = object_value(item, f"pins[{index}]")
        pin_name = nonempty_string(required_value(pin, "pin", f"pins[{index}].pin"), f"pins[{index}].pin")
        if not PIN_IDENTIFIER.fullmatch(pin_name):
            raise BoardProfileError(f"pins[{index}].pin must look like PA0 or PB12.")
        if pin_name in seen_pins:
            raise BoardProfileError(f"pins[{index}].pin repeats {pin_name}.")
        seen_pins.add(pin_name)
        nonempty_string(required_value(pin, "board_signal", f"pins[{index}].board_signal"), f"pins[{index}].board_signal")
        status = nonempty_string(required_value(pin, "status", f"pins[{index}].status"), f"pins[{index}].status")
        if status not in PIN_STATUSES:
            raise BoardProfileError(f"pins[{index}].status must be one of: {', '.join(sorted(PIN_STATUSES))}.")
        electrical_constraints = list_value(pin.get("electrical_constraints", []), f"pins[{index}].electrical_constraints")
        for constraint_index, constraint in enumerate(electrical_constraints, start=1):
            nonempty_string(constraint, f"pins[{index}].electrical_constraints[{constraint_index}]")
        validate_evidence(required_value(pin, "evidence", f"pins[{index}].evidence"), f"pins[{index}].evidence")

    clocks = list_value(profile.get("clocks", []), "clocks")
    for index, item in enumerate(clocks, start=1):
        clock = object_value(item, f"clocks[{index}]")
        nonempty_string(required_value(clock, "name", f"clocks[{index}].name"), f"clocks[{index}].name")
        frequency = required_value(clock, "frequency_hz", f"clocks[{index}].frequency_hz")
        if isinstance(frequency, bool) or not isinstance(frequency, int) or frequency < 1:
            raise BoardProfileError(f"clocks[{index}].frequency_hz must be a positive integer.")
        validate_evidence(required_value(clock, "evidence", f"clocks[{index}].evidence"), f"clocks[{index}].evidence")

    constraints = list_value(profile.get("constraints", []), "constraints")
    for index, item in enumerate(constraints, start=1):
        constraint = object_value(item, f"constraints[{index}]")
        nonempty_string(required_value(constraint, "description", f"constraints[{index}].description"), f"constraints[{index}].description")
        validate_evidence(required_value(constraint, "evidence", f"constraints[{index}].evidence"), f"constraints[{index}].evidence")


def read_manual_snapshot(path: Path) -> bytes:
    if not path.is_file():
        raise BoardProfileError(f"Manual PDF path is missing: {path}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise BoardProfileError(f"Could not read manual PDF: {path}: {error}") from error


def read_pdf_page_texts_from_bytes(raw_manual: bytes, source_path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise BoardProfileError("PDF support requires pypdf. Install it with: python -m pip install pypdf") from error
    try:
        return [page.extract_text() or "" for page in PdfReader(io.BytesIO(raw_manual)).pages]
    except Exception as error:  # pypdf exposes several parse-specific exception types.
        raise BoardProfileError(f"Could not read manual PDF: {source_path}: {error}") from error


def read_pdf_page_texts(path: Path) -> list[str]:
    return read_pdf_page_texts_from_bytes(read_manual_snapshot(path), path)


def read_pdf_page_count(path: Path) -> int:
    return len(read_pdf_page_texts(path))


def validate_evidence_anchors(profile: dict[str, Any], page_texts: list[str]) -> None:
    """Require each claimed fact to have a short text anchor on its cited page."""

    normalized_pages = [normalize_evidence_text(page_text) for page_text in page_texts]
    for label, citations in evidence_collections(profile):
        for index, citation in enumerate(citations, start=1):
            page = citation["page"]
            if not normalized_pages[page - 1]:
                raise BoardProfileError(
                    f"{label}[{index}] cites manual page {page}, but that page has no extractable text. "
                    "Provide a text-accessible source for this fact."
                )
            anchor = normalize_evidence_text(citation["anchor"])
            if anchor not in normalized_pages[page - 1]:
                raise BoardProfileError(
                    f"{label}[{index}].anchor is absent from cited manual page {page}."
                )


def load_and_validate_profile_snapshot(
    profile_path: Path,
    manual_path: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    profile_snapshot = read_profile_snapshot(profile_path)
    profile = read_json_bytes(profile_snapshot, profile_path)
    validate_profile_data(profile)
    if manual_path is not None:
        manual_snapshot = read_manual_snapshot(manual_path)
        expected_digest = profile["board"]["manual"]["sha256"]
        actual_digest = hashlib.sha256(manual_snapshot).hexdigest()
        if actual_digest != expected_digest:
            raise BoardProfileError("Manual SHA-256 differs from board.manual.sha256; rebuild the profile from this exact manual.")
        page_texts = read_pdf_page_texts_from_bytes(manual_snapshot, manual_path)
        page_count = len(page_texts)
        too_large = sorted({page for page in evidence_pages(profile) if page > page_count})
        if too_large:
            raise BoardProfileError(f"Board profile cites page(s) beyond the manual length ({page_count}): {too_large}.")
        validate_evidence_anchors(profile, page_texts)
    return profile, profile_snapshot


def load_and_validate_profile(profile_path: Path, manual_path: Path | None = None) -> dict[str, Any]:
    profile, _ = load_and_validate_profile_snapshot(profile_path, manual_path)
    return profile


def index_pdf(manual_path: Path, output_path: Path) -> None:
    validate_manual_index_output(output_path)
    manual_snapshot = read_manual_snapshot(manual_path)
    page_texts = read_pdf_page_texts_from_bytes(manual_snapshot, manual_path)
    if not any(normalize_evidence_text(page_text) for page_text in page_texts):
        raise BoardProfileError(
            "Manual PDF has no extractable text. Provide a text-accessible manual or source."
        )
    pages = [{"page": index, "text": page_text} for index, page_text in enumerate(page_texts, start=1)]
    payload = {
        "schema_version": 1,
        "manual": {"path": str(manual_path), "sha256": hashlib.sha256(manual_snapshot).hexdigest()},
        "pages": pages,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8") as output:
            output.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as error:
        raise BoardProfileError(f"Manual index output already exists: {output_path}") from error


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    index = commands.add_parser("index-pdf", help="Extract page-numbered text and a SHA-256 digest from a manual PDF.")
    index.add_argument("--manual", required=True, help="Manual PDF supplied by the user.")
    index.add_argument(
        "--output",
        required=True,
        help="New private *.manual-index.json output path for the full-text manual index.",
    )

    validate = commands.add_parser("validate", help="Validate an evidence-backed board profile.")
    validate.add_argument("--profile", required=True, help="board-profile.json path.")
    validate.add_argument("--manual", help="Optional source PDF to hash-check and validate cited page numbers.")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "index-pdf":
            index_pdf(Path(args.manual).expanduser().resolve(), Path(args.output).expanduser().resolve())
            print(f"Created private manual index: {Path(args.output).expanduser().resolve()}")
            return 0
        if args.command == "validate":
            profile_path = Path(args.profile).expanduser().resolve()
            manual_path = Path(args.manual).expanduser().resolve() if args.manual else None
            profile = load_and_validate_profile(profile_path, manual_path)
            print(f"Board profile is valid: {profile_path}")
            print(f"MCU: {profile['mcu']['part_number']}")
            return 0
    except BoardProfileError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
