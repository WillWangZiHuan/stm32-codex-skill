# UART pack

Use this pack only for a new project generated from an evidence-backed
`board-profile.json` and `configuration-plan.json`.

The plan must include `"packs": ["uart"]` (plus any other selected pack IDs).
Every UART operation must use `"pack": "uart"`. The core accepts only
`USART`, `UART`, or `LPUART` instance prefixes for that ownership;
the local CubeMX database still decides the exact mode, pins, and parameters.
All manual, generated-output, and compilation checks below remain required.

1. Read the profile citations for the physical TX and RX pins, their voltage
   level, any on-board USB/UART bridge or transceiver, and their reservation
   status. Stop if either pin is not `available`, if the external interface is
   unknown, or if the requested baud rate lacks a meaningful board clock basis.
   Do not assume that an external adapter's TX/RX crossover or voltage level is
   safe from a board name.
2. Inspect the selected MCU's local CubeMX USART/UART mode XML and MCU pin XML.
   Choose the exact asynchronous mode, instance, TX/RX signals, baud rate,
   framing, and flow-control settings from those files. Do not copy parameter
   names from another STM32 family.
3. Attach one generated-file `verification` to every UART parameter and include
   generated-source assertions for the UART handle, `Init.BaudRate`,
   `Init.Mode`, and `HAL_UART_Init`. For the local F401
   USART-v1 example, asynchronous full duplex uses mode `Asynchronous`,
   `BaudRate`, and generated `UART_MODE_TX_RX`; these names are not portable
   defaults.
4. Run `generate` with `--board-profile`, `--manual`, and `--plan`. Do not call
   the configuration successful until the generated pin and source assertions
   pass.
5. In the plan's `modules` list, declare the module name, `pack: "uart"`,
   and the `UART_HANDLE` expected from the local CubeMX output. Generate first, then
   run `module --name <declared-name> --pack uart`, `integrate`, and compile.
   Generation rejects a syntactically valid planned handle if it was not frozen
   from the generated CubeMX configuration source.

The two module APIs explicitly pass their timeout to the STM32 HAL. They may
block, so do not call them from the default `process()` hook, an interrupt, or a
time-critical control loop without an explicit design decision. This initial
pack intentionally does not configure DMA, receive interrupts, callback
ownership, `printf` retargeting, line editing, framing protocols, or buffering.
