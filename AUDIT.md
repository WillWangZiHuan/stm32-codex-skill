# Audit log

Each audit begins with one question:

> 目前最大的问题是什么？ / What is the largest problem right now?

Record only the single dominant problem. An entry is complete only after its
smallest in-scope corrective action has been verified; otherwise state the
remaining gap explicitly. Do not use a new capability to hide an unresolved
problem.

## 2026-07-29 — timer/PWM rate proof

- **Question:** What is the largest problem right now?
- **Dominant problem:** PWM and base-timer plans proved that CubeMX wrote
  `Prescaler` and `Period`, but did not prove that those values produced the
  user-requested frequency under the generated clock tree.
- **Evidence:** A fresh STM32F401RETx CubeMX project generated
  `RCC.AHBFreq_Value=16000000` and `RCC.APB1Freq_Value=16000000`. With
  prescaler 83 and period 999, the configured rate is
  `16000000 / ((83 + 1) * (999 + 1))`, not 1 kHz.
- **Root cause:** The configuration-plan contract had parameter-output
  assertions but no rate target, clock-domain check, or arithmetic check.
- **Smallest corrective action:** Bump the plan schema to 5. Require a
  `timing` object for `pwm` and `timer` operations, restrict the first
  frequency-proof model to STM32F4 `TIM1`–`TIM14` with an unprescaled
  generated APB clock and 16-bit counter values, then verify generated RCC
  values and exact integer counter math before provenance is written.
- **Verification:** 68 deterministic tests pass. Real local CubeMX generated,
  safely integrated, and compiled a 1 kHz TIM3 PWM project and a 1 kHz TIM2
  interrupt project with prescaler 15 and period 999. A deliberately wrong PWM
  plan with prescaler 83 failed at the timing check and wrote no
  `codex-stm32-project.json`.
- **Remaining boundary:** This is a compile-time configuration proof, not a
  hardware frequency measurement. Custom/prescaled clock trees, LPTIM, and
  non-STM32F4 families stop until they receive their own evidence-backed clock
  model.

## 2026-07-29 — manual text-evidence failure clarity

- **Question:** What is the largest problem right now?
- **Dominant problem:** A scanned or diagram-only board manual correctly could
  not support an evidence-backed profile, but the prior failure looked like a
  generic missing-anchor error. That leaves a new user unable to distinguish a
  document-evidence gap from a configuration mistake.
- **Evidence:** Profile proof requires a short anchor present in extracted PDF
  page text. An empty extracted page cannot contain an anchor, and an entirely
  image-only PDF produces an empty private manual index.
- **Root cause:** The validator performed the strict anchor comparison but did
  not identify the empty-text condition before reporting the comparison
  failure.
- **Smallest corrective action:** Refuse indexing when every page has no
  extractable text. When a cited page is empty, report that exact page and
  require a text-accessible source rather than allowing an image-based guess.
- **Verification:** Two deterministic regression tests cover both failure
  paths; the full suite now has 71 passing tests. A real local PDF index and
  validation of the synthetic STM32F401RETx fixture still succeeds.
- **Remaining boundary:** The Skill intentionally does not OCR or infer a
  board's wiring from visual diagrams. The user must supply a textual manual,
  schematic annotation, or other verifiable source for any fact that needs to
  enter `board-profile.json`.

## 2026-07-29 — incomplete I2C/PWM operation rejection

- **Question:** What is the largest problem right now?
- **Dominant problem:** An I2C or PWM plan could pass the existing pack-prefix,
  profile-pin, generated-output, and compile checks while omitting a required
  physical bus/output signal. A one-wire I2C plan or pinless PWM plan is not a
  usable initialization, even if CubeMX produces compilable code.
- **Evidence:** The pack manifests previously declared only owned instance
  prefixes and direct-pin signals. The core therefore did not require
  `I2C1_SCL` plus `I2C1_SDA`, nor any PWM pin, before CubeMX started.
- **Root cause:** Pin completeness was written as guidance in `PACK.md`, not
  encoded in the machine-checked `plan_resources` contract.
- **Smallest corrective action:** Move only the initial product scope into that
  contract: require I2C `SCL` and `SDA` suffixes, require one PWM pin, and
  explicitly allow a base timer to use zero pins. The core rejects a missing
  signal or undersized pin list before it invokes CubeMX; it does not add a
  general configuration-rule engine.
- **Verification:** 72 deterministic tests pass, including positive timer
  behavior and new negative I2C/PWM plan-shape cases. All six built-in packs
  pass manifest validation, and the Python helper scripts compile cleanly.
- **Remaining boundary:** This proves only the stated plan shape before
  generation. It does not prove electrical suitability, a device response, or
  hardware behavior; UART/SPI completeness has not been expanded in this
  intentionally small correction.

## 2026-07-29 — release-candidate I2C evidence refresh

- **Question:** What is the largest problem right now?
- **Dominant problem:** The newest I2C operation-shape guard had deterministic
  coverage, but the release candidate needed fresh end-to-end evidence from the
  current source rather than relying only on an older generated project.
- **Evidence:** The current I2C contract now requires both
  `I2C1_SCL` and `I2C1_SDA` before CubeMX starts, while the previous
  real I2C evidence predated that contract revision.
- **Root cause:** The contract change altered pre-generation acceptance, so a
  green unit suite alone was weaker release evidence than a new actual
  generation and compilation pass.
- **Smallest corrective action:** Generate one fresh no-board STM32F401RETx
  I2C1 project from the current source and a cited synthetic PDF/profile, then
  render the plan-declared `release_i2c` module, safely integrate it, and
  compile it with CubeIDE's bundled toolchain.
- **Verification:** The current source generated a fresh private temporary
  STM32F401RETx I2C1 PB8/PB9 project at 400 kHz, created the App module,
  passed provenance preflight, and produced `.elf`, `.bin`,
  `.hex`, and `.map` artifacts. This is compile-only evidence.
- **Remaining boundary:** The fixture is not a real board manual or a hardware
  test. A real Windows host still needs to run the provided Windows acceptance
  harness before any Windows runtime claim; publication also needs the user's
  chosen GitHub remote.
