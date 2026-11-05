"""The local dashboard server (Flask, which ships with Dash). Reads the store, the research book, the judgement log,
the watchlist and the cached feeds; writes only by appending a judgement or a watchlist entry. It never trades and
never steps a paper account. Bound to 127.0.0.1 only.

    oq dashboard            # http://127.0.0.1:8060
"""

from __future__ import annotations

import html
from functools import lru_cache
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

E = html.escape
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
    decisions = td.merge_items(td.decisions(snap, cases, newest, today, watch), td.report_items(cases, today), td.pre_report_items(cases, today),
                               td.post_report_items(cases, today), td.report_tp_items(cases, today), _habit_items(cases, today))
    ctx = dict(decisions=decisions, upcoming=td.upcoming(cases, today),
               moves=td.target_moves(snap, cases, today), alerts=alerts, sessions=sessions, asof=snap.asof, today=today,
               book_codes={c.code for c in cases}, price_label=mk.price_label(snap.asof),
               announcements=fd.announcements(codes, days=7))
    from osloquant.dashboard import insiders as ins
    from osloquant.dashboard import portfolio as pf
    from osloquant.dashboard import sizing

    ctx["insiders"] = ins.recent(set(codes), days=7)
    ctx["shorts_moved"] = ins.short_moves(codes, days=7)
    from osloquant.dashboard import coverage as cv

    ctx["coverage"] = {"n": len(cases), "claude": sum(bool(c.claude_view) for c in cases),
                       "only_claude": sum(bool(c.claude_view) and not c.view for c in cases),
                       **cv.counts(cv.universe(snap, cases, watch, today))}
    ctx["portfolio"] = pf.exposure(cases, {c.code: snap.group(c.code) for c in cases}, sizing.config())
    from osloquant.dashboard import desk

    ctx["desk"] = desk.front_summary(f"{snap.asof:%Y-%m-%d}")
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
    from osloquant.dashboard import calendar as cal
    from osloquant.dashboard import lightcase as lcm

    today = pd.Timestamp.now().normalize()
    nxt = next((e for e in cal.events([c] if c else [], today=today, days=200) if e.get("code") == code and e["kind"] in ("report", "case")), None)
    from osloquant.dashboard import reportpdf as rpdf

    ents = rpdf.entries(code)
    reports_html = rpdf.block_html(code, ents, rpdf.revision(ents), rpdf.tp_mismatch(ents[0] if ents else None, c.view if c else None, c.history if c else None))
    from osloquant.dashboard import afterreport as ar
    from osloquant.dashboard import desk

    return dict(status=st, case=c, name=snap.names.get(code, c.name if c else code), group=snap.group(code), lightcase=lcm.load(code),
                next_event=nxt, today=today, reports_html=reports_html, afterreport_html=ar.block_html(code, ar.load(code)),
                update_html=_update_html(code, c, today),
                inversion_html=_inversion_html(code, c, lp[0] if lp else None),
                baserate_html=_baserate_html(code),
                forecast_html=_forecast_html(code, c, today),
                pass_html=_pass_html(code),
                price_label=mk.price_label(lp[1]) if lp else "", alerts=[a for a in alerts if a.code == code],
                ytd=ret.loc[code, "ytd"] if code in ret.index else None, chart=price_chart(snap, code, c),
                rdcf=reverse_dcf(c.model) if c else None, news=fd.company_news(code, snap.names.get(code, code), snap.names),
                odds=case_odds, report=_report(code) if c else None, insiders=_insiders(code), sizing=_sizing(code),
                desk_runs=desk.runs_for(code))


def attach_desk(ctx: dict, code: str, run_id: str) -> None:
    """A stock page opened from a desk run (``?desk=<run id>``): the debate is attached above the form and, when the
    run ended in "klar for vurdering", the form is prefilled from the view and the Risk role. Nothing is written."""
    from osloquant.dashboard import desk

    run = desk.load_run(run_id)
    sr = run.stock(code) if run else None
    if not sr:
        ctx.setdefault("errors", []).append(f"no desk run {run_id} for {code}")
        return
    ctx["desk_attached"] = (run, sr)
    form = dict(ctx.get("form") or {})
    if sr.outcome == "ready" and sr.prefill:
        form.update({k: v for k, v in sr.prefill.items() if v not in (None, "")})
    form["desk_run"] = run.run_id
    ctx["form"] = form


def coverage_rows(cases, snap, today: pd.Timestamp) -> list[dict]:
    """One row per company with a view from either analyst, for the coverage page."""
    from osloquant.dashboard import calendar as cal
    from osloquant.dashboard import lightcase as lcm

    nxt: dict = {}
    for e in cal.events(cases, today=today, days=200):
        if e.get("code") and e["kind"] in ("report", "case") and e["code"] not in nxt:
            nxt[e["code"]] = e
    out = []
    for c in cases:
        if not (c.view or c.claude_view):
            continue
        lp = mk.last_price(snap, c.code)
        px = lp[0] if lp else None

        def v(view, px=px):
            if not view or not view.get("target"):
                return None
            since = px / view["price"] - 1 if px and view.get("price") else None
            return {"rating": view.get("rating"), "target": float(view["target"]), "date": view.get("date"),
                    "since": 0.0 if since is not None and abs(since) < 5e-4 else since,      # no "-0.0 %" on the day a view is logged
                    "to_tp": float(view["target"]) / px - 1 if px else None}
        lc = lcm.load(c.code)
        out.append({"code": c.code, "name": c.name, "group": snap.group(c.code), "price": px, "oscar": v(c.view), "claude": v(c.claude_view),
                    "reads": _short_read(lc), "next": nxt.get(c.code)})
    return sorted(out, key=lambda r: (r["group"], r["code"]))


def _short_read(lc: dict | None) -> str | None:
    if not lc:
        return None
    rv = lc["reverse"]
    if lc["financial"]:
        return None if rv.get("implied_roe") is None else f"ROE {rv['implied_roe'] * 100:.0f} % for good (har {(rv.get('actual_roe') or 0) * 100:.0f} %)"
    g, vs = rv.get("implied_g"), rv.get("ev_vs_no_growth")
    if vs is not None and vs < 0:
        return f"fallende resultat (EV {vs * 100:.0f} % under null-vekst)"
    if g is None:
        return "høyere marginer, ikke vekst" if rv.get("roic") is not None and rv["roic"] < rv["wacc_est"] else "–"
    return f"{g * 100:+.1f} %/år vekst for alltid"


def _sizing(code: str) -> dict | None:
    from osloquant.dashboard import sizing

    cfg = sizing.config()
    if not cfg:
        return None
    opened = sizing.open_positions(exclude=code)
    used = sum(float(r.get("position_value") or 0) for r in opened.values())
    return {"cfg": cfg, "cost": sizing.COST, "free": max(float(cfg["paper_capital"]) - used, 0.0),
            "open_loss": sum(float(r.get("loss_at_kill") or 0) for r in opened.values())}


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


@lru_cache(maxsize=1)
def _icon_bytes() -> bytes:
    """The app icon (D45) as the favicon, so the app window and the tab carry it."""
    from osloquant.dashboard import desktop

    return desktop.ico((16, 32, 48))


def _habit_items(cases, today) -> list:
    """D48–D52 on the front page; a failure here must never take the front page down."""
    from osloquant.dashboard import calendar as cal

    try:
        return td.habit_items(cases, today, cal_doc=fd.read(cal.CAL_FEED))
    except Exception as e:  # noqa: BLE001
        return [td.Item("", "chief", "Løkkene fra 5. nov kunne ikke leses", f"{type(e).__name__}: {e}", 2)]


def _pass_html(code: str) -> str:
    """D54: log a decision not to buy."""
    from osloquant.dashboard import passes as ps

    return ps.stock_html(code, jg.read_log())


def _forecast_html(code: str, c, today) -> str:
    """D52: an 80 % interval for the next report's numbers, answered by the report reader."""
    from osloquant.dashboard import forecasts as fc

    return fc.block_html(code, fc.upcoming(code, [c] if c else [], today), jg.read_log())


def _baserate_html(code: str) -> str:
    """D47: the newest report's estimates against the base rates (shown above the report box)."""
    from osloquant.dashboard import baserate as bsr

    try:
        res = bsr.for_code(code)
    except Exception as e:  # noqa: BLE001 – a missing store table must not take the stock page down
        return f'<div class="src">Base rates could not be computed: {E(type(e).__name__)}</div>'
    return f'<h2>Base rates for estimatene</h2><div class="card">{bsr.box_html(res, with_reason=False)}</div>' if res else ""


def _inversion_html(code: str, c, price: float | None) -> str:
    """D51: what has to go wrong for a 30 % loss, from the model's sensitivity tables."""
    from osloquant.dashboard import inversion as iv

    return iv.block_html(iv.for_case(c, price), code)


def _update_html(code: str, c, today) -> str:
    """D48: the «has your probability changed?» question when a report came after the open view."""
    from osloquant.dashboard import calendar as cal
    from osloquant.dashboard import updates as up

    rows = jg.read_log()
    item = next((p for p in up.pending(rows, [c] if c else [], today, fd.read(cal.CAL_FEED)) if p["code"] == code), None)
    return up.block_html(item, rows)


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/ping")
    def ping():
        return Response("ok", mimetype="text/plain")                # the app launcher's "is it up" (D45)

    @app.get("/favicon.ico")
    def favicon():
        return Response(_icon_bytes(), mimetype="image/x-icon", headers={"Cache-Control": "max-age=86400"})

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

    @app.get("/reports/<code>/<fname>")
    def report_file(code, fname):
        from osloquant.dashboard import reportpdf as rpdf

        if not code.isalnum() or not rpdf.safe_name(fname):
            abort(404)
        p = rpdf.folder(code) / fname
        if not p.exists() or p.parent != rpdf.folder(code):
            abort(404)
        return send_file(p, mimetype="application/pdf")

    @app.get("/stock/<code>/pretrade")
    def pretrade_page(code):
        from osloquant.dashboard import pretrade as pt

        if not code.isalnum():
            abort(404)
        return pt.page_html(pt.context(code))

    @app.get("/")
    def home():
        return rd.today_page(today_context(mark_seen=not app.config.get("SNAPSHOT")))     # a copy (D44) must not mark signals seen

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
        if request.args.get("passed"):
            ctx["ok"] = [f"Pass logged as row #{request.args['passed']} in the judgement log."]
        if request.args.get("forecast"):
            ctx["ok"] = [f"Forecast logged as row #{request.args['forecast']} in the judgement log."]
        if request.args.get("updated"):
            ctx["ok"] = [f"Update logged as row #{request.args['updated']} in the judgement log."]
        if request.args.get("checklist"):
            ctx["form"] = {"checklist": ",".join(k for k in request.args["checklist"].split(",") if k.replace("_", "").isalnum())}
        if request.args.get("desk"):
            attach_desk(ctx, code.upper(), request.args["desk"])
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
        form["consensus_source"] = (f.get("consensus_source") or "").strip()
        form["ack_triggered"] = bool(f.get("ack_triggered"))
        form["claude_exists"] = bool(f.get("claude_exists"))
        form["saw_claude"] = f.get("saw_claude") or None
        form["checklist"] = ",".join(k for k in (f.get("checklist") or "").split(",") if k.replace("_", "").isalnum())
        form["desk_run"] = (f.get("desk_run") or "").strip()
        from osloquant.dashboard import discipline as dsc

        form["premortem"] = dsc.premortem_from_form(f)                       # D46
        form["probs_deliberate"] = bool(f.get("probs_deliberate"))
        form["anchor_reason"] = (f.get("anchor_reason") or "").strip()
        form["base_rate_reason"] = (f.get("base_rate_reason") or "").strip()            # D47
        for k in ("variant_kind", "variant_edge", "catalyst", "catalyst_by"):              # D55
            form[k] = (f.get(k) or "").strip()
        for k in ("story", "story_rev_cagr", "story_ebitda_m", "story_eps"):                # D53
            form[k] = (f.get(k) or "").strip()
        for k in ("target", "bear", "base", "bull", "p_bear", "p_base", "p_bull", "kill_level", "position_shares", "consensus_target"):
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
        if form.get("desk_run"):
            attach_desk(ctx, code, form["desk_run"])
            ctx["form"] = form                                    # the typed values win over the prefill
        return Response(rd.stock_page(code, ctx), status=400)

    @app.post("/stock/<code>/pass")
    def pass_(code):
        from osloquant.dashboard import passes as ps

        if not code.isalnum():
            abort(404)
        code = code.upper()
        lp = mk.last_price(mk.snapshot(), code)
        try:
            if lp is None:
                raise ValueError(f"no price for {code} in the store")
            row = ps.write(code, request.form.get("reason", ""), bool(request.form.get("inside")), lp[0], f"{lp[1]:%Y-%m-%d}", pd.Timestamp.now().strftime("%Y-%m-%d"))
            return redirect(f"/stock/{code}?passed={row['seq']}", code=303)
        except (ValueError, RuntimeError) as e:
            ctx = stock_context(code)
            ctx["errors"] = [str(e)]
            return Response(rd.stock_page(code, ctx), status=400)

    @app.post("/stock/<code>/forecast")
    def forecast(code):
        from osloquant.dashboard import forecasts as fc

        if not code.isalnum():
            abort(404)
        code = code.upper()
        f = request.form
        report = {k: f.get(f"report_{k}") for k in ("date", "what", "source")} if f.get("report_date") else None
        try:
            row = fc.write(code, {k: f.get(k) for k in ("metric", "low", "mid", "high")}, report, pd.Timestamp.now().normalize())
            return redirect(f"/stock/{code}?forecast={row['seq']}", code=303)
        except (ValueError, RuntimeError) as e:
            ctx = stock_context(code)
            ctx["errors"] = [str(e)]
            return Response(rd.stock_page(code, ctx), status=400)

    @app.post("/stock/<code>/update")
    def update(code):
        from osloquant.dashboard import updates as up

        if not code.isalnum():
            abort(404)
        code = code.upper()
        f = request.form
        form = {k: f.get(k) for k in ("p_bear", "p_base", "p_bull", "reason", "trigger_date", "trigger_what", "trigger_source")} | {"changed": bool(f.get("changed"))}
        lp = mk.last_price(mk.snapshot(), code)
        try:
            if lp is None:
                raise ValueError(f"no price for {code} in the store")
            row = up.write(code, form, lp[0], f"{lp[1]:%Y-%m-%d}", pd.Timestamp.now().strftime("%Y-%m-%d"))
            return redirect(f"/stock/{code}?updated={row['seq']}", code=303)
        except (ValueError, RuntimeError) as e:
            ctx = stock_context(code)
            ctx["errors"] = [str(e)]
            return Response(rd.stock_page(code, ctx), status=400)

    def _review_page(msg: dict | None = None, status: int = 200):
        from osloquant.dashboard import review as rv

        rows = jg.read_log()
        table, _ = jg.calibration(rows)
        today = pd.Timestamp.now().normalize()
        notes = "".join(f'<div class="err">{E(m)}</div>' for m in (msg or {}).get("errors", [])) + "".join(f'<div class="ok">{E(m)}</div>' for m in (msg or {}).get("ok", []))
        return Response(rd.page("Feilgjennomgang", "/review", notes + rv.page_html(rv.items(rows, table, today), rv.summary(rows), today)), status=status)

    def _chief_page(msg: dict | None = None, status: int = 200):
        from osloquant.dashboard import chief as ch

        runs = ch.latest_runs(2)
        today = f"{pd.Timestamp.now():%Y-%m-%d}"
        if runs and runs[-1]["date"] == today:
            doc, prev, stored = runs[-1], (runs[-2] if len(runs) > 1 else None), True
            doc = doc | ch.proposals(doc["results"], ch.read_decisions())          # decisions made since the run apply at once
        else:
            doc, prev, stored = ch.run(ch.build_ctx()), (runs[-1] if runs else None), False
        return Response(rd.page("Analysesjef", "/chief", ch.page_html(doc, prev, stored, msg)), status=status)

    @app.get("/chief")
    def chief_page():
        return _chief_page()

    @app.post("/chief/decide")
    def chief_decide():
        from osloquant.dashboard import chief as ch

        f = request.form
        try:
            mv = f.get("metric_at")
            row = ch.decide(f.get("proposal", ""), f.get("decision", ""), f.get("reason", ""), f.get("reason_kind") or None,
                            float(mv) if mv not in (None, "") else None)
            return _chief_page({"ok": [f"{row['proposal']}: {row['decision']} ({row['reason']})."]})
        except ValueError as e:
            return _chief_page({"errors": [str(e)]}, 400)

    @app.get("/review")
    def review_page():
        return _review_page()

    @app.post("/review/<int:seq>")
    def review_write(seq):
        from osloquant.dashboard import review as rv

        try:
            row = rv.write(seq, {k: request.form.get(k) for k in ("premortem_hit", "info_available", "cause", "bias", "lesson", "vs_target", "status")},
                           pd.Timestamp.now().normalize())
            return _review_page({"ok": [f"Gjennomgangen av #{seq} er lagret som rad #{row['seq']}."]})
        except (ValueError, RuntimeError) as e:
            return _review_page({"errors": [str(e)]}, 400)

    @app.get("/desk")
    def desk_page():
        from osloquant.dashboard import desk, deskpage

        runs = desk.index()[::-1]
        last = desk.load_run(runs[0]["run_id"]) if runs else None
        return deskpage.desk_page(last, runs, desk.veto_stats(), pd.Timestamp.now().normalize())

    @app.post("/desk/run")
    def desk_run():
        from osloquant.dashboard import desk, deskpage

        code = (request.form.get("code") or "").strip().upper().removesuffix(".OL")
        if not code.isalnum():
            runs = desk.index()[::-1]
            return Response(deskpage.desk_page(desk.load_run(runs[0]["run_id"]) if runs else None, runs, desk.veto_stats(), pd.Timestamp.now().normalize(),
                                               msg={"errors": ["a stock code has letters and digits only"]}), status=400)
        run = desk.run([code], trigger="manual")
        if run.stock(code) is None:
            runs = desk.index()[::-1]
            return Response(deskpage.desk_page(run, runs, desk.veto_stats(), pd.Timestamp.now().normalize(),
                                               msg={"errors": [f"no close for {code} on the newest session in the store – nothing for the desk to read"]}), status=400)
        return redirect(f"/desk/run/{run.run_id}/{code}", code=303)

    @app.get("/desk/run/<run_id>")
    def desk_run_page(run_id):
        from osloquant.dashboard import desk, deskpage

        run = desk.load_run(run_id)
        if run is None:
            abort(404)
        return deskpage.run_page(run)

    @app.get("/desk/run/<run_id>/<code>")
    def desk_stock_page(run_id, code):
        from osloquant.dashboard import desk, deskpage

        run = desk.load_run(run_id) if code.isalnum() else None
        sr = run.stock(code.upper()) if run else None
        if sr is None:
            abort(404)
        return deskpage.stock_log_page(run, sr)

    @app.get("/calendar")
    def calendar_page():
        from osloquant.dashboard import calendar as cal

        today = pd.Timestamp.now().normalize()
        return cal.page_html(cal.events(bk.cases(), bk.watchlist(), today), today, fd.read(cal.CAL_FEED), cal.norges_bank_meetings())

    @app.get("/health")
    def health():
        from osloquant.dashboard import datahealth as dh
        from osloquant.dashboard import odds as od

        closes = od.long_closes()
        return dh.page_html(dh.overview(closes, bk.cases(), closes.index[-1] if len(closes) else None))

    @app.get("/calibration")
    def calibration():
        check = jg.verify()
        rows = jg.read_log()
        table, summary = jg.calibration(rows)
        kills = [r for r in rows if r["kind"] == "kill_check"]
        rel = jg.reliability(rows, table=table) if len(table) else None
        fp = jg.fingerprint([dict(c.view, code=c.code) for c in bk.cases() if c.view])
        from osloquant.dashboard import learn

        learn_html = ""
        if len(table):
            prices = jg.load_prices(start=min(pd.Timestamp(j["date"]) for j in jg.judgements(rows)) - pd.Timedelta(days=10))
            learn_html = learn.by_case_html(learn.by_case(table, rel)) + learn.patterns_html(learn.error_patterns(rows, table, prices))
            from osloquant.dashboard import discipline as dsc

            learn_html = dsc.grid_html(dsc.decision_grid(rows, table)) + learn_html          # D46: process against outcome
            from osloquant.dashboard import calendar as cal
            from osloquant.dashboard import updates as up

            learn_html += up.calibration_html(up.scoring(rows, table, pd.Timestamp.now().normalize(), bk.cases(), fd.read(cal.CAL_FEED)))   # D48
        from osloquant.dashboard import forecasts as fcs

        learn_html += fcs.calibration_html(fcs.scoring(rows))                                         # D52
        from osloquant.dashboard import passes as pss

        learn_html += pss.calibration_html(pss.scoring(rows))                                         # D54
        return rd.calibration_page(table, summary, check, kills, rel, fp, jg.head_to_head(table), learn_html)

    @app.get("/funds")
    def funds_page():
        from osloquant.dashboard import funds as fn

        b = fn.load_build()
        tracked = []
        if fn.load_all():
            pr = jg.load_prices(start=pd.Timestamp.now().normalize() - pd.Timedelta(days=400))
            tracked = fn.tracking(pr.adjusted, pr.index, fn.risk_free()[0])
        return rd.funds_page(b, tracked, pd.Timestamp.now().normalize())

    @app.get("/coverage")
    def coverage():
        from osloquant.dashboard import calendar as cal
        from osloquant.dashboard import coverage as cv

        snap = mk.snapshot()
        today = pd.Timestamp.now().normalize()
        cases, watch = bk.cases(), bk.watchlist()
        rows = coverage_rows(cases, snap, today)
        table = jg.calibration()[0] if any(r["claude"] and r["oscar"] for r in rows) else pd.DataFrame()
        nxt: dict = {}
        for e in cal.events(cases, watch, today=today, days=200):
            if e.get("code") and e["kind"] in ("report", "case") and e["code"] not in nxt:
                nxt[e["code"]] = e
        uni = cv.universe(snap, cases, watch, today, next_events=nxt)
        from osloquant.dashboard import afterreport as ar

        queue = ar.queue_html(ar.due(cases, uni, today, fd.read(cal.CAL_FEED)), today)
        return rd.coverage_page(rows, today, jg.head_to_head(table) if len(table) else None, uni, cv.summary(uni), queue)

    @app.get("/screen")
    def screen():
        from osloquant.dashboard import coverage as cv
        from osloquant.dashboard import lightcase as lcm
        from osloquant.dashboard import screen as sc

        snap = mk.snapshot()
        today = pd.Timestamp.now().normalize()
        uni = cv.universe(snap, bk.cases(), bk.watchlist(), today)
        cases = [x for x in (lcm.load(r["code"]) for r in uni) if x]
        rs = sc.rows(cases, {r["code"]: r["level"] for r in uni})
        return rd.screen_page(rs, sc.candidates(rs), sc.counts(rs), today)

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
