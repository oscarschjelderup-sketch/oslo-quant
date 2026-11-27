"""The policy rate against Norges Bank's rate path, and rates against the sectors (D73, holiday plan step 2).

Three things live here.

- **The paths.** Each Monetary Policy Report carries the bank's projected policy rate, a quarterly average, from the
  report's quarter about three years ahead. The bank publishes no stable machine-readable source for it (the chart
  workbook's name and layout change from report to report), so the paths are copied by hand from the workbooks into
  ``resources/norges_bank_rate_path.yaml`` with the report, its page, the workbook and the date copied – like the
  meeting files (D71). When a report day in the meeting file has passed that is newer than the newest path here, the
  page and the data-health page say the file must be filled in.
- **What was signalled and what happened.** The actual policy rate is Norges Bank's daily series from the macro feed;
  its quarterly average (business days) is set against what each report's path said for that quarter.
- **Rates and the sectors, measured on our own data.** Each sector group's equal-weighted weekly return regressed on
  the weekly change in a rate with OSEBX beside it (the same method as the stock-level sensitivity, D65, on the group
  as one portfolio), and the groups' moves against the market on the days a new path came out. Every number has its
  observation count, and a group with no measurable link is said to have none. Co-movement, not cause; no forecast.
"""

from __future__ import annotations

import json
import math
from importlib import resources

import numpy as np
import pandas as pd
import yaml

from osloquant.dashboard.dates import dato
from osloquant.dashboard.tall import NBSP, gruppe, tall

PATH_FILE = "norges_bank_rate_path.yaml"
SHOW_FROM = "2024-04-01"          # the chart starts with the oldest path in the file
RATE_DRIVERS = ("stat3m", "stat10y")
STEP = 0.25                       # the move every sensitivity is stated for, in percentage points
FOLLOWS = 2.0


def _E(s) -> str:
    from osloquant.dashboard.render import E

    return E(s)


# ------------------------------------------------------------------------------------------------ the file
def load_paths(text: str | None = None) -> dict | None:
    """The resource file, reports sorted oldest first; None when it is missing."""
    try:
        doc = yaml.safe_load(text if text is not None else resources.files("osloquant").joinpath(f"resources/{PATH_FILE}").read_text(encoding="utf-8"))
    except (OSError, FileNotFoundError):
        return None
    if not doc or not doc.get("reports"):
        return None
    for r in doc["reports"]:
        r["published"] = pd.Timestamp(str(r["published"]))
        r["path"] = {str(q): float(v) for q, v in (r.get("path") or {}).items()}
    doc["reports"].sort(key=lambda r: r["published"])
    return doc


def quarter(q: str) -> pd.Period:
    return pd.Period(q, freq="Q")


def report_days(meetings: dict | None) -> list[pd.Timestamp]:
    """The days in the meeting file that bring a Monetary Policy Report («pengepolitisk rapport»)."""
    return sorted(pd.Timestamp(str(d["date"])) for d in (meetings or {}).get("dates") or [] if "rapport" in str(d.get("what", "")).lower())


def refill_note(today: pd.Timestamp, doc: dict | None, meetings: dict | None) -> str | None:
    """Why the path file must be filled in, or None. The newest report in the file is compared with the newest report
    day that has passed in Norges Bank's meeting file; a report is out at 10.00, so its own day counts from the next."""
    if doc is None:
        return f"Rentebanen: kildefilen mangler (resources/{PATH_FILE}). Ingen bane er gjettet."
    newest = doc["reports"][-1]["published"]
    passed = [d for d in report_days(meetings) if newest < d < today]
    if passed:
        return (f'Rentebanen må fylles på: Norges Bank la frem en ny pengepolitisk rapport {dato(passed[-1])}, og den nyeste i filen er '
                f'{doc["reports"][-1]["report"]} ({dato(newest)}). Kopier banen fra rapportens figurdata ({doc.get("source")}).')
    return None


# ------------------------------------------------------------------------------------------------ signalled against actual
def quarterly_actual(rate: pd.Series) -> pd.Series:
    """The policy rate's average over each complete quarter (business days), indexed by quarter."""
    if rate is None or rate.empty:
        return pd.Series(dtype=float)
    q = rate.groupby(rate.index.to_period("Q")).mean()
    last = rate.index[-1]
    return q[[p.end_time.normalize() <= last for p in q.index]]


def signal_rows(doc: dict | None, rate: pd.Series) -> list[dict]:
    """Per report: what its path said for the next quarter and for four quarters on, what the quarter's average turned
    out to be, and the mean gap over every quarter of the path that is complete."""
    if not doc:
        return []
    actual = quarterly_actual(rate)
    out = []
    for r in doc["reports"]:
        q0 = r["published"].to_period("Q")
        row = {"report": r["report"], "published": r["published"], "url": r.get("url")}
        for k, ahead in (("next", 1), ("year", 4)):
            q = q0 + ahead
            row[k] = {"q": q, "said": r["path"].get(str(q)), "was": float(actual[q]) if q in actual.index else None}
        gaps = [float(actual[quarter(q)]) - v for q, v in r["path"].items() if quarter(q) > q0 and quarter(q) in actual.index]
        row["gap"], row["n"] = (float(np.mean(gaps)) if gaps else None), len(gaps)
        out.append(row)
    return out


def chart_json(doc: dict | None, rate: pd.Series, newest_n: int = 3) -> str:
    """The data the rate-path chart draws, on one weekly grid (Fridays) so that the time axis is even: the chart library
    spaces points by count, not by date. ``grid``: every Friday from SHOW_FROM to the end of the longest path;
    ``actual``: the policy rate in force each Friday; each path: its quarters, each on the Friday nearest its middle."""
    out = {"grid": [], "actual": {"t": [], "v": []}, "paths": []}
    reports = (doc or {}).get("reports") or []
    start = pd.Timestamp(SHOW_FROM)
    ends = [quarter(q).end_time.normalize() for r in reports for q in r["path"]]
    if rate is not None and not rate.empty:
        ends.append(rate.index[-1])
    if not ends:
        return '<script type="application/json" id="rp-data">' + json.dumps(out) + "</script>"
    grid = pd.date_range(start, max(ends) + pd.Timedelta(days=7), freq="W-FRI")
    out["grid"] = [f"{d:%Y-%m-%d}" for d in grid]
    if rate is not None and not rate.empty:
        s = rate.sort_index()
        weekly = s.reindex(grid.union(s.index)).ffill().reindex(grid)
        weekly = weekly[(weekly.index <= s.index[-1]) & weekly.notna()]
        out["actual"] = {"t": [f"{d:%Y-%m-%d}" for d in weekly.index], "v": [round(float(v), 4) for v in weekly.tolist()]}
    for i, r in enumerate(reports):
        pts = sorted((quarter(q), v) for q, v in r["path"].items())
        rank = len(reports) - 1 - i                                         # 0 = the newest
        days = [grid[abs(grid - (p.start_time + (p.end_time - p.start_time) / 2)).argmin()] for p, _ in pts]
        keep = [(d, v, p) for d, (p, v) in zip(days, pts, strict=True) if d >= start]
        out["paths"].append({"name": r["report"], "published": f'{r["published"]:%Y-%m-%d}', "rank": rank, "strong": rank < newest_n,
                             "t": [f"{d:%Y-%m-%d}" for d, _, _ in keep], "v": [v for _, v, _ in keep], "q": [f"{p.quarter}. kv. {p.year}" for _, _, p in keep]})
    return '<script type="application/json" id="rp-data">' + json.dumps(out, separators=(",", ":")).replace("</", "<\\/") + "</script>"


# ------------------------------------------------------------------------------------------------ rates and the sectors
def _ols(y: np.ndarray, X: np.ndarray) -> tuple[float, float] | None:
    """The second coefficient and its t-value."""
    n = len(y)
    if n <= X.shape[1] or np.std(X[:, 1]) == 0 or np.std(y) == 0:
        return None
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    var = np.linalg.pinv(X.T @ X)[1, 1] * (resid @ resid / (n - X.shape[1]))
    return float(coef[1]), (float(coef[1] / math.sqrt(var)) if var > 0 else 0.0)


def group_returns(closes: pd.DataFrame, groups: dict[str, str], freq: str | None = "W-FRI", min_obs: int = 60) -> tuple[pd.DataFrame, dict[str, int]]:
    """Each sector group's equal-weighted log return (weekly, or daily with ``freq=None``) and how many stocks are in it."""
    px = closes.resample(freq).last() if freq else closes
    r = np.log(px.where(px > 0)).diff()
    out, sizes = {}, {}
    for g in sorted(set(groups.values())):
        cols = [c for c in r.columns if groups.get(c) == g and r[c].notna().sum() >= min_obs]
        if cols:
            out[g], sizes[g] = r[cols].mean(axis=1, skipna=True), len(cols)
    return pd.DataFrame(out), sizes


def sector_rates(closes: pd.DataFrame, series: dict[str, pd.Series], groups: dict[str, str], weeks: int = 156) -> pd.DataFrame:
    """One row per sector group and rate: the group's weekly return beyond what OSEBX explains, per +0.25 pp in the
    rate (``beta``, per cent), its t-value, the weeks used (``n``) and the stocks in the group (``stocks``)."""
    from osloquant.dashboard import macro as mc

    cols = ["group", "driver", "beta", "t", "n", "stocks"]
    osebx = series.get("osebx")
    if closes is None or closes.empty or osebx is None or osebx.empty:
        return pd.DataFrame(columns=cols)
    rets, sizes = group_returns(closes, groups)
    rets = rets.iloc[-weeks:]
    market = np.log(mc.weekly(osebx)).diff().reindex(rets.index)
    rows = []
    for key in RATE_DRIVERS:
        s = series.get(key)
        if s is None or len(s) < 2:
            continue
        x = mc.weekly(s).diff().reindex(rets.index)
        for g in rets.columns:
            y = rets[g]
            ok = (x.notna() & y.notna() & market.notna()).to_numpy()
            if ok.sum() < mc.MIN_WEEKS:
                continue
            fit = _ols(y.to_numpy()[ok], np.column_stack([np.ones(ok.sum()), x.to_numpy()[ok], market.to_numpy()[ok]]))
            if fit:
                rows.append({"group": g, "driver": key, "beta": fit[0] * STEP * 100, "t": fit[1], "n": int(ok.sum()), "stocks": sizes[g]})
    return pd.DataFrame(rows, columns=cols)


def path_revisions(doc: dict | None) -> list[dict]:
    """How much each report moved the path: the mean change over the quarters it shares with the report before, pp."""
    reps = (doc or {}).get("reports") or []
    out = []
    for a, b in zip(reps, reps[1:], strict=False):
        common = [q for q in b["path"] if q in a["path"]]
        if common:
            out.append({"report": b["report"], "day": b["published"], "revision": float(np.mean([b["path"][q] - a["path"][q] for q in common])),
                        "quarters": len(common), "before": a["report"]})
    return out


def report_day_moves(closes: pd.DataFrame, osebx: pd.Series, groups: dict[str, str], doc: dict | None) -> pd.DataFrame:
    """Per sector group: its move against OSEBX on the days a new path came out, regressed on the path's revision.
    ``beta`` is per cent per +0.25 pp of revision, ``n`` the report days with prices."""
    cols = ["group", "beta", "t", "n"]
    revs = path_revisions(doc)
    if closes is None or closes.empty or osebx is None or osebx.empty or not revs:
        return pd.DataFrame(columns=cols)
    daily, _ = group_returns(closes, groups, freq=None)
    mkt = np.log(osebx).diff()
    rows = []
    for g in daily.columns:
        xs, ys = [], []
        for r in revs:
            d = r["day"]
            if d in daily.index and d in mkt.index and not np.isnan(daily.at[d, g]) and not np.isnan(mkt.at[d]):
                xs.append(r["revision"])
                ys.append(daily.at[d, g] - mkt.at[d])
        if len(xs) >= 3:
            fit = _ols(np.array(ys), np.column_stack([np.ones(len(xs)), np.array(xs)]))
            if fit:
                rows.append({"group": g, "beta": fit[0] * STEP * 100, "t": fit[1], "n": len(xs)})
    return pd.DataFrame(rows, columns=cols)


def moves_count(s: pd.Series | None, weeks: int = 156) -> int:
    """How many times a rate changed in the last ``weeks`` weeks (daily data)."""
    if s is None or len(s) < 2:
        return 0
    s = s[s.index >= s.index[-1] - pd.Timedelta(weeks=weeks)]
    return int((s.diff().abs() > 1e-9).sum())


# ------------------------------------------------------------------------------------------------ html
def _pp(v: float | None, sign: bool = False) -> str:
    return "–" if v is None else tall(v, 2, sign=sign) + (f"{NBSP}pp" if sign else f"{NBSP}%")


def _qname(p: pd.Period) -> str:
    return f"{p.quarter}. kv. {p.year}"


def path_section(doc: dict | None, rate: pd.Series, today: pd.Timestamp, meetings: dict | None, fetched: str) -> str:
    """«Styringsrenten mot rentebanen»: the chart, the table of what was signalled and what happened, and the sources."""
    note = refill_note(today, doc, meetings)
    warn = f'<p class="st-warn">{_E(note)}</p>' if note else ""
    if not doc:
        return f'<h2 id="rentebane">Styringsrenten mot rentebanen</h2><div class="card">{warn}</div>'
    rows = signal_rows(doc, rate)
    newest = doc["reports"][-1]
    last = f"{rate.iloc[-1]:.2f}" if rate is not None and len(rate) else None
    legend = []
    for r in reversed(doc["reports"]):
        rank = len(doc["reports"]) - 1 - doc["reports"].index(r)
        cls = ("rp-new", "rp-mid", "rp-mid2")[rank] if rank < 3 else "rp-old"
        if rank < 3:
            legend.append(f'<span class="rp-key {cls}"><i></i>{_E(r["report"])} ({dato(r["published"])})</span>')
    legend.append('<span class="rp-key rp-old"><i></i>eldre rapporter</span><span class="rp-key rp-act"><i></i>faktisk styringsrente</span>')

    def cell(c):
        if c["said"] is None:
            return '<td>–</td><td>–</td>'
        if c["was"] is None:
            return f'<td>{_pp(c["said"])}</td><td class="src">ikke ferdig</td>'
        gap = c["was"] - c["said"]
        return f'<td>{_pp(c["said"])}</td><td title="{_E(_qname(c["q"]))}: faktisk snitt {_pp(c["was"])}">{_pp(c["was"])} <span class="src">({_pp(gap, True)})</span></td>'

    trs = "".join(
        f'<tr><td class="l"><a href="{_E(r["url"])}" rel="noopener">{_E(r["report"])}</a></td><td class="l">{dato(r["published"])}</td>'
        f'{cell(r["next"])}{cell(r["year"])}'
        f'<td>{"–" if r["gap"] is None else _pp(r["gap"], True)}</td><td>{r["n"]}</td></tr>' for r in reversed(rows))
    table = ('<table class="odds"><thead><tr><th class="l">Rapport</th><th class="l">Lagt frem</th>'
             '<th title="Banens snitt for kvartalet etter rapportens kvartal">Banen, neste kvartal</th><th>Faktisk</th>'
             '<th title="Banens snitt fire kvartaler etter rapportens kvartal">Banen, om ett år</th><th>Faktisk</th>'
             '<th title="Faktisk snitt minus banen, i snitt over alle kvartalene i banen som er ferdige">Snittavvik</th><th title="Ferdige kvartaler i banen">Kvartaler</th></tr></thead>'
             f'<tbody>{trs}</tbody></table>')
    return (f'<h2 id="rentebane">Styringsrenten mot rentebanen</h2><div class="card">{warn}'
            f'<p class="sub" style="margin:0 0 6px">Linjene er rentebanene Norges Bank har lagt frem i de pengepolitiske rapportene; den trappeformede linjen er '
            f'styringsrenten som faktisk gjaldt' + (f' (nå {_pp(float(last))})' if last else "") + '. Der linjen ligger over banene, har renten blitt høyere enn banken signaliserte.</p>'
            f'<div class="rp-legend">{"".join(legend)}</div>'
            '<div class="rp" id="rp-chart" role="img" aria-label="Styringsrenten mot rentebanene i de siste pengepolitiske rapportene"></div>'
            f'{table}'
            '<div class="src">Banen er Norges Banks anslag for styringsrenten som snitt per kvartal, tegnet midt i kvartalet; første kvartal i en bane er delvis historie. Grafen viser renten uke for uke (fredag). '
            '«Faktisk» er snittet av styringsrenten over kvartalets børsdager, regnet av oss fra Norges Banks daglige serie (bare ferdige kvartaler); i parentes faktisk minus banen. '
            f'Kilder: banene er skrevet av fra figurdataene til hver rapport (Norges Bank, lenke i tabellen), kopiert {dato(str(doc.get("copied", "")))}, nyeste {_E(newest["report"])} '
            f'lagt frem {dato(newest["published"])}; styringsrenten fra Norges Banks åpne data (NLOD), hentet {_E(fetched)}. Neste rapport står i <a href="/calendar">Kalender</a>.</div></div>')


def _verdict(t: float, n: int) -> str:
    return "målbar" if abs(t) >= FOLLOWS else "ingen målbar følsomhet"


def sector_section(table: pd.DataFrame, events: pd.DataFrame, series: dict[str, pd.Series], order: list[str], revs: list[dict]) -> str:
    """«Renter og sektorene»: per sector group, the measured link to the short and the long Norwegian rate, and the move
    on report days – with the observation counts, and «ingen målbar følsomhet» where the data shows none."""
    from osloquant.dashboard import macro as mc

    head = '<h2 id="renter-sektorer">Renter og sektorene</h2><div class="card">'
    if table.empty:
        return head + '<p class="empty">Ikke regnet ennå: lageret har for kort kurshistorikk, eller rentene og OSEBX er ikke hentet.</p></div>'
    names = {k: mc.BY_KEY[k].name for k in RATE_DRIVERS}
    th = "".join(f'<th title="{_E(mc.BY_KEY[k].source)}">{_E(names[k])}</th>' for k in RATE_DRIVERS)
    trs, found, none = [], [], []
    for g in order:
        sub = table[table["group"] == g]
        if sub.empty:
            continue
        cells = []
        for k in RATE_DRIVERS:
            r = sub[sub["driver"] == k]
            if r.empty:
                cells.append("<td>–</td>")
                continue
            r = r.iloc[0]
            hit = abs(r["t"]) >= FOLLOWS
            (found if hit else none).append((g, k, r))
            tone = ("pos" if r["t"] > 0 else "neg") + ("3" if abs(r["t"]) >= mc.STRONG else "2") if hit else ""
            cells.append(f'<td class="mx {tone}" title="{_E(gruppe(g))} og {_E(names[k])}: {mc.beta_text(r["beta"])} mot børsen per +0,25 pp, t-verdi {tall(r["t"], 1, sign=True)}, '
                         f'{int(r["n"])} uker, {int(r["stocks"])} aksjer.">' + (f'<b>{mc.beta_text(r["beta"])}</b>' if hit else '<span class="src">ingen målbar</span>')
                         + f' <span class="src">t {tall(r["t"], 1, sign=True)}</span></td>')
        ev = events[events["group"] == g] if not events.empty else events
        if ev is None or ev.empty:
            cells.append("<td>–</td>")
        else:
            e = ev.iloc[0]
            hit = abs(e["t"]) >= FOLLOWS
            cells.append(f'<td title="{int(e["n"])} rapportdager">' + (f'<b>{mc.beta_text(e["beta"])}</b>' if hit else '<span class="src">ingen målbar</span>')
                         + f' <span class="src">t {tall(e["t"], 1, sign=True)}</span></td>')
        stocks = int(sub["stocks"].iloc[0])
        trs.append(f'<tr><td class="l"><b>{_E(g)}</b> <span class="src">{stocks} aksjer</span></td>{"".join(cells)}</tr>')
    n_weeks = int(table["n"].max())
    n_days = int(events["n"].max()) if not events.empty else 0

    def says(items):
        return "; ".join(f'{_E(gruppe(g))} og {_E(names[k].lower() if k == "stat10y" else names[k])}: {mc.beta_text(r["beta"])} per +0,25{NBSP}pp '
                         f'(t {tall(r["t"], 1, sign=True)}, {int(r["n"])} uker)' for g, k, r in items)

    plain = []
    if found:
        plain.append(f'<li><b>Målbar sammenheng:</b> {says(sorted(found, key=lambda x: -abs(x[2]["t"])))}.</li>')
    short_none = [g for g, k, _ in none if k == "stat3m"]
    if len(short_none) == len(table[table["driver"] == "stat3m"]) and short_none:
        plain.append(f'<li><b>Den korte renten:</b> ingen sektorgruppe viser målbar følsomhet for 3 måneders statskasseveksel ({n_weeks} uker). '
                     'Markedets forventning til styringsrenten har ikke skilt gruppene fra børsen i disse dataene.</li>')
    none_long = sorted({g for g, k, _ in none if k == "stat10y"}, key=order.index)
    if none_long:
        plain.append(f'<li><b>Ingen målbar følsomhet for 10 års stat:</b> {_E(", ".join(gruppe(g) for g in none_long))}.</li>')
    if not events.empty:
        hits = events[events["t"].abs() >= FOLLOWS]
        plain.append(f'<li><b>Dagene en ny rentebane kom ({n_days} rapporter):</b> '
                     + ("ingen sektorgruppe har beveget seg målbart mot børsen etter hvor mye banen ble endret. Med så få dager skal det mye til; tallene er med for å vise at de er sjekket."
                        if hits.empty else f'målbart for {_E(", ".join(gruppe(g) for g in hits["group"]))} – men {n_days} dager er svært få observasjoner, og ett utslag kan bære hele sammenhengen.')
                     + "</li>")
    pr, esb = moves_count(series.get("styringsrente")), moves_count(series.get("esb"))
    plain.append(f'<li><b>Ikke målt:</b> styringsrenten selv ({pr} endringer på tre år) og ESB-renten ({esb} endringer) – for få steg til at en ukentlig regresjon sier noe. '
                 '3 måneders statskasseveksel beveger seg hver uke og fanger forventningene til styringsrenten.</li>')
    rev_txt = ", ".join(f'{_E(r["report"])} {tall(r["revision"], 2, sign=True)}' for r in revs)
    return (head + f'<ul class="news">{"".join(plain)}</ul>'
            f'<table class="odds mxt"><thead><tr><th class="l">Sektorgruppe</th>{th}<th title="Gruppens bevegelse mot OSEBX på dagen en ny rentebane kom, per +0,25 pp endring i banen">Rapportdagene</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table>'
            '<div class="src" style="margin-top:6px"><b>Slik er det målt:</b> hver sektorgruppe som én portefølje med lik vekt på aksjene i lageret. Ukentlig avkastning de siste tre årene '
            f'(inntil 156 uker; her {n_weeks}) regnet mot ukentlig endring i renten, med OSEBX i samme regresjon. Tallet er hva gruppen har gjort utover børsen når renten steg 0,25 prosentpoeng; '
            '«målbar» betyr t-verdi 2 eller mer i tallverdi. Rapportdagene: gruppens avkastning minus OSEBX samme dag, regnet mot hvor mye banen ble flyttet '
            f'(snittet av endringene i kvartalene banen deler med forrige rapport: {rev_txt} pp). Kurser: Yahoo Finance via lageret; renter: Norges Bank. '
            'Dette er samvariasjon i våre egne data, ikke årsak og ikke en prognose. Den lange renten kan bevege seg sammen med andre drivere (oljeprisen, kronen, utenlandske renter), så et utslag her kan like gjerne komme fra dem.</div></div>')

