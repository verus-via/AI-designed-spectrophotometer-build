# Operation

## Firmware

1. Flash MicroPython onto the ESP32-C6 SuperMini.
2. Copy `firmware/main.py` and `firmware/tsl2591.py` to the board's root (e.g. with Thonny).
3. Reset. The board prints `READY` and then waits for commands on the USB serial port.

Close Thonny or any serial monitor before starting the PC software; only one program can hold the port.

## PC software

Requires Python 3 on the PC. `Fidelity1.bat` finds Python, installs `pyserial` if missing and
starts the server; the UI opens at <http://localhost:8080>. Alternatively:

```
pip install pyserial
python software/spectro_server.py            # --port 9000, --no-browser available
```

Do not open `index.html` directly from disk; it needs the server.

## Measuring

1. Choose the serial port and **Connect**.
2. **Dark scan** — LED off, cap on. Captures detector offset and stray light.
3. **Blank scan** — cuvette filled with solvent only.
4. Enter an optional note and **Scan sample**.

Absorbance per channel: `A = -log10((sample_vis - dark_vis) / (blank_vis - dark_vis))`.
Dark and blank references are stored and are only valid at the brightness, integration time and
gain they were taken at; the UI marks them "settings changed" if you alter those.
Flags: "blank not above dark", "sample at or below dark", "sample brighter than blank".

Scans are saved as `dark_*.txt`, `blank_*.txt` and `sample_*.txt` next to `spectro_server.py`.

## Serial commands (for scripting)

One command per line, case-insensitive: `PING`, `STATE`, `MAP`, `SCAN`, `DARKSCAN`, `DARK`,
`SENSORINIT`, `I2CSCAN`, `LED r g b`, `LEDOFF`, `GAIN LOW|MED|HIGH|MAX`, `INTEG 100..600`,
`SETTLE <ms>`, `BRIGHT <0-255>`. Data lines are
`step,nm,r,g,b,full,ir,visible`, terminated by `END`.
