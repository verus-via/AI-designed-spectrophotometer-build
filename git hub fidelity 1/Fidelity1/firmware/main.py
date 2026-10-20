"""
Fidelity1 scanning colorimeter firmware -- ESP32-C6 Supermini, MicroPython.
Software beta 2 -- three discrete channels, one per LED die.

Drives a single NeoPixel one die at a time -- blue 465 nm, green 525 nm,
red 630 nm -- reading the TSL2591 after each, and talks to a host PC over the
USB serial console using short plain-text commands.

Wiring:
    NeoPixel DIN -> GPIO7   (through ~330 ohm resistor)
    NeoPixel VCC -> 3V3       NeoPixel GND -> GND
    TSL2591 SDA  -> GPIO20    TSL2591 SCL  -> GPIO19
    TSL2591 VIN  -> 3V3       TSL2591 GND  -> GND

Commands (one per line, case-insensitive):
    PING                    -> "OK"
    STATE                   -> key=value settings lines, then "END"
    MAP                     -> color map (step,nm,r,g,b), then "END"
    SCAN                    -> sweep + read at every step, then "END"
    DARKSCAN                -> same sweep with the LED off, then "END"
    DARK                    -> LED off, single reading, then "END"
    SENSORINIT              -> re-attempt sensor bring-up, "OK" or "ERR ..."
    GAIN LOW|MED|HIGH|MAX   -> set sensor gain, "OK"
    INTEG 100..600          -> set integration time in ms, "OK"
    SETTLE <ms>             -> LED settling delay before each read, "OK"
    BRIGHT <0-255>          -> NeoPixel brightness (HSV "V"), "OK"

Note on SETTLE: this is the LED/driver settling allowance only. Every
reading additionally restarts the sensor's integration window and waits
a full integration period, so each value is integrated entirely under
the colour being measured. See TSL2591.read_fresh().
"""

import sys
import time
from machine import Pin, I2C
import neopixel
from tsl2591 import TSL2591, GAIN_NAMES, INTEGRATION_NAMES

NEOPIXEL_PIN = 7
I2C_SCL_PIN = 19
I2C_SDA_PIN = 20

# Bytes per pixel. 3 for ordinary WS2812/WS2812B (RGB). Set to 4 if the
# part is an RGBW type such as SK6812 RGBW -- those clock in 32 bits per
# pixel, and feeding them 24 leaves the chip waiting, which typically
# shows up as a pixel stuck full white regardless of what you send.
PIXEL_BPP = 3

# Three measurement channels -- one per LED die.
#
# Earlier versions swept 17 or 29 intermediate colours, but those were
# mixtures of these same three dies and carried no spectral information
# the dies do not already give. Worse, any step between two dies emits
# at BOTH die peaks and nothing in between, so its "wavelength" was a
# centroid sitting in a gap where no light exists. Driving one die at a
# time gives three honest, single-peaked measurements instead of many
# points that only look like a spectrum.
#
# peak nm, FWHM nm, relative radiant power at full drive
DIE_BLUE = (465.0, 25.0, 1.00)
DIE_GREEN = (525.0, 35.0, 0.40)
DIE_RED = (630.0, 20.0, 0.49)

# (name, nm, which channel of the RGB drive to use)
CHANNELS = [("blue", DIE_BLUE[0], "b"),
            ("green", DIE_GREEN[0], "g"),
            ("red", DIE_RED[0], "r")]

NUM_STEPS = len(CHANNELS)

DEFAULT_SETTLE_MS = 20
DEFAULT_BRIGHTNESS = 160

# Mutable runtime settings. Defined before build_color_map() because that
# function reads state["brightness"] to scale every channel.
state = {"settle_ms": DEFAULT_SETTLE_MS, "brightness": DEFAULT_BRIGHTNESS}


def build_color_map():
    """One entry per die, each driving that die alone at the current
    brightness. No mixing, so every entry is a single-peaked emission at
    a wavelength the LED genuinely produces."""
    level = state["brightness"]
    colors = []
    for step, (name, nm, chan) in enumerate(CHANNELS):
        r = level if chan == "r" else 0
        g = level if chan == "g" else 0
        b = level if chan == "b" else 0
        colors.append({"step": step, "nm": nm, "name": name,
                       "r": r, "g": g, "b": b})
    return colors


COLOR_MAP = build_color_map()

np = neopixel.NeoPixel(Pin(NEOPIXEL_PIN), 1, bpp=PIXEL_BPP)
i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=400_000)

# Come up even if the sensor is missing. A failed sensor used to raise
# here and kill the whole script, which took the I2CSCAN command down
# with it -- the one command you actually want when the sensor is not
# answering. Start regardless, and report the fault on demand.
sensor = None
sensor_error = None


def set_led(r, g, b):
    # Pass RGB in natural order. MicroPython's neopixel driver already
    # reorders to the GRB the wire protocol wants (its ORDER table is
    # (1, 0, 2, 3)), so swapping here as well would cancel out and put
    # red where green should be.
    np[0] = (r, g, b, 0)[:PIXEL_BPP]
    np.write()


def led_off():
    set_led(0, 0, 0)


def do_state():
    print("brightness={}".format(state["brightness"]))
    print("settle_ms={}".format(state["settle_ms"]))
    if sensor is not None:
        print("integration_ms={}".format(sensor.integration_ms()))
        print("gain={}".format(sensor.gain_label()))
        print("sensor=ok")
    else:
        print("integration_ms=0")
        print("gain=NONE")
        print("sensor=missing")
        print("sensor_error={}".format(sensor_error))
    print("steps={}".format(NUM_STEPS))
    print("channels={}".format(",".join("%s:%.0f" % (n, w) for n, w, _ in CHANNELS)))
    print("END")


def do_map():
    for c in COLOR_MAP:
        print("{},{:.1f},{},{},{}".format(c["step"], c["nm"], c["r"], c["g"], c["b"]))
    print("END")


def do_scan():
    if not require_sensor():
        print("END")
        return
    for c in COLOR_MAP:
        set_led(c["r"], c["g"], c["b"])
        full, ir = sensor.read_fresh(state["settle_ms"])
        visible = full - ir
        print("{},{:.1f},{},{},{},{},{},{}".format(
            c["step"], c["nm"], c["r"], c["g"], c["b"], full, ir, visible))
    led_off()
    print("END")


def do_darkscan():
    """Walk the same step sequence with the LED held off.

    A single dark reading would only capture detector offset. Sweeping
    the full sequence captures offset AND any stray light reaching the
    sensor through the housing, step by step, so it subtracts on the
    same footing as the signal it is correcting."""
    if not require_sensor():
        print("END")
        return
    led_off()
    for c in COLOR_MAP:
        full, ir = sensor.read_fresh(state["settle_ms"])
        print("{},{:.1f},{},{},{},{},{},{}".format(
            c["step"], c["nm"], 0, 0, 0, full, ir, full - ir))
    print("END")


def do_dark():
    if not require_sensor():
        print("END")
        return
    led_off()
    full, ir = sensor.read_fresh(state["settle_ms"])
    print("{},{}".format(full, ir))
    print("END")


def try_init_sensor():
    """(Re)attempt to bring up the TSL2591. Returns True on success.

    Initialisation used to happen once at import, which meant a sensor
    that was unplugged at boot stayed dead for the life of the program
    even after the wiring was fixed -- and on this board's native USB,
    opening the serial port does not reset it, so reconnecting did not
    help either. This lets the host retry without a power cycle."""
    global sensor, sensor_error
    try:
        sensor = TSL2591(i2c)
        sensor_error = None
        return True
    except Exception as exc:
        sensor = None
        sensor_error = repr(exc)
        return False


def do_i2cscan():
    try:
        found = i2c.scan()
    except Exception as exc:
        print("I2C bus error: " + repr(exc))
        print("END")
        return
    if found:
        for a in found:
            print("0x{:02X}{}".format(a, "  <- TSL2591" if a == 0x29 else ""))
    else:
        print("no devices found on the I2C bus")
        print("configured SCL=GPIO{}  SDA=GPIO{}".format(I2C_SCL_PIN, I2C_SDA_PIN))
    print("END")


def require_sensor():
    """True if the sensor is usable; otherwise explain and return False."""
    if sensor is not None:
        return True
    print("ERR sensor not available: " + (sensor_error or "not initialised"))
    return False


def handle(line):
    parts = line.strip().split()
    if not parts:
        return
    cmd = parts[0].upper()

    if cmd == "PING":
        print("OK")
    elif cmd == "I2CSCAN":
        do_i2cscan()
    elif cmd == "SENSORINIT":
        if try_init_sensor():
            print("OK")
        else:
            print("ERR " + (sensor_error or "sensor not found"))
    elif cmd == "LED" and len(parts) == 4:
        r = max(0, min(255, int(parts[1])))
        g = max(0, min(255, int(parts[2])))
        b = max(0, min(255, int(parts[3])))
        set_led(r, g, b)
        print("OK")
    elif cmd == "LEDOFF":
        led_off()
        print("OK")
    elif cmd == "STATE":
        do_state()
    elif cmd == "MAP":
        do_map()
    elif cmd == "SCAN":
        do_scan()
    elif cmd == "DARK":
        do_dark()
    elif cmd == "DARKSCAN":
        do_darkscan()
    elif cmd == "GAIN" and len(parts) == 2 and parts[1].upper() in GAIN_NAMES:
        if not require_sensor():
            return
        sensor.set_gain_integration(GAIN_NAMES[parts[1].upper()], sensor.integration)
        print("OK")
    elif cmd == "INTEG" and len(parts) == 2 and parts[1] in INTEGRATION_NAMES:
        if not require_sensor():
            return
        sensor.set_gain_integration(sensor.gain, INTEGRATION_NAMES[parts[1]])
        print("OK")
    elif cmd == "SETTLE" and len(parts) == 2:
        state["settle_ms"] = max(0, min(5000, int(parts[1])))
        print("OK")
    elif cmd == "BRIGHT" and len(parts) == 2:
        state["brightness"] = max(0, min(255, int(parts[1])))
        global COLOR_MAP
        COLOR_MAP = build_color_map()
        print("OK")
    else:
        print("ERR unknown command: " + line)


def main():
    led_off()
    try_init_sensor()
    if sensor is None:
        print("WARN sensor not found: " + (sensor_error or "?"))
        print("WARN LED and I2CSCAN still work; scanning is disabled")
    print("READY")
    while True:
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            led_off()
            return
        if line:
            handle(line)


main()
