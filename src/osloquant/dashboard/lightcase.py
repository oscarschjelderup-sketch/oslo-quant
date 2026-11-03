"""Light cases: one page per company built from what the store already holds, so a view can be formed on many
companies without a full model for each (DECISIONS D31).

Every figure carries where it came from and when: prices from the store (Yahoo, delayed), statements from Yahoo's
annual and quarterly reports in the store, the reporting currency from Yahoo's quote summary, FX from the store's
daily USDNOK/EURNOK closes. Figures are kept in the company's reporting currency (millions) and converted to NOK
only where they meet the share price. The inputs that are judgement – the cost of capital, the long-run growth –
are named EST and shown as such.

What the price asks for:

- operating companies: the value-driver formula EV = NOPAT x (1 - g / ROIC) / (WACC - g), solved for g, the
  perpetual growth in operating profit the enterprise value pays for at today's return on capital;
- banks and insurers (sector group "Finance"): the justified P/B = (ROE - g) / (COE - g), solved for the ROE the
  price pays for.

Both are one-line summaries of a DCF, not a DCF: they say what has to be true, and the view says whether it will be.
The case file is written to ``~/osloquant-home/cases/<CODE>.json`` (private, like the rest of the research book).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

CASE_DIR = "cases"
CURRENCY_FILE = "currency.json"
FIN_GROUPS = {"Finance"}
#: cost of capital by sector group, EST: a round number per business risk, not a computed WACC
WACC_EST = {"Energy": 0.095, "Shipping": 0.10, "Seafood": 0.085, "Industrials & materials": 0.09, "Technology & renewables": 0.095,
            "Consumer, telecom & real estate": 0.08, "Investment companies": 0.09, "Other": 0.09}
COE_EST = 0.10
G_LONG_EST = 0.02
TAX_FALLBACK = 0.22
UNIT = 1e6


# ------------------------------------------------------------------------------------------------ pure computation
def implied_growth(ev: float, nopat: float, roic: float, wacc: float) -> float | None:
    """g in EV = NOPAT (1 - g/ROIC) / (WACC - g); None when there is no economic answer (no profit, no return on
    capital, or a price that would need growth at or above the cost of capital)."""
    if not all(map(math.isfinite, (ev, nopat, roic, wacc))) or nopat <= 0 or roic <= 0 or ev <= 0:
        return None
    den = nopat / roic - ev
    if den == 0:
        return None
    g = (nopat - ev * wacc) / den
    return g if g < wacc - 0.005 else None


def implied_roe(pb: float, coe: float, g: float) -> float | None:
    if not (math.isfinite(pb) and pb > 0):
        return None
    return pb * (coe - g) + g


def ltm(q: pd.DataFrame, col: str) -> tuple[float | None, str | None]:
    """Sum of the last four quarters of ``col`` when they are four consecutive quarters; (value, 'LTM to YYYY-MM-DD')."""
    if q is None or not len(q) or col not in q:
        return None, None
    s = q[["report_date", col]].dropna().sort_values("report_date").tail(4)
    if len(s) < 4:
        return None, None
    span = (pd.Timestamp(s["report_date"].iloc[-1]) - pd.Timestamp(s["report_date"].iloc[0])).days
    if not 250 <= span <= 300:                      # four consecutive quarter ends are ~273 days apart
        return None, None
    return float(s[col].sum()), f"LTM to {pd.Timestamp(s['report_date'].iloc[-1]):%Y-%m-%d}"


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _latest(df: pd.DataFrame, col: str) -> tuple[float | None, str | None]:
    if df is None or not len(df) or col not in df:
        return None, None
    s = df[["report_date", col]].dropna().sort_values("report_date")
    return (float(s[col].iloc[-1]), f"{pd.Timestamp(s['report_date'].iloc[-1]):%Y-%m-%d}") if len(s) else (None, None)


def profit_figures(inc_y: pd.DataFrame, inc_q: pd.DataFrame, cf_y: pd.DataFrame, cf_q: pd.DataFrame) -> dict:
    """Revenue, EBIT, net income, FCF and tax rate: LTM when four consecutive quarters exist, else the last year."""
    out = {}
    for key, frame_q, frame_y, col in (("revenue", inc_q, inc_y, "total_revenue"), ("ebit", inc_q, inc_y, "ebit"),
                                       ("net_income", inc_q, inc_y, "net_income"), ("pretax", inc_q, inc_y, "pretax_income"),
                                       ("tax", inc_q, inc_y, "tax_provision"), ("fcf", cf_q, cf_y, "free_cash_flow")):
        v, label = ltm(frame_q, col)
        if v is None and frame_y is not None and len(frame_y) and col in frame_y:
            newest = frame_y.sort_values("report_date").iloc[-1]          # the newest year only: an older year is not "the last year"
            v = _num(newest[col])
            label = f"FY to {pd.Timestamp(newest['report_date']):%Y-%m-%d}" if v is not None else None
        out[key] = {"value": v, "period": label}
    pre, tax = out["pretax"]["value"], out["tax"]["value"]
    rate = tax / pre if pre and tax is not None and pre > 0 else None
    out["tax_rate"] = {"value": min(max(rate, 0.0), 0.9) if rate is not None else TAX_FALLBACK,
                       "period": out["pretax"]["period"] if rate is not None else "EST (Norwegian corporate rate, no usable tax line)"}
    return out


def annual_table(inc_y: pd.DataFrame, bal_y: pd.DataFrame, cf_y: pd.DataFrame, years: int = 5) -> list[dict]:
    rows = []
    if inc_y is None or not len(inc_y):
        return rows
    for _, r in inc_y.sort_values("report_date").tail(years).iterrows():
        d = pd.Timestamp(r["report_date"])
        b = bal_y[pd.to_datetime(bal_y["report_date"]) == d] if bal_y is not None and len(bal_y) else pd.DataFrame()
        c = cf_y[pd.to_datetime(cf_y["report_date"]) == d] if cf_y is not None and len(cf_y) else pd.DataFrame()
        g = lambda f, k: _num(f[k].iloc[0]) if len(f) and k in f else None  # noqa: E731
        rows.append({"year": int(d.year), "date": f"{d:%Y-%m-%d}", "revenue": _num(r.get("total_revenue")), "ebit": _num(r.get("ebit")),
                     "net_income": _num(r.get("net_income")), "fcf": g(c, "free_cash_flow"), "net_debt": g(b, "net_debt"), "equity": g(b, "total_equity")})
    return rows


def compute(code: str, name: str, group: str, price: float, price_date: str, shares: float | None, currency: str | None, fx: float | None,
            fx_date: str | None, inc_y: pd.DataFrame, inc_q: pd.DataFrame, bal: pd.DataFrame, cf_y: pd.DataFrame, cf_q: pd.DataFrame,
            peers: dict | None = None, built_at: str | None = None) -> dict:
    """The case from frames already loaded (``bal`` holds both annual and quarterly rows). Pure: no store, no network."""
    warn = []
    fin = group in FIN_GROUPS
    bal_q = bal[bal["report_period"] == "quarter"] if len(bal) else bal
    bal_y = bal[bal["report_period"] == "year"] if len(bal) else bal
    newest_bal = bal.sort_values("report_date") if len(bal) else bal
    pf = profit_figures(inc_y, inc_q, cf_y, cf_q)
    nd, nd_date = _latest(newest_bal, "net_debt")
    eq, eq_date = _latest(newest_bal, "total_equity")
    mi, _ = _latest(newest_bal, "minority_interest")
    if shares is None:
        warn.append("no share count in the store: market value not computed")
    if currency and currency != "NOK" and not fx:
        warn.append(f"reports in {currency} but no {currency}NOK rate: multiples not computed")
    to_rep = (1.0 if currency in (None, "NOK") else (1.0 / fx if fx else None))     # NOK -> reporting currency
    mcap_nok = price * shares if shares else None
    mcap = mcap_nok * to_rep if mcap_nok is not None and to_rep else None
    ebit, ni, fcf, rev = (pf[k]["value"] for k in ("ebit", "net_income", "fcf", "revenue"))
    tax = pf["tax_rate"]["value"]
    m: dict = {}
    if nd is None and not fin:
        warn.append("net debt missing in Yahoo's balance sheet: EV is the market value alone (cash not deducted)")
    if mcap:
        m["pe"] = mcap / ni if ni and ni > 0 else None
        m["pb"] = mcap / (eq - (mi or 0)) if eq and eq - (mi or 0) > 0 else None
        m["fcf_yield"] = fcf / mcap if fcf is not None and not fin else None
        if not fin:
            m["ev"] = mcap + (nd or 0) + (mi or 0)
            m["ev_ebit"] = m["ev"] / ebit if ebit and ebit > 0 else None
            m["ev_sales"] = m["ev"] / rev if rev and rev > 0 else None
    ret: dict = {"tax_rate": tax, "tax_period": pf["tax_rate"]["period"]}
    if eq and eq > 0 and ni is not None:
        ret["roe"] = ni / (eq - (mi or 0)) if eq - (mi or 0) > 0 else None
    if not fin and ebit is not None and eq is not None:
        ic = eq + (nd or 0)
        ret["roic"] = ebit * (1 - tax) / ic if ic and ic > 0 else None
    rev_model: dict
    if fin:
        g = G_LONG_EST
        roe_req = implied_roe(m.get("pb") or float("nan"), COE_EST, g)
        rev_model = {"model": "justified P/B", "coe_est": COE_EST, "g_est": g, "implied_roe": roe_req, "actual_roe": ret.get("roe"),
                     "reads": None if roe_req is None else f"the price pays for a {roe_req * 100:.1f} % return on equity for good, at a {COE_EST:.0%} cost of equity and {g:.0%} growth (EST)"}
    else:
        wacc = WACC_EST.get(group, WACC_EST["Other"])
        nopat = ebit * (1 - tax) if ebit is not None else None
        roic = ret.get("roic")
        ev = m.get("ev")
        g = implied_growth(ev or float("nan"), nopat or float("nan"), roic or float("nan"), wacc) if ev else None
        no_growth = nopat / wacc if nopat and nopat > 0 else None
        vs = ev / no_growth - 1 if ev and no_growth else None
        if not ev or not nopat or nopat <= 0:
            reads = "no answer: no market value or no positive operating profit in the last twelve months"
        elif roic is not None and roic < wacc:
            reads = (f"today's {roic * 100:.0f} % return on capital is below the {wacc:.1%} cost of capital (EST): at that return growth destroys "
                     f"value, so the price pays for higher margins or returns, not for growth – EV is {vs * 100:+.0f} % against the no-growth value")
        elif g is None:
            reads = f"the price needs growth at or above the {wacc:.1%} cost of capital (EST): it pays for more than today's business can earn"
        elif vs is not None and vs < 0:
            reads = (f"EV is {abs(vs) * 100:.0f} % below the no-growth value at a {wacc:.1%} cost of capital (EST): the price pays for operating profit "
                     f"falling from the last twelve months' level ({g * 100:+.1f} % a year at today's {roic * 100:.0f} % return on capital) – it treats "
                     "the current result as a peak")
        else:
            reads = (f"at a {wacc:.1%} cost of capital (EST) and today's {roic * 100:.0f} % return on capital, the enterprise value pays for "
                     f"{g * 100:+.1f} % a year growth in operating profit for good (EV {vs * 100:+.0f} % against the no-growth value)")
        rev_model = {"model": "value driver", "wacc_est": wacc, "nopat": nopat, "roic": roic, "implied_g": g, "no_growth_ev": no_growth,
                     "ev_vs_no_growth": vs, "reads": reads}
    through = _latest(bal_q, "total_equity")[1] if len(bal_q) else None
    if through and (pd.Timestamp(price_date) - pd.Timestamp(through)).days > 115:
        warn.append(f"Yahoo has quarterly statements only to {through}: a newer report may be out (see the calendar and NewsWeb) "
                    "and is not in these figures")
    return {"code": code, "name": name, "group": group, "financial": fin, "built_at": built_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price": {"value": price, "date": price_date, "source": "Yahoo Finance via the oslo-quant store (daily close, delayed)"},
            "shares": shares, "currency": {"reporting": currency or "NOK", "fx": fx, "fx_date": fx_date,
                                            "source": "Yahoo quote summary (financialCurrency); FX: store's daily USDNOK/EURNOK close"},
            "mcap_nok": mcap_nok, "profit": {k: pf[k] for k in ("revenue", "ebit", "net_income", "fcf")},
            "balance": {"net_debt": nd, "equity": eq, "minority": mi, "date": nd_date or eq_date},
            "annual": annual_table(inc_y, bal_y, cf_y), "multiples": m, "returns": ret, "reverse": rev_model, "peers": peers or {},
            "statements_source": "Yahoo Finance annual and quarterly statements via the oslo-quant store", "warnings": warn,
            "quarters_through": through}


def peer_stats(rows: list[dict]) -> dict:
    """Medians of the group's multiples from cases computed the same way (the company itself included, marked)."""
    def med(k):
        v = [r[k] for r in rows if r.get(k) is not None and r[k] > 0 and math.isfinite(r[k])]
        return (float(np.median(v)), len(v)) if v else (None, 0)
    out = {}
    for k in ("ev_ebit", "pe", "pb"):
        out[k], out[f"n_{k}"] = med(k)
    out["members"] = sorted(r["code"] for r in rows)
    return out


# ------------------------------------------------------------------------------------------------ store and Yahoo
def case_dir() -> Path:
    from osloquant import judgements as jg

    return jg.home() / CASE_DIR


def case_path(code: str) -> Path:
    return case_dir() / f"{code.upper()}.json"


def load(code: str) -> dict | None:
    p = case_path(code)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def currencies() -> dict:
    p = case_dir() / CURRENCY_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def fetch_currencies(codes: list[str], pause: float = 1.0) -> dict:
    """Reporting currency per code from Yahoo's quote summary, for codes not cached yet (one request each)."""
    import time

    from osloquant.recorders.yahoo import client

    have = currencies()
    sym = _symbols(codes)
    for code in codes:
        if code in have:
            continue
        info = client.fetch_info(sym.get(code, f"{code}.OL"))
        have[code] = {"reporting": info.get("financialCurrency"), "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        time.sleep(pause)
    case_dir().mkdir(parents=True, exist_ok=True)
    (case_dir() / CURRENCY_FILE).write_text(json.dumps(have, indent=1, sort_keys=True), encoding="utf-8")
    return have


def _symbols(codes: list[str]) -> dict[str, str]:
    from osloquant.domain import Stock

    df = Stock.query_data(codes=codes, columns=["code", "symbol"])
    return dict(zip(df["code"], df["symbol"], strict=True)) if len(df) else {}


def _frames(code: str) -> tuple[pd.DataFrame, ...]:
    from osloquant.domain import BalanceSheet, CashFlowStatement, IncomeStatement

    inc = IncomeStatement.query_data(code=code)
    bal = BalanceSheet.query_data(code=code)
    cf = CashFlowStatement.query_data(code=code)
    split = lambda f, p: f[f["report_period"] == p] if len(f) else f  # noqa: E731
    return split(inc, "year"), split(inc, "quarter"), bal, split(cf, "year"), split(cf, "quarter")


def fx_rate(currency: str | None, day: pd.Timestamp) -> tuple[float | None, str | None]:
    if currency in (None, "NOK"):
        return 1.0, None
    from osloquant.domain import Currency1dKdata

    df = Currency1dKdata.query_data(code=f"{currency}NOK", columns=["timestamp", "close"], end_timestamp=day)
    if not len(df):
        return None, None
    last = df.sort_values("timestamp").iloc[-1]
    return float(last["close"]), f"{pd.Timestamp(last['timestamp']):%Y-%m-%d}"


def _shares(bal: pd.DataFrame, inc_q: pd.DataFrame, inc_y: pd.DataFrame) -> float | None:
    for frame, col in ((bal, "shares_outstanding"), (inc_q, "diluted_shares"), (inc_y, "diluted_shares")):
        v, _ = _latest(frame, col)
        if v:
            return v
    return None


def _records(df: pd.DataFrame) -> list[dict]:
    """A statements frame as plain records: dates as strings, NaN as None, the store's bookkeeping columns dropped."""
    if df is None or not len(df):
        return []
    keep = [c for c in df.columns if c not in ("id", "entity_id", "timestamp", "provider", "code")]
    out = []
    for _, r in df.sort_values("report_date").iterrows():
        rec = {}
        for c in keep:
            v = r[c]
            if isinstance(v, pd.Timestamp):
                rec[c] = f"{v:%Y-%m-%d}"
            elif isinstance(v, float) and not math.isfinite(v):
                rec[c] = None
            elif hasattr(v, "item"):
                rec[c] = v.item()
            else:
                rec[c] = v
        out.append(rec)
    return out


def export_statements(code: str, snap=None, write: bool = True) -> dict:
    """Every statement line the store holds for ``code`` – annual and quarterly income statement, balance sheet and
    cash flow as Yahoo reports them – with the price, share count and reporting currency, written to
    ``cases/<CODE>.statements.json`` for the Equity Research Toolkit's case factory (`new_case.py`)."""
    from osloquant.dashboard import market as mk

    snap = snap or mk.snapshot()
    code = code.upper()
    inc_y, inc_q, bal, cf_y, cf_q = _frames(code)
    if not len(inc_y) and not len(inc_q):
        raise ValueError(f"no statements for {code} in the store")
    lp = mk.last_price(snap, code)
    rep = (currencies().get(code) or {}).get("reporting")
    fx, fx_date = fx_rate(rep, lp[1]) if lp else (None, None)
    bal_y = bal[bal["report_period"] == "year"] if len(bal) else bal
    bal_q = bal[bal["report_period"] == "quarter"] if len(bal) else bal
    prices_ye = {}
    if code in snap.panel["close"].columns:
        c = snap.panel["close"][code].dropna()
        for d in inc_y["report_date"] if len(inc_y) else []:
            upto = c[c.index <= pd.Timestamp(d)]
            if len(upto):
                prices_ye[f"{pd.Timestamp(d):%Y-%m-%d}"] = {"close": float(upto.iloc[-1]), "date": f"{upto.index[-1]:%Y-%m-%d}"}
    doc = {"code": code, "name": snap.names.get(code, code), "group": snap.group(code), "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "prices_ye": prices_ye,
           "price": {"value": lp[0], "date": f"{lp[1]:%Y-%m-%d}", "source": mk.PRICE_SOURCE} if lp else None,
           "shares": _shares(bal, inc_q, inc_y), "currency": {"reporting": rep or "NOK", "fx": fx, "fx_date": fx_date, "source": "Yahoo quote summary; FX: store's daily close"},
           "unit": "reporting currency, units as Yahoo reports them (not millions)",
           "annual": {"income": _records(inc_y), "balance": _records(bal_y), "cashflow": _records(cf_y)},
           "quarterly": {"income": _records(inc_q), "balance": _records(bal_q), "cashflow": _records(cf_q)},
           "source": "Yahoo Finance annual and quarterly statements via the oslo-quant store (oq case export)"}
    if write:
        case_dir().mkdir(parents=True, exist_ok=True)
        (case_dir() / f"{code}.statements.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return doc


def build(code: str, snap=None, write: bool = True, with_peers: bool = True) -> dict:
    """The light case for ``code`` from the store, with the group's medians computed the same way."""
    from osloquant.dashboard import market as mk

    snap = snap or mk.snapshot()
    code = code.upper()
    cur = currencies()

    def one(c: str, peers: dict | None = None) -> dict | None:
        lp = mk.last_price(snap, c)
        if not lp:
            return None
        inc_y, inc_q, bal, cf_y, cf_q = _frames(c)
        if not len(inc_y) and not len(inc_q):
            return None
        rep = (cur.get(c) or {}).get("reporting")
        fx, fx_date = fx_rate(rep, lp[1])
        return compute(c, snap.names.get(c, c), snap.group(c), lp[0], f"{lp[1]:%Y-%m-%d}", _shares(bal, inc_q, inc_y), rep, fx, fx_date,
                       inc_y, inc_q, bal, cf_y, cf_q, peers)

    peers = None
    if with_peers:
        group = snap.group(code)
        members = [c for c in snap.names if snap.group(c) == group]
        rows = []
        for c in members:
            if c != code and c not in cur:
                continue                                  # no reporting currency known: its multiples would be wrong
            x = one(c)
            if x:
                rows.append({"code": c, **{k: x["multiples"].get(k) for k in ("ev_ebit", "pe", "pb")}})
        peers = peer_stats(rows) | {"group": group, "note": "medians over the group's stocks with a known reporting currency, same method"}
    case = one(code, peers)
    if case is None:
        raise ValueError(f"no price or statements for {code} in the store")
    if (cur.get(code) or {}).get("reporting") is None:
        case["warnings"].append("reporting currency unknown – run oq case build with --refresh")
    if write:
        case_dir().mkdir(parents=True, exist_ok=True)
        case_path(code).write_text(json.dumps(case, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return case
