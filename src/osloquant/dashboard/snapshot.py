"""A static, clickable copy of the dashboard for someone without the store (DECISIONS D44).

Every GET page reachable from the front page is rendered through the app itself (Flask's test client – no server has
to run), links are rewritten to flat relative file names (``/stock/SATS`` -> ``stock-SATS.html``, ``/`` ->
``idag.html``, and ``index.html`` is the front page too), forms are switched off in script except the ticker search,
which goes to the copied stock page, and a banner on every page says it is a copy and when it was taken. The
dashboard's own report PDFs are copied; the companies' quarterly reports link to their NewsWeb message instead of being
copied. ``cdn=True`` loads plotly.js from cdnjs (the same version the installed plotly bundles) instead of copying the
3.5 MB file, for hosts that refuse large inline files.

The copy holds whatever the dashboard shows – the research book, the judgement log, private cases – so it is written
only outside the repository (refused inside it) and shared only by the person who owns it. Nothing is published here.
"""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from importlib import resources
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parents[3]
HREF = re.compile(r'(href|src|action)="((?:http://127\.0\.0\.1:\d+)?/[^"]*)"')
FIX = """<script>
(function(){
  document.querySelectorAll('form').forEach(function(f){
    var a=(f.getAttribute('action')||'');
    if(a==='go'){f.addEventListener('submit',function(e){e.preventDefault();var i=f.querySelector('input[name=code]');var c=((i&&i.value)||'').trim().toUpperCase().replace(/\\.OL$/,'');if(c)location.href='stock-'+c+'.html';});return;}
    f.addEventListener('submit',function(e){e.preventDefault();});
    f.querySelectorAll('button,input[type=submit]').forEach(function(b){b.disabled=true;b.title='Statisk kopi: skjemaet er slått av';});
  });
})();
</script>"""


def fname(path: str) -> str | None:
    """A dashboard path -> the copy's file name (None = not copied: POST targets, the search, NewsWeb PDFs)."""
    path = unquote(urlsplit(path).path)
    if path in ("", "/"):
        return "idag.html"
    if path == "/static/plotly.min.js":
        return "plotly.min.js"
    m = re.fullmatch(r"/reports/([A-Za-z0-9]+)/([\w.\-]+\.pdf)", path)
    if m:
        return f"reports/{m.group(1).upper()}/{m.group(2)}"
    if path.startswith(("/report/", "/go")) or path.endswith("/judge"):
        return None
    slug = path.strip("/").replace("/", "-")
    return slug + ".html" if re.fullmatch(r"[A-Za-z0-9_\-]+", slug) else None


def plotly_version() -> str | None:
    p = Path(str(resources.files("plotly").joinpath("package_data/plotly.min.js")))
    with p.open(encoding="utf-8", errors="replace") as f:
        m = re.search(r"plotly\.js v(\d+\.\d+\.\d+)", f.read(400))
    return m.group(1) if m else None


def banner(stamp: str) -> str:
    return ('<div style="background:#fff4d6;color:#6b4a00;border-bottom:1px solid #e6c766;padding:6px 12px;font:12.5px/1.4 system-ui,sans-serif">'
            f'<b>Statisk kopi</b> av dashbordet, tatt {stamp}. Alle tall er fra da; skjemaer og knapper er slått av, '
            'søkefeltet virker for aksjer som er med i kopien. Papirpenger, ikke investeringsråd.</div>')


def rewrite(html: str, enqueue, stamp: str, plotly_src: str) -> str:
    def sub(m):
        attr, url = m.group(1), m.group(2)
        path = re.sub(r"^http://127\.0\.0\.1:\d+", "", url)
        mm = re.fullmatch(r"/report/([A-Za-z0-9]+)/(\d+)\.pdf", urlsplit(path).path)
        if mm:
            return f'{attr}="https://newsweb.oslobors.no/message/{mm.group(2)}" target="_blank" rel="noopener"'
        if attr == "action":
            return f'{attr}="{"go" if path.startswith("/go") else "#"}"'
        f = fname(path)
        if f is None:
            return f'{attr}="#"'
        if f == "plotly.min.js":
            if plotly_src != f:
                return f'{attr}="{plotly_src}"'
        enqueue(urlsplit(path).path or "/")
        return f'{attr}="{f}"'
    html = HREF.sub(sub, html)
    html = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + banner(stamp), html, count=1)
    return html.replace("</body>", FIX + "</body>") if "</body>" in html else html + FIX


def write(out: Path, app=None, cdn: bool = False, stamp: str | None = None, limit: int = 2000) -> dict:
    """Crawl the app from "/" and write the copy to ``out``. Returns counts and the paths that failed."""
    out = Path(out).resolve()
    if out == REPO or REPO in out.parents:
        raise ValueError(f"refusing to write a copy of the private research book inside the repository ({REPO})")
    if app is None:
        from osloquant.dashboard import server

        app = server.create_app()
    app.config["SNAPSHOT"] = True                 # the front page then leaves the signals unseen
    client = app.test_client()
    stamp = stamp or datetime.now().strftime("%d.%m.%Y kl. %H:%M")
    ver = plotly_version() if cdn else None
    plotly_src = f"https://cdnjs.cloudflare.com/ajax/libs/plotly.js/{ver}/plotly.min.js" if ver else "plotly.min.js"
    out.mkdir(parents=True, exist_ok=True)
    queue, seen, failed = deque(["/"]), {"/"}, {}
    pages = files = 0

    def enqueue(p: str) -> None:
        if p not in seen and len(seen) < limit:
            seen.add(p)
            queue.append(p)

    while queue:
        path = queue.popleft()
        f = fname(path)
        if f is None:
            continue
        try:
            r = client.get(path)
        except Exception as e:  # noqa: BLE001 – one broken page is reported, the rest of the copy is written
            failed[path] = f"{type(e).__name__}: {e}"
            continue
        if r.status_code != 200:
            failed[path] = r.status_code
            continue
        dest = out / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        if f.endswith(".html"):
            dest.write_text(rewrite(r.get_data(as_text=True), enqueue, stamp, plotly_src), encoding="utf-8")
            pages += 1
        else:
            dest.write_bytes(r.get_data())
            files += 1
    (out / "index.html").write_text((out / "idag.html").read_text(encoding="utf-8"), encoding="utf-8")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return {"pages": pages, "files": files, "failed": failed, "bytes": size, "plotly": plotly_src, "out": str(out)}
