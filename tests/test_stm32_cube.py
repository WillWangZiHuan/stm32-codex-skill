"""Small unit tests for the deterministic parts of the STM32 Skill helper."""

from __future__ import annotations

import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "stm32-cubemx-build" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import stm32_cube  # noqa: E402


class CubeScriptTests(unittest.TestCase):
    @staticmethod
    def generated_makefile_text() -> str:
        return (
            "C_SOURCES = Src/stm32f4xx_hal_msp.c\n"
            "ASM_SOURCES = startup.s\n"
            "C_INCLUDES = -IInc\n"
            "AS_INCLUDES =\n"
            "LDSCRIPT = STM32F401xx_FLASH.ld\n"
            "all:\n"
            "\t@true\n"
            "#######################################\n"
            "# build the application\n"
        )

    @staticmethod
    def board_profile() -> dict[str, object]:
        return {
            "schema_version": 2,
            "board": {
                "name": "F401 reference board",
                "manual": {"path": "reference.pdf", "sha256": "a" * 64},
            },
            "mcu": {
                "part_number": "STM32F401RETx",
                "evidence": [{"page": 1, "anchor": "STM32F401RETx", "claim": "MCU marking"}],
            },
            "pins": [
                {
                    "pin": "PB8",
                    "board_signal": "SCL",
                    "status": "available",
                    "electrical_constraints": ["pull-up present"],
                    "evidence": [{"page": 2, "anchor": "PB8 SCL wiring", "claim": "SCL wiring"}],
                },
                {
                    "pin": "PB9",
                    "board_signal": "SDA",
                    "status": "available",
                    "electrical_constraints": ["pull-up present"],
                    "evidence": [{"page": 2, "anchor": "PB9 SDA wiring", "claim": "SDA wiring"}],
                },
            ],
        }

    @staticmethod
    def write_ioc_generation_facts(project_dir: Path) -> Path:
        ioc_path = project_dir / "verified.ioc"
        ioc_path.write_text(
            "MxCube.Version=6.18.0\n"
            "MxDb.Version=DB.6.0.180\n"
            "ProjectManager.FirmwarePackage=STM32Cube FW_F4 V1.28.3\n",
            encoding="utf-8",
        )
        return ioc_path

    def write_project_provenance(
        self,
        project_dir: Path,
        packs: list[str],
        modules: list[dict[str, object]] | None = None,
    ) -> Path:
        self.write_ioc_generation_facts(project_dir)
        (project_dir / "Makefile").write_text(self.generated_makefile_text(), encoding="utf-8")
        (project_dir / "startup.s").write_text(".syntax unified\n", encoding="utf-8")
        (project_dir / "STM32F401xx_FLASH.ld").write_text(
            "MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 512K }\n",
            encoding="utf-8",
        )
        generated_header = project_dir / "Inc" / "build_input.h"
        generated_header.parent.mkdir(parents=True, exist_ok=True)
        generated_header.write_text("#define GENERATED_BUILD_INPUT 1\n", encoding="utf-8")
        generated_source = project_dir / "Src" / "stm32f4xx_hal_msp.c"
        generated_source.parent.mkdir(parents=True, exist_ok=True)
        generated_source.write_text(
            '#include "build_input.h"\n'
            "/* USER CODE BEGIN 0 */\n"
            "/* USER CODE END 0 */\n"
            "extern I2C_HandleTypeDef hi2c1;\n"
            "extern SPI_HandleTypeDef hspi1;\n"
            "extern TIM_HandleTypeDef htim2;\n"
            "extern UART_HandleTypeDef huart2;\n"
            "void HAL_MspInit(void)\n"
            "{\n"
            "  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_SET);\n"
            "  (void)GPIO_PIN_2;\n"
            "  (void)TIM_CHANNEL_1;\n"
            "  HAL_NVIC_SetPriority(TIM2_IRQn, 0, 0);\n"
            "}\n",
            encoding="utf-8",
        )
        configuration = {
            "mcu": "STM32F401RETx",
            "plan_sha256": "b" * 64,
            "packs": packs,
            "modules": modules or [],
        }
        return stm32_cube.write_project_provenance(
            project_dir,
            configuration,
            self.board_profile(),
            "c" * 64,
        )

    def test_validates_expected_mcu_identifier(self) -> None:
        self.assertEqual(stm32_cube.validated_mcu_identifier("STM32F401RETx"), "STM32F401RETx")
        self.assertEqual(stm32_cube.validated_mcu_identifier("STM32F103C(8-B)Tx"), "STM32F103C(8-B)Tx")
        self.assertTrue(stm32_cube.cubemx_refname_matches_mcu("STM32F401R(D-E)Tx", "STM32F401RETx"))
        self.assertTrue(stm32_cube.cubemx_refname_matches_mcu("STM32X(G-E)Tx", "STM32XFTx"))

    def test_rejects_mcu_command_injection(self) -> None:
        with self.assertRaises(ValueError):
            stm32_cube.validated_mcu_identifier("STM32F401RETx\nexit")

    def test_doctor_strict_requires_pypdf_for_manual_driven_generation(self) -> None:
        toolchain = stm32_cube.Toolchain(
            platform="Darwin",
            cubemx="/Applications/STM32CubeMX",
            cubeide="/Applications/STM32CubeIDE",
            gcc="/Applications/arm-none-eabi-gcc",
            make="/Applications/make",
            cmake=None,
            ninja=None,
            pypdf=None,
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(stm32_cube.report_tools(toolchain, as_json=False, strict=True), 2)
        self.assertIn("pypdf", stderr.getvalue())

    def test_windows_candidates_include_standard_all_user_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            program_files = Path(temporary_directory)
            with mock.patch.dict(
                stm32_cube.os.environ,
                {"ProgramFiles": str(program_files), "ProgramFiles(x86)": str(program_files)},
                clear=True,
            ):
                cubemx_candidates, cubeide_candidates, plugin_root = stm32_cube.windows_candidates()

        self.assertIn(
            program_files / "STMicroelectronics" / "STM32Cube" / "STM32CubeMX" / "STM32CubeMX.exe",
            cubemx_candidates,
        )
        self.assertIn(
            program_files / "STMicroelectronics" / "STM32CubeIDE" / "STM32CubeIDE" / "stm32cubeide.exe",
            cubeide_candidates,
        )
        self.assertIsNone(plugin_root)

    def test_windows_tool_overrides_find_cubeide_plugin_tools(self) -> None:
        def executable(path: Path) -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            path.chmod(0o755)
            return path

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cubemx = executable(root / "custom-cubemx" / "STM32CubeMX.exe")
            cubeide = executable(root / "custom-cubeide" / "stm32cubeide.exe")
            plugins = cubeide.parent / "plugins"
            gcc = executable(
                plugins
                / "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.0"
                / "tools"
                / "bin"
                / "arm-none-eabi-gcc.exe"
            )
            make = executable(
                plugins
                / "com.st.stm32cube.ide.mcu.externaltools.make.win32_2.0.0"
                / "tools"
                / "bin"
                / "make.exe"
            )
            cmake = executable(
                plugins
                / "com.st.stm32cube.ide.mcu.externaltools.cmake.win32_1.0.0"
                / "tools"
                / "bin"
                / "cmake.exe"
            )
            ninja = executable(
                plugins
                / "com.st.stm32cube.ide.mcu.externaltools.ninja.win32_1.0.0"
                / "tools"
                / "bin"
                / "ninja.exe"
            )
            with (
                mock.patch.object(stm32_cube.platform, "system", return_value="Windows"),
                mock.patch.object(stm32_cube, "windows_candidates", return_value=([], [], None)),
                mock.patch.object(stm32_cube, "command_path", return_value=None),
                mock.patch.object(stm32_cube, "installed_pypdf_version", return_value="test"),
            ):
                toolchain = stm32_cube.discover_tools(str(cubemx), str(cubeide))

        self.assertEqual(toolchain.platform, "Windows")
        self.assertEqual(toolchain.cubemx, str(cubemx))
        self.assertEqual(toolchain.cubeide, str(cubeide))
        self.assertEqual(toolchain.gcc, str(gcc))
        self.assertEqual(toolchain.make, str(make))
        self.assertEqual(toolchain.cmake, str(cmake))
        self.assertEqual(toolchain.ninja, str(ninja))
        self.assertEqual(toolchain.pypdf, "test")
        arguments = stm32_cube.parser().parse_args(
            ["--cubemx", str(cubemx), "--cubeide", str(cubeide), "doctor", "--strict"]
        )
        self.assertEqual(arguments.cubemx, str(cubemx))
        self.assertEqual(arguments.cubeide, str(cubeide))
        self.assertTrue(arguments.strict)

    def test_doctor_rejects_an_invalid_explicit_tool_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_cubemx = Path(temporary_directory) / "missing" / "STM32CubeMX.exe"
            stderr = io.StringIO()
            with (
                mock.patch.object(stm32_cube.platform, "system", return_value="Windows"),
                mock.patch.object(stm32_cube, "windows_candidates", return_value=([], [], None)),
                mock.patch.object(
                    sys,
                    "argv",
                    ["stm32_cube.py", "--cubemx", str(missing_cubemx), "doctor", "--strict"],
                ),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(stm32_cube.main(), 2)

        self.assertIn("STM32CubeMX override does not exist", stderr.getvalue())

    def test_script_places_project_under_output_directory(self) -> None:
        script = stm32_cube.cubemx_script("STM32F401RETx", "demo", Path("/tmp/output"))
        self.assertIn('project name demo', script)
        self.assertIn('project path "/tmp/output"', script)
        self.assertIn('project toolchain "Makefile"', script)
        self.assertNotIn('project path "/tmp/output/demo"', script)

    def test_generate_rejects_the_evidence_chain_bypass(self) -> None:
        arguments = stm32_cube.argparse.Namespace(
            name="demo",
            mcu="STM32F401RETx",
            output_dir="/tmp",
            board_profile=None,
            manual=None,
            plan=None,
            cubemx=None,
            cubeide=None,
            dry_run=True,
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(stm32_cube.run_generate(arguments), 2)
        self.assertIn("evidence-free baseline generation is unsupported", stderr.getvalue())

        parser_stderr = io.StringIO()
        with contextlib.redirect_stderr(parser_stderr), self.assertRaises(SystemExit) as error:
            stm32_cube.parser().parse_args(
                ["generate", "--mcu", "STM32F401RETx", "--name", "demo", "--output-dir", "/tmp"]
            )
        self.assertEqual(error.exception.code, 2)
        self.assertIn("--board-profile", parser_stderr.getvalue())

    def test_generate_records_the_hash_of_the_validated_profile_snapshot(self) -> None:
        profile_snapshot = b'{"profile":"validated snapshot"}'
        configuration = {
            "mcu": "STM32F401RETx",
            "plan_sha256": "b" * 64,
            "packs": ["gpio"],
            "modules": [],
            "operations": [],
            "pin_assignments": [],
            "ioc_overrides": [],
            "verifications": [],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            arguments = stm32_cube.argparse.Namespace(
                name="demo",
                mcu="STM32F401RETx",
                output_dir=str(output_dir),
                board_profile=str(output_dir / "board-profile.json"),
                manual=str(output_dir / "manual.pdf"),
                plan=str(output_dir / "configuration-plan.json"),
                cubemx=None,
                cubeide=None,
                dry_run=False,
            )
            toolchain = stm32_cube.Toolchain(
                platform="Darwin",
                cubemx="/Applications/STM32CubeMX",
                cubeide=None,
                gcc=None,
                make=None,
                cmake=None,
                ninja=None,
                pypdf="test",
            )

            def create_project(*_args: object) -> object:
                project_dir = output_dir / "demo"
                project_dir.mkdir()
                (project_dir / "Makefile").write_text("all:\n", encoding="utf-8")
                return stm32_cube.subprocess.CompletedProcess([], 0, "")

            with (
                mock.patch.object(
                    stm32_cube,
                    "load_and_validate_profile_snapshot",
                    return_value=(self.board_profile(), profile_snapshot),
                ),
                mock.patch.object(stm32_cube, "config_plan", return_value=configuration),
                mock.patch.object(stm32_cube, "discover_tools", return_value=toolchain),
                mock.patch.object(stm32_cube, "run_cubemx_quiet_script", side_effect=create_project),
                mock.patch.object(stm32_cube, "configuration_verification_failures", return_value=[]),
                mock.patch.object(
                    stm32_cube,
                    "write_project_provenance",
                    return_value=output_dir / "demo" / stm32_cube.PROJECT_PROVENANCE_FILE,
                ) as write_provenance,
            ):
                self.assertEqual(stm32_cube.run_generate(arguments), 0)

        self.assertEqual(
            write_provenance.call_args.args[3],
            hashlib.sha256(profile_snapshot).hexdigest(),
        )

    def test_generation_preflight_uses_concrete_local_cubemx_operation_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "CubeMX" / "Resources"
            executable = root / "STM32CubeMX"
            database = root / "db" / "mcu"
            ip_database = database / "IP"
            ip_database.mkdir(parents=True)
            windows_executable = Path(temporary_directory) / "WindowsCubeMX" / "STM32CubeMX.exe"
            windows_database = windows_executable.parent / "db" / "mcu"
            windows_database.mkdir(parents=True)
            self.assertEqual(stm32_cube.cubemx_database_root(str(windows_executable)), windows_database)
            (database / "STM32F401R(D-E)Tx.xml").write_text(
                '<Mcu RefName="STM32F401R(D-E)Tx">'
                '<IP InstanceName="TIM2" Name="TIM1_8" Version="gptimer2_v2_x_Cube"/>'
                '<Pin Name="PB8"><Signal Name="TIM2_CH1"/></Pin>'
                "</Mcu>",
                encoding="utf-8",
            )
            (ip_database / "TIM1_8-gptimer2_v2_x_Cube_Modes.xml").write_text(
                '<IP><RefParameter Name="Prescaler"/>'
                '<Mode Name="Clock Source">'
                '<Mode Name="Internal" UserName="Internal Clock"/>'
                "</Mode>"
                '<Mode Name="PWM Generation1 CH1" UserName="PWM Generation CH1"/>'
                "</IP>",
                encoding="utf-8",
            )
            configuration = {
                "operations": [
                    {
                        "instance": "TIM2",
                        "mode": "Internal Clock",
                        "pins": [{"pin": "PB8", "signal": "TIM2_CH1"}],
                        "parameters": [{"name": "Prescaler", "value": "83"}],
                    }
                ],
            }

            stm32_cube.validate_operations_against_cubemx_database(
                configuration,
                "STM32F401RETx",
                str(executable),
            )
            self.assertEqual(
                stm32_cube.cubemx_leaf_mode_names(database, "STM32F401RETx", "TIM2"),
                {"Internal", "Internal Clock", "PWM Generation1 CH1", "PWM Generation CH1"},
            )
            self.assertEqual(
                stm32_cube.cubemx_parameter_names(database, "STM32F401RETx", "TIM2"),
                {"Prescaler"},
            )
            configuration["operations"][0]["mode"] = "Base"
            with self.assertRaisesRegex(ValueError, r"operations\[1\]\.mode 'Base'.*concrete CubeMX mode"):
                stm32_cube.validate_operations_against_cubemx_database(
                    configuration,
                    "STM32F401RETx",
                    str(executable),
                )
            configuration["operations"][0]["mode"] = "Internal Clock"
            configuration["operations"][0]["pins"][0]["signal"] = "TIM2_CH2"
            with self.assertRaisesRegex(ValueError, r"operations\[1\]\.pins\[1\].*does not provide"):
                stm32_cube.validate_operations_against_cubemx_database(
                    configuration,
                    "STM32F401RETx",
                    str(executable),
                )
            configuration["operations"][0]["pins"][0]["signal"] = "TIM2_CH1"
            configuration["operations"][0]["parameters"][0]["name"] = "NotATimerParameter"
            with self.assertRaisesRegex(ValueError, r"operations\[1\]\.parameters\[1\]\.name 'NotATimerParameter'.*not declared"):
                stm32_cube.validate_operations_against_cubemx_database(
                    configuration,
                    "STM32F401RETx",
                    str(executable),
                )

    def test_generate_rejects_an_unknown_mode_before_cubemx_runs(self) -> None:
        configuration = {
            "mcu": "STM32F401RETx",
            "plan_sha256": "b" * 64,
            "packs": ["timer"],
            "modules": [],
            "operations": [{"instance": "TIM2", "mode": "Base", "pins": [], "parameters": []}],
            "pin_assignments": [],
            "ioc_overrides": [],
            "verifications": [],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            arguments = stm32_cube.argparse.Namespace(
                name="demo",
                mcu="STM32F401RETx",
                output_dir=str(output_dir),
                board_profile=str(output_dir / "board-profile.json"),
                manual=str(output_dir / "manual.pdf"),
                plan=str(output_dir / "configuration-plan.json"),
                cubemx=None,
                cubeide=None,
                dry_run=False,
            )
            toolchain = stm32_cube.Toolchain(
                platform="Darwin",
                cubemx="/Applications/STM32CubeMX",
                cubeide=None,
                gcc=None,
                make=None,
                cmake=None,
                ninja=None,
                pypdf="test",
            )
            stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(stderr),
                mock.patch.object(
                    stm32_cube,
                    "load_and_validate_profile_snapshot",
                    return_value=(self.board_profile(), b"validated profile"),
                ),
                mock.patch.object(stm32_cube, "config_plan", return_value=configuration),
                mock.patch.object(stm32_cube, "discover_tools", return_value=toolchain),
                mock.patch.object(
                    stm32_cube,
                    "validate_operations_against_cubemx_database",
                    side_effect=ValueError("unknown local mode"),
                ) as validate_operations,
                mock.patch.object(stm32_cube, "run_cubemx_quiet_script") as run_cubemx,
            ):
                self.assertEqual(stm32_cube.run_generate(arguments), 2)

        validate_operations.assert_called_once_with(configuration, "STM32F401RETx", "/Applications/STM32CubeMX")
        run_cubemx.assert_not_called()
        self.assertIn("unknown local mode", stderr.getvalue())

    def test_configuration_plan_emits_only_validated_cube_commands(self) -> None:
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["i2c"],
            "operations": [
                {
                    "pack": "i2c",
                    "instance": "I2C1",
                    "mode": "I2C",
                    "pins": [
                        {"pin": "PB8", "signal": "I2C1_SCL"},
                        {"pin": "PB9", "signal": "I2C1_SDA"},
                    ],
                    "parameters": [
                        {
                            "name": "I2C_Mode",
                            "value": "I2C_Fast",
                            "verification": {
                                "file": "$IOC",
                                "contains": "I2C1.I2C_Mode=I2C_Fast",
                            },
                        },
                        {
                            "name": "ClockSpeed",
                            "value": 400000,
                            "verification": {
                                "file": "Src/main.c",
                                "contains": "hi2c1.Init.ClockSpeed = 400000;",
                            },
                        },
                    ],
                }
            ],
            "verifications": [
                {"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"},
                {"file": "Src/main.c", "contains": "hi2c1.Init.ClockSpeed = 400000;"},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            configuration = stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

        script = stm32_cube.cubemx_script("STM32F401RETx", "demo", Path("/tmp/output"), configuration)
        self.assertIn("set mode I2C1 I2C", script)
        self.assertIn("set pin PB8 I2C1_SCL", script)
        self.assertIn("set ip parameters I2C1 ClockSpeed 400000", script)
        self.assertLess(script.index("set mode I2C1 I2C"), script.index("project generate"))
        self.assertEqual(configuration["pin_assignments"], [])
        self.assertEqual(configuration["packs"], ["i2c"])
        self.assertEqual(configuration["modules"], [])
        self.assertRegex(configuration["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(configuration["ioc_overrides"], [])

    def test_configuration_plan_requires_a_generated_evidence_assertion_for_each_parameter(self) -> None:
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["i2c"],
            "operations": [
                {
                    "pack": "i2c",
                    "instance": "I2C1",
                    "mode": "I2C",
                    "pins": [{"pin": "PB8", "signal": "I2C1_SCL"}],
                    "parameters": [{"name": "ClockSpeed", "value": 400000}],
                }
            ],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"operations\[1\]\.parameters\[1\]\.verification"):
                stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_configuration_plan_requires_i2c_bus_signals_and_a_pwm_output_pin(self) -> None:
        incomplete_i2c_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["i2c"],
            "operations": [
                {
                    "pack": "i2c",
                    "instance": "I2C1",
                    "mode": "I2C",
                    "pins": [
                        {"pin": "PB8", "signal": "I2C1_SCL"},
                        {"pin": "PB9", "signal": "I2C1_SMBA"},
                    ],
                    "parameters": [],
                }
            ],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"}],
        }
        pinless_pwm_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["pwm"],
            "operations": [
                {
                    "pack": "pwm",
                    "instance": "TIM3",
                    "mode": "PWM Generation1 CH1",
                    "pins": [],
                    "parameters": [
                        {
                            "name": "Prescaler",
                            "value": 15,
                            "verification": {"file": "$IOC", "contains": "TIM3.Prescaler=15"},
                        },
                        {
                            "name": "Period",
                            "value": 999,
                            "verification": {"file": "$IOC", "contains": "TIM3.Period=999"},
                        },
                    ],
                    "timing": {
                        "timer_input_hz": 16000000,
                        "target_hz": 1000,
                        "tolerance_ppm": 0,
                        "prescaler_parameter": "Prescaler",
                        "period_parameter": "Period",
                    },
                }
            ],
            "verifications": [{"file": "$IOC", "contains": "TIM3.Prescaler=15"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(incomplete_i2c_plan), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                r"must include required signal\(s\): I2C1_SDA",
            ):
                stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

            plan_path.write_text(json.dumps(pinless_pwm_plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"requires at least 1 planned pin\(s\), but has 0"):
                stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_configuration_plan_requires_a_frequency_contract_for_timer_operations(self) -> None:
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["timer"],
            "operations": [
                {
                    "pack": "timer",
                    "instance": "TIM3",
                    "mode": "Internal Clock",
                    "pins": [],
                    "parameters": [
                        {
                            "name": "Prescaler",
                            "value": 15,
                            "verification": {
                                "file": "$IOC",
                                "contains": "TIM3.Prescaler=15",
                            },
                        },
                        {
                            "name": "Period",
                            "value": 999,
                            "verification": {
                                "file": "$IOC",
                                "contains": "TIM3.Period=999",
                            },
                        },
                    ],
                }
            ],
            "verifications": [{"file": "$IOC", "contains": "TIM3.Prescaler=15"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"operations\[1\]\.timing is required"):
                stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_timer_timing_contract_verifies_generated_clock_and_frequency(self) -> None:
        self.assertEqual(
            stm32_cube.stm32f4_timer_clock_property("STM32F401RETx", "TIM1", "operations[1].timing"),
            "RCC.APB2Freq_Value",
        )
        with self.assertRaisesRegex(ValueError, "STM32F4 TIM instances"):
            stm32_cube.stm32f4_timer_clock_property("STM32G071KBTx", "TIM1", "operations[1].timing")
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["timer"],
            "operations": [
                {
                    "pack": "timer",
                    "instance": "TIM3",
                    "mode": "Internal Clock",
                    "pins": [],
                    "parameters": [
                        {
                            "name": "Prescaler",
                            "value": 15,
                            "verification": {
                                "file": "$IOC",
                                "contains": "TIM3.Prescaler=15",
                            },
                        },
                        {
                            "name": "Period",
                            "value": 999,
                            "verification": {
                                "file": "$IOC",
                                "contains": "TIM3.Period=999",
                            },
                        },
                    ],
                    "timing": {
                        "timer_input_hz": 16000000,
                        "target_hz": 1000,
                        "tolerance_ppm": 0,
                        "prescaler_parameter": "Prescaler",
                        "period_parameter": "Period",
                    },
                }
            ],
            "verifications": [{"file": "$IOC", "contains": "TIM3.Prescaler=15"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            plan_path = root / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            configuration = stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())
            self.assertEqual(
                configuration["operations"][0]["timing"],
                {
                    "timer_input_hz": 16000000,
                    "target_hz": 1000,
                    "tolerance_ppm": 0,
                    "prescaler_parameter": "Prescaler",
                    "period_parameter": "Period",
                    "prescaler": 15,
                    "period": 999,
                    "clock_property": "RCC.APB1Freq_Value",
                },
            )
            ioc_path = root / "demo.ioc"
            ioc_path.write_text(
                "RCC.AHBFreq_Value=16000000\n"
                "RCC.APB1Freq_Value=16000000\n"
                "TIM3.Prescaler=15\n"
                "TIM3.Period=999\n",
                encoding="utf-8",
            )
            self.assertEqual(stm32_cube.configuration_verification_failures(root, configuration), [])

            ioc_path.write_text(
                "RCC.AHBFreq_Value=16000000\n"
                "RCC.APB1Freq_Value=8000000\n"
                "TIM3.Prescaler=15\n"
                "TIM3.Period=999\n",
                encoding="utf-8",
            )
            self.assertEqual(
                stm32_cube.configuration_verification_failures(root, configuration),
                [
                    "operations[1].timing requires an unprescaled STM32F4 APB clock, but "
                    "RCC.APB1Freq_Value=8000000 differs from RCC.AHBFreq_Value=16000000."
                ],
            )

            ioc_path.write_text(
                "RCC.AHBFreq_Value=16000000\n"
                "RCC.APB1Freq_Value=16000000\n"
                "TIM3.Prescaler=15\n"
                "TIM3.Period=999\n",
                encoding="utf-8",
            )
            configuration["operations"][0]["timing"]["prescaler"] = 83
            self.assertEqual(
                stm32_cube.configuration_verification_failures(root, configuration),
                [
                    "operations[1].timing configures 16000000/84000 Hz, which differs from "
                    "target_hz=1000 by 809524 ppm (tolerance_ppm=0)."
                ],
            )

    def test_configuration_plan_rejects_resources_not_owned_by_their_selected_pack(self) -> None:
        operation = {
            "pack": "i2c",
            "instance": "I2C1",
            "mode": "I2C",
            "pins": [
                {"pin": "PB8", "signal": "I2C1_SCL"},
                {"pin": "PB9", "signal": "I2C1_SDA"},
            ],
            "parameters": [],
        }
        operation_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["i2c"],
            "operations": [operation],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"}],
        }
        direct_pin_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["i2c"],
            "pin_assignments": [{"pack": "i2c", "pin": "PB8", "signal": "GPIO_Output"}],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"}],
        }
        cases = [
            (
                {**operation_plan, "packs": ["gpio"], "operations": [{**operation, "pack": "gpio"}]},
                "does not provide peripheral instance I2C1",
            ),
            (
                {**operation_plan, "operations": [{key: value for key, value in operation.items() if key != "pack"}]},
                r"operations\[1\].pack is required",
            ),
            (
                {**operation_plan, "operations": [{**operation, "pack": "gpio"}]},
                r"operations\[1\].pack must be selected in packs",
            ),
            (direct_pin_plan, "does not provide direct pin signal GPIO_Output"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            for plan, message in cases:
                with self.subTest(message=message):
                    plan_path.write_text(json.dumps(plan), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_configuration_plan_allows_only_pack_owned_semantic_ioc_overrides(self) -> None:
        gpio_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["gpio"],
            "pin_assignments": [{"pack": "gpio", "pin": "PB8", "signal": "GPIO_Output"}],
            "ioc_overrides": [
                {"pack": "gpio", "kind": "gpio-initial-state", "key": "PB8.GPIOParameters", "value": "PinState"},
                {"pack": "gpio", "kind": "gpio-initial-state", "key": "PB8.PinState", "value": "GPIO_PIN_SET"},
            ],
            "verifications": [
                {"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"},
                {"file": "$IOC", "contains": "PB8.GPIOParameters=PinState"},
                {"file": "$IOC", "contains": "PB8.PinState=GPIO_PIN_SET"},
            ],
        }
        timer_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["timer"],
            "operations": [
                {
                    "pack": "timer",
                    "instance": "TIM2",
                    "mode": "Internal Clock",
                    "pins": [],
                    "parameters": [
                        {
                            "name": "Prescaler",
                            "value": 15,
                            "verification": {
                                "file": "Src/main.c",
                                "contains": "htim2.Init.Prescaler = 15;",
                            },
                        },
                        {
                            "name": "Period",
                            "value": 999,
                            "verification": {
                                "file": "Src/main.c",
                                "contains": "htim2.Init.Period = 999;",
                            },
                        },
                    ],
                    "timing": {
                        "timer_input_hz": 16000000,
                        "target_hz": 1000,
                        "tolerance_ppm": 0,
                        "prescaler_parameter": "Prescaler",
                        "period_parameter": "Period",
                    },
                }
            ],
            "ioc_overrides": [
                {
                    "pack": "timer",
                    "kind": "timer-nvic-enable",
                    "key": "NVIC.TIM2_IRQn",
                    "value": r"true\:0\:0\:false\:false\:true\:true\:true\:false",
                }
            ],
            "verifications": [
                {
                    "file": "$IOC",
                    "contains": r"NVIC.TIM2_IRQn=true\:0\:0\:false\:false\:true\:true\:true\:false",
                }
            ],
        }
        cases = [
            (
                {**gpio_plan, "schema_version": 1},
                "schema_version must be 5",
            ),
            (
                {
                    **gpio_plan,
                    "ioc_overrides": [
                        {
                            "pack": "gpio",
                            "kind": "gpio-initial-state",
                            "key": "ProjectManager.ProjectName",
                            "value": "unsafe",
                        }
                    ],
                },
                "GPIOParameters or .PinState",
            ),
            (
                {
                    **gpio_plan,
                    "ioc_overrides": [
                        {"pack": "gpio", "kind": "timer-nvic-enable", "key": "NVIC.TIM2_IRQn", "value": "true"}
                    ],
                },
                "not declared by selected pack gpio",
            ),
            (
                {
                    **gpio_plan,
                    "ioc_overrides": [
                        {"pack": "gpio", "kind": "gpio-initial-state", "key": "PB9.GPIOParameters", "value": "PinState"},
                        {"pack": "gpio", "kind": "gpio-initial-state", "key": "PB9.PinState", "value": "GPIO_PIN_SET"},
                    ],
                },
                "assigned to GPIO_Output",
            ),
            (
                {
                    **gpio_plan,
                    "ioc_overrides": [
                        {"pack": "gpio", "kind": "gpio-initial-state", "key": "PB8.PinState", "value": "GPIO_PIN_SET"}
                    ],
                },
                "must declare both GPIOParameters and PinState",
            ),
            (
                {
                    **gpio_plan,
                    "verifications": [{"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"}],
                },
                "requires an exact \\$IOC verification",
            ),
            (
                {
                    **timer_plan,
                    "ioc_overrides": [
                        {"pack": "timer", "kind": "timer-nvic-enable", "key": "NVIC.TIM3_IRQn", "value": "true"}
                    ],
                    "verifications": [{"file": "$IOC", "contains": "NVIC.TIM3_IRQn=true"}],
                },
                "timer instance declared in operations",
            ),
            (
                {
                    "schema_version": 5,
                    "mcu": "STM32F401RETx",
                    "packs": ["pwm", "timer"],
                    "operations": [
                        {
                            "pack": "pwm",
                            "instance": "TIM2",
                            "mode": "Internal Clock",
                            "pins": [{"pin": "PB8", "signal": "TIM2_CH1"}],
                            "parameters": [
                                {
                                    "name": "Prescaler",
                                    "value": 15,
                                    "verification": {
                                        "file": "Src/main.c",
                                        "contains": "htim2.Init.Prescaler = 15;",
                                    },
                                },
                                {
                                    "name": "Period",
                                    "value": 999,
                                    "verification": {
                                        "file": "Src/main.c",
                                        "contains": "htim2.Init.Period = 999;",
                                    },
                                },
                            ],
                            "timing": {
                                "timer_input_hz": 16000000,
                                "target_hz": 1000,
                                "tolerance_ppm": 0,
                                "prescaler_parameter": "Prescaler",
                                "period_parameter": "Period",
                            },
                        }
                    ],
                    "ioc_overrides": [
                        {"pack": "timer", "kind": "timer-nvic-enable", "key": "NVIC.TIM2_IRQn", "value": "true"}
                    ],
                    "verifications": [{"file": "$IOC", "contains": "NVIC.TIM2_IRQn=true"}],
                },
                "must own the timer instance",
            ),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(gpio_plan), encoding="utf-8")
            gpio_configuration = stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())
            self.assertEqual(gpio_configuration["ioc_overrides"], gpio_plan["ioc_overrides"])
            plan_path.write_text(json.dumps(timer_plan), encoding="utf-8")
            timer_configuration = stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())
            self.assertEqual(timer_configuration["ioc_overrides"], timer_plan["ioc_overrides"])

            for plan, message in cases:
                with self.subTest(message=message):
                    plan_path.write_text(json.dumps(plan), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_direct_pin_assignment_emits_no_mode_and_verifies_generated_ioc(self) -> None:
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["gpio"],
            "pin_assignments": [{"pack": "gpio", "pin": "PB8", "signal": "GPIO_Output"}],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            configuration = stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())
            script = stm32_cube.cubemx_script("STM32F401RETx", "demo", Path("/tmp/output"), configuration)
            project_dir = Path(temporary_directory) / "project"
            project_dir.mkdir()
            (project_dir / "demo.ioc").write_text("PB8.Signal=GPIO_Output\n", encoding="utf-8")

            self.assertEqual(stm32_cube.configuration_verification_failures(project_dir, configuration), [])

        self.assertIn("set pin PB8 GPIO_Output", script)
        self.assertNotIn("set mode GPIO", script)
        self.assertEqual(configuration["operations"], [])
        self.assertEqual(configuration["packs"], ["gpio"])

    def test_configuration_plan_declares_exact_pack_module_bindings(self) -> None:
        base_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["gpio"],
            "pin_assignments": [{"pack": "gpio", "pin": "PB8", "signal": "GPIO_Output"}],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"}],
        }
        valid_module = {
            "name": "status_output",
            "pack": "gpio",
            "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"},
        }
        cases = [
            (
                {**valid_module, "pack": "i2c"},
                "pack must be selected in packs",
            ),
            (
                {**valid_module, "bindings": {"GPIO_PORT": "GPIOA"}},
                "missing required template bindings: GPIO_PIN",
            ),
            (
                {
                    **valid_module,
                    "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1", "UNUSED": "GPIO_PIN_SET"},
                },
                "contains names not used by pack gpio: UNUSED",
            ),
            (
                {
                    **valid_module,
                    "bindings": {"MODULE_NAME": "bad", "GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"},
                },
                "derived from name",
            ),
            (
                {
                    **valid_module,
                    "bindings": {"GPIO_PORT": "GPIOA); Error_Handler();", "GPIO_PIN": "GPIO_PIN_1"},
                },
                "GPIO_PORT must start with a letter",
            ),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            valid_plan = {**base_plan, "modules": [valid_module]}
            plan_path.write_text(json.dumps(valid_plan), encoding="utf-8")
            configuration = stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())
            self.assertEqual(configuration["modules"], [valid_module])
            for module, message in cases:
                with self.subTest(module=module):
                    plan_path.write_text(json.dumps({**base_plan, "modules": [module]}), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_configuration_plan_requires_unique_installed_capability_packs(self) -> None:
        base_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "pin_assignments": [{"pack": "gpio", "pin": "PB8", "signal": "GPIO_Output"}],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"}],
        }
        cases = [
            ({}, "packs is required"),
            ({"packs": []}, "packs must contain at least one"),
            ({"packs": ["does_not_exist"]}, "must name an installed, contract-valid capability pack"),
            ({"packs": ["gpio", "gpio"]}, "packs repeats capability pack gpio"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            for patch, message in cases:
                with self.subTest(patch=patch):
                    plan = {**base_plan, **patch}
                    plan_path.write_text(json.dumps(plan), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_direct_pin_assignment_respects_profile_and_duplicate_guards(self) -> None:
        reserved_profile = self.board_profile()
        reserved_profile["pins"][0]["status"] = "reserved"  # type: ignore[index]
        reserved_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["gpio"],
            "pin_assignments": [{"pack": "gpio", "pin": "PB8", "signal": "GPIO_Output"}],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"}],
        }
        duplicate_plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["i2c", "gpio"],
            "operations": [
                {
                    "pack": "i2c",
                    "instance": "I2C1",
                    "mode": "I2C",
                    "pins": [{"pin": "PB8", "signal": "I2C1_SCL"}],
                    "parameters": [],
                }
            ],
            "pin_assignments": [{"pack": "gpio", "pin": "PB8", "signal": "GPIO_Output"}],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            reserved_path = Path(temporary_directory) / "reserved.json"
            reserved_path.write_text(json.dumps(reserved_plan), encoding="utf-8")
            with self.assertRaises(ValueError):
                stm32_cube.config_plan(reserved_path, "STM32F401RETx", reserved_profile)

            duplicate_path = Path(temporary_directory) / "duplicate.json"
            duplicate_path.write_text(json.dumps(duplicate_plan), encoding="utf-8")
            with self.assertRaises(ValueError):
                stm32_cube.config_plan(duplicate_path, "STM32F401RETx", self.board_profile())

    def test_configuration_plan_requires_operation_or_direct_pin_assignment(self) -> None:
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["gpio"],
            "operations": [],
            "pin_assignments": [],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=GPIO_Output"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(ValueError):
                stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_ioc_override_is_restricted_and_applied_to_a_fresh_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            ioc_path = project_dir / "demo.ioc"
            ioc_path.write_text("ProjectManager.ProjectName=demo\nNVIC.TIM2_IRQn=false\n", encoding="utf-8")
            result = stm32_cube.apply_ioc_overrides(
                project_dir,
                [{"key": "NVIC.TIM2_IRQn", "value": r"true\:0\:0\:false\:false\:true\:true\:true\:false"}],
            )

            self.assertEqual(result, ioc_path)
            self.assertIn(r"NVIC.TIM2_IRQn=true\:0\:0\:false\:false\:true\:true\:true\:false", ioc_path.read_text(encoding="utf-8"))
            self.assertEqual(
                stm32_cube.cubemx_config_reload_script(ioc_path),
                'config load "' + str(ioc_path) + '"\nproject generate\nexit\n',
            )

    def test_configuration_plan_rejects_ioc_override_injection(self) -> None:
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["timer"],
            "operations": [
                {
                    "pack": "timer",
                    "instance": "TIM2",
                    "mode": "Internal Clock",
                    "pins": [],
                    "parameters": [
                        {
                            "name": "Prescaler",
                            "value": 15,
                            "verification": {
                                "file": "Src/main.c",
                                "contains": "htim2.Init.Prescaler = 15;",
                            },
                        },
                        {
                            "name": "Period",
                            "value": 999,
                            "verification": {
                                "file": "Src/main.c",
                                "contains": "htim2.Init.Period = 999;",
                            },
                        },
                    ],
                    "timing": {
                        "timer_input_hz": 16000000,
                        "target_hz": 1000,
                        "tolerance_ppm": 0,
                        "prescaler_parameter": "Prescaler",
                        "period_parameter": "Period",
                    },
                }
            ],
            "ioc_overrides": [
                {"pack": "timer", "kind": "timer-nvic-enable", "key": "NVIC.TIM2_IRQn", "value": "true\nexit"}
            ],
            "verifications": [{"file": "$IOC", "contains": "NVIC.TIM2_IRQn=true"}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(ValueError):
                stm32_cube.config_plan(plan_path, "STM32F401RETx", self.board_profile())

    def test_configuration_plan_rejects_board_reserved_pin(self) -> None:
        plan = {
            "schema_version": 5,
            "mcu": "STM32F401RETx",
            "packs": ["i2c"],
            "operations": [
                {
                    "pack": "i2c",
                    "instance": "I2C1",
                    "mode": "I2C",
                    "pins": [{"pin": "PB8", "signal": "I2C1_SCL"}],
                    "parameters": [],
                }
            ],
            "verifications": [{"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"}],
        }
        profile = self.board_profile()
        profile["pins"][0]["status"] = "reserved"  # type: ignore[index]
        with tempfile.TemporaryDirectory() as temporary_directory:
            plan_path = Path(temporary_directory) / "configuration-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(ValueError):
                stm32_cube.config_plan(plan_path, "STM32F401RETx", profile)

    def test_cube_script_quotes_mode_or_parameter_value_with_spaces(self) -> None:
        configuration = {
            "operations": [
                {
                    "instance": "TIM3",
                    "mode": "PWM Generation1 CH1",
                    "pins": [],
                    "parameters": [{"name": "ClockSource", "value": "Internal Clock"}],
                }
            ],
            "pin_assignments": [],
        }
        script = stm32_cube.cubemx_script("STM32F401RETx", "demo", Path("/tmp/output"), configuration)
        self.assertIn('set mode TIM3 "PWM Generation1 CH1"', script)
        self.assertIn('set ip parameters TIM3 ClockSource "Internal Clock"', script)

    def test_configuration_verifies_cube_special_signal_alias(self) -> None:
        configuration = {
            "operations": [
                {"instance": "TIM3", "pins": [{"pin": "PA6", "signal": "TIM3_CH1"}]}
            ],
            "pin_assignments": [],
            "verifications": [],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "demo.ioc").write_text("PA6.Signal=S_TIM3_CH1\n", encoding="utf-8")
            self.assertEqual(stm32_cube.configuration_verification_failures(project_dir, configuration), [])
            (project_dir / "demo.ioc").write_text("PA6.Signal=GPIO_Output\n", encoding="utf-8")
            failures = stm32_cube.configuration_verification_failures(project_dir, configuration)
        self.assertEqual(failures, ["$IOC does not assign PA6 to TIM3_CH1"])

    def test_parameter_bound_verification_is_evaluated_after_generation(self) -> None:
        configuration = {
            "operations": [
                {
                    "instance": "I2C1",
                    "pins": [],
                    "parameters": [
                        {
                            "name": "ClockSpeed",
                            "value": "400000",
                            "verification": {
                                "file": "Src/main.c",
                                "contains": "hi2c1.Init.ClockSpeed = 400000;",
                            },
                        }
                    ],
                }
            ],
            "pin_assignments": [],
            "verifications": [],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "demo.ioc").write_text("", encoding="utf-8")
            source_path = project_dir / "Src" / "main.c"
            source_path.parent.mkdir()
            source_path.write_text("hi2c1.Init.ClockSpeed = 400000;\n", encoding="utf-8")
            self.assertEqual(stm32_cube.configuration_verification_failures(project_dir, configuration), [])
            source_path.write_text("hi2c1.Init.ClockSpeed = 100000;\n", encoding="utf-8")
            failures = stm32_cube.configuration_verification_failures(project_dir, configuration)
        self.assertEqual(failures, ["Src/main.c does not contain 'hi2c1.Init.ClockSpeed = 400000;'"])

    def test_detects_cube_command_rejection_marker(self) -> None:
        self.assertTrue(stm32_cube.cubemx_rejected_commands("set mode TIM3 bad\nKO\n"))
        self.assertFalse(stm32_cube.cubemx_rejected_commands("set mode TIM3 good\nOK\n"))

    def test_project_name_rejects_path_characters(self) -> None:
        with self.assertRaises(ValueError):
            stm32_cube.validated_project_name("../unsafe")

    def test_module_name_rejects_c_identifier_breakers(self) -> None:
        with self.assertRaises(ValueError):
            stm32_cube.validated_module_name("Motor-Control")

    def test_module_command_creates_sources_and_managed_makefile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "Makefile").write_text(
                "C_SOURCES =\n"
                "C_INCLUDES =\n"
                "#######################################\n"
                "# build the application\n",
                encoding="utf-8",
            )
            result = stm32_cube.run_module(
                stm32_cube.argparse.Namespace(project_dir=str(project_dir), name="motor_control")
            )

            self.assertEqual(result, 0)
            self.assertTrue((project_dir / "App" / "Inc" / "motor_control.h").is_file())
            self.assertTrue((project_dir / "App" / "Src" / "motor_control.c").is_file())
            makefile = (project_dir / "Makefile").read_text(encoding="utf-8")
            self.assertIn("include codex-modules.mk", makefile)
            self.assertLess(makefile.index("include codex-modules.mk"), makefile.index("# build the application"))
            self.assertIn("$(wildcard App/Src/*.c)", (project_dir / "codex-modules.mk").read_text(encoding="utf-8"))

    def test_module_refuses_header_created_during_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "Makefile").write_text(
                "C_SOURCES =\n"
                "C_INCLUDES =\n"
                "#######################################\n"
                "# build the application\n",
                encoding="utf-8",
            )
            header_path = project_dir / "App" / "Inc" / "motor_control.h"
            original_header_renderer = stm32_cube.module_header_text

            def create_competing_header(name: str) -> str:
                header_path.parent.mkdir(parents=True, exist_ok=True)
                header_path.write_text("private competing header\n", encoding="utf-8")
                return original_header_renderer(name)

            stderr = io.StringIO()
            with (
                mock.patch.object(stm32_cube, "module_header_text", side_effect=create_competing_header),
                contextlib.redirect_stderr(stderr),
            ):
                result = stm32_cube.run_module(
                    stm32_cube.argparse.Namespace(project_dir=str(project_dir), name="motor_control")
                )

            self.assertEqual(result, 2)
            self.assertEqual(header_path.read_text(encoding="utf-8"), "private competing header\n")
            self.assertIn("refusing to overwrite", stderr.getvalue().lower())

    def test_pack_module_renders_only_from_verified_project_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "Makefile").write_text(
                "#######################################\n# build the application\n", encoding="utf-8"
            )
            main_path = project_dir / "Src" / "main.c"
            main_path.parent.mkdir(parents=True)
            main_path.write_text(
                '#include "main.h"\n'
                '/* USER CODE BEGIN Includes */\n'
                '/* USER CODE END Includes */\n'
                'int main(void)\n{\n'
                '  /* USER CODE BEGIN 2 */\n'
                '  /* USER CODE END 2 */\n'
                '  while (1) {\n'
                '    /* USER CODE BEGIN 3 */\n'
                '    /* USER CODE END 3 */\n'
                '  }\n}\n',
                encoding="utf-8",
            )
            planned_modules = [
                {
                    "name": "status_output",
                    "pack": "gpio",
                    "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"},
                }
            ]
            provenance_path = self.write_project_provenance(project_dir, ["gpio"], planned_modules)
            provenance = stm32_cube.load_project_provenance(project_dir)
            self.assertEqual(provenance["mcu"], "STM32F401RETx")
            self.assertEqual(provenance["packs"], ["gpio"])
            self.assertEqual(provenance["board_profile_sha256"], "c" * 64)
            self.assertIn("GPIOA", provenance["generated_identifiers"])
            self.assertIn("GPIO_PIN_1", provenance["generated_identifiers"])
            self.assertIn("GPIO_PIN_2", provenance["generated_identifiers"])
            self.assertEqual(
                provenance["generator"],
                {
                    "firmware_package": "STM32Cube FW_F4 V1.28.3",
                    "mx_cube_version": "6.18.0",
                    "mx_db_version": "DB.6.0.180",
                },
            )
            self.assertEqual(provenance["modules"], planned_modules)

            self.assertEqual(
                stm32_cube.run_module(
                    stm32_cube.argparse.Namespace(
                        project_dir=str(project_dir),
                        name="status_output",
                        pack="gpio",
                    )
                ),
                0,
            )
            header = (project_dir / "App" / "Inc" / "status_output.h").read_text(encoding="utf-8")
            source = (project_dir / "App" / "Src" / "status_output.c").read_text(encoding="utf-8")
            self.assertIn("GPIO_PinState", header)
            self.assertIn("HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, state);", source)
            self.assertNotIn("{{", header + source)
            self.assertEqual(
                stm32_cube.run_integrate(stm32_cube.argparse.Namespace(project_dir=str(project_dir), name="status_output")),
                0,
            )
            self.assertIn("status_output_init();", main_path.read_text(encoding="utf-8"))
            self.assertEqual(stm32_cube.load_project_provenance(project_dir)["modules"], planned_modules)

            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["packs"][0]["content_sha256"] = "0" * 64
            provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed after this project was generated"):
                stm32_cube.load_project_provenance(project_dir)

    def test_project_provenance_requires_the_exact_board_profile_input_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            provenance_path = self.write_project_provenance(project_dir, ["gpio"])
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            self.assertEqual(provenance["board_profile_sha256"], "c" * 64)

            del provenance["board_profile_sha256"]
            provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"project provenance\.board_profile_sha256 is required"):
                stm32_cube.load_project_provenance(project_dir)

    def test_project_provenance_refuses_output_created_during_recording(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            provenance_path = project_dir / stm32_cube.PROJECT_PROVENANCE_FILE

            def create_competing_provenance(*_args: object) -> dict[str, object]:
                provenance_path.write_text("private competing provenance\n", encoding="utf-8")
                return {"schema_version": stm32_cube.PROJECT_PROVENANCE_SCHEMA_VERSION}

            with mock.patch.object(stm32_cube, "project_provenance_record", side_effect=create_competing_provenance):
                with self.assertRaisesRegex(ValueError, "Refusing to overwrite existing project provenance"):
                    stm32_cube.write_project_provenance(
                        project_dir,
                        {"mcu": "STM32F401RETx"},
                        self.board_profile(),
                        "c" * 64,
                    )

            self.assertEqual(provenance_path.read_text(encoding="utf-8"), "private competing provenance\n")

    def test_pack_module_rejects_unplanned_or_wrong_pack_and_timer_callback_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "Makefile").write_text(
                "#######################################\n# build the application\n", encoding="utf-8"
            )
            self.write_project_provenance(
                project_dir,
                ["gpio"],
                [
                    {
                        "name": "status_output",
                        "pack": "gpio",
                        "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"},
                    }
                ],
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    stm32_cube.run_module(
                        stm32_cube.argparse.Namespace(
                            project_dir=str(project_dir), name="other_output", pack="gpio"
                        )
                    ),
                    2,
                )
            self.assertIn("does not declare pack module other_output", stderr.getvalue())
            with self.assertRaisesRegex(ValueError, "not i2c"):
                stm32_cube.pack_module_text(project_dir, "status_output", "i2c")

            generic_stderr = io.StringIO()
            with contextlib.redirect_stderr(generic_stderr):
                self.assertEqual(
                    stm32_cube.run_module(
                        stm32_cube.argparse.Namespace(project_dir=str(project_dir), name="status_output")
                    ),
                    2,
                )
            self.assertIn("render it with --pack gpio", generic_stderr.getvalue())

            timer_project = project_dir / "timer"
            timer_project.mkdir()
            self.write_project_provenance(
                timer_project,
                ["timer"],
                [
                    {
                        "name": "tick_dispatcher",
                        "pack": "timer",
                        "bindings": {"TIM_HANDLE": "htim2", "IRQ_NAME": "TIM2_IRQn"},
                    }
                ],
            )
            timer_source = timer_project / "Src" / "callbacks.c"
            timer_source.parent.mkdir(exist_ok=True)
            timer_source.write_text(
                "void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim) { (void)htim; }\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "second HAL_TIM_PeriodElapsedCallback"):
                stm32_cube.pack_module_text(timer_project, "tick_dispatcher", "timer")

    def test_project_provenance_rejects_planned_binding_absent_from_generated_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            configuration = {
                "mcu": "STM32F401RETx",
                "plan_sha256": "b" * 64,
                "packs": ["gpio"],
                "modules": [
                    {
                        "name": "status_output",
                        "pack": "gpio",
                        "bindings": {"GPIO_PORT": "GPIOZ", "GPIO_PIN": "GPIO_PIN_1"},
                    }
                ],
            }
            generated_source = project_dir / "Src" / "stm32f4xx_hal_msp.c"
            generated_source.parent.mkdir(parents=True)
            generated_source.write_text(
                "void HAL_MspInit(void) { HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_SET); }\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "verified CubeMX-generated source"):
                stm32_cube.write_project_provenance(
                    project_dir,
                    configuration,
                    self.board_profile(),
                    "c" * 64,
                )

    def test_project_provenance_rejects_source_or_inventory_drift(self) -> None:
        planned_modules = [
            {
                "name": "status_output",
                "pack": "gpio",
                "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"},
            }
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            provenance_path = self.write_project_provenance(project_dir, ["gpio"], planned_modules)
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["generated_identifiers"].append("GPIOZ")
            provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identifier inventory changed after verified generation"):
                stm32_cube.load_project_provenance(project_dir)

            provenance_path.unlink()
            provenance_path = self.write_project_provenance(project_dir, ["gpio"], planned_modules)
            generated_source = project_dir / "Src" / "stm32f4xx_hal_msp.c"
            generated_source.write_text(
                generated_source.read_text(encoding="utf-8") + "\nvoid generated_configuration_change(void) {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "configuration source changed after verified generation"):
                stm32_cube.load_project_provenance(project_dir)

    def test_project_provenance_rejects_ioc_or_generator_fact_drift(self) -> None:
        planned_modules = [
            {
                "name": "status_output",
                "pack": "gpio",
                "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"},
            }
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            provenance_path = self.write_project_provenance(project_dir, ["gpio"], planned_modules)
            ioc_path = self.write_ioc_generation_facts(project_dir)
            ioc_path.write_text(
                ioc_path.read_text(encoding="utf-8") + "PA1.Signal=GPIO_Output\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"CubeMX \.ioc configuration changed after verified generation"):
                stm32_cube.load_project_provenance(project_dir)

            provenance_path.unlink()
            provenance_path = self.write_project_provenance(project_dir, ["gpio"], planned_modules)
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["generator"]["mx_cube_version"] = "9.9.9"
            provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CubeMX generator facts changed after verified generation"):
                stm32_cube.load_project_provenance(project_dir)

    def test_project_provenance_rejects_makefile_and_controlled_module_makefile_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            makefile = project_dir / "Makefile"
            makefile.write_text(
                "C_SOURCES =\n"
                "C_INCLUDES =\n"
                "#######################################\n"
                "# build the application\n",
                encoding="utf-8",
            )
            self.write_project_provenance(project_dir, ["gpio"])
            original_makefile = makefile.read_text(encoding="utf-8")
            makefile.write_text(
                original_makefile + "C_DEFS += -DUNVERIFIED_BUILD_INPUT\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "CubeMX Makefile changed after verified generation"):
                stm32_cube.load_project_provenance(project_dir)

            makefile.write_text(original_makefile, encoding="utf-8")
            stm32_cube.synchronize_module_makefile(project_dir)
            self.assertEqual(stm32_cube.load_project_provenance(project_dir)["packs"], ["gpio"])

            modules_makefile = project_dir / stm32_cube.MODULES_MAKEFILE
            modules_makefile.write_text(
                modules_makefile.read_text(encoding="utf-8") + "# changed\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "Codex module Makefile integration changed after verified generation",
            ):
                stm32_cube.load_project_provenance(project_dir)

    def test_project_provenance_rejects_generated_header_or_linker_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            provenance_path = self.write_project_provenance(project_dir, ["gpio"])
            generated_header = project_dir / "Inc" / "build_input.h"
            generated_header.write_text("#define GENERATED_BUILD_INPUT 2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CubeMX generated build input changed after verified generation"):
                stm32_cube.load_project_provenance(project_dir)

            provenance_path.unlink()
            self.write_project_provenance(project_dir, ["gpio"])
            linker_script = project_dir / "STM32F401xx_FLASH.ld"
            linker_script.write_text(
                linker_script.read_text(encoding="utf-8") + "/* changed */\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "CubeMX generated build input changed after verified generation"):
                stm32_cube.load_project_provenance(project_dir)

    def test_generated_build_input_fingerprint_allows_user_code_and_line_ending_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            self.write_project_provenance(project_dir, ["gpio"])
            generated_source = project_dir / "Src" / "stm32f4xx_hal_msp.c"
            source_text = generated_source.read_text(encoding="utf-8").replace(
                "/* USER CODE BEGIN 0 */\n/* USER CODE END 0 */",
                "/* USER CODE BEGIN 0 */\nvoid user_owned_code(void) {}\n/* USER CODE END 0 */",
            )
            with generated_source.open("w", encoding="utf-8", newline="") as output:
                output.write(source_text.replace("\n", "\r\n"))
            self.assertEqual(stm32_cube.load_project_provenance(project_dir)["packs"], ["gpio"])

    def test_project_provenance_requires_cube_mx_ioc_generation_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            generated_source = project_dir / "Src" / "stm32f4xx_hal_msp.c"
            generated_source.parent.mkdir(parents=True)
            generated_source.write_text(
                "void HAL_MspInit(void) { HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_SET); }\n",
                encoding="utf-8",
            )
            (project_dir / "broken.ioc").write_text("MxCube.Version=6.18.0\n", encoding="utf-8")
            configuration = {
                "mcu": "STM32F401RETx",
                "plan_sha256": "b" * 64,
                "packs": ["gpio"],
                "modules": [],
            }
            with self.assertRaisesRegex(ValueError, "missing required generation facts"):
                stm32_cube.write_project_provenance(
                    project_dir,
                    configuration,
                    self.board_profile(),
                    "c" * 64,
                )

    def test_build_requires_verified_project_provenance_before_make(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            self.write_project_provenance(project_dir, ["gpio"])
            toolchain = stm32_cube.Toolchain(
                platform="Darwin",
                cubemx="/Applications/STM32CubeMX",
                cubeide="/Applications/STM32CubeIDE",
                gcc="/Applications/arm-none-eabi-gcc",
                make="/Applications/make",
                cmake=None,
                ninja=None,
                pypdf="test",
            )
            args = stm32_cube.argparse.Namespace(
                project_dir=str(project_dir),
                jobs=1,
                cubemx=None,
                cubeide=None,
            )
            completed = stm32_cube.subprocess.CompletedProcess(
                args=["make"],
                returncode=0,
                stdout="make completed\n",
            )
            with (
                mock.patch.object(stm32_cube, "discover_tools", return_value=toolchain) as discover_tools,
                mock.patch.object(stm32_cube.subprocess, "run", return_value=completed) as make_run,
            ):
                self.assertEqual(stm32_cube.run_build(args), 0)
            discover_tools.assert_called_once_with(None, None)
            make_run.assert_called_once()

            ioc_path = project_dir / "verified.ioc"
            ioc_path.write_text(
                ioc_path.read_text(encoding="utf-8") + "PA1.Signal=GPIO_Output\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(stderr),
                mock.patch.object(stm32_cube, "discover_tools") as changed_discover_tools,
                mock.patch.object(stm32_cube.subprocess, "run") as changed_make_run,
            ):
                self.assertEqual(stm32_cube.run_build(args), 2)
            self.assertIn("CubeMX .ioc configuration changed after verified generation", stderr.getvalue())
            changed_discover_tools.assert_not_called()
            changed_make_run.assert_not_called()

            provenance_path = project_dir / stm32_cube.PROJECT_PROVENANCE_FILE
            provenance_path.unlink()
            self.write_ioc_generation_facts(project_dir)
            self.write_project_provenance(project_dir, ["gpio"])
            makefile = project_dir / "Makefile"
            makefile.write_text(
                makefile.read_text(encoding="utf-8") + "# unverified build change\n",
                encoding="utf-8",
            )
            makefile_stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(makefile_stderr),
                mock.patch.object(stm32_cube, "discover_tools") as changed_makefile_discover_tools,
                mock.patch.object(stm32_cube.subprocess, "run") as changed_makefile_run,
            ):
                self.assertEqual(stm32_cube.run_build(args), 2)
            self.assertIn("CubeMX Makefile changed after verified generation", makefile_stderr.getvalue())
            changed_makefile_discover_tools.assert_not_called()
            changed_makefile_run.assert_not_called()

            provenance_path = project_dir / stm32_cube.PROJECT_PROVENANCE_FILE
            provenance_path.unlink()
            self.write_project_provenance(project_dir, ["gpio"])
            (project_dir / "Inc" / "build_input.h").write_text(
                "#define GENERATED_BUILD_INPUT 2\n",
                encoding="utf-8",
            )
            build_input_stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(build_input_stderr),
                mock.patch.object(stm32_cube, "discover_tools") as changed_build_input_discover_tools,
                mock.patch.object(stm32_cube.subprocess, "run") as changed_build_input_run,
            ):
                self.assertEqual(stm32_cube.run_build(args), 2)
            self.assertIn("CubeMX generated build input changed after verified generation", build_input_stderr.getvalue())
            changed_build_input_discover_tools.assert_not_called()
            changed_build_input_run.assert_not_called()

    def test_build_rejects_project_without_provenance_before_tool_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            args = stm32_cube.argparse.Namespace(
                project_dir=str(project_dir),
                jobs=1,
                cubemx=None,
                cubeide=None,
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), mock.patch.object(
                stm32_cube,
                "discover_tools",
            ) as discover_tools:
                self.assertEqual(stm32_cube.run_build(args), 2)
            self.assertIn(stm32_cube.PROJECT_PROVENANCE_FILE, stderr.getvalue())
            discover_tools.assert_not_called()

    def test_generated_identifier_inventory_excludes_comments_strings_and_app_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            generated_main = project_dir / "Src" / "main.c"
            generated_main.parent.mkdir(parents=True)
            generated_main.write_text(
                "/* GPIOZ is not a generated binding. */\n"
                'const char *label = "GPIOY";\n'
                "#define GPIOW GPIOA\n"
                "/* USER CODE BEGIN 0 */\n"
                "GPIOV;\n"
                "/* USER CODE END 0 */\n"
                "void MX_GPIO_Init(void)\n"
                "{\n"
                "  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_SET);\n"
                "}\n",
                encoding="utf-8",
            )
            app_source = project_dir / "App" / "Src" / "untrusted.c"
            app_source.parent.mkdir(parents=True)
            app_source.write_text("GPIOX\n", encoding="utf-8")

            identifiers = stm32_cube.generated_identifier_inventory(project_dir)

        self.assertIn("GPIOA", identifiers)
        self.assertIn("GPIO_PIN_1", identifiers)
        self.assertNotIn("GPIOZ", identifiers)
        self.assertNotIn("GPIOY", identifiers)
        self.assertNotIn("GPIOW", identifiers)
        self.assertNotIn("GPIOV", identifiers)
        self.assertNotIn("GPIOX", identifiers)
        self.assertNotIn("define", identifiers)
        self.assertNotIn("void", identifiers)

    def test_pack_module_rejects_provenance_without_frozen_identifier_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / stm32_cube.PROJECT_PROVENANCE_FILE).write_text(
                json.dumps({"schema_version": 1}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "schema_version must be 11"):
                stm32_cube.load_project_provenance(project_dir)

    def test_integrate_only_updates_cubemx_user_regions_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            (project_dir / "Makefile").write_text(
                "#######################################\n# build the application\n", encoding="utf-8"
            )
            main_path = project_dir / "Src" / "main.c"
            main_path.parent.mkdir(parents=True)
            main_path.write_text(
                '#include "main.h"\n'
                '/* USER CODE BEGIN Includes */\n'
                '/* USER CODE END Includes */\n'
                'static void untouched_generated_function(void) {}\n'
                'int main(void)\n{\n'
                '  /* USER CODE BEGIN 2 */\n'
                '  /* USER CODE END 2 */\n'
                '  while (1) {\n'
                '    /* USER CODE BEGIN 3 */\n'
                '    /* USER CODE END 3 */\n'
                '  }\n}\n',
                encoding="utf-8",
            )
            self.assertEqual(
                stm32_cube.run_module(stm32_cube.argparse.Namespace(project_dir=str(project_dir), name="motor_control")),
                0,
            )
            self.assertEqual(
                stm32_cube.run_integrate(stm32_cube.argparse.Namespace(project_dir=str(project_dir), name="motor_control")),
                0,
            )
            first = main_path.read_text(encoding="utf-8")
            self.assertIn('#include "motor_control.h"', first)
            self.assertIn("motor_control_init();", first)
            self.assertIn("motor_control_process();", first)
            self.assertIn("static void untouched_generated_function(void) {}", first)
            self.assertEqual(
                stm32_cube.run_integrate(stm32_cube.argparse.Namespace(project_dir=str(project_dir), name="motor_control")),
                0,
            )
            self.assertEqual(first, main_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
