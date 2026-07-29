# SPI pack

Use this pack to configure an 8-bit, MSB-first, Motorola-frame, full-duplex
SPI master and generate an HAL transfer module.

## Plan requirements

Add `spi` to `packs` and map the operation to `pack: "spi"`. Record the
selected `SCK`, `MISO`, and `MOSI` pins, voltage levels, attached devices,
routing, level shifters, and reservation status in the board profile.

Read the target-device protocol source for clock polarity/phase, maximum clock
rate, bit order, frame size, and chip-select strategy. Inspect the local CubeMX
SPI mode and pin XML, then select the matching mode, prescaler, polarity,
phase, data size, first-bit, TI mode, CRC, and NSS values.

For the local F401 SPI-v2.2 example, the configuration uses
`Full_Duplex_Master`, `BaudRatePrescaler`, `CLKPolarity`, `CLKPhase`,
`DataSize`, `FirstBit`, `TIMode`, `CRCCalculation`, and `NSS`. Use names from
the installed database for each target.

Software NSS places chip-select control in the device-level App module. Add
generated-file assertions for every selected parameter, the SPI handle, and
the pin configuration.

## Module bindings

Declare the module name, `pack: "spi"`, and generated `SPI_HANDLE` in
`modules`. Generate, render, integrate, and compile. The transfer API sends
and receives equal-length buffers with an explicit timeout.
