# Community board-package contract

A community board package makes verified board facts reusable without storing
the vendor manual in the repository. Put each package under
`boards/<board-id>/`, where `<board-id>` is globally unique lowercase
hyphen-case such as `st-nucleo-f401re`.

## Required layout

```text
boards/<board-id>/
├── manifest.json
├── board-profile.json
└── examples/
    └── optional.configuration-plan.json
```

`manifest.json` uses this shape:

```json
{
  "schema_version": 1,
  "id": "vendor-board-name",
  "vendor": "Documented vendor name",
  "name": "Board name exactly matching board-profile.json",
  "summary": "One sentence describing the reusable board data.",
  "revisions": ["documented hardware revision"],
  "mcu": "STM32F401RETx",
  "profile": "board-profile.json",
  "manual": {
    "title": "Official manual title and revision",
    "url": "https://vendor.example/manual.pdf",
    "sha256": "<64 lowercase hex characters>"
  },
  "result_level": "profile",
  "examples": []
}
```

## Contribution rules

- Link to an official HTTPS source. Do not commit vendor manuals or extracted
  full-text manual indexes unless their license explicitly permits
  redistribution.
- Set `manual.sha256` to the exact PDF used for the profile. It must match
  `board-profile.json`.
- Follow `board-profile-contract.md` for page-cited MCU, clock, pin, connector,
  electrical, conflict, and board-revision facts.
- Use `profile`, `configuration`, `compile`, or `hardware` for
  `result_level`. Do not claim a higher result level than the submitted
  evidence establishes.
- Put optional configuration plans below the package directory and list their
  relative paths in `examples`. Every example must use the package MCU.
- Keep one pull request focused on one board package or one capability.

Before opening a pull request, run:

```bash
python scripts/validate_boards.py
python scripts/list_boards.py
```

When using a community package, download the official manual yourself, verify
its SHA-256, validate the cited profile against that exact PDF, and then create
the configuration plan. A board package never authorizes automatic downloads,
firmware-package installation, flashing, or external commands.
