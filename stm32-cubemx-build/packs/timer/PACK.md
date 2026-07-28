# Timer pack

This pack supplies a non-blocking dispatch pattern, not an unchecked duplicate
of the global `HAL_TIM_PeriodElapsedCallback` function.

The plan must include `"packs": ["timer"]` (plus any other selected pack IDs).
Every base-timer operation and `timer-nvic-enable` override must use
`"pack": "timer"`. The core accepts only `TIM` or `LPTIM`
instance prefixes for that ownership; the local CubeMX database still decides
the exact mode, pins, and parameters. All manual, generated-output, and
compilation checks below remain required.

Every timer operation must declare the `timing` contract from
`references/configuration-plan-contract.md`. Its frequency proof is
currently deliberately narrow: STM32F4 `TIM1`–`TIM14` with a generated,
unprescaled APB clock. Custom/prescaled clock trees, LPTIM, and other MCU
families stop rather than receiving a claimed interrupt period.

1. Read the profile's evidence for the request's board wiring and constraints,
   then calculate prescaler/period from the supported generated clock model.
   The core will read the generated root `.ioc` and independently check
   the declared timer-input frequency and resulting counter math; do not
   substitute a board-clock guess.
2. Inspect the installed timer mode/configuration XML and determine the exact
   base-timer mode, parameters, and NVIC property supported by that MCU family.
   Do not assume the timer configuration syntax is shared by all STM32 series.
   `Base` is a generic category, not a valid mode value. Use a concrete leaf
   mode name from that local XML; for the locally tested STM32F401 TIM2 case,
   this was `Internal Clock`, not a cross-family default.
   If the direct CubeMX command cannot enable the NVIC entry, declare one exact
   `timer-nvic-enable` override in the approved plan. Its `NVIC.<IRQ>_IRQn`
   key must name this plan's timer instance, its value must enable that entry,
   and the plan must assert its exact resulting `$IOC` property. The core only
   applies it to its just-created project, reloads it with `config load`,
   regenerates, and verifies the resulting source.
3. Attach one generated-file `verification` to every timer parameter,
   include `timer_input_hz`, `target_hz`, `tolerance_ppm`,
   `prescaler_parameter`, and `period_parameter` in `timing`, then
   make the plan verify generated initialization, the `.ioc` NVIC property,
   `Src/stm32*_it.c` IRQ handler, and the `HAL_TIM_IRQHandler(&handle)` route.
   Generate the new project and check every assertion.
4. Search the project for `HAL_TIM_PeriodElapsedCallback`. If a callback already
   exists, route this module through that one owner. If none exists, add exactly
   one callback through the rendered App template; it should call
   `{{MODULE_NAME}}_on_period_elapsed(htim)` and never do blocking work.
5. Only when no callback owner exists, declare `TIM_HANDLE` and `IRQ_NAME`
   in the plan's `modules` entry with `pack: "timer"`. Generate first, then run
   `module --name <declared-name> --pack timer`, `integrate`, and compile. The
   renderer refuses a second callback definition; generation refuses any
   planned value absent from the frozen generated-identifier inventory. The
   template enables the approved IRQ and starts the base timer only after
   `MX_TIM*_Init()` has completed.

The periodic application logic runs from `process()` in the main loop. The IRQ
only increments a counter, so it remains bounded and does not perform I2C,
printing, allocation, or lengthy control work.
