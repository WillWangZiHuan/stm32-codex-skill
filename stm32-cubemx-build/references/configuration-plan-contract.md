# Configuration-plan contract

`configuration-plan.json` is an approved, deterministic translation from board
facts plus the local CubeMX MCU database into a new project's CubeMX commands.
It deliberately does not accept free-form script lines.

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
          "verification": {
            "file": "$IOC",
            "contains": "I2C1.I2C_Mode=I2C_Fast"
          }
        },
        {
          "name": "ClockSpeed",
          "value": 400000,
          "verification": {
            "file": "Src/main.c",
            "contains": "hi2c1.Init.ClockSpeed = 400000;"
          }
        }
      ]
    }
  ],
  "pin_assignments": [
    {"pack": "gpio", "pin": "PA1", "signal": "GPIO_Output"}
  ],
  "ioc_overrides": [
    {
      "pack": "gpio",
      "kind": "gpio-initial-state",
      "key": "PA1.GPIOParameters",
      "value": "PinState"
    },
    {
      "pack": "gpio",
      "kind": "gpio-initial-state",
      "key": "PA1.PinState",
      "value": "GPIO_PIN_SET"
    }
  ],
  "verifications": [
    {"file": "$IOC", "contains": "PB8.Signal=I2C1_SCL"},
    {"file": "$IOC", "contains": "PA1.GPIOParameters=PinState"},
    {"file": "$IOC", "contains": "PA1.PinState=GPIO_PIN_SET"}
  ]
}
```

## Rules

- The plan's `schema_version` must be `5`. Its MCU must exactly match `--mcu`
  and the validated board profile.
- `packs` is a non-empty, duplicate-free list of the capability packs selected
  for this request. Every ID must resolve to an installed pack whose
  `manifest.json` passes the stable pack contract. List every pack whose
  `PACK.md` or template informed the plan or App module; the example selects
  both `i2c` and `gpio` because it configures both kinds of capability.
- `modules` is optional and declares every pack-rendered App module before
  CubeMX runs. Each entry has one unique lowercase `name`, one `pack` already
  listed in `packs`, and a `bindings` object. Its keys must be exactly the
  non-derived placeholders used by that pack's two templates; `MODULE_NAME` and
  `MODULE_GUARD` are derived from `name` and may not be supplied. Each binding
  value is one C identifier, not an expression or source fragment.
- Every `operations` entry, `pin_assignments` entry, and `ioc_overrides`
  entry must name its owning selected `pack`. The core checks the operation's
  peripheral-instance prefix or direct pin signal against that pack's machine
  checked `plan_resources` manifest declaration. This prevents a selected pack
  from being used only as a label for an unrelated CubeMX resource; it does not
  replace the required local CubeMX database check for the exact mode, pins, or
  parameters.
- The same `plan_resources` declaration may require a minimum number of pins
  and exact operation signal suffixes. The core expands each declared suffix to
  `<instance>_<suffix>` and rejects an incomplete operation before CubeMX
  runs. The initial usable rules are intentionally narrow: I2C requires SCL
  and SDA, PWM requires at least one output pin, and base timers allow zero
  pins.
- A selected-pack check establishes provenance, not electrical or configuration
  correctness. The manual citations, local CubeMX database inspection, profile
  pin checks, generated-output assertions, and compilation remain mandatory.
- After all generated-output assertions pass, the fresh project receives a
  `codex-stm32-project.json` provenance record. It hashes the exact approved
  board profile, plan, and manual, fingerprints the selected pack contracts, freezes identifiers from
  the CubeMX configuration source/header files, and fingerprints that generated
  content with CubeMX user-code-region contents excluded. It also records the
  exact root `.ioc` hash, a baseline fingerprint of the root CubeMX Makefile
  after excluding only the exact owned module include block, plus the
  `MxCube.Version`, `MxDb.Version`, and firmware-package facts CubeMX embedded
  in that file. If the owned block exists, its `codex-modules.mk` content must
  exactly match the core-generated file. It also fingerprints the direct
  generated C/assembly/linker files named by the frozen Makefile and every file
  below its generated C/assembly include directories. `App/` is excluded, while
  C/H `USER CODE` content and line-ending style are normalized. It records the
  plan-declared modules only after every binding matches that frozen inventory.
  It lets
  `module --pack` prove that a rendered App module came from the exact pack,
  name, and resource bindings approved in this plan; it contains no extracted
  manual text and must not be hand-edited.
- `operations` and `pin_assignments` are individually optional, but at least
  one of them must contain an entry. Each peripheral instance has one
  operation. Every listed pin must be present and `available` in the profile. A
  pin may be assigned once only across both lists. An operation's `pack` must
  declare its instance prefix in `plan_resources.operation_instance_prefixes` and
  satisfy that pack's `minimum_operation_pins` and
  `required_operation_signal_suffixes`. This is a plan-shape guard; the local
  CubeMX database still establishes whether a requested signal exists on the
  exact selected MCU pin.
- `mode`, signal, and parameter names come from the locally installed CubeMX
  database for the selected MCU/IP version. Before CubeMX is launched, the
  core resolves each planned operation to that IP's mode XML and rejects a
  `mode` that is not one of its concrete leaf `Name` or `UserName` entries.
  It also rejects an operation pin/signal pair unless that MCU's local XML
  declares the requested signal on the requested pin, and rejects a parameter
  key absent from that IP's local mode database. This parameter check proves
  key presence only, not conditional availability or value validity. Generic
  labels such as `Base` are not configuration modes. Never carry a parameter
  name from a different STM32 family without checking it.
- Every operation parameter has `name`, `value`, and one attached
  `verification` object with the same safe `file`/`contains` shape as a
  top-level assertion. The core evaluates that attached assertion after
  generation, so the plan must choose a generated `.ioc` or source fragment that
  proves this exact parameter's effect. Do not rely on a separate generic
  assertion to prove a parameter.
- Every `pwm` or `timer` operation additionally has a required `timing`
  object:

  ```json
  {
    "timer_input_hz": 16000000,
    "target_hz": 1000,
    "tolerance_ppm": 0,
    "prescaler_parameter": "Prescaler",
    "period_parameter": "Period"
  }
  ```

  Its named prescaler and period parameters must belong to that operation,
  have non-negative decimal values no greater than 65535, and are checked as
  `timer_input_hz / ((prescaler + 1) * (period + 1))` using integer
  arithmetic. The core currently supports this frequency proof only for
  `TIM1`–`TIM14` on STM32F4 with an unprescaled generated APB clock: it
  reads the generated `RCC.AHBFreq_Value` plus the timer's APB1/APB2
  frequency from the root `.ioc`, requires them to match, then requires that
  APB frequency to equal `timer_input_hz`. A prescaled/custom clock tree,
  LPTIM, or another MCU family stops generation rather than receiving an
  unproven frequency claim. `tolerance_ppm` is required and may not exceed
  100000 (10%). This proves the generated clock-tree model and configured
  counter math, not an oscilloscope measurement on hardware.
- An item in `pin_assignments` has `pack`, `pin`, and `signal`. Its `pack`
  must list that exact signal in `plan_resources.direct_pin_signals`. It emits the exact
  restricted command `set pin <pin> <signal>` and never synthesizes an
  instance, mode, or IP parameter. Use it only when the locally verified
  CubeMX command interface accepts that direct assignment; the GPIO-output pack
  is the initial use case.
- Values are limited to safe CubeMX token characters. Arbitrary CubeMX script
  text is intentionally unsupported.
- `ioc_overrides` is optional and exists only for a local CubeMX setting that
  cannot be expressed through the direct command interface. Every entry has
  `pack`, `kind`, `key`, and `value`; its kind must be declared by its selected
  `pack` in that pack's `ioc_override_kinds` manifest field. The current
  semantic kinds are:
  - `gpio-initial-state`: exactly the pair
    `<planned GPIO_Output pin>.GPIOParameters=PinState` and
    `<same pin>.PinState=GPIO_PIN_SET|GPIO_PIN_RESET`;
  - `timer-nvic-enable`: an enabled `NVIC.<IRQ>_IRQn` property whose IRQ names
    a timer instance declared in `operations`.
  Every override needs an exact `$IOC` assertion containing its final
  `key=value`. Arbitrary `.ioc` keys, free-form property text, and overrides for
  an unplanned pin or peripheral are unsupported. The override's `pack` must also
  own the referenced planned GPIO output or timer operation. The core applies an approved
  override only after creating a new project, reloads that fresh `.ioc` with
  `config load`, and regenerates before any assertion is evaluated. It never
  authorizes edits to a user-owned existing project.
- The core always verifies every requested physical pin against the generated
  root `.ioc`. CubeMX may represent a timer channel as `S_TIM3_CH1` rather than
  `TIM3_CH1`; both representations are checked as the same requested signal.
  Every plan must additionally include at least one explicit post-generation
  assertion. Use `$IOC` only for an exact raw property already verified against
  the installed CubeMX version; use safe relative paths such as `Src/main.c`
  for source assertions.
- Assertions prove that generated output reflects the intended setup. A CubeMX
  `OK` response alone is not proof; the core also fails immediately if CubeMX
  emits its standalone `KO` command-rejection marker. An unknown parameter key
  is rejected before CubeMX starts, and each known parameter's attached
  assertion must prove its generated effect. Conditional availability and
  value validity are therefore established by generated output, not by a
  successful command alone.
- The plan is for a new project only. It is never a license to modify an
  existing `.ioc`.
- After a successful generate, render a declared pack module only with
  `module --name <declared-name> --pack <declared-pack>`. There is no
  post-generation bindings file. A generic module command refuses a name
  declared in `modules`, so it cannot bypass the approved template or resource
  mapping. Pack rendering recomputes the generated identifier inventory,
  non-user-code source fingerprint, and root `.ioc` hash; a CubeMX
  configuration, Makefile, or generated compiler/linker input change requires
  fresh generation, while legal `USER CODE` integration, `App/` edits, and
  the exact owned module Makefile block do not. `build` performs the same
  provenance preflight before it invokes Make.
