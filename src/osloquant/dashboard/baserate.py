"""Base rates for the model's estimates (DECISIONS D47), after Mauboussin's Base Rate Book and Kahneman's outside view:
before an estimate is trusted, ask how often comparable companies have actually done it.

Two reference classes, each named with its sample and period wherever it is shown:

- **Oslo Børs (the store):** every non-financial company with four annual statements in the store – revenue growth a
  year over three years, and the change in EBITDA margin over the same three years. Small (about 55 companies) and
  one period (2022–2025, which starts at a cyclical peak for energy, shipping and seafood); it is said.
- **Published (resources/base_rates.yaml):** a distribution transcribed from a published study with its source, page
  and sample, when one has been obtained; absent otherwise – never filled in from memory.

A forecast is checked as the share of the reference class that did *at least as well* (for growth and margin
expansion) and *at most as well* (for a decline). Fewer than 20 % on either side – outside the 20th–80th percentile
band – is flagged, in the judgement form (the reason is asked for and stored on the row) and on the report's page.
The forecast is read from the report's published estimates (``estimates_*.json``): revenue growth a year from the
first estimate year three years on, and the EBITDA margin change over the same years.
"""

from __future__ import annotations

import glob
import html
import json
from functools import lru_cache
from pathlib import Path

import yaml

E = html.escape
FLAG_SHARE = 0.20
INFLATION_EST = 0.02          # Norges Bank's inflation target, used to deflate a nominal forecast for a real base rate (EST)
YEARS = 3
PUBLISHED = Path(__file__).resolve().parents[1] / "resources" / "base_rates.yaml"
METRICS = {"rev_cagr": "omsetningsvekst per år (3 år)", "ebitda_m_chg": "endring i EBITDA-margin (3 år, pp)"}


# ------------------------------------------------------------------------------------------------ reference classes
def sample_from(annual: dict[str, list[dict]], groups: dict[str, str] | None = None, skip_groups=("Finance", "Investment companies")) -> list[dict]:
    """From {code: [annual rows with year, revenue, ebitda]} the three-year outcomes per company (the newest four years)."""
    out = []
    for code, rows in annual.items():
        if groups and groups.get(code) in skip_groups:
            continue
        rs = sorted((r for r in rows if r.get("revenue")), key=lambda r: r["year"])[-(YEARS + 1):]
        if len(rs) < YEARS + 1 or rs[-1]["year"] - rs[0]["year"] != YEARS:
            continue
        r0, r1 = rs[0], rs[-1]
        g = (r1["revenue"] / r0["revenue"]) ** (1 / YEARS) - 1 if r0["revenue"] > 0 and r1["revenue"] > 0 else None
        m = None
        if r0.get("ebitda") is not None and r1.get("ebitda") is not None and r0["revenue"] > 0 and r1["revenue"] > 0:
            m = r1["ebitda"] / r1["revenue"] - r0["ebitda"] / r0["revenue"]
        out.append({"code": code, "from": r0["year"], "to": r1["year"], "rev_cagr": g, "ebitda_m_chg": m})
    return out


def local_sample() -> dict:
    """The store's reference class: annual income statements (Yahoo via the store); computed once a day."""
    from datetime import date

    return _local_cached(date.today().isoformat())


@lru_cache(maxsize=2)
def _local_cached(_day: str) -> dict:
    from osloquant.dashboard import market as mk
    from osloquant.domain import IncomeStatement

    snap = mk.snapshot()
    inc = IncomeStatement.query_data(columns=["code", "report_period", "report_date", "total_revenue", "ebitda"])
    inc = inc[inc["report_period"] == "year"]
    annual: dict[str, list[dict]] = {}
    for _, r in inc.iterrows():
        annual.setdefault(r["code"], []).append({"year": int(str(r["report_date"])[:4]), "revenue": _f(r["total_revenue"]), "ebitda": _f(r["ebitda"])})
    rows = sample_from(annual, {c: snap.group(c) for c in snap.names})
    yrs = sorted({(x["from"], x["to"]) for x in rows})
    return {"name": "Oslo Børs (lageret)", "rows": rows, "n": len(rows), "period": ", ".join(f"{a}–{b}" for a, b in yrs[-2:]),
            "source": "Yahoo Finance annual income statements via the oslo-quant store; non-financial companies with four annual years",
            "caveat": "one three-year period that starts at a cyclical peak (2022) for energy, shipping and seafood; nominal, mixed reporting currencies"}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def published() -> list[dict]:
    """Published distributions: [{name, metric, buckets: [[lo, hi, share], ...], n, source, page, sample}] – empty if none."""
    if not PUBLISHED.exists():
        return []
    doc = yaml.safe_load(PUBLISHED.read_text(encoding="utf-8")) or {}
    return [d for d in doc.get("distributions", []) if d.get("buckets") and d.get("source")]


def share_at_least(value: float, values: list[float]) -> float | None:
    v = [x for x in values if x is not None]
    return sum(1 for x in v if x >= value) / len(v) if v else None


def share_at_most(value: float, values: list[float]) -> float | None:
    v = [x for x in values if x is not None]
    return sum(1 for x in v if x <= value) / len(v) if v else None


def bucket_at_least(value: float, buckets: list[list[float]]) -> float:
    """Share of a bucketed distribution at or above ``value`` (uniform within the bucket that holds it)."""
    tot = sum(b[2] for b in buckets)
    s = 0.0
    for lo, hi, share in buckets:
        lo_ = -1e9 if lo is None else lo
        hi_ = 1e9 if hi is None else hi
        if value <= lo_:
            s += share
        elif value < hi_:
            width = hi_ - lo_
            s += share * ((hi_ - value) / width if width < 1e8 else 0.5)
    return s / tot if tot else 0.0


# ------------------------------------------------------------------------------------------------ the forecast
def forecast(est: dict) -> dict | None:
    """Revenue CAGR and EBITDA margin change over three estimate years, from a report's estimates file."""
    yrs, rows = est.get("years") or [], est.get("rows") or {}
    rev, ebitda = rows.get("rev") or [], rows.get("ebitda") or []
    if len(yrs) < YEARS + 1 or len(rev) < YEARS + 1:
        return None
    r0, r1 = rev[0], rev[YEARS]
    out = {"from": yrs[0], "to": yrs[YEARS], "rev_cagr": (r1 / r0) ** (1 / YEARS) - 1 if r0 and r1 and r0 > 0 and r1 > 0 else None, "ebitda_m_chg": None}
    if len(ebitda) > YEARS and r0 and r1 and ebitda[0] is not None and ebitda[YEARS] is not None:
        out["ebitda_m_chg"] = ebitda[YEARS] / r1 - ebitda[0] / r0
    out["ebitda_m_from"] = ebitda[0] / r0 if ebitda and r0 else None
    return out


def check(fc: dict | None, local: dict | None, pub: list[dict] | None = None) -> dict | None:
    """The forecast against each reference class. ``flags`` names every metric outside the 20–80 band."""
    if not fc:
        return None
    pub = pub or []
    items, flags = [], []
    for key, label in METRICS.items():
        v = fc.get(key)
        if v is None:
            continue
        refs = []
        if local and local.get("rows"):
            vals = [x[key] for x in local["rows"]]
            up, down = share_at_least(v, vals), share_at_most(v, vals)
            refs.append({"name": local["name"], "n": sum(x is not None for x in vals), "period": local["period"], "at_least": up, "at_most": down})
        for d in pub:
            if d.get("metric") == key:
                vv = (1 + v) / (1 + INFLATION_EST) - 1 if d.get("real") else v
                up = bucket_at_least(vv, d["buckets"])
                refs.append({"name": d["name"], "n": d.get("n"), "period": d.get("sample"), "at_least": up, "at_most": 1 - up,
                             "source": f'{d["source"]}, {d.get("page", "")}'.strip(", "),
                             "deflated": vv if d.get("real") else None})
        side = None
        for r in refs:
            if r["at_least"] is not None and r["at_least"] < FLAG_SHARE:
                side = "over"
            elif r["at_most"] is not None and r["at_most"] < FLAG_SHARE:
                side = side or "under"
        if side:
            flags.append(f"{label} {_pc(key, v)} is {'above the 80th' if side == 'over' else 'below the 20th'} percentile of " + " and ".join(r["name"] for r in refs
                         if (r["at_least"] if side == "over" else r["at_most"]) is not None and (r["at_least"] if side == "over" else r["at_most"]) < FLAG_SHARE))
        items.append({"metric": key, "label": label, "forecast": v, "refs": refs, "side": side})
    return {"from": fc["from"], "to": fc["to"], "items": items, "flags": flags}


def _pc(key, v) -> str:
    return f"{v * 100:+.1f} %" if key == "rev_cagr" else f"{v * 100:+.1f} pp"


def for_code(code: str, local: dict | None = None) -> dict | None:
    """The check for the newest published report of ``code`` (cases/reports_pdf/<CODE>/estimates_*.json)."""
    from osloquant.dashboard import reportpdf as rpdf

    files = sorted(glob.glob(str(rpdf.folder(code) / "estimates_*.json")))
    if not files:
        return None
    est = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    res = check(forecast(est), local if local is not None else local_sample(), published())
    return res | {"estimates": Path(files[-1]).name} if res else None


# ------------------------------------------------------------------------------------------------ html
def box_html(res: dict | None, f: dict | None = None, with_reason: bool = True) -> str:
    """The base-rate block in the judgement form: each estimate against each reference class, the flags, the reason."""
    if not res:
        return ""
    rows = []
    for it in res["items"]:
        for r in it["refs"]:
            real = f' <span class="src">(reelt {r["deflated"] * 100:+.1f} %: minus {INFLATION_EST:.0%} inflasjon, EST)</span>' if r.get("deflated") is not None else ""
            rows.append(f'<tr><td>{E(it["label"])}</td><td><b>{_pc(it["metric"], it["forecast"])}</b>{real}</td><td style="white-space:normal;text-align:left">{E(r["name"])} <span class="src">(n {r["n"]}, {E(str(r["period"]))}{"; " + E(r["source"]) if r.get("source") else ""})</span></td>'
                        f'<td>{_share(r["at_least"])}</td><td>{_share(r["at_most"])}</td></tr>')
    flagged = bool(res["flags"])
    reason = E(str((f or {}).get("base_rate_reason") or ""))
    return ('<div class="' + ("warn" if flagged else "src") + '" style="margin-top:10px"><b>Base rates (Mauboussin): hvor ofte har sammenlignbare selskaper levert dette?</b>'
            f'<table class="odds"><thead><tr><th>Estimat {res["from"]}–{res["to"]}</th><th>Modellen</th><th>Referanseklasse</th><th>Andel som klarte minst så mye</th>'
            f'<th>Andel som endte på eller under</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            + ("<div><b>Utenfor 20–80-båndet:</b> " + E("; ".join(res["flags"])) + "</div>"
               + (f'<label>Hva skiller selskapet fra de andre? (begrunnelsen lagres på raden)</label><input name="base_rate_reason" value="{reason}">' if with_reason else "")
               if flagged else "")
            + f'<div class="src">Fra rapportens estimater ({E(res.get("estimates", ""))}). Lageret: Yahoo-regnskap, én treårsperiode som starter på en syklustopp – liten og grov referanseklasse. '
            'Mauboussin: reell vekst, globale storselskaper 1950–2015; analytikernes treårsestimater spriker mindre enn utfallene (SD 8,3 % mot 18,7 %, s. 21). '
            'Marginer er seige (r = 0,79 over tre år, s. 59): start fra fjorårets margin og let etter grunner til å avvike.</div></div>')


def _share(v) -> str:
    return "–" if v is None else f"{v * 100:.0f} %"


def row_field(res: dict | None, reason: str | None) -> dict | None:
    """What goes on the judgement row: the forecast, the shares per reference class, the flags and the reason."""
    if not res:
        return None
    return {"from": res["from"], "to": res["to"], "estimates": res.get("estimates"), "flags": res["flags"], "reason": (reason or "").strip() or None,
            "items": [{"metric": i["metric"], "forecast": round(i["forecast"], 5),
                       "refs": [{"name": r["name"], "n": r["n"], "at_least": None if r["at_least"] is None else round(r["at_least"], 3)} for r in i["refs"]]}
                      for i in res["items"]]}
