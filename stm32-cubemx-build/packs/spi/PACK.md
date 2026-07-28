# SPI pack

Use this pack only for a new project generated from an evidence-backed
`board-profile.json` and `configuration-plan.json`.

The plan must include `"packs": ["spi"]` (plus any other selected pack IDs).
Every SPI operation must use `"pack": "spi"`. The core accepts only an
`SPI` instance prefix for that ownership; the local CubeMX database still
decides the exact mode, pins, and parameters. All manual, generated-output,
and compilation checks below remain required.

1. Read the profile citations for the physical `SCK`, `MISO`, and `MOSI` pins.
   Check voltage levels, attached devices, routing or level-shifter constraints,
   and reservation status. Stop if any selected pin is not `available` or if
   the board-side electrical topology is unknown.
2. Read the target-device data sheet or another user-supplied protocol source.
   It must establish clock polarity/phase, maximum SPI clock rate, bit order,
   frame size, and the chip-select strategy. A board manual normally proves
   wiring, not a peripheral's SPI timing; do not guess a device protocol from a
   board name or from CubeMX defaults.
3. Inspect the selected MCU's local CubeMX SPI mode XML and MCU pin XML. For
   the local F401 SPI-v2.2 example, the initial supported bus mode is
   `Full_Duplex_Master`, with `BaudRatePrescaler`, `CLKPolarity`, `CLKPhase`,
   `DataSize`, `FirstBit`, `TIMode`, `CRCCalculation`, and `NSS` parameter
   names. Those names are not portable defaults.
4. This initial pack supports only an 8-bit, MSB-first, Motorola-frame,
   full-duplex SPI master using software NSS. Put the exact approved
   clock-polarity, clock-phase, and prescaler values into the configuration
   plan. Attach one generated-file `verification` to every parameter, plus
   `.ioc` pin evidence and generated-source assertions for the SPI handle and
   every approved SPI initializer value.
5. Software NSS means this pack does not create or toggle a chip-select GPIO.
   A device-level App module must own the documented chip-select action. Stop
   if that ownership cannot be identified from the supplied material.
6. In the plan's `modules` list, declare the module name, `pack: "spi"`,
   and the exact `SPI_HANDLE` expected from the local CubeMX output. Run
   `generate` with `--board-profile`, `--manual`, and `--plan`; then run
   `module --name <declared-name> --pack spi`, `integrate`, and compile.
   Generation rejects a syntactically valid planned handle if it is absent from
   the frozen generated-identifier inventory.

`{{MODULE_NAME}}_transfer()` sends and receives the same number of bytes with
an explicit timeout. It may block. Do not call it from the default `process()`
hook, an interrupt, or a time-critical control loop without an explicit design.
This initial pack deliberately excludes chip-select GPIO control, DMA,
interrupts, callbacks, one-line SPI, hardware NSS, and device register
protocols.
