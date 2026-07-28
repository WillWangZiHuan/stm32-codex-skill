# Legacy STM32CubeMX 6.x command-line contract

Use legacy STM32CubeMX 6.x in quiet script mode for new-project generation.

## Stable generation commands

- Run one CubeMX command per script line.
- Run `-q <script>` for the non-interactive generator path.
- Load an exact MCU with `load <mcu>`.
- Set the project name, parent path, Makefile toolchain, structure, and copy
  policy before `project generate`.
- `project path` is the parent output directory. CubeMX creates a child
  directory named after `project name`.

```text
load STM32F401RETx
waitclock 5
project name f401_baseline
project toolchain "Makefile"
project path "/absolute/output/path"
SetStructure Basic
SetCopyLibrary "copy all"
project generate
exit
```

## Configuration commands used by the Skill

CubeMX 6.18 on the verified macOS installation accepts these interactive-script
forms before project setup:

```text
set mode I2C1 I2C
set pin PB8 I2C1_SCL
set ip parameters I2C1 I2C_Mode I2C_Fast
set ip parameters I2C1 ClockSpeed 400000
```

The specific mode, signal, and parameter names are MCU/IP-version dependent.
Use them only after inspecting the local CubeMX database and put generated-file
assertions in the configuration plan. An `OK` result does not prove that an
arbitrary parameter changed generated C code.

Quote a mode or parameter value that contains spaces, for example
`set mode TIM3 "PWM Generation1 CH1"`.

## GPIO-output exception observed on macOS CubeMX 6.18

On the verified local F401 probe, CubeMX rejected `set mode GPIO Output` with
its standalone `KO` marker, but accepted `set pin PA1 GPIO_Output`. The core
therefore exposes the deliberately restricted `pin_assignments` plan field for
this case. It emits only the accepted `set pin` command; it must never invent a
generic `set mode GPIO ...` command.

For that same probe, a non-default `PinState` needed the restricted
fresh-project `gpio-initial-state` pair:
`<pin>.GPIOParameters=PinState` and
`<pin>.PinState=GPIO_PIN_SET|GPIO_PIN_RESET`. The pair is allowed only for
the same planned `GPIO_Output` pin, followed by `config load` and
regeneration. Treat that as version-specific evidence: declare the exact
properties only after checking the local MCU database and generated output,
then assert both resulting `.ioc` properties and the generated GPIO
initialization source. Do not generalize this observation to another MCU,
CubeMX version, or electrical load without local evidence.

Do **not** use `config save` in this Skill's no-GUI workflow: on the verified
macOS CubeMX version it opens a system Save Project As window. New-project
`project generate` writes the `.ioc` non-interactively after the validated
commands above.

When an approved configuration plan needs one supported `.ioc` property that
the direct command interface cannot set, the core may edit only its just-created
new project's `.ioc`, then force CubeMX to read and regenerate it using:

```text
config load "/absolute/new-project/new-project.ioc"
project generate
exit
```

`load <mcu>` is only for selecting an MCU. It must never be used to load an
`.ioc` path.

## Safety rules

- Do not place credentials in CubeMX scripts.
- Firmware package downloads and license acceptance remain user actions.
- Do not modify existing user-owned `.ioc` files through this contract.
- Validate CubeMX behavior on each operating system/version before reporting it
  as verified.

## Official reference

Use ST's [STM32CubeMX 6.18 command-line documentation](https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.0/en/docs/markup/CubeMX_CLI.html) as the source of truth for documented command syntax and package-management behavior.
