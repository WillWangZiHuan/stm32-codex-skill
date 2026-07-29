# I2C pack

Use this pack to configure an I2C bus and generate an HAL memory-read module.

## Plan requirements

Add `i2c` to `packs` and map each I2C operation to `pack: "i2c"`. Include the
selected instance's `SCL` and `SDA` signals and the two cited board pins. Record
their pull-ups, voltage constraints, and reservation status in the board
profile.

Inspect the selected MCU's local CubeMX I2C mode and configuration XML. Put the
exact mode, pins, and parameter names in the plan, and attach one
generated-file assertion to each parameter together with `.ioc` pin evidence.
For the F401 I2C-v1 example, Fast Mode uses `I2C_Mode: I2C_Fast` and
`ClockSpeed: 400000`; use the names from the installed database for each MCU.

Run `generate` with `--board-profile`, `--manual`, and `--plan`, then evaluate
the generated pin and source assertions.

## Module bindings

Declare the module name, `pack: "i2c"`, and the generated `I2C_HANDLE` in
`modules`. Render with `module --name <declared-name> --pack i2c`, integrate,
and compile.

The module's HAL memory APIs use an 8-bit, left-shifted device address. Keep
sensor register layout and conversion timing in device-specific application
code.
