# Wiring

All connections match the constants at the top of `firmware/main.py`.

| ESP32-C6 SuperMini | Goes to | Notes |
|---|---|---|
| GPIO7 | WS2812B **DIN**, through ~330 Ω | `NEOPIXEL_PIN = 7` |
| 3V3 | WS2812B **VCC** | LED runs from 3.3 V (also avoids a logic-level mismatch) |
| GND | WS2812B **GND** | |
| GPIO20 | TSL2591 **SDA** | `I2C_SDA_PIN = 20` |
| GPIO19 | TSL2591 **SCL** | `I2C_SCL_PIN = 19` |
| 3V3 | TSL2591 **VIN** | |
| GND | TSL2591 **GND** | |
| — | TSL2591 INT | Not connected |

I²C runs at 400 kHz on I2C bus 0, TSL2591 address 0x29. The firmware expects a WS2812-type LED
with 3 bytes per pixel (`PIXEL_BPP = 3`); set it to 4 for an RGBW (SK6812) part.

```
 ESP32-C6 SuperMini                TSL2591
   3V3 ───────────────────────────  VIN
   GND ───────────────────────────  GND
   GPIO20 ────────────────────────  SDA
   GPIO19 ────────────────────────  SCL

 ESP32-C6 SuperMini                WS2812B (round board)
   3V3 ───────────────────────────  VCC
   GND ───────────────────────────  GND
   GPIO7 ──[ ~330 Ω ]─────────────  DIN
```

USB-C on the SuperMini provides power and the serial link to the PC.

## Wire routing in the printed parts

Each end plate has an internal channel and an outer-face groove that lead the wires down and out
of the plate bottom, through slots in the deck, and into the puck. See the wire holes in
`vs_src_plate.stl` and `vs_det_plate.stl`.

## Troubleshooting notes from the build

* A solder bridge between SDA and SCL on the TSL2591 breakout produced `ENODEV` errors. If the
  sensor is not found, check for bridges and run the `I2CSCAN` command (it should list `0x29`).
* If the LED shows the wrong colour or is stuck white, check `PIXEL_BPP` and the LED type.
