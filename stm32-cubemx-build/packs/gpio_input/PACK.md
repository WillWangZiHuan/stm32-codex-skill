# GPIO input and key pack

Use this pack for buttons, switches, and digital inputs. Record the board
silkscreen, connector, pull circuit, active level, and shared networks in the
board profile.

Select `GPIO_Input` for polling or the matching `GPIO_EXTI<n>` signal for an
interrupt-assisted design. Add the paired `gpio-input-pull` overrides:

```json
[
  {"pack": "gpio_input", "kind": "gpio-input-pull", "key": "PE3.GPIOParameters", "value": "GPIO_PuPd"},
  {"pack": "gpio_input", "kind": "gpio-input-pull", "key": "PE3.GPIO_PuPd", "value": "GPIO_PULLUP"}
]
```

Declare a module with `GPIO_PORT`, `GPIO_PIN`, `ACTIVE_LEVEL`, `DEBOUNCE_MS`,
and `LONG_PRESS_MS`. Use `GPIO_PIN_RESET` for active-low inputs and
`GPIO_PIN_SET` for active-high inputs. The module exposes stable state, press,
release, and long-press events. Call `notify_exti()` from the project's single
EXTI callback owner when EXTI is selected; the module does not claim the HAL
callback itself.
