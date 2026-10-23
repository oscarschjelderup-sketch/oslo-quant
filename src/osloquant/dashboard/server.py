"""The local dashboard server (Flask, which ships with Dash). Reads the store, the research book, the judgement log,
the watchlist and the cached feeds; writes only by appending a judgement or a watchlist entry. It never trades and
never steps a paper account. Bound to 127.0.0.1 only.

    oq dashboard            # http://127.0.0.1:8060
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pandas as pd
from flask import Flask, Response, abort, redirect, request, send_file

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import market as mk
from osloquant.dashboard import render as rd
from osloquant.dashboard import today as td

PORT = 8060


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except ValueError:
        raise ValueError(f"'{v}' is not a number") from None


def today_context(mark_seen: bool = True, last_seen: str | None = None) -> dict:
    """Everything the front page shows. Signals are those after ``last_seen`` (default: the last visit)."""
    snap = mk.snapshot()
    today = pd.Timestamp.now().normalize()
    cases = bk.cases()
    watch = bk.watchlist()
    state = td.load_state()
    alerts, sessions = td.signals_since(snap, last_seen or state.get("last_seen_session"))
    newest = [a for a in alerts if a.session == f"{snap.asof:%Y-%m-%d}"]
    codes = [c.code for c in cases] + [w["code"] for w in watch if not w.get("moved_to_book")]
    decisions = sorted(td.decisions(snap, cases, newest, today, watch) + td.report_items(cases, today), key=lambda i: (i.urgency, i.code))
    ctx = dict(decisions=decisions, upcoming=td.upcoming(cases, today),
               moves=td.target_moves(snap, cases), alerts=alerts, sessions=sessions, asof=snap.asof, today=today,
               book_codes={c.code for c in cases}, price_label=mk.price_label(snap.asof),
               announcements=fd.announcements(codes, days=7))
    from osloquant.dashboard import insiders as ins

    ctx["insiders"] = ins.recent(set(codes), days=7)
    ctx["shorts_moved"] = ins.short_moves(codes, days=7)
    if mark_seen:
        state["last_seen_session"] = f"{snap.asof:%Y-%m-%d}"
        td.save_state(state)
    return ctx


def stock_context(code: str) -> dict:
    snap = mk.snapshot()
    code = code.upper().removesuffix(".OL")
    st = sg.status(snap.panel, code)
    c = bk.case(code)
    ret = mk.returns(snap)
    alerts, _ = td.signals_since(snap, None, max_sessions=10)
    from osloquant.dashboard.casefile import reverse_dcf
    from osloquant.dashboard.charts import price_chart

    lp = mk.last_price(snap, code)
    case_odds = None
    if c and c.view and c.view.get("target"):
        from osloquant.dashboard import odds as od

        kill, why = od.kill_level(c.view)
        if kill:
            case_odds = od.case_odds(code, float(c.view["target"]), kill, why)
    return dict(status=st, case=c, name=snap.names.get(code, c.name if c else code), group=snap.group(code),
                price_label=mk.price_label(lp[1]) if lp else "", alerts=[a for a in alerts if a.code == code],
                ytd=ret.loc[code, "ytd"] if code in ret.index else None, chart=price_chart(snap, code, c),
                rdcf=reverse_dcf(c.model) if c else None, news=fd.company_news(code, snap.names.get(code, code), snap.names),
                odds=case_odds, report=_report(code) if c else None, insiders=_insiders(code))


def _insiders(code: str) -> dict:
    from osloquant.dashboard import insiders as ins
    from osloquant.dashboard.charts import short_chart

    year_ago = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    items = [i for i in ins.for_code(code, limit=200) if i["time"][:10] >= year_ago][:20]
    s = ins.shorts(code)
    return {"items": items, "shorts": s, "short_change_30": ins.short_change(s, 30) if s else None,
            "short_chart": short_chart(s["series"], code) if s else ""}


def _report(code: str) -> dict | None:
    from osloquant.dashboard import reports as rp

    s = rp.latest(code)
    return {"summary": s, "spec": rp.specs().get(code) or {}} if s else ({"summary": None, "spec": rp.specs().get(code)} if rp.specs().get(code) else None)


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/static/plotly.min.js")
    def plotly_js():
        path = Path(str(resources.files("plotly").joinpath("package_data/plotly.min.js")))
        return send_file(path, mimetype="application/javascript", max_age=86400)

    @app.get("/report/<code>/<int:mid>.pdf")
    def report_pdf(code, mid):
        if not code.isalnum():
            abort(404)
        p = jg.home() / "reports" / code.upper() / f"{mid}.pdf"
        if not p.exists():
            abort(404)
        return send_file(p, mimetype="application/pdf")

    @app.get("/")
    def home():
        return rd.today_page(today_context())

    @app.get("/sectors")
    def sectors():
        snap = mk.snapshot()
        return rd.sectors_page(mk.returns(snap), fd.sector_drivers(), mk.GROUP_ORDER + ["Other"], snap.asof)

    @app.get("/go")
    def go():
        code = (request.args.get("code") or "").strip().upper().removesuffix(".OL")
        return redirect(f"/stock/{code}") if code.isalnum() else redirect("/")

    @app.get("/stock/<code>")
    def stock(code):
        if not code.isalnum():
            abort(404)
        ctx = stock_context(code)
        if request.args.get("logged"):
            ctx["ok"] = [f"Logged as row #{request.args['logged']} in the judgement log."]
        return rd.stock_page(code.upper(), ctx)

    @app.post("/stock/<code>/judge")
    def judge(code):
        if not code.isalnum():
            abort(404)
        code = code.upper()
        f = request.form
        form = {"rating": f.get("rating", ""), "rationale": f.get("rationale", ""), "kill_text": f.get("kill", ""),
                "kill": [k for k in f.get("kill", "").splitlines() if k.strip()], "horizon": f.get("horizon") or 12}
        errors = []
        for k in ("target", "bear", "base", "bull", "p_bear", "p_base", "p_bull", "kill_level"):
            try:
                form[k] = _num(f.get(k))
            except ValueError as e:
                errors.append(f"{k}: {e}")
        snap = mk.snapshot()
        lp = mk.last_price(snap, code)
        if lp is None:
            errors.append(f"no price for {code} in the store")
        if not errors:
            try:
                row = bk.write_judgement(code, f.get("name") or code, form, lp[0], f"{lp[1]:%Y-%m-%d}", mk.PRICE_SOURCE)
                return redirect(f"/stock/{code}?logged={row['seq']}", code=303)
            except (ValueError, RuntimeError) as e:
                errors.append(str(e))
        ctx = stock_context(code)
        ctx["errors"], ctx["form"] = errors, form
        return Response(rd.stock_page(code, ctx), status=400)

    @app.get("/calibration")
    def calibration():
        check = jg.verify()
        table, summary = jg.calibration()
        kills = [r for r in jg.read_log() if r["kind"] == "kill_check"]
        return rd.calibration_page(table, summary, check, kills)

    def _watch(msg=None, status=200):
        snap = mk.snapshot()
        alerts, _ = td.signals_since(snap, None, max_sessions=10)
        return Response(rd.watchlist_page(bk.watchlist(), mk.returns(snap), alerts, msg), status=status)

    @app.get("/watchlist")
    def watchlist():
        return _watch()

    @app.post("/watchlist")
    def watch_add():
        try:
            e = bk.add_watch(request.form.get("code", ""), request.form.get("note", ""))
            return _watch({"ok": [f"{e['code']} added."]})
        except ValueError as err:
            return _watch({"errors": [str(err)]}, 400)

    return app


def static_today_html(last_seen: str | None = None) -> str:
    """The front page as a self-contained file (links point at the running dashboard); does not mark signals seen."""
    return rd.today_page(today_context(mark_seen=False, last_seen=last_seen), static=True)


def write_static_today(path: Path | None = None, last_seen: str | None = None) -> Path:
    path = path or (sg.signals_dir() / "latest.html")
    path.write_text(static_today_html(last_seen), encoding="utf-8")
    return path


def main(port: int = PORT, open_browser: bool = True) -> None:
    app = create_app()
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
