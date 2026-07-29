# STM32 Manual-Driven Codex Skill

Turn a board manual and a plain-language STM32 request into a new CubeMX
Makefile project, an App module, and compiled firmware artifacts.

`stm32-cubemx-build` is a Codex Skill for GPIO output, UART, I2C, SPI, PWM,
timer, and application-module work. CubeMX generates the project; CubeIDE
provides the Arm compiler and Make tools. The normal workflow runs from the
command line on macOS or Windows.

## What the Skill produces

- a page-cited `board-profile.json` for the MCU, board pins, clocks, and
  board constraints used by the request;
- a `configuration-plan.json` that maps the request to local CubeMX settings;
- a fresh CubeMX Makefile project with `.ioc`, HAL/CMSIS source, and build
  files;
- pack-backed or generic App modules in `App/Inc` and `App/Src`;
- integration calls in CubeMX `USER CODE` regions; and
- a compilation result with the generated artifacts reported by the toolchain.

## Included packs

| Pack | Purpose | Generated App API |
| --- | --- | --- |
| `gpio` | Push-pull digital output | Write and toggle a documented pin |
| `uart` | Asynchronous serial port | Send and receive with an explicit timeout |
| `i2c` | I2C bus | Read device registers through an HAL handle |
| `spi` | 8-bit full-duplex master bus | Transfer buffers through an HAL handle |
| `pwm` | Timer PWM output | Set duty cycle for a selected channel |
| `timer` | Periodic timer dispatch | Consume timer ticks from the main loop |

## Workflow

1. Upload the board manual and describe the firmware task.
2. Build a board profile from page-cited manual facts. Each fact records a
   concise anchor from the cited page.
3. Select the required packs and create a configuration plan from the board
   profile and the installed CubeMX MCU database.
4. Generate the new project and verify the requested pins, parameters, and
   source assertions in CubeMX output.
5. Render the selected App module, integrate it into `main.c`, and compile.

The local PDF index contains extracted manual pages. Keep it as a local working
artifact; the shareable board profile contains citations and short anchors.

Each plan uses a new output directory. Existing projects stay in place, while
generated project code comes from CubeMX and application code lives in `App/`
and CubeMX user-code regions.

## Install in Codex

Copy the inner `stm32-cubemx-build` directory into your Codex skills folder:

- macOS: `~/.codex/skills/stm32-cubemx-build`
- Windows: `%USERPROFILE%\.codex\skills\stm32-cubemx-build`

Then upload a board manual and ask, for example:

> Use `$stm32-cubemx-build` to read this board manual and create a 400 kHz I2C
> temperature-sensor project. Use documented available pins, create a
> `sensor_service` App module, and compile it.

## Prerequisites

1. STM32CubeMX 6.x.
2. STM32CubeIDE, which supplies the Arm GCC and Make tools.
3. Python 3 and `pypdf`:

   ```bash
   python -m pip install -r stm32-cubemx-build/requirements.txt
   ```

4. The STM32Cube firmware package for the selected MCU family.

Check the environment with:

```bash
python stm32-cubemx-build/scripts/stm32_cube.py doctor --strict
```

On Windows, provide custom application locations as leading options:

~~~powershell
python stm32-cubemx-build/scripts/stm32_cube.py --cubemx "C:\path\to\STM32CubeMX.exe" --cubeide "C:\path\to\stm32cubeide.exe" doctor --strict
~~~

Use the same `--cubemx` and `--cubeide` options with `generate` and `build`.

## Windows end-to-end check

`scripts/windows_smoke.ps1` runs the complete local workflow from a manual,
board profile, and configuration plan: environment check, project generation,
App module creation, integration, and compilation.

~~~powershell
$skill = "$env:USERPROFILE\.codex\skills\stm32-cubemx-build\scripts\windows_smoke.ps1"
& $skill -Manual "C:\work\board-manual.pdf" -BoardProfile "C:\work\board-profile.json" -Plan "C:\work\configuration-plan.json" -Mcu "STM32F401RETx" -OutputDir "C:\work\stm32-output" -ProjectName "f401_windows_smoke"
~~~

`WINDOWS_SMOKE_PASS` reports a complete generation-and-compilation run. Flash,
debug, and on-board measurements belong to a separate hardware run.

## Result vocabulary

The Skill reports results at the level it has completed:

- **Configuration verified**: CubeMX output matches the plan's requested pins,
  parameters, and assertions.
- **Compile verified**: CubeIDE's toolchain builds the generated source.
- **Hardware run**: a board has been flashed and exercised through a dedicated
  on-board workflow.

## Validation in this release

- 72 deterministic tests cover profile validation, configuration planning,
  generation provenance, pack rendering, integration, and build preparation.
- All six built-in pack contracts validate.
- The current source completed an I2C flow with CubeMX generation, App module
  integration, and compilation to `.elf`, `.bin`, and `.hex` artifacts.

See [VALIDATION.md](VALIDATION.md) for the concise validation record and
[CONTRIBUTING.md](CONTRIBUTING.md) for the community pack model.

## Development check

From the repository root:

```bash
python -m unittest discover -s tests -v
python stm32-cubemx-build/scripts/validate_packs.py
python stm32-cubemx-build/scripts/stm32_cube.py doctor --strict
```

GitHub Actions runs the deterministic tests, pack validation, and Python
compile check on Linux, macOS, and Windows.

The complete operating workflow is in
[`stm32-cubemx-build/SKILL.md`](stm32-cubemx-build/SKILL.md). The detailed data
contracts live in `stm32-cubemx-build/references/`.

## License

Apache-2.0. See [LICENSE](LICENSE).
