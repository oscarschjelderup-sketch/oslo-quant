"""The stock page (D57): a sticky top bar, seven tabs with the active one in the URL, and every block the page had
before placed in one of them (docs/design/aksjeside-inventar.md). Server-rendered: all panels are in the HTML, the
inactive ones hidden; a small script switches tabs, moves the chart's axes for the period buttons and filters the
news list. Every new number carries its source and time in a hover title; delayed prices say so; estimates say EST.
Nothing here labels buy, sell or neutral."""

from __future__ import annotations

import json
import re

import pandas as pd

from osloquant import signals as sg
from osloquant.dashboard import charts as ch
from osloquant.dashboard import render as rd
from osloquant.dashboard.dates import dato, periode
from osloquant.dashboard.render import E, _fact_rows, _nok, cls, pct, when

TABS = [("oversikt", "Oversikt"), ("regnskap", "Regnskap"), ("verdsettelse", "Verdsettelse"), ("teknisk", "Teknisk"),
        ("rapporter", "Rapporter"), ("eiere", "Eiere"), ("vurdering", "Min vurdering")]
SUBTABS = [("oversikt", "Oversikt"), ("resultat", "Resultat"), ("balanse", "Balanse"), ("kontantstrom", "Kontantstrøm"),
           ("segmenter", "Segmenter"), ("utbytte", "Utbytte")]
TAB_KEYS = {k for k, _ in TABS}
SUB_KEYS = {k for k, _ in SUBTABS}

#: the signal catalogue's kinds as words – a direction the odds were measured on, never a label to act on
KIND_NO = {sg.BUY: "opp", sg.RISK: "risiko", sg.INFO: "info"}

INCOME_LINES = [("total_revenue", "Omsetning"), ("cost_of_revenue", "Varekostnad"), ("gross_profit", "Bruttoresultat"), ("operating_income", "Driftsresultat"),
                ("ebitda", "EBITDA"), ("ebit", "EBIT"), ("interest_expense", "Rentekostnad"), ("pretax_income", "Resultat før skatt"), ("tax_provision", "Skatt"),
                ("net_income", "Resultat"), ("basic_eps", "EPS"), ("diluted_eps", "EPS utvannet"), ("diluted_shares", "Aksjer utvannet (m)")]
BALANCE_LINES = [("total_assets", "Sum eiendeler"), ("current_assets", "Omløpsmidler"), ("cash_and_equivalents", "Kontanter"), ("goodwill_and_intangibles", "Goodwill og immaterielle"),
                 ("total_liabilities", "Sum gjeld"), ("current_liabilities", "Kortsiktig gjeld"), ("total_debt", "Rentebærende gjeld"), ("net_debt", "Netto gjeld"),
                 ("total_equity", "Egenkapital"), ("minority_interest", "Minoriteter"), ("shares_outstanding", "Aksjer (m)")]
CASHFLOW_LINES = [("operating_cash_flow", "Kontantstrøm fra drift"), ("capital_expenditure", "Investeringer (capex)"), ("free_cash_flow", "Fri kontantstrøm"),
                  ("dividends_paid", "Utbytte betalt"), ("repurchase_of_stock", "Tilbakekjøp"), ("depreciation_and_amortization", "Av- og nedskrivninger")]
PER_SHARE = {"basic_eps", "diluted_eps"}
IN_MILLIONS_SHARES = {"diluted_shares", "shares_outstanding"}
WEBCAST = re.compile(r"(?i)webcast|presentation|presentasjon|invitation|invitasjon|kapitalmarked|capital markets")


# ------------------------------------------------------------------------------------------------ helpers
def nv(text: str, source: str, klass: str = "") -> str:
    """A number with its source and time in the hover title."""
    return f'<span class="nv{" " + klass if klass else ""}" title="{E(source)}">{text}</span>'


def _m(v, d: int = 0) -> str:
    return "–" if v is None or v != v else f"{v / 1e6:,.{d}f}".replace(",", " ")


def _f(v, d: int = 2) -> str:
    return "–" if v is None or v != v else f"{v:,.{d}f}".replace(",", " ")


def _x(v, d: int = 1) -> str:
    return "–" if v is None or v != v else f"{v:.{d}f}x"


def _plabel(rec: dict, period: str) -> str:
    d = pd.Timestamp(rec["report_date"])
    return f"{d.year}" if period == "year" else f"Q{(d.month - 1) // 3 + 1} {d.year}"


def live_multiples(lc: dict | None, px: float) -> dict:
    """Market value and the multiples at today's price from the light case's share count and LTM figures (the light
    case itself was built at an older price). Reporting currency where the statements are; sources on each."""
    if not lc or not lc.get("shares"):
        return {}
    shares = float(lc["shares"])
    cur = lc["currency"]["reporting"]
    fx = lc["currency"].get("fx")
    to_rep = 1.0 if cur == "NOK" else (1.0 / fx if fx else None)
    mcap_nok = px * shares
    mcap = mcap_nok * to_rep if to_rep else None
    pr, b = lc["profit"], lc["balance"]
    ni, rev = pr["net_income"]["value"], pr["revenue"]["value"]
    eq = (b.get("equity") or 0) - (b.get("minority") or 0) if b.get("equity") else None
    built = str(lc.get("built_at", ""))[:10]
    out = {"shares": shares, "cur": cur, "mcap_nok": mcap_nok, "built": built,
           "src_shares": f"aksjer fra Yahoo-balansen via lageret (lett case bygget {built})",
           "src_mcap": f"kurs {px:.2f} × {shares / 1e6:,.1f} m aksjer (Yahoo-balanse); lett case bygget {built}".replace(",", " ")}
    if mcap:
        out["pe"] = mcap / ni if ni and ni > 0 else None
        out["ps"] = mcap / rev if rev and rev > 0 else None
        out["pb"] = mcap / eq if eq and eq > 0 else None
        out["eps"] = ni / shares if ni is not None else None
        out["src_pe"] = f"børsverdi ved kurs {px:.2f} / resultat {periode(pr['net_income']['period'])} (Yahoo-regnskap via lageret)"
        out["src_ps"] = f"børsverdi ved kurs {px:.2f} / omsetning {periode(pr['revenue']['period'])} (Yahoo-regnskap via lageret)"
        out["src_pb"] = f"børsverdi ved kurs {px:.2f} / egenkapital minus minoriteter {periode(b.get('date'))} (Yahoo-balanse via lageret)"
        out["src_eps"] = f"resultat {periode(pr['net_income']['period'])} / aksjer (Yahoo via lageret), i {cur}"
    return out


def _dividends_12m(divs: list[dict], asof: pd.Timestamp) -> tuple[float, str | None]:
    cutoff = asof - pd.Timedelta(days=365)
    paid = [d for d in divs if d.get("dividend") and pd.Timestamp(d["date"]) > cutoff and pd.Timestamp(d["date"]) <= asof]
    total = sum(float(d["dividend"]) for d in paid)
    last = max((d["date"] for d in divs if d.get("dividend")), default=None)
    return total, last


# ------------------------------------------------------------------------------------------------ the bar and the tabs
def _period_buttons(periods: list[dict], with_returns: bool, active: str | None = None) -> str:
    if active is None:          # the chart opens on 1Å, or on Maks when the store has less than a year
        active = "1a" if any(p["key"] == "1a" and p.get("enough") for p in periods) else "maks"
    out = ['<div class="pers">', '<button type="button" class="per" disabled title="Lageret har bare daglige sluttkurser – ingen intradagkurve. Dagens åpning, høy og lav står i nøkkeltallene.">1D</button>']
    for p in periods:
        ret = (f'<small class="{cls(p["ret"])}">{pct(p["ret"])}</small>' if with_returns and p.get("enough") and p.get("ret") is not None else "")
        dis = "" if p.get("enough") else " disabled"
        title = (f'{p["label"]}: {p["sessions"]} økter fra {dato(p["x0"])} til {dato(p["x1"])} – avkastning {pct(p["ret"])} på sluttkurser (Yahoo via lageret, forsinket)'
                 + (" – aksjen er notert senere enn periodestart, så dette er fra første kurs i lageret" if p.get("from_listing") else "")
                 if p.get("enough") else f'for kort historikk i lageret for {p["label"]} (første kurs {dato(p["x0"])})')
        out.append(f'<button type="button" class="per{" on" if p["key"] == active else ""}" data-p="{p["key"]}" data-r=\'{json.dumps({k: p[k] for k in ("x0", "x1")})}\''
                   f' title="{E(title)}"{dis}>{E(p["label"])}{ret}</button>')
    out.append("</div>")
    return "".join(out)


def bar_html(code: str, ctx: dict) -> str:
    st, c = ctx["status"], ctx["case"]
    px = st["price"]
    chg = st.get("chg_1d")
    prev = px / (1 + chg) if chg is not None and chg != -1 else None
    nok = f"{px - prev:+.2f}" if prev is not None else "–"
    asof = dato(st.get("session")) if st.get("session") else ""
    src = ctx.get("price_label", "")
    v = (c.view if c else None) or {}
    view = ""
    if v.get("target"):
        tp = float(v["target"])
        up = tp / px - 1
        tp_src = f"ditt kursmål (EST), syn fra {dato(v.get('date'))} ({c.view_source})"
        view = (f'<div class="view">Mitt syn <b>{E(v.get("rating", "?"))}</b> · kursmål {nv(f"NOK {tp:g}", tp_src)} · '
                f'<span class="{cls(up)}">{pct(up, 0)}</span></div>')
    nxt = ctx.get("next_event")
    if nxt:
        nxt_src = f"{nxt['what']} – {nxt['source']}"
        nxt_txt = f"{dato(nxt['date'])}"
        nxt_html = f'<div class="view">Neste rapport <b>{nv(nxt_txt, nxt_src)}</b></div>'
    else:
        nxt_html = '<div class="view muted">Neste rapport: ikke i kalenderen</div>'
    kind = ctx.get("status_kind", "none")
    stat = {"book": ('<span class="stat">Research book</span>'), "watch": ('<span class="stat">Overvåkning</span>'),
            "none": ('<span class="stat none">Ikke fulgt</span>')}[kind]
    return (f'<div class="stockbar"><div class="who"><div class="nm">{E(ctx["name"])}<span class="tick">{E(code)}</span></div><div class="grp">{E(ctx["group"])} · {stat}</div></div>'
            f'<div><div class="px">{nv(f"{px:.2f}", f"siste sluttkurs {asof} – {src}")}<span class="chg {cls(chg)}"> {nok} ({pct(chg)})</span><span class="delayed" title="{E(src)}">forsinket</span></div>'
            f'<div class="asof">{E(f"sluttkurs {asof}")} · endring mot forrige sluttkurs</div></div>'
            f'{_period_buttons(ctx.get("periods") or [], with_returns=False)}'
            f'<div>{view}{nxt_html}</div></div>')


def tabs_html(code: str, active: str, badges: dict[str, int]) -> str:
    links = "".join(f'<a href="/aksje/{E(code)}/{k}" data-tab="{k}" class="{"on" if k == active else ""}">{E(label)}'
                    + (f'<span class="badge">{badges[k]}</span>' if badges.get(k) else "") + '</a>' for k, label in TABS)
    return f'<nav class="tabs" data-code="{E(code)}">{links}</nav>'


def _panel(key: str, active: str, body: str) -> str:
    return f'<section class="panel" data-tab="{key}" id="tab-{key}"{"" if key == active else " hidden"}>{body}</section>'


# ------------------------------------------------------------------------------------------------ 1 Oversikt
def _news_items(ctx: dict) -> list[dict]:
    """Announcements, headlines, insider notifications and short moves as one list with a kind on each."""
    items: list[dict] = []
    news = ctx.get("news") or {}
    for n in news.get("items", []):
        items.append({"time": n["time"], "title": n["title"], "url": n.get("url") or n.get("link", ""),
                      "kind": "borsmelding" if n.get("kind") == "børsmelding" else "nyheter", "label": "børsmelding" if n.get("kind") == "børsmelding" else str(n.get("kind") or "nyheter")})
    ins = ctx.get("insiders") or {}
    for i in ins.get("items", []):
        items.append({"time": i["time"], "title": i["title"], "url": i["url"], "kind": "innsidehandel", "label": f"innsidehandel · {rd.SIDE_NO.get(i['side'], i['side'])}"})
    s = ins.get("shorts")
    if s and s.get("series"):
        ser = sorted(s["series"])
        for (_d0, v0), (d1, v1) in zip(ser, ser[1:], strict=False):
            if abs(v1 - v0) >= 0.25:
                items.append({"time": f"{d1}T16:00:00Z", "title": f"Shortposisjonene {v0:.2f} % → {v1:.2f} % av aksjene", "url": "", "kind": "short", "label": "shortregisteret"})
    by_url: dict[str, dict] = {}
    out = []
    for it in items:
        if it["url"]:
            prev = by_url.get(it["url"])
            if prev:
                if it["kind"] == "innsidehandel" and prev["kind"] != "innsidehandel":
                    prev.update(it)
                continue
            by_url[it["url"]] = it
        out.append(it)
    return sorted(out, key=lambda a: a["time"], reverse=True)[:40]


def news_card(ctx: dict) -> str:
    items = _news_items(ctx)
    filt = ('<div class="filt"><button type="button" class="on" data-k="alle">Alle</button><button type="button" data-k="borsmelding">Børsmeldinger</button>'
            '<button type="button" data-k="innsidehandel">Innsidehandel</button><button type="button" data-k="short">Short</button><button type="button" data-k="nyheter">Nyheter</button></div>')
    if items:
        li = "".join(f'<li data-k="{it["kind"]}"><span class="src">{when(it["time"])}</span><span>'
                     + (f'<a href="{E(it["url"])}" target="_blank" rel="noopener">{E(it["title"])}</a>' if it["url"] else E(it["title"]))
                     + f'<span class="kind">{E(it["label"])}</span></span></li>' for it in items)
        body = f'<ul class="newsl">{li}</ul>'
    else:
        body = '<p class="empty">Ingen børsmelding i bufferen (14 dager), ingen overskrift som nevner selskapet, ingen innsidemelding og ingen shortendring.</p>'
    news = ctx.get("news") or {}
    src = (E(news.get("source", "ikke hentet – oq dashboard --refresh")) + '. Innsidehandler: NewsWeb-bufferen (meldepliktige). Short: Finanstilsynets register, endringer på 0,25 prosentpoeng eller mer.')
    return f'<div class="card"><h3>Meldinger og nyheter</h3>{filt}{body}<div class="src">{src}</div></div>'


def key_grid(ctx: dict) -> str:
    bar = ctx.get("bar") or {}
    st = ctx["status"]
    px = st["price"]
    lc = ctx.get("lightcase")
    lm = live_multiples(lc, px)
    bsrc = f'dagsbar {dato(bar.get("date", st.get("session")))} – {ctx.get("price_label", "")} (justert for utbytte og splitt)'
    tiles = [("Åpning", _f(bar.get("open")), bsrc), ("Høy", _f(bar.get("high")), bsrc), ("Lav", _f(bar.get("low")), bsrc),
             ("Volum", f"{bar['volume']:,.0f}".replace(",", " ") if bar.get("volume") else "–", bsrc),
             ("Omsetning (EST)", f"NOK {_m(bar['volume'] * px, 1)} m" if bar.get("volume") else "–", "≈ sluttkurs × volum (EST): lageret har ikke omsetning per dag")]
    if lm:
        tiles += [("Børsverdi", f"NOK {_nok(lm['mcap_nok'])} mrd", lm["src_mcap"]),
                  ("P/E (LTM)", _x(lm.get("pe")), lm.get("src_pe", "")), (f"EPS LTM ({lm['cur']})", _f(lm.get("eps")), lm.get("src_eps", ""))]
    else:
        tiles += [("Børsverdi", "–", "ingen lett case bygget (oq case build)"), ("P/E (LTM)", "–", "ingen lett case bygget"), ("EPS LTM", "–", "ingen lett case bygget")]
    last, nxt = ctx.get("last_report"), ctx.get("next_event")
    tiles.append(("Siste rapport", dato(last["date"]) if last else "–", f"{last['what']} – {last['source']}" if last else "ingen rapport funnet i kalenderen, leseren eller research book"))
    tiles.append(("Neste rapport", dato(nxt["date"]) if nxt else "–", f"{nxt['what']} – {nxt['source']}" if nxt else "ikke i kalenderen (NewsWeb finanskalender / research book)"))
    html = "".join(f'<div class="kt"><div class="kl">{E(k)}</div><div class="kvv">{nv(v, s)}</div></div>' for k, v, s in tiles)
    return f'<div class="card"><h3>Nøkkeltall i dag</h3><div class="kgrid">{html}</div><div class="src">Hold musen over et tall for kilde og tidspunkt. Kurser er daglige sluttkurser, forsinket.</div></div>'


def key_table(ctx: dict) -> str:
    st = ctx["status"]
    px = st["price"]
    lc = ctx.get("lightcase")
    lm = live_multiples(lc, px)
    closes: pd.Series | None = ctx.get("closes")
    rows = []
    if closes is not None and len(closes) > 1:
        c12 = closes.iloc[-250:]
        rows.append(("12 m lav / høy", nv(f"{float(c12.min()):.2f} / {float(c12.max()):.2f}", f"laveste og høyeste sluttkurs over {len(c12)} økter til {dato(c12.index[-1])} (Yahoo via lageret, justert, forsinket)")))
    divs = ctx.get("dividends") or []
    asof = pd.Timestamp(st.get("session"))
    total, last_ex = _dividends_12m(divs, asof)
    dsrc = "Yahoo Finance utbytter (StockAction) via lageret, per aksje i NOK, eks-datoer"
    rows.append(("Utbytte siste 12 m", nv(f"NOK {total:.2f}" if total else "–", dsrc)))
    rows.append(("Direkteavkastning", nv(pct(total / px, 1, False) if total else "–", f"utbytte siste 12 m / kurs {px:.2f}; {dsrc}")))
    rows.append(("Siste eks-dato", nv(dato(last_ex) if last_ex else "–", dsrc)))
    if lm:
        rows.append(("P/S (LTM)", nv(_x(lm.get("ps"), 2), lm.get("src_ps", ""))))
        rows.append(("P/B", nv(_x(lm.get("pb"), 2), lm.get("src_pb", ""))))
        r = (lc or {}).get("returns") or {}
        rows.append(("ROE", nv(pct(r.get("roe"), 0, False) if r.get("roe") is not None else "–", f"resultat LTM / egenkapital (Yahoo via lageret; lett case bygget {lm['built']})")))
        rows.append(("Antall aksjer", nv(f"{_m(lm['shares'], 1)} m", lm["src_shares"])))
    else:
        rows.append(("P/S, P/B, ROE, aksjer", '<span class="empty">ingen lett case bygget (oq case build)</span>'))
    return f'<div class="card"><h3>Nøkkeltall</h3>{_fact_rows(rows)}<div class="src">Hold musen over et tall for kilde og tidspunkt.</div></div>'


def overview_panel(code: str, ctx: dict) -> str:
    chart = ctx.get("long_chart") or ctx.get("chart", "")
    per = _period_buttons(ctx.get("periods") or [], with_returns=True)
    if 'id="pc-data"' in chart:
        from osloquant.dashboard import pricechart as pc

        note = ('Periodeknappene, zoom (hjul eller dra) og verktøylinjen virker på grafen. Avkastningen under hver knapp er sluttkurs mot sluttkurs, '
                'justert for utbytte og splitt; grafen er grønn når perioden er opp og rød når den er ned. 1D er slått av: lageret har bare dagskurser.' + pc.attribution_html())
    else:
        note = ('Periodeknappene flytter aksene i grafen over; avkastningen under hver knapp er '
                'sluttkurs mot sluttkurs, justert for utbytte og splitt. 1D er slått av: lageret har bare dagskurser.')
    chart_card = f'<div class="card">{chart}{per}<div class="src">{note}</div></div>'
    return chart_card + key_grid(ctx) + f'<div class="grid2">{news_card(ctx)}{key_table(ctx)}</div>'


# ------------------------------------------------------------------------------------------------ 2 Regnskap
def _stm_table(recs: list[dict], lines: list[tuple[str, str]], cur: str, period: str, n: int) -> str:
    recs = sorted(recs, key=lambda r: r["report_date"])[-n:]
    if not recs:
        return f'<p class="empty">Ingen {"års" if period == "year" else "kvartals"}tall i lageret.</p>'
    head = "".join(f'<th>{E(_plabel(r, period))}</th>' for r in recs)
    body = []
    for key, label in lines:
        if not any(r.get(key) is not None for r in recs):
            continue
        cells = []
        for r in recs:
            v = r.get(key)
            txt = "–" if v is None else (_f(v, 2) if key in PER_SHARE else _m(v, 1 if key in IN_MILLIONS_SHARES else 0))
            src = f"{label} {_plabel(r, period)}: Yahoo Finance via lageret, rapportdato {dato(r['report_date'])}"
            cells.append(f'<td>{nv(txt, src)}</td>')
        body.append(f'<tr><td>{E(label)}</td>{"".join(cells)}</tr>')
    unit = f"{cur} m; EPS i {cur}; aksjer i millioner"
    return (f'<table class="stm"><thead><tr><th>{E(unit)}</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>')


def _chart_rows(recs: list[dict], period: str, n: int) -> list[dict]:
    recs = sorted(recs, key=lambda r: r["report_date"])[-n:]
    return [{"label": _plabel(r, period), **r} for r in recs]


def _multiple_points(stm: dict, to_rep: float | None) -> list[dict]:
    pts = []
    bal = {b["report_date"]: b for b in stm["annual"].get("balance", [])}
    for r in sorted(stm["annual"].get("income", []), key=lambda r: r["report_date"]):
        pye = (stm.get("prices_ye") or {}).get(r["report_date"])
        shares = (bal.get(r["report_date"]) or {}).get("shares_outstanding") or r.get("diluted_shares")
        if not pye or not shares or to_rep is None:
            continue
        mcap = pye["close"] * shares * to_rep
        ni, rev = r.get("net_income"), r.get("total_revenue")
        pts.append({"label": _plabel(r, "year"), "pe": mcap / ni if ni and ni > 0 else None, "ps": mcap / rev if rev and rev > 0 else None})
    return pts


def capital_box(lc: dict | None) -> str:
    if not lc:
        return ""
    m, b, pr = lc["multiples"], lc["balance"], lc["profit"]
    cur = lc["currency"]["reporting"]
    built = str(lc.get("built_at", ""))[:10]
    s = f"lett case bygget {dato(built)} ved kurs {lc['price']['value']:.2f} ({dato(lc['price']['date'])}); Yahoo-regnskap via lageret"
    rows = [("Markedsverdi (NOK mrd)", nv(_nok(lc.get("mcap_nok")), s)), ("Aksjer (m)", nv(_nok(lc.get("shares"), 1e6, 1), s)),
            (f"Netto gjeld ({cur} m)", nv(_nok(b.get("net_debt"), 1e6, 0), f"balanse {periode(b.get('date'))}; {s}")),
            (f"EV ({cur} m)", nv(_nok(m.get("ev"), 1e6, 0), s) if m.get("ev") else None),
            ("EV/EBIT (LTM)", nv(_x(m.get("ev_ebit")), f"EBIT {periode(pr['ebit']['period'])}; {s}") if m.get("ev_ebit") else None),
            ("P/E (LTM)", nv(_x(m.get("pe")), s) if m.get("pe") else None), ("P/B", nv(_x(m.get("pb"), 2), s) if m.get("pb") else None),
            ("FCF-yield", nv(pct(m.get("fcf_yield"), 1, False), s) if m.get("fcf_yield") is not None else None),
            ("Rapporteringsvaluta", E(cur) + (f' · {E(cur)}NOK {lc["currency"]["fx"]:.3f}' if lc["currency"].get("fx") and cur != "NOK" else ""))]
    return (f'<div class="card"><h3>Kapitalstruktur</h3>{_fact_rows(rows)}'
            f'<div class="src">Yahoo-regnskap via lageret, kvartaler til {dato(lc.get("quarters_through"))}; LTM = {periode(pr["ebit"]["period"])}. Multiplene her er ved lett-casens kurs; Oversikt regner dem på dagens.</div></div>')


def accounts_panel(code: str, ctx: dict, sub: str) -> str:
    lc = ctx.get("lightcase")
    stm = ctx.get("statements")
    px = ctx["status"]["price"]
    cur = (stm or lc or {}).get("currency", {}).get("reporting", "NOK") if (stm or lc) else "NOK"
    nav = '<div class="subtabs">' + "".join(f'<a href="/aksje/{E(code)}/regnskap/{k}" data-sub="{k}" class="{"on" if k == sub else ""}">{E(label)}</a>' for k, label in SUBTABS) + '</div>'
    panels = []
    # Oversikt: the key-figure table, the capital structure, the charts
    charts = ""
    if stm:
        fx = stm["currency"].get("fx")
        to_rep = 1.0 if cur == "NOK" else (1.0 / fx if fx else None)
        inc_y, inc_q = stm["annual"].get("income", []), stm["quarterly"].get("income", [])
        ry, rq = _chart_rows(inc_y, "year", 8), _chart_rows(inc_q, "quarter", 12)
        tog = ('<div class="pertog"><button type="button" class="on" data-per="year">År</button><button type="button" data-per="quarter">Kvartal</button></div>')
        rev = (f'<div class="pv" data-per="year">{ch.revenue_result_chart(ry, cur, "year")}{ch.margins_chart(ry, "year")}</div>'
               f'<div class="pv" data-per="quarter" hidden>{ch.revenue_result_chart(rq, cur, "quarter")}{ch.margins_chart(rq, "quarter")}</div>')
        wf = ch.waterfall_chart(ry[-1], cur) if ry else ""
        mh = ch.multiples_history_chart(_multiple_points(stm, to_rep))
        charts = (f'<div class="card"><h3>Omsetning, resultat og marginer</h3>{tog}{rev}<div class="src">Yahoo Finance års- og kvartalsregnskap via lageret, eksportert {dato(stm["exported_at"][:10])}; {E(cur)} m. Kvartaler er som rapportert (ikke LTM).</div></div>'
                  + (f'<div class="grid2f"><div class="card">{wf}<div class="src">Linjene Yahoo gir; en linje som mangler hoppes over.</div></div>'
                     f'<div class="card">{mh or "<p class=empty>For få årsslutt med kurs og aksjetall til en multippelhistorikk.</p>"}<div class="src">Egen historikk, ikke estimater: kurs ved årsslutt fra lageret, aksjer fra balansen (EST der balansen mangler og utvannede aksjer brukes).</div></div></div>'))
    else:
        charts = '<div class="card"><p class="empty">Ingen regnskap i lageret for selskapet (oq record --finance).</p></div>'
    kf = rd.key_figures(lc, px)
    kf = kf.replace("<h2>Nøkkeltall</h2>", '<div class="card"><h3>Nøkkeltall per år</h3>', 1) + "</div>" if kf else '<div class="card"><p class="empty">Ingen lett case bygget – nøkkeltalltabellen krever oq case build.</p></div>'
    panels.append(("oversikt", kf + capital_box(lc) + charts))
    for key, lines, which in (("resultat", INCOME_LINES, "income"), ("balanse", BALANCE_LINES, "balance"), ("kontantstrom", CASHFLOW_LINES, "cashflow")):
        if stm:
            body = (f'<div class="card"><h3>Per år</h3>{_stm_table(stm["annual"].get(which, []), lines, cur, "year", 6)}</div>'
                    f'<div class="card"><h3>Per kvartal</h3>{_stm_table(stm["quarterly"].get(which, []), lines, cur, "quarter", 8)}</div>'
                    f'<div class="src">Yahoo Finance via lageret ({E(stm["source"])}), eksportert {dato(stm["exported_at"][:10])}. Som rapportert; Yahoo omgrupperer enkelte linjer.</div>')
        else:
            body = '<div class="card"><p class="empty">Ingen regnskap i lageret for selskapet.</p></div>'
        panels.append((key, body))
    panels.append(("segmenter", '<div class="card"><h3>Segmenter</h3><p class="empty">Ikke tilgjengelig: Yahoo gir ingen segmenttall, så lageret har dem ikke. '
                                'For fulle caser står segmentene i Toolkit-modellen og i rapporten under Rapporter.</p></div>'))
    panels.append(("utbytte", dividends_card(ctx)))
    html = "".join(f'<div class="subpanel" data-sub="{k}"{"" if k == sub else " hidden"}>{b}</div>' for k, b in panels)
    return nav + html


def dividends_card(ctx: dict) -> str:
    divs = [d for d in (ctx.get("dividends") or []) if d.get("dividend")]
    closes: pd.Series | None = ctx.get("closes")
    if not divs:
        return '<div class="card"><h3>Utbytte</h3><p class="empty">Ingen utbytter i lageret for selskapet (Yahoo Finance, StockAction) – enten betaler det ikke utbytte, eller oq record har ikke hentet dem.</p></div>'
    rows = []
    for d in sorted(divs, key=lambda d: d["date"], reverse=True)[:24]:
        ex = pd.Timestamp(d["date"])
        before = closes[closes.index < ex] if closes is not None else None
        pb = float(before.iloc[-1]) if before is not None and len(before) else None
        y = d["dividend"] / pb if pb else None
        dsrc = f"utbytte per aksje, eks-dato {d['date']} (Yahoo Finance via lageret)"
        pcell = nv(_f(pb), "siste sluttkurs før eks-dato (justert, forsinket)") if pb else "–"
        dtxt = f"{d['dividend']:.2f}"
        rows.append(f'<tr><td>{dato(d["date"])}</td><td>{nv(dtxt, dsrc)}</td>'
                    f'<td>{pcell}</td><td>{pct(y, 1, False) if y else "–"}</td></tr>')
    by_year: dict[int, float] = {}
    for d in divs:
        by_year[pd.Timestamp(d["date"]).year] = by_year.get(pd.Timestamp(d["date"]).year, 0) + float(d["dividend"])
    yr = "".join(f'<tr><td>{y}</td><td>{nv(f"{v:.2f}", f"sum utbytte per aksje med eks-dato i {y} (Yahoo Finance via lageret)")}</td></tr>' for y, v in sorted(by_year.items(), reverse=True)[:10])
    return (f'<div class="grid2"><div class="card"><h3>Utbytte per eks-dato</h3><table class="odds"><thead><tr><th>Eks-dato</th><th>NOK/aksje</th><th>Kurs før</th><th>Yield</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="card"><h3>Per år</h3><table class="odds"><thead><tr><th>År</th><th>NOK/aksje</th></tr></thead><tbody>{yr}</tbody></table>'
            '<div class="src">Yahoo Finance utbytter via lageret (eks-datoer; beløp i NOK per aksje). Ingen prognose: bare det som er betalt. Oversikt regner direkteavkastning av de siste 12 månedene.</div></div></div>')


# ------------------------------------------------------------------------------------------------ 3 Verdsettelse
def valuation_panel(code: str, ctx: dict) -> str:
    c, lc = ctx["case"], ctx.get("lightcase")
    v = (c.view if c else None) or {}
    cone = ctx.get("chart", "")
    note = ('Kjeglen går fra siste sluttkurs til synets bear, kursmål og bull ved horisonten (EST, ditt syn). Konsensus vises bare når den er logget for hånd på raden.'
            if v.get("target") else 'Ingen kjegle: ingen vurdering med kursmål er logget for selskapet. Skriv den under Min vurdering.')
    if v.get("consensus_target"):
        csrc = f"logget for hånd {dato(v.get('date'))}; kilde: {v.get('consensus_source')}"
        ctxt = f"NOK {float(v['consensus_target']):g}"
        cons = (f'<p>Analytikerkonsensus (manuell): <b>{nv(ctxt, csrc)}</b> '
                f'<span class="src">kilde {E(str(v.get("consensus_source") or ""))}, logget {dato(v.get("date"))} – merket manuell</span></p>')
    else:
        cons = '<p class="empty">Analytikerkonsensus: ikke tilgjengelig gratis (Finwire, Pinpoint). Et konsensusmål kan logges manuelt med kilde og dato i vurderingsskjemaet og vises da her, merket manuell.</p>'
    parts = [f'<div class="card">{cone}<div class="src">{note}</div>{cons}</div>']
    if c:
        parts.append('<h2>Hva prisen krever (modellen)</h2>' + rd.case_rdcf_card(c, ctx.get("rdcf")))
    else:
        parts.append('<h2>Hva prisen krever (modellen)</h2><div class="card"><p class="empty">Ingen Toolkit-modell koblet: reverse DCF krever et case i research book med model: {xlsx, map}. Lett-casens lesning står under.</p></div>')
    parts.append(ctx.get("inversion_html", ""))
    parts.append('<div class="card"><h3>Sum-of-the-parts</h3><p class="empty">Ikke i dashbordet: en SOTP finnes bare i Toolkit-modellen for de fulle casene (Rapporter → Mine rapporter). Lageret har ingen segmenttall å bygge den av.</p></div>')
    parts.append(rd.lightcase_block(lc) or '<div class="card"><p class="empty">Ingen lett case bygget (oq case build): multipler mot gruppen og «hva prisen krever» mangler.</p></div>')
    return "".join(parts)


# ------------------------------------------------------------------------------------------------ 4 Teknisk
def technical_panel(code: str, ctx: dict) -> str:
    st = ctx["status"]
    rows = ctx.get("technicals") or []
    odds_doc = rd._odds()
    meas = odds_doc.get("measured") or {}
    cost = meas.get("round_trip_cost", 0.005)
    tr = []
    for r in rows:
        o = r.odds or {}
        if r.signal and o.get("n"):
            sigcell = (f'{E(r.signal)}' + (' <span class="src">(utløst nå)</span>' if r.active else ' <span class="src">(ikke utløst)</span>'))
            osrc = f"meravkastning mot likevektet univers 20 og 60 økter etter {cost * 100:.1f} % rundtur; signal_odds.yaml målt {meas.get('from')}–{meas.get('to')}"
            oval = f"{pct(o.get('exc20'))} / {pct(o.get('exc60'))}"
            odds = (f'<td>{nv(oval, osrc)}</td>'
                    f'<td>{pct(o.get("hit20"), 0, False)}</td><td>{rd._int(o["n"])}</td><td>{E(str(o.get("grade60") or "–"))}</td>')
        else:
            sigcell = '<span class="src">ingen målt odds</span>'
            odds = '<td>–</td><td>–</td><td>–</td><td>–</td>'
        vsrc = f"regnet fra lagerets daglige kurser til {st.get('session')} (Yahoo Finance, forsinket)"
        tr.append(f'<tr><td>{E(r.label)}</td><td>{nv(E(r.value), vsrc)}</td>'
                  f'<td style="white-space:normal;text-align:left">{E(r.detail)}</td><td style="white-space:normal;text-align:left">{sigcell}</td>{odds}</tr>')
    table = ('<table class="odds"><thead><tr><th>Indikator</th><th>Verdi</th><th>Detalj</th><th>Målt signal</th><th>Meravkastning 20 / 60 økter</th><th>Treff 20</th><th>Tilfeller</th><th>Grad</th></tr></thead>'
             f'<tbody>{"".join(tr) or "<tr><td colspan=8 class=empty>for kort historikk</td></tr>"}</tbody></table>')
    src = (f'<div class="src">Regnet fra lagerets daglige kurser (Yahoo Finance via lageret, forsinket), sist {dato(st.get("session"))}. Odds: signal_odds.yaml, målt {dato(meas.get("from"))}–{dato(meas.get("to"))} '
           f'på {meas.get("stocks", "?")} aksjer som meravkastning mot det likevektede universet etter {cost * 100:.1f} % rundtur; grad A–D er stabilitetssjekkene (D20, D23). '
           'Ingen kjøp-, selg- eller nøytralmerkelapper: en indikator uten målt signal får ingen odds.</div>')
    sig = "".join(f'<div class="alert"><b>{E(KIND_NO.get(a.kind, a.kind))}</b><span><b>{E(a.signal)}</b> · {dato(a.session)}</span><span class="chip {rd.chip_class(a)} odds">'
                  f'{pct(a.exc20)} / {pct(a.exc60)} · treff {pct(a.hit20, 0, False)}{rd._n(a)}</span><span class="d">{E(a.detail)}{rd.bracket_line(a.signal)}</span></div>'
                  for a in ctx["alerts"]) or '<p class="empty">Ingen signal fra katalogen de siste 10 øktene.</p>'
    return (f'<div class="card"><h3>Indikatorer</h3>{table}{src}</div>'
            f'<h2>Signaler siste 10 økter</h2><div class="card">{sig}<div class="src">Signalkatalogens egne navn (engelsk). «opp» og «risiko» er retningen oddsene er målt på, ikke et råd; fargen følger graden og fortegnet på meravkastningen (D23).</div></div>')


# ------------------------------------------------------------------------------------------------ 5 Rapporter
def reports_panel(code: str, ctx: dict) -> str:
    last, nxt = ctx.get("last_report"), ctx.get("next_event")
    today = ctx.get("today")
    ev = []
    ev.append(("Siste rapport", nv(dato(last["date"]), f"{last['what']} – {last['source']}") + f' <span class="src">{E(last["what"])} ({E(last["source"])})</span>' if last else '<span class="empty">ingen funnet</span>'))
    if nxt:
        days = f' ({(nxt["date"] - today).days} d)' if today is not None else ""
        ev.append(("Neste hendelse", nv(f"{dato(nxt['date'])}", f"{nxt['what']} – {nxt['source']}") + f'{days} <span class="src">{E(nxt["what"])} ({E(nxt["source"])})</span>'))
    else:
        ev.append(("Neste hendelse", '<span class="empty">ikke i kalenderen</span>'))
    events = f'<div class="card"><h3>Siste og neste rapport</h3>{_fact_rows(ev)}<div class="src">Kilder: NewsWeb-finanskalenderen, rapportleseren og research book.</div></div>'
    nw = ctx.get("newsweb_reports") or []
    if nw:
        def pdf_link(r: dict) -> str:
            return f'<a href="{E(r["pdf"])}">PDF</a>' if r.get("pdf") else "–"

        rows = "".join(f'<tr><td>{dato(r["date"])}</td><td style="white-space:normal;text-align:left"><a href="{E(r["url"])}" target="_blank" rel="noopener">{E(r["title"])}</a></td>'
                       f'<td>{pdf_link(r)}</td></tr>' for r in nw)
        nwh = f'<table class="odds"><thead><tr><th>Publisert</th><th>Melding</th><th></th></tr></thead><tbody>{rows}</tbody></table>'
    else:
        nwh = '<p class="empty">Ingen rapporter lastet ned ennå. oq dashboard --refresh leser nye rapporter fra NewsWeb for selskaper i ~/osloquant-home/reports.yaml.</p>'
    wc = [a for a in (ctx.get("company_announcements") or []) if WEBCAST.search(a.get("title", ""))]
    wch = ("<ul class='news'>" + "".join(f'<li>{when(a["time"])} – <a href="{E(a["url"])}" target="_blank" rel="noopener">{E(a["title"])}</a></li>' for a in wc[:12]) + "</ul>"
           if wc else '<p class="empty">Ingen webcast- eller presentasjonsmelding i meldingsbufferen (120 dager).</p>')
    company = (f'<div class="grid2"><div class="card"><h3>Selskapets rapporter (NewsWeb)</h3>{nwh}<div class="src">Oslo Børs NewsWeb via rapportleseren (~/osloquant-home/reports/{E(code)}/, privat bruk). Lenkene går til meldingen; PDF-en er den nedlastede rapporten.</div></div>'
               f'<div class="card"><h3>Webcast og presentasjoner</h3>{wch}<div class="src">Meldinger fra NewsWeb-bufferen med «webcast», «presentation» eller «invitation» i tittelen.</div></div></div>')
    mine = (ctx.get("reports_html") or "").replace("<h2>Rapporter</h2>", "<h2>Mine rapporter</h2>")
    parts = [events, company, mine]
    if ctx["case"] and (ctx["case"].view or ctx["case"].history):
        parts.append(rd.report_block(code, ctx.get("report")))
    parts += [ctx.get("baserate_html", ""), ctx.get("afterreport_html", ""), ctx.get("forecast_html", "")]
    return "".join(parts)


# ------------------------------------------------------------------------------------------------ 6 Eiere
def owners_panel(code: str, ctx: dict) -> str:
    holders = ('<div class="card"><h3>Største aksjonærer</h3><p class="empty">Ikke tilgjengelig: aksjonærlister er ikke gratis i maskinlesbar form (VPS/Euronext krever abonnement), '
               'og dashbordet henter ingenting fra sider som forbyr det. Selskapets IR-side pleier å publisere de 20 største.</p></div>')
    ins = rd.insider_block(code, ctx.get("insiders")) or '<div class="card"><p class="empty">Innsidehandler og shortposisjoner er ikke hentet (oq dashboard --refresh).</p></div>'
    return holders + ins


# ------------------------------------------------------------------------------------------------ 7 Min vurdering
def judgement_panel(code: str, ctx: dict) -> str:
    c, st, lc = ctx["case"], ctx["status"], ctx.get("lightcase")
    px, name = st["price"], ctx["name"]
    parts = [ctx.get("update_html", "")]
    parts.append(f'<div class="card" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap"><a class="btnlink" href="/stock/{E(code)}/pretrade">Før du kjøper</a>'
                 '<span class="src">Hva markedet priser inn, oddsene, motargumentene, hendelsene før horisonten, posisjonen og sjekklisten – på én side, før skjemaet.</span></div>')
    parts.append(f'<div class="vbox">{rd.view_box(c, px, ctx["price_label"])}</div>')
    parts.append(rd.case_columns(c, px, lc))
    if c and (c.view or c.history):
        parts.append('<h2>Research book</h2><div class="grid2">' + rd.case_view_card(c, px) + rd.case_history_card(c) + '</div>')
        parts.append(rd.odds_block(ctx.get("odds"), c.view or {}))
        from osloquant.dashboard import story as sty

        parts.append(sty.stock_html(c.view))
    parts.append(ctx.get("pass_html", ""))
    parts.append(rd.claude_view_block(c, px))
    if "desk_runs" in ctx:
        from osloquant.dashboard import deskpage

        parts.append(deskpage.stock_block(code, ctx["desk_runs"]))
        if ctx.get("desk_attached"):
            parts.append(deskpage.attached_html(*ctx["desk_attached"]))
    parts.append(rd.judge_form(code, name, px, ctx["price_label"], ctx.get("form", {}), c, ctx.get("sizing")))
    return "".join(parts)


# ------------------------------------------------------------------------------------------------ the page
SCRIPT = r"""<script>
(function(){
  var nav = document.querySelector('nav.tabs'); if(!nav) return;
  var code = nav.dataset.code;
  function resize(panel){ if(!window.Plotly || !panel) return; panel.querySelectorAll('.js-plotly-plot').forEach(function(g){ try { Plotly.Plots.resize(g); } catch(e){} }); }
  function currentSub(){ var on = document.querySelector('.subtabs a.on'); return on ? on.dataset.sub : 'oversikt'; }
  function url(tab){ var sub = currentSub(); return '/aksje/' + code + '/' + tab + (tab === 'regnskap' && sub !== 'oversikt' ? '/' + sub : ''); }
  function showTab(tab, push){
    if(!document.querySelector('.panel[data-tab="' + tab + '"]')) tab = 'oversikt';
    document.querySelectorAll('.panel').forEach(function(p){ p.hidden = p.dataset.tab !== tab; });
    nav.querySelectorAll('a').forEach(function(a){ a.classList.toggle('on', a.dataset.tab === tab); });
    if(push) history.pushState({}, '', url(tab));
    resize(document.querySelector('.panel[data-tab="' + tab + '"]'));
  }
  function showSub(sub, push){
    if(!document.querySelector('.subpanel[data-sub="' + sub + '"]')) sub = 'oversikt';
    document.querySelectorAll('.subpanel').forEach(function(p){ p.hidden = p.dataset.sub !== sub; });
    document.querySelectorAll('.subtabs a').forEach(function(a){ a.classList.toggle('on', a.dataset.sub === sub); });
    if(push) history.pushState({}, '', url('regnskap'));
    resize(document.querySelector('.panel[data-tab="regnskap"]'));
  }
  nav.querySelectorAll('a').forEach(function(a){ a.addEventListener('click', function(e){ e.preventDefault(); showTab(a.dataset.tab, true); window.scrollTo(0, 0); }); });
  document.querySelectorAll('.subtabs a').forEach(function(a){ a.addEventListener('click', function(e){ e.preventDefault(); showSub(a.dataset.sub, true); }); });
  window.addEventListener('popstate', function(){
    var m = location.pathname.match(/\/(aksje|stock)\/[^\/]+(?:\/([a-z]+))?(?:\/([a-z]+))?/);
    if(m && m[3]) showSub(m[3], false);
    showTab(m && m[2] ? m[2] : 'oversikt', false);
  });
  document.querySelectorAll('button.per[data-r]').forEach(function(b){ b.addEventListener('click', function(){
    var r = JSON.parse(b.dataset.r); var g = document.getElementById('chart-price');
    if(window.PriceChart){ PriceChart.period(b.dataset.p); }
    else if(g && window.Plotly && g.classList.contains('js-plotly-plot')){ Plotly.relayout(g, {'xaxis.range': [r.x0, r.x1], 'yaxis.autorange': true}); }
    document.querySelectorAll('button.per').forEach(function(x){ x.classList.toggle('on', x.dataset.p === b.dataset.p); });
    var ov = document.querySelector('.panel[data-tab="oversikt"]'); if(ov && ov.hidden) showTab('oversikt', true);
  }); });
  document.querySelectorAll('.filt button').forEach(function(b){ b.addEventListener('click', function(){
    var k = b.dataset.k; document.querySelectorAll('.filt button').forEach(function(x){ x.classList.toggle('on', x === b); });
    document.querySelectorAll('ul.newsl li').forEach(function(li){ li.hidden = (k !== 'alle' && li.dataset.k !== k); });
  }); });
  document.querySelectorAll('.pertog button').forEach(function(b){ b.addEventListener('click', function(){
    var p = b.dataset.per; document.querySelectorAll('.pertog button').forEach(function(x){ x.classList.toggle('on', x.dataset.per === p); });
    document.querySelectorAll('.pv').forEach(function(d){ d.hidden = d.dataset.per !== p; }); resize(document.querySelector('.panel[data-tab="regnskap"]'));
  }); });
  function fit(){ resize(document.querySelector('.panel:not([hidden])')); }
  window.addEventListener('load', fit); setTimeout(fit, 60); setTimeout(fit, 600);
})();
</script>"""


def stock_page(code: str, ctx: dict) -> str:
    st = ctx["status"]
    if not st.get("price"):
        return rd.page(code, "", f'<h1>{E(code)}</h1><p class="err">Ingen kurser for {E(code)} i lageret. Legg den til i universe.yaml og kjør oq record.</p>')
    tab = ctx.get("tab") if ctx.get("tab") in TAB_KEYS else "oversikt"
    sub = ctx.get("subtab") if ctx.get("subtab") in SUB_KEYS else "oversikt"
    msgs = "".join(f'<div class="err">{E(m)}</div>' for m in ctx.get("errors", [])) + "".join(f'<div class="ok">{E(m)}</div>' for m in ctx.get("ok", []))
    badges = {"vurdering": 1 if ctx.get("update_html") else 0}
    panels = [_panel("oversikt", tab, overview_panel(code, ctx)), _panel("regnskap", tab, accounts_panel(code, ctx, sub)),
              _panel("verdsettelse", tab, valuation_panel(code, ctx)), _panel("teknisk", tab, technical_panel(code, ctx)),
              _panel("rapporter", tab, reports_panel(code, ctx)), _panel("eiere", tab, owners_panel(code, ctx)),
              _panel("vurdering", tab, judgement_panel(code, ctx))]
    body = bar_html(code, ctx) + msgs + tabs_html(code, tab, badges) + "".join(panels) + SCRIPT
    return rd.page(f"{code}", "", body)
