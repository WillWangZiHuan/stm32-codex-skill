"""Tests for the independently validatable capability-pack contract."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "stm32-cubemx-build" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_packs  # noqa: E402


class PackTests(unittest.TestCase):
    def test_public_docs_describe_the_manual_to_build_workflow(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        documents = [
            repository_root / "stm32-cubemx-build" / "SKILL.md",
            repository_root / "CONTRIBUTING.md",
            repository_root / "README.md",
        ]
        for document in documents:
            with self.subTest(document=document.name):
                text = document.read_text(encoding="utf-8")
                normalized_text = " ".join(text.split())
                self.assertIn("board", normalized_text.lower())
                self.assertIn("configuration", normalized_text.lower())
                self.assertIn("compil", normalized_text.lower())

    def test_validation_record_describes_current_evidence(self) -> None:
        validation_record = (Path(__file__).resolve().parents[1] / "VALIDATION.md").read_text(encoding="utf-8")
        for required_fragment in (
            "72 deterministic tests",
            "6 pack contracts",
            "End-to-end I2C run",
            "Configuration verified",
            "Compile verified",
            "Hardware run",
        ):
            with self.subTest(required_fragment=required_fragment):
                self.assertIn(required_fragment, validation_record)

    def test_windows_smoke_harness_runs_the_full_generation_chain(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "stm32-cubemx-build"
            / "scripts"
            / "windows_smoke.ps1"
        ).read_text(encoding="utf-8")
        for required_fragment in (
            '"doctor", "--strict"',
            '"generate"',
            '"module"',
            '"integrate"',
            '"build"',
            '"--cubemx"',
            '"--cubeide"',
            '"--board-profile"',
            '"--manual"',
            '"--plan"',
            "WINDOWS_SMOKE_PASS",
            "Project directory already exists",
            "Generation and compilation completed.",
        ):
            with self.subTest(required_fragment=required_fragment):
                self.assertIn(required_fragment, script)
        self.assertNotIn("Remove-Item", script)
        self.assertNotIn("Invoke-Expression", script)

    def test_builtin_packs_satisfy_contract(self) -> None:
        self.assertEqual(validate_packs.validate_packs(), ["gpio", "i2c", "pwm", "spi", "timer", "uart"])

    def test_builtin_packs_declare_only_supported_ioc_override_kinds(self) -> None:
        expected = {
            "gpio": ["gpio-initial-state"],
            "i2c": [],
            "pwm": [],
            "spi": [],
            "timer": ["timer-nvic-enable"],
            "uart": [],
        }
        for pack_id, override_kinds in expected.items():
            with self.subTest(pack_id=pack_id):
                manifest = validate_packs.validate_pack(validate_packs.PACKS_ROOT / pack_id)
                self.assertEqual(manifest["ioc_override_kinds"], override_kinds)

    def test_builtin_packs_declare_machine_checked_plan_resources(self) -> None:
        expected = {
            "gpio": {
                "operation_instance_prefixes": [],
                "direct_pin_signals": ["GPIO_Output"],
                "required_operation_signal_suffixes": [],
                "minimum_operation_pins": 0,
            },
            "i2c": {
                "operation_instance_prefixes": ["I2C"],
                "direct_pin_signals": [],
                "required_operation_signal_suffixes": ["SCL", "SDA"],
                "minimum_operation_pins": 2,
            },
            "pwm": {
                "operation_instance_prefixes": ["TIM", "LPTIM"],
                "direct_pin_signals": [],
                "required_operation_signal_suffixes": [],
                "minimum_operation_pins": 1,
            },
            "spi": {
                "operation_instance_prefixes": ["SPI"],
                "direct_pin_signals": [],
                "required_operation_signal_suffixes": [],
                "minimum_operation_pins": 0,
            },
            "timer": {
                "operation_instance_prefixes": ["TIM", "LPTIM"],
                "direct_pin_signals": [],
                "required_operation_signal_suffixes": [],
                "minimum_operation_pins": 0,
            },
            "uart": {
                "operation_instance_prefixes": ["USART", "UART", "LPUART"],
                "direct_pin_signals": [],
                "required_operation_signal_suffixes": [],
                "minimum_operation_pins": 0,
            },
        }
        for pack_id, plan_resources in expected.items():
            with self.subTest(pack_id=pack_id):
                manifest = validate_packs.validate_pack(validate_packs.PACKS_ROOT / pack_id)
                self.assertEqual(manifest["plan_resources"], plan_resources)

    def test_pack_contract_requires_renderable_header_source_pair_and_valid_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            pack_dir = Path(temporary_directory) / "broken"
            templates_dir = pack_dir / "templates"
            templates_dir.mkdir(parents=True)
            (pack_dir / "PACK.md").write_text("# Broken\n", encoding="utf-8")
            manifest = {
                "schema_version": 4,
                "id": "broken",
                "summary": "Broken test fixture.",
                "requires": ["One fact."],
                "templates": ["templates/broken.c.tmpl"],
                "plan_resources": {
                    "operation_instance_prefixes": [],
                    "direct_pin_signals": [],
                    "required_operation_signal_suffixes": [],
                    "minimum_operation_pins": 0,
                },
                "ioc_override_kinds": [],
                "verifications": ["One check."],
            }
            (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (templates_dir / "broken.c.tmpl").write_text("{{bad_token}}", encoding="utf-8")
            with self.assertRaisesRegex(validate_packs.PackValidationError, "exactly one .h.tmpl"):
                validate_packs.validate_pack(pack_dir)

            manifest["templates"] = ["templates/broken.h.tmpl", "templates/broken.c.tmpl"]
            (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (templates_dir / "broken.h.tmpl").write_text("#define BROKEN\n", encoding="utf-8")
            with self.assertRaisesRegex(validate_packs.PackValidationError, "malformed placeholder"):
                validate_packs.validate_pack(pack_dir)

            (templates_dir / "broken.c.tmpl").write_text("void broken(void) {}\n", encoding="utf-8")
            manifest["plan_resources"] = {
                "operation_instance_prefixes": ["i2c"],
                "direct_pin_signals": [],
                "required_operation_signal_suffixes": [],
                "minimum_operation_pins": 0,
            }
            (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(validate_packs.PackValidationError, "unsupported resource token"):
                validate_packs.validate_pack(pack_dir)

            manifest["plan_resources"] = {
                "operation_instance_prefixes": [],
                "direct_pin_signals": [],
                "required_operation_signal_suffixes": [],
                "minimum_operation_pins": 0,
            }
            manifest["ioc_override_kinds"] = ["arbitrary-write"]
            (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(validate_packs.PackValidationError, "unsupported ioc_override_kinds"):
                validate_packs.validate_pack(pack_dir)

    def test_gpio_template_keeps_output_and_interrupt_boundaries_explicit(self) -> None:
        gpio_source = (
            Path(__file__).resolve().parents[1]
            / "stm32-cubemx-build"
            / "packs"
            / "gpio"
            / "templates"
            / "gpio_output.c.tmpl"
        ).read_text(encoding="utf-8")
        self.assertIn("HAL_GPIO_WritePin", gpio_source)
        self.assertIn("HAL_GPIO_TogglePin", gpio_source)
        self.assertNotIn("HAL_GPIO_EXTI_Callback", gpio_source)
        self.assertNotIn("HAL_GPIO_ReadPin", gpio_source)

    def test_uart_template_keeps_timeout_and_interrupt_boundaries_explicit(self) -> None:
        uart_source = (
            Path(__file__).resolve().parents[1]
            / "stm32-cubemx-build"
            / "packs"
            / "uart"
            / "templates"
            / "uart_port.c.tmpl"
        ).read_text(encoding="utf-8")
        self.assertIn("HAL_UART_Transmit", uart_source)
        self.assertIn("HAL_UART_Receive", uart_source)
        self.assertIn("timeout_ms", uart_source)
        self.assertNotIn("HAL_UART_Receive_IT", uart_source)
        self.assertNotIn("HAL_UART_Receive_DMA", uart_source)

    def test_spi_template_keeps_chip_select_and_async_boundaries_explicit(self) -> None:
        spi_source = (
            Path(__file__).resolve().parents[1]
            / "stm32-cubemx-build"
            / "packs"
            / "spi"
            / "templates"
            / "spi_bus.c.tmpl"
        ).read_text(encoding="utf-8")
        self.assertIn("HAL_SPI_TransmitReceive", spi_source)
        self.assertIn("timeout_ms", spi_source)
        self.assertNotIn("HAL_SPI_TransmitReceive_IT", spi_source)
        self.assertNotIn("HAL_SPI_TransmitReceive_DMA", spi_source)
        self.assertNotIn("HAL_GPIO_WritePin", spi_source)
