# Board-profile contract

`board-profile.json` is a project-owned record of verified board facts. It is
not a copy of the user manual and it is not a global memory store. Keep the
user's PDF private unless they explicitly choose to commit it. Each evidence
record contains only a short page-local text anchor, never a page or manual
copy.

`index-pdf` produces a separate full-text `*.manual-index.json` working file.
That file is private, must use the enforced suffix, and is ignored by this
repository; do not publish it with a board profile or a capability pack.
It uses exclusive creation: if that output path already exists, or another
process creates it while indexing runs, indexing stops without replacing it.
Both indexing and validation take one in-memory snapshot of their manual input:
the extracted page text and recorded SHA-256 always come from the same bytes.
Profile validation likewise returns the exact profile bytes it validated so
`generate` can record that same profile hash in project provenance.

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

`pins`, `clocks`, and `constraints` may be empty when the manual does not make
those facts available. That is not permission to guess: a feature needing an
absent fact must stop until the user supplies it.

## Rules

- Every claimed MCU, pin, clock, and board constraint needs at least one
  evidence object with a one-based PDF `page`, a concise `claim`, and an
  `anchor` copied from the cited page's extractable text. After NFKC,
  case, and whitespace normalization, the anchor must contain 8–240 characters
  and occur on that exact page. Keep it short; it is a proof handle, not a
  manual excerpt store.
- `status` is exactly `available`, `reserved`, or `used`. A configuration plan
  can use only `available` pins.
- `board_signal` describes real board wiring, connector labeling, or the
  documented board role. It is not a guessed MCU alternate function.
- A timer/PWM request must cite enough clock information to make frequency or
  period calculations meaningful. If the board uses only internal clocking,
  record the manual's relevant constraint or explicitly state that the manual
  does not establish an external clock.
- Do not add a pin merely because the MCU package exposes it. The board may not
  route it, may reserve it, or may attach incompatible circuitry.
- Validate the profile against the exact uploaded PDF before generation. The
  validator checks its SHA-256, cited page bounds, and every page-local anchor.
  Codex must still read the cited page and make only a claim supported by that
  anchor. If a needed schematic or picture has no extractable text anchor, stop
  and request a textual source that establishes the fact; do not translate an
  unverified visual guess into a profile. Indexing rejects a PDF with no
  extractable text, and validation explicitly identifies an empty cited page,
  so report that document-evidence gap rather than describing it as a generic
  profile error.
- Do not replace the profile or PDF while validation or generation is running.
  The core uses a one-read input snapshot, so its validation and provenance
  hashes describe the same bytes even if the source path changes afterwards.
