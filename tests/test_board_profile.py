"""Tests for evidence-backed board profile validation."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "stm32-cubemx-build" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import board_profile  # noqa: E402


def valid_profile() -> dict[str, object]:
    return {
        "schema_version": 2,
        "board": {"name": "Reference board", "manual": {"path": "manual.pdf", "sha256": "b" * 64}},
        "mcu": {
            "part_number": "STM32F401RETx",
            "evidence": [{"page": 1, "anchor": "STM32F401RETx", "claim": "MCU"}],
        },
        "pins": [
            {
                "pin": "PA8",
                "board_signal": "PWM_OUT",
                "status": "available",
                "electrical_constraints": [],
                "evidence": [{"page": 3, "anchor": "PA8 PWM connector", "claim": "PWM connector"}],
            }
        ],
        "clocks": [
            {
                "name": "HSE",
                "frequency_hz": 8000000,
                "evidence": [{"page": 4, "anchor": "8 MHz crystal", "claim": "crystal"}],
            }
        ],
    }


class BoardProfileTests(unittest.TestCase):
    def test_valid_profile_is_accepted(self) -> None:
        board_profile.validate_profile_data(valid_profile())

    def test_pin_evidence_is_required(self) -> None:
        profile = valid_profile()
        profile["pins"][0].pop("evidence")  # type: ignore[index]
        with self.assertRaises(board_profile.BoardProfileError):
            board_profile.validate_profile_data(profile)

    def test_evidence_anchor_is_required(self) -> None:
        profile = valid_profile()
        profile["mcu"]["evidence"][0].pop("anchor")  # type: ignore[index]
        with self.assertRaisesRegex(board_profile.BoardProfileError, r"mcu\.evidence\[1\]\.anchor is required"):
            board_profile.validate_profile_data(profile)

    def test_manual_validation_accepts_anchors_on_their_cited_pages(self) -> None:
        profile = valid_profile()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            manual_path = temporary_root / "manual.pdf"
            manual_path.write_bytes(b"test manual bytes")
            profile["board"]["manual"]["sha256"] = board_profile.sha256_file(manual_path)  # type: ignore[index]
            profile_path = temporary_root / "board-profile.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            with mock.patch.object(
                board_profile,
                "read_pdf_page_texts_from_bytes",
                return_value=[
                    "STM32F401RETx reference fixture",
                    "unused page",
                    "PA8 PWM connector",
                    "8 MHz crystal",
                ],
            ):
                loaded = board_profile.load_and_validate_profile(profile_path, manual_path)
        self.assertEqual(loaded["mcu"]["part_number"], "STM32F401RETx")

    def test_profile_snapshot_uses_exact_profile_and_manual_bytes(self) -> None:
        profile = valid_profile()
        original_manual = b"original manual bytes"
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            manual_path = temporary_root / "manual.pdf"
            manual_path.write_bytes(original_manual)
            profile["board"]["manual"]["sha256"] = hashlib.sha256(original_manual).hexdigest()  # type: ignore[index]
            profile_path = temporary_root / "board-profile.json"
            profile_path.write_text(json.dumps(profile, sort_keys=True), encoding="utf-8")
            original_profile = profile_path.read_bytes()

            def read_snapshot_page_texts(raw_manual: bytes, source: Path) -> list[str]:
                self.assertEqual(raw_manual, original_manual)
                self.assertEqual(source, manual_path)
                manual_path.write_bytes(b"replaced manual bytes")
                profile_path.write_text('{"schema_version": 999}', encoding="utf-8")
                return [
                    "STM32F401RETx reference fixture",
                    "unused page",
                    "PA8 PWM connector",
                    "8 MHz crystal",
                ]

            with mock.patch.object(
                board_profile,
                "read_pdf_page_texts_from_bytes",
                side_effect=read_snapshot_page_texts,
                create=True,
            ):
                loaded, profile_snapshot = board_profile.load_and_validate_profile_snapshot(profile_path, manual_path)

        self.assertEqual(profile_snapshot, original_profile)
        self.assertEqual(loaded["mcu"]["part_number"], "STM32F401RETx")

    def test_manual_index_hashes_the_same_snapshot_it_extracts(self) -> None:
        original_manual = b"original manual bytes"
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            manual_path = temporary_root / "manual.pdf"
            manual_path.write_bytes(original_manual)
            index_path = temporary_root / "manual.manual-index.json"

            def read_snapshot_page_texts(raw_manual: bytes, source: Path) -> list[str]:
                self.assertEqual(raw_manual, original_manual)
                self.assertEqual(source, manual_path)
                manual_path.write_bytes(b"replaced manual bytes")
                return ["Snapshot page text"]

            with mock.patch.object(
                board_profile,
                "read_pdf_page_texts_from_bytes",
                side_effect=read_snapshot_page_texts,
            ):
                board_profile.index_pdf(manual_path, index_path)

            index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["manual"]["sha256"], hashlib.sha256(original_manual).hexdigest())
        self.assertEqual(index["pages"], [{"page": 1, "text": "Snapshot page text"}])

    def test_manual_index_requires_extractable_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            manual_path = temporary_root / "manual.pdf"
            manual_path.write_bytes(b"manual bytes")
            index_path = temporary_root / "manual.manual-index.json"
            with mock.patch.object(
                board_profile,
                "read_pdf_page_texts_from_bytes",
                return_value=["", "  \n"],
            ):
                with self.assertRaisesRegex(board_profile.BoardProfileError, "no extractable text"):
                    board_profile.index_pdf(manual_path, index_path)
            self.assertFalse(index_path.exists())

    def test_manual_index_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            manual_path = temporary_root / "manual.pdf"
            manual_path.write_bytes(b"manual bytes")
            index_path = temporary_root / "manual.manual-index.json"

            def create_competing_index(_raw_manual: bytes, _source: Path) -> list[str]:
                index_path.write_text("private competing index", encoding="utf-8")
                return ["Page text"]

            with mock.patch.object(
                board_profile,
                "read_pdf_page_texts_from_bytes",
                side_effect=create_competing_index,
            ):
                with self.assertRaisesRegex(board_profile.BoardProfileError, "Manual index output already exists"):
                    board_profile.index_pdf(manual_path, index_path)

            self.assertEqual(index_path.read_text(encoding="utf-8"), "private competing index")

    def test_profile_validates_unique_pins(self) -> None:
        profile = valid_profile()
        profile["pins"].append(profile["pins"][0])  # type: ignore[index]
        with self.assertRaises(board_profile.BoardProfileError):
            board_profile.validate_profile_data(profile)

    def test_manual_index_requires_private_filename_suffix(self) -> None:
        board_profile.validate_manual_index_output(Path("/private/tmp/board.manual-index.json"))
        with self.assertRaises(board_profile.BoardProfileError):
            board_profile.validate_manual_index_output(Path("/private/tmp/board-index.json"))

    def test_manual_validation_checks_anchor_on_its_cited_page(self) -> None:
        profile = valid_profile()
        for evidence_owner in [profile["mcu"], *profile["pins"], *profile["clocks"]]:  # type: ignore[index]
            evidence_owner["evidence"][0]["page"] = 1  # type: ignore[index]
        profile["mcu"]["evidence"][0]["anchor"] = "not present on the cited page"  # type: ignore[index]

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            manual_path = temporary_root / "manual.pdf"
            manual_path.write_bytes(b"test manual bytes")
            profile["board"]["manual"]["sha256"] = board_profile.sha256_file(manual_path)  # type: ignore[index]
            profile_path = temporary_root / "board-profile.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            with (
                mock.patch.object(
                    board_profile,
                    "read_pdf_page_texts_from_bytes",
                    return_value=["STM32F401RETx reference fixture"],
                    create=True,
                ),
            ):
                with self.assertRaisesRegex(
                    board_profile.BoardProfileError,
                    r"mcu\.evidence\[1\]\.anchor is absent from cited manual page 1",
                ):
                    board_profile.load_and_validate_profile(profile_path, manual_path)

    def test_manual_validation_explains_when_a_cited_page_has_no_extractable_text(self) -> None:
        profile = valid_profile()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            manual_path = temporary_root / "manual.pdf"
            manual_path.write_bytes(b"test manual bytes")
            profile["board"]["manual"]["sha256"] = board_profile.sha256_file(manual_path)  # type: ignore[index]
            profile_path = temporary_root / "board-profile.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            with mock.patch.object(
                board_profile,
                "read_pdf_page_texts_from_bytes",
                return_value=["", "unused page", "PA8 PWM connector", "8 MHz crystal"],
            ):
                with self.assertRaisesRegex(
                    board_profile.BoardProfileError,
                    r"mcu\.evidence\[1\] cites manual page 1, but that page has no extractable text",
                ):
                    board_profile.load_and_validate_profile(profile_path, manual_path)
