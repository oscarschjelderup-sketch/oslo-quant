"""Passes: the decisions not to buy (DECISIONS D54), after Buffett – the biggest mistakes are often the opportunities
understood and not taken, and they never show in the accounts (letter for 1989).

A pass is a row of kind ``pass`` in the judgement log: the company, the date and price (set by the server, as for a
view), the reason (at least fifteen characters) and whether the company was inside the circle of competence – Buffett
counts only those as true omissions. Nothing else is asked: a pass should be cheap, so it is logged.

The record is scored like a view without a target: the total return since the pass against OSEBX, to twelve months.
A pass inside the circle whose stock beat OSEBX by more than 20 percentage points is listed as a *possible omission*
(the threshold is mine, not a source's); outside the circle it is listed but not counted. Provisional until twelve
months have passed, and said so.
"""

from __future__ import annotations

import html

import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard.dates import dato

E = html.escape
REASON_MIN = 15
HORIZON_MONTHS = 12
OMISSION_EXCESS = 0.20


def passes(rows: list[dict], code: str | None = None, analyst: str = jg.DEFAULT_ANALYST) -> list[dict]:
    return [r for r in rows if r.get("kind") == "pass" and (code is None or r["code"] == code) and jg.analyst_of(r) == analyst]


def write(code: str, reason: str, inside: bool, price: float, price_date: str, today: str) -> dict:
    if len((reason or "").strip()) < REASON_MIN:
        raise ValueError(f"say why you pass (at least {REASON_MIN} characters) – the reason is what the review reads")
    return jg.append("pass", dict(code=code, date=today, price=round(float(price), 4), price_date=price_date, reason=reason.strip(),
                                  inside_circle=bool(inside), source="dashboard"))


def score(p: dict, prices: jg.Prices, asof: pd.Timestamp) -> dict:
    start = pd.Timestamp(p["date"])
    end = min(asof, start + pd.DateOffset(months=HORIZON_MONTHS))
    out = {"seq": p["seq"], "code": p["code"], "date": p["date"], "price": p["price"], "reason": p["reason"], "inside": p.get("inside_circle"),
           "final": asof >= start + pd.DateOffset(months=HORIZON_MONTHS), "tsr": None, "excess": None}
    a, b = prices.price_on(prices.adjusted, p["code"], start), prices.price_on(prices.adjusted, p["code"], end)
    if a is None or b is None or b[0] <= a[0]:
        return out
    out["tsr"] = b[1] / a[1] - 1
    idx = prices.index.dropna()
    i0, i1 = idx[idx.index <= start], idx[idx.index <= end]
    if len(i0) and len(i1):
        out["excess"] = out["tsr"] - (float(i1.iloc[-1]) / float(i0.iloc[-1]) - 1)
    out["omission"] = bool(out["inside"] and out["excess"] is not None and out["excess"] > OMISSION_EXCESS)
    return out


def scoring(rows: list[dict], prices: jg.Prices | None = None, asof: pd.Timestamp | None = None) -> dict:
    ps = passes(rows)
    if not ps:
        return {"rows": [], "n": 0, "omissions": 0}
    asof = asof or pd.Timestamp.now().normalize()
    prices = prices or jg.load_prices(start=min(pd.Timestamp(p["date"]) for p in ps) - pd.Timedelta(days=10))
    out = [score(p, prices, asof) for p in ps]
    return {"rows": out, "n": len(out), "omissions": sum(bool(x.get("omission")) for x in out)}


# ------------------------------------------------------------------------------------------------ html
def stock_html(code: str, rows: list[dict]) -> str:
    mine = passes(rows, code)
    earlier = "".join(f'<li>{dato(p["date"])} ved {p["price"]:g}: {E(p["reason"])}{" (innenfor sirkelen)" if p.get("inside_circle") else ""}</li>' for p in mine)
    return (f'<details class="card"><summary><b>Lar du være? Logg det (unnlatelse)</b>{f" – {len(mine)} tidligere" if mine else ""}</summary>'
            f'<form class="judge" method="post" action="/stock/{E(code)}/pass"><label>Hvorfor lar du være å kjøpe nå?</label><input name="reason" minlength="{REASON_MIN}">'
            '<label style="font-weight:600"><input type="checkbox" style="width:auto" name="inside" value="1"> Selskapet er innenfor sirkelen min (jeg forstår det)</label>'
            '<button class="go" type="submit">Logg unnlatelsen</button></form>' + (f'<ul>{earlier}</ul>' if earlier else "")
            + '<div class="src">Buffett (brevet for 1989): de dyreste feilene er mulighetene du forsto og ikke tok – de synes aldri i regnskapet. Kurs og dato settes av serveren; '
            f'raden scores mot OSEBX i {HORIZON_MONTHS} måneder.</div></details>')


def calibration_html(sc: dict) -> str:
    if not sc.get("n"):
        return ('<h2>Unnlatelser (Buffett)</h2><div class="card"><p class="empty">Ingen unnlatelser logget. Logg «lar være» på aksjesiden når du vurderer og '
                'ikke kjøper – ellers kan kostnaden av å la være aldri måles.</p></div>')

    def pc(v):
        return "–" if v is None else f"{v * 100:+.1f} %"
    rows = "".join(f'<tr><td>{E(x["code"])}</td><td>{dato(x["date"])}</td><td>{x["price"]:g}</td><td>{"ja" if x["inside"] else "nei"}</td><td>{pc(x["tsr"])}</td>'
                   f'<td>{pc(x["excess"])}</td><td>{"mulig unnlatelse" if x.get("omission") else ""}</td><td>{"endelig" if x["final"] else "foreløpig"}</td>'
                   f'<td class="src">{E(x["reason"])}</td></tr>' for x in sc["rows"])
    return ('<h2>Unnlatelser (Buffett)</h2><div class="card">'
            f'<p>{sc["n"]} logget; {sc["omissions"]} mulige unnlatelser (innenfor sirkelen og mer enn {OMISSION_EXCESS:.0%} bedre enn OSEBX).</p>'
            '<table class="odds"><thead><tr><th>Selskap</th><th>Dato</th><th>Kurs</th><th>Sirkel</th><th>Avkastning siden</th><th>Mot OSEBX</th><th></th><th>Status</th>'
            f'<th>Grunn</th></tr></thead><tbody>{rows}</tbody></table>'
            '<div class="src">Justerte sluttkurser (utbytte med), OSEBX fra lageret; tolv måneder. Terskelen på 20 pp er min, ikke en kildes.</div></div>')
