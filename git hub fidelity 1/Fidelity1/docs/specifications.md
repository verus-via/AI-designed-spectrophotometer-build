# Specifications

Values below come from `cad/vs_body.scad` (design spec VS-SPEC-001, 0.1 rev D) and the firmware /
software source. All dimensions in mm.

## Optical

| Item | Value |
|---|---|
| Source | WS2812B RGB LED on a round ~10 mm board, driven one die at a time |
| Channels | Blue 465 nm (FWHM ~25), green 525 nm (FWHM ~35), red 630 nm (FWHM ~20) |
| Relative radiant power at full drive (model) | Blue 1.00, green 0.40, red 0.49 |
| Detector | Adafruit TSL2591 (visible + IR channels; absorbance uses *visible* = full − IR) |
| Lenses | 2 × Ø5 mm plano-convex half-ball, borosilicate n ≈ 1.474, vendor focal length 5 mm |
| Lens-to-source spacing | 3.58 mm (retainer ring length) |
| Cuvette | 12.5 × 12.5 × 45 mm standard macro cuvette, 10 mm path length |
| Optical axis height | 15.0 above the body bottom, centred across the 23 mm width |
| Apertures | Ø2.5 mm either side of the cuvette well, 2.0 mm long (no print compensation) |

## Mechanical (printed parts)

| Part | File | Size (X × Y × Z) | Qty |
|---|---|---|---|
| Optical body | `vs_body.stl` | 28.5 × 23.0 × 34.0 | 1 |
| Source plate | `vs_src_plate.stl` | 34.0 × 23.0 × 6.0 | 1 |
| Detector plate | `vs_det_plate.stl` | 34.0 × 23.0 × 6.0 | 1 |
| Lens retainer ring | `vs_ring.stl` | 2 rings, Ø5.15 OD × 3.58, Ø3.5 bore | 1 file = 2 rings |
| Cuvette cap | `vs_cap.stl` | 44.2 × 26.7 × 23.0 | 1 |
| Puck base cup | `vs_base_cup.stl` | 74.6 × 76.2 × 22.4 | 1 |
| Puck deck | `vs_base_deck.stl` | 74.6 × 76.2 × 3.0 | 1 |
| Assembled reference (view only) | `vs_assembly_reference.stl` | 74.6 × 76.2 × 78.4 | — |

* Cuvette well: 13.0 × 13.0, floor 4.0 above the body bottom, starting 7.75 from the source face.
* Lens bores: Ø5.2 + 0.2 mm print compensation (5.4), 5.75 deep.
* M2 self-tap pilots Ø1.7 × 6 deep, on a 16 mm square pattern, for the end plates; 2 underside
  M2 pilots (8 deep) for the deck screws.
* Puck: Ø76.2 × 25.4 (hockey-puck size), 2.0 wall, 3.0 deck, three M3 bosses, flat on one side
  for the USB-C port. ESP32 board is held by rails, side guides and a snap hook.
* Cuvette cap: chimney bore 13.6, skirt 4.0 deep that drops over the body and end plates;
  light-blocking cap for the ~15 mm of cuvette above the body.
* All STLs were checked closed (watertight) after export.

## Electronics and firmware

| Item | Value |
|---|---|
| Controller | ESP32-C6 SuperMini, MicroPython |
| LED data | GPIO7 via ~330 Ω; LED powered from 3V3 |
| I²C | SDA GPIO20, SCL GPIO19, 400 kHz, TSL2591 at 0x29 |
| Gain | LOW 1×, MED 25×, HIGH 428×, MAX 9876× (default MED) |
| Integration | 100–600 ms (default 100 ms) |
| LED brightness | 0–255 (default 160) |
| LED settle delay | 0–5000 ms in firmware (default 20 ms; UI slider 0–200 ms) |
| Reading method | Each value is integrated entirely under the colour being measured: wait settle, restart integration, wait one integration period + 25 ms, read |
| Serial | USB CDC, 115200 baud, line commands, `END`-terminated replies |

## Software

* `spectro_server.py` (beta 2): local HTTP server on 127.0.0.1:8080 (loopback only) with a
  browser UI; needs Python 3 and `pyserial`.
* Dark / blank references stored as `reference_dark.json` / `reference_blank.json`; mismatched
  gain, integration or brightness is flagged.

## Performance seen so far

From the author's serial-dilution tests with food dyes (single build, not a validated method):

* Blue channel on red dye: R² = 0.9999. Green channel: R² = 0.9965 over the full range, 0.9987
  excluding the undiluted stock. Red channel on blue dye: R² = 0.9992.
* Points above ~1 AU deviated from linearity (stray light).

## Limits

* Three bands, not a spectrum: an analyte absorbing only between the bands reads low on all three.
* Visible light only. The TSL2591 rejects UV, and glass/polystyrene cuvettes absorb it.
* Not a validated analytical instrument; qualify it yourself before relying on results.
