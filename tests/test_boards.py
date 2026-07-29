"""Tests for independently validatable community board packages."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "stm32-cubemx-build" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import list_boards  # noqa: E402
import validate_boards  # noqa: E402


MANUAL_SHA256 = "1" * 64


def valid_profile() -> dict[str, object]:
    return {
        "schema_version": 3,
        "board": {
            "name": "Example STM32 Board",
            "manual": {"path": "example-board-manual.pdf", "sha256": MANUAL_SHA256},
        },
        "mcu": {
            "part_number": "STM32F401RETx",
            "evidence": [
                {"page": 4, "anchor": "STM32F401RE controller", "claim": "The board uses STM32F401RE."}
            ],
        },
        "pins": [
            {
                "pin": "PB8",
                "board_signal": "Expansion I2C SCL",
                "silkscreen": "SCL",
                "connector": "J2.3",
                "position_note": "Expansion header contact 3",
                "manual_figure": "Figure 7",
                "shared_with": [],
                "status": "available",
                "electrical_constraints": ["4.7 kOhm pull-up to 3.3 V"],
                "electrical": {
                    "power_domain": "3V3",
                    "logic_voltage_v": 3.3,
                    "max_current_ma": 8,
                    "external_supply_required": False,
                    "conflicts": [],
                },
                "evidence": [
                    {
                        "page": 12,
                        "anchor": "J2.3 PB8 I2C SCL",
                        "claim": "J2.3 routes the I2C clock to PB8.",
                    }
                ],
            }
        ],
        "clocks": [],
        "constraints": [],
    }


def valid_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "example-stm32-board",
        "vendor": "Example Vendor",
        "name": "Example STM32 Board",
        "summary": "Reusable, cited board facts for one STM32F401 board.",
        "revisions": ["Rev A"],
        "mcu": "STM32F401RETx",
        "profile": "board-profile.json",
        "manual": {
            "title": "Example STM32 Board User Manual Rev A",
            "url": "https://example.com/example-board-manual.pdf",
            "sha256": MANUAL_SHA256,
        },
        "result_level": "profile",
        "examples": [],
    }


def write_board_package(boards_root: Path) -> Path:
    package_dir = boards_root / "example-stm32-board"
    package_dir.mkdir(parents=True)
    (package_dir / "manifest.json").write_text(
        json.dumps(valid_manifest(), indent=2) + "\n",
        encoding="utf-8",
    )
    (package_dir / "board-profile.json").write_text(
        json.dumps(valid_profile(), indent=2) + "\n",
        encoding="utf-8",
    )
    return package_dir


class BoardPackageTests(unittest.TestCase):
    def test_empty_builtin_catalog_is_valid_and_listable(self) -> None:
        self.assertEqual(validate_boards.validate_boards(), [])
        self.assertEqual(list_boards.board_records(), [])

    def test_valid_board_package_is_validated_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            boards_root = Path(temporary_directory)
            write_board_package(boards_root)
            self.assertEqual(validate_boards.validate_boards(boards_root), ["example-stm32-board"])
            records = list_boards.board_records(boards_root)
            self.assertEqual(records[0]["mcu"], "STM32F401RETx")
            self.assertEqual(records[0]["result_level"], "profile")

    def test_list_marks_a_non_object_manifest_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            boards_root = Path(temporary_directory)
            package_dir = boards_root / "invalid-board"
            package_dir.mkdir()
            (package_dir / "manifest.json").write_text("[]\n", encoding="utf-8")
            self.assertEqual(list_boards.board_records(boards_root)[0]["status"], "invalid")

    def test_package_directory_must_match_global_board_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            boards_root = Path(temporary_directory)
            package_dir = write_board_package(boards_root)
            renamed = boards_root / "wrong-directory"
            package_dir.rename(renamed)
            with self.assertRaisesRegex(
                validate_boards.BoardPackageValidationError,
                "package directory must match",
            ):
                validate_boards.validate_board_package(renamed)

    def test_manifest_manual_hash_must_match_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            boards_root = Path(temporary_directory)
            package_dir = write_board_package(boards_root)
            manifest = valid_manifest()
            manifest["manual"]["sha256"] = "2" * 64  # type: ignore[index]
            (package_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                validate_boards.BoardPackageValidationError,
                "must match board-profile.json",
            ):
                validate_boards.validate_board_package(package_dir)

    def test_profile_path_cannot_escape_board_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            boards_root = Path(temporary_directory)
            package_dir = write_board_package(boards_root)
            manifest = valid_manifest()
            manifest["profile"] = "../board-profile.json"
            (package_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                validate_boards.BoardPackageValidationError,
                "profile must be board-profile.json",
            ):
                validate_boards.validate_board_package(package_dir)

    def test_public_docs_define_board_package_contributions(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        contributing = (repository_root / "CONTRIBUTING.md").read_text(encoding="utf-8")
        contract = (
            repository_root
            / "stm32-cubemx-build"
            / "references"
            / "board-package-contract.md"
        ).read_text(encoding="utf-8")
        self.assertIn("boards/<board-id>/", contributing)
        self.assertIn("validate_boards.py", contributing)
        self.assertIn("official HTTPS source", contract)
        self.assertIn("result_level", contract)

    def test_board_pull_request_template_requires_evidence_and_validation(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        template = (
            repository_root
            / ".github"
            / "PULL_REQUEST_TEMPLATE"
            / "board-package.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Official manual URL", template)
        self.assertIn("SHA-256 matches the profile", template)
        self.assertIn("validate_boards.py", template)
        self.assertIn("Result level", template)


if __name__ == "__main__":
    unittest.main()
