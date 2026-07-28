# PWM pack

Use this pack only after the board profile establishes the physical output pin
and electrical constraints. Every PWM operation must also declare the
`timing` contract defined in
`references/configuration-plan-contract.md`. The current core proves
frequency only for STM32F4 `TIM1`–`TIM14` using CubeMX's generated,
unprescaled APB clock model; it stops for a custom/prescaled tree, LPTIM, or a
different family rather than claiming an unproven PWM frequency.

The plan must include `"packs": ["pwm"]` (plus any other selected pack IDs).
Every PWM operation must use `"pack": "pwm"`. The core accepts only
`TIM` or `LPTIM` instance prefixes for that ownership; the local CubeMX
database still decides the exact channel, mode, pins, and parameters. All
manual, generated-output, and compilation checks below remain required.
At least one explicit PWM output pin is required; a pinless timer operation
belongs to the timer pack instead.

1. Read the board-profile evidence for the output pin and electrical load. For
   the supported STM32F4 clock model, use the generated root `.ioc` as the
   chip-level clock fact; do not substitute an undocumented board oscillator
   assumption.
2. Inspect the local CubeMX timer mode XML for the exact timer instance and
   channel. Names vary by IP version; for example, one F4 configuration uses
   `PWM Generation1 CH1`, not a guessed generic string.
3. Build a plan with `Prescaler`, `Period`, and the channel's pulse parameter
   only after checking the installed configuration XML. Attach one
   generated-file `verification` to every parameter, then include
   `timer_input_hz`, `target_hz`, `tolerance_ppm`, and the two parameter
   names in `timing`. The core checks the generated APB frequency and exact
   counter arithmetic after CubeMX runs; it is not enough for the source text
   merely to contain the requested prescaler and period.
4. In the plan's `modules` list, declare the module name, `pack: "pwm"`,
   and the exact `TIM_HANDLE`/`TIM_CHANNEL` expected from the local CubeMX
   output. Generate first, then run
   `module --name <declared-name> --pack pwm` and `integrate`. Provenance is
   written only when those planned values appear in CubeMX configuration source.

The template changes duty cycle only. The core proves the generated
configuration's theoretical carrier rate; hardware measurement remains outside
this compile-only Skill.
