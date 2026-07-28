# STM32 Manual-Driven Codex Skill

An open-source, Codex-first STM32 workflow for people who want to describe
firmware work in natural language rather than operate STM32CubeIDE by hand.

The first release turns a user-supplied board manual plus a GPIO-output, UART,
I2C, SPI, PWM, timer, or application-module request into a **new,
source-verified, compile-only** STM32 Makefile project. STM32CubeMX remains the
generator and STM32CubeIDE supplies the compiler, but neither IDE GUI is needed
for the normal workflow.

## Repository layout

```text
stm32-codex-skill/
├── stm32-cubemx-build/  # the single directory users install as a Codex Skill
├── tests/               # deterministic core and pack tests
├── .github/workflows/   # public CI checks
├── README.md
├── AUDIT.md             # dominant-problem audit records
├── CONTRIBUTING.md
└── LICENSE
```

## What it does

1. Snapshots and indexes a board manual PDF, then records only cited hardware facts in a
   persistent `board-profile.json`: exact MCU, board wiring, available/reserved
   pins, clock facts, and electrical constraints. Each fact carries a short
   text anchor that the Skill verifies against its cited PDF page; a fact
   without an extractable anchor stops rather than becoming a guess.
2. Combines those board facts with the installed CubeMX MCU database to make a
   `configuration-plan.json` for a new project. Each peripheral operation,
   direct pin assignment, and semantic override names the selected capability
   pack that owns it, so a pack cannot be used as a label for an unrelated
   CubeMX resource.
3. Calls CubeMX without its GUI to generate the `.ioc`, HAL/CMSIS source, and
   Makefile project.
4. Reads generated output back. Every requested physical pin must match the
   generated `.ioc` signal (including CubeMX's documented `S_` channel alias),
   and every explicit plan assertion—including one attached to each planned
   parameter—must be present in the `.ioc` or generated C. For PWM and
   base-timer plans, it also checks an approved target rate using generated
   STM32F4 unprescaled-APB clock values and exact integer counter arithmetic.
   A standalone CubeMX `KO` response is a hard failure.
5. Records the successful evidence chain in a project-local,
   manual-text-free `codex-stm32-project.json`, including hashes of the exact
   manual, `board-profile.json`, and configuration plan. The manual/profile
   hashes come from the same one-read bytes used for validation, then it records a frozen inventory of
   configuration-bearing CubeMX C identifiers, and a fingerprint of generated
   source outside user-code regions. It also records the root `.ioc` hash, a
   baseline fingerprint of the CubeMX Makefile, and the `MxCube.Version`,
   `MxDb.Version`, and firmware-package facts emitted by CubeMX. The Makefile
   baseline permits only the exact owned include block and exact
   `codex-modules.mk` content used to compile `App/`; every other Makefile
   change is drift. It also fingerprints the generated C/assembly/linker files
   named by that baseline and every file below its generated include
   directories. `App/` is deliberately excluded, and `USER CODE` content plus
   C/H line-ending style is normalized, so normal application work remains
   editable. A pack module's name, pack, and bindings
   are approved in the configuration plan before generation, then recorded only
   if those exact values are present in that inventory. It renders the approved
   template into new `App/Inc/*.h` and `App/Src/*.c` files.
6. Safely wires each module's include, init, and non-blocking process calls into
   `main.c` user-code regions, then compiles with CubeIDE's bundled Arm GCC.

The initial capability packs are:

- `gpio` — documented push-pull GPIO-output plan and explicit write/toggle module template;
- `uart` — asynchronous serial configuration and explicit HAL send/receive module template;
- `i2c` — bus initialization plan and HAL memory-read module template;
- `spi` — 8-bit MSB-first full-duplex master-bus plan and explicit HAL transfer module template;
- `pwm` — timer PWM configuration plan and duty-cycle module template;
- `timer` — base-timer plan and non-blocking periodic-dispatch template.

## The important safety model

The Skill does not trust a model's memory of a board. The **board manual** is
the source for board-specific truth, while the **installed CubeMX database** is
the source for what the selected MCU can configure. A missing fact or conflict
stops the workflow rather than producing a guessed pin assignment.

Before CubeMX runs, the core resolves every requested peripheral instance,
operation mode, operation pin/signal pair, and parameter key to that installed
MCU/IP database. It rejects a plan mode that is not one of the IP's concrete
leaf-mode names or display aliases, an operation pin that does not expose the
requested signal on the selected MCU, or a parameter key absent from that IP's
local mode database. A generic category such as `Base` is not accepted as a
timer configuration. Key presence does not prove that a conditional parameter
  value is valid; CubeMX generation and each parameter's attached
  generated-file assertion remain mandatory.

PWM and timer operations have a required rate contract: target frequency,
tolerance, declared timer-input rate, and the exact prescaler/period parameter
names. The first proof model deliberately covers only STM32F4 `TIM1`–`TIM14`
when CubeMX generated an unprescaled APB clock. The core reads the generated
`.ioc` clock values, rejects a prescaled/custom tree, and performs the
counter calculation with integers. A different family, LPTIM, or unproven
clock tree stops rather than producing a claimed PWM frequency or timer
period. This remains a configuration proof, not a hardware measurement.

The page-numbered manual index contains extracted full-text manual content. It
uses the private `*.manual-index.json` suffix and is ignored by this repository;
do not publish it with a profile or pack.

The profile retains only a short source anchor for each fact, not the manual
text. Before generation, the exact uploaded PDF must match its hash, cited page,
and that page's anchor. A visual-only claim with no textual anchor is treated as
missing evidence, not as permission to infer wiring.

Every audit pass—whether a feature audit, release audit, or repeat
self-audit—first asks “目前最大的问题是什么？ / What is the largest problem
right now?” It then identifies which single unresolved problem is most likely
to make this proof chain incorrect, unsafe, or misleading. For that one
problem, the audit records the evidence, root cause, smallest in-scope
corrective action, and the verification result that proves the action worked.
That action must be executed and verified first; the next audit pass asks the
question again. An idea to solve it later cannot be hidden by a new capability
or a silent fallback.

It deliberately does not flash, reset, debug, or claim that firmware ran on a
board. A physical board is therefore not needed for this first version; compile
success is useful but is not hardware validation.

## Prerequisites

1. STM32CubeMX 6.x.
2. STM32CubeIDE (used only for its bundled Arm GCC and Make).
3. Python 3.
4. The matching STM32Cube firmware package installed in CubeMX.
5. `pypdf` for PDF indexing and evidence/page validation:

   ```bash
   python -m pip install -r stm32-cubemx-build/requirements.txt
   ```

Run `doctor --strict` with that same Python interpreter; it reports a missing
`pypdf` package before a manual-driven generation attempt.

CubeMX itself is not enough: the family firmware package supplies the HAL/CMSIS
source needed to generate and compile. Review and accept any ST package license
yourself.

### Windows tool location

`doctor` automatically checks the normal all-user installation locations and
the conventional `C:\ST\STM32CubeIDE_*` CubeIDE location. If CubeMX or CubeIDE
was installed only for the current user, or into a custom folder, do not guess
the location: pass the two executable paths explicitly before the subcommand.

~~~powershell
python stm32-cubemx-build/scripts/stm32_cube.py --cubemx "C:\path\to\STM32CubeMX.exe" --cubeide "C:\path\to\stm32cubeide.exe" doctor --strict
~~~

Use the same two leading options with later `generate` and `build` commands.
The explicit CubeIDE path also tells the Skill where to find CubeIDE's bundled
Arm GCC and Make tools. A successful `doctor` remains a host-environment check,
not a firmware or hardware result. It rejects an explicit path that is missing,
a directory, or not executable, instead of reporting a false healthy toolchain.

### Windows real-machine acceptance

The repository includes a no-board Windows acceptance runner. It starts with
your real manual, cited board-profile.json, and approved
configuration-plan.json; it runs strict environment validation, creates a
fresh project, creates and safely integrates one App module, then compiles.
It refuses an existing project directory and never deletes one.

~~~powershell
$skill = "$env:USERPROFILE\.codex\skills\stm32-cubemx-build\scripts\windows_smoke.ps1"
& $skill -Manual "C:\work\board-manual.pdf" -BoardProfile "C:\work\board-profile.json" -Plan "C:\work\configuration-plan.json" -Mcu "STM32F401RETx" -OutputDir "C:\work\stm32-output" -ProjectName "f401_windows_smoke"
~~~

Add -CubeMX and -CubeIDE when the applications use custom paths. Use -Pack
gpio only when the plan declares the chosen -ModuleName for that exact pack. A
successful run prints WINDOWS_SMOKE_PASS. It is compile-only acceptance, not a
claim that firmware ran on hardware.

## Install in Codex

Copy only the inner `stm32-cubemx-build` directory into the Codex user-skill
directory:

- macOS: `~/.codex/skills/stm32-cubemx-build`
- Windows: `%USERPROFILE%\.codex\skills\stm32-cubemx-build`

Then upload a board manual and ask, for example:

> Use `$stm32-cubemx-build` to read this board manual and create a 400 kHz I2C
> temperature-sensor project. Use only documented available pins, create a
> `sensor_service` App module, and compile it.

## Development check

From this repository root:

```bash
python -m unittest discover -s tests -v
python stm32-cubemx-build/scripts/validate_packs.py
python stm32-cubemx-build/scripts/stm32_cube.py doctor --strict
```

GitHub Actions runs the deterministic tests, pack validation, and Python
compile check on Linux, macOS, and Windows. It intentionally does not install
CubeMX, accept ST licenses, or claim a hardware validation result.

The complete manual-driven command sequence is specified inside
[`stm32-cubemx-build/SKILL.md`](stm32-cubemx-build/SKILL.md). The project does
not modify an existing user-owned `.ioc`; every configuration plan creates a
fresh project directory. A restricted, plan-declared `.ioc` property may be
applied only inside that fresh project and is then reloaded by CubeMX before
source verification. Overrides are semantic, pack-declared operations—not
arbitrary property writes—and each requires an exact resulting `.ioc`
assertion. `generate` always requires the exact manual,
`board-profile.json`, and `configuration-plan.json`; it has no evidence-free
baseline-project mode.

For a pack-backed App module, declare its exact `name`, `pack`, and
template `bindings` in `configuration-plan.json` before `generate`. After
generation verifies that each binding exists in CubeMX-generated source, run
`module --name <declared-name> --pack <declared-pack>`. The command rejects an
undeclared name, a wrong pack, an existing module, or a pack whose
manifest/instructions/templates changed after generation. A generic module
cannot take the name of a planned pack module. Before rendering, it rechecks
the CubeMX-generated source inventory, non-user-code fingerprint, and root
`.ioc` hash, plus the frozen Makefile baseline and its exact controlled App
module inclusion file and frozen generated build inputs, so a regenerated or
changed configuration requires a fresh project. `build` repeats that
provenance preflight before calling Make, so compile success remains tied to
the verified configuration. It never stores manual text in the project
provenance file.

## Verified status

| Capability | macOS | Windows |
| --- | --- | --- |
| Tool discovery | Verified with CubeMX 6.18 and CubeIDE 2.2 | Standard and explicit-path branches have deterministic tests; pending real-machine validation |
| Manual-capable environment preflight | Verified: strict doctor rejects a Python runtime without `pypdf` and reports the installed version when available | Implemented, pending real-machine validation |
| Manual/profile input snapshot, hash/page, and profile validation | Verified: profile and manual provenance hashes come from the same one-read bytes used for validation | Implemented, pending real-machine validation |
| Private full-text manual-index safeguard | Verified with a local 28-page PDF; invalid output names and concurrent output creation are rejected without replacing the private index | Implemented, pending real-machine validation |
| Mandatory manual/profile/plan gate for new-project generation | Verified by CLI rejection plus a synthetic, no-board STM32F401RETx generation and compilation | Implemented, pending real-machine validation |
| Mandatory selected-pack manifest gate for configuration plans | Verified by CLI rejection plus a synthetic, no-board STM32F401RETx GPIO generation, App-module integration, and compilation | Implemented, pending real-machine validation |
| Semantic, pack-owned `.ioc` overrides and exact generated-file assertions | Verified by a synthetic, no-board STM32F401RETx GPIO generation: only a planned GPIO output's initial-state pair is accepted, reloaded through CubeMX, source-verified, integrated, and compiled | Implemented, pending real-machine validation |
| Root `.ioc` drift guard and frozen CubeMX generation facts | Verified by a synthetic, no-board STM32F401RETx generation: changed `.ioc` or tampered provenance facts block pack-module rendering and build | Implemented, pending real-machine validation |
| Frozen CubeMX Makefile and controlled App-module inclusion guard | Verified with a fresh, no-board STM32F401RETx project: a CRLF CubeMX Makefile, GPIO module, safe integration, and compilation succeed; changed Makefile or `codex-modules.mk` blocks build before Make, and restored files compile again | Implemented, pending real-machine validation |
| Frozen generated compiler/linker input guard | Verified with a fresh, no-board STM32F401RETx project: changed HAL header or linker script blocks build before Make; a normal `App/` edit recompiles, and safe `USER CODE` integration remains valid across CRLF/LF conversion | Implemented, pending real-machine validation |
| Plan-declared pack template binding, binding provenance, and generated-source drift guard | Verified by a synthetic, no-board STM32F401RETx generation: wrong generic/wrong-pack module routes are rejected; a declared GPIO module, safe integration, a subsequent generic module, and compilation all succeed | Implemented, pending real-machine validation |
| Concrete local CubeMX operation preflight | Verified by synthetic database regression tests and the local STM32F401RETx database: valid I2C/PWM/timer modes, pins, and parameter keys are accepted; generic `Base`, PB9 requested as `I2C1_SCL`, and an unknown I2C parameter key are rejected before CubeMX can create output | Implemented, pending real-machine validation |
| Parameter-bound generated-output evidence | Verified by regression tests: every planned parameter requires its own safe generated-file assertion, and an absent asserted result blocks generation before provenance is written | Implemented, pending real-machine validation |
| GPIO push-pull-output plan, no-GUI CubeMX generation, module integration, and compilation | Verified with a synthetic, no-board STM32F401RETx fixture | Implemented, pending real-machine validation |
| UART plan, no-GUI CubeMX generation, module integration, and compilation | Verified with a synthetic, no-board STM32F401RETx fixture | Implemented, pending real-machine validation |
| I2C plan, no-GUI CubeMX generation, module integration, and compilation | Verified with a synthetic, no-board STM32F401RETx fixture using I2C1 on cited PB8/PB9 at 400 kHz | Implemented, pending real-machine validation |
| SPI master plan, no-GUI CubeMX generation, module integration, and compilation | Verified with a synthetic, no-board STM32F401RETx fixture | Implemented, pending real-machine validation |
| PWM frequency contract, generated pin/source verification, module integration, and compilation | Verified with real local CubeMX for a no-board STM32F401RETx TIM3/PA6 `TIM3_CH1` project: generated unprescaled 16 MHz APB1, prescaler 15, period 999, pulse 500, exact 1 kHz carrier contract, safe module integration, and compilation all succeeded; a deliberately wrong prescaler 83 configuration was rejected without provenance | Implemented, pending real-machine validation |
| Base-timer period contract, regenerated IRQ handler, module integration, and compilation | Verified with real local CubeMX for a no-board STM32F401RETx TIM2 `Internal Clock` project: generated unprescaled 16 MHz APB1, prescaler 15, period 999, exact 1 kHz dispatch contract, enabled TIM2 NVIC route, safe module integration, and compilation all succeeded | Implemented, pending real-machine validation |
| Safe `main.c` module integration and compilation | Verified | Implemented, pending real-machine validation |

The synthetic fixture used a real local PDF only to exercise its SHA-256 and
page-citation machinery. It is deliberately **not** presented as a real board
manual or a hardware test.

## Open-source contribution model

The stable core handles profiles, plans, CubeMX generation, user-code
integration, and compilation. Community pull requests add isolated capability
or board-data packages under `stm32-cubemx-build/packs/`; they do not alter the
core to add a peripheral. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
