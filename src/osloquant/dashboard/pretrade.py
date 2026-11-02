"""«Før du kjøper»: everything that should be on one page before the judgement form opens (DECISIONS, rapporter
2026-11-02, part 2). Numbers, lists and sources only – no generated text:

1. what the market prices in (the toolkit model's reverse DCF, the light case's implied growth) against the view;
2. the outcome odds – target first, kill level first or neither at 3, 6 and 12 months;
3. the bull and bear case and the strongest arguments against buying, quoted from the case, the latest report reading,
   Claude's view, the light case and the risk signals;
4. the dated events before the horizon;
5. the position size at the maximum loss and the exposure already in the same sector group;
6. a checklist that has to be ticked before the form is reached; the ticks are written on the judgement row.
"""

from __future__ import annotations

import pandas as pd

from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import market as mk

CHECKLIST = [("read_report", "Jeg har lest siste rapport fra selskapet (ikke bare sammendraget)"),
             ("knows_kill", "Jeg kjenner kill-kriteriene og kursnivået der caset er brutt"),
             ("new_argument", "Dette er et nytt argument – ikke en kurs som har steget"),
             ("seen_implied", "Jeg har sett hva markedet priser inn, og mitt syn avviker fra det i tall")]
MAX_ARGS = 3


def arguments_against(c: bk.Case | None, lc: dict | None, rep: dict | None, alerts: list, px: float | None) -> list[dict]:
    """The strongest arguments against buying, each a quote with its source. Order of strength: a kill criterion over
    the line in the latest report, one nearer, Claude's lower view, the light case's reading of the price, a risk
    signal, the case's own bear value."""
    out = []
    if rep and rep.get("summary"):
        s = rep["summary"]
        src = f"rapportleseren, Q{s.get('quarter')} {s.get('year')} ({str(s.get('published', ''))[:10]})"
        for k in s.get("kill", []):
            st = str(k.get("status", ""))
            if st.startswith("triggered"):
                out.append({"rank": 0, "text": f"{k['criterion']}: {st}" + (f" – nå {k['now']:.4g} mot {k['threshold']:.4g}" if isinstance(k.get("now"), (int, float)) and isinstance(k.get("threshold"), (int, float)) else ""), "source": src})
        for k in s.get("kill", []):
            st = str(k.get("status", ""))
            if st.startswith("intact, nearer"):
                out.append({"rank": 1, "text": f"{k['criterion']}: {st}", "source": src})
    v = (c.view if c else None) or {}
    cv = (c.claude_view if c else None) or {}
    if cv and cv.get("target") and (not v.get("target") or float(cv["target"]) < float(v["target"]) or (cv.get("rating") in ("SELL", "HOLD") and v.get("rating") == "BUY")):
        out.append({"rank": 2, "text": f"Claudes syn {cv.get('rating')} med kursmål {float(cv['target']):g}" + (f" – «{str(cv.get('thesis'))[:220]}»" if cv.get("thesis") else ""),
                    "source": f"Claudes vurdering {cv.get('date')}"})
    if lc:
        rv = lc.get("reverse") or {}
        if rv.get("reads"):
            out.append({"rank": 3, "text": str(rv["reads"]), "source": f"lett case, bygget {str(lc.get('built_at', ''))[:10]} (Yahoo-regnskap, EST-forutsetninger)"})
        for w in lc.get("warnings") or []:
            out.append({"rank": 4, "text": str(w), "source": f"lett case, bygget {str(lc.get('built_at', ''))[:10]}"})
    for a in alerts:
        if a.kind == sg.RISK:
            out.append({"rank": 5, "text": f"{a.signal}: {a.detail}", "source": f"signal {a.session} (lageret, forsinket)"})
    if v.get("bear") and px:
        out.append({"rank": 6, "text": f"Bear-verdi {float(v['bear']):g} ({(float(v['bear']) / px - 1) * 100:+.0f} % fra kursen) med sannsynlighet {v.get('p_bear') if v.get('p_bear') is not None else '–'}",
                    "source": f"din vurdering {v.get('date')}"})
    out.sort(key=lambda a: a["rank"])
    return out


def implied(c: bk.Case | None, lc: dict | None, rdcf: dict | None, px: float | None) -> list[dict]:
    """Rows of 'the market prices in X, I say Y', each with its source."""
    rows = []
    v = (c.view if c else None) or {}
    if rdcf and not rdcf.get("error"):
        md = rdcf.get("model_date")
        src = f"casemodellen ({rdcf.get('file')}, {str(md)[:10] if md else '?'}; kurs {rdcf.get('price')} per {str(rdcf.get('price_date'))[:10]})"
        if rdcf.get("rd_m_last") is not None:
            rows.append({"what": "EBIT adj.-margin siste år", "market": f"{rdcf['rd_m_last'] * 100:.1f} %", "mine": f"{rdcf['rd_m_last_ours'] * 100:.1f} %" if rdcf.get("rd_m_last_ours") is not None else "–",
                         "today": f"{rdcf['rd_m_last_ref'] * 100:.1f} %" if rdcf.get("rd_m_last_ref") is not None else "–", "source": src})
        if rdcf.get("rd_cagr") is not None:
            rows.append({"what": "Omsetningsvekst per år", "market": f"{rdcf['rd_cagr'] * 100:.1f} %", "mine": f"{rdcf['rd_cagr_ours'] * 100:.1f} %" if rdcf.get("rd_cagr_ours") is not None else "–",
                         "today": f"{rdcf['rd_cagr_ref'] * 100:.1f} %" if rdcf.get("rd_cagr_ref") is not None else "–", "source": src})
        if rdcf.get("rd_wacc") is not None:
            rows.append({"what": "Avkastningskrav (WACC)", "market": f"{rdcf['rd_wacc'] * 100:.1f} %", "mine": f"{rdcf['rd_wacc_ours'] * 100:.1f} %" if rdcf.get("rd_wacc_ours") is not None else "–", "today": "–", "source": src})
        if rdcf.get("dcf") is not None and px:
            rows.append({"what": "DCF-verdi mot kurs", "market": f"{px:.2f}", "mine": f"{rdcf['dcf']:.1f} ({(rdcf['dcf'] / px - 1) * 100:+.0f} %)", "today": f"TP {rdcf.get('tp')}", "source": src})
    if lc:
        rv = lc.get("reverse") or {}
        src = f"lett case ({str(lc.get('built_at', ''))[:10]}; WACC EST {rv.get('wacc_est', 0) * 100:.0f} %)"
        if rv.get("implied_g") is not None:
            rows.append({"what": "Evig vekst som forklarer kursen", "market": f"{rv['implied_g'] * 100:+.1f} %/år", "mine": "–", "today": f"ROIC {rv['roic'] * 100:.0f} %" if rv.get("roic") is not None else "–", "source": src})
        if rv.get("ev_vs_no_growth") is not None:
            rows.append({"what": "EV mot null-vekst-verdi", "market": f"{rv['ev_vs_no_growth'] * 100:+.0f} %", "mine": "–", "today": "–", "source": src})
    if v.get("target") and px:
        rows.append({"what": "Kursmål mot kurs", "market": f"{px:.2f}", "mine": f"{float(v['target']):g} ({(float(v['target']) / px - 1) * 100:+.0f} %)", "today": f"{v.get('rating')}", "source": f"din vurdering {v.get('date')}"})
    return rows


def events_before_horizon(c: bk.Case | None, code: str, today: pd.Timestamp, months: int) -> list[dict]:
    from osloquant.dashboard import calendar as cal

    days = int(months * 30.5)
    evs = cal.events([c] if c else [], today=today, days=days)
    return [e for e in evs if e.get("code") == code or e.get("kind") == "rates"]


def position(code: str, px: float | None, view: dict, group: str | None, cases) -> dict:
    from osloquant.dashboard import odds as od
    from osloquant.dashboard import portfolio as pf
    from osloquant.dashboard import sizing

    cfg = sizing.config()
    kill, why = od.kill_level(view)
    out = {"cfg": cfg, "kill": kill, "kill_source": why, "size": None, "error": None}
    if cfg and px and kill and kill < px:
        try:
            groups = bk._groups()
            out["size"] = sizing.size(px, kill, cfg, code, group=group, groups=groups)
        except ValueError as e:
            out["error"] = str(e)
    elif cfg and px and kill and kill >= px:
        out["error"] = f"kill-nivået {kill:g} ligger over kursen {px:.2f} – ingen størrelse for et kjøp"
    ex = pf.exposure(cases, {c.code: group if c.code == code else bk._groups().get(c.code, "Other") for c in cases}, cfg) if cases else None
    out["exposure"] = ex
    out["group"] = group
    out["same_group"] = (ex or {}).get("groups", {}).get(group) if ex and group else None
    return out


def context(code: str) -> dict:
    """Everything the page shows. Reads only."""
    from osloquant.dashboard import lightcase as lcm
    from osloquant.dashboard import reports as rp
    from osloquant.dashboard import today as td
    from osloquant.dashboard.casefile import reverse_dcf

    snap = mk.snapshot()
    code = code.upper().removesuffix(".OL")
    c = bk.case(code)
    cases = bk.cases()
    lp = mk.last_price(snap, code)
    px = lp[0] if lp else None
    today = pd.Timestamp.now().normalize()
    v = (c.view if c else None) or {}
    months = int(v.get("horizon_months") or 12)
    lc = lcm.load(code)
    rdcf = reverse_dcf(c.model) if c and c.model else None
    alerts, _ = td.signals_since(snap, None, max_sessions=10)
    alerts = [a for a in alerts if a.code == code]
    s = rp.latest(code) if c else None
    rep = {"summary": s} if s else None
    case_odds = None
    if c and v.get("target") and px:
        from osloquant.dashboard import odds as od

        kill, why = od.kill_level(v)
        if kill:
            case_odds = od.case_odds(code, float(v["target"]), kill, why)
    st = sg.status(snap.panel, code)
    chg20 = st.get("chg_20d")
    return {"code": code, "name": snap.names.get(code, c.name if c else code), "case": c, "price": px, "price_label": mk.price_label(lp[1]) if lp else "",
            "today": today, "months": months, "implied": implied(c, lc, rdcf, px), "odds": case_odds,
            "against": arguments_against(c, lc, rep, alerts, px), "events": events_before_horizon(c, code, today, months),
            "position": position(code, px, v, snap.group(code), cases), "report": s, "lightcase": lc, "chg20": chg20,
            "checklist": CHECKLIST}


# ------------------------------------------------------------------------------------------------ html
def page_html(ctx: dict) -> str:
    from osloquant.dashboard.render import E, cls, page, pct

    code, c, px = ctx["code"], ctx["case"], ctx["price"]
    v = (c.view if c else None) or {}
    if not px:
        return page(f"Før du kjøper – {code}", "", f'<h1>{E(code)}</h1><p class="err">Ingen kurs for {E(code)} i lageret.</p>')
    head = (f'<div class="src">{E(code)} · {E(ctx["price_label"])}</div><h1>Før du kjøper <span class="code">{E(ctx["name"])}</span></h1>'
            f'<div class="sub">Kurs {px:.2f}. Horisont {ctx["months"]} måneder. Alt under er tall fra kildene som står ved hvert punkt – ingenting er skrevet for anledningen. '
            f'Skjemaet åpnes nederst når sjekklisten er krysset av.</div>')
    # 1 implied
    irows = "".join(f'<tr><td>{E(r["what"])}</td><td>{E(r["market"])}</td><td>{E(r["mine"])}</td><td>{E(r["today"])}</td><td class="src">{E(r["source"])}</td></tr>' for r in ctx["implied"])
    implied_html = ('<h2>1. Hva markedet priser inn – mot mitt syn</h2><div class="card>' if False else '<h2>1. Hva markedet priser inn – mot mitt syn</h2><div class="card">'
                    + (f'<table class="odds"><thead><tr><th>Størrelse</th><th>Markedet (kursen)</th><th>Mitt syn</th><th>I dag / referanse</th><th>Kilde</th></tr></thead><tbody>{irows}</tbody></table>'
                       if irows else '<p class="empty">Ingen modell knyttet til casen og ingen lett case: koble regnearket i research book (model: xlsx/map) eller bygg en lett case (oq case build).</p>')
                    + '<div class="src">Reverse DCF: den verdien av én driver som gir dagens kurs med de andre på mitt base-case. Lett case: evig vekst som forklarer EV med WACC EST.</div></div>')
    # 2 odds
    o = ctx["odds"]
    if o and not o.note:
        rows = []
        for lab, _ in (("3 mnd", 63), ("6 mnd", 126), ("12 mnd", 252)):
            sim, uni, own = o.simulation.get(lab), o.universe.get(lab), o.own.get(lab)
            cell = lambda x: f'{pct(x.target, 0, False)} / {pct(x.kill, 0, False)} / {pct(x.neither, 0, False)}' + (f' <span class="src">n {x.n}</span>' if getattr(x, "n", None) else "") if x and x.target == x.target else "–"  # noqa: E731
            rows.append(f'<tr><td>{lab}</td><td>{cell(sim)}</td><td>{cell(uni)}</td><td>{cell(own)}</td></tr>')
        r_, be = __import__("osloquant.dashboard.odds", fromlist=["breakeven"]).breakeven(o.price, o.target, o.kill)
        odds_html = ('<h2>2. Utfallsodds: kursmål først, kill-nivå først eller ingen av dem</h2><div class="card">'
                     f'<p>Kursmål {o.target:g} ({pct(o.target / o.price - 1, 0)}), kill-nivå {o.kill:g} ({pct(o.kill / o.price - 1, 0)}; {E(o.kill_source)}). '
                     f'Reward/risk {r_:.2f} – kursmålet må nås først i minst {pct(be, 0, False)} av de avgjorte tilfellene for å gå i null.</p>'
                     '<table class="odds"><thead><tr><th>Horisont</th><th>Simulering (blokk-bootstrap av egen historikk)</th><th>Alle aksjer i lageret, like nivåer</th><th>Egen historikk</th></tr></thead>'
                     f'<tbody>{"".join(rows)}</tbody></table><div class="src">Hver celle: kursmål først / kill først / ingen av dem. Kilde: lagerets daglige sluttkurser siden 2010 (Yahoo, forsinket), '
                     f'odds.py, per {o.asof:%Y-%m-%d}. Simuleringen bruker aksjens egen volatilitet; analogiene bruker samme prosentavstander. Ikke en prognose – et grunnlag.</div></div>')
    else:
        why = o.note if o else ("ingen vurdering med kursmål og kill-nivå – oddsene regnes når skjemaet har begge" if not v.get("target") else "ingen kill-nivå eller bear-verdi i vurderingen")
        odds_html = f'<h2>2. Utfallsodds</h2><div class="card"><p class="empty">{E(why)}.</p></div>'
    # 3 bull/bear + against
    bb = ""
    if v:
        bb = ('<table class="odds"><thead><tr><th></th><th>Verdi</th><th>Fra kursen</th><th>Sannsynlighet</th></tr></thead><tbody>'
              + "".join(f'<tr><td>{lab}</td><td>{float(v[k]):g}</td><td class="{cls(float(v[k]) / px - 1)}">{pct(float(v[k]) / px - 1, 0)}</td><td>{v.get("p_" + k) if v.get("p_" + k) is not None else "–"}</td></tr>'
                        for lab, k in (("Bear", "bear"), ("Base", "base"), ("Bull", "bull")) if v.get(k) is not None)
              + f'</tbody></table><div class="src">Din vurdering {E(str(v.get("date")))} ({E(str(c.view_source))}).'
              + (f' Begrunnelsen: «{E(str(v.get("thesis"))[:400])}»' if v.get("thesis") else " Ingen begrunnelse på raden (synkronisert fra research book).") + '</div>')
    else:
        bb = '<p class="empty">Ingen vurdering logget: bull og bear settes i skjemaet.</p>'
    ag = ctx["against"]
    ag_html = ("<ol>" + "".join(f'<li>{E(a["text"])} <span class="src">({E(a["source"])})</span></li>' for a in ag[:MAX_ARGS]) + "</ol>"
               + (f'<details><summary>{len(ag) - MAX_ARGS} til</summary><ul>' + "".join(f'<li>{E(a["text"])} <span class="src">({E(a["source"])})</span></li>' for a in ag[MAX_ARGS:]) + '</ul></details>' if len(ag) > MAX_ARGS else "")
               if ag else '<p class="empty">Ingen motargument funnet i kildene: ingen rapportlesing med kill-regel, ingen lett case, ingen risikosignal, ingen bear-verdi. Det er i seg selv et varsel.</p>')
    case_html = (f'<h2>3. Bull og bear – og de sterkeste argumentene mot kjøp</h2><div class="grid2"><div><h3>Scenarioene i vurderingen</h3>{bb}</div>'
                 f'<div><h3>Mot kjøp (sitert fra kildene)</h3>{ag_html}</div></div>')
    # 4 events
    ev = ctx["events"]
    ev_html = ("<ul class='news'>" + "".join(f'<li><b>{e["date"]:%d %b %Y}</b> ({(e["date"] - ctx["today"]).days} d) {E(e["name"])} – {E(e["what"])} <span class="src">({E(e["source"])})</span></li>' for e in ev) + "</ul>"
               if ev else '<p class="empty">Ingen datert hendelse i kalenderen før horisonten – sjekk selskapets finanskalender (oq dashboard --refresh).</p>')
    ev_html = f'<h2>4. Hendelser før horisonten ({ctx["months"]} mnd)</h2><div class="card">{ev_html}<div class="src">Research book, finanskalendere på NewsWeb, Norges Banks møtekalender.</div></div>'
    # 5 position
    p = ctx["position"]
    if not p["cfg"]:
        pos_html = '<p class="empty">Ingen grenser i dashboard.yaml (sizing: paper_capital, max_loss, max_position).</p>'
    elif p["size"]:
        s = p["size"]
        lim = ", ".join(f"{k}: {n}" for k, n in s.limits.items())
        pos_html = (f'<p>Kill-nivå {p["kill"]:g} ({E(p["kill_source"])}). Største tillatte posisjon: <b>{s.shares} aksjer</b> = NOK {s.value:,.0f} '
                    f'({s.value / float(p["cfg"]["paper_capital"]) * 100:.1f} % av papirsummen), tap hvis kill-nivået nås: <b>NOK {s.loss_at_kill:,.0f}</b> '
                    f'(grensen NOK {float(p["cfg"]["max_loss"]):,.0f}; bindende: {E(s.binding)}).</p><div class="src">Grenser i aksjer: {E(lim)}. Fritt av papirsummen: NOK {s.free:,.0f}; '
                    f'tap ved kill-nivå i åpne BUY-syn: NOK {s.open_loss:,.0f}. Tap per aksje = kurs − kill-nivå + kostnad tur-retur.</div>').replace(",", " ")
    else:
        pos_html = f'<p class="empty">{E(p["error"] or "Ingen kill-nivå i vurderingen – størrelsen regnes i skjemaet når du setter et.")}</p>'
    ex = p.get("exposure") or {}
    sg_ = p.get("same_group")
    grp_html = (f'<p>Sektorgruppe <b>{E(p["group"] or "–")}</b>: {len(sg_["cases"])} åpne BUY-syn fra før ({", ".join(sg_["cases"])}), tap ved kill-nivåene NOK {sg_["loss"]:,.0f}'
                + (f' = {sg_["share"] * 100:.1f} % av papirsummen' if sg_.get("share") is not None else "") + '.</p>' if sg_ else
                f'<p>Sektorgruppe <b>{E(p["group"] or "–")}</b>: ingen åpne BUY-syn i samme gruppe.</p>').replace(",", " ")
    if ex:
        grp_html += (f'<div class="src">Alle åpne BUY-syn: {ex.get("views", 0)}, samlet tap ved kill-nivåene NOK {ex.get("total_loss_at_kill", 0):,.0f}'
                     + (f' ({ex["total_loss_share"] * 100:.1f} % av papirsummen)' if ex.get("total_loss_share") is not None else "")
                     + (". Delt driver mellom åpne syn: " + ", ".join(d + " (" + ", ".join(cs) + ")" for d, cs in ex["shared_drivers"].items()) if ex.get("shared_drivers") else "")
                     + '. Kilde: vurderingsloggen (posisjoner på BUY-rader) og dashboard.yaml; papirkontoene i live.yaml er egne strategier og telles ikke her.</div>').replace(",", " ")
    pos_html = f'<h2>5. Posisjonsstørrelse ved maks tap – og hva som ligger i samme sektor</h2><div class="card">{pos_html}{grp_html}</div>'
    # 6 checklist
    rep = ctx.get("report")
    rep_note = f' (siste lest: Q{rep.get("quarter")} {rep.get("year")}, {str(rep.get("published", ""))[:10]})' if rep else ""
    chg = ctx.get("chg20")
    chg_note = f' (kursen er {pct(chg)} siste 20 økter)' if chg is not None else ""
    boxes = "".join(f'<label style="display:block;margin:6px 0;font-weight:500"><input type="checkbox" class="pt" data-key="{k}" style="width:auto;margin-right:8px">{E(t)}'
                    + (E(rep_note) if k == "read_report" else "") + (E(chg_note) if k == "new_argument" else "") + '</label>' for k, t in ctx["checklist"])
    check_html = (f'<h2>6. Sjekkliste før skjemaet</h2><div class="card decide">{boxes}'
                  f'<p><a id="go" class="chip plain" href="#" aria-disabled="true" style="pointer-events:none;opacity:.5;padding:8px 16px;font-size:13px">Kryss av alt over for å åpne skjemaet</a></p>'
                  '<div class="src">Avkryssingen skrives på raden i vurderingsloggen (feltet checklist), så kalibreringen senere kan se om de uten sjekkliste gikk dårligere.</div></div>'
                  f"""<script>(function(){{var bs=[].slice.call(document.querySelectorAll('input.pt')),a=document.getElementById('go');
function u(){{var ok=bs.every(function(b){{return b.checked}});var keys=bs.filter(function(b){{return b.checked}}).map(function(b){{return b.dataset.key}}).join(',');
a.href='/stock/{code}?checklist='+keys+'#judge';a.style.pointerEvents=ok?'auto':'none';a.style.opacity=ok?1:.5;a.className=ok?'chip buy':'chip plain';
a.textContent=ok?'Åpne vurderingsskjemaet for {code} →':'Kryss av alt over for å åpne skjemaet';}}bs.forEach(function(b){{b.addEventListener('change',u)}});u();}})();</script>""")
    return page(f"Før du kjøper – {code}", "", "\n".join([head, implied_html, odds_html, case_html, ev_html, pos_html, check_html]))
