# UART pack

Use this pack to configure an asynchronous UART, USART, or LPUART port and
generate HAL send/receive calls with an explicit timeout.

## Plan requirements

Add `uart` to `packs` and map the port operation to `pack: "uart"`. Record the
TX/RX pins, voltage level, external bridge or transceiver, reservation status,
and clock basis in the board profile.

Inspect the selected MCU's local CubeMX UART XML and pin XML. Select the exact
asynchronous mode, instance, TX/RX signals, baud rate, framing, and
flow-control settings. Attach generated-file assertions for each parameter and
for the generated UART handle, `Init.BaudRate`, `Init.Mode`, and `HAL_UART_Init`.

For the local F401 USART-v1 example, asynchronous full duplex uses
`Asynchronous`, `BaudRate`, and generated `UART_MODE_TX_RX`; obtain the names
for each target from its installed CubeMX data.

## Module bindings

Declare the module name, `pack: "uart"`, and the generated `UART_HANDLE` in
`modules`. Generate, render the pack module, integrate it, and compile.

Schedule the timeout-based HAL calls in the application flow that owns their
time budget.
