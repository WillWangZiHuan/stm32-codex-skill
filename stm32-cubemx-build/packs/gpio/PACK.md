# GPIO push-pull output pack

Use this pack to configure a documented push-pull digital output and generate
an App module with explicit write and toggle calls.

## Plan requirements

Add `gpio` to `packs`. Express the output through `pin_assignments`:

```json
{
  "pack": "gpio",
  "pin": "PA1",
  "signal": "GPIO_Output"
}
```

Document the selected pin's connected load, voltage/current constraints,
polarity, and startup level in the board profile. Inspect the selected MCU's
local CubeMX GPIO mode and pin XML, then add assertions for the generated
signal, initialization call, mode, pull, speed, and initial level relevant to
the hardware.

The macOS CubeMX 6.18 workflow uses the direct command
`set pin PA1 GPIO_Output`. Add the `gpio-initial-state` override pair when the
plan requires an explicit generated `PinState`:

```json
[
  {"pack": "gpio", "kind": "gpio-initial-state", "key": "PA1.GPIOParameters", "value": "PinState"},
  {"pack": "gpio", "kind": "gpio-initial-state", "key": "PA1.PinState", "value": "GPIO_PIN_SET"}
]
```

Use `$IOC` assertions for both properties and a source assertion for
`HAL_GPIO_WritePin`.

## Module bindings

Declare the generated identifiers in `modules`:

```json
{
  "name": "status_output",
  "pack": "gpio",
  "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"}
}
```

Generate the project, render the module, integrate it, and compile. The module
API exposes raw HAL pin levels; application code maps those levels to the
device's visible behavior.
