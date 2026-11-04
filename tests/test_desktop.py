"""The dashboard as an app on the PC (D45): the icon is a valid PNG and ICO, the launcher reuses a running dashboard and
starts one only when nothing answers, the window opens in app mode, a server that dies is reported, and the shortcut
script names the right target – without touching the real desktop. The server's /ping and /favicon.ico."""

from __future__ import annotations

import struct
import zlib

from osloquant.dashboard import desktop as dt
from osloquant.dashboard import snapshot as sn

from .test_dashboard import app  # noqa: F401  (fixture)


def test_the_icon_is_a_valid_png_and_ico():
    p = dt.png(32)
    assert p[:8] == b"\x89PNG\r\n\x1a\n" and p[12:16] == b"IHDR" and struct.unpack(">II", p[16:24]) == (32, 32)
    idat_len = struct.unpack(">I", p[33:37])[0]
    raw = zlib.decompress(p[41:41 + idat_len])
    assert len(raw) == 32 * (1 + 32 * 4)                                                   # a filter byte and 32 RGBA pixels a row
    px = dt.icon_rgba(32)
    assert px[:4] == b"\x00\x00\x00\x00"                                                   # the rounded corner is transparent
    centre = (16 * 32 + 3) * 4
    assert px[centre:centre + 4] == bytes((*dt.BG, 255))                                   # teal left of the first bar
    bar = (int(0.7 * 32) * 32 + int(0.25 * 32)) * 4
    assert px[bar:bar + 4] == bytes((*dt.FG, 255))                                         # white inside the first bar
    i = dt.ico((16, 256))
    assert struct.unpack("<HHH", i[:6]) == (0, 1, 2)
    w, h, _, _, planes, bpp, size, off = struct.unpack("<BBBBHHII", i[6:22])
    assert (w, h, planes, bpp) == (16, 16, 1, 32) and i[off:off + 8] == b"\x89PNG\r\n\x1a\n" and size == len(dt.png(16))
    assert struct.unpack("<BB", i[22:24]) == (0, 0)                                        # 256 is written as 0


def test_the_launcher_reuses_a_running_dashboard_and_starts_one_otherwise(home, monkeypatch):
    opened, started = [], []
    monkeypatch.setattr(dt, "open_window", lambda port, browser=None: opened.append(port) or "edge")
    monkeypatch.setattr(dt, "is_up", lambda port=8060, timeout=1.0: True)
    monkeypatch.setattr(dt, "start_server", lambda port: started.append(port))
    assert dt.main() == 0 and opened == [8060] and started == []                           # already up: reused, not started twice
    state = {"n": 0}

    def up(port=8060, timeout=1.0):
        state["n"] += 1
        return state["n"] > 3                                                              # answers on the fourth look

    class Proc:
        def poll(self):
            return None
    monkeypatch.setattr(dt, "is_up", up)
    monkeypatch.setattr(dt, "start_server", lambda port: started.append(port) or Proc())
    monkeypatch.setattr(dt.time, "sleep", lambda s: None)
    assert dt.main(8065) == 0 and started == [8065] and opened == [8060, 8065]


def test_a_server_that_dies_is_reported_with_the_log(home, monkeypatch):
    msgs = []

    class Dead:
        def poll(self):
            return 1
    monkeypatch.setattr(dt, "is_up", lambda port=8060, timeout=1.0: False)
    monkeypatch.setattr(dt, "start_server", lambda port: Dead())
    monkeypatch.setattr(dt, "message", msgs.append)
    monkeypatch.setattr(dt, "open_window", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no window for a dead server")))
    assert dt.main() == 1 and "dashboard.log" in msgs[0] and "startet ikke" in msgs[0]


def test_start_server_and_open_window_build_the_right_commands(home, monkeypatch):
    calls = []
    dt.start_server(8061, popen=lambda cmd, **kw: calls.append((cmd, kw)))
    cmd, kw = calls[0]
    assert cmd[-4:] == ["dashboard", "--no-browser", "--port", "8061"] and "from osloquant.cli import app" in cmd[2]
    assert kw["stdin"] is not None and kw["env"]["PYTHONIOENCODING"] == "utf-8" and (dt.app_dir() / "dashboard.log").exists()
    win = []
    assert dt.open_window(8060, browser=r"C:\x\msedge.exe", popen=lambda cmd, **kw: win.append(cmd)) == r"C:\x\msedge.exe"
    assert win[0] == [r"C:\x\msedge.exe", "--app=http://127.0.0.1:8060/", "--window-size=1440,960"]
    assert dt.find_browser(("Z:/nope/a.exe",)) is None


def test_install_writes_the_icon_and_one_shortcut_per_folder(home, monkeypatch):
    if dt.os.name != "nt":
        return
    seen = {}

    class Res:
        returncode, stderr = 0, ""
        stdout = "C:\\Users\\x\\Desktop\\Oslo Børs-dashbord.lnk\nC:\\Users\\x\\Start Menu\\Programs\\Oslo Børs-dashbord.lnk\n"

    def run(cmd, **kw):
        seen["cmd"] = cmd
        return Res()
    paths = dt.install(run=run)
    script = seen["cmd"][-1]
    assert len(paths) == 2 and (dt.app_dir() / "dashboard.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert script.count("CreateShortcut") == 2 and "GetFolderPath('Desktop')" in script and "GetFolderPath('Programs')" in script
    assert "pythonw.exe" in script and "-m osloquant.dashboard.desktop" in script and "Oslo Børs-dashbord.lnk" in script and "dashboard.ico,0" in script


def test_the_server_answers_ping_and_serves_the_icon(app, tmp_path):  # noqa: F811
    client, _ = app
    assert client.get("/ping").get_data() == b"ok"
    r = client.get("/favicon.ico")
    assert r.status_code == 200 and r.mimetype == "image/x-icon" and r.get_data()[:4] == b"\x00\x00\x01\x00"
    assert '<link rel="icon" href="/favicon.ico">' in client.get("/coverage").get_data(as_text=True)
    assert sn.fname("/favicon.ico") == "favicon.ico"


def test_is_up_reads_ping_and_counts_an_older_dashboard_as_up(monkeypatch):
    import io
    import urllib.error

    class R(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dt.urllib.request, "urlopen", lambda u, timeout: R(b"ok"))
    assert dt.is_up(8060)

    def old(u, timeout):
        raise urllib.error.HTTPError(u, 404, "not found", {}, None)
    monkeypatch.setattr(dt.urllib.request, "urlopen", old)
    assert dt.is_up(8060)                                                                  # something answers: do not start a second one

    def nothing(u, timeout):
        raise ConnectionRefusedError
    monkeypatch.setattr(dt.urllib.request, "urlopen", nothing)
    assert not dt.is_up(8060)
