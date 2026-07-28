---
name: stm32-cubemx-build
description: Build compile-only STM32 Makefile projects from an evidence-backed board manual and natural-language GPIO-output, UART, I2C, SPI, PWM, timer, or App-module request. Use when Codex must turn a user-supplied STM32 board PDF into a validated board profile, configure a new CubeMX project without CubeIDE GUI use, create safe App C modules, integrate them in CubeMX user-code regions, and compile on macOS or Windows. Never use for flashing, live debugging, or claims that firmware ran on hardware.
---

# STM32 Manual-Driven Project Builder

Generate and compile firmware only. This Skill does not flash, debug, reset, or
claim a target board ran the result.

## Hardware facts are evidence, not model memory

For a manual-driven task, require all of the following before configuring a
project:

1. The user-supplied board manual PDF.
2. A precise requested behavior and acceptance criteria.
3. A new output directory and project name.

Use `scripts/board_profile.py index-pdf` to make a local page-numbered
`*.manual-index.json` working index, then read the relevant manual pages. It
contains extracted manual text, so keep it private and never commit it; the
required suffix is ignored by this repository. Create `board-profile.json` as a
project artifact, with an exact manual SHA-256, page citation, and short
page-local text anchor for every MCU, pin, clock, and electrical fact used.
Copy each anchor from the indexed cited page; the validator verifies it occurs
there after standard text normalization. If a required fact has no textual
anchor, stop and request a document that states it rather than guessing from a
diagram. If indexing reports that the PDF has no extractable text, or
validation identifies a cited page with no extractable text, request a
text-accessible source for that fact; do not turn a visual interpretation into
a profile claim. Run:

```bash
python scripts/board_profile.py validate \
  --profile /absolute/project-input/board-profile.json \
  --manual /absolute/user-upload/board-manual.pdf
```

For each command, treat the profile and manual as immutable input snapshots:
the validator reads each file once, validates and hashes those exact bytes, and
generation records the profile snapshot's hash. Do not replace either input
while the command is running.

Do not infer a board's wiring from its name, a chip datasheet, online pinouts,
or a similar board. The manual controls board-level truth; the installed CubeMX
MCU database controls valid alternate functions and IP parameters. If either
source is missing or conflicts, stop and explain what is missing.

Read [references/board-profile-contract.md](references/board-profile-contract.md)
before creating or changing a profile.

At the start of **every audit pass**—a feature audit, release audit, or repeat
self-audit—first ask: **“目前最大的问题是什么？” (“What is the largest problem
right now?”)** Then identify the single current problem most likely to make this
pipeline incorrect, unsafe, or misleading. For that one problem, record the
evidence, root cause, smallest in-scope corrective action, and the exact
verification result that will prove the action worked. Execute and verify that
action before adding a lower-priority capability. Start the next audit pass by
asking the question again; an idea to solve it later is not a resolution. If the
problem cannot be resolved within these boundaries, stop and report the exact
remaining gap rather than treating it as closed.

## New-project configuration workflow

This Skill configures **new** projects only. Never alter an existing user
project's `.ioc` or regenerate it without separate, explicit authorization.
`generate` requires `--board-profile`, `--manual`, and `--plan` together; it
has no evidence-free baseline-project mode.
For a new project, an approved plan may contain a restricted `ioc_overrides`
entry when direct CubeMX commands cannot express an exact local setting. The
entry must use a semantic kind declared by a selected capability pack, must
remain tied to a planned GPIO output or timer instance, and must have an exact
post-generation `$IOC` assertion. The core applies it only to that
just-created project, reloads it through `config load`, and re-verifies
generated files; arbitrary `.ioc` keys are never accepted.

The pack contract also sets the minimum pin shape for each operation before
CubeMX starts. In this first usable scope, an I2C operation must explicitly
include its exact `<instance>_SCL` and `<instance>_SDA` signals, a PWM
operation must explicitly include at least one output pin, and a base timer
may use no physical pin. Do not rely on CubeMX defaults to fill in omitted bus
or output pins.

1. Check tools:

   ```bash
   python scripts/stm32_cube.py doctor --strict
   ```

   Run it with the same Python interpreter that will run `generate`; strict
   mode also checks the required `pypdf` package before any manual is read.

   On Windows, `doctor` checks the conventional all-user installation paths.
   If either application was installed into a user-specific or custom folder,
   do not guess a hidden path. Supply both executable paths before the
   subcommand instead:

   ~~~powershell
   python scripts/stm32_cube.py --cubemx "C:\path\to\STM32CubeMX.exe" --cubeide "C:\path\to\stm32cubeide.exe" doctor --strict
   ~~~

   Keep the same leading `--cubemx` and `--cubeide` options on later
   `generate` and `build` commands. The CubeIDE path is also the source of the
   bundled Arm GCC and Make tools. `doctor` rejects an explicit path that is
   missing, is a directory, or is not executable; it must not report that
   broken override as a healthy toolchain.

   To close a Windows-host validation gap, use
   scripts/windows_smoke.ps1 with a real manual, board profile, and
   configuration plan. It checks tools, creates one fresh project, creates and
   safely integrates one App module, then compiles. It refuses an existing
   project directory and never flashes or tests hardware. Supply -Pack only
   when the plan declares that exact module for that pack.

2. Discover available capability packs:

   ```bash
   python scripts/list_packs.py
   python scripts/validate_packs.py
   ```

3. Read every selected `packs/<id>/PACK.md`. Inspect the local CubeMX MCU/IP
   XML for the exact instance, mode, pin signal, and parameter names. Do not
   invent a generic GPIO, UART, I2C, SPI, PWM, or timer setting.
   Before CubeMX is launched, `generate` independently rejects an operation
   mode that is not a concrete local IP-mode `Name` or `UserName`, and
   rejects an operation pin/signal pair that the selected MCU's local XML does
   not expose, or an operation parameter key absent from that IP's local mode
   database. A category such as `Base` is not an acceptable timer-mode
   substitute. Key presence does not validate a conditional value; every
   operation parameter must carry its own generated-file assertion.

4. Create an approved `configuration-plan.json`. It must list only
   evidence-backed `available` profile pins, a non-empty `packs` list of the
   selected capability-pack IDs, and both `.ioc` and generated-source
   assertions. Every peripheral operation, direct pin assignment, and semantic
   override must name the selected pack that owns it; its instance prefix or
   direct signal must match that pack's machine-checked resource declaration.
   Every `operations[].parameters[]` entry must attach one `verification`
   object that proves its effect in the generated `.ioc` or source file.
   Every `pwm` or `timer` operation must also declare the mandatory
   `timing` contract (target rate, tolerance, timer-input rate, and the two
   counter parameter names). The current proof model is intentionally limited
   to STM32F4 `TIM1`–`TIM14` with an unprescaled generated APB clock:
   it checks the post-generation `.ioc` clock frequencies and exact integer
   counter math. Stop for a custom/prescaled clock tree, LPTIM, or another MCU
   family; do not state a PWM frequency or timer period without that proof.
   If the request needs a pack-rendered App module, its exact module name, pack
   ID, and template bindings must also be declared here, before generation. The
   core verifies that each selected manifest is installed and contract-valid;
   that provenance check never replaces the evidence checks.
   Read
   [references/configuration-plan-contract.md](references/configuration-plan-contract.md).

5. Generate and source-verify the new project:

   ```bash
   python scripts/stm32_cube.py generate \
     --mcu STM32F401RETx \
     --name f401_i2c \
     --output-dir /absolute/output \
     --board-profile /absolute/project-input/board-profile.json \
     --manual /absolute/user-upload/board-manual.pdf \
     --plan /absolute/project-input/configuration-plan.json
   ```

   The command refuses an existing project directory. A successful CubeMX exit
   is insufficient: every plan assertion, including every parameter-attached
   assertion, must be found in the generated files. For PWM/timer requests the
   generated clock-domain values and calculated rate must also satisfy the
   approved `timing` contract.
   If any assertion fails, report configuration failure; do not say the board is
   configured. On success, it writes `codex-stm32-project.json` beside the
   generated files. It contains the exact manual, board-profile, and plan
   hashes, selected-pack fingerprints, the plan-declared pack modules, a frozen
   inventory of C identifiers, and a
   fingerprint of CubeMX configuration-bearing source/header content outside
   user-code regions. It also freezes the exact root `.ioc` hash plus the
   `MxCube.Version`, `MxDb.Version`, and firmware-package facts that CubeMX
   wrote there. It never copies manual text; do not hand-create or edit it.

## App modules and safe integration

Create a generic application module only when no capability-pack template is
needed:

```bash
python scripts/stm32_cube.py module \
  --project-dir /absolute/output/f401_i2c \
  --name sensor_service
```

For a selected capability pack, declare the module in the approved
`configuration-plan.json` before generation, instead of choosing its resources
afterwards. For example:

```json
{
  "modules": [
    {
      "name": "status_output",
      "pack": "gpio",
      "bindings": {
        "GPIO_PORT": "GPIOA",
        "GPIO_PIN": "GPIO_PIN_1"
      }
    }
  ]
}
```

After successful generation has verified those exact bindings against the
CubeMX-generated identifier inventory, render it with:

```bash
python scripts/stm32_cube.py module \
  --project-dir /absolute/output/f401_i2c \
  --name status_output \
  --pack gpio
```

`module --pack` requires the exact name, pack, and bindings declared in the
verified generation plan, and requires the current pack fingerprint to match
the generated project. Every external binding must exactly match an identifier
frozen from CubeMX configuration source or headers; a syntactically valid but
guessed handle, channel, IRQ, port, or pin is rejected before provenance is
written. Before every pack render, the frozen source inventory, its
non-user-code fingerprint, and the root `.ioc` hash are checked again; a
regenerated or altered CubeMX configuration requires a fresh generation. A generic `module --name` cannot
replace a plan-declared pack module.
It never overwrites an existing module. If a pack changed after project
generation, regenerate a fresh project rather than bypassing the provenance
check. Module files use exclusive creation, so a concurrent file appearing at
the target path stops rendering rather than being replaced. Keep hand-written code in `App/Inc/*.h` and `App/Src/*.c`; never guess a
handle, channel, or pin.

Safely wire the module into `Src/main.c`:

```bash
python scripts/stm32_cube.py integrate \
  --project-dir /absolute/output/f401_i2c \
  --name sensor_service
```

`integrate` modifies only these CubeMX user-code regions:

- `USER CODE BEGIN Includes`: include;
- `USER CODE BEGIN 2`: module initialization;
- `USER CODE BEGIN 3`: one non-blocking process call.

It uses idempotent managed markers and stops rather than duplicating an existing
manual include or call. Do not write outside CubeMX user-code regions. For a
timer pack, it refuses to render when an existing
`HAL_TIM_PeriodElapsedCallback` owner is found; route through that owner instead.

## Build and report

Compile with CubeIDE's bundled GNU tools:

```bash
python scripts/stm32_cube.py build --project-dir /absolute/output/f401_i2c
```

`build` first reloads the project's verified provenance. It refuses a missing,
altered, or regenerated root `.ioc`, changed generated configuration source,
changed CubeMX Makefile, changed controlled `codex-modules.mk`, or changed
selected pack before it invokes Make. It also rejects changed generated
C/assembly/linker inputs or generated include-tree files named by the frozen
Makefile; `App/` and `USER CODE` remain intentionally editable. A compiler
success therefore remains attached to the verified fresh-project configuration,
not just to arbitrary files that happen to compile.

Report the manual/profile path, exact MCU, selected pack IDs, generated
project, module paths, source-verification result, build result, artifact
paths, and the remaining hardware validation. Compilation is not hardware
validation.

## Boundaries

- `pypdf` is required for manual indexing/hash/page validation; install it from
  `requirements.txt` in the Python environment that runs the Skill.
- Do not automatically download firmware packages, accept ST licenses, or use
  user credentials.
- Do not flash or debug hardware in this Skill.
- Use legacy STM32CubeMX 6.x as the generator and CubeIDE only as the compiler
  backend. Do not require the CubeIDE GUI.

Read [references/core-contract.md](references/core-contract.md) when modifying
generated projects or reviewing an integration failure. Read
[references/legacy-cubemx-cli.md](references/legacy-cubemx-cli.md) when changing
CubeMX invocation behavior.
