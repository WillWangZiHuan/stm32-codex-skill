---
name: stm32-cubemx-build
description: Build STM32 CubeMX Makefile projects from a user-supplied board manual and natural-language GPIO-output, UART, I2C, SPI, PWM, timer, or App-module request. Use when Codex needs to create a cited board profile, an evidence-backed configuration plan, a new CubeMX project, App modules, and a compilation result on macOS or Windows.
---

# STM32 Manual-Driven Project Builder

Build a fresh STM32 Makefile project from the user's manual and request. Use
CubeMX for project generation and CubeIDE's bundled toolchain for compilation.

## Inputs

Collect these inputs before configuration:

1. A board manual PDF supplied by the user.
2. A concrete requested behavior and acceptance criteria.
3. A new output directory and project name.
4. The matching STM32Cube firmware package in the local CubeMX installation.

Run environment discovery with the same Python interpreter that will run the
workflow:

```bash
python scripts/stm32_cube.py doctor --strict
```

On Windows, pass custom CubeMX and CubeIDE locations before the subcommand and
reuse those options for `generate` and `build`:

~~~powershell
python scripts/stm32_cube.py --cubemx "C:\path\to\STM32CubeMX.exe" --cubeide "C:\path\to\stm32cubeide.exe" doctor --strict
~~~

## Build the board profile

Create a page-numbered local index, read the relevant manual pages, and create
`board-profile.json`:

```bash
python scripts/board_profile.py index-pdf \
  --manual /absolute/user-upload/board-manual.pdf \
  --output /absolute/project-input/board.manual-index.json

python scripts/board_profile.py validate \
  --profile /absolute/project-input/board-profile.json \
  --manual /absolute/user-upload/board-manual.pdf
```

Record the exact MCU, board pins, clock facts, and board constraints used by
the request. Every profile fact carries a cited page and a concise text anchor
from that page. The local index contains extracted manual text; keep it in the
project's private working area. The profile stores the shareable citations and
anchors.

Use the manual for board wiring and electrical facts. Use the installed CubeMX
database for MCU modes, alternate functions, and parameter names. When a
needed fact is absent, ask the user for a source that establishes it. Keep the
manual and profile unchanged while a validation or generation command runs.

Read [references/board-profile-contract.md](references/board-profile-contract.md)
before creating or revising a profile.

## Prepare the configuration plan

Create one new project directory per plan. Treat work on an existing `.ioc`
project as a separate request.

1. List and validate the installed capability packs:

   ```bash
   python scripts/list_packs.py
   python scripts/validate_packs.py
   ```

2. Read the `PACK.md` for every selected pack. Inspect the local CubeMX MCU/IP
   XML for the exact peripheral instance, mode, signal, and parameter names.

3. Create `configuration-plan.json` with the selected pack IDs, available
   profile pins, generated-file assertions, and the required module bindings.
   Map each operation, direct pin assignment, and semantic `.ioc` override to
   its owning pack.

4. Include `SCL` and `SDA` signals for each I2C operation, an output pin for
   each PWM operation, and the selected timing contract for PWM or timer work.
   The current timing model evaluates STM32F4 `TIM1`–`TIM14` with CubeMX's
   generated unprescaled APB clocks. Begin another timer family or clock tree
   with its verified timing model.

5. Attach a generated-file assertion to every operation parameter. Use the
   generated `.ioc` or source to show the parameter's resulting configuration.

Semantic `ioc_overrides` describe pack-supported configuration details such as
GPIO initial state and timer NVIC enablement. Apply them through the plan,
reload the fresh `.ioc` with CubeMX, and verify the resulting files.

Read [references/configuration-plan-contract.md](references/configuration-plan-contract.md)
for the full schema.

## Generate the project

Run generation with the manual, profile, and plan:

```bash
python scripts/stm32_cube.py generate \
  --mcu STM32F401RETx \
  --name f401_i2c \
  --output-dir /absolute/output \
  --board-profile /absolute/project-input/board-profile.json \
  --manual /absolute/user-upload/board-manual.pdf \
  --plan /absolute/project-input/configuration-plan.json
```

Generation creates the CubeMX project, evaluates plan assertions in generated
files, and writes `codex-stm32-project.json` beside the project. That record
links the project to the manual, board profile, plan, selected pack files,
generated identifiers, `.ioc`, Makefile, and generated build inputs. It
supports repeatable module rendering and build preparation while leaving
`App/` and CubeMX `USER CODE` regions available for application work.

## Create and integrate App modules

Use a generic module for request-specific application logic:

```bash
python scripts/stm32_cube.py module \
  --project-dir /absolute/output/f401_i2c \
  --name sensor_service
```

For a pack template, declare the module name, pack ID, and bindings in the
configuration plan before generation. After generation, render it with:

```bash
python scripts/stm32_cube.py module \
  --project-dir /absolute/output/f401_i2c \
  --name status_output \
  --pack gpio
```

Pack bindings use identifiers found in CubeMX-generated configuration source.
Render modules in `App/Inc` and `App/Src`, then integrate them with:

```bash
python scripts/stm32_cube.py integrate \
  --project-dir /absolute/output/f401_i2c \
  --name sensor_service
```

Integration manages three CubeMX user-code regions:

- `USER CODE BEGIN Includes` for the include;
- `USER CODE BEGIN 2` for initialization; and
- `USER CODE BEGIN 3` for the main-loop process call.

For timer modules, route periodic dispatch through the project's single
`HAL_TIM_PeriodElapsedCallback` owner.

## Compile and report

Compile with CubeIDE's bundled GNU tools:

```bash
python scripts/stm32_cube.py build --project-dir /absolute/output/f401_i2c
```

Report the manual and profile paths, MCU, selected packs, project directory,
module paths, source-verification result, compilation result, and artifact
paths. Describe the outcome as configuration verified or compile verified.
Flash, debug, and on-board measurement continue in a dedicated hardware run.

## Operating scope

- Use `pypdf` from `requirements.txt` for manual indexing and page validation.
- Use STM32CubeMX 6.x as the generator and CubeIDE as the compiler backend.
- Keep firmware package installation and license acceptance in the user's
  environment.

Read [references/core-contract.md](references/core-contract.md) when changing
project integration. Read [references/legacy-cubemx-cli.md](references/legacy-cubemx-cli.md)
when changing CubeMX invocation behavior.
