# STM32CubeMX 6.x command-line notes

Use STM32CubeMX 6.x quiet script mode for fresh-project generation.

## Project generation commands

- Put one CubeMX command on each script line.
- Run CubeMX with `-q <script>`.
- Select the MCU with `load <mcu>`.
- Set project name, parent path, Makefile toolchain, structure, and copy policy
  before `project generate`.
- Use `project path` for the parent output directory; CubeMX creates the child
  project directory from `project name`.

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

## Configuration commands

CubeMX 6.18 on the verified macOS installation accepts these forms before
project setup:

```text
set mode I2C1 I2C
set pin PB8 I2C1_SCL
set ip parameters I2C1 I2C_Mode I2C_Fast
set ip parameters I2C1 ClockSpeed 400000
```

Mode, signal, and parameter names vary by MCU and IP version. Read the local
CubeMX database for the selected device and attach generated-file assertions
to the configuration plan. Quote values containing spaces, for example:

```text
set mode TIM3 "PWM Generation1 CH1"
```

## GPIO output workflow

The verified macOS CubeMX 6.18 GPIO workflow uses:

```text
set pin PA1 GPIO_Output
```

Use `pin_assignments` in the configuration plan for this direct GPIO signal.
For an initial output state, add the `gpio-initial-state` pair
`<pin>.GPIOParameters=PinState` and
`<pin>.PinState=GPIO_PIN_SET|GPIO_PIN_RESET`, then reload and regenerate the
fresh project through `config load`.

## Reloading a generated `.ioc`

For a plan-supported semantic `.ioc` setting, apply the property to the fresh
project, then reload and regenerate it:

```text
config load "/absolute/new-project/new-project.ioc"
project generate
exit
```

Use `load <mcu>` for MCU selection and `config load <path>` for the generated
project configuration.

## Environment notes

- Keep credentials outside CubeMX scripts.
- Install firmware packages and accept their licenses in the user's local
  CubeMX environment.
- Validate command behavior for the local operating system and CubeMX version
  used by the project.

## Official reference

Use ST's [STM32CubeMX 6.18 command-line documentation](https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.0/en/docs/markup/CubeMX_CLI.html)
for command syntax and package-management behavior.
