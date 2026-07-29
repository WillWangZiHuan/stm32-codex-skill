# Community board package

## Board

- Board ID:
- Vendor and model:
- Hardware revision:
- MCU:
- Official manual URL:
- Result level: profile / configuration / compile / hardware

## Contribution

- [ ] I added one package under `stm32-cubemx-build/boards/<board-id>/`.
- [ ] The package contains `manifest.json` and `board-profile.json`.
- [ ] The manifest ID matches the package directory.
- [ ] The official manual uses HTTPS and its SHA-256 matches the profile.
- [ ] MCU, clock, pin, connector, electrical, and conflict facts have page
      citations and concise text anchors.
- [ ] I did not commit a vendor PDF or extracted full-text manual index unless
      its license explicitly permits redistribution.
- [ ] Every optional example uses the package MCU.
- [ ] The declared result level matches the evidence attached to this pull
      request.

## Validation

```bash
python -m unittest discover -s tests -v
python stm32-cubemx-build/scripts/validate_packs.py
python stm32-cubemx-build/scripts/validate_boards.py
```

Describe the generated configuration, compilation artifacts, or hardware
observations that establish the selected result level:
