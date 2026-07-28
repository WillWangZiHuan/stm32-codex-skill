# Stable core contract

## Ownership boundaries

| Area | Owner | Rule |
| --- | --- | --- |
| User board manual | User | Source of board wiring and electrical facts. Keep private unless the user chooses otherwise. |
| `board-profile.json` | Project | Evidence-backed, page-anchor-validated facts derived from the supplied manual. |
| CubeMX database | Installed CubeMX | Source of MCU pin modes, peripheral instances, and parameter names. |
| Generated `.ioc` and HAL code | CubeMX | Create a new project; do not manually edit generated sections. |
| `App/Inc`, `App/Src` | Codex/user | Application logic and capability-pack modules. |
| `Src/main.c` user-code blocks | Codex/user | Only safe place this Skill may add includes, init calls, and non-blocking process calls. |

## Integration invariants

- `generate` requires the exact manual, its validated `board-profile.json`,
  and an approved `configuration-plan.json`; it rejects an evidence-free
  baseline project. The plan must also name one or more installed,
  contract-valid capability packs so the requested configuration and App
  modules have an auditable source. It reads the profile and manual once,
  validates and hashes those exact input snapshots, and records the exact
  validated profile snapshot hash in fresh-project provenance.
- Every planned peripheral operation, direct pin assignment, and semantic
  `ioc_overrides` entry must name the selected capability pack that owns it.
  The stable core rejects a peripheral instance prefix or direct pin signal not
  declared in that pack's machine-checked `plan_resources` contract. It also
  rejects an operation that misses the pack's declared minimum pin count or
  exact `<instance>_<suffix>` signals. Exact mode, alternate-function pin,
  and parameter validity still comes only from the locally installed CubeMX
  database and generated-output assertions.
- A fresh-project `ioc_overrides` entry is never a general property-write
  escape hatch. It must use one semantic kind declared by a selected pack,
  remain tied to a planned GPIO output or timer operation, and have an exact
  generated `$IOC` assertion before CubeMX reloads and regenerates the project.
- After generated-file verification, `generate` writes
  `codex-stm32-project.json` in that fresh project. It records only the exact
  MCU, manual/board-profile/plan hashes, selected pack IDs, and a fingerprint of each pack's
  manifest, instructions, and templates. It also freezes the C identifiers
  found in CubeMX's configuration-bearing generated source/header files before
  any App module exists, plus a fingerprint of that source with user-code
  contents excluded. It freezes the exact root `.ioc` hash and the
  `MxCube.Version`, `MxDb.Version`, and firmware-package facts embedded in
  that fresh `.ioc`, and it fingerprints the root CubeMX Makefile after
  removing only the exact owned `codex-modules.mk` include block. If that block
  exists, its `codex-modules.mk` file must have the exact core-generated
  content. It also fingerprints the direct generated C/assembly/linker files
  named by that Makefile and every file below its generated C/assembly include
  directories. `App/` is excluded; C/H files normalize line endings and strip
  only `USER CODE` regions before hashing. Every pack-rendered module's name, pack,
  and bindings must
  have been declared in the approved configuration plan and are recorded only
  after all bindings match that frozen inventory; it never copies manual text.
- The manual index, project provenance, and new App module `.h`/`.c` files use
  exclusive file creation. If a competing file appears after a preflight check,
  the command stops without overwriting that file.
- Application modules provide `<name>_init()` and `<name>_process()`.
- `module` manages Makefile inclusion only through its exact owned
  `codex-modules.mk` include block and exact generated
  `codex-modules.mk` content; it does not overwrite an existing `.c` or `.h`
  module file or accept a manually changed integration block. Its module source
  files are created exclusively rather than trusting a prior existence check.
- `module --pack <id>` renders exactly one declared `.h.tmpl` and one
  `.c.tmpl` for a new module. The project provenance must name that exact
  unmodified pack module and its exact planned bindings. Bindings may only be
  generated C identifiers and must exactly match the frozen identifier
  inventory before provenance is written. The core recomputes the identifier
  inventory, source fingerprint, root `.ioc` hash, Makefile baseline, and
  generated build-input fingerprint at rendering time. It ignores only
  CubeMX user-code-region contents and `App/`. A generic module cannot use a
  plan-declared pack-module name. A pack fingerprint or provenance-schema
  mismatch requires a fresh generation, not a manual provenance edit.
- `build` reloads the same project provenance before invoking Make. A missing,
  altered, or regenerated configuration, CubeMX Makefile, or owned module
  inclusion file, generated compiler/linker input, or generated include-tree
  file must stop compilation rather than produce a misleading compile-success
  claim.
- `integrate` owns only its marker blocks inside `USER CODE BEGIN Includes`,
  `USER CODE BEGIN 2`, and `USER CODE BEGIN 3`. It is idempotent.
- If the matching include or call already appears outside a managed marker,
  integration stops instead of duplicating it.
- A capability pack may add a HAL callback only after determining that one
  existing callback owner will dispatch all needed behavior. Never add a second
  definition of a global HAL callback. The timer renderer rejects a project
  that already defines `HAL_TIM_PeriodElapsedCallback`.
- Build success means the toolchain accepted the source. It says nothing about
  pin voltage, device response, timing margins, boot behavior, or hardware
  safety.
