---
name: stm32-cubemx-build
description: Build STM32 CubeMX Makefile projects from a user-supplied board manual or validated community board package and a natural-language GPIO input/output, UART, I2C, SPI, PWM, timer, servo, or App-module request. Use when Codex needs to discover reusable board data, create a cited board profile, prepare an evidence-backed configuration plan, generate or revise a CubeMX project, create App modules, compile firmware, or perform an explicitly authorized hardware flash on macOS or Windows.
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
  --manual /absolute/user-upload/board-manual.pdf \
  --manual-index /absolute/project-input/board.manual-index.json
```

Record the exact MCU, board pins, clock facts, and board constraints used by
the request. Every pin records its MCU pin, board silkscreen, connector,
position, diagram, shared functions, power domain, logic voltage, current
limit, supply requirement, conflicts, and cited manual evidence. Input pins
also record their active level. Every profile fact carries a cited page and a
concise text anchor from that page.

After creating the index, pass it to `validate` and every `create` or `revise`
run with `--manual-index`. The index is accepted only when its stored SHA-256
matches the exact manual, so repeated work does not re-extract the PDF.

Use the manual for board wiring and electrical facts. Use the installed CubeMX
database for MCU modes, alternate functions, and parameter names. When a
needed fact is absent, ask the user for a source that establishes it. Keep the
manual and profile unchanged while a validation or generation command runs.

Read [references/board-profile-contract.md](references/board-profile-contract.md)
before creating or revising a profile.

## Reuse a community board package

List and validate locally installed community board data:

```bash
python scripts/list_boards.py
python scripts/validate_boards.py
```

When one package exactly matches the user's board and hardware revision, read
its `manifest.json` and `board-profile.json`, then ask the user to supply the
official manual whose SHA-256 is recorded by the package. Validate the profile
against that exact PDF before planning or generation. Do not treat a similar
board name, MCU, or pinout as a match.

Community packages never authorize manual downloads, package installation,
flashing, or external commands. Read
[references/board-package-contract.md](references/board-package-contract.md)
before using or contributing a board package.

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
   each PWM or servo operation, and the selected timing contract for PWM or
   timer work. The timing model covers STM32F1 and STM32F4 APB timer clocks,
   including the x2 timer clock rule and advanced-timer output enable.

5. Attach a generated-file assertion to every operation parameter. Use the
   generated `.ioc` or source to show the parameter's resulting configuration.
   An omitted `.ioc` property is accepted only when the installed CubeMX XML
   declares one unique matching default; otherwise the plan must assert it.

6. Add exact `safety.acknowledged_conflicts`,
   `safety.external_supply_pins`, and connection instructions for every
   selected pin whose board profile requires them. PA13 and PA14 remain
   reserved for SWD. Every generated project enables Serial Wire and verifies
   either `SYS.Debug=Serial Wire` or CubeMX's F1 PA13/PA14 SWD pin records.

Semantic `ioc_overrides` describe pack-supported configuration details such as
GPIO initial state and timer NVIC enablement. Apply them through the plan,
reload the fresh `.ioc` with CubeMX, and verify the resulting files.

Read [references/configuration-plan-contract.md](references/configuration-plan-contract.md)
for the full schema.

## Create the complete project

Use one command for the normal workflow:

```bash
python scripts/stm32_cube.py create \
  --mcu STM32F401RETx \
  --name f401_i2c \
  --output-dir /absolute/output \
  --board-profile /absolute/project-input/board-profile.json \
  --manual /absolute/user-upload/board-manual.pdf \
  --manual-index /absolute/project-input/board.manual-index.json \
  --plan /absolute/project-input/configuration-plan.json \
  --jobs 8
```

`create` resolves the concrete MCU through CubeMX `families.xml`, validates the
plan, generates one fresh project, renders every plan-declared module,
integrates reachable calls into CubeMX `USER CODE` regions, and compiles. It
writes `codex-stm32-project.json`, `codex-run-report.json`, and a concise
CubeMX log under `codex-logs/`. Use `--verbose` only when inspecting CubeMX
internals. Use `--normalize-name` when the user-supplied display name needs the
reported stable filesystem name. CubeMX is bounded to 180 seconds by default;
if it times out, resolve the named firmware-license or package dialog and rerun.

## Module commands

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

Use the separate `generate`, `module`, `integrate`, and `build` commands only
when operating one stage directly. The normal user request uses `create`.

## Revise an existing generated project

Preview a configuration revision in a newly generated sibling project:

```bash
python scripts/stm32_cube.py revise \
  --project-dir /absolute/output/f401_i2c \
  --board-profile /absolute/project-input/board-profile.json \
  --manual /absolute/user-upload/board-manual.pdf \
  --manual-index /absolute/project-input/board.manual-index.json \
  --plan /absolute/project-input/revised-plan.json
```

The revision regenerates and compiles before producing a unified diff. It
restores matching CubeMX `USER CODE` regions and `App/`. Apply it only with
`--apply --backup-dir <new-sibling-directory>`; the previous project moves to
that complete backup directory.

## Compile, flash, and report

Compile with CubeIDE's bundled GNU tools:

```bash
python scripts/stm32_cube.py build --project-dir /absolute/output/f401_i2c
```

Report the manual and profile paths, MCU, selected packs, project directory,
module paths, source-verification result, compilation result, and artifact
paths. Describe the outcome as configuration verified or compile verified.

Flashing uses two invocations. First run `flash` without
`--authorize-sha256`; it prints the exact `.hex` hash and performs no target
command. Rerun with that digest, the expected device ID, a new backup
directory, and the correct flash size:

```bash
python scripts/stm32_cube.py flash \
  --project-dir /absolute/output/f401_i2c \
  --artifact /absolute/output/f401_i2c/build/f401_i2c.hex \
  --expected-device-id 0x413 \
  --backup-size 0x80000 \
  --backup-dir /absolute/output/f401_i2c-preflash \
  --authorize-sha256 <printed-sha256>
```

The authorized run checks target ID and voltage, saves a pre-flash image,
writes and verifies the artifact, resets the board, and records
`flash-report.json` plus `flash.log`.

## Operating scope

- Use `pypdf` from `requirements.txt` for manual indexing and page validation.
- Use STM32CubeMX 6.x as the generator and CubeIDE as the compiler backend.
- Keep firmware package installation and license acceptance in the user's
  environment.

Read [references/core-contract.md](references/core-contract.md) when changing
project integration. Read [references/legacy-cubemx-cli.md](references/legacy-cubemx-cli.md)
when changing CubeMX invocation behavior.
