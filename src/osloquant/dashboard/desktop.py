"""The decision dashboard as an app on the PC (DECISIONS D45).

`oq app --install` puts a shortcut named "Oslo Børs-dashbord" on the desktop and in the Start menu. The shortcut runs
this module with the virtual environment's ``pythonw.exe`` (no console window): if nothing answers on the dashboard's
port it starts ``oq dashboard --no-browser`` in the background (no window; output to ``~/osloquant-home/app/
dashboard.log``), waits until ``/ping`` answers, and opens the dashboard in an app window – Edge or Chrome with
``--app=``, so it has its own window, taskbar entry and icon and no address bar. When the dashboard is already
running (the evening task, a terminal, Claude's preview) it is reused, never started twice. Closing the window leaves
the server running, as a terminal-started dashboard does; it stops with the PC or the process.

The icon is drawn here (a teal square with three rising bars) and written as PNG and ICO without an image library;
the dashboard serves it as its favicon so the app window carries it too. Nothing here reads or writes the research
book; the only files written are the icon, the log and the two shortcuts.
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

PORT = 8060
APP_NAME = "Oslo Børs-dashbord"
APP_DIR = "app"
WAIT_SECONDS = 120
BG = (11, 92, 92)            # the nav bar's --accent-dark
FG = (255, 255, 255)
ICO_SIZES = (16, 24, 32, 48, 64, 256)
BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


# ------------------------------------------------------------------------------------------------ the icon
def icon_rgba(n: int) -> bytes:
    """n x n RGBA pixels: a rounded teal square with three white bars rising left to right."""
    r = n * 0.2
    bars = [(0.20, 0.50), (0.42, 0.34), (0.64, 0.18)]          # (left edge, top) as shares of n; bottoms at 0.80
    w = 0.16
    out = bytearray()
    for y in range(n):
        for x in range(n):
            cx, cy = x + 0.5, y + 0.5
            dx = max(r - cx, 0, cx - (n - r))
            dy = max(r - cy, 0, cy - (n - r))
            if dx * dx + dy * dy > r * r:
                out += b"\x00\x00\x00\x00"
                continue
            bar = any(left * n <= cx < (left + w) * n and top * n <= cy < 0.80 * n for left, top in bars)
            out += bytes((*(FG if bar else BG), 255))
    return bytes(out)


def png(n: int) -> bytes:
    raw = icon_rgba(n)
    rows = b"".join(b"\x00" + raw[y * n * 4:(y + 1) * n * 4] for y in range(n))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def ico(sizes: tuple[int, ...] = ICO_SIZES) -> bytes:
    """An ICO file with one PNG image per size (Windows reads PNG entries since Vista)."""
    images = [png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(sizes, images, strict=True):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return head + entries + b"".join(images)


# ------------------------------------------------------------------------------------------------ server and window
def app_dir() -> Path:
    from osloquant import judgements as jg

    d = jg.home() / APP_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def url(port: int = PORT, path: str = "/") -> str:
    return f"http://127.0.0.1:{port}{path}"


def is_up(port: int = PORT, timeout: float = 1.0) -> bool:
    """True when a dashboard answers on the port: /ping says ok, or – a dashboard started before /ping existed – the
    server answers /ping with an HTTP error, so something is listening and a second server would only fail to bind."""
    import urllib.error

    try:
        with urllib.request.urlopen(url(port, "/ping"), timeout=timeout) as r:
            return r.status == 200 and r.read(16) == b"ok"
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001 – no answer at all means not up
        return False


def find_browser(paths: tuple[str, ...] = BROWSERS) -> str | None:
    return next((p for p in paths if Path(p).exists()), None)


def start_server(port: int = PORT, popen=subprocess.Popen):
    """``oq dashboard --no-browser`` in the background with no window, output appended to the app log."""
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe" and py.with_name("python.exe").exists():
        py = py.with_name("python.exe")                       # the server writes to its log, not to a missing console
    log = (app_dir() / "dashboard.log").open("a", encoding="utf-8")
    log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting the dashboard on port {port}\n")
    log.flush()
    flags = (CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    return popen([str(py), "-c", "from osloquant.cli import app; app()", "dashboard", "--no-browser", "--port", str(port)],
                 stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags,
                 env={**os.environ, "PYTHONIOENCODING": "utf-8"}, close_fds=True)


def wait_up(port: int = PORT, seconds: float = WAIT_SECONDS, proc=None, sleep=time.sleep) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if is_up(port):
            return True
        if proc is not None and proc.poll() is not None:     # the server died: no point waiting
            return False
        sleep(0.5)
    return False


def open_window(port: int = PORT, browser: str | None = None, popen=subprocess.Popen) -> str:
    """The dashboard in an app window (Edge or Chrome ``--app``); the default browser if neither is installed."""
    browser = browser or find_browser()
    if browser:
        popen([browser, f"--app={url(port)}", "--window-size=1440,960"], close_fds=True)
        return browser
    import webbrowser

    webbrowser.open(url(port))
    return "default browser"


def message(text: str) -> None:
    if os.name == "nt" and Path(sys.executable).name.lower() == "pythonw.exe":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
    else:
        print(text, file=sys.stderr)


def main(port: int = PORT, browser: str | None = None) -> int:
    """What the shortcut runs: reuse or start the dashboard, then open the app window."""
    if not is_up(port):
        proc = start_server(port)
        if not wait_up(port, proc=proc):
            message(f"Dashbordet startet ikke på port {port} innen {WAIT_SECONDS} sekunder. Se loggen: {app_dir() / 'dashboard.log'}")
            return 1
    open_window(port, browser)
    return 0


# ------------------------------------------------------------------------------------------------ the shortcuts
def install(port: int = PORT, folders: tuple[str, ...] = ("Desktop", "Programs"), run=subprocess.run) -> list[str]:
    """Write the icon and create one shortcut per folder (Windows special folders: the desktop and the Start menu's
    programs). Returns the shortcut paths PowerShell reports."""
    if os.name != "nt":
        raise RuntimeError("the shortcuts are for Windows; elsewhere run `oq app` from a terminal")
    icon = app_dir() / "dashboard.ico"
    icon.write_bytes(ico())
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        raise RuntimeError(f"no pythonw.exe beside {sys.executable}")
    args = "-m osloquant.dashboard.desktop" + ("" if port == PORT else f" --port {port}")
    lines = ["[Console]::OutputEncoding = [Text.Encoding]::UTF8", "$s = New-Object -ComObject WScript.Shell"]
    for f in folders:
        lines += [f"$p = Join-Path ([Environment]::GetFolderPath('{f}')) '{APP_NAME}.lnk'",
                  "$l = $s.CreateShortcut($p)", f"$l.TargetPath = '{pyw}'", f"$l.Arguments = '{args}'",
                  f"$l.WorkingDirectory = '{app_dir()}'", f"$l.IconLocation = '{icon},0'",
                  "$l.Description = 'Oslo Børs decision dashboard (oslo-quant)'", "$l.Save()", "Write-Output $p"]
    res = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "; ".join(lines)], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "PowerShell could not create the shortcuts")
    return [x.strip() for x in res.stdout.splitlines() if x.strip()]


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    sys.exit(main(port))
