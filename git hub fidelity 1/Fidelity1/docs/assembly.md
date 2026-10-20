# Printing and assembly

## 1. Print

Printed on a Bambu H2D by the author. Print in the orientation exported in `stl/`.

| STL | Qty | Orientation | Notes |
|---|---|---|---|
| `vs_body.stl` | 1 | as exported | |
| `vs_src_plate.stl` | 1 | outer face down | |
| `vs_det_plate.stl` | 1 | outer face down | |
| `vs_ring.stl` | 1 | as exported | File contains both lens retainer rings |
| `vs_cap.stl` | 1 | skirt on the bed | |
| `vs_base_cup.stl` | 1 | as exported | |
| `vs_base_deck.stl` | 1 | as exported | |

Use a dark filament (black preferred) for the body, plates and cap: light leaking through thin
walls raises stray light. The bore, aperture and pilot sizes already include the author's
printer compensation; if parts fit differently on your printer, edit the values at the top of
`cad/vs_body.scad` and re-export:

```
openscad -D 'part="body"' -o stl/vs_body.stl cad/vs_body.scad
```

Parts: `body`, `src_plate`, `det_plate`, `ring`, `cap`, `base_cup`, `base_deck`, `assembly`
(`lid` is superseded by `cap`).

See [images/photo_parts.jpg](../images/photo_parts.jpg) for the printed parts and electronics
laid out, and [images/exploded_view.png](../images/exploded_view.png) for how they stack.

## 2. Check fit before assembling

Measure your ESP32-C6 SuperMini, the TSL2591 board and the LED board with calipers against the
dimensions in [bom.md](bom.md). The puck, detector plate and source plate are fitted to those
specific boards.

## 3. Assemble

1. **Lenses.** Seat one lens in each bore of the body so it rests on the aperture shoulder.
   Hold each with a retainer ring pushed in behind it. Orientation, per the exploded view
   ([images/exploded_view.png](../images/exploded_view.png)): on the source side the lens's **flat face
   points toward the LED**; on the detector side the **flat face points toward the detector**. The
   convex (ball) sides therefore face the cuvette.
2. **Source plate.** Place the WS2812B round board in the plate's board pocket, LED facing the
   body. Solder three wires to the board rim pads (the chamber behind the board leaves room for
   the joints) and lead them through the wire hole into the channel and out the bottom.
3. **Detector plate.** Set the TSL2591 breakout, component side toward the body, over the two
   locating pegs through its mounting holes; this puts the sensor on the optical axis. Solder
   wires to the header pads behind the board and lead them through the trench and groove to the
   bottom edge.
4. **Plates to body.** Fasten each plate with four M2 screws through its counterbored holes into
   the body's self-tap pilots.
5. **Body to deck.** Place the body in the deck's locating pocket, wires dropping through the
   deck slots, and fasten from below with two M2 screws.
6. **ESP32.** Seat the SuperMini in the puck cup (USB-C toward the flat side) on its rails, behind
   the snap hook. Make the connections in [wiring.md](wiring.md).
7. **Close the puck.** Screw the deck to the cup bosses with three M3 screws.
8. **Cap.** Drop the cuvette cap over the body top; the skirt covers the plates and the chimney
   shields the cuvette.
9. Flash the firmware and test ([operation.md](operation.md)). Run `I2CSCAN` first to confirm the
   TSL2591 at `0x29`.
