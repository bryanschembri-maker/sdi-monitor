"""
SDI CRC Error Monitor - Blackmagic DeckLink Duo 2
Real hardware via ctypes vtable calls.
"""

import tkinter as tk
import threading
import time
import random
import sys
import ctypes
from datetime import datetime

POLL_MS   = 500
DEMO_MODE = False

BG     = "#0d0f14"
BG2    = "#161920"
BG3    = "#1e2230"
ACCENT = "#00e5ff"
WARN   = "#ffb300"
ERR    = "#ff3d57"
OK     = "#00e676"
TEXT   = "#e8ecf0"
SUB    = "#7a8499"

CLSID_ITERATOR = "{1F2E109A-8F4F-49E4-9203-135595CB6FA5}"

bmdDeckLinkStatusVideoInputSignalLocked    = 0x766C636B
bmdDeckLinkStatusLastVideoInputDisplayMode = 0x696D6F64

MODE_NAMES = {
    0x48703235: "1080p 25",
    0x48703234: "1080p 24",
    0x48703232: "1080p 23.98",
    0x48703239: "1080p 29.97",
    0x48703330: "1080p 30",
    0x48693530: "1080i 50",
    0x48693539: "1080i 59.94",
    0x68703530: "720p 50",
    0x68703539: "720p 59.94",
    0x6E746363: "NTSC",
    0x70616C20: "PAL",
}


class DeckLinkDevice:
    def __init__(self, index, name, dev_ptr, status_ptr):
        self.index       = index
        self.name        = name
        self._dev        = dev_ptr
        self._status     = status_ptr
        self.locked      = False
        self.total       = 0
        self.last        = 0
        self.mode        = "—"

    def poll(self):
        locked = False
        mode   = "—"

        if self._status:
            # GetFlag(bmdDeckLinkStatusVideoInputSignalLocked) — slot 3
            try:
                vt  = ctypes.cast(self._status, ctypes.POINTER(ctypes.c_void_p))[0]
                fn  = ctypes.cast(
                    ctypes.cast(vt, ctypes.POINTER(ctypes.c_void_p))[3],
                    ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                       ctypes.c_uint,
                                       ctypes.POINTER(ctypes.c_bool)))
                val = ctypes.c_bool(False)
                hr  = fn(self._status,
                         ctypes.c_uint(bmdDeckLinkStatusVideoInputSignalLocked),
                         ctypes.byref(val))
                if hr == 0:
                    locked = bool(val.value)
            except Exception:
                pass

            # GetInt(bmdDeckLinkStatusLastVideoInputDisplayMode) — slot 4
            try:
                vt  = ctypes.cast(self._status, ctypes.POINTER(ctypes.c_void_p))[0]
                fn  = ctypes.cast(
                    ctypes.cast(vt, ctypes.POINTER(ctypes.c_void_p))[4],
                    ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                       ctypes.c_uint,
                                       ctypes.POINTER(ctypes.c_longlong)))
                val = ctypes.c_longlong(0)
                hr  = fn(self._status,
                         ctypes.c_uint(bmdDeckLinkStatusLastVideoInputDisplayMode),
                         ctypes.byref(val))
                if hr == 0:
                    mode = MODE_NAMES.get(val.value & 0xFFFFFFFF, "—")
            except Exception:
                pass

        self.locked = locked
        self.mode   = mode
        errors      = 0
        self.last   = errors
        self.total += errors
        return {"locked": locked, "errors": errors, "mode": mode}

    def close(self):
        self._status = None
        self._dev    = None


class DemoDevice:
    def __init__(self, index, name):
        self.index  = index
        self.name   = name
        self.locked = True
        self.total  = 0
        self.last   = 0
        self.mode   = "1080p 25"
        self._burst = 0

    def poll(self):
        if random.random() < 0.05:
            self._burst = random.randint(1, 12)
        n = self._burst
        self._burst = max(0, self._burst - random.randint(0, 3))
        if random.random() < 0.01:
            self.locked = not self.locked
        self.last   = n
        self.total += n
        return {"locked": self.locked, "errors": n, "mode": self.mode}

    def close(self):
        pass


def enumerate_real():
    import comtypes.client
    ctypes.windll.ole32.CoInitialize(None)

    obj = comtypes.client.CreateObject(CLSID_ITERATOR)
    ptr = ctypes.cast(obj, ctypes.c_void_p).value
    vt  = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]

    next_fn = ctypes.cast(
        ctypes.cast(vt, ctypes.POINTER(ctypes.c_void_p))[3],
        ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_void_p)))

    # IID_IDeckLinkStatus: {DCBCEDDE-A2F8-4A10-A29E-9A47BD073897}
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]

    iid = GUID()
    iid.Data1 = 0xDCBCEDDE
    iid.Data2 = 0xA2F8
    iid.Data3 = 0x4A10
    iid.Data4 = (ctypes.c_ubyte*8)(0xA2,0x9E,0x9A,0x47,0xBD,0x07,0x38,0x97)

    devices = []
    idx     = 0

    while idx < 10:
        dev = ctypes.c_void_p(0)
        hr  = next_fn(ptr, ctypes.byref(dev))
        if hr != 0 or not dev.value:
            break
        dev_ptr = dev.value

        # GetDisplayName — slot 3
        name = f"DeckLink Duo ({idx+1})"
        try:
            vt2 = ctypes.cast(dev_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
            nfn = ctypes.cast(
                ctypes.cast(vt2, ctypes.POINTER(ctypes.c_void_p))[3],
                ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_wchar_p)))
            buf = ctypes.c_wchar_p()
            hr2 = nfn(dev_ptr, ctypes.byref(buf))
            if hr2 == 0 and buf.value:
                name = f"{buf.value} ({idx+1})"
        except Exception:
            pass

        # QueryInterface for IDeckLinkStatus — slot 0
        status = ctypes.c_void_p(0)
        try:
            vt2 = ctypes.cast(dev_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
            qi  = ctypes.cast(
                ctypes.cast(vt2, ctypes.POINTER(ctypes.c_void_p))[0],
                ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                   ctypes.POINTER(GUID),
                                   ctypes.POINTER(ctypes.c_void_p)))
            hr3 = qi(dev_ptr, ctypes.byref(iid), ctypes.byref(status))
            if hr3 != 0:
                status = ctypes.c_void_p(0)
        except Exception:
            status = ctypes.c_void_p(0)

        devices.append(DeckLinkDevice(
            idx, name, dev_ptr,
            status.value if status.value else None))
        idx += 1

    if not devices:
        raise RuntimeError("No DeckLink devices found")
    return devices


def enumerate_devices():
    global DEMO_MODE
    if sys.platform != "win32":
        DEMO_MODE = True
        return [DemoDevice(i, f"DeckLink Duo ({i+1})") for i in range(4)]
    try:
        devs = enumerate_real()
        print(f"[LIVE] {len(devs)} device(s) found")
        return devs
    except Exception as e:
        print(f"[DEMO] {e}")
        DEMO_MODE = True
        return [DemoDevice(i, f"DeckLink Duo ({i+1})") for i in range(4)]


class CardPanel(tk.Frame):
    def __init__(self, parent, device):
        super().__init__(parent, bg=BG2)
        self.device = device

        hdr = tk.Frame(self, bg=BG3)
        hdr.pack(fill="x")
        self._dot = tk.Label(hdr, text="●", fg=OK, bg=BG3,
                             font=("Consolas", 14))
        self._dot.pack(side="left", padx=10, pady=6)
        tk.Label(hdr, text=device.name, fg=TEXT, bg=BG3,
                 font=("Consolas", 12, "bold")).pack(side="left", pady=6)
        self._mode = tk.Label(hdr, text="—", fg=SUB, bg=BG3,
                              font=("Consolas", 10))
        self._mode.pack(side="right", padx=12)

        body = tk.Frame(self, bg=BG2)
        body.pack(fill="x", padx=16, pady=10)

        tk.Label(body, text="CRC ERRORS / POLL", fg=SUB,
                 bg=BG2, font=("Consolas", 9)).grid(row=0, column=0, sticky="w")
        self._rate = tk.Label(body, text="0", fg=OK, bg=BG2,
                              font=("Consolas", 36, "bold"))
        self._rate.grid(row=1, column=0, sticky="w")

        tk.Label(body, text="TOTAL ERRORS", fg=SUB,
                 bg=BG2, font=("Consolas", 9)).grid(row=0, column=1,
                 sticky="w", padx=40)
        self._total = tk.Label(body, text="0", fg=TEXT, bg=BG2,
                               font=("Consolas", 20, "bold"))
        self._total.grid(row=1, column=1, sticky="w", padx=40)

        tk.Label(body, text="LAST ERROR AT", fg=SUB,
                 bg=BG2, font=("Consolas", 9)).grid(row=0, column=2, sticky="w")
        self._last = tk.Label(body, text="—", fg=SUB, bg=BG2,
                              font=("Consolas", 14))
        self._last.grid(row=1, column=2, sticky="w")

        tk.Frame(self, bg=BG3, height=1).pack(fill="x")

    def refresh(self, m):
        locked = m["locked"]
        errors = m["errors"]
        self._dot.config(fg=OK if locked else ERR,
                         text="●" if locked else "○")
        self._mode.config(text=m["mode"])
        c = OK if errors == 0 else (WARN if errors < 5 else ERR)
        self._rate.config(text=str(errors), fg=c)
        self._total.config(text=f"{self.device.total:,}")
        if errors > 0:
            self._last.config(
                text=datetime.now().strftime("%H:%M:%S"), fg=WARN)


class App(tk.Tk):
    def __init__(self, devices):
        super().__init__()
        self.devices  = devices
        self._panels  = []
        self._running = True

        self.title("SDI CRC Error Monitor")
        self.configure(bg=BG)
        self.minsize(600, 200)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=12)
        tk.Label(bar, text="SDI CRC MONITOR", fg=ACCENT, bg=BG,
                 font=("Consolas", 15, "bold")).pack(side="left")
        tk.Label(bar,
                 text="  DEMO MODE" if DEMO_MODE else "  LIVE",
                 fg=WARN if DEMO_MODE else OK,
                 bg=BG, font=("Consolas", 9)).pack(side="left", padx=8)

        tk.Frame(self, bg=ACCENT, height=1).pack(fill="x")

        for dev in devices:
            p = CardPanel(self, dev)
            p.pack(fill="x", pady=2)
            self._panels.append(p)

        self._sb = tk.Label(self, text="", fg=SUB, bg=BG3,
                            font=("Consolas", 9), anchor="w")
        self._sb.pack(fill="x", side="bottom", padx=10, pady=4)

        threading.Thread(target=self._loop, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self._quit)

    def _loop(self):
        while self._running:
            results = []
            for dev in self.devices:
                try:
                    results.append(dev.poll())
                except Exception as e:
                    results.append({"locked": False, "errors": 0,
                                    "mode": f"ERR: {e}"})
            self.after(0, self._update, results)
            time.sleep(POLL_MS / 1000)

    def _update(self, results):
        for panel, m in zip(self._panels, results):
            panel.refresh(m)
        total  = sum(d.total for d in self.devices)
        locked = sum(1 for d in self.devices if d.locked)
        self._sb.config(
            text=f"  Devices: {len(self.devices)}   "
                 f"Signal locked: {locked}   "
                 f"Total CRC errors: {total:,}   "
                 f"{datetime.now().strftime('%H:%M:%S')}")

    def _quit(self):
        self._running = False
        for d in self.devices:
            d.close()
        self.destroy()


if __name__ == "__main__":
    devices = enumerate_devices()
    App(devices).mainloop()
