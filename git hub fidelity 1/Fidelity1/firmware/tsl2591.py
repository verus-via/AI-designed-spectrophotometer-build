"""
Minimal register-level MicroPython driver for the AMS/TAOS TSL2591
light-to-digital converter.

Only what the Fidelity1 scanning colorimeter needs: power on/off, gain and
integration-time control, and raw channel reads. We deliberately do
NOT implement the datasheet lux formula -- for this project we only
care about *relative* intensity between a blank (water) and a sample
scan taken at the same fixed gain/integration setting, so lux is
irrelevant and would just add another place for unit mistakes to
creep in.

Wiring (ESP32-C6 Supermini):
    TSL2591 VIN -> 3V3
    TSL2591 GND -> GND
    TSL2591 SDA -> GPIO20
    TSL2591 SCL -> GPIO19
"""

import time
from machine import I2C

_ADDR = 0x29
_CMD = 0xA0  # command bit (0x80) | "normal" transaction type (0x20)

# Registers
_REG_ENABLE = 0x00
_REG_CONFIG = 0x01
_REG_ID = 0x12
_REG_C0DATAL = 0x14
_REG_C1DATAL = 0x16

# ENABLE bits
_ENABLE_POWERON = 0x01
_ENABLE_AEN = 0x02

# Gain settings (CONFIG[5:4])
GAIN_LOW = 0x00   # 1x    -- bright light / direct sun
GAIN_MED = 0x10   # 25x   -- good default indoors
GAIN_HIGH = 0x20  # 428x  -- dim light
GAIN_MAX = 0x30   # 9876x -- near-dark

GAIN_NAMES = {"LOW": GAIN_LOW, "MED": GAIN_MED, "HIGH": GAIN_HIGH, "MAX": GAIN_MAX}
GAIN_LABELS = {v: k for k, v in GAIN_NAMES.items()}

# Integration time settings (CONFIG[2:0])
INTEGRATION_100MS = 0x00
INTEGRATION_200MS = 0x01
INTEGRATION_300MS = 0x02
INTEGRATION_400MS = 0x03
INTEGRATION_500MS = 0x04
INTEGRATION_600MS = 0x05

INTEGRATION_NAMES = {
    "100": INTEGRATION_100MS, "200": INTEGRATION_200MS,
    "300": INTEGRATION_300MS, "400": INTEGRATION_400MS,
    "500": INTEGRATION_500MS, "600": INTEGRATION_600MS,
}
INTEGRATION_MS = {
    INTEGRATION_100MS: 100, INTEGRATION_200MS: 200, INTEGRATION_300MS: 300,
    INTEGRATION_400MS: 400, INTEGRATION_500MS: 500, INTEGRATION_600MS: 600,
}

# Extra margin on top of one integration period before trusting the
# register. The internal cycle free-runs and is not phase-locked to our
# I2C writes, so a small slop allowance avoids reading one conversion
# too early.
_CYCLE_MARGIN_MS = 25


class TSL2591:
    def __init__(self, i2c, address=_ADDR,
                 gain=GAIN_MED, integration=INTEGRATION_100MS):
        self.i2c = i2c
        self.address = address

        chip_id = self._read_u8(_REG_ID)
        if chip_id != 0x50:
            raise RuntimeError(
                "TSL2591 not found (got ID 0x{:02X}, expected 0x50). "
                "Check wiring / I2C address.".format(chip_id))

        self.enable()
        self.set_gain_integration(gain, integration)

    # -- low-level register access ---------------------------------
    def _write_u8(self, reg, value):
        self.i2c.writeto_mem(self.address, _CMD | reg, bytes([value & 0xFF]))

    def _read_u8(self, reg):
        return self.i2c.readfrom_mem(self.address, _CMD | reg, 1)[0]

    def _read_u16(self, reg):
        data = self.i2c.readfrom_mem(self.address, _CMD | reg, 2)
        return data[0] | (data[1] << 8)

    # -- control ------------------------------------------------------
    def enable(self):
        self._write_u8(_REG_ENABLE, _ENABLE_POWERON | _ENABLE_AEN)

    def disable(self):
        self._write_u8(_REG_ENABLE, 0x00)

    def set_gain_integration(self, gain, integration):
        self.gain = gain
        self.integration = integration
        self._write_u8(_REG_CONFIG, gain | integration)

    def integration_ms(self):
        return INTEGRATION_MS[self.integration]

    def gain_label(self):
        return GAIN_LABELS[self.gain]

    def restart_integration(self):
        """Drop AEN and raise it again, which aborts the in-flight
        conversion and starts a new integration window from now."""
        self._write_u8(_REG_ENABLE, _ENABLE_POWERON)
        self._write_u8(_REG_ENABLE, _ENABLE_POWERON | _ENABLE_AEN)

    # -- readings -------------------------------------------------------
    def raw_channels(self):
        """Return (full_spectrum, infrared) raw 16-bit counts -- whatever
        is sitting in the register right now."""
        full = self._read_u16(_REG_C0DATAL)
        ir = self._read_u16(_REG_C1DATAL)
        return full, ir

    def read_fresh(self, settle_ms=20):
        """Read one value integrated ENTIRELY under the light present now.

        This matters for a stepped colour scan. The ADC free-runs, so
        immediately after changing the LED the register still holds
        charge accumulated under the previous colour; reading it would
        blend step N into step N-1. Sequence:

          1. wait settle_ms for the LED driver and die output to settle
          2. restart the integration window
          3. wait one full integration period plus margin
          4. read

        settle_ms is the LED settling allowance ONLY. It is not a
        substitute for the integration period and cannot be shortened
        to speed up a scan without corrupting the data.
        """
        time.sleep_ms(settle_ms)
        self.restart_integration()
        time.sleep_ms(self.integration_ms() + _CYCLE_MARGIN_MS)
        return self.raw_channels()

    def visible(self):
        """Approximate visible-only counts (full - IR)."""
        full, ir = self.raw_channels()
        return full - ir
