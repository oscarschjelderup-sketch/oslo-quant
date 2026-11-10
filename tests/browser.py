"""A headless Chromium driven over the DevTools protocol, for the tests that need a real browser.

It covers the price chart's state, the hover box, console errors and the visual baselines. On Windows the browser is
Edge; on the CI runner it is google-chrome or chromium. Tests that need a browser skip when none is installed or the
``websockets`` package is missing.

Visual baselines are small grids rather than images: a screenshot is decoded and averaged by the browser itself into
cells of a few pixels. ``compare_grid`` checks such a grid against ``tests/visual/<platform>/<name>.json``.
- A baseline exists only for the platform it was taken on, because fonts differ between systems.
- With no baseline for the current platform the comparison skips.
- ``OQ_UPDATE_VISUAL=1`` writes the baselines.
- The screenshot of every compared view is written to ``$OQ_VISUAL_OUT`` (default: the test's temp dir), so a person
  can look at it.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

CANDIDATES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge"]
VISUAL = Path(__file__).resolve().parent / "visual"


def find() -> str | None:
    """The first Chromium on the machine, or None."""
    try:
        import websockets.sync.client  # noqa: F401
    except ImportError:
        return None
    for c in CANDIDATES:
        p = c if os.path.isabs(c) and os.path.exists(c) else shutil.which(c)
        if p:
            return p
    return None


class Page:
    def __init__(self, ws_url: str):
        from websockets.sync.client import connect

        self.ws = connect(ws_url, max_size=None, open_timeout=20)
        self.n = 0
        self.events: list[dict] = []
        for m in ("Runtime.enable", "Log.enable", "Page.enable"):
            self.call(m)

    def call(self, method: str, timeout: float = 30, **params) -> dict:
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            msg = json.loads(self.ws.recv(timeout=max(0.1, end - time.monotonic())))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)
        raise TimeoutError(method)

    def eval(self, expr: str, timeout: float = 30):
        r = self.call("Runtime.evaluate", timeout=timeout, expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError((d.get("exception") or {}).get("description") or d.get("text"))
        return (r.get("result") or {}).get("value")

    def wait(self, expr: str, timeout: float = 20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            v = self.eval(expr)
            if v:
                return v
            time.sleep(0.1)
        raise TimeoutError(expr)

    def goto(self, url: str, width: int = 1280, height: int = 1000, scale: float = 1, ready: str | None = None) -> Page:
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=scale, mobile=False)
        self.call("Page.navigate", url=url)
        self.wait("document.readyState === 'complete'")
        if ready:
            self.wait(ready)
        time.sleep(0.3)                    # one more frame for the canvases
        return self

    def mouse(self, x: float, y: float) -> None:
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        time.sleep(0.15)

    def rect(self, selector: str) -> dict:
        return self.eval(f"(function(){{var r=document.querySelector({json.dumps(selector)}).getBoundingClientRect();"
                         "return {x:r.left+window.scrollX,y:r.top+window.scrollY,width:r.width,height:r.height};})()")

    def screenshot(self, clip: dict | None = None) -> bytes:
        params = {"format": "png", "captureBeyondViewport": True}
        if clip:
            params["clip"] = {**clip, "scale": 1}
        return base64.b64decode(self.call("Page.captureScreenshot", **params)["data"])

    def grid(self, png: bytes, cols: int) -> dict:
        """The browser decodes the PNG and averages it into ``cols`` columns of square cells: luminance 0–255 each."""
        b64 = base64.b64encode(png).decode()
        return self.eval("new Promise(function(ok){var im=new Image();im.onload=function(){var c=" + str(cols) + ",s=im.width/c,r=Math.max(1,Math.round(im.height/s));"
                         "var cv=document.createElement('canvas');cv.width=c;cv.height=r;var x=cv.getContext('2d');x.imageSmoothingQuality='high';x.drawImage(im,0,0,c,r);"
                         "var d=x.getImageData(0,0,c,r).data,out=[];for(var i=0;i<d.length;i+=4)out.push(Math.round(0.299*d[i]+0.587*d[i+1]+0.114*d[i+2]));"
                         "ok({cols:c,rows:r,w:im.width,h:im.height,v:out});};im.src='data:image/png;base64," + b64 + "';})")

    def errors(self) -> list[str]:
        out = []
        for m in self.events:
            p = m.get("params", {})
            if m["method"] == "Runtime.exceptionThrown":
                d = p["exceptionDetails"]
                out.append("exception: " + ((d.get("exception") or {}).get("description") or d.get("text", ""))[:300])
            elif m["method"] == "Runtime.consoleAPICalled" and p.get("type") in ("error", "assert"):
                out.append("console.error: " + " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))[:300])
            elif m["method"] == "Log.entryAdded" and p["entry"]["level"] == "error":
                out.append(f"log[{p['entry'].get('source')}]: {p['entry'].get('text', '')[:250]} {p['entry'].get('url', '')}")
        return out

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


class Browser:
    def __init__(self, exe: str):
        self.prof = tempfile.mkdtemp(prefix="oq-cdp-")
        self.proc = subprocess.Popen([exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
                                      "--font-render-hinting=none", f"--user-data-dir={self.prof}", "--remote-debugging-port=0", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.prof) / "DevToolsActivePort"
        for _ in range(200):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.05)
        self.port = port_file.read_text().split()[0]

    def page(self) -> Page:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
        target = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return Page(target["webSocketDebuggerUrl"])

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.prof, ignore_errors=True)


def console_errors(urls: list[str]) -> list[dict]:
    """Open each URL and collect console errors and uncaught exceptions."""
    exe = find()
    if not exe:
        return [{"url": u, "errors": [], "skipped": "no Chromium browser"} for u in urls]
    b = Browser(exe)
    try:
        out = []
        for u in urls:
            p = b.page()
            try:
                p.goto(u)
                time.sleep(0.5)
                out.append({"url": u, "errors": p.errors()})
            finally:
                p.close()
        return out
    finally:
        b.close()


def serve(flask_app):
    """Serve a Flask app on a free local port in a thread; returns (base_url, stop)."""
    from werkzeug.serving import make_server

    srv = make_server("127.0.0.1", 0, flask_app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return f"http://127.0.0.1:{srv.server_port}", srv.shutdown


def has_baseline(name: str) -> bool:
    """True when this platform has the baseline, or when baselines are being written."""
    return os.environ.get("OQ_UPDATE_VISUAL") == "1" or (VISUAL / sys.platform / f"{name}.json").exists()


def compare_grid(name: str, grid: dict, png: bytes | None = None, mean_tol: float = 2.5, cell_tol: int = 70, cell_share: float = 0.01) -> str | None:
    """Compare a grid with the baseline for this platform. Returns None when it matches, a message when it does not, and
    raises ``LookupError`` when there is no baseline (the caller skips)."""
    out_dir = Path(os.environ.get("OQ_VISUAL_OUT") or tempfile.gettempdir()) / "oq-visual"
    out_dir.mkdir(parents=True, exist_ok=True)
    if png:
        (out_dir / f"{name}.png").write_bytes(png)
    base = VISUAL / sys.platform / f"{name}.json"
    if os.environ.get("OQ_UPDATE_VISUAL") == "1":
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text(json.dumps(grid, separators=(",", ":")), encoding="utf-8")
        return None
    if not base.exists():
        raise LookupError(f"no visual baseline {base.relative_to(VISUAL.parent)} for {sys.platform} (OQ_UPDATE_VISUAL=1 writes it)")
    ref = json.loads(base.read_text(encoding="utf-8"))
    if (ref["cols"], ref["rows"]) != (grid["cols"], grid["rows"]):
        return f"{name}: size {grid['cols']}×{grid['rows']} cells, baseline {ref['cols']}×{ref['rows']} (screenshot in {out_dir})"
    diffs = [abs(a - b) for a, b in zip(grid["v"], ref["v"], strict=True)]
    mean = sum(diffs) / len(diffs)
    big = sum(d > cell_tol for d in diffs) / len(diffs)
    if mean > mean_tol or big > cell_share:
        return f"{name}: mean difference {mean:.2f} (tolerance {mean_tol}), {big:.1%} of cells differ by more than {cell_tol} (tolerance {cell_share:.0%}); screenshot in {out_dir}"
    return None
