# I2C pack

Use this pack only for a new project generated with an evidence-backed
`board-profile.json` and `configuration-plan.json`.

The plan must include `"packs": ["i2c"]` (plus any other selected pack IDs).
Every I2C operation must use `"pack": "i2c"`. The core accepts only an
`I2C` instance prefix for that ownership; the local CubeMX database still
decides the exact instance, mode, pins, and parameters. All manual,
generated-output, and compilation checks below remain required.
The plan must explicitly include both `<instance>_SCL` and
`<instance>_SDA` signals; a one-wire or default-pin I2C plan stops before
CubeMX runs.

1. Read the profile citations for the two physical pins, their pull-ups, voltage
   constraints, and reservation status. Stop if either pin is not `available`.
2. Inspect the installed MCU's CubeMX I2C mode/configuration XML. Select an I2C
   instance and its exact `SCL`/`SDA` signals from that database; do not infer
   alternate functions from a board name or an online pinout.
3. Put the exact mode, pins, and parameter names into the configuration plan.
   Attach one generated-file `verification` to every parameter, as well as
   `.ioc` pin evidence. For the
   F401 I2C-v1 example, Fast Mode uses `I2C_Mode: I2C_Fast` and
   `ClockSpeed: 400000`; other MCU IP versions may use different names.
4. Run `generate` with `--board-profile`, `--manual`, and `--plan`. Do not call
   this pack successful until the declared generated-source assertions pass.
5. In the plan's `modules` list, declare the module name, `pack: "i2c"`,
   and `I2C_HANDLE` expected from the locally inspected generated HAL
   declarations. Then generate and run `module --name <declared-name> --pack i2c`
   followed by `integrate`. Generation refuses to write provenance if the declared
   handle is absent from the frozen generated-identifier inventory.

The HAL address parameter below is explicitly an 8-bit, left-shifted address,
which is the convention expected by the STM32 HAL I2C memory APIs. Sensor
register layout and conversion timing remain device-specific application code.
