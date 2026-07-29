"""Tests for the deterministic Windows PowerShell smoke fixture."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

import windows_smoke_contract  # noqa: E402


class WindowsSmokeContractTests(unittest.TestCase):
    def test_complete_skill_command_sequence_creates_expected_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill_script = root / "stm32_cube.py"
            cubemx = root / "STM32CubeMX.exe"
            cubeide = root / "stm32cubeide.exe"
            manual = root / "board manual.pdf"
            profile = root / "board-profile.json"
            plan = root / "configuration-plan.json"
            output_dir = root / "output with spaces"
            state = root / "contract-state.json"
            for path in (skill_script, cubemx, cubeide, manual, profile, plan):
                path.write_text("contract\n", encoding="utf-8")
            output_dir.mkdir()

            common = [
                str(skill_script),
                "--cubemx",
                str(cubemx),
                "--cubeide",
                str(cubeide),
            ]
            project_dir = output_dir / "windows_contract"
            environment = {
                windows_smoke_contract.STATE_ENV: str(state),
                windows_smoke_contract.EXPECTED_CUBEMX_ENV: str(cubemx),
                windows_smoke_contract.EXPECTED_CUBEIDE_ENV: str(cubeide),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                self.assertEqual(windows_smoke_contract.run_skill_invocation(common + ["doctor", "--strict"]), 0)
                self.assertEqual(
                    windows_smoke_contract.run_skill_invocation(
                        common
                        + [
                            "create",
                            "--mcu",
                            "STM32F401RETx",
                            "--name",
                            "windows_contract",
                            "--output-dir",
                            str(output_dir),
                            "--board-profile",
                            str(profile),
                            "--manual",
                            str(manual),
                            "--plan",
                            str(plan),
                            "--jobs",
                            "3",
                        ]
                    ),
                    0,
                )

            windows_smoke_contract.verify_contract(state, project_dir)


if __name__ == "__main__":
    unittest.main()
