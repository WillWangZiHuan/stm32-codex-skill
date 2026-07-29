# Board-profile contract

`board-profile.json` is the project record for page-cited board facts. Keep
the user manual and full-text `*.manual-index.json` in local working storage;
the profile carries concise claims and anchors.

`index-pdf` creates a page-numbered index from one manual snapshot. Validation
uses the same snapshot to check page anchors and record the SHA-256. Generation
records the matching profile snapshot hash in project provenance.

## Required shape

```json
{
  "schema_version": 2,
  "board": {
    "name": "Board name exactly as documented",
    "manual": {"path": "board-manual.pdf", "sha256": "<64 lowercase hex characters>"}
  },
  "mcu": {
    "part_number": "STM32F401RETx",
    "evidence": [{"page": 4, "anchor": "STM32F401RE", "claim": "U1 is STM32F401RE"}]
  },
  "pins": [
    {
      "pin": "PB8",
      "board_signal": "I2C SCL on J2.3",
      "status": "available",
      "electrical_constraints": ["4.7 kOhm pull-up to 3.3 V"],
      "evidence": [{"page": 12, "anchor": "J2.3 PB8 4.7 kOhm", "claim": "J2.3 routes to PB8 and has a 4.7 kOhm pull-up"}]
    }
  ],
  "clocks": [
    {
      "name": "HSE",
      "frequency_hz": 8000000,
      "evidence": [{"page": 8, "anchor": "8 MHz crystal", "claim": "8 MHz crystal connected to HSE"}]
    }
  ],
  "constraints": [
    {
      "description": "PA13 and PA14 are reserved for SWD",
      "evidence": [{"page": 10, "anchor": "PA13 PA14 SWD", "claim": "SWD header wiring"}]
    }
  ]
}
```

## Profile rules

- Add evidence for every MCU, pin, clock, and board constraint used by the
  plan. An evidence object contains a one-based page number, concise claim,
  and an 8–240 character text anchor from that page.
- Use `available`, `reserved`, or `used` for pin status. Configuration plans
  select pins marked `available`.
- Describe `board_signal` as documented wiring, connector labeling, or board
  role. Use CubeMX for alternate-function selection.
- Include the clock facts needed by PWM or timer calculations.
- Validate the profile against the exact uploaded PDF before generation. When a
  needed diagram fact lacks extractable text, ask for a cited textual source
  for that fact.
- Keep profile and manual inputs unchanged while validation or generation is
  running.
