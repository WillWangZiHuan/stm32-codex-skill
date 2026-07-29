# Validation record

## Current release snapshot

The release candidate covers board-profile validation, configuration planning,
CubeMX project generation, pack-backed App modules, `main.c` integration, and
compilation.

## Automated checks

- **72 deterministic tests** exercise profile facts, manual indexing,
  configuration-plan rules, pack contracts, generated-project provenance,
  module rendering, integration, and build preparation.
- **6 pack contracts** validate: `gpio`, `i2c`, `pwm`, `spi`, `timer`, and
  `uart`.
- **GitHub Actions** runs the deterministic suite, pack validation, and Python
  compile checks on Linux, macOS, and Windows.

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
- **Hardware run**: a board has been flashed and exercised through a dedicated
  on-board workflow.

This structure keeps project generation, compilation, and board execution
easy to identify in issues and pull requests.
