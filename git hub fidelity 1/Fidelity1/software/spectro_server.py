"""
Fidelity1 scanning colorimeter -- local control server.  Software beta 1.

Serves the browser UI and does the serial work on its behalf, because a
page cannot write files to its own directory. Dark, blank and sample
scans are written next to this script, named by date and time.

Usage:
    pip install pyserial
    python spectro_server.py                 # opens the browser itself
    python spectro_server.py --port 9000     # different HTTP port
    python spectro_server.py --no-browser    # stay put

Nothing is exposed beyond the loopback interface.

Version history:
    final test  -- single SCAN, raw intensity only
    beta 1      -- dark / blank / sample workflow, stored references,
                   absorbance on screen, per-step wavelength estimate
    beta 1a     -- uniform 10 nm wavelength steps (465-625) replacing the
                   uneven, non-monotonic hue sweep
    beta 2      -- three discrete channels (465 / 525 / 630) instead of a
                   sweep; intermediate steps were die mixtures carrying no
                   information the dies themselves did not already give
"""

import argparse
import datetime as dt
import json
import math
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    raise SystemExit(
        "pyserial is not installed.\n"
        "Run:  python -m pip install pyserial\n"
        "(the package is 'pyserial' but imports as 'serial')")

VERSION = "beta 2"
HERE = Path(__file__).resolve().parent
BAUD = 115200

GAINS = ["LOW", "MED", "HIGH", "MAX"]
INTEGRATIONS = ["100", "200", "300", "400", "500", "600"]

DARK_FILE = HERE / "reference_dark.json"
BLANK_FILE = HERE / "reference_blank.json"

# Settings that must match between a reference and the sample it is used
# with. Comparing intensities taken at different gain or integration is
# meaningless, so this is checked rather than trusted.
CRITICAL = ("brightness", "integration_ms", "gain")


# ----------------------------------------------------------------------
# Per-step wavelength estimate
# ----------------------------------------------------------------------
# The NeoPixel has three fixed dies. Any step is a weighted sum of them,
# so the "wavelength" of a step is the intensity-weighted centroid of
# that sum -- NOT a physical emission line. For steps that drive two dies
# at once the spectrum is genuinely bimodal and the centroid falls in a
# gap where the LED emits almost nothing. Those steps are flagged, and
# the flag matters more than the number.

_DIES = [(465.0, 25.0, 1.00),   # blue  peak nm, FWHM nm, relative radiant power
         (525.0, 35.0, 0.40),   # green
         (630.0, 20.0, 0.49)]   # red
_LAM = [400.0 + i for i in range(321)]


def _gauss(centre, fwhm, x):
    return math.exp(-(x - centre) ** 2 / (2 * (fwhm / 2.355) ** 2))


def estimate_wavelength(r, g, b):
    """Return (centroid_nm, bimodal) for one RGB drive setting."""
    drives = (b / 255.0, g / 255.0, r / 255.0)   # order matches _DIES
    spec = []
    for x in _LAM:
        s = 0.0
        for (centre, fwhm, power), drive in zip(_DIES, drives):
            if drive:
                s += power * drive * _gauss(centre, fwhm, x)
        spec.append(s)

    total = sum(spec)
    if total <= 0:
        return None, False
    centroid = sum(x * s for x, s in zip(_LAM, spec)) / total

    peak = max(spec)
    norm = [s / peak for s in spec]
    modes = sum(1 for i in range(1, len(norm) - 1)
                if norm[i] > norm[i - 1] and norm[i] >= norm[i + 1] and norm[i] > 0.2)
    return centroid, modes > 1


CHANNEL_NAMES = {465.0: "blue", 525.0: "green", 630.0: "red"}


def annotate(rows):
    """Cross-check the achieved emission centroid against the wavelength
    the firmware reported. Driving one die alone should put the centroid
    exactly on that die's peak; anything else means the two die models
    have drifted apart, which is worth seeing rather than assuming."""
    for r in rows:
        nm, bimodal = estimate_wavelength(r["r"], r["g"], r["b"])
        r["est_nm"] = round(nm, 1) if nm else None
        r["bimodal"] = bimodal
        r["name"] = CHANNEL_NAMES.get(r.get("nm"), "")
        if r.get("nm") is not None and nm:
            r["nm_error"] = round(nm - r["nm"], 2)
        else:
            r["nm_error"] = None
    return rows


# ----------------------------------------------------------------------
# Instrument
# ----------------------------------------------------------------------
class Colorimeter:
    """Owns the serial port. One command in flight at a time."""

    def __init__(self):
        self.ser = None
        self.port = None
        self.boot_log = []
        self.sensor_ok = True
        self.sensor_error = None
        self.lock = threading.Lock()
        self.settings = {"brightness": 160, "settle_ms": 20,
                         "integration_ms": 100, "gain": "MED", "steps": 29}

    # -- connection -------------------------------------------------
    @staticmethod
    def _drain(ser, seconds):
        out, deadline = [], time.time() + seconds
        old = ser.timeout
        ser.timeout = 0.2
        try:
            while time.time() < deadline:
                raw = ser.readline()
                if not raw:
                    continue
                text = raw.decode(errors="replace").rstrip()
                if text:
                    out.append(text)
        finally:
            ser.timeout = old
        return out

    def connect(self, port):
        self.disconnect()
        ser = serial.Serial(port, BAUD, timeout=8)
        time.sleep(2.0)
        boot = self._drain(ser, 2.0)      # keep the boot chatter, it explains failures
        self.boot_log = boot
        self.ser = ser
        self.port = port
        try:
            self._command("PING", expect_end=False)
            self.refresh_state()
            if not self.sensor_ok:
                # The board may have started before the sensor was wired,
                # and opening this port does not reset it. Retry first.
                try:
                    self._command("SENSORINIT", expect_end=False)
                except Exception:
                    pass
                self.refresh_state()
        except Exception:
            diag = self._diagnose(boot)
            self.disconnect()
            raise RuntimeError(diag)

    def _repl_eval(self, expr, wait=1.2):
        """Drop to the REPL and evaluate one expression. Only called once
        the command protocol has already failed."""
        try:
            self.ser.write(b"\x03")          # break whatever is running
            self.ser.flush()
            time.sleep(0.4)
            self._drain(self.ser, 0.5)       # discard banner / prompt
            self.ser.write((expr + "\r\n").encode())
            self.ser.flush()
            time.sleep(0.3)
            return self._drain(self.ser, wait)
        except Exception:
            return []

    def _diagnose(self, boot):
        """Work out why the board is silent and say so in plain terms."""
        text = "\n".join(boot)

        if "Traceback" in text or "Error" in text:
            return ("The firmware crashed on startup. The board reported:\n\n"
                    + text.strip()
                    + "\n\nIf this mentions TSL2591, the sensor is not answering "
                      "on I2C -- check SDA on GPIO20, SCL on GPIO19, 3V3 and GND.")

        # Ask the device what is actually in its root directory. Note that
        # breaking in also stops main.py if it WAS running, so a REPL
        # prompt on its own proves nothing -- hence the direct listing.
        listing = self._repl_eval("import os;print(os.listdir())")
        files = None
        for line in listing:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                files = [f.strip().strip("'\"") for f in line[1:-1].split(",") if f.strip()]
                break

        if files is not None:
            have_main = "main.py" in files
            have_drv = "tsl2591.py" in files
            shown = ", ".join(files) if files else "(empty)"
            if not have_main or not have_drv:
                missing = [n for n, ok in (("main.py", have_main),
                                           ("tsl2591.py", have_drv)) if not ok]
                return ("Device root contains: " + shown
                        + "\n\nMissing: " + ", ".join(missing)
                        + "\nCopy the missing file(s) to the device root and reset it.")

            reboot = self._repl_eval("import machine;machine.soft_reset()", wait=3.0)
            rtext = "\n".join(reboot)
            if "Traceback" in rtext or "Error" in rtext:
                return ("Both files are on the device, but main.py fails when it "
                        "runs. The board reported:\n\n" + rtext.strip())
            if "READY" in rtext:
                return ("main.py is present and starts correctly (it printed READY "
                        "on restart), but it did not answer PING in time. Try "
                        "connecting again. If it keeps failing, close Thonny or any "
                        "serial monitor competing for the port.")
            return ("Both files are on the device (" + shown + ") but main.py is "
                    "not responding. Restart output was:\n\n"
                    + (rtext.strip() or "(nothing)"))

        if boot:
            return ("The board said:\n\n" + text.strip()
                    + "\n\n...but did not answer PING.")

        return ("No response at all from " + str(self.port) + ". Check that this is "
                "the right COM port, that MicroPython is flashed, and that nothing "
                "else (Thonny, a serial monitor) is holding the port open.")

    def disconnect(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.port = None

    @property
    def connected(self):
        return self.ser is not None and self.ser.is_open

    # -- protocol ---------------------------------------------------
    def _command(self, cmd, expect_end=True, line_cb=None):
        if not self.connected:
            raise RuntimeError("not connected")
        self.ser.reset_input_buffer()
        self.ser.write((cmd.strip() + "\n").encode())
        self.ser.flush()
        lines = []
        while True:
            raw = self.ser.readline().decode(errors="replace").strip()
            if raw == "":
                raise RuntimeError("timed out waiting for the device")
            if raw.startswith("ERR"):
                raise RuntimeError(raw)
            if not expect_end:
                return [raw]
            if raw == "END":
                return lines
            lines.append(raw)
            if line_cb:
                line_cb(raw)

    def command(self, cmd, expect_end=True, line_cb=None):
        with self.lock:
            return self._command(cmd, expect_end, line_cb)

    def refresh_state(self):
        lines = self._command("STATE")
        self.sensor_ok = True
        self.sensor_error = None
        for line in lines:
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k in ("brightness", "settle_ms", "integration_ms", "steps"):
                self.settings[k] = int(v)
            elif k == "channels":
                self.settings["channels"] = v
            elif k == "gain":
                self.settings[k] = v
            elif k == "sensor":
                self.sensor_ok = (v == "ok")
            elif k == "sensor_error":
                self.sensor_error = v
        return self.settings

    def apply_settings(self, brightness=None, integration_ms=None,
                       gain=None, settle_ms=None):
        with self.lock:
            if brightness is not None:
                self._command("BRIGHT %d" % int(brightness), expect_end=False)
            if integration_ms is not None:
                self._command("INTEG %s" % str(int(integration_ms)), expect_end=False)
            if gain is not None:
                self._command("GAIN %s" % gain.upper(), expect_end=False)
            if settle_ms is not None:
                self._command("SETTLE %d" % int(settle_ms), expect_end=False)
            return self.refresh_state()

    # -- scanning ---------------------------------------------------
    def scan(self, progress_cb=None):
        rows = []

        def on_line(raw):
            parts = raw.split(",")
            if len(parts) != 8:
                return
            rows.append({"step": int(parts[0]), "nm": float(parts[1]),
                         "r": int(parts[2]), "g": int(parts[3]), "b": int(parts[4]),
                         "full": int(parts[5]), "ir": int(parts[6]),
                         "visible": int(parts[7])})
            if progress_cb:
                progress_cb(len(rows))

        with self.lock:
            per_step = (self.settings["settle_ms"]
                        + self.settings["integration_ms"] + 200) / 1000.0
            old = self.ser.timeout
            self.ser.timeout = max(8.0, per_step * 3)
            try:
                self._command("SCAN", line_cb=on_line)
            finally:
                self.ser.timeout = old
        return annotate(rows)

    def scan_dark(self, progress_cb=None):
        """A dark scan is the ordinary sweep with the LED held off, so it
        captures detector offset AND any stray light reaching the sensor
        through the housing -- both of which must come out of the signal."""
        self.command("LEDOFF", expect_end=False)
        rows = []

        def on_line(raw):
            parts = raw.split(",")
            if len(parts) != 8:
                return
            rows.append({"step": int(parts[0]), "nm": float(parts[1]),
                         "r": int(parts[2]), "g": int(parts[3]), "b": int(parts[4]),
                         "full": int(parts[5]), "ir": int(parts[6]),
                         "visible": int(parts[7])})
            if progress_cb:
                progress_cb(len(rows))

        with self.lock:
            per_step = (self.settings["settle_ms"]
                        + self.settings["integration_ms"] + 200) / 1000.0
            old = self.ser.timeout
            self.ser.timeout = max(8.0, per_step * 3)
            try:
                self._command("DARKSCAN", line_cb=on_line)
            finally:
                self.ser.timeout = old
        return annotate(rows)


DEV = Colorimeter()


# ----------------------------------------------------------------------
# Stored references
# ----------------------------------------------------------------------
def save_reference(kind, rows, settings):
    path = DARK_FILE if kind == "dark" else BLANK_FILE
    payload = {"kind": kind,
               "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
               "settings": dict(settings), "rows": rows}
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def load_reference(kind):
    path = DARK_FILE if kind == "dark" else BLANK_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def settings_match(ref, settings):
    """References are only valid at the gain, integration and brightness
    they were taken at. Mismatched ones are not silently used."""
    if not ref:
        return False
    rs = ref.get("settings", {})
    return all(rs.get(k) == settings.get(k) for k in CRITICAL)


def reference_summary(settings):
    out = {}
    for kind in ("dark", "blank"):
        ref = load_reference(kind)
        out[kind] = None if not ref else {
            "timestamp": ref["timestamp"],
            "settings": ref["settings"],
            "matches": settings_match(ref, settings),
            "steps": len(ref["rows"]),
        }
    return out


# ----------------------------------------------------------------------
# Absorbance
# ----------------------------------------------------------------------
def compute_absorbance(sample_rows, dark, blank, channel="visible"):
    """A = -log10((sample - dark) / (blank - dark)) per step.

    Returns rows carrying the raw components alongside the result, so the
    saved file records everything the number was derived from rather than
    just the conclusion."""
    d = {r["step"]: r for r in dark["rows"]}
    b = {r["step"]: r for r in blank["rows"]}
    out = []
    for s in sample_rows:
        i = s["step"]
        dk = d.get(i)
        bk = b.get(i)
        row = dict(s)
        row["dark_visible"] = dk[channel] if dk else None
        row["blank_visible"] = bk[channel] if bk else None
        row["absorbance"] = None
        row["flag"] = ""
        if dk is None or bk is None:
            row["flag"] = "no reference for this step"
            out.append(row)
            continue

        i0 = bk[channel] - dk[channel]
        it = s[channel] - dk[channel]
        if i0 <= 0:
            row["flag"] = "blank not above dark"
        elif it <= 0:
            row["flag"] = "sample at or below dark"
        else:
            row["absorbance"] = round(-math.log10(it / i0), 4)
            if it / i0 > 1.02:
                row["flag"] = "sample brighter than blank"
        out.append(row)
    return out


# ----------------------------------------------------------------------
# File output
# ----------------------------------------------------------------------
def _header(f, name, kind, settings, note):
    f.write("# VerusVia Fidelity1 scanning colorimeter\n")
    f.write("# software\t\t%s\n" % VERSION)
    f.write("# scan type\t\t%s\n" % kind)
    f.write("# file\t\t\t%s\n" % name)
    f.write("# timestamp\t\t%s\n" % dt.datetime.now().isoformat(timespec="seconds"))
    if note:
        f.write("# note\t\t\t%s\n" % note.replace("\n", " ").strip())
    f.write("# brightness\t\t%d\n" % settings["brightness"])
    f.write("# integration_ms\t%d\n" % settings["integration_ms"])
    f.write("# gain\t\t\t%s\n" % settings["gain"])
    f.write("# settle_ms\t\t%d\n" % settings["settle_ms"])


def write_reference_file(kind, rows, settings, note):
    now = dt.datetime.now()
    name = "%s_%s.txt" % (kind, now.strftime("%Y%m%d_%H%M%S"))
    with (HERE / name).open("w", encoding="utf-8") as f:
        _header(f, name, kind, settings, note)
        f.write("# steps\t\t\t%d\n" % len(rows))
        f.write("#\n# Raw TSL2591 counts. Stored as the current %s reference.\n#\n" % kind)
        f.write("step\tchannel\tnm\tr\tg\tb\tfull\tir\tvisible\n")
        for r in rows:
            f.write("%d\t%s\t%.0f\t%d\t%d\t%d\t%d\t%d\t%d\n" % (
                r["step"], r["name"], r["nm"],
                r["r"], r["g"], r["b"], r["full"], r["ir"], r["visible"]))
    return name


def write_sample_file(rows, settings, note, dark, blank):
    now = dt.datetime.now()
    name = "sample_%s.txt" % now.strftime("%Y%m%d_%H%M%S")
    with (HERE / name).open("w", encoding="utf-8") as f:
        _header(f, name, "sample", settings, note)
        f.write("# steps\t\t\t%d\n" % len(rows))
        f.write("#\n")
        f.write("# dark reference\t%s  (gain %s, %d ms, brightness %d)\n" % (
            dark["timestamp"], dark["settings"]["gain"],
            dark["settings"]["integration_ms"], dark["settings"]["brightness"]))
        f.write("# blank reference\t%s  (gain %s, %d ms, brightness %d)\n" % (
            blank["timestamp"], blank["settings"]["gain"],
            blank["settings"]["integration_ms"], blank["settings"]["brightness"]))
        f.write("#\n")
        f.write("# A = -log10((sample_visible - dark_visible) / (blank_visible - dark_visible))\n")
        f.write("#\n")
        f.write("# Each channel drives ONE LED die alone, so its emission is single-peaked\n")
        f.write("# at the stated wavelength with roughly 20-35 nm FWHM. These are three\n")
        f.write("# discrete measurements, not a spectrum -- nothing is measured between\n")
        f.write("# them, and a compound absorbing only between two dies will read low.\n")
        f.write("#\n")
        f.write("step\tchannel\tnm\tr\tg\tb\t"
                "dark_vis\tblank_vis\tsample_full\tsample_ir\tsample_vis\tabsorbance\tflag\n")
        for r in rows:
            f.write("%d\t%s\t%.0f\t%d\t%d\t%d\t%s\t%s\t%d\t%d\t%d\t%s\t%s\n" % (
                r["step"], r["name"], r["nm"],
                r["r"], r["g"], r["b"],
                r["dark_visible"], r["blank_visible"],
                r["full"], r["ir"], r["visible"],
                "" if r["absorbance"] is None else "%.4f" % r["absorbance"],
                r["flag"]))
    return name


# ----------------------------------------------------------------------
# Scan job
# ----------------------------------------------------------------------
SCAN = {"running": False, "kind": None, "step": 0, "total": 0,
        "rows": [], "filename": None, "error": None, "warning": None}
SCAN_LOCK = threading.Lock()


def run_scan(kind, note):
    try:
        total = DEV.settings.get("steps", 29)
        with SCAN_LOCK:
            SCAN.update(running=True, kind=kind, step=0, total=total,
                        rows=[], filename=None, error=None, warning=None)

        def progress(n):
            with SCAN_LOCK:
                SCAN["step"] = n

        settings = dict(DEV.settings)

        if kind == "dark":
            rows = DEV.scan_dark(progress_cb=progress)
            save_reference("dark", rows, settings)
            name = write_reference_file("dark", rows, settings, note)
            result = rows
        elif kind == "blank":
            rows = DEV.scan(progress_cb=progress)
            save_reference("blank", rows, settings)
            name = write_reference_file("blank", rows, settings, note)
            result = rows
        else:
            dark = load_reference("dark")
            blank = load_reference("blank")
            if not dark or not blank:
                raise RuntimeError("take a dark scan and a blank scan first")
            warn = []
            if not settings_match(dark, settings):
                warn.append("dark reference was taken at different settings")
            if not settings_match(blank, settings):
                warn.append("blank reference was taken at different settings")
            rows = DEV.scan(progress_cb=progress)
            result = compute_absorbance(rows, dark, blank)
            name = write_sample_file(result, settings, note, dark, blank)
            if warn:
                with SCAN_LOCK:
                    SCAN["warning"] = "; ".join(warn)

        with SCAN_LOCK:
            SCAN.update(running=False, rows=result, filename=name,
                        step=len(rows), total=len(rows) or total)
    except Exception as exc:
        with SCAN_LOCK:
            SCAN.update(running=False, error=str(exc))


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        # The UI changes far more often than a browser expects a static
        # page to, and a stale cached copy looks exactly like a failed
        # update. Never let it cache.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode() or "{}") if n else {}

    def _state(self):
        return {"version": VERSION,
                "connected": DEV.connected,
                "port": DEV.port,
                "settings": DEV.settings,
                "sensor_ok": DEV.sensor_ok,
                "sensor_error": DEV.sensor_error,
                "gains": GAINS,
                "integrations": INTEGRATIONS,
                "references": reference_summary(DEV.settings),
                "directory": str(HERE)}

    def do_GET(self):
        if self.path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if self.path == "/api/state":
            return self._json(self._state())
        if self.path == "/api/ports":
            return self._json({"ports": [{"device": p.device, "description": p.description}
                                         for p in list_ports.comports()]})
        if self.path == "/api/scan/progress":
            with SCAN_LOCK:
                return self._json({"running": SCAN["running"], "kind": SCAN["kind"],
                                   "step": SCAN["step"], "total": SCAN["total"],
                                   "rows": SCAN["rows"], "filename": SCAN["filename"],
                                   "error": SCAN["error"], "warning": SCAN["warning"],
                                   "references": reference_summary(DEV.settings)})
        if self.path == "/api/scans":
            files = sorted((p.name for p in HERE.glob("*_2*.txt")), reverse=True)
            return self._json({"scans": files[:60]})
        return super().do_GET()

    def do_POST(self):
        try:
            if self.path == "/api/connect":
                DEV.connect(self._read_json()["port"])
                return self._json(self._state())
            if self.path == "/api/disconnect":
                DEV.disconnect()
                return self._json(self._state())
            if self.path == "/api/settings":
                b = self._read_json()
                DEV.apply_settings(brightness=b.get("brightness"),
                                   integration_ms=b.get("integration_ms"),
                                   gain=b.get("gain"), settle_ms=b.get("settle_ms"))
                return self._json(self._state())
            if self.path == "/api/scan":
                b = self._read_json()
                kind = (b.get("kind") or "sample").lower()
                if kind not in ("dark", "blank", "sample"):
                    return self._json({"error": "unknown scan kind"}, 400)
                with SCAN_LOCK:
                    if SCAN["running"]:
                        return self._json({"error": "a scan is already running"}, 409)
                if not DEV.connected:
                    return self._json({"error": "not connected"}, 400)
                if not DEV.sensor_ok:
                    return self._json({"error": "sensor not responding"}, 400)
                note = (b.get("note") or "").strip()
                threading.Thread(target=run_scan, args=(kind, note), daemon=True).start()
                return self._json({"started": True, "kind": kind})
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as exc:
            return self._json({"error": str(exc)}, 500)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8080, help="HTTP port")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open a browser window")
    args = ap.parse_args()

    if not (HERE / "index.html").exists():
        print("WARNING: index.html is not next to this script; the UI will 404.")

    url = "http://localhost:%d" % args.port
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        raise SystemExit("Could not start on port %d: %s\n"
                         "Another copy may already be running -- try --port 8081."
                         % (args.port, exc))

    print("=" * 56)
    print(" Fidelity1 scanning colorimeter -- software %s" % VERSION)
    print("=" * 56)
    print(" UI            %s" % url)
    print(" Scans saved   %s" % HERE)
    print(" Stop          Ctrl-C, or just close this window")
    print("=" * 56)

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        DEV.disconnect()
        srv.server_close()


if __name__ == "__main__":
    main()
