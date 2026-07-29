# Core project contract

## Ownership

| Area | Owner | Role |
| --- | --- | --- |
| Board manual | User | Board wiring, clocks, and electrical facts |
| `board-profile.json` | Project | Page-cited facts derived from the supplied manual |
| CubeMX database | Installed CubeMX | MCU modes, pin signals, peripheral instances, and parameter names |
| Generated `.ioc` and HAL code | CubeMX | Generated project configuration and source |
| `App/Inc`, `App/Src` | Codex and user | Application logic and pack modules |
| `Src/main.c` user-code regions | Codex and user | Module include, initialization, and process call |

## Project lifecycle

1. **Inputs** — Generate from the exact manual, validated board profile, and
   approved configuration plan. Read and hash the profile and manual from the
   same input snapshots used for validation.
2. **Plan ownership** — Select one or more contract-valid packs. Map every
   peripheral operation, direct pin assignment, and semantic `ioc_overrides`
   entry to its owning pack and the pack's `plan_resources` declaration.
3. **Generation** — Create a fresh CubeMX project, evaluate generated-file
   assertions, and write `codex-stm32-project.json` after successful
   verification.
4. **Provenance** — Record the MCU, hashes of the manual/profile/plan, selected
   pack fingerprints, plan-declared modules, CubeMX identifier inventory, root
   `.ioc`, CubeMX version facts, Makefile baseline, generated source, linker,
   and include-tree inputs. Keep extracted manual text outside this record.
5. **Application area** — Keep hand-written modules in `App/` and integration
   in CubeMX `USER CODE` regions. The source fingerprint normalizes those
   application areas and C/H line endings.
6. **Pack modules** — Render one declared header/source pair from a selected
   pack. Bind template placeholders to identifiers captured from CubeMX output.
   Regenerate a fresh project after changing the generation inputs or selected
   pack files.
7. **Integration** — Manage markers in `USER CODE BEGIN Includes`,
   `USER CODE BEGIN 2`, and `USER CODE BEGIN 3`. The marker set is idempotent.
8. **Timer dispatch** — Use one owner for
   `HAL_TIM_PeriodElapsedCallback` and route timer modules through it.
9. **Build** — Reload the project provenance and evaluate the recorded
   configuration and build inputs before Make runs.

## Generated-file verification

Verify every planned physical pin against the generated `.ioc`; timer channel
aliases such as `S_TIM3_CH1` and `TIM3_CH1` represent the same requested
signal. Evaluate each parameter's attached assertion after generation. PWM and
base-timer plans also evaluate the plan's generated-clock and integer counter
calculation.

## Result levels

Build success records a configuration-and-toolchain result. Board voltage,
device response, timing margins, and boot behavior are established through a
separate hardware run.
