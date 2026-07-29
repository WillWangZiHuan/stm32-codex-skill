# Configuration-plan contract

`configuration-plan.json` translates the board profile and the installed
CubeMX database into commands for a fresh project.

## Required shape

```json
{
  "schema_version": 5,
  "mcu": "STM32F401RETx",
  "packs": ["i2c", "gpio"],
  "modules": [
    {
      "name": "status_output",
      "pack": "gpio",
      "bindings": {
        "GPIO_PORT": "GPIOA",
        "GPIO_PIN": "GPIO_PIN_1"
      }
    }
  ],
  "operations": [
    {
      "pack": "i2c",
      "instance": "I2C1",
      "mode": "I2C",
      "pins": [
        {"pin": "PB8", "signal": "I2C1_SCL"},
        {"pin": "PB9", "signal": "I2C1_SDA"}
      ],
      "parameters": [
        {
          "name": "I2C_Mode",
          "value": "I2C_Fast",
          "verification": {"file": "$IOC", "contains": "I2C1.I2C_Mode=I2C_Fast"}
        },
        {
          "name": "ClockSpeed",
          "value": 400000,
          "verification": {"file": "Src/main.c", "contains": "hi2c1.Init.ClockSpeed = 400000;"}
        }
      ]
    }
  ],
  "pin_assignments": [
    {"pack": "gpio", "pin": "PA1", "signal": "GPIO_Output"}
  ],
  "ioc_overrides": [
    {"pack": "gpio", "kind": "gpio-initial-state", "key": "PA1.GPIOParameters", "value": "PinState"},
    {"pack": "gpio", "kind": "gpio-initial-state", "key": "PA1.PinState", "value": "GPIO_PIN_SET"}
  ],
  "safety": {
    "acknowledged_conflicts": [],
    "external_supply_pins": []
  },
  "verifications": [
    {"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"},
    {"file": "$IOC", "contains": "PA1.GPIOParameters=PinState"},
    {"file": "$IOC", "contains": "PA1.PinState=GPIO_PIN_SET"}
  ]
}
```

## Plan fields

- Set `schema_version` to `5`. Set `mcu` to the value used by `--mcu` and the
  validated board profile.
- List each selected capability pack in the non-empty `packs` array. The pack
  manifests provide the project resources, templates, and override kinds.
- Use `modules` for pack-backed App modules. Declare the module name, pack,
  and every non-derived template binding. `MODULE_NAME` and `MODULE_GUARD`
  derive from the module name.
- Use `operations` for peripheral configuration and `pin_assignments` for
  direct CubeMX pin signals. Supply at least one entry across those arrays.
- Use `verifications` for generated `.ioc` or source assertions. Every
  operation parameter includes its own `verification` object.
- Use `safety.acknowledged_conflicts` for the exact conflict strings declared
  by selected profile pins. Put each selected pin whose profile requires an
  external supply in `safety.external_supply_pins` after checking voltage and
  common ground. The generated project record carries the resulting physical
  connection guide.

## Pack ownership and pins

Map each operation, direct pin assignment, and `ioc_overrides` entry to a pack
listed in `packs`. The pack's `plan_resources` defines its peripheral-instance
prefixes, direct pin signals, minimum pin count, and required signal suffixes.

Use each physical pin once across operations and direct assignments. Select
pins marked `available` in the board profile. The local CubeMX database then
resolves the exact mode, signal, and parameter names for the selected MCU.

Current built-in shapes include I2C operations with `SCL` and `SDA`, PWM and
servo operations with an output pin, base timer operations, and direct GPIO
input/output or `GPIO_EXTI0`–`GPIO_EXTI15` assignments. PA13 and PA14 are
reserved for SWD.

## Modes, parameters, and output assertions

Choose `mode`, signal, and parameter names from the selected MCU/IP XML in the
installed CubeMX database. Use concrete mode names such as `I2C` or
`PWM Generation1 CH1`. Attach an assertion that identifies each generated
parameter result. `$IOC` addresses the generated root `.ioc`; source assertions
use relative paths such as `Src/main.c`. If CubeMX omits a default-valued
property, generation accepts it only when the installed IP XML has one unique
default equal to the requested value. Conditional, absent, or differing
defaults still require generated evidence.

Generation evaluates the requested pins, top-level assertions, parameter
assertions, and CubeMX command result. A successful project receives
`codex-stm32-project.json`, which records the input hashes, selected pack
fingerprints, generated identifier inventory, root `.ioc`, Makefile, and
generated build inputs. The record supports repeatable module rendering and
build preparation.

## PWM and timer timing

PWM and timer operations include:

```json
{
  "timer_input_hz": 16000000,
  "target_hz": 1000,
  "tolerance_ppm": 0,
  "prescaler_parameter": "Prescaler",
  "period_parameter": "Period"
}
```

Use `Prescaler` and `Period` values from the selected CubeMX configuration.
The timing evaluator calculates
`timer_input_hz / ((prescaler + 1) * (period + 1))` with integer arithmetic.
The model covers STM32F1 and STM32F4 APB timers, derives the x2 timer clock when
the APB divider exceeds one, and records whether TIM1/TIM8 requires the
advanced-timer main output enable. Add a verified clock model before
configuring another family or clock-tree form.

## Direct pin assignments and semantic overrides

`pin_assignments` emit a direct `set pin <pin> <signal>` CubeMX command. Use a
signal declared by the selected pack's `direct_pin_signals` list.

`ioc_overrides` capture supported semantic configuration details. The built-in
kinds are:

- `gpio-initial-state`: the `GPIOParameters=PinState` and
  `PinState=GPIO_PIN_SET|GPIO_PIN_RESET` pair for a planned GPIO output;
- `timer-nvic-enable`: an enabled `NVIC.<IRQ>_IRQn` property for a planned
  timer operation;
- `gpio-input-pull`: the `GPIOParameters=GPIO_PuPd` and
  `GPIO_PuPd=GPIO_NOPULL|GPIO_PULLUP|GPIO_PULLDOWN` pair for a planned input.

Attach an exact `$IOC` assertion to every override. Generation applies the
override in the fresh project, reloads its `.ioc` with `config load`, and
regenerates before evaluating assertions.

## Module rendering and build preparation

Render a declared pack module with:

```bash
python scripts/stm32_cube.py module \
  --project-dir /absolute/output/project \
  --name <declared-name> \
  --pack <declared-pack>
```

The renderer compares the plan-declared name, pack, bindings, and pack files
with the generated project record. It preserves `App/`, CubeMX user-code
regions, and the core-owned module Makefile include while tracking generation
inputs for the next build.
