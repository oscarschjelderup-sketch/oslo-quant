"""The stock page's price chart (night session 10 Nov 2026, part 1 – docs/natt/endringer.md K1–K3).

The browser draws it with TradingView Lightweight Charts™ 5.2.1. The library is Apache-2.0 and is served from
``dashboard/static`` together with its LICENSE and NOTICE. The chart keeps TradingView's attribution logo, and the
NOTICE text and a link stand under it. ``static/pricechart.js`` is our own drawing code.

What goes into the payload:
- the store's own adjusted daily bars for the whole history
- the period buttons' ranges and returns
- the events the dashboard knows: reports, ex-dividend dates and splits, insider notifications, Oscar's own judgements
- the view's target and kill level
- two comparisons: OSEBX, and an equal-weighted average of the rest of the stock's group (our own calculation)

Nothing comes from TradingView; the library only draws. Prices are delayed and adjusted, and every number carries its
source.
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from osloquant.dashboard import market as mk
from osloquant.dashboard.charts import period_ranges
from osloquant.dashboard.dates import SHORT_DAYS, SHORT_MONTHS, dato

LIB = "lightweight-charts.standalone.production.js"
LIB_VERSION = "5.2.1"
SCRIPT = "pricechart.js"
STATIC = Path(__file__).resolve().parent / "static"
SOURCE = "Yahoo Finance via oslo-quant-lageret, daglige sluttkurser, forsinket, justert for utbytte og splitt"
REPORT_WORDS = re.compile(r"(?i)report|rapport|result|kvartal|quarter|half-year|halvår|presentation")
KILL_WHY = {"kill level in the view": "kill-nivået i synet", "bear value (no kill level set)": "bear-verdien (synet har ikke eget kill-nivå)"}
SIDE_NO = {"buy": "kjøp", "sell": "salg", "subscription": "tegning", "programme": "program", "company": "selskapet", "other": "annet", "unknown": "uklart"}


def notice() -> str:
    """The NOTICE text the library's licence asks every page that shows it to carry."""
    try:
        return (STATIC / "lightweight-charts.NOTICE").read_text(encoding="utf-8").strip()
    except OSError:
        return "TradingView Lightweight Charts™ Copyright (c) TradingView, Inc. https://www.tradingview.com/"


def _num(x, nd: int = 6):
    """A float for the JSON payload: None for NaN, ``nd`` significant digits otherwise."""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else float(f"{x:.{nd}g}")


def _decimals(s: pd.Series, sig: int = 6) -> int:
    """Decimals that keep ``sig`` significant digits of the column's largest value (two to eight)."""
    a = np.abs(pd.to_numeric(s, errors="coerce").to_numpy(dtype=float))
    a = a[np.isfinite(a) & (a > 0)]
    return int(min(8, max(2, sig - math.ceil(math.log10(float(a.max())))))) if a.size else 2


def _arr(s: pd.Series, d: int | None = None) -> list:
    """A price column for the payload, rounded as one array to ``d`` decimals (default: from its own largest value);
    NaN as None. Open, high, low and close share one ``d`` so a rounded bar never turns impossible."""
    a = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    a = np.round(a, _decimals(s) if d is None else d)
    return [None if v != v or v in (math.inf, -math.inf) else v for v in a.tolist()]


def _nf(x: float, d: int = 2) -> str:
    """Norwegian number: space as the thousands separator, decimal comma, a real minus sign."""
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",").replace("-", "−")


def _pct(x: float, d: int = 1) -> str:
    return f"{x * 100:+.{d}f}".replace(".", ",").replace("-", "−") + " %"


# ------------------------------------------------------------------------------------------------ prices
def _frame_from_snapshot(snap: mk.Snapshot, code: str) -> pd.DataFrame:
    P = snap.panel
    if code not in P["close"].columns:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    c = P["close"][code].dropna()
    return pd.DataFrame({k: P[k][code].reindex(c.index) if code in P[k].columns else None for k in ("open", "high", "low", "close", "volume")})


@lru_cache(maxsize=96)
def _store_bars(code: str, key: tuple) -> pd.DataFrame:
    """The whole adjusted daily history of one stock. ``key`` carries the snapshot's newest bar, so the cache is renewed
    whenever the snapshot sees a newer session or a rewritten close for the same session."""
    from osloquant.domain import Stock1dAdjKdata

    df = Stock1dAdjKdata.query_data(code=code, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = df.dropna(subset=["close"]).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    return df.set_index(pd.DatetimeIndex(df["timestamp"]))[["open", "high", "low", "close", "volume"]]


def _key(snap: mk.Snapshot, code: str) -> tuple:
    P = snap.panel
    c = P["close"][code].dropna() if code in P["close"].columns else pd.Series(dtype=float)
    return (str(snap.asof), float(c.iloc[-1]) if len(c) else None, str(c.index[-1]) if len(c) else None)


def history(snap: mk.Snapshot, code: str) -> pd.DataFrame:
    """Open, high, low, close and volume for every session the store has, oldest first. The snapshot (800 days) is
    the fallback when the store cannot be read or has less than the snapshot."""
    short = _frame_from_snapshot(snap, code)
    try:
        full = _store_bars(code, _key(snap, code))
    except Exception:  # noqa: BLE001 – the chart falls back to the snapshot
        full = short.iloc[0:0]
    df = full if len(full) >= len(short) else short
    df = df.copy()
    for k in ("open", "high", "low"):            # a missing or impossible open/high/low draws as the close
        bad = df[k].isna() | (df[k] <= 0)
        df.loc[bad, k] = df.loc[bad, "close"]
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    return df


@lru_cache(maxsize=8)
def _osebx_store(key: str) -> pd.Series:
    from osloquant.domain import Index1dKdata

    df = Index1dKdata.query_data(code="OSEBX", columns=["timestamp", "close"])
    if df is None or df.empty:
        return pd.Series(dtype=float)
    df = df.dropna(subset=["close"]).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    return pd.Series(df["close"].to_numpy(), index=pd.DatetimeIndex(df["timestamp"]))


@lru_cache(maxsize=16)
def _closes_store(codes: tuple[str, ...], key: str) -> pd.DataFrame:
    from osloquant import signals as sg

    P = sg.load_panel(codes=list(codes))
    return P["close"] if not P["close"].empty else pd.DataFrame()


def sector_index(closes: pd.DataFrame, min_members: int = 2) -> pd.Series:
    """An equal-weighted index of the members' daily closes: the mean daily return of the members that traded both
    days, chained from 1. Days with fewer than ``min_members`` returns before the first such day are left out; later
    gaps add nothing (a return of 0). Pure: closes in, index out."""
    if closes is None or closes.empty:
        return pd.Series(dtype=float)
    r = closes.sort_index().pct_change(fill_method=None)
    cnt = r.notna().sum(axis=1)
    ok = cnt >= min_members
    if not ok.any():
        return pd.Series(dtype=float)
    pos = int(ok.to_numpy().argmax())
    mean = r.mean(axis=1).where(ok, 0.0).iloc[pos:]
    if pos > 0:                                  # the index starts at 1 on the session before the first return
        mean = pd.concat([pd.Series([0.0], index=r.index[pos - 1:pos]), mean])
    else:
        mean = mean.copy()
        mean.iloc[0] = 0.0
    return (1 + mean).cumprod()


def comparisons(snap: mk.Snapshot, code: str, index: pd.DatetimeIndex) -> dict:
    """OSEBX and the sector, aligned to the stock's sessions (a missing day stays empty). A comparison the store
    cannot give is left out with the reason, so the button can say why it is off."""
    out: dict = {}
    off: dict = {}
    key = str(snap.asof)
    try:
        ob = _osebx_store(key)
    except Exception:  # noqa: BLE001
        ob = pd.Series(dtype=float)
    if len(ob):
        v = ob.reindex(index)
        out["osebx"] = {"short": "OSEBX", "label": "Oslo Børs hovedindeks (OSEBX)", "v": _arr(v),
                        "src": f"OSEBX fra Yahoo Finance via lageret, daglige sluttkurser fra {dato(ob.index[0])}, forsinket", "first": f"{ob.index[0]:%Y-%m-%d}"}
    else:
        off["osebx"] = "OSEBX finnes ikke i lageret (oq record --index)"
    group = snap.group(code)
    members = tuple(sorted(c for c in snap.sectors if c != code and snap.group(c) == group))
    if len(members) < 2:
        off["sector"] = f"for få andre aksjer i gruppen {group} til et snitt ({len(members)})"
        return {"cmp": out, "off": off}
    try:
        closes = _closes_store(members, key)
    except Exception:  # noqa: BLE001
        closes = pd.DataFrame()
    if closes is None or closes.empty or len(closes) < len(snap.panel["close"]):
        closes = snap.panel["close"].reindex(columns=[c for c in members if c in snap.panel["close"].columns])
    idx = sector_index(closes)
    if idx.empty:
        off["sector"] = f"ingen felles kurser for gruppen {group}"
    else:
        v = idx.reindex(index)
        out["sector"] = {"short": "Sektor", "label": f"{group}: likevektet snitt av {len(closes.columns)} andre aksjer", "v": _arr(v),
                         "src": f"egen beregning: daglig snittavkastning for {', '.join(closes.columns)} (Yahoo via lageret, justert, forsinket); dagens univers, så aksjer som er tatt av børs mangler"}
    return {"cmp": out, "off": off}


# ------------------------------------------------------------------------------------------------ events and lines
def _snap_day(day, index: pd.DatetimeIndex) -> str | None:
    """The first session on or after ``day`` (an event on a weekend or holiday lands on the next session)."""
    d = pd.Timestamp(str(day)[:10])
    i = index.searchsorted(d)
    return f"{index[i]:%Y-%m-%d}" if i < len(index) else None


def events(code: str, index: pd.DatetimeIndex, case=None, dividends=None, insiders=None, newsweb_reports=None,
           cal_doc=None, log_rows=None) -> list[dict]:
    """Every dated thing the dashboard knows about the stock, on the session it belongs to, oldest first. Kinds:
    rapport, utbytte, innside (with side), vurdering. Pure apart from the inputs."""
    from osloquant import judgements as jg

    if not len(index):
        return []
    out: list[dict] = []
    last = index[-1]

    def add(day, kind, txt, src, **extra) -> str | None:
        if pd.Timestamp(str(day)[:10]) > last:
            return None
        t = _snap_day(day, index)
        if t:
            out.append({"t": t, "k": kind, "txt": txt, "src": src, **extra})
        return t

    seen_reports: set[str] = set()               # one report marker per session: the calendar and the download agree
    for ev in (((cal_doc or {}).get("companies") or {}).get(code) or {}).get("events", []):
        if REPORT_WORDS.search(str(ev.get("what", ""))) and _snap_day(ev["date"], index) not in seen_reports:
            seen_reports.add(add(ev["date"], "rapport", str(ev["what"]), "NewsWeb finanskalender"))
    for r in newsweb_reports or []:
        if r.get("date") and _snap_day(r["date"], index) not in seen_reports:
            seen_reports.add(add(r["date"], "rapport", str(r.get("title") or "Rapport"), "NewsWeb, nedlastet av rapportleseren"))
    for d in dividends or []:
        if d.get("dividend"):
            add(d["date"], "utbytte", f"Eks-utbytte NOK {_nf(float(d['dividend']))} per aksje", "Yahoo Finance via lageret (StockAction)")
        if d.get("split"):
            add(d["date"], "utbytte", f"Aksjesplitt {float(d['split']):g}:1", "Yahoo Finance via lageret (StockAction)")
    for i in insiders or []:
        side = i.get("side") if i.get("side") in ("buy", "sell") else None
        add(i["time"], "innside", f"Innsidehandel ({SIDE_NO.get(i.get('side'), i.get('side') or 'uklart')}): {i.get('title', '')}",
            "NewsWeb, meldepliktig handel", **({"side": side} if side else {}))
    days_logged: set[str] = set()
    for row in log_rows or []:
        if row.get("kind", "judgement") != "judgement" or row.get("code") != code or jg.analyst_of(row) != "oscar":
            continue
        tp = row.get("target")
        txt = "Din vurdering logget" + (f": kursmål NOK {_nf(float(tp))}" if tp else "") + (f", kurs da {_nf(float(row['price']))}" if row.get("price") else "")
        add(row["date"], "vurdering", txt, f"vurderingsloggen, rad {row.get('seq', '?')}")
        days_logged.add(str(row["date"])[:10])
    v = (case.view if case else None) or {}
    if v.get("date") and str(v["date"])[:10] not in days_logged:
        tp = v.get("target")
        add(v["date"], "vurdering", "Syn i research book" + (f": kursmål NOK {_nf(float(tp))}" if tp else ""), f"research book ({getattr(case, 'view_source', 'synet')})")
    return sorted(out, key=lambda e: (e["t"], e["k"]))


def lines(case, last_px: float) -> list[dict]:
    """The view's target and kill level as horizontal lines, with the distance from today's price."""
    from osloquant.dashboard import odds as od

    v = (case.view if case else None) or {}
    out = []
    if v.get("target"):
        tp = float(v["target"])
        out.append({"k": "target", "p": tp, "title": "Kursmål", "dist": tp / last_px - 1,
                    "src": f"ditt kursmål (EST), syn fra {dato(v.get('date'))}"})
        kill, why = od.kill_level(v)
        if kill:
            out.append({"k": "kill", "p": float(kill), "title": "Kill-nivå", "dist": float(kill) / last_px - 1,
                        "src": f"{KILL_WHY.get(why, why)}, syn fra {dato(v.get('date'))} (EST)"})
    return out


# ------------------------------------------------------------------------------------------------ the payload and the card
def payload(snap: mk.Snapshot, code: str, case=None, extra: dict | None = None) -> dict:
    """Everything the browser needs to draw the chart, as plain JSON (no NaN)."""
    extra = extra or {}
    df = history(snap, code)
    if df.empty:
        return {}
    idx = pd.DatetimeIndex(df.index)
    c = df["close"]
    ranges = period_ranges(c, df["volume"])
    periods = [{k: p[k] for k in ("key", "label", "x0", "x1", "sessions", "enough", "from_listing")} | {"ret": _num(p["ret"])} for p in ranges]
    default = "1a" if any(p["key"] == "1a" and p["enough"] for p in periods) else "maks"
    cmp = comparisons(snap, code, idx)
    last_px = float(c.iloc[-1])
    dec = _decimals(df["high"])
    return {
        "code": code, "cur": "NOK", "src": SOURCE, "asof": f"{idx[-1]:%Y-%m-%d}",
        "t": [f"{d:%Y-%m-%d}" for d in idx],
        "o": _arr(df["open"], dec), "h": _arr(df["high"], dec), "l": _arr(df["low"], dec), "c": _arr(c, dec),
        "v": [None if x != x else int(x) for x in pd.to_numeric(df["volume"], errors="coerce").to_numpy(dtype=float).tolist()],
        "last": last_px, "prev": float(c.iloc[-2]) if len(c) > 1 else last_px,
        "periods": periods, "default": default,
        "cmp": cmp["cmp"], "cmp_off": cmp["off"],
        "events": events(code, idx, case, extra.get("dividends"), extra.get("insiders"), extra.get("newsweb_reports"), extra.get("cal_doc"), extra.get("log_rows")),
        "lines": lines(case, last_px),
        "months": SHORT_MONTHS, "days": SHORT_DAYS,
    }


EV_LABEL = {"rapport": ("R", "Rapporter", "Rapportdager lageret kjenner: NewsWeb-finanskalenderen og rapportene leseren har lastet ned. Eldre rapportdatoer finnes ikke i lageret."),
            "utbytte": ("U", "Utbytte", "Eks-utbyttedager og splitter fra Yahoo Finance via lageret (StockAction)."),
            "innside": ("I", "Innsidehandel", "Meldepliktige handler fra NewsWeb-bufferen: pil opp er kjøp, pil ned er salg."),
            "vurdering": ("V", "Mine vurderinger", "Dine rader i vurderingsloggen og synet i research book (Claudes rader er ikke med).")}


def card_html(data: dict, div_id: str = "chart-price") -> str:
    """The chart card's top: title with the unit, the return line the script fills, the toolbar, the drawing area, the
    hover box and the payload. The period buttons and the source line are added by the stock page."""
    from osloquant.dashboard.render import E

    if not data:
        return '<p class="empty">Ingen kurser i lageret for aksjen.</p>'
    code = data["code"]
    first, last = data["t"][0], data["t"][-1]
    info = (f"Daglige sluttkurser for {code} fra {dato(first)} til {dato(last)} ({len(data['t'])} økter), justert for utbytte og splitt. "
            "Kilde: Yahoo Finance via lageret, forsinket – ikke sanntid. Periodeknappene, zoom (hjul eller dra) og verktøylinjen virker på grafen; "
            "hold musen over grafen for kurs, endring, volum og hendelser den dagen.")
    counts = {k: sum(1 for e in data["events"] if e["k"] == k) for k in EV_LABEL}
    on = {"rapport": True, "utbytte": True, "innside": False, "vurdering": True}

    def evb(k: str) -> str:
        letter, label, why = EV_LABEL[k]
        n = counts[k]
        dis = " disabled" if not n else ""
        title = why + (f" {n} i grafen." if n else " Ingen i lageret for aksjen.")
        return (f'<button type="button" data-ev="{k}" class="ev-{k}{" on" if on[k] and n else ""}" aria-pressed="{str(on[k] and bool(n)).lower()}" title="{E(title)}"{dis}>'
                f'<i>{letter}</i>{E(label)} <small>{n}</small></button>')

    def cmpb(k: str, label: str) -> str:
        c = data["cmp"].get(k)
        if c:
            return f'<button type="button" data-cmp="{k}" aria-pressed="false" title="{E(c["label"] + ". " + c["src"] + ". Grafen viser da prosent siden periodens første dag for alle linjene.")}">{E(label)}</button>'
        return f'<button type="button" data-cmp="{k}" disabled title="{E(data["cmp_off"].get(k, "ikke tilgjengelig"))}">{E(label)}</button>'

    tools = ('<div class="pc-tools" role="toolbar" aria-label="Valg for kursgrafen">'
             '<span class="grp"><button type="button" data-type="area" class="on" aria-pressed="true" title="Sluttkurs som kurve">Kurve</button>'
             '<button type="button" data-type="candles" aria-pressed="false" title="Åpning, høy, lav og slutt per dag (justert)">Lysestaker</button></span>'
             '<span class="grp"><button type="button" data-opt="log" aria-pressed="false" disabled title="Log-skala er bare for 5Å og Maks.">Log</button></span>'
             f'<span class="grp"><span class="lbl">Sammenlign</span>{cmpb("osebx", "OSEBX")}{cmpb("sector", "Sektor")}</span>'
             '<span class="grp"><button type="button" data-sma="50" aria-pressed="false" title="Glidende snitt av 50 sluttkurser">SMA 50</button>'
             '<button type="button" data-sma="200" aria-pressed="false" title="Glidende snitt av 200 sluttkurser">SMA 200</button></span>'
             f'<span class="grp"><span class="lbl">Hendelser</span>{"".join(evb(k) for k in EV_LABEL)}</span></div>')
    lines_txt = " · ".join(f'{E(ln["title"])} {E(_nf(ln["p"]))} (<span class="{"up" if ln["dist"] >= 0 else "down"}">{E(_pct(ln["dist"]))}</span> fra dagens kurs)' for ln in data["lines"])
    lines_html = f'<div class="pc-lines" title="{E("; ".join(ln["src"] for ln in data["lines"]))}">{lines_txt}</div>' if data["lines"] else ""
    blob = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("</", "<\\/")
    return (f'<div class="pc"><div class="pc-head"><h3>Kurs <span class="unit">NOK</span> <span class="info" title="{E(info)}">i</span></h3>'
            f'<div class="pc-ret" aria-live="polite"></div></div>'
            f'<div class="pc-sub">{E(code)} · daglige sluttkurser til {dato(last)} · justert for utbytte og splitt · Yahoo Finance via lageret, '
            f'<span class="delayed" title="{E(SOURCE)}">forsinket</span></div>{lines_html}{tools}'
            f'<div class="pc-box"><div id="{div_id}" class="pc-canvas"></div><div class="pc-tip" hidden></div></div>'
            f'<noscript><p class="empty">Grafen trenger JavaScript.</p></noscript>'
            f'<script type="application/json" id="pc-data">{blob}</script>'
            f'<script src="/static/{LIB}"></script><script src="/static/{SCRIPT}"></script></div>')


def attribution_html() -> str:
    """The licence's attribution: the NOTICE text and a link to TradingView (the logo also stays on the chart)."""
    from osloquant.dashboard.render import E

    first, _, rest = notice().partition("\n")
    return (f'<span class="attrib">Graf: {E(first)} {LIB_VERSION} – {E(rest.replace("https://www.tradingview.com/", "").strip())} '
            '<a href="https://www.tradingview.com/" target="_blank" rel="noopener">tradingview.com</a>, Apache-2.0. Dataene er lagerets egne; ingenting hentes fra TradingView.</span>')


def build(snap: mk.Snapshot, code: str, case=None, extra: dict | None = None) -> tuple[str, list[dict]]:
    """The chart card's HTML and the period list the stock page's buttons use."""
    data = payload(snap, code, case, extra)
    return card_html(data), (data.get("periods") or [])
