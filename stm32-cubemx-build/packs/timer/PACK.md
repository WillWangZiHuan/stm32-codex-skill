# Timer pack

Use this pack to configure a base timer and provide periodic dispatch for the
application main loop.

## Plan requirements

Add `timer` to `packs` and map the base-timer operation and any
`timer-nvic-enable` override to `pack: "timer"`. Include the timing contract:

```json
{
  "timer_input_hz": 16000000,
  "target_hz": 1000,
  "tolerance_ppm": 0,
  "prescaler_parameter": "Prescaler",
  "period_parameter": "Period"
}
```

Inspect the local timer mode and configuration XML for the exact base-timer
mode, prescaler, period, and NVIC setting. The local STM32F401 TIM2 example
uses `Internal Clock`; select the corresponding concrete mode for the target
MCU. Add generated-file assertions for the timer initialization, `.ioc` NVIC
property, IRQ handler, and `HAL_TIM_IRQHandler(&handle)` route.

When the direct command interface needs an explicit NVIC property, use the
`timer-nvic-enable` override and assert the generated `$IOC` value. The current
rate evaluator covers STM32F4 `TIM1`–`TIM14` with CubeMX-generated
unprescaled APB clocks.

## Module bindings and dispatch

Use one `HAL_TIM_PeriodElapsedCallback` owner for the project. Route the
module through that owner with `{{MODULE_NAME}}_on_period_elapsed(htim)`.

Declare `TIM_HANDLE` and `IRQ_NAME` for a new timer callback route in the
module's `bindings`. Generate, render, integrate, and compile. The IRQ path
increments a tick counter; the main loop consumes those ticks through
`process()`.
