# Validation record

## Current release snapshot

The release candidate covers board-profile validation, configuration planning,
CubeMX project generation, pack-backed App modules, `main.c` integration,
compilation, revision preview/apply, and explicitly authorized flashing.

## Automated checks

- **92 deterministic tests** exercise profile facts, manual indexing,
  configuration-plan rules, pack contracts, generated-project provenance,
  module rendering, integration, build preparation, revision, and flash
  authorization.
- **8 pack contracts** validate: `gpio`, `gpio_input`, `i2c`, `pwm`, `servo`,
  `spi`, `timer`, and `uart`.
- **GitHub Actions** runs the deterministic suite, pack validation, and Python
  compile checks on Linux, macOS, and Windows.
- **Windows smoke orchestration** executes `doctor` and the one-shot `create`
  workflow through PowerShell with paths that contain spaces, explicit
  CubeMX/CubeIDE locations, planned-module integration, report validation, and
  artifact checks.

## Performance path

The normal workflow uses one `create` command. Concrete MCU lookup reads the
CubeMX family index before any fallback scan. A hash-bound manual index avoids
re-extracting the same PDF. CubeMX output is saved to one log by default, and
`codex-run-report.json` records generation, module, and build durations so a
slow stage can be identified directly. CubeMX has a 180-second default bound;
a pending firmware-license or package dialog returns a targeted timeout result.

## End-to-end I2C run

The current source completed this local flow with STM32CubeMX and CubeIDE:

1. Create an STM32F401RETx I2C1 project using PB8/PB9 at 400 kHz.
2. Render and integrate the `release_i2c` App module.
3. Compile the project and produce `.elf`, `.bin`, `.hex`, and `.map`
   artifacts.

## Result levels

The project records the evidence produced by each run:

- **Configuration verified**: generated CubeMX files match the approved plan.
- **Compile verified**: the local Arm toolchain accepts the generated project.
- **Flash verified**: authorization hash, target identity, voltage, backup,
  write/verify, and reset all pass.
- **Hardware run**: a board has been flashed and exercised through a dedicated
  on-board workflow.

This structure keeps project generation, compilation, and board execution
easy to identify in issues and pull requests.
