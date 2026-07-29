# Contributing

Contributions extend the same manual-to-project workflow used by the built-in
packs. A pull request can add a capability pack or a shareable, page-cited
board-data example.

## Contribution path

Start from the project flow:

```text
board manual → board profile → CubeMX configuration plan → App module → compilation
```

Describe the STM32 task your change enables, the board facts it uses, the
CubeMX settings it selects, and the generated output that confirms the result.

## Design checklist

1. **Task** — state the concrete GPIO, UART, I2C, SPI, PWM, timer, or App
   workflow made easier by the change.
2. **Board facts** — cite the manual page and a concise text anchor for each
   MCU, pin, clock, and board constraint used by the workflow.
3. **CubeMX facts** — select modes, pins, and parameters from the installed
   CubeMX database for the exact MCU family.
4. **Project layout** — create application code in `App/` and connect it
   through CubeMX `USER CODE` regions.
5. **Validation** — add deterministic tests for changed behavior; include
   generated-file assertions and a compilation result where the change reaches
   the generator.
6. **Documentation** — update the pack instructions, plan contract, and user
   documentation together.

Keep the contribution focused on one capability or one board-data package.

## Capability-pack layout

Each pack contains:

```text
packs/<id>/
├── manifest.json
├── PACK.md
└── templates/
```

- `manifest.json` defines a lowercase ID, inputs, templates, generated-output
  checks, `plan_resources`, and supported `ioc_override_kinds`.
- `PACK.md` explains the local CubeMX inspection, board evidence,
  configuration plan, module bindings, and validation steps.
- `templates/` contains one `.h.tmpl` and one `.c.tmpl` for `module --pack`.

`plan_resources.operation_instance_prefixes` identifies the peripheral
families a pack configures. `plan_resources.direct_pin_signals` identifies
direct CubeMX pin assignments. `minimum_operation_pins` and
`required_operation_signal_suffixes` describe the complete pin shape for an
operation.

Use uppercase template placeholders. `MODULE_NAME` and `MODULE_GUARD` come
from the module name; other placeholders map to C identifiers found in the
generated CubeMX source, such as `hi2c1`, `GPIOA`, `GPIO_PIN_1`, or `TIM2_IRQn`.
Declare each pack-backed module and its bindings in `configuration-plan.json`
before generation.

## Project conventions

- Board profiles store shareable page citations and short anchors. Keep user
  manuals and full-text `*.manual-index.json` files in local working storage.
- Configuration plans select installed packs and map every operation, direct
  pin assignment, and semantic `.ioc` override to its owning pack.
- Generated project files come from CubeMX. App modules live in `App/`, and
  integration uses the owned markers in `Src/main.c` user-code regions.
- The generated provenance record ties the project to its manual, profile,
  plan, selected pack files, generated source inventory, `.ioc`, and build
  inputs. Regenerate a fresh project after changing those generation inputs.

## Required checks

Run before opening a pull request:

```bash
python -m unittest discover -s tests -v
python stm32-cubemx-build/scripts/validate_packs.py
```

For executable behavior, add a deterministic test under `tests/`. For a real
board workflow, cite the manual pages and report the completed result level:
configuration, compilation, or hardware run. Windows-specific work can use
`scripts/windows_smoke.ps1` with a local manual/profile/plan set.

See [VALIDATION.md](VALIDATION.md) for the current release evidence.
