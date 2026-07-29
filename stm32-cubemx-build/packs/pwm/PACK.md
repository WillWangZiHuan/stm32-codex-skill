# PWM pack

Use this pack to configure a timer PWM output and generate a duty-cycle module.

## Plan requirements

Add `pwm` to `packs`, map the timer operation to `pack: "pwm"`, and include
the selected output pin. Record the pin, electrical load, and relevant board
constraints in the board profile.

Inspect the selected timer mode XML and choose the exact timer instance,
channel, mode, prescaler, period, and pulse parameter. Attach a generated-file
assertion to every parameter.

Add this `timing` object to the operation:

```json
{
  "timer_input_hz": 16000000,
  "target_hz": 1000,
  "tolerance_ppm": 0,
  "prescaler_parameter": "Prescaler",
  "period_parameter": "Period"
}
```

The current rate evaluator covers STM32F4 `TIM1`–`TIM14` with CubeMX-generated
unprescaled APB clocks. It reads the generated `.ioc` clock data and evaluates
the exact counter arithmetic for the selected target rate.

## Module bindings

Declare the module name, `pack: "pwm"`, generated `TIM_HANDLE`, and
`TIM_CHANNEL` in `modules`. Generate, render the pack module, integrate it,
and compile. The generated API updates duty cycle for the selected channel.
