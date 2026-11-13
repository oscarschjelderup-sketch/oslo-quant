"""The macro page and the macro cards other pages show (D65). The numbers come from dashboard/macro.py; this module only
draws them. Charts are TradingView Lightweight Charts, like the price chart, drawn by static/minichart.js."""

from __future__ import annotations

import json

import pandas as pd

from osloquant.dashboard import feeds as fd
from osloquant.dashboard import macro as mc
from osloquant.dashboard.dates import dato, stempel
from osloquant.dashboard.tall import NBSP, gruppe, tall

MINI_SCRIPT = "minichart.js"


def _E(s) -> str:
    from osloquant.dashboard.render import E

    return E(s)


def _link(code: str, text: str | None = None) -> str:
    from osloquant.dashboard.render import link

    return link(code, text)


def chart_scripts() -> str:
    from osloquant.dashboard import pricechart as pc

    return f'<script src="/static/{pc.LIB}"></script><script src="/static/{MINI_SCRIPT}"></script>'


def series_json(series: dict[str, pd.Series], keys, points: int = 800) -> str:
    """The histories the mini charts draw, as one JSON block: {key: {t, v, d}} with d = decimals."""
    out = {}
    for k in keys:
        s = series.get(k)
        if s is None or len(s) < 2:
            continue
        s = s.iloc[-points:]
        d = mc.BY_KEY[k]
        out[k] = {"t": [f"{x:%Y-%m-%d}" for x in s.index], "v": [round(float(v), 4) for v in s.tolist()], "d": d.decimals, "pct": d.unit == "%"}
    return '<script type="application/json" id="mc-data">' + json.dumps(out, separators=(",", ":")).replace("</", "<\\/") + "</script>"


def _exposed(table: pd.DataFrame, d: mc.Driver, names: dict[str, str]) -> str:
    rows = mc.most_sensitive(table, d.key, 6)
    if d.key in mc.NOT_A_DRIVER:
        return ""
    if d.key not in set(table["driver"]):
        return ('<div class="mexp empty">Følsomheten er ikke målt: driveren har endret seg for sjelden eller har for kort historikk til at en ukentlig '
                'regresjon sier noe' + (' – se 3 mnd statskasseveksel, som beveger seg hver uke' if d.key == "styringsrente" else '') + '.</div>')
    if not rows:
        return '<div class="mexp empty">Ingen aksjer i lageret har fulgt denne driveren tydelig de siste tre årene.</div>'
    items = "".join(
        f'<li title="{_E(names.get(r["code"], r["code"]))}: {mc.beta_text(r["beta"])} for {mc.step_text(d)} i {_E(d.name)}, utover det OSEBX forklarer. '
        f't-verdi {tall(r["t"], 1, sign=True)}, korrelasjon {tall(r["corr"], 2, sign=True)}, {r["n"]} uker.">'
        f'{_link(r["code"])} <span class="{"up" if r["beta"] > 0 else "down"}">{mc.beta_text(r["beta"])}</span></li>' for r in rows)
    return (f'<div class="mexp"><span class="src">Mest følsomme aksjer, for {mc.step_text(d)} i driveren:</span><ul>{items}</ul></div>')


FRED_WHY = {
    "mangler": "Krever en gratis nøkkel fra FRED (St. Louis Fed): lagre den i <code>~/osloquant-home/keys/fred.txt</code>, så henter kveldsoppgaven serien.",
    "feil format": "FRED-nøkkelen i <code>~/osloquant-home/keys/fred.txt</code> har feil format (den skal være 32 bokstaver og tall).",
    "avvist": "FRED avviste nøkkelen i <code>~/osloquant-home/keys/fred.txt</code>. Sjekk den på fredaccount.stlouisfed.org.",
}


def driver_card(d: mc.Driver, series: dict[str, pd.Series], table: pd.DataFrame, names: dict[str, str]) -> str:
    c = mc.cell(d, series.get(d.key, pd.Series(dtype=float)))
    head = f'<h3 id="d-{_E(d.key)}">{_E(d.name)}' + (f' <span class="unit">{_E(d.unit)}</span>' if d.unit and d.unit != "%" else "") + "</h3>"
    if c.get("empty"):
        state = ((fd.read(mc.FEED) or {}).get("fred") or {}).get("key") if mc.from_fred(d) else None
        why = FRED_WHY.get(state or "", "Ikke hentet ennå. Kveldsoppgaven henter serien; for hånd: <code>oq dashboard --refresh</code>.")
        return (f'<div class="card mcard">{head}<p class="empty">{why}</p>'
                f'<div class="src">Kilde: {_E(d.source)}.</div></div>')
    short = len(series[d.key]) < 30
    figs = (f'<div class="mfig"><b>{mc.fmt_level(d, c["level"])}</b>'
            f'<span class="{mc._cls(c["d1"])}" title="Endring fra {"uken før" if d.weekly else "forrige notering"}">{mc.fmt_change(d, c["d1"])}</span>'
            f'<span class="src">1 mnd <span class="{mc._cls(c["m1"])}">{mc.fmt_change(d, c["m1"])}</span> · 1 år <span class="{mc._cls(c["y1"])}">{mc.fmt_change(d, c["y1"])}</span></span></div>')
    chart = (f'<p class="empty">For kort historikk til en graf ({len(series[d.key])} noteringer). Serien bygges opp dag for dag.</p>' if short
             else f'<div class="mc" data-key="{_E(d.key)}" role="img" aria-label="{_E(d.name)} over tid"></div>')
    note = f'{_E(d.note[0].upper() + d.note[1:])}. ' if d.note else ""
    return (f'<div class="card mcard">{head}{figs}{chart}{_exposed(table, d, names)}'
            f'<div class="src">{note}Siste notering {dato(c["date"])}. Kilde: {_E(d.source)}.</div></div>')


def matrix_html(table: pd.DataFrame, groups: dict[str, str], order: list[str]) -> str:
    """Sector groups against drivers: how many of the group's stocks have followed the driver, and which way."""
    m = mc.sector_matrix(table, groups)
    if m.empty:
        return '<p class="empty">Ingen følsomhet regnet ennå: makroseriene er ikke hentet, eller lageret har under 60 uker med kurser.</p>'
    drivers = [d for d in mc.DRIVERS if d.key not in mc.NOT_A_DRIVER and d.key in set(m["driver"])]
    head = "".join(f'<th title="{_E(d.source)}">{_E(d.name)}</th>' for d in drivers)
    body = []
    for g in order:
        sub = m[m["group"] == g]
        if sub.empty:
            continue
        cells = []
        for d in drivers:
            r = sub[sub["driver"] == d.key]
            if r.empty:
                cells.append("<td>–</td>")
                continue
            r = r.iloc[0]
            share = r["follow"] / r["n"] if r["n"] else 0
            tone = "pos" if r["t"] > 0 else "neg"
            level = 3 if share >= 0.6 else 2 if share >= 0.3 else 1 if r["follow"] else 0
            cells.append(f'<td class="mx {tone}{level}" title="{_E(gruppe(g))} og {_E(d.name)}: {int(r["follow"])} av {int(r["n"])} aksjer har fulgt driveren (|t| ≥ 2). '
                         f'Median: {mc.beta_text(r["beta"])} for {mc.step_text(d)}, utover det OSEBX forklarer; median t-verdi {tall(r["t"], 1, sign=True)}.">'
                         f'{int(r["follow"])}/{int(r["n"])}' + (f' <span class="src">{mc.beta_text(r["beta"])}</span>' if r["follow"] else "") + "</td>")
        body.append(f'<tr><td class="l"><b>{_E(g)}</b></td>{"".join(cells)}</tr>')
    return (f'<table class="odds mxt"><thead><tr><th class="l">Sektorgruppe</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'
            '<div class="src">Tallet er hvor mange av gruppens aksjer som har fulgt driveren, og medianen av hva aksjene har gjort for driverens steg '
            f'(+10{NBSP}% for en pris, +0,25{NBSP}pp for en rente). Blått: aksjene har gått sterkere enn børsen når driveren steg. Oransje: svakere. '
            'Sterkere farge = større andel av gruppen.</div>')


def calendar_html(events: list[dict], today: pd.Timestamp, days: int = 45) -> str:
    """What is coming: the rate meetings of Norges Bank, the Fed and the ECB (120 days ahead), the followed companies'
    dated events, and the releases of SSB and the US (45 days)."""
    rows = []
    for e in events:
        d = pd.Timestamp(e["date"])
        if e.get("kind") == "rates":
            rows.append((d, "Renter", f'{e.get("name", "")}: {e.get("what", "")}', (e.get("source") or "").split(" (")[0] or "møteplanen"))
        elif e.get("kind") == "release":
            if today <= d <= today + pd.Timedelta(days=days):
                rows.append((d, e.get("name") or "", f'Tallslipp: {e.get("what", "")}', e.get("source") or ""))
        elif today <= d <= today + pd.Timedelta(days=days) and not e.get("duplicate_of_case_event"):
            rows.append((d, e.get("code") or "", f'{e.get("name") or e.get("code") or ""}: {e.get("what", "")}'[:110], e.get("source") or ""))
    if not rows:
        return '<p class="empty">Ingen daterte hendelser de neste ukene i kildene vi har.</p>'
    rows.sort(key=lambda r: r[0])
    tr = "".join(f'<tr><td class="l">{dato(d, False, short_weekday=True)}</td><td class="l">{(d - today).days} d</td>'
                 f'<td class="l">{_link(tag) if tag and tag not in ("Renter", "USA", "Norge") and tag.isalnum() and tag.isupper() else _E(tag)}</td>'
                 f'<td class="l" style="white-space:normal">{_E(what)}</td><td class="l src">{_E(src)}</td></tr>' for d, tag, what, src in rows[:40])
    return (f'<table class="odds"><thead><tr><th class="l">Dato</th><th class="l">Om</th><th class="l">Hvem</th><th class="l">Hva</th><th class="l">Kilde</th></tr></thead>'
            f'<tbody>{tr}</tbody></table>')


def page_html(series: dict[str, pd.Series], table: pd.DataFrame, snap, events: list[dict], today: pd.Timestamp) -> str:
    from osloquant.dashboard import market as mk
    from osloquant.dashboard import pricechart as pc
    from osloquant.dashboard.render import page

    doc = fd.read(mc.FEED) or {}
    fetched = stempel(doc["fetched_at"]) if doc.get("fetched_at") else "aldri"
    errs = doc.get("errors") or []
    fred = mc.uses_fred(doc)
    groups = {c: snap.group(c) for c in snap.names}
    head = ('<h1>Makro</h1><div class="sub">Rentene, kronen, råvarene og børsen: hva de har gjort, og hvilke aksjer i lageret som faktisk har fulgt dem.</div>'
            f'<div class="src">Hentet {fetched}. Daglige serier, ikke sanntid; Yahoo-serier er forsinket.'
            + (f' <span class="st-warn">Ikke hentet sist: {_E(", ".join(errs))} – de viser forrige henting.</span>' if errs else "") + "</div>"
            + (f'<div class="src" id="fred-notice">{mc.fred_notice_html()}</div>' if fred else ""))
    strip = mc.strip_html(series, static=False)
    periods = ('<div class="mper" id="mc-periods"><span class="src">Periode for alle grafene:</span>'
               '<button type="button" class="per" data-mp="3m">3M</button><button type="button" class="per on" data-mp="1a">1Å</button>'
               '<button type="button" class="per" data-mp="3a">3Å</button></div>')
    sections = []
    for g in mc.GROUP_ORDER:
        cards = "".join(driver_card(d, series, table, snap.names) for d in mc.DRIVERS if d.group == g)
        sections.append(f'<h2 id="g-{_E(g.lower())}">{_E(g)}</h2><div class="mgrid">{cards}</div>')
    matrix = ('<h2 id="folsomhet">Hvem følger hva</h2><div class="card">' + matrix_html(table, groups, mk.GROUP_ORDER + ["Other"])
              + '<div class="src" style="margin-top:6px"><b>Slik er det målt:</b> ukentlig avkastning for hver aksje de siste tre årene (inntil 156 uker), regnet mot ukentlig endring i '
              'driveren, med OSEBX ved siden av i samme regresjon. Det som står igjen er hva aksjen har gjort utover børsen når driveren beveget seg. '
              'En aksje «følger» driveren når t-verdien er 2 eller mer i tallverdi. Dette er samvariasjon i våre egne data, ikke årsak og ikke en prognose: '
              'en oljetung børs gjør for eksempel at banker ser ut til å falle mot børsen når Brent stiger.</div></div>')
    from osloquant.dashboard import calendar as calmod

    us = mc.releases(doc)
    refill = calmod.refill_notes(today)
    cal = ('<h2 id="kalender">Det som kommer</h2><div class="card">' + calendar_html(list(events), today)
           + '<div class="src">Rentemøter: de publiserte møteplanene til Norges Bank, Fed og ESB, skrevet av for hånd med kilde og dato (se '
           '<a href="/calendar">Kalender</a>). Tallslipp i Norge (KPI, AKU, BNP, detaljomsetning): SSBs publiseringskalender (CC BY 4.0), de neste 45 dagene. '
           + ('Tallslipp i USA (KPI, sysselsetting, BNP): FRED-kalenderen. ' if us else 'Tallslipp i USA kommer med FRED-nøkkelen. ')
           + 'Selskapshendelser: research book og selskapenes finanskalendere på NewsWeb.'
           + (f' <span class="st-warn">Møteplanen må fylles på: {_E("; ".join(refill))}.</span>' if refill else '') + '</div></div>')
    keys = [d.key for d in mc.DRIVERS]
    body = (head + strip + periods + "".join(sections) + matrix + cal + series_json(series, keys) + chart_scripts()
            + f'<div class="src attrib">{pc.attribution_html()}' + (f" {mc.fred_notice_html()}" if fred else "") + "</div>")
    return page("Makro", "/makro", body)


def stock_card(code: str, name: str, rows: list[dict]) -> str:
    """«Makro som betyr noe for denne aksjen»: the drivers the stock has followed, how strongly, and what they did lately."""
    if not rows:
        return ('<div class="card" id="makro-aksje"><h3>Makro som betyr noe for denne aksjen</h3><p class="empty">Ingen av driverne vi følger har forklart '
                f'kursen til {_E(code)} tydelig de siste tre årene, utover det børsen selv forklarer. Selskapets egne nyheter betyr mer. '
                '<a href="/makro#folsomhet">Se hele oversikten</a>.</p></div>')
    tr = []
    for r in rows:
        d, c = mc.BY_KEY[r["driver"]], r["cell"]
        m1 = c.get("m1")
        implied = None if m1 is None else r["beta"] * ((m1 / d.step) if d.kind == "rate" else (m1 * 100 / d.step))
        bar = min(100, int(abs(r["t"]) / 8 * 100))
        tr.append(
            f'<tr><td class="l"><a href="/makro#d-{_E(d.key)}">{_E(d.name)}</a></td>'
            f'<td class="l"><span class="sbar" title="t-verdi {tall(r["t"], 1, sign=True)}, korrelasjon {tall(r["corr"], 2, sign=True)}, {r["n"]} uker"><i style="width:{bar}%"></i></span> {_E(r["strength"])}</td>'
            f'<td class="{"up" if r["beta"] > 0 else "down"}" title="Aksjens bevegelse for {mc.step_text(d)} i driveren, utover det OSEBX forklarer">{mc.beta_text(r["beta"])}</td>'
            f'<td>{mc.fmt_level(d, c.get("level"))}</td><td class="{mc._cls(m1)}">{mc.fmt_change(d, m1)}</td>'
            f'<td class="{mc._cls(implied)}" title="Driverens bevegelse siste måned ganger aksjens målte følsomhet. En regnestykke på historikken, ikke en prognose.">'
            f'{"–" if implied is None else mc.beta_text(implied)}</td>'
            f'<td class="l">{mc.sparkline(c.get("spark") or [], 70, 20)}</td></tr>')
    return ('<div class="card" id="makro-aksje"><h3>Makro som betyr noe for denne aksjen</h3>'
            '<table class="odds"><thead><tr><th class="l">Driver</th><th class="l">Sammenheng</th><th title="For +10 % i en pris eller +0,25 pp i en rente">Aksjen per steg</th>'
            '<th>Nå</th><th>Siste måned</th><th title="Driverens bevegelse siste måned ganger følsomheten">Tilsvarer</th><th class="l">Trend</th></tr></thead>'
            f'<tbody>{"".join(tr)}</tbody></table>'
            f'<div class="src">Driverne {_E(name)} har fulgt de siste tre årene, målt på ukentlig avkastning med OSEBX i samme regresjon – altså utover det børsen forklarer. '
            f'Steget er +10{NBSP}% for en pris og +0,25{NBSP}pp for en rente. «Tilsvarer» er driverens bevegelse siste måned ganger følsomheten: et regnestykke på historikken '
            '(EST), ikke en prognose og ikke en årsak. <a href="/makro#folsomhet">Metoden og alle aksjene</a>.</div></div>')
