# GPIO push-pull output pack

Use this pack only for one documented, push-pull digital output in a new
project. It deliberately does **not** implement GPIO input, EXTI, interrupts,
callbacks, open-drain output, pull selection, output-speed selection, or an
automatic blink loop.

The plan must include `"packs": ["gpio"]` (plus any other selected pack IDs).
Every direct pin assignment owned by this pack must use `"pack": "gpio"`
and its only supported direct signal is `GPIO_Output`. This pack owns no
peripheral operations. That machine-checked boundary records this pack as the
source of the workflow; it does not replace the manual, local CubeMX,
generated-output, or compilation evidence below.

1. Read the board-profile citations for the selected physical pin. The manual
   must establish what it connects to, its voltage/current or load constraint,
   its active polarity, and which physical startup level is safe. Stop if an
   LED, relay, chip-select, or other load is merely assumed from a board name
   or a schematic fragment without a cited safe level.
2. Inspect the selected MCU's local CubeMX GPIO mode XML and pin XML. Confirm
   that the exact pin supports `GPIO_Output`. On the local F401 GPIO database,
   the observed default output properties are `GPIO_MODE_OUTPUT_PP`,
   `GPIO_NOPULL`, and `GPIO_SPEED_FREQ_LOW`; check the installed version rather
   than treating those names as portable facts.
3. Use `pin_assignments`, not a fake GPIO peripheral operation. The verified
   macOS CubeMX 6.18 probe accepted `set pin PA1 GPIO_Output` but rejected
   `set mode GPIO Output`; the core's direct assignment emits only the accepted
   `set pin` form. A minimal plan has this shape:

   ```json
   {
     "schema_version": 5,
     "mcu": "STM32F401RETx",
     "packs": ["gpio"],
     "modules": [
       {
         "name": "status_output",
         "pack": "gpio",
         "bindings": {"GPIO_PORT": "GPIOA", "GPIO_PIN": "GPIO_PIN_1"}
       }
     ],
     "operations": [],
     "pin_assignments": [
       {"pack": "gpio", "pin": "PA1", "signal": "GPIO_Output"}
     ],
     "ioc_overrides": [
       {"pack": "gpio", "kind": "gpio-initial-state", "key": "PA1.GPIOParameters", "value": "PinState"},
       {"pack": "gpio", "kind": "gpio-initial-state", "key": "PA1.PinState", "value": "GPIO_PIN_SET"}
     ],
     "verifications": [
       {"file": "$IOC", "contains": "PA1.Signal=GPIO_Output"},
       {"file": "$IOC", "contains": "PA1.GPIOParameters=PinState"},
       {"file": "$IOC", "contains": "PA1.PinState=GPIO_PIN_SET"},
       {"file": "Src/main.c", "contains": "HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_SET);"},
       {"file": "Src/main.c", "contains": "GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;"}
     ]
   }
   ```

   Replace every pin, port, and initial level with facts from the actual
   profile and generated project. `GPIO_PIN_SET` and `GPIO_PIN_RESET` are
   electrical levels, not guessed `on` and `off` semantics. Declare an
   `gpio-initial-state` override pair only when the local CubeMX output proves
   it is needed. Both properties must name the same planned `GPIO_Output` pin,
   and the plan must assert both exact `$IOC` properties. The core applies it
   only in the newly created project, reloads it, and regenerates it before
   evaluating assertions.
4. Assert the generated `.ioc`, the initial `HAL_GPIO_WritePin`, and every
   `GPIO_InitStruct` property that matters to the documented load. A successful
   CubeMX command alone is not proof.
5. Declare `GPIO_PORT` and `GPIO_PIN` in that plan's `modules` entry,
   as shown above, using the expected local CubeMX-generated identifiers. Generate
   first: the core records the module only if both values are actually frozen
   from `MX_GPIO_Init()`'s configuration source. Then run
   `module --name status_output --pack gpio`, `integrate`, and compile. The
   App API exposes raw HAL pin state so it does not invent active-high or
   active-low semantics.

The template does not write or toggle from `process()`. Application code must
decide when an output transition is safe. Compilation proves integration only;
it does not prove voltage levels, load current, boot behavior, or hardware
operation.
