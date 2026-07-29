#!/usr/bin/env python3
"""Discover, generate, and build legacy STM32CubeMX Makefile projects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from board_profile import BoardProfileError, load_and_validate_profile_snapshot
from validate_packs import PACK_ID, PACKS_ROOT, PackValidationError, SUPPORTED_IOC_OVERRIDE_KINDS, validate_pack


PROJECT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
MCU_IDENTIFIER = re.compile(r"^[A-Za-z0-9()_-]+$")
MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
PIN_IDENTIFIER = re.compile(r"^P[A-Z][0-9]{1,2}$")
GPIO_INITIAL_STATE_KEY = re.compile(r"^(P[A-Z][0-9]{1,2})\.(GPIOParameters|PinState)$")
NVIC_TIMER_IRQ_KEY = re.compile(r"^NVIC\.([A-Za-z][A-Za-z0-9_]*_IRQn)$")
TIMER_INSTANCE = re.compile(r"^(?:TIM|LPTIM)[0-9]+$")
CUBE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CUBE_TOKEN = re.compile(r"^[A-Za-z0-9_().,:/=+\- ]+$")
RELATIVE_PROJECT_FILE = re.compile(r"^(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+$")
IOC_PROPERTY_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
IOC_PROPERTY_VALUE = re.compile(r"^[A-Za-z0-9_.,:+\\-]+$")
TEMPLATE_TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
TEMPLATE_TOKEN_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
C_IDENTIFIER_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*\b")
C_NONCODE = re.compile(
    r"/\*.*?\*/|//[^\r\n]*|\"(?:\\.|[^\"\\\r\n])*\"|'(?:\\.|[^'\\\r\n])*'",
    re.DOTALL,
)
C_PREPROCESSOR_DIRECTIVE = re.compile(r"^[ \t]*\#[^\r\n]*(?:\\\r?\n[^\r\n]*)*", re.MULTILINE)
USER_CODE_REGION_CONTENT = re.compile(
    r"(?P<begin>/\* USER CODE BEGIN [^\r\n]*?\*/).*?(?P<end>/\* USER CODE END [^\r\n]*?\*/)",
    re.DOTALL,
)
C_KEYWORDS = {
    "auto",
    "break",
    "case",
    "char",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "inline",
    "int",
    "long",
    "register",
    "restrict",
    "return",
    "short",
    "signed",
    "sizeof",
    "static",
    "struct",
    "switch",
    "typedef",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
}
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
TIM_PERIOD_ELAPSED_CALLBACK = re.compile(r"\bvoid\s+HAL_TIM_PeriodElapsedCallback\s*\(")
TIMING_PACK_IDS = frozenset({"pwm", "timer"})
STM32F4_APB1_TIMER_INSTANCES = frozenset(
    {"TIM2", "TIM3", "TIM4", "TIM5", "TIM6", "TIM7", "TIM12", "TIM13", "TIM14"}
)
STM32F4_APB2_TIMER_INSTANCES = frozenset({"TIM1", "TIM8", "TIM9", "TIM10", "TIM11"})
MAX_TIMER_COUNTER_VALUE = 0xFFFF
MAX_TIMING_TOLERANCE_PPM = 100_000

MODULES_MAKEFILE = "codex-modules.mk"
PROJECT_PROVENANCE_FILE = "codex-stm32-project.json"
PROJECT_PROVENANCE_SCHEMA_VERSION = 11
CONFIGURATION_PLAN_SCHEMA_VERSION = 5
MAKEFILE_MARKER_BEGIN = "# >>> CODEX STM32 MODULES BEGIN"
MAKEFILE_MARKER_END = "# <<< CODEX STM32 MODULES END"
IOC_VERIFICATION_FILE = "$IOC"
IOC_GENERATION_FACT_PROPERTIES = {
    "MxCube.Version": "mx_cube_version",
    "MxDb.Version": "mx_db_version",
    "ProjectManager.FirmwarePackage": "firmware_package",
}
CORE_TEMPLATE_BINDINGS = frozenset({"MODULE_NAME", "MODULE_GUARD"})
GENERATED_IDENTIFIER_DIRECTORIES = (
    Path("Src"),
    Path("Inc"),
    Path("Core") / "Src",
    Path("Core") / "Inc",
)
GENERATED_IDENTIFIER_FILE_NAMES = {"main.c", "main.h"}
GENERATED_IDENTIFIER_FILE_SUFFIXES = ("_hal_msp.c", "_it.c", "_it.h")
USER_CODE_BLOCKS = {
    "Includes": "INCLUDES",
    "2": "INIT",
    "3": "PROCESS",
}


@dataclass
class Toolchain:
    platform: str
    cubemx: str | None
    cubeide: str | None
    gcc: str | None
    make: str | None
    cmake: str | None
    ninja: str | None
    pypdf: str | None


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def first_executable(paths: Iterable[Path]) -> Path | None:
    for path in unique_paths(paths):
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def command_path(*names: str) -> Path | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def executable_override(value: str | None, label: str) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.exists():
        raise RuntimeError(f"Set {label} override to an existing executable path: {path}")
    if not path.is_file():
        raise RuntimeError(f"Set {label} override to an executable file: {path}")
    if not os.access(path, os.X_OK):
        raise RuntimeError(f"Set {label} override to a file with execute permission: {path}")
    return path


def plugin_tool(plugin_root: Path | None, plugin_prefix: str, executable: str) -> Path | None:
    if plugin_root is None or not plugin_root.is_dir():
        return None
    candidates = sorted(plugin_root.glob(f"{plugin_prefix}*/tools/bin/{executable}"), reverse=True)
    return first_executable(candidates)


def installed_pypdf_version() -> str | None:
    try:
        import pypdf
    except ImportError:
        return None
    return str(getattr(pypdf, "__version__", "available"))


def macos_candidates() -> tuple[list[Path], list[Path], Path | None]:
    cubemx = [
        Path("/Applications/STMicroelectronics/STM32CubeMX.app/Contents/Resources/STM32CubeMX"),
        Path("/Applications/STMicroelectronics/STM32CubeMX.app/Contents/MacOS/STM32CubeMX"),
    ]
    cubeide = [Path("/Applications/STM32CubeIDE.app/Contents/MacOS/STM32CubeIDE")]
    plugin_root = Path("/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins")
    return cubemx, cubeide, plugin_root


def windows_candidates() -> tuple[list[Path], list[Path], Path | None]:
    program_files = [
        Path(value)
        for value in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"))
        if value
    ]
    cubemx: list[Path] = []
    cubeide: list[Path] = []
    for base in program_files:
        cubemx.extend(
            [
                base / "STMicroelectronics" / "STM32Cube" / "STM32CubeMX" / "STM32CubeMX.exe",
                base / "STMicroelectronics" / "STM32CubeMX" / "STM32CubeMX.exe",
            ]
        )
        cubeide.extend(
            [
                base / "STMicroelectronics" / "STM32CubeIDE" / "STM32CubeIDE" / "stm32cubeide.exe",
                base / "STMicroelectronics" / "STM32CubeIDE" / "stm32cubeide.exe",
            ]
        )
    for root in (Path("C:/ST"), Path("C:/STMicroelectronics")):
        if root.is_dir():
            cubeide.extend(root.glob("STM32CubeIDE_*/STM32CubeIDE/stm32cubeide.exe"))

    ide_executable = first_executable(cubeide)
    plugin_root = ide_executable.parent / "plugins" if ide_executable else None
    return cubemx, cubeide, plugin_root


def discover_tools(cubemx_override: str | None = None, cubeide_override: str | None = None) -> Toolchain:
    host = platform.system()
    if host == "Darwin":
        cubemx_candidates, cubeide_candidates, plugin_root = macos_candidates()
        suffix = ""
    elif host == "Windows":
        cubemx_candidates, cubeide_candidates, plugin_root = windows_candidates()
        suffix = ".exe"
    else:
        raise RuntimeError(f"v0.1 supports macOS and Windows hosts; received: {host}.")

    cubemx = executable_override(cubemx_override, "STM32CubeMX") or first_executable(
        [*cubemx_candidates, *(p for p in [command_path("STM32CubeMX", "STM32CubeMX.exe")] if p)]
    )
    cubeide = executable_override(cubeide_override, "STM32CubeIDE") or first_executable(
        [*cubeide_candidates, *(p for p in [command_path("stm32cubeide", "stm32cubeide.exe")] if p)]
    )

    if cubeide and host == "Darwin":
        plugin_root = cubeide.parents[1] / "Eclipse" / "plugins"
    elif cubeide and host == "Windows":
        plugin_root = cubeide.parent / "plugins"

    gcc = plugin_tool(plugin_root, "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.", f"arm-none-eabi-gcc{suffix}")
    make = plugin_tool(plugin_root, "com.st.stm32cube.ide.mcu.externaltools.make.", f"make{suffix}")
    cmake = plugin_tool(plugin_root, "com.st.stm32cube.ide.mcu.externaltools.cmake.", f"cmake{suffix}")
    ninja = plugin_tool(plugin_root, "com.st.stm32cube.ide.mcu.externaltools.ninja.", f"ninja{suffix}")

    fallback_gcc = command_path(f"arm-none-eabi-gcc{suffix}", "arm-none-eabi-gcc")
    fallback_make = command_path(f"make{suffix}", "make")
    fallback_cmake = command_path(f"cmake{suffix}", "cmake")
    fallback_ninja = command_path(f"ninja{suffix}", "ninja")

    return Toolchain(
        platform=host,
        cubemx=str(cubemx) if cubemx else None,
        cubeide=str(cubeide) if cubeide else None,
        gcc=str(gcc or fallback_gcc) if (gcc or fallback_gcc) else None,
        make=str(make or fallback_make) if (make or fallback_make) else None,
        cmake=str(cmake or fallback_cmake) if (cmake or fallback_cmake) else None,
        ninja=str(ninja or fallback_ninja) if (ninja or fallback_ninja) else None,
        pypdf=installed_pypdf_version(),
    )


def xml_local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def parse_cubemx_xml(path: Path, label: str) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"Could not read {label}: {path}: {error}") from error


def cubemx_database_root(cubemx_executable: str) -> Path:
    executable = Path(cubemx_executable).expanduser()
    candidates = unique_paths(
        (
            executable.parent / "db" / "mcu",
            executable.parent / "resources" / "db" / "mcu",
            executable.parent.parent / "db" / "mcu",
        )
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise ValueError(
        "Could not locate the CubeMX MCU database next to the discovered executable. "
        "Install the complete STM32CubeMX package and select its executable path."
    )


def cubemx_refname_matches_mcu(ref_name: str, mcu: str) -> bool:
    """Match CubeMX RefName ranges such as STM32F401R(D-E)Tx against a concrete MCU."""
    if ref_name == mcu:
        return True
    pattern_parts: list[str] = []
    position = 0
    found_range = False
    for match in re.finditer(r"\(([A-Za-z0-9])-([A-Za-z0-9])\)", ref_name):
        found_range = True
        pattern_parts.append(re.escape(ref_name[position : match.start()]))
        first, last = sorted((ord(match.group(1)), ord(match.group(2))))
        variants = "".join(chr(codepoint) for codepoint in range(first, last + 1))
        pattern_parts.append(f"[{re.escape(variants)}]")
        position = match.end()
    if not found_range:
        return False
    pattern_parts.append(re.escape(ref_name[position:]))
    return re.fullmatch("".join(pattern_parts), mcu) is not None


def cubemx_mcu_description_path(mcu_database: Path, mcu: str) -> Path:
    matches: list[Path] = []
    for candidate in sorted(mcu_database.glob("*.xml")):
        root = parse_cubemx_xml(candidate, "CubeMX MCU description")
        if xml_local_name(root) != "Mcu":
            continue
        ref_name = root.attrib.get("RefName")
        if ref_name and cubemx_refname_matches_mcu(ref_name, mcu):
            matches.append(candidate)
    if len(matches) != 1:
        raise ValueError(
            f"CubeMX MCU database must contain exactly one description for {mcu}; found {len(matches)}."
        )
    return matches[0]


def cubemx_ip_modes_path(
    mcu_database: Path,
    mcu: str,
    instance: str,
    mcu_description: Path | None = None,
) -> Path:
    mcu_description = mcu_description or cubemx_mcu_description_path(mcu_database, mcu)
    mcu_root = parse_cubemx_xml(mcu_description, "CubeMX MCU description")
    matching_ips = [
        element
        for element in mcu_root.iter()
        if xml_local_name(element) == "IP" and element.attrib.get("InstanceName") == instance
    ]
    if len(matching_ips) != 1:
        raise ValueError(
            f"CubeMX MCU description for {mcu} must contain exactly one IP entry for {instance}; "
            f"found {len(matching_ips)}."
        )
    ip = matching_ips[0]
    ip_name = ip.attrib.get("Name")
    ip_version = ip.attrib.get("Version")
    if not ip_name or not ip_version:
        raise ValueError(f"CubeMX MCU description for {mcu} lacks Name or Version for {instance}.")
    return mcu_database / "IP" / f"{ip_name}-{ip_version}_Modes.xml"


def cubemx_leaf_mode_names(
    mcu_database: Path,
    mcu: str,
    instance: str,
    mcu_description: Path | None = None,
) -> set[str]:
    modes_path = cubemx_ip_modes_path(mcu_database, mcu, instance, mcu_description)
    modes_root = parse_cubemx_xml(modes_path, f"CubeMX mode database for {instance}")
    names: set[str] = set()
    for element in modes_root.iter():
        if xml_local_name(element) != "Mode":
            continue
        if any(xml_local_name(child) == "Mode" for child in element):
            continue
        for attribute in ("Name", "UserName"):
            value = element.attrib.get(attribute, "").strip()
            if value:
                names.add(value)
    if not names:
        raise ValueError(f"CubeMX mode database for {instance} contains no concrete leaf modes.")
    return names


def cubemx_parameter_names(
    mcu_database: Path,
    mcu: str,
    instance: str,
    mcu_description: Path | None = None,
) -> set[str]:
    """Return all parameter keys declared by this installed IP's mode database."""
    modes_path = cubemx_ip_modes_path(mcu_database, mcu, instance, mcu_description)
    modes_root = parse_cubemx_xml(modes_path, f"CubeMX mode database for {instance}")
    names = {
        element.attrib["Name"].strip()
        for element in modes_root.iter()
        if xml_local_name(element) in {"RefParameter", "Parameter"} and element.attrib.get("Name", "").strip()
    }
    if not names:
        raise ValueError(f"CubeMX mode database for {instance} contains no parameter declarations.")
    return names


def validate_operation_modes_against_cubemx_database(
    configuration: dict[str, Any],
    mcu: str,
    cubemx_executable: str,
    *,
    mcu_database: Path | None = None,
    mcu_description: Path | None = None,
) -> None:
    """Validate each operation mode against the local CubeMX database."""
    if not configuration["operations"]:
        return
    database = mcu_database or cubemx_database_root(cubemx_executable)
    mcu_description = mcu_description or cubemx_mcu_description_path(database, mcu)
    names_by_instance: dict[str, set[str]] = {}
    for operation_index, operation in enumerate(configuration["operations"], start=1):
        instance = operation["instance"]
        if instance not in names_by_instance:
            names_by_instance[instance] = cubemx_leaf_mode_names(
                database,
                mcu,
                instance,
                mcu_description,
            )
        known_modes = names_by_instance[instance]
        if operation["mode"] not in known_modes:
            raise ValueError(
                f"operations[{operation_index}].mode {operation['mode']!r} requires a concrete CubeMX mode "
                f"for {instance} on {mcu}. Use an exact leaf Name or UserName from the local CubeMX XML."
            )


def validate_operation_parameters_against_cubemx_database(
    configuration: dict[str, Any],
    mcu: str,
    cubemx_executable: str,
    *,
    mcu_database: Path | None = None,
    mcu_description: Path | None = None,
) -> None:
    """Validate operation parameter keys against the selected IP database."""
    if not configuration["operations"]:
        return
    database = mcu_database or cubemx_database_root(cubemx_executable)
    description = mcu_description or cubemx_mcu_description_path(database, mcu)
    names_by_instance: dict[str, set[str]] = {}
    for operation_index, operation in enumerate(configuration["operations"], start=1):
        instance = operation["instance"]
        if instance not in names_by_instance:
            names_by_instance[instance] = cubemx_parameter_names(
                database,
                mcu,
                instance,
                description,
            )
        known_parameters = names_by_instance[instance]
        for parameter_index, parameter in enumerate(operation.get("parameters", []), start=1):
            if parameter["name"] not in known_parameters:
                raise ValueError(
                    f"operations[{operation_index}].parameters[{parameter_index}].name {parameter['name']!r} "
                    f"is not declared by the local CubeMX mode database for {instance} on {mcu}."
                )


def cubemx_pin_signals(mcu_description: Path) -> dict[str, set[str]]:
    root = parse_cubemx_xml(mcu_description, "CubeMX MCU description")
    pin_signals: dict[str, set[str]] = {}
    for element in root.iter():
        if xml_local_name(element) != "Pin":
            continue
        physical_name = element.attrib.get("Name", "").split("-", 1)[0]
        if not PIN_IDENTIFIER.fullmatch(physical_name):
            continue
        signals = {
            child.attrib["Name"]
            for child in element
            if xml_local_name(child) == "Signal" and child.attrib.get("Name")
        }
        if signals:
            pin_signals.setdefault(physical_name, set()).update(signals)
    return pin_signals


def validate_operation_pins_against_cubemx_database(
    configuration: dict[str, Any],
    mcu: str,
    cubemx_executable: str,
    *,
    mcu_database: Path | None = None,
    mcu_description: Path | None = None,
) -> None:
    """Validate operation pin and signal pairs against the selected MCU."""
    if not configuration["operations"]:
        return
    database = mcu_database or cubemx_database_root(cubemx_executable)
    description = mcu_description or cubemx_mcu_description_path(database, mcu)
    pin_signals = cubemx_pin_signals(description)
    for operation_index, operation in enumerate(configuration["operations"], start=1):
        for pin_index, assignment in enumerate(operation["pins"], start=1):
            pin = assignment["pin"]
            signal = assignment["signal"]
            available_signals = pin_signals.get(pin)
            if available_signals is None:
                raise ValueError(
                    f"operations[{operation_index}].pins[{pin_index}].pin {pin} must name an MCU I/O pin on {mcu}."
                )
            if signal not in available_signals:
                raise ValueError(
                    f"operations[{operation_index}].pins[{pin_index}] assigns {pin} to {signal}; "
                    f"choose a signal listed for this pin in the local CubeMX MCU description for {mcu}."
                )


def validate_operations_against_cubemx_database(
    configuration: dict[str, Any],
    mcu: str,
    cubemx_executable: str,
) -> None:
    """Validate local CubeMX operation facts before it can create a project."""
    if not configuration["operations"]:
        return
    database = cubemx_database_root(cubemx_executable)
    mcu_description = cubemx_mcu_description_path(database, mcu)
    validate_operation_modes_against_cubemx_database(
        configuration,
        mcu,
        cubemx_executable,
        mcu_database=database,
        mcu_description=mcu_description,
    )
    validate_operation_pins_against_cubemx_database(
        configuration,
        mcu,
        cubemx_executable,
        mcu_database=database,
        mcu_description=mcu_description,
    )
    validate_operation_parameters_against_cubemx_database(
        configuration,
        mcu,
        cubemx_executable,
        mcu_database=database,
        mcu_description=mcu_description,
    )


def report_tools(toolchain: Toolchain, as_json: bool, strict: bool) -> int:
    required = {
        "cubemx": toolchain.cubemx,
        "gcc": toolchain.gcc,
        "make": toolchain.make,
        "pypdf": toolchain.pypdf,
    }
    if as_json:
        print(json.dumps(asdict(toolchain), indent=2, sort_keys=True))
    else:
        print(f"Host: {toolchain.platform}")
        for label, value in asdict(toolchain).items():
            if label == "platform":
                continue
            print(f"{label}: {value or 'MISSING'}")
    missing = [name for name, value in required.items() if not value]
    if missing:
        message = f"Missing required dependency/dependencies: {', '.join(missing)}"
        print(message, file=sys.stderr)
        return 2 if strict else 0
    return 0


def build_environment(toolchain: Toolchain) -> dict[str, str]:
    env = os.environ.copy()
    tool_dirs = [
        Path(value).parent
        for value in (toolchain.gcc, toolchain.make, toolchain.cmake, toolchain.ninja)
        if value
    ]
    ordered_dirs: list[str] = []
    for directory in tool_dirs:
        directory_text = str(directory)
        if directory_text not in ordered_dirs:
            ordered_dirs.append(directory_text)
    if ordered_dirs:
        env["PATH"] = os.pathsep.join([*ordered_dirs, env.get("PATH", "")])
    return env


def validated_project_name(name: str) -> str:
    if not PROJECT_NAME.fullmatch(name):
        raise ValueError("Use a project name that starts with a letter and contains letters, numbers, underscores, or hyphens.")
    return name


def validated_mcu_identifier(mcu: str) -> str:
    if not MCU_IDENTIFIER.fullmatch(mcu):
        raise ValueError("Use an MCU identifier containing letters, numbers, parentheses, underscores, and hyphens.")
    return mcu


def validated_module_name(name: str) -> str:
    if not MODULE_NAME.fullmatch(name):
        raise ValueError("Use a module name that starts with a lowercase letter and contains lowercase letters, numbers, or underscores.")
    return name


def cube_quote(value: Path | str) -> str:
    text = str(value)
    if '"' in text or "\n" in text or "\r" in text:
        raise ValueError("Use a CubeMX path free of quotes and line breaks.")
    return f'"{text}"'


def cube_script_value(value: str) -> str:
    return cube_quote(value) if " " in value else value


def plan_required(container: dict[str, Any], key: str, label: str) -> Any:
    if key not in container:
        raise ValueError(f"{label} is required.")
    return container[key]


def plan_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def plan_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    return value


def plan_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be a non-empty string.")
    return value


def cube_plan_token(value: Any, label: str) -> str:
    text = plan_string(value, label)
    if not CUBE_TOKEN.fullmatch(text):
        raise ValueError(f"{label} contains unsupported CubeMX script characters.")
    return text


def cube_plan_identifier(value: Any, label: str) -> str:
    text = plan_string(value, label)
    if not CUBE_IDENTIFIER.fullmatch(text):
        raise ValueError(f"Use {label} with a leading letter and letters, numbers, or underscores.")
    return text


def generated_c_identifier(value: Any, label: str) -> str:
    identifier = cube_plan_identifier(value, label)
    if identifier in C_KEYWORDS:
        raise ValueError(f"Choose a {label} that differs from a C keyword.")
    return identifier


def normalized_parameter_value(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{label} must be a string or integer.")
    return cube_plan_token(str(value), label)


def positive_plan_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def nonnegative_plan_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer.")
    return value


def stm32f4_timer_clock_property(mcu: str, instance: str, label: str) -> str:
    if not mcu.upper().startswith("STM32F4"):
        raise ValueError(
            f"{label} frequency proof currently covers STM32F4 TIM instances with an unprescaled APB clock."
        )
    if instance in STM32F4_APB1_TIMER_INSTANCES:
        return "RCC.APB1Freq_Value"
    if instance in STM32F4_APB2_TIMER_INSTANCES:
        return "RCC.APB2Freq_Value"
    raise ValueError(
        f"{label} frequency proof currently covers STM32F4 TIM1-TIM14; select one of those instances."
    )


def normalized_timer_timing(
    raw_timing: Any,
    label: str,
    mcu: str,
    instance: str,
    parameters: list[dict[str, Any]],
) -> dict[str, Any]:
    timing = plan_object(raw_timing, label)
    timer_input_hz = positive_plan_integer(
        plan_required(timing, "timer_input_hz", f"{label}.timer_input_hz"),
        f"{label}.timer_input_hz",
    )
    target_hz = positive_plan_integer(
        plan_required(timing, "target_hz", f"{label}.target_hz"),
        f"{label}.target_hz",
    )
    tolerance_ppm = nonnegative_plan_integer(
        plan_required(timing, "tolerance_ppm", f"{label}.tolerance_ppm"),
        f"{label}.tolerance_ppm",
    )
    if tolerance_ppm > MAX_TIMING_TOLERANCE_PPM:
        raise ValueError(
            f"Use {label}.tolerance_ppm at or below {MAX_TIMING_TOLERANCE_PPM}; "
            "choose an exactly representable rate or a tighter tolerance."
        )
    prescaler_parameter = cube_plan_identifier(
        plan_required(timing, "prescaler_parameter", f"{label}.prescaler_parameter"),
        f"{label}.prescaler_parameter",
    )
    period_parameter = cube_plan_identifier(
        plan_required(timing, "period_parameter", f"{label}.period_parameter"),
        f"{label}.period_parameter",
    )
    if prescaler_parameter == period_parameter:
        raise ValueError(f"{label} must name distinct prescaler_parameter and period_parameter values.")

    parameter_values = {parameter["name"]: parameter["value"] for parameter in parameters}
    counters: dict[str, int] = {}
    for field_name, parameter_name in (
        ("prescaler_parameter", prescaler_parameter),
        ("period_parameter", period_parameter),
    ):
        value = parameter_values.get(parameter_name)
        if value is None:
            raise ValueError(f"{label}.{field_name} must name a parameter declared by this operation.")
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
            raise ValueError(
                f"{label}.{field_name} ({parameter_name}) must use a non-negative decimal parameter value."
            )
        counter_value = int(value)
        if counter_value > MAX_TIMER_COUNTER_VALUE:
            raise ValueError(
                f"Use {label}.{field_name} ({parameter_name}) at or below "
                f"{MAX_TIMER_COUNTER_VALUE}; the frequency model uses 16-bit counter values."
            )
        counters[field_name] = counter_value

    return {
        "timer_input_hz": timer_input_hz,
        "target_hz": target_hz,
        "tolerance_ppm": tolerance_ppm,
        "prescaler_parameter": prescaler_parameter,
        "period_parameter": period_parameter,
        "prescaler": counters["prescaler_parameter"],
        "period": counters["period_parameter"],
        "clock_property": stm32f4_timer_clock_property(mcu, instance, label),
    }


def normalized_ioc_property_value(value: Any, label: str) -> str:
    text = plan_string(value, label)
    if not IOC_PROPERTY_VALUE.fullmatch(text):
        raise ValueError(f"{label} contains unsupported .ioc property characters.")
    return text


def selected_capability_packs(plan: dict[str, Any]) -> list[str]:
    raw_packs = plan_list(plan_required(plan, "packs", "packs"), "packs")
    if not raw_packs:
        raise ValueError("packs must contain at least one selected capability pack.")

    selected: list[str] = []
    seen: set[str] = set()
    for pack_index, raw_pack_id in enumerate(raw_packs, start=1):
        pack_id = plan_string(raw_pack_id, f"packs[{pack_index}]")
        if not PACK_ID.fullmatch(pack_id):
            raise ValueError(f"packs[{pack_index}] must be a lowercase capability-pack identifier.")
        if pack_id in seen:
            raise ValueError(f"packs repeats capability pack {pack_id}.")
        try:
            validate_pack(PACKS_ROOT / pack_id)
        except PackValidationError as error:
            raise ValueError(
                f"packs[{pack_index}] must name an installed, contract-valid capability pack: {error}"
            ) from error
        seen.add(pack_id)
        selected.append(pack_id)
    return selected


def selected_pack_manifests(selected_packs: list[str]) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for pack_id in selected_packs:
        try:
            manifest = validate_pack(PACKS_ROOT / pack_id)
        except PackValidationError as error:
            raise ValueError(f"Capability pack {pack_id} is not available as a valid local contract: {error}") from error
        manifests[pack_id] = manifest
    return manifests


def resource_pack_id(
    resource: dict[str, Any],
    label: str,
    pack_manifests: dict[str, dict[str, Any]],
) -> str:
    pack_id = plan_string(plan_required(resource, "pack", f"{label}.pack"), f"{label}.pack")
    if not PACK_ID.fullmatch(pack_id):
        raise ValueError(f"{label}.pack must be a lowercase capability-pack identifier.")
    if pack_id not in pack_manifests:
        raise ValueError(f"{label}.pack must be selected in packs.")
    return pack_id


def require_pack_operation_instance(
    pack_id: str,
    instance: str,
    label: str,
    pack_manifests: dict[str, dict[str, Any]],
) -> None:
    prefixes = pack_manifests[pack_id]["plan_resources"]["operation_instance_prefixes"]
    if not any(instance.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"{label} requires a peripheral instance prefix declared by pack {pack_id}; received {instance}.")


def require_pack_operation_pin_contract(
    pack_id: str,
    instance: str,
    pins: list[dict[str, str]],
    label: str,
    pack_manifests: dict[str, dict[str, Any]],
) -> None:
    resources = pack_manifests[pack_id]["plan_resources"]
    minimum_pins = resources["minimum_operation_pins"]
    if len(pins) < minimum_pins:
        raise ValueError(
            f"{label} for pack {pack_id} requires at least {minimum_pins} planned pin(s), "
            f"but has {len(pins)}."
        )
    planned_signals = {pin["signal"] for pin in pins}
    required_signals = [
        f"{instance}_{suffix}" for suffix in resources["required_operation_signal_suffixes"]
    ]
    missing_signals = [signal for signal in required_signals if signal not in planned_signals]
    if missing_signals:
        raise ValueError(
            f"{label} for pack {pack_id} must include required signal(s): {', '.join(missing_signals)}."
        )


def require_pack_direct_pin_signal(
    pack_id: str,
    signal: str,
    label: str,
    pack_manifests: dict[str, dict[str, Any]],
) -> None:
    allowed_signals = pack_manifests[pack_id]["plan_resources"]["direct_pin_signals"]
    if signal not in allowed_signals:
        raise ValueError(f"{label} requires a direct pin signal declared by pack {pack_id}; received {signal}.")


def normalized_ioc_overrides(
    raw_overrides: list[Any],
    pack_manifests: dict[str, dict[str, Any]],
    operations: list[dict[str, Any]],
    pin_assignments: list[dict[str, str]],
) -> list[dict[str, str]]:
    gpio_output_packs = {
        assignment["pin"]: assignment["pack"]
        for assignment in pin_assignments
        if assignment["signal"] == "GPIO_Output"
    }
    timer_instance_packs = {
        operation["instance"]: operation["pack"]
        for operation in operations
        if TIMER_INSTANCE.fullmatch(operation["instance"])
    }
    normalized: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    gpio_properties: dict[str, set[str]] = {}

    for override_index, raw_override in enumerate(raw_overrides, start=1):
        label = f"ioc_overrides[{override_index}]"
        override = plan_object(raw_override, label)
        pack_id = resource_pack_id(override, label, pack_manifests)
        kind = plan_string(plan_required(override, "kind", f"{label}.kind"), f"{label}.kind")
        if kind not in SUPPORTED_IOC_OVERRIDE_KINDS:
            raise ValueError(f"Choose a supported semantic .ioc override kind for {label}; received {kind}.")
        if kind not in pack_manifests[pack_id]["ioc_override_kinds"]:
            raise ValueError(
                f"{label}.kind ({kind}) is not declared by selected pack {pack_id}."
            )
        key = plan_string(plan_required(override, "key", f"{label}.key"), f"{label}.key")
        if not IOC_PROPERTY_KEY.fullmatch(key):
            raise ValueError(f"{label}.key contains unsupported .ioc property characters.")
        if key in seen_keys:
            raise ValueError(f"ioc_overrides repeats property {key}.")
        seen_keys.add(key)
        value = normalized_ioc_property_value(
            plan_required(override, "value", f"{label}.value"),
            f"{label}.value",
        )

        if kind == "gpio-initial-state":
            match = GPIO_INITIAL_STATE_KEY.fullmatch(key)
            if not match:
                raise ValueError(
                    f"{label}.key must be <planned GPIO output pin>.GPIOParameters or .PinState."
                )
            pin, property_name = match.groups()
            if pin not in gpio_output_packs:
                raise ValueError(
                    f"{label}.key must reference a pin assigned to GPIO_Output in this configuration plan."
                )
            if gpio_output_packs[pin] != pack_id:
                raise ValueError(f"{label}.pack must own the matching GPIO_Output pin {pin}.")
            expected_value = "PinState" if property_name == "GPIOParameters" else None
            if expected_value and value != expected_value:
                raise ValueError(f"{label}.value for {key} must be {expected_value}.")
            if property_name == "PinState" and value not in {"GPIO_PIN_SET", "GPIO_PIN_RESET"}:
                raise ValueError(f"{label}.value for {key} must be GPIO_PIN_SET or GPIO_PIN_RESET.")
            gpio_properties.setdefault(pin, set()).add(property_name)
        elif kind == "timer-nvic-enable":
            match = NVIC_TIMER_IRQ_KEY.fullmatch(key)
            if not match:
                raise ValueError(f"{label}.key must be an NVIC.<timer IRQ> property ending in _IRQn.")
            irq_segments = match.group(1).removesuffix("_IRQn").split("_")
            matching_instances = [instance for instance in irq_segments if instance in timer_instance_packs]
            if not matching_instances:
                raise ValueError(
                    f"{label}.key must name an IRQ for a timer instance declared in operations."
                )
            if not any(timer_instance_packs[instance] == pack_id for instance in matching_instances):
                raise ValueError(f"{label}.pack must own the timer instance named by {label}.key.")
            value_parts = value.split(r"\:")
            if value_parts[0] != "true" or any(
                not part or not re.fullmatch(r"(?:true|false|[0-9]+)", part) for part in value_parts[1:]
            ):
                raise ValueError(
                    f"Set {label}.value to true followed by local scalar fields for the NVIC entry."
                )
        else:
            raise AssertionError(f"Unhandled supported .ioc override kind: {kind}")

        normalized.append({"pack": pack_id, "kind": kind, "key": key, "value": value})

    for pin, properties in gpio_properties.items():
        missing = {"GPIOParameters", "PinState"} - properties
        if missing:
            raise ValueError(
                f"gpio-initial-state overrides for {pin} must declare both GPIOParameters and PinState; "
                f"missing {', '.join(sorted(missing))}."
            )
    return normalized


def require_ioc_override_verifications(
    overrides: list[dict[str, str]],
    verifications: list[dict[str, str]],
) -> None:
    ioc_assertions = {
        verification["contains"] for verification in verifications if verification["file"] == IOC_VERIFICATION_FILE
    }
    for override_index, override in enumerate(overrides, start=1):
        expected = f"{override['key']}={override['value']}"
        if expected not in ioc_assertions:
            raise ValueError(
                f"ioc_overrides[{override_index}] requires an exact $IOC verification containing {expected!r}."
            )


def template_external_binding_names(pack_id: str) -> set[str]:
    """Return the non-derived placeholders declared by one installed pack."""
    header_template, source_template = module_template_paths(pack_id)
    header_tokens = template_tokens(header_template.read_text(encoding="utf-8"), header_template)
    source_tokens = template_tokens(source_template.read_text(encoding="utf-8"), source_template)
    return (header_tokens | source_tokens) - CORE_TEMPLATE_BINDINGS


def normalized_planned_modules(
    raw_modules: list[Any],
    selected_packs: list[str],
    label: str,
    generated_identifiers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate plan-declared pack module bindings before and after generation."""
    selected_pack_set = set(selected_packs)
    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for module_index, raw_module in enumerate(raw_modules, start=1):
        module_label = f"{label}[{module_index}]"
        module = plan_object(raw_module, module_label)
        name = validated_module_name(
            plan_string(plan_required(module, "name", f"{module_label}.name"), f"{module_label}.name")
        )
        if name in seen_names:
            raise ValueError(f"{label} repeats module {name}.")
        seen_names.add(name)
        pack_id = plan_string(plan_required(module, "pack", f"{module_label}.pack"), f"{module_label}.pack")
        if not PACK_ID.fullmatch(pack_id):
            raise ValueError(f"{module_label}.pack must be a lowercase capability-pack identifier.")
        if pack_id not in selected_pack_set:
            raise ValueError(f"{module_label}.pack must be selected in packs.")

        expected_bindings = template_external_binding_names(pack_id)
        raw_bindings = plan_object(
            plan_required(module, "bindings", f"{module_label}.bindings"),
            f"{module_label}.bindings",
        )
        bindings: dict[str, str] = {}
        for raw_key, raw_value in raw_bindings.items():
            if not isinstance(raw_key, str) or not TEMPLATE_TOKEN_NAME.fullmatch(raw_key):
                raise ValueError(f"{module_label}.bindings names must use uppercase letters, numbers, or underscores.")
            if raw_key in CORE_TEMPLATE_BINDINGS:
                raise ValueError(f"{module_label}.bindings.{raw_key} derives from name and is added by the renderer.")
            identifier = generated_c_identifier(raw_value, f"{module_label}.bindings.{raw_key}")
            if generated_identifiers is not None and identifier not in generated_identifiers:
                raise ValueError(
                    f"{module_label}.bindings.{raw_key} must reference an identifier recorded from this project's "
                    "verified CubeMX-generated source."
                )
            bindings[raw_key] = identifier

        missing = sorted(expected_bindings - bindings.keys())
        if missing:
            raise ValueError(f"{module_label}.bindings is missing required template bindings: {', '.join(missing)}")
        unexpected = sorted(bindings.keys() - expected_bindings)
        if unexpected:
            raise ValueError(
                f"{module_label}.bindings contains names not used by pack {pack_id}: {', '.join(unexpected)}"
            )
        normalized.append({"name": name, "pack": pack_id, "bindings": bindings})
    return normalized


def pack_contract_fingerprint(pack_id: str) -> str:
    if not PACK_ID.fullmatch(pack_id):
        raise ValueError(f"Use a valid capability-pack identifier; received {pack_id!r}.")
    pack_dir = PACKS_ROOT / pack_id
    try:
        manifest = validate_pack(pack_dir)
        relative_paths = [Path("manifest.json"), Path("PACK.md"), *(Path(value) for value in manifest["templates"])]
        digest = hashlib.sha256()
        for relative_path in sorted(relative_paths, key=lambda path: path.as_posix()):
            digest.update(relative_path.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update((pack_dir / relative_path).read_bytes())
            digest.update(b"\0")
    except (OSError, PackValidationError) as error:
        raise ValueError(f"Capability pack {pack_id} is not available as a valid local contract: {error}") from error
    return digest.hexdigest()


def generated_identifier_source_files(project_dir: Path) -> list[Path]:
    source_files: set[Path] = set()
    for relative_directory in GENERATED_IDENTIFIER_DIRECTORIES:
        directory = project_dir / relative_directory
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if not path.is_file():
                continue
            if path.name in GENERATED_IDENTIFIER_FILE_NAMES or path.name.endswith(GENERATED_IDENTIFIER_FILE_SUFFIXES):
                source_files.add(path)
    return sorted(source_files, key=lambda path: path.relative_to(project_dir).as_posix())


def configuration_bearing_source_text(source_text: str) -> str:
    """Discard user-owned CubeMX regions before recording generated-code facts."""
    return USER_CODE_REGION_CONTENT.sub(
        lambda match: f"{match.group('begin')}\n{match.group('end')}",
        source_text,
    )


def read_generated_configuration_source(source_path: Path) -> str:
    try:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise ValueError(f"Could not read CubeMX configuration source/header: {source_path}: {error}") from error
    return configuration_bearing_source_text(source_text)


def generated_identifier_inventory(project_dir: Path) -> list[str]:
    source_files = generated_identifier_source_files(project_dir)
    if not source_files:
        raise ValueError(
            "Verified project has no CubeMX configuration source/header files from which to record template bindings."
        )
    identifiers: set[str] = set()
    for source_path in source_files:
        source_text = read_generated_configuration_source(source_path)
        code_only = C_PREPROCESSOR_DIRECTIVE.sub(" ", C_NONCODE.sub(" ", source_text))
        identifiers.update(identifier for identifier in C_IDENTIFIER_TOKEN.findall(code_only) if identifier not in C_KEYWORDS)
    if not identifiers:
        raise ValueError("CubeMX configuration source/header files did not contain any C identifiers.")
    return sorted(identifiers)


def generated_configuration_source_fingerprint(project_dir: Path) -> str:
    source_files = generated_identifier_source_files(project_dir)
    if not source_files:
        raise ValueError(
            "Verified project has no CubeMX configuration source/header files from which to record a source fingerprint."
        )
    digest = hashlib.sha256()
    for source_path in source_files:
        digest.update(source_path.relative_to(project_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(read_generated_configuration_source(source_path).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def managed_modules_makefile_text() -> str:
    return "\n".join(
        [
            "# Generated by STM32 Project Builder. Managed by the module command.",
            "CODEX_APP_SOURCES := $(wildcard App/Src/*.c)",
            "C_SOURCES += $(CODEX_APP_SOURCES)",
            "C_INCLUDES += -IApp/Inc",
            "",
        ]
    )


def read_makefile_text(makefile: Path) -> str:
    with makefile.open("r", encoding="utf-8", newline="") as source:
        return source.read()


def managed_makefile_marker_block(newline: str) -> str:
    return newline.join(
        [
            MAKEFILE_MARKER_BEGIN,
            f"include {MODULES_MAKEFILE}",
            MAKEFILE_MARKER_END,
        ]
    )


def generated_makefile_baseline_text(project_dir: Path) -> str:
    """Return the CubeMX Makefile after validating/removing the one owned block."""
    makefile = project_dir / "Makefile"
    if not makefile.is_file():
        raise ValueError(
            "Verified project has no CubeMX Makefile from which to record a build fingerprint."
        )
    original = read_makefile_text(makefile)
    begin_count = original.count(MAKEFILE_MARKER_BEGIN)
    end_count = original.count(MAKEFILE_MARKER_END)
    modules_makefile = project_dir / MODULES_MAKEFILE
    if begin_count == 0 and end_count == 0:
        if modules_makefile.exists():
            raise ValueError(
                "Codex module Makefile requires the matching managed integration block."
            )
        return original
    if begin_count != 1 or end_count != 1:
        raise ValueError(
            "CubeMX Makefile has incomplete or repeated Codex module integration markers."
        )

    newline = "\r\n" if "\r\n" in original else "\n"
    marker_block = managed_makefile_marker_block(newline)
    marker_with_trailing_newline = marker_block + newline
    if original.count(marker_block) != 1 or marker_with_trailing_newline not in original:
        raise ValueError(
            "CubeMX Makefile Codex module integration differs from the controlled block."
        )
    if not modules_makefile.is_file():
        raise ValueError(
            "Codex module Makefile integration changed after verified generation; "
            f"expected {MODULES_MAKEFILE}."
        )
    if read_makefile_text(modules_makefile) != managed_modules_makefile_text():
        raise ValueError(
            "Codex module Makefile integration changed after verified generation."
        )
    return original.replace(marker_with_trailing_newline, "", 1)


def generated_makefile_fingerprint(project_dir: Path) -> str:
    return hashlib.sha256(generated_makefile_baseline_text(project_dir).encode("utf-8")).hexdigest()


def makefile_assignment_words(makefile_text: str, variable: str, *, required: bool) -> list[str]:
    assignment = re.compile(rf"^{re.escape(variable)}\s*(?:\+)?=\s*(.*)$")
    lines = makefile_text.splitlines()
    values: list[str] = []
    found = False
    line_index = 0
    while line_index < len(lines):
        match = assignment.fullmatch(lines[line_index])
        if match is None:
            line_index += 1
            continue
        found = True
        segment = match.group(1)
        while True:
            stripped = segment.rstrip()
            continues = stripped.endswith("\\")
            if continues:
                stripped = stripped[:-1].rstrip()
            values.append(stripped)
            if not continues:
                break
            line_index += 1
            if line_index >= len(lines):
                raise ValueError(f"CubeMX Makefile {variable} assignment ends with a dangling continuation.")
            segment = lines[line_index]
        line_index += 1
    if required and not found:
        raise ValueError(f"CubeMX Makefile must declare required {variable} build inputs.")
    return " ".join(values).split()


def safe_makefile_build_path(project_dir: Path, value: str, label: str) -> Path:
    relative_path = Path(value)
    if (
        relative_path.is_absolute()
        or not RELATIVE_PROJECT_FILE.fullmatch(value)
        or any(part in {".", ".."} for part in relative_path.parts)
    ):
        raise ValueError(f"Use {label} as a relative generated-project path.")
    project_root = project_dir.resolve()
    resolved = (project_root / relative_path).resolve()
    if project_root not in resolved.parents:
        raise ValueError(f"{label} escapes the generated project directory.")
    return resolved


def generated_build_input_paths(project_dir: Path) -> list[Path]:
    """List the generated sources, linker input, and generated include tree used by Make."""
    project_root = project_dir.resolve()
    makefile_text = generated_makefile_baseline_text(project_root)
    paths: dict[str, Path] = {}

    def add(path: Path, label: str) -> None:
        if not path.is_file():
            raise ValueError(f"Expected generated project file for {label}: {path}")
        resolved = path.resolve()
        if project_root not in resolved.parents:
            raise ValueError(f"{label} escapes the generated project directory.")
        relative = resolved.relative_to(project_root).as_posix()
        paths[relative] = resolved

    for variable, required in (("C_SOURCES", True), ("ASM_SOURCES", False)):
        for value in makefile_assignment_words(makefile_text, variable, required=required):
            add(safe_makefile_build_path(project_root, value, f"CubeMX Makefile {variable} entry"), f"CubeMX Makefile {variable} entry")

    linker_scripts = makefile_assignment_words(makefile_text, "LDSCRIPT", required=True)
    if len(linker_scripts) != 1:
        raise ValueError("CubeMX Makefile LDSCRIPT must declare exactly one generated linker script.")
    add(
        safe_makefile_build_path(project_root, linker_scripts[0], "CubeMX Makefile LDSCRIPT entry"),
        "CubeMX Makefile LDSCRIPT entry",
    )

    for variable in ("C_INCLUDES", "AS_INCLUDES"):
        for value in makefile_assignment_words(makefile_text, variable, required=False):
            if not value.startswith("-I") or value == "-I":
                raise ValueError(
                    f"CubeMX Makefile {variable} contains an unsupported generated include entry: {value!r}."
                )
            include_directory = safe_makefile_build_path(
                project_root,
                value[2:],
                f"CubeMX Makefile {variable} entry",
            )
            if not include_directory.is_dir():
                raise ValueError(
                    f"CubeMX Makefile {variable} entry must identify a generated include directory: {include_directory}"
                )
            for candidate in include_directory.rglob("*"):
                if candidate.is_file():
                    add(candidate, f"CubeMX Makefile {variable} generated include file")

    if not paths:
        raise ValueError("CubeMX Makefile declares no generated build inputs to fingerprint.")
    return [paths[relative] for relative in sorted(paths)]


def read_generated_build_input(path: Path) -> bytes:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError(f"Could not read generated build input: {path}: {error}") from error
    if path.suffix.lower() in {".c", ".h"}:
        source_text = content.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        return configuration_bearing_source_text(source_text).encode("utf-8")
    return content


def generated_build_input_fingerprint(project_dir: Path) -> str:
    project_root = project_dir.resolve()
    digest = hashlib.sha256()
    for input_path in generated_build_input_paths(project_root):
        digest.update(input_path.relative_to(project_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(read_generated_build_input(input_path))
        digest.update(b"\0")
    return digest.hexdigest()


def project_provenance_record(
    project_dir: Path,
    configuration: dict[str, Any],
    board_profile: dict[str, Any],
    board_profile_sha256: str,
) -> dict[str, Any]:
    if not SHA256_HEX.fullmatch(board_profile_sha256):
        raise ValueError("board_profile_sha256 must be a lowercase SHA-256 digest.")
    generated_identifiers = set(generated_identifier_inventory(project_dir))
    modules = normalized_planned_modules(
        configuration["modules"],
        configuration["packs"],
        "configuration plan.modules",
        generated_identifiers,
    )
    ioc_facts = root_ioc_generation_facts(project_dir)
    return {
        "schema_version": PROJECT_PROVENANCE_SCHEMA_VERSION,
        "mcu": configuration["mcu"],
        "manual_sha256": board_profile["board"]["manual"]["sha256"],
        "board_profile_sha256": board_profile_sha256,
        "configuration_plan_sha256": configuration["plan_sha256"],
        "generated_identifiers": sorted(generated_identifiers),
        "generated_source_sha256": generated_configuration_source_fingerprint(project_dir),
        "generated_makefile_sha256": generated_makefile_fingerprint(project_dir),
        "generated_build_inputs_sha256": generated_build_input_fingerprint(project_dir),
        "ioc_sha256": ioc_facts["ioc_sha256"],
        "generator": ioc_facts["generator"],
        "packs": [
            {"id": pack_id, "content_sha256": pack_contract_fingerprint(pack_id)}
            for pack_id in configuration["packs"]
        ],
        "modules": modules,
    }


def write_project_provenance(
    project_dir: Path,
    configuration: dict[str, Any],
    board_profile: dict[str, Any],
    board_profile_sha256: str,
) -> Path:
    provenance_path = project_dir / PROJECT_PROVENANCE_FILE
    record = project_provenance_record(project_dir, configuration, board_profile, board_profile_sha256)
    try:
        with provenance_path.open("x", encoding="utf-8") as output:
            output.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    except FileExistsError as error:
        raise ValueError(f"Project provenance path already exists: {provenance_path}") from error
    return provenance_path


def load_project_provenance(project_dir: Path) -> dict[str, Any]:
    provenance_path = project_dir / PROJECT_PROVENANCE_FILE
    try:
        raw = json.loads(provenance_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"Pack-backed module generation requires {PROJECT_PROVENANCE_FILE} from a verified fresh generate command."
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Project provenance is not valid JSON: {provenance_path}: {error.msg}") from error

    provenance = plan_object(raw, "project provenance")
    if provenance.get("schema_version") != PROJECT_PROVENANCE_SCHEMA_VERSION:
        raise ValueError(f"project provenance schema_version must be {PROJECT_PROVENANCE_SCHEMA_VERSION}.")
    mcu = validated_mcu_identifier(plan_string(plan_required(provenance, "mcu", "project provenance.mcu"), "project provenance.mcu"))
    input_hashes: dict[str, str] = {}
    for key in ("manual_sha256", "board_profile_sha256", "configuration_plan_sha256"):
        digest = plan_string(plan_required(provenance, key, f"project provenance.{key}"), f"project provenance.{key}")
        if not SHA256_HEX.fullmatch(digest):
            raise ValueError(f"project provenance.{key} must be a lowercase SHA-256 digest.")
        input_hashes[key] = digest
    expected_ioc_sha256 = plan_string(
        plan_required(provenance, "ioc_sha256", "project provenance.ioc_sha256"),
        "project provenance.ioc_sha256",
    )
    if not SHA256_HEX.fullmatch(expected_ioc_sha256):
        raise ValueError("project provenance.ioc_sha256 must be a lowercase SHA-256 digest.")
    raw_generator = plan_object(
        plan_required(provenance, "generator", "project provenance.generator"),
        "project provenance.generator",
    )
    expected_generator_keys = set(IOC_GENERATION_FACT_PROPERTIES.values())
    actual_generator_keys = set(raw_generator)
    if actual_generator_keys != expected_generator_keys:
        missing = sorted(expected_generator_keys - actual_generator_keys)
        unexpected = sorted(actual_generator_keys - expected_generator_keys)
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected {', '.join(unexpected)}")
        raise ValueError(
            "project provenance.generator must contain exactly the frozen CubeMX generation facts "
            f"({'; '.join(details)})."
        )
    expected_generator = {
        key: ioc_generation_fact_value(raw_generator[key], f"project provenance.generator.{key}")
        for key in sorted(expected_generator_keys)
    }
    actual_ioc_facts = root_ioc_generation_facts(project_dir)
    if actual_ioc_facts["ioc_sha256"] != expected_ioc_sha256:
        raise ValueError(
            "CubeMX .ioc configuration changed after verified generation; "
            "regenerate a fresh project before rendering its module."
        )
    if actual_ioc_facts["generator"] != expected_generator:
        raise ValueError(
            "CubeMX generator facts changed after verified generation; "
            "regenerate a fresh project before rendering its module."
        )

    raw_identifiers = plan_list(
        plan_required(provenance, "generated_identifiers", "project provenance.generated_identifiers"),
        "project provenance.generated_identifiers",
    )
    if not raw_identifiers:
        raise ValueError("project provenance.generated_identifiers must contain CubeMX-generated C identifiers.")
    generated_identifiers: set[str] = set()
    for identifier_index, raw_identifier in enumerate(raw_identifiers, start=1):
        identifier = generated_c_identifier(
            raw_identifier, f"project provenance.generated_identifiers[{identifier_index}]"
        )
        if identifier in generated_identifiers:
            raise ValueError(f"project provenance.generated_identifiers repeats {identifier}.")
        generated_identifiers.add(identifier)
    expected_source_fingerprint = plan_string(
        plan_required(
            provenance,
            "generated_source_sha256",
            "project provenance.generated_source_sha256",
        ),
        "project provenance.generated_source_sha256",
    )
    if not SHA256_HEX.fullmatch(expected_source_fingerprint):
        raise ValueError("project provenance.generated_source_sha256 must be a lowercase SHA-256 digest.")
    actual_source_fingerprint = generated_configuration_source_fingerprint(project_dir)
    if actual_source_fingerprint != expected_source_fingerprint:
        raise ValueError(
            "CubeMX configuration source changed after verified generation; regenerate a fresh project before rendering its module."
        )
    expected_makefile_fingerprint = plan_string(
        plan_required(
            provenance,
            "generated_makefile_sha256",
            "project provenance.generated_makefile_sha256",
        ),
        "project provenance.generated_makefile_sha256",
    )
    if not SHA256_HEX.fullmatch(expected_makefile_fingerprint):
        raise ValueError(
            "project provenance.generated_makefile_sha256 must be a lowercase SHA-256 digest."
        )
    actual_makefile_fingerprint = generated_makefile_fingerprint(project_dir)
    if actual_makefile_fingerprint != expected_makefile_fingerprint:
        raise ValueError(
            "CubeMX Makefile changed after verified generation; "
            "regenerate a fresh project before compiling or rendering its module."
        )
    expected_build_input_fingerprint = plan_string(
        plan_required(
            provenance,
            "generated_build_inputs_sha256",
            "project provenance.generated_build_inputs_sha256",
        ),
        "project provenance.generated_build_inputs_sha256",
    )
    if not SHA256_HEX.fullmatch(expected_build_input_fingerprint):
        raise ValueError(
            "project provenance.generated_build_inputs_sha256 must be a lowercase SHA-256 digest."
        )
    actual_build_input_fingerprint = generated_build_input_fingerprint(project_dir)
    if actual_build_input_fingerprint != expected_build_input_fingerprint:
        raise ValueError(
            "CubeMX generated build input changed after verified generation; "
            "regenerate a fresh project before compiling or rendering its module."
        )
    actual_generated_identifiers = set(generated_identifier_inventory(project_dir))
    if actual_generated_identifiers != generated_identifiers:
        raise ValueError(
            "CubeMX configuration identifier inventory changed after verified generation; "
            "regenerate a fresh project before rendering its module."
        )

    raw_packs = plan_list(plan_required(provenance, "packs", "project provenance.packs"), "project provenance.packs")
    if not raw_packs:
        raise ValueError("project provenance.packs must contain at least one selected capability pack.")
    packs: list[str] = []
    seen: set[str] = set()
    for pack_index, raw_pack in enumerate(raw_packs, start=1):
        pack = plan_object(raw_pack, f"project provenance.packs[{pack_index}]")
        pack_id = plan_string(
            plan_required(pack, "id", f"project provenance.packs[{pack_index}].id"),
            f"project provenance.packs[{pack_index}].id",
        )
        if not PACK_ID.fullmatch(pack_id):
            raise ValueError(f"Use a valid project provenance pack identifier at packs[{pack_index}].id.")
        if pack_id in seen:
            raise ValueError(f"project provenance.packs repeats capability pack {pack_id}.")
        expected_fingerprint = plan_string(
            plan_required(pack, "content_sha256", f"project provenance.packs[{pack_index}].content_sha256"),
            f"project provenance.packs[{pack_index}].content_sha256",
        )
        if not SHA256_HEX.fullmatch(expected_fingerprint):
            raise ValueError(f"project provenance.packs[{pack_index}].content_sha256 must be a lowercase SHA-256 digest.")
        actual_fingerprint = pack_contract_fingerprint(pack_id)
        if actual_fingerprint != expected_fingerprint:
            raise ValueError(
                f"Capability pack {pack_id} changed after this project was generated; regenerate a fresh project before rendering its module."
            )
        seen.add(pack_id)
        packs.append(pack_id)
    raw_modules = plan_list(
        plan_required(provenance, "modules", "project provenance.modules"),
        "project provenance.modules",
    )
    modules = normalized_planned_modules(
        raw_modules,
        packs,
        "project provenance.modules",
        generated_identifiers,
    )
    return {
        "mcu": mcu,
        **input_hashes,
        "packs": packs,
        "generated_identifiers": generated_identifiers,
        "generator": expected_generator,
        "modules": modules,
    }


def normalized_plan_verification(raw_verification: Any, label: str) -> dict[str, str]:
    verification = plan_object(raw_verification, label)
    file_name = plan_string(
        plan_required(verification, "file", f"{label}.file"),
        f"{label}.file",
    )
    if file_name != IOC_VERIFICATION_FILE and (
        Path(file_name).is_absolute() or not RELATIVE_PROJECT_FILE.fullmatch(file_name) or ".." in Path(file_name).parts
    ):
        raise ValueError(f"Use {label}.file as $IOC or a relative project path.")
    contains = plan_string(
        plan_required(verification, "contains", f"{label}.contains"),
        f"{label}.contains",
    )
    return {"file": file_name, "contains": contains}


def config_plan(plan_path: Path, expected_mcu: str, board_profile: dict[str, Any]) -> dict[str, Any]:
    try:
        raw_bytes = plan_path.read_bytes()
        raw = json.loads(raw_bytes)
    except FileNotFoundError as error:
        raise ValueError(f"Configuration plan path is missing: {plan_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Configuration plan is not valid JSON: {plan_path}: {error.msg}") from error
    plan = plan_object(raw, "configuration plan")
    if plan_required(plan, "schema_version", "schema_version") != CONFIGURATION_PLAN_SCHEMA_VERSION:
        raise ValueError(f"configuration plan schema_version must be {CONFIGURATION_PLAN_SCHEMA_VERSION}.")

    plan_mcu = validated_mcu_identifier(plan_string(plan_required(plan, "mcu", "mcu"), "mcu"))
    profile_mcu = board_profile["mcu"]["part_number"]
    if plan_mcu != expected_mcu or plan_mcu != profile_mcu:
        raise ValueError(
            "Configuration plan MCU must match both --mcu and board-profile.json "
            f"({expected_mcu} / {profile_mcu})."
        )

    selected_packs = selected_capability_packs(plan)
    pack_manifests = selected_pack_manifests(selected_packs)
    normalized_modules = normalized_planned_modules(
        plan_list(plan.get("modules", []), "modules"),
        selected_packs,
        "modules",
    )
    profile_pins = {pin["pin"]: pin for pin in board_profile["pins"]}
    operations = plan_list(plan.get("operations", []), "operations")
    pin_assignments = plan_list(plan.get("pin_assignments", []), "pin_assignments")
    if not operations and not pin_assignments:
        raise ValueError("configuration plan must contain at least one peripheral operation or direct pin assignment.")
    normalized_operations: list[dict[str, Any]] = []
    seen_instances: set[str] = set()
    seen_pins: set[str] = set()
    for operation_index, raw_operation in enumerate(operations, start=1):
        operation = plan_object(raw_operation, f"operations[{operation_index}]")
        operation_label = f"operations[{operation_index}]"
        pack_id = resource_pack_id(operation, operation_label, pack_manifests)
        instance = cube_plan_identifier(
            plan_required(operation, "instance", f"{operation_label}.instance"),
            f"{operation_label}.instance",
        )
        require_pack_operation_instance(pack_id, instance, operation_label, pack_manifests)
        if instance in seen_instances:
            raise ValueError(f"operations[{operation_index}].instance repeats {instance}; use one operation per peripheral instance.")
        seen_instances.add(instance)
        mode = cube_plan_token(
            plan_required(operation, "mode", f"operations[{operation_index}].mode"),
            f"operations[{operation_index}].mode",
        )
        pins = plan_list(plan_required(operation, "pins", f"operations[{operation_index}].pins"), f"operations[{operation_index}].pins")
        normalized_pins: list[dict[str, str]] = []
        for pin_index, raw_pin in enumerate(pins, start=1):
            pin = plan_object(raw_pin, f"operations[{operation_index}].pins[{pin_index}]")
            pin_name = plan_string(
                plan_required(pin, "pin", f"operations[{operation_index}].pins[{pin_index}].pin"),
                f"operations[{operation_index}].pins[{pin_index}].pin",
            )
            if not PIN_IDENTIFIER.fullmatch(pin_name):
                raise ValueError(f"operations[{operation_index}].pins[{pin_index}].pin must look like PA0 or PB12.")
            if pin_name in seen_pins:
                raise ValueError(f"Configuration plan assigns {pin_name} more than once.")
            seen_pins.add(pin_name)
            profile_pin = profile_pins.get(pin_name)
            if profile_pin is None:
                raise ValueError(f"Configuration plan uses {pin_name}, which is absent from board-profile.json.")
            if profile_pin["status"] != "available":
                raise ValueError(
                    f"Configuration plan uses {pin_name}, but board-profile.json marks it as {profile_pin['status']}."
                )
            signal = cube_plan_identifier(
                plan_required(pin, "signal", f"operations[{operation_index}].pins[{pin_index}].signal"),
                f"operations[{operation_index}].pins[{pin_index}].signal",
            )
            normalized_pins.append({"pin": pin_name, "signal": signal})

        parameters = plan_list(
            plan_required(operation, "parameters", f"operations[{operation_index}].parameters"),
            f"operations[{operation_index}].parameters",
        )
        normalized_parameters: list[dict[str, Any]] = []
        seen_parameters: set[str] = set()
        for parameter_index, raw_parameter in enumerate(parameters, start=1):
            parameter = plan_object(raw_parameter, f"operations[{operation_index}].parameters[{parameter_index}]")
            parameter_name = cube_plan_identifier(
                plan_required(parameter, "name", f"operations[{operation_index}].parameters[{parameter_index}].name"),
                f"operations[{operation_index}].parameters[{parameter_index}].name",
            )
            if parameter_name in seen_parameters:
                raise ValueError(f"operations[{operation_index}] repeats parameter {parameter_name}.")
            seen_parameters.add(parameter_name)
            parameter_value = normalized_parameter_value(
                plan_required(parameter, "value", f"operations[{operation_index}].parameters[{parameter_index}].value"),
                f"operations[{operation_index}].parameters[{parameter_index}].value",
            )
            parameter_verification = normalized_plan_verification(
                plan_required(
                    parameter,
                    "verification",
                    f"operations[{operation_index}].parameters[{parameter_index}].verification",
                ),
                f"operations[{operation_index}].parameters[{parameter_index}].verification",
            )
            normalized_parameters.append(
                {
                    "name": parameter_name,
                    "value": parameter_value,
                    "verification": parameter_verification,
                }
            )
        timing: dict[str, Any] | None = None
        if pack_id in TIMING_PACK_IDS:
            timing = normalized_timer_timing(
                plan_required(operation, "timing", f"{operation_label}.timing"),
                f"{operation_label}.timing",
                plan_mcu,
                instance,
                normalized_parameters,
            )
        elif "timing" in operation:
            raise ValueError(f"Use {operation_label}.timing with a pwm or timer operation.")
        require_pack_operation_pin_contract(
            pack_id,
            instance,
            normalized_pins,
            operation_label,
            pack_manifests,
        )
        normalized_operations.append(
            {
                "pack": pack_id,
                "instance": instance,
                "mode": mode,
                "pins": normalized_pins,
                "parameters": normalized_parameters,
                "timing": timing,
            }
        )

    normalized_pin_assignments: list[dict[str, str]] = []
    for assignment_index, raw_assignment in enumerate(pin_assignments, start=1):
        assignment = plan_object(raw_assignment, f"pin_assignments[{assignment_index}]")
        assignment_label = f"pin_assignments[{assignment_index}]"
        pack_id = resource_pack_id(assignment, assignment_label, pack_manifests)
        pin_name = plan_string(
            plan_required(assignment, "pin", f"{assignment_label}.pin"),
            f"{assignment_label}.pin",
        )
        if not PIN_IDENTIFIER.fullmatch(pin_name):
            raise ValueError(f"pin_assignments[{assignment_index}].pin must look like PA0 or PB12.")
        if pin_name in seen_pins:
            raise ValueError(f"Configuration plan assigns {pin_name} more than once.")
        seen_pins.add(pin_name)
        profile_pin = profile_pins.get(pin_name)
        if profile_pin is None:
            raise ValueError(f"Configuration plan uses {pin_name}, which is absent from board-profile.json.")
        if profile_pin["status"] != "available":
            raise ValueError(
                f"Configuration plan uses {pin_name}, but board-profile.json marks it as {profile_pin['status']}."
            )
        signal = cube_plan_identifier(
            plan_required(assignment, "signal", f"{assignment_label}.signal"),
            f"{assignment_label}.signal",
        )
        require_pack_direct_pin_signal(pack_id, signal, assignment_label, pack_manifests)
        normalized_pin_assignments.append({"pack": pack_id, "pin": pin_name, "signal": signal})

    verifications = plan_list(plan_required(plan, "verifications", "verifications"), "verifications")
    if not verifications:
        raise ValueError("verifications must contain expected .ioc or generated-source evidence.")
    normalized_verifications: list[dict[str, str]] = []
    for verification_index, raw_verification in enumerate(verifications, start=1):
        normalized_verifications.append(
            normalized_plan_verification(raw_verification, f"verifications[{verification_index}]")
        )
    normalized_overrides = normalized_ioc_overrides(
        plan_list(plan.get("ioc_overrides", []), "ioc_overrides"),
        pack_manifests,
        normalized_operations,
        normalized_pin_assignments,
    )
    require_ioc_override_verifications(normalized_overrides, normalized_verifications)
    return {
        "mcu": plan_mcu,
        "plan_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "packs": selected_packs,
        "modules": normalized_modules,
        "operations": normalized_operations,
        "pin_assignments": normalized_pin_assignments,
        "ioc_overrides": normalized_overrides,
        "verifications": normalized_verifications,
    }


def cubemx_script(mcu: str, name: str, output_dir: Path, configuration: dict[str, Any] | None = None) -> str:
    commands = [f"load {mcu}", "waitclock 5"]
    if configuration:
        for operation in configuration["operations"]:
            commands.append(f"set mode {operation['instance']} {cube_script_value(operation['mode'])}")
            commands.extend(f"set pin {pin['pin']} {pin['signal']}" for pin in operation["pins"])
            commands.extend(
                f"set ip parameters {operation['instance']} {parameter['name']} {cube_script_value(parameter['value'])}"
                for parameter in operation["parameters"]
            )
        commands.extend(f"set pin {pin['pin']} {pin['signal']}" for pin in configuration["pin_assignments"])
    commands.extend(
        [
            f"project name {name}",
            'project toolchain "Makefile"',
            f"project path {cube_quote(output_dir)}",
            "SetStructure Basic",
            'SetCopyLibrary "copy all"',
            "project generate",
            "exit",
            "",
        ]
    )
    return "\n".join(commands)


def cubemx_config_reload_script(ioc_path: Path) -> str:
    return "\n".join([f"config load {cube_quote(ioc_path)}", "project generate", "exit", ""])


def root_ioc_file(project_dir: Path) -> Path:
    ioc_files = sorted(project_dir.glob("*.ioc"))
    if len(ioc_files) != 1:
        raise ValueError(f"Expected exactly one root .ioc file in the new project: {project_dir}")
    return ioc_files[0]


def ioc_generation_fact_value(value: Any, label: str) -> str:
    text = plan_string(value, label)
    if "\r" in text or "\n" in text:
        raise ValueError(f"{label} must be a single .ioc property value.")
    return text


def root_ioc_generation_facts(project_dir: Path) -> dict[str, Any]:
    """Read the generator identity embedded by CubeMX in the verified root .ioc."""
    ioc_path = root_ioc_file(project_dir)
    try:
        raw_ioc = ioc_path.read_bytes()
        ioc_text = raw_ioc.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Could not read CubeMX root .ioc generation facts: {ioc_path}: {error}") from error

    generator: dict[str, str] = {}
    for line in ioc_text.splitlines():
        property_key, separator, property_value = line.partition("=")
        generator_key = IOC_GENERATION_FACT_PROPERTIES.get(property_key)
        if generator_key is None:
            continue
        if not separator:
            raise ValueError(f"CubeMX root .ioc has malformed generation fact {property_key}.")
        if generator_key in generator:
            raise ValueError(f"CubeMX root .ioc repeats generation fact {property_key}.")
        generator[generator_key] = ioc_generation_fact_value(
            property_value,
            f"CubeMX root .ioc {property_key}",
        )

    expected_keys = set(IOC_GENERATION_FACT_PROPERTIES.values())
    missing = sorted(expected_keys - set(generator))
    if missing:
        raise ValueError(
            "CubeMX root .ioc is missing required generation facts: "
            f"{', '.join(missing)}."
        )
    return {
        "ioc_sha256": hashlib.sha256(raw_ioc).hexdigest(),
        "generator": {key: generator[key] for key in sorted(expected_keys)},
    }


def apply_ioc_overrides(project_dir: Path, overrides: list[dict[str, str]]) -> Path:
    ioc_path = root_ioc_file(project_dir)
    original = ioc_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines(keepends=True)
    for override in overrides:
        key = override["key"]
        value = override["value"]
        prefix = f"{key}="
        matches = [index for index, line in enumerate(lines) if line.rstrip("\r\n").startswith(prefix)]
        if len(matches) > 1:
            raise ValueError(f"Fresh .ioc contains duplicate property {key}; refusing to choose one.")
        replacement = f"{key}={value}"
        if matches:
            index = matches[0]
            ending = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
            lines[index] = replacement + ending
        else:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            lines.append(replacement + newline)
    ioc_path.write_text("".join(lines), encoding="utf-8")
    return ioc_path


def run_cubemx_quiet_script(toolchain: Toolchain, output_dir: Path, project_name: str, script_text: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".mxscript",
        prefix=f"{project_name}-",
        dir=output_dir,
        delete=False,
    ) as script_file:
        script_file.write(script_text)
        script_path = Path(script_file.name)
    try:
        return subprocess.run(
            [toolchain.cubemx, "-q", str(script_path)],
            cwd=output_dir,
            env=build_environment(toolchain),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    finally:
        script_path.unlink(missing_ok=True)


def cubemx_rejected_commands(output: str) -> bool:
    """Return true for CubeMX CLI's standalone KO command marker."""
    return any(line.strip() == "KO" for line in output.splitlines())


def generated_pin_verification_failures(project_dir: Path, configuration: dict[str, Any]) -> list[str]:
    """Check requested physical-pin assignments despite CubeMX's S_ signal alias."""
    try:
        ioc_content = root_ioc_file(project_dir).read_text(encoding="utf-8", errors="replace")
    except ValueError as error:
        return [str(error)]

    failures: list[str] = []
    assignments = [assignment for operation in configuration["operations"] for assignment in operation["pins"]]
    assignments.extend(configuration["pin_assignments"])
    for assignment in assignments:
        pin = assignment["pin"]
        signal = assignment["signal"]
        expected = re.compile(rf"^{re.escape(pin)}\.Signal=(?:S_)?{re.escape(signal)}$", re.MULTILINE)
        if not expected.search(ioc_content):
            failures.append(f"$IOC expected {pin} to map to {signal}")
    return failures


def ioc_frequency_property_value(ioc_content: str, key: str) -> int | None:
    values = re.findall(rf"^{re.escape(key)}=([0-9]+)$", ioc_content, re.MULTILINE)
    if len(values) != 1:
        return None
    return int(values[0])


def timer_timing_verification_failures(project_dir: Path, configuration: dict[str, Any]) -> list[str]:
    timer_operations = [
        (index, operation)
        for index, operation in enumerate(configuration["operations"], start=1)
        if operation.get("timing") is not None
    ]
    if not timer_operations:
        return []
    try:
        ioc_content = root_ioc_file(project_dir).read_text(encoding="utf-8", errors="replace")
    except ValueError as error:
        return [str(error)]

    hclk_hz = ioc_frequency_property_value(ioc_content, "RCC.AHBFreq_Value")
    failures: list[str] = []
    for operation_index, operation in timer_operations:
        timing = operation["timing"]
        clock_property = timing["clock_property"]
        peripheral_hz = ioc_frequency_property_value(ioc_content, clock_property)
        label = f"operations[{operation_index}].timing"
        if hclk_hz is None:
            failures.append(f"{label} is missing generated RCC.AHBFreq_Value.")
            continue
        if peripheral_hz is None:
            failures.append(f"{label} is missing generated {clock_property}.")
            continue
        if peripheral_hz != hclk_hz:
            failures.append(
                f"{label} requires an unprescaled STM32F4 APB clock, but "
                f"{clock_property}={peripheral_hz} differs from RCC.AHBFreq_Value={hclk_hz}."
            )
            continue
        if timing["timer_input_hz"] != peripheral_hz:
            failures.append(
                f"{label}.timer_input_hz={timing['timer_input_hz']} differs from "
                f"generated {clock_property}={peripheral_hz}."
            )
            continue

        divisor = (timing["prescaler"] + 1) * (timing["period"] + 1)
        expected_scaled = timing["target_hz"] * divisor
        difference = abs(timing["timer_input_hz"] - expected_scaled)
        if difference * 1_000_000 > timing["tolerance_ppm"] * expected_scaled:
            error_ppm = (difference * 1_000_000 + expected_scaled - 1) // expected_scaled
            failures.append(
                f"{label} configures {timing['timer_input_hz']}/{divisor} Hz, which differs from "
                f"target_hz={timing['target_hz']} by {error_ppm} ppm "
                f"(tolerance_ppm={timing['tolerance_ppm']})."
            )
    return failures


def configuration_verification_failures(project_dir: Path, configuration: dict[str, Any]) -> list[str]:
    ioc_files = sorted(project_dir.glob("*.ioc"))
    failures = generated_pin_verification_failures(project_dir, configuration)
    verifications = list(configuration["verifications"])
    verifications.extend(
        parameter["verification"]
        for operation in configuration["operations"]
        for parameter in operation.get("parameters", [])
        if parameter.get("verification") is not None
    )
    for verification in verifications:
        target = ioc_files[0] if verification["file"] == IOC_VERIFICATION_FILE and ioc_files else project_dir / verification["file"]
        if not target.is_file():
            failures.append(f"missing {verification['file']}")
            continue
        content = target.read_text(encoding="utf-8", errors="replace")
        if verification["contains"] not in content:
            failures.append(f"{verification['file']} is missing {verification['contains']!r}")
    failures.extend(timer_timing_verification_failures(project_dir, configuration))
    return failures


def run_generate(args: argparse.Namespace) -> int:
    try:
        name = validated_project_name(args.name)
        mcu = validated_mcu_identifier(args.mcu)
        if not all((args.board_profile, args.manual, args.plan)):
            raise ValueError("generate requires --board-profile, --manual, and --plan.")
        profile_path = Path(args.board_profile).expanduser().resolve()
        manual_path = Path(args.manual).expanduser().resolve()
        board_profile, profile_snapshot = load_and_validate_profile_snapshot(profile_path, manual_path)
        board_profile_sha256 = hashlib.sha256(profile_snapshot).hexdigest()
        plan_path = Path(args.plan).expanduser().resolve()
        configuration = config_plan(plan_path, mcu, board_profile)
        toolchain = discover_tools(args.cubemx, args.cubeide)
    except (BoardProfileError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    if not toolchain.cubemx:
        print("Error: STM32CubeMX is required. Run doctor to inspect the expected installation.", file=sys.stderr)
        return 2
    try:
        validate_operations_against_cubemx_database(configuration, mcu, toolchain.cubemx)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve()
    if not output_dir.is_dir():
        print(f"Error: output directory is missing: {output_dir}", file=sys.stderr)
        return 2
    project_dir = output_dir / name
    script_text = cubemx_script(mcu, name, output_dir, configuration)
    if args.dry_run:
        print(script_text, end="")
        return 0
    if project_dir.exists():
        print(f"Error: refusing to overwrite existing project directory: {project_dir}", file=sys.stderr)
        return 2

    try:
        result = run_cubemx_quiet_script(toolchain, output_dir, name, script_text)
    except OSError as error:
        print(f"CubeMX generation could not start: {error}", file=sys.stderr)
        return 1

    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        print(f"CubeMX generation failed with exit code {result.returncode}.", file=sys.stderr)
        return result.returncode or 1
    if cubemx_rejected_commands(result.stdout):
        print("CubeMX reported a KO marker for one or more configuration commands.", file=sys.stderr)
        return 1
    if not project_dir.is_dir():
        print("CubeMX reported success but did not create the requested project directory.", file=sys.stderr)
        return 1

    if configuration and configuration["ioc_overrides"]:
        try:
            ioc_path = apply_ioc_overrides(project_dir, configuration["ioc_overrides"])
            reload_result = run_cubemx_quiet_script(
                toolchain,
                output_dir,
                name,
                cubemx_config_reload_script(ioc_path),
            )
        except (OSError, ValueError) as error:
            print(f"CubeMX configuration reload could not start: {error}", file=sys.stderr)
            return 1
        if reload_result.stdout:
            print(reload_result.stdout, end="" if reload_result.stdout.endswith("\n") else "\n")
        if reload_result.returncode != 0:
            print(f"CubeMX configuration reload failed with exit code {reload_result.returncode}.", file=sys.stderr)
            return reload_result.returncode or 1
        if cubemx_rejected_commands(reload_result.stdout):
            print("CubeMX reported a KO marker for one or more configuration reload commands.", file=sys.stderr)
            return 1

    ioc_files = sorted(project_dir.glob("*.ioc"))
    makefile = project_dir / "Makefile"
    print(f"Generated project: {project_dir}")
    if ioc_files:
        print(f"Configuration: {ioc_files[0]}")
    else:
        print("Warning: no .ioc file was found at the project root.", file=sys.stderr)
    if not makefile.is_file():
        print(
            "CubeMX output is missing a Makefile project. "
            "Install the matching STM32Cube firmware package in CubeMX, then rerun generate.",
            file=sys.stderr,
        )
        return 1
    if configuration:
        failures = configuration_verification_failures(project_dir, configuration)
        if failures:
            print("Generated project did not satisfy the approved configuration plan:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
        print("Configuration plan verified against generated files.")
    try:
        provenance_path = write_project_provenance(
            project_dir,
            configuration,
            board_profile,
            board_profile_sha256,
        )
    except (OSError, ValueError) as error:
        print(f"Could not write verified project provenance: {error}", file=sys.stderr)
        return 1
    print(f"Project provenance: {provenance_path}")
    return 0


def module_header_text(name: str) -> str:
    guard = f"CODEX_APP_{name.upper()}_H"
    return "\n".join(
        [
            f"#ifndef {guard}",
            f"#define {guard}",
            "",
            f"void {name}_init(void);",
            f"void {name}_process(void);",
            "",
            f"#endif /* {guard} */",
            "",
        ]
    )


def module_source_text(name: str) -> str:
    return "\n".join(
        [
            f'#include "{name}.h"',
            "",
            f"void {name}_init(void)",
            "{",
            "  /* Codex: initialize this module here. */",
            "}",
            "",
            f"void {name}_process(void)",
            "{",
            "  /* Codex: run one non-blocking application step here. */",
            "}",
            "",
        ]
    )


def module_template_paths(pack_id: str) -> tuple[Path, Path]:
    if not PACK_ID.fullmatch(pack_id):
        raise ValueError(f"Use a valid capability-pack identifier; received {pack_id!r}.")
    pack_dir = PACKS_ROOT / pack_id
    try:
        manifest = validate_pack(pack_dir)
    except PackValidationError as error:
        raise ValueError(f"Capability pack {pack_id} is not available as a valid local contract: {error}") from error
    template_paths = [pack_dir / Path(value) for value in manifest["templates"]]
    headers = [path for path in template_paths if path.name.endswith(".h.tmpl")]
    sources = [path for path in template_paths if path.name.endswith(".c.tmpl")]
    if len(headers) != 1 or len(sources) != 1:
        raise ValueError(
            f"Capability pack {pack_id} must declare exactly one .h.tmpl and one .c.tmpl for module rendering."
        )
    return headers[0], sources[0]


def template_tokens(template_text: str, template_path: Path) -> set[str]:
    tokens = set(TEMPLATE_TOKEN.findall(template_text))
    remainder = TEMPLATE_TOKEN.sub("", template_text)
    if "{{" in remainder or "}}" in remainder:
        raise ValueError(f"Template contains a malformed placeholder: {template_path}")
    return tokens


def render_module_template(template_text: str, template_path: Path, bindings: dict[str, str]) -> str:
    tokens = template_tokens(template_text, template_path)
    missing = sorted(tokens - bindings.keys())
    if missing:
        raise ValueError(f"Template {template_path.name} is missing bindings for: {', '.join(missing)}")
    rendered = TEMPLATE_TOKEN.sub(lambda match: bindings[match.group(1)], template_text)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError(f"Template rendering left an unresolved placeholder: {template_path}")
    return rendered


def assert_pack_callback_boundary(project_dir: Path, pack_id: str) -> None:
    if pack_id != "timer":
        return
    for source_root in (project_dir / "Src", project_dir / "App" / "Src"):
        if not source_root.is_dir():
            continue
        for source_path in source_root.rglob("*.c"):
            source_text = source_path.read_text(encoding="utf-8", errors="replace")
            if TIM_PERIOD_ELAPSED_CALLBACK.search(source_text):
                raise ValueError(
                    "Route timer dispatch through the existing HAL_TIM_PeriodElapsedCallback owner."
                )


def planned_module(provenance: dict[str, Any], name: str) -> dict[str, Any] | None:
    for module in provenance["modules"]:
        if module["name"] == name:
            return module
    return None


def pack_module_text(project_dir: Path, name: str, pack_value: Any) -> tuple[str, str, str]:
    pack_id = plan_string(pack_value, "pack")
    if not PACK_ID.fullmatch(pack_id):
        raise ValueError("pack must be a lowercase capability-pack identifier.")
    provenance = load_project_provenance(project_dir)
    declared_module = planned_module(provenance, name)
    if declared_module is None:
        raise ValueError(
            f"Project provenance must declare pack module {name}; "
            "add it to configuration-plan.json and generate a fresh project."
        )
    if declared_module["pack"] != pack_id:
        raise ValueError(
            f"Project provenance declares module {name} for pack {declared_module['pack']}, not {pack_id}."
        )
    assert_pack_callback_boundary(project_dir, pack_id)
    header_template, source_template = module_template_paths(pack_id)
    header_text = header_template.read_text(encoding="utf-8")
    source_text = source_template.read_text(encoding="utf-8")
    bindings = {
        "MODULE_NAME": name,
        "MODULE_GUARD": name.upper(),
        **declared_module["bindings"],
    }
    return (
        render_module_template(header_text, header_template, bindings),
        render_module_template(source_text, source_template, bindings),
        pack_id,
    )


def synchronize_module_makefile(project_dir: Path) -> None:
    makefile = project_dir / "Makefile"
    if not makefile.is_file():
        raise ValueError(f"Expected a Makefile project at: {project_dir}")

    original = read_makefile_text(makefile)
    generated_makefile_baseline_text(project_dir)
    newline = "\r\n" if "\r\n" in original else "\n"
    marker_block = managed_makefile_marker_block(newline)
    if MAKEFILE_MARKER_BEGIN in original or MAKEFILE_MARKER_END in original:
        return
    else:
        anchor = f"#######################################{newline}# build the application"
        if anchor not in original:
            raise ValueError("Could not locate the CubeMX Makefile application-build section.")
        updated = original.replace(anchor, marker_block + newline + anchor, 1)

    if updated != original:
        with makefile.open("w", encoding="utf-8", newline="") as output:
            output.write(updated)
    with (project_dir / MODULES_MAKEFILE).open("w", encoding="utf-8", newline="") as output:
        output.write(managed_modules_makefile_text())


def run_module(args: argparse.Namespace) -> int:
    try:
        name = validated_module_name(args.name)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not (project_dir / "Makefile").is_file():
        print(f"Error: expected a Makefile project at: {project_dir}", file=sys.stderr)
        return 2
    header_path = project_dir / "App" / "Inc" / f"{name}.h"
    source_path = project_dir / "App" / "Src" / f"{name}.c"
    pack_value = getattr(args, "pack", None)
    if header_path.exists() != source_path.exists():
        print(
            f"Error: module {name} has one existing module file. Use a new module name or complete the existing module.",
            file=sys.stderr,
        )
        return 2

    try:
        if pack_value is None and (project_dir / PROJECT_PROVENANCE_FILE).exists():
            provenance = load_project_provenance(project_dir)
            declared_module = planned_module(provenance, name)
            if declared_module is not None:
                raise ValueError(
                    f"Module {name} is declared for pack {declared_module['pack']}; "
                    f"render it with --pack {declared_module['pack']}."
                )
        if header_path.exists():
            if pack_value is not None:
                raise ValueError(f"Module {name} already exists; refusing to overwrite it with a pack template.")
            synchronize_module_makefile(project_dir)
            print(f"Module already exists; synchronized build integration: {name}")
            return 0

        source_name_conflicts = [
            path
            for path in project_dir.rglob(f"{name}.c")
            if path.resolve() != source_path.resolve()
        ]
        if source_name_conflicts:
            print(
                f"Error: module source name conflicts with existing file: {source_name_conflicts[0]}",
                file=sys.stderr,
            )
            return 2

        if pack_value is None:
            header_text = module_header_text(name)
            source_text = module_source_text(name)
            rendered_pack = None
        else:
            header_text, source_text, rendered_pack = pack_module_text(project_dir, name, pack_value)
        header_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with header_path.open("x", encoding="utf-8") as output:
                output.write(header_text)
            with source_path.open("x", encoding="utf-8") as output:
                output.write(source_text)
        except FileExistsError as error:
            raise ValueError(f"Module {name} already exists; refusing to overwrite it.") from error
        synchronize_module_makefile(project_dir)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    if rendered_pack:
        print(f"Created {rendered_pack} module header: {header_path}")
        print(f"Created {rendered_pack} module source: {source_path}")
    else:
        print(f"Created module header: {header_path}")
        print(f"Created module source: {source_path}")
    print(f"Synchronized build integration: {project_dir / MODULES_MAKEFILE}")
    return 0


def user_code_region(text: str, label: str) -> tuple[int, int]:
    begin_marker = f"/* USER CODE BEGIN {label} */"
    end_marker = f"/* USER CODE END {label} */"
    if text.count(begin_marker) != 1 or text.count(end_marker) != 1:
        raise ValueError(f"Expected exactly one CubeMX USER CODE BEGIN/END {label} region.")
    begin = text.index(begin_marker) + len(begin_marker)
    end = text.index(end_marker)
    if begin > end:
        raise ValueError(f"CubeMX USER CODE {label} region is malformed.")
    return begin, end


def main_module_marker(name: str, block: str, edge: str) -> str:
    suffix = "BEGIN" if edge == ">>>" else "END"
    return f"/* {edge} CODEX STM32 MODULE {name} {block} {suffix} */"


def main_module_block(name: str, block: str, statement: str, newline: str) -> str:
    begin = main_module_marker(name, block, ">>>")
    end = main_module_marker(name, block, "<<<")
    return newline.join([begin, statement, end])


def synchronize_main_user_block(text: str, label: str, name: str, block: str, statement: str, newline: str) -> str:
    begin, end = user_code_region(text, label)
    region = text[begin:end]
    marker_begin = main_module_marker(name, block, ">>>")
    marker_end = main_module_marker(name, block, "<<<")
    begin_count = region.count(marker_begin)
    end_count = region.count(marker_end)
    if begin_count != end_count or begin_count > 1:
        raise ValueError(f"Codex integration markers for module {name} in USER CODE {label} are incomplete.")
    managed = main_module_block(name, block, statement, newline)
    if begin_count == 0:
        if statement in text:
            raise ValueError(
                f"main.c already contains {statement!r} outside Codex's managed marker; refusing to duplicate it."
            )
        if label == "Includes" and f'#include "{name}.h"' in text:
            raise ValueError(f"main.c already includes {name}.h outside Codex's managed marker; refusing to duplicate it.")
        if region and not region.endswith(("\n", "\r")):
            region += newline
        region += managed + newline
    else:
        managed_begin = region.index(marker_begin)
        managed_end = region.index(marker_end, managed_begin)
        if managed_end < managed_begin:
            raise ValueError(f"Codex integration markers for module {name} in USER CODE {label} are malformed.")
        region = region[:managed_begin] + managed + region[managed_end + len(marker_end) :]
    return text[:begin] + region + text[end:]


def synchronize_main_module(project_dir: Path, name: str) -> None:
    main_path = project_dir / "Src" / "main.c"
    if not main_path.is_file():
        raise ValueError(f"Expected CubeMX main source at: {main_path}")
    original = main_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    updated = synchronize_main_user_block(
        original,
        "Includes",
        name,
        USER_CODE_BLOCKS["Includes"],
        f'#include "{name}.h"',
        newline,
    )
    updated = synchronize_main_user_block(
        updated,
        "2",
        name,
        USER_CODE_BLOCKS["2"],
        f"{name}_init();",
        newline,
    )
    updated = synchronize_main_user_block(
        updated,
        "3",
        name,
        USER_CODE_BLOCKS["3"],
        f"{name}_process();",
        newline,
    )
    if updated != original:
        main_path.write_text(updated, encoding="utf-8")


def run_integrate(args: argparse.Namespace) -> int:
    try:
        name = validated_module_name(args.name)
        project_dir = Path(args.project_dir).expanduser().resolve()
        if not (project_dir / "Makefile").is_file():
            raise ValueError(f"Expected a Makefile project at: {project_dir}")
        header_path = project_dir / "App" / "Inc" / f"{name}.h"
        source_path = project_dir / "App" / "Src" / f"{name}.c"
        if not header_path.is_file() or not source_path.is_file():
            raise ValueError(f"Module {name} must have both App/Inc/{name}.h and App/Src/{name}.c before integration.")
        synchronize_main_module(project_dir, name)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Integrated module into CubeMX user-code blocks: {name}")
    return 0


def find_artifacts(project_dir: Path) -> list[Path]:
    extensions = {".elf", ".bin", ".hex", ".map"}
    artifacts = [path for path in project_dir.rglob("*") if path.is_file() and path.suffix.lower() in extensions]
    return sorted(artifacts, key=lambda path: (path.suffix, str(path)))


def run_build(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).expanduser().resolve()
    makefile = project_dir / "Makefile"
    if not makefile.is_file():
        print(f"Error: expected a Makefile project at: {project_dir}", file=sys.stderr)
        return 2
    try:
        load_project_provenance(project_dir)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    try:
        toolchain = discover_tools(args.cubemx, args.cubeide)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    if not toolchain.gcc or not toolchain.make:
        print("Error: CubeIDE ARM GCC and Make are required. Run doctor --strict for details.", file=sys.stderr)
        return 2

    print("Verified project provenance before compilation.")
    jobs = args.jobs or min(os.cpu_count() or 1, 8)
    result = subprocess.run(
        [toolchain.make, "-C", str(project_dir), f"-j{jobs}"],
        cwd=project_dir,
        env=build_environment(toolchain),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        print(f"Build failed with exit code {result.returncode}.", file=sys.stderr)
        return result.returncode or 1

    artifacts = find_artifacts(project_dir)
    print("Build succeeded.")
    if artifacts:
        print("Artifacts:")
        for artifact in artifacts:
            print(f"- {artifact}")
    else:
        print("Warning: Make completed but no .elf, .bin, .hex, or .map artifact was found.", file=sys.stderr)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--cubemx", help="Override the discovered STM32CubeMX executable path.")
    root.add_argument("--cubeide", help="Override the discovered STM32CubeIDE executable path.")
    commands = root.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Inspect STM32CubeMX and CubeIDE build-tool availability.")
    doctor.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    doctor.add_argument(
        "--strict", action="store_true", help="Fail if CubeMX, ARM GCC, Make, or pypdf is missing."
    )

    generate = commands.add_parser("generate", help="Generate a new legacy STM32CubeMX project.")
    generate.add_argument("--mcu", required=True, help="Exact CubeMX MCU identifier, for example STM32F401RETx.")
    generate.add_argument("--name", required=True, help="New project directory and project name.")
    generate.add_argument("--output-dir", required=True, help="Existing parent directory for the new project.")
    generate.add_argument("--board-profile", required=True, help="Evidence-backed board-profile.json for this manual-driven project.")
    generate.add_argument("--manual", required=True, help="Exact user-provided manual PDF cited by --board-profile.")
    generate.add_argument("--plan", required=True, help="Approved configuration-plan.json for this new project.")
    generate.add_argument("--dry-run", action="store_true", help="Print the CubeMX script.")

    module = commands.add_parser("module", help="Create an App module and synchronize its Makefile integration.")
    module.add_argument("--project-dir", required=True, help="CubeMX-generated Makefile project directory.")
    module.add_argument("--name", required=True, help="Lowercase application module name, for example motor_control.")
    module.add_argument("--pack", help="Selected capability pack whose .h/.c templates will render this new module.")

    integrate = commands.add_parser("integrate", help="Connect an App module to CubeMX main.c user-code regions.")
    integrate.add_argument("--project-dir", required=True, help="CubeMX-generated Makefile project directory.")
    integrate.add_argument("--name", required=True, help="Existing lowercase App module name, for example motor_control.")

    build = commands.add_parser("build", help="Compile a CubeMX-generated Makefile project with CubeIDE tools.")
    build.add_argument("--project-dir", required=True, help="Project directory containing Makefile.")
    build.add_argument("--jobs", type=int, help="Parallel Make jobs; defaults to up to 8 logical CPUs.")
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "doctor":
        try:
            return report_tools(discover_tools(args.cubemx, args.cubeide), args.json, args.strict)
        except RuntimeError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
    if args.command == "generate":
        return run_generate(args)
    if args.command == "build":
        return run_build(args)
    if args.command == "module":
        return run_module(args)
    if args.command == "integrate":
        return run_integrate(args)
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
