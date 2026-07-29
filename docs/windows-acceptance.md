# Windows deployment and acceptance

## Product form

Install `stm32-cubemx-build` as a local Skill in the Codex desktop app. Codex
drives the workflow; STM32CubeMX generates the project and STM32CubeIDE supplies
Arm GCC and Make. VS Code is optional for viewing generated files.

## Prerequisites

Install these components before testing:

1. Codex desktop app for Windows.
2. Python 3.11 or newer.
3. STM32CubeMX 6.x and the firmware package for the selected MCU family.
4. STM32CubeIDE with its bundled GNU tools.

Copy the repository's inner `stm32-cubemx-build` directory to:

```text
%USERPROFILE%\.codex\skills\stm32-cubemx-build
```

Install the Python dependency from PowerShell:

~~~powershell
python -m pip install -r "$env:USERPROFILE\.codex\skills\stm32-cubemx-build\requirements.txt"
~~~

Restart Codex after copying or updating the Skill.

## Inputs

Prepare these files in a private working directory:

- the board manual PDF;
- the validated `board-profile.json` derived from that exact PDF;
- the approved `configuration-plan.json`;
- a new output directory and unused project name;
- the matching `*.manual-index.json`, created once and reused for this exact PDF.

The selected MCU, pins, peripheral instances, modes, parameters, and module
bindings must match the manual, board profile, plan, and installed CubeMX
database.

## End-to-end command

Run this command from PowerShell. Replace each example path with the local test
paths:

~~~powershell
$skill = "$env:USERPROFILE\.codex\skills\stm32-cubemx-build\scripts\windows_smoke.ps1"
& $skill `
  -Manual "C:\work\board-manual.pdf" `
  -ManualIndex "C:\work\board.manual-index.json" `
  -BoardProfile "C:\work\board-profile.json" `
  -Plan "C:\work\configuration-plan.json" `
  -Mcu "STM32F103ZETx" `
  -OutputDir "C:\work\stm32-output" `
  -ProjectName "servo_windows_smoke"
~~~

If CubeMX or CubeIDE uses a custom location, add:

~~~powershell
  -CubeMX "C:\path\to\STM32CubeMX.exe" `
  -CubeIDE "C:\path\to\stm32cubeide.exe"
~~~

The plan declares all modules and bindings. The harness calls `create` once;
it does not repeat module, integration, or build commands.

## Codex test prompt

Paste this into the Windows Codex desktop app after attaching the manual:

> Install this repository's inner `stm32-cubemx-build` folder as a local Skill
> and restart Codex. Use `$stm32-cubemx-build` to read the attached board manual
> and create a new 50 Hz servo project. Resolve the concrete MCU and a documented
> timer-channel pin, keep SWD enabled, and use the board's physical connector and
> electrical data. Create one `servo` App module, integrate it into reachable
> CubeMX `USER CODE` regions, and compile with the CubeIDE toolchain. Reuse the
> manual index after it is created. Use the one-shot `create` workflow and report
> each stage's time, the `.ioc`, `.c/.h`, `.elf/.bin/.hex`, connection guide, and
> `codex-run-report.json`. Stop after compilation unless I explicitly authorize
> a specific artifact hash for flashing.

## Acceptance result

A complete Windows acceptance run produces:

1. `WINDOWS_SMOKE_PASS` in PowerShell.
2. A new CubeMX project with one root `.ioc` file.
3. Generated module files under `App\Inc` and `App\Src`.
4. Module calls inside the expected `main.c` `USER CODE` regions.
5. A successful Make build with `.elf`, `.bin`, `.hex`, or `.map` artifacts.
6. `codex-run-report.json` with generation, module, and build stage timings.

Record the Codex, Python, CubeMX, CubeIDE, and firmware-package versions with
the PowerShell output, report, and artifact paths. An authorized hardware run
also records the artifact hash, target ID, voltage, pre-flash backup, verify
status, and reset status.
