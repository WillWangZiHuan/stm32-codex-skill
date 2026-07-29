#!/usr/bin/env python3
"""Deterministic command fixture for the Windows PowerShell smoke harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


STATE_ENV = "STM32_SMOKE_CONTRACT_STATE"
EXPECTED_CUBEMX_ENV = "STM32_SMOKE_EXPECTED_CUBEMX"
EXPECTED_CUBEIDE_ENV = "STM32_SMOKE_EXPECTED_CUBEIDE"
EXPECTED_SEQUENCE = ["doctor", "create"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def normalized_path(value: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(value)))


def option_pairs(arguments: list[str], expected: set[str]) -> dict[str, str]:
    require(len(arguments) % 2 == 0, f"Expected option/value pairs, received: {arguments}")
    parsed: dict[str, str] = {}
    for index in range(0, len(arguments), 2):
        option = arguments[index]
        require(option in expected, f"Unexpected option: {option}")
        require(option not in parsed, f"Repeated option: {option}")
        parsed[option] = arguments[index + 1]
    require(set(parsed) == expected, f"Expected options {sorted(expected)}, received {sorted(parsed)}")
    return parsed


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sequence": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(state, dict), "Contract state must be an object.")
    require(isinstance(state.get("sequence"), list), "Contract state sequence must be a list.")
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def parse_root_arguments(arguments: list[str]) -> tuple[dict[str, str], str, list[str]]:
    overrides: dict[str, str] = {}
    index = 0
    while index < len(arguments) and arguments[index] in {"--cubemx", "--cubeide"}:
        option = arguments[index]
        require(index + 1 < len(arguments), f"Missing value for {option}")
        require(option not in overrides, f"Repeated root option: {option}")
        overrides[option] = arguments[index + 1]
        index += 2
    require(index < len(arguments), "Missing STM32 Skill command.")
    return overrides, arguments[index], arguments[index + 1 :]


def validate_tool_overrides(overrides: dict[str, str]) -> None:
    require(set(overrides) == {"--cubemx", "--cubeide"}, "Smoke contract requires both tool overrides.")
    expected_cubemx = os.environ.get(EXPECTED_CUBEMX_ENV)
    expected_cubeide = os.environ.get(EXPECTED_CUBEIDE_ENV)
    require(expected_cubemx is not None, f"Missing {EXPECTED_CUBEMX_ENV}.")
    require(expected_cubeide is not None, f"Missing {EXPECTED_CUBEIDE_ENV}.")
    require(
        normalized_path(overrides["--cubemx"]) == normalized_path(expected_cubemx),
        "CubeMX override changed while PowerShell assembled the command.",
    )
    require(
        normalized_path(overrides["--cubeide"]) == normalized_path(expected_cubeide),
        "CubeIDE override changed while PowerShell assembled the command.",
    )
    require(Path(overrides["--cubemx"]).is_file(), "Contract CubeMX path must be a file.")
    require(Path(overrides["--cubeide"]).is_file(), "Contract CubeIDE path must be a file.")


def create_generated_project(options: dict[str, str], state: dict[str, Any]) -> None:
    for input_option in ("--manual", "--board-profile", "--plan"):
        require(Path(options[input_option]).is_file(), f"Missing generate input: {input_option}")
    output_dir = Path(options["--output-dir"])
    require(output_dir.is_dir(), "PowerShell must create the output directory before generate.")
    project_dir = output_dir / options["--name"]
    require(not project_dir.exists(), "Generate contract requires a fresh project directory.")
    project_dir.mkdir()
    (project_dir / f"{options['--name']}.ioc").write_text(
        f"Mcu.Name={options['--mcu']}\nProjectManager.ProjectName={options['--name']}\n",
        encoding="utf-8",
    )
    core_source = project_dir / "Core" / "Src"
    core_source.mkdir(parents=True)
    (core_source / "main.c").write_text(
        "/* USER CODE BEGIN Includes */\n"
        "/* USER CODE END Includes */\n"
        "int main(void)\n"
        "{\n"
        "  /* USER CODE BEGIN 2 */\n"
        "  /* USER CODE END 2 */\n"
        "  while (1)\n"
        "  {\n"
        "    /* USER CODE BEGIN 3 */\n"
        "    /* USER CODE END 3 */\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    (project_dir / "Makefile").write_text("all:\n\t@echo contract build\n", encoding="utf-8")
    module_name = "planned_module"
    include_dir = project_dir / "App" / "Inc"
    source_dir = project_dir / "App" / "Src"
    include_dir.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    (include_dir / f"{module_name}.h").write_text(
        f"void {module_name}_init(void);\nvoid {module_name}_process(void);\n",
        encoding="utf-8",
    )
    (source_dir / f"{module_name}.c").write_text(
        f'#include "{module_name}.h"\n'
        f"void {module_name}_init(void) {{}}\n"
        f"void {module_name}_process(void) {{}}\n",
        encoding="utf-8",
    )
    main_path = core_source / "main.c"
    main_text = main_path.read_text(encoding="utf-8")
    main_text = main_text.replace(
        "/* USER CODE BEGIN Includes */\n",
        f'/* USER CODE BEGIN Includes */\n#include "{module_name}.h"\n',
    )
    main_text = main_text.replace(
        "  /* USER CODE BEGIN 2 */\n",
        f"  /* USER CODE BEGIN 2 */\n  {module_name}_init();\n",
    )
    main_text = main_text.replace(
        "    /* USER CODE BEGIN 3 */\n",
        f"    /* USER CODE BEGIN 3 */\n    {module_name}_process();\n",
    )
    main_path.write_text(main_text, encoding="utf-8")
    build_dir = project_dir / "build"
    build_dir.mkdir()
    for suffix in (".elf", ".bin", ".hex", ".map"):
        (build_dir / f"{options['--name']}{suffix}").write_bytes(b"contract artifact\n")
    (project_dir / "codex-run-report.json").write_text(
        json.dumps({"command": "create", "status": "passed"}),
        encoding="utf-8",
    )
    state["project_dir"] = str(project_dir)
    state["project_name"] = options["--name"]
    state["module_name"] = module_name


def run_skill_invocation(arguments: list[str]) -> int:
    require(arguments, "Missing stm32_cube.py path.")
    skill_script = Path(arguments[0])
    require(skill_script.name == "stm32_cube.py" and skill_script.is_file(), "Unexpected Skill script path.")
    overrides, command, command_arguments = parse_root_arguments(arguments[1:])
    validate_tool_overrides(overrides)

    state_value = os.environ.get(STATE_ENV)
    require(state_value is not None, f"Missing {STATE_ENV}.")
    state_path = Path(state_value)
    state = load_state(state_path)
    sequence = state["sequence"]
    require(len(sequence) < len(EXPECTED_SEQUENCE), "Smoke harness invoked too many commands.")
    require(command == EXPECTED_SEQUENCE[len(sequence)], f"Expected {EXPECTED_SEQUENCE[len(sequence)]}, received {command}.")

    if command == "doctor":
        require(command_arguments == ["--strict"], "Doctor arguments changed.")
    elif command == "create":
        options = option_pairs(
            command_arguments,
            {"--mcu", "--name", "--output-dir", "--board-profile", "--manual", "--plan", "--jobs"},
        )
        require(options["--jobs"] == "3", "PowerShell must preserve the requested build job count.")
        create_generated_project(options, state)

    sequence.append(command)
    save_state(state_path, state)
    print(f"WINDOWS_SMOKE_CONTRACT_{command.upper()}_PASS")
    return 0


def verify_contract(state_path: Path, project_dir: Path) -> None:
    state = load_state(state_path)
    module_name = state["module_name"]
    require(state["sequence"] == EXPECTED_SEQUENCE, "PowerShell did not execute the complete command sequence.")
    require(normalized_path(project_dir) == normalized_path(state["project_dir"]), "Final project path changed.")
    require(len(list(project_dir.glob("*.ioc"))) == 1, "Generated project must contain one root .ioc file.")
    require((project_dir / "App" / "Inc" / f"{module_name}.h").is_file(), "Final module header is missing.")
    require((project_dir / "App" / "Src" / f"{module_name}.c").is_file(), "Final module source is missing.")
    main_text = (project_dir / "Core" / "Src" / "main.c").read_text(encoding="utf-8")
    require(f'#include "{module_name}.h"' in main_text, "Final main.c include is missing.")
    require(f"{module_name}_init();" in main_text, "Final main.c initialization call is missing.")
    require(f"{module_name}_process();" in main_text, "Final main.c process call is missing.")
    artifacts = sorted(path.suffix for path in (project_dir / "build").iterdir() if path.is_file())
    require(artifacts == [".bin", ".elf", ".hex", ".map"], f"Unexpected artifact set: {artifacts}")
    report = json.loads((project_dir / "codex-run-report.json").read_text(encoding="utf-8"))
    require(report == {"command": "create", "status": "passed"}, "One-shot create report is invalid.")
    print("WINDOWS_SMOKE_ORCHESTRATION_PASS")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--state", required=True)
    verify.add_argument("--project", required=True)
    return root


def main(arguments: list[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
        if raw_arguments and raw_arguments[0] == "verify":
            parsed = parser().parse_args(raw_arguments)
            verify_contract(Path(parsed.state), Path(parsed.project))
            return 0
        return run_skill_invocation(raw_arguments)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Windows smoke contract error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
