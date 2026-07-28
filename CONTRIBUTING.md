# Contributing

This project accepts two kinds of focused pull request:

1. A capability pack under `stm32-cubemx-build/packs/<id>/`.
2. A board-data example that contains only shareable, cited facts; never commit
   a user's private manual or full-text `*.manual-index.json` without their
   permission.

## Change-admission and self-audit gate

Treat every proposed feature as a candidate for the same fixed pipeline:

```text
board manual evidence → CubeMX MCU facts → new-project configuration
→ App module → generated-source verification → compilation
```

Before implementing a change, state which link it strengthens. Reject it if it
does not strengthen one of these links, or if it creates a second workflow,
device-side agent, or IDE-dependent path.

Every audit pass—initial or repeat—must first answer the dominant-problem
question, then audit all six points:

0. **Dominant problem:** First ask, “目前最大的问题是什么？ / What is the
   largest problem right now?” Then identify the single current problem that
   could make the main pipeline incorrect, unsafe, or misleading. State the
   evidence and root cause, choose the smallest in-scope corrective action, and
   state the exact verification result that will prove it worked. Execute and
   verify that action before adding a lower-priority capability. Start the next
   audit pass by asking the same question again. An idea to solve it later does
   not count as resolution. If it cannot be resolved within the pipeline's
   boundaries, stop and record the exact gap instead of hiding it behind a new
   feature. Append the evidence, root cause, corrective action, verification,
   and remaining boundary to the root `AUDIT.md`.

1. **Need:** Identify the concrete STM32 task it makes easier.
2. **Evidence:** State the required manual facts and local CubeMX facts. Every
   new or changed board-profile fact needs a short page-local text anchor that
   validates against the exact manual; stop on missing, visual-only, or
   conflicting facts rather than guessing.
3. **Boundary:** Keep generated CubeMX code and user-owned existing `.ioc`
   files untouched; put application code in `App/` and integration only in
   CubeMX user-code regions.
4. **Minimality:** Prefer one focused pack or the smallest core change. Do not
   add a runtime, dependency, abstraction, or compatibility path without a
   direct requirement.
5. **Proof:** Add deterministic tests when behavior changes, then run the
   relevant generated-file and compilation checks. Label the result precisely:
   unit-tested, compile-verified, or hardware-verified.
6. **Handoff:** Update the pack contract and user-facing documentation, review
   the staged file list for private manuals, full-text manual indexes, and
   generated artifacts, and record any remaining validation gap.

If any point fails, stop the feature instead of compensating with a guess or a
silent fallback.

## Capability-pack contract

Each pack is independent and must contain:

```text
packs/<id>/
├── manifest.json
├── PACK.md
└── templates/
```

- `manifest.json` declares an exact lowercase ID, its evidence/CubeMX
  requirements, templates, post-generation checks, a machine-checked
  `plan_resources` object, and an explicit `ioc_override_kinds` list.
  `plan_resources.operation_instance_prefixes` lists the peripheral
  instance prefixes the pack owns; `plan_resources.direct_pin_signals`
  lists the exact direct `set pin` signals it owns.
  `plan_resources.minimum_operation_pins` is the minimum number of explicit
  pins for one operation, and `required_operation_signal_suffixes` lists
  suffixes that the core expands to `<instance>_<suffix>` and requires in
  that operation. Use empty/zero values only when the pack genuinely supports
  that shape; for example, a base timer can use no physical pin. Only
  core-supported semantic override kinds may be declared.
- `PACK.md` tells Codex how to inspect the local CubeMX database, what profile
  evidence is mandatory, how to build a configuration plan, and how to verify
  generated code.
- Templates live under `templates/`, use explicit `{{TOKEN}}` placeholders, and
  must not hard-code a board pin, timer handle, or peripheral instance.

Every executable capability pack must declare exactly one `.h.tmpl` and one
`.c.tmpl` for `module --pack`. Use uppercase placeholder names. Except for the
core-provided `MODULE_NAME` and `MODULE_GUARD`, every placeholder must resolve
to one generated C identifier such as `hi2c1`, `GPIOA`, `GPIO_PIN_1`, or
`TIM2_IRQn`; never design a template that needs arbitrary C expressions or
free-form source fragments. The plan declares every rendered module's exact
name, selected pack, and placeholder values before CubeMX runs; do not design a
post-generation binding-file workflow.

Do not put free-form CubeMX script commands in a pack. A pack must produce the
restricted `configuration-plan.json` contract and let the stable generator
validate it. Every plan that uses the pack must include its ID in the plan's
non-empty `packs` list; the core checks that this manifest remains
contract-valid before it generates a project. Every operation, direct pin
assignment, and semantic override in that plan must name its owning selected
pack; the core rejects a resource absent from that pack's `plan_resources`
or override kinds. The successful generation records
the pack contract fingerprint in the new project, so a later module render
stops if a contributor changed that pack's manifest, instructions, or template.
It also freezes the project-specific generated C identifier inventory before
App files exist, and fingerprints its non-user-code content. All plan-declared
bindings must be present in that inventory before the project provenance is
written. It freezes the root `.ioc` hash and CubeMX's embedded generator,
database, and firmware-package facts too. Rendering rechecks all of those
facts, while safe CubeMX `USER CODE` edits are excluded from the source
fingerprint. It also freezes the root CubeMX Makefile after excluding only the
exact core-owned `codex-modules.mk` include block; if that block exists, the
included file must exactly match the core-generated content. A manually changed
Makefile or module inclusion file requires fresh generation. It also freezes
the direct generated C/assembly/linker files named by that Makefile and every
file below its generated C/assembly include directories. Keep user work in
`App/` or CubeMX `USER CODE` regions: those are deliberately excluded (with
C/H line endings normalized), while a changed generated build input requires
fresh generation.

## Required checks

Run these before opening a pull request:

```bash
python -m unittest discover -s tests -v
python stm32-cubemx-build/scripts/validate_packs.py
```

For a pack that changes executable behavior, add a deterministic test under the
repository `tests/` directory. For a pack that targets a real board, document
the precise manual pages and record whether its claim was compile-verified or
hardware-verified. Never label a compile-only test as hardware validation.

For a Windows-specific claim, run scripts/windows_smoke.ps1 on a Windows host
with a real manual/profile/plan chain and include the non-private command output
in the pull request. Its WINDOWS_SMOKE_PASS result is compile-only evidence,
not hardware evidence.

## Core boundaries

Do not change generated CubeMX code outside user-code regions, do not alter an
existing user-owned `.ioc`, and do not add flashing, debugging, dynamic
downloads, device agents, or user credentials to this Skill. A pack may declare
only a core-supported semantic `ioc_override_kinds` capability for the freshly
created project; it may not authorize arbitrary keys. Every planned override
must be tied to the planned peripheral or pin and have an exact regenerated
`$IOC` assertion. Keep the core cross-platform and use only dependencies
declared in `stm32-cubemx-build/requirements.txt`.
