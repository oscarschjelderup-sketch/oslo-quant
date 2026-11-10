"""The macro picture (D65): the drivers a Norwegian stock picker watches, each with its history, what it did lately, and
how the stocks in the store have moved with it.

Three things live here.

- **The drivers.** Rates, currencies, commodities and the market, each from a free source whose terms allow it
  (docs/dashboard/data-sources.md). The history is fetched into the ``macro`` feed by the evening job; OSEBX comes from
  the store. A page only reads the cache, so every number carries its source, its date and when it was fetched.
- **The strip.** One cell per driver, always the same shape: level, change, a small trend line. Identical cells are
  what makes a row of numbers readable in ten seconds.
- **Sensitivity, measured on our own data.** For every stock and driver: a weekly regression over the last three
  years of the stock's return on the driver's change, with OSEBX beside it so that «everything moves with the market»
  is taken out. The result is co-movement, not cause, and the page says so. A stock «follows» a driver when the
  t-value is 2 or more in absolute value.

Nothing here is a forecast and nothing is a recommendation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from osloquant.dashboard import feeds as fd
from osloquant.dashboard.dates import dato
from osloquant.dashboard.tall import MINUS, NBSP, tall

FEED = "macro"
WEEKS = 156                 # three years of weekly observations in the sensitivity
MIN_WEEKS = 60
MIN_MOVES = 26              # weeks in which the driver actually changed; fewer, and a regression measures two or three events
FOLLOWS = 2.0               # |t| at or above this: the stock has followed the driver
NOT_A_DRIVER = ("osebx", "vix")   # the market and its mood: shown in the strip, never listed as «a driver the stock follows»
STRONG = 3.5


@dataclass(frozen=True)
class Driver:
    key: str
    name: str
    group: str               # Renter, Valuta, Råvarer, Marked
    unit: str
    kind: str                # "rate": changes in percentage points; "price": changes in per cent
    decimals: int
    source: str
    note: str = ""
    weekly: bool = False     # published weekly (the salmon price)
    step: float = 10.0       # the move the sensitivity is stated for: +10 % for a price, +0.25 pp for a rate


DRIVERS: tuple[Driver, ...] = (
    Driver("styringsrente", "Styringsrente", "Renter", "%", "rate", 2, "Norges Bank", step=0.25),
    Driver("stat3m", "3 mnd statskasseveksel", "Renter", "%", "rate", 2, "Norges Bank", "markedets rente tre måneder frem – beveger seg før styringsrenten", step=0.25),
    Driver("stat10y", "10 års stat", "Renter", "%", "rate", 2, "Norges Bank", step=0.25),
    Driver("us10y", "USA 10 år", "Renter", "%", "rate", 2, "Yahoo Finance (^TNX), forsinket", step=0.25),
    Driver("us2y", "USA 2 år", "Renter", "%", "rate", 2, "FRED (DGS2, US Treasury)", "følger forventningene til Fed-renten tettest", step=0.25),
    Driver("fed", "Fed-renten, øvre grense", "Renter", "%", "rate", 2, "FRED (DFEDTARU, Federal Reserve)", step=0.25),
    Driver("usdnok", "USD/NOK", "Valuta", "", "price", 3, "Norges Bank, fixing 14:15"),
    Driver("eurnok", "EUR/NOK", "Valuta", "", "price", 3, "Norges Bank, fixing 14:15"),
    Driver("i44", "Kronekursindeks I44", "Valuta", "", "price", 2, "Norges Bank", "importveid; høyere = svakere krone"),
    Driver("dollar", "Dollarindeks, bred", "Valuta", "", "price", 2, "FRED (DTWEXBGS, Federal Reserve)",
           "handelsveid dollar mot de største handelspartnerne; høyere = sterkere dollar; publiseres ukentlig"),
    Driver("brent", "Brent", "Råvarer", "USD/fat", "price", 2, "Yahoo Finance (BZ=F), forsinket"),
    Driver("gass_ttf", "Gass TTF", "Råvarer", "EUR/MWh", "price", 2, "Yahoo Finance (TTF=F), forsinket"),
    Driver("aluminium", "Aluminium", "Råvarer", "USD/t", "price", 0, "Yahoo Finance (ALI=F), forsinket"),
    Driver("kobber", "Kobber", "Råvarer", "USD/lb", "price", 3, "Yahoo Finance (HG=F), forsinket"),
    Driver("laks", "Laksepris", "Råvarer", "NOK/kg", "price", 2, "SSB tabell 03024", "eksportpris fersk laks, ukentlig – ikke spotpris", weekly=True),
    Driver("kraft_no2", "Kraftpris NO2", "Råvarer", "øre/kWh", "price", 1, "hvakosterstrommen.no (ENTSO-E)", "døgnsnitt av timeprisene, Sør-Norge, uten avgifter"),
    Driver("osebx", "OSEBX", "Marked", "", "price", 0, "Yahoo Finance via lageret, forsinket"),
    Driver("vix", "VIX", "Marked", "", "price", 1, "Yahoo Finance (^VIX), forsinket", "forventet uro i amerikanske aksjer"),
)
BY_KEY = {d.key: d for d in DRIVERS}
#: the front page's strip, in the order a morning reads it
STRIP = ("styringsrente", "stat10y", "usdnok", "eurnok", "i44", "brent", "laks", "osebx")
GROUP_ORDER = ("Renter", "Valuta", "Råvarer", "Marked")
#: the drivers each sector group is expected to care about – shown first on the sector page; the measured
#: sensitivity beside them says whether the stocks actually have
SECTOR_DRIVERS = {
    "Energy": ("brent", "gass_ttf", "usdnok"), "Shipping": ("brent", "usdnok", "us10y"), "Seafood": ("laks", "eurnok", "i44"),
    "Finance": ("styringsrente", "stat3m", "stat10y"), "Industrials & materials": ("aluminium", "kraft_no2", "eurnok", "i44"),
    "Consumer, telecom & real estate": ("styringsrente", "stat10y", "i44"), "Technology & renewables": ("us10y", "stat10y", "kraft_no2"),
    "Investment companies": ("osebx", "stat10y"),
}


def from_fred(d: Driver) -> bool:
    return d.source.startswith("FRED")


def uses_fred(doc: dict | None = None) -> bool:
    """Whether the cached feed holds anything from FRED – then the FRED notice belongs on the page that shows it."""
    doc = fd.read(FEED) if doc is None else doc
    series = (doc or {}).get("series") or {}
    return any((series.get(k) or {}).get("t") for k in fd.MACRO_FRED) or bool((doc or {}).get("releases"))


def fred_notice_html() -> str:
    return f'<span lang="en">{fd.FRED_NOTICE}</span> <a href="{fd.FRED_TERMS}" rel="noopener">FRED API Terms of Use</a>.'


def releases(doc: dict | None = None) -> list[dict]:
    """The coming US release dates from FRED's calendar, as calendar events."""
    doc = fd.read(FEED) if doc is None else doc
    return [{"date": r["date"], "kind": "release", "what": r["what"], "source": "FRED-kalenderen (St. Louis Fed)"} for r in (doc or {}).get("releases") or []]


# ------------------------------------------------------------------------------------------------ the series
def _osebx() -> pd.Series:
    try:
        from osloquant.contract.api import get_data
        from osloquant.domain import Index1dKdata

        df = get_data(Index1dKdata, codes=["OSEBX"], columns=["timestamp", "close"], start_timestamp=pd.Timestamp.now().normalize() - pd.Timedelta(days=365 * 4))
        return pd.Series(dtype=float) if df is None or df.empty else df.dropna().set_index("timestamp")["close"].sort_index()
    except Exception:  # noqa: BLE001 – no index in the store: the cell says so
        return pd.Series(dtype=float)


def load(doc: dict | None = None) -> dict[str, pd.Series]:
    """Every driver's history as a date-indexed series. A driver with nothing fetched is an empty series."""
    doc = fd.read(FEED) if doc is None else doc
    out = {}
    for d in DRIVERS:
        raw = ((doc or {}).get("series") or {}).get(d.key)
        if d.key == "osebx":
            out[d.key] = _osebx()
        elif raw and raw.get("t"):
            out[d.key] = pd.Series(raw["v"], index=pd.to_datetime(raw["t"]), dtype=float).dropna().sort_index()
        else:
            out[d.key] = pd.Series(dtype=float)
    return out


def _back(s: pd.Series, back: pd.Timestamp) -> float | None:
    before = s[s.index <= back]
    return float(before.iloc[-1]) if len(before) else None


def change(d: Driver, now: float, then: float | None) -> float | None:
    """The change as this driver states it: percentage points for a rate, a fraction for a price."""
    if then is None or (d.kind == "price" and not then):
        return None
    return now - then if d.kind == "rate" else now / then - 1


def cell(d: Driver, s: pd.Series) -> dict:
    """What one cell of the strip shows: level, the change since the previous observation, a month and a year back,
    and the last ninety observations for the trend line."""
    if s is None or s.empty:
        return {"key": d.key, "name": d.name, "empty": True, "source": d.source}
    last, day = float(s.iloc[-1]), s.index[-1]
    prev = float(s.iloc[-2]) if len(s) > 1 else None
    return {"key": d.key, "name": d.name, "empty": False, "level": last, "date": day, "prev_date": s.index[-2] if len(s) > 1 else None,
            "d1": change(d, last, prev), "m1": change(d, last, _back(s, day - pd.DateOffset(months=1))),
            "y1": change(d, last, _back(s, day - pd.DateOffset(years=1))), "spark": [float(x) for x in s.iloc[-90:].tolist()],
            "source": d.source, "unit": d.unit, "note": d.note, "kind": d.kind, "decimals": d.decimals, "weekly": d.weekly}


def fmt_level(d: Driver, v: float | None) -> str:
    return "–" if v is None else tall(v, d.decimals) + (f"{NBSP}%" if d.unit == "%" else "")


def fmt_change(d: Driver, v: float | None) -> str:
    """«+0,25 pp» for a rate, «−1,4 %» for a price."""
    if v is None:
        return "–"
    return tall(v, 2, sign=True) + f"{NBSP}pp" if d.kind == "rate" else tall(v * 100, 1, sign=True) + f"{NBSP}%"


def _cls(v: float | None) -> str:
    return "" if v is None or abs(v) < 1e-12 else ("up" if v > 0 else "down")


def sparkline(values: list[float], width: int = 92, height: int = 26) -> str:
    """A small trend line as inline SVG: no library, sharp at every zoom. Green when the window ends above its start,
    red when below – the same rule as the price chart."""
    vals = [v for v in values if v == v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = (width - 2) / (len(vals) - 1)
    pts = " ".join(f"{1 + i * step:.1f},{1 + (height - 2) * (1 - (v - lo) / span):.1f}" for i, v in enumerate(vals))
    colour = "var(--buy)" if vals[-1] > vals[0] else "var(--risk)" if vals[-1] < vals[0] else "var(--muted)"
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" aria-hidden="true">'
            f'<polyline fill="none" stroke="{colour}" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round" points="{pts}"/></svg>')


def cell_html(c: dict, static: bool = False) -> str:
    from osloquant.dashboard.render import E

    d = BY_KEY[c["key"]]
    if c.get("empty"):
        return (f'<div class="mcell empty" title="{E(d.source)}: ikke hentet ennå – kjør oq dashboard --refresh">'
                f'<span class="mname">{E(d.name)}</span><span class="mlevel">–</span><span class="mchg">ikke hentet</span></div>')
    since = "uken før" if c["weekly"] else "forrige notering"
    title = (f'{d.name} {fmt_level(d, c["level"])}{" " + d.unit if d.unit and d.unit != "%" else ""} per {dato(c["date"])}. '
             f'Endring fra {since}: {fmt_change(d, c["d1"])}; siste måned {fmt_change(d, c["m1"])}; siste år {fmt_change(d, c["y1"])}. '
             + (f'{d.note}. ' if d.note else '') + f'Kilde: {d.source}. Linjen viser de siste {len(c["spark"])} noteringene.')
    inner = (f'<span class="mname">{E(d.name)}</span><span class="mlevel">{fmt_level(d, c["level"])}</span>'
             f'<span class="mchg {_cls(c["d1"])}">{fmt_change(d, c["d1"])}</span>{sparkline(c["spark"])}'
             f'<span class="mdate">{dato(c["date"], False)} · 1 mnd <span class="{_cls(c["m1"])}">{fmt_change(d, c["m1"])}</span></span>')
    return (f'<div class="mcell" title="{E(title)}">{inner}</div>' if static
            else f'<a class="mcell" href="/makro#d-{E(d.key)}" title="{E(title)}">{inner}</a>')


def strip_html(series: dict[str, pd.Series] | None = None, keys: tuple[str, ...] = STRIP, static: bool = False) -> str:
    """The macro strip: the same cell for every driver. Shown at the top of the front page and of the macro page."""
    series = load() if series is None else series
    cells = "".join(cell_html(cell(BY_KEY[k], series.get(k, pd.Series(dtype=float))), static) for k in keys)
    return f'<div class="mstrip" id="makrostripe">{cells}</div>'


# ------------------------------------------------------------------------------------------------ sensitivity
def weekly(s: pd.Series) -> pd.Series:
    """The last observation of each week (Friday), carried forward over a week without one."""
    return s.resample("W-FRI").last().ffill() if len(s) else s


def driver_moves(series: dict[str, pd.Series]) -> pd.DataFrame:
    """Weekly changes per driver: percentage points for a rate, log returns for a price."""
    out = {}
    for d in DRIVERS:
        w = weekly(series.get(d.key, pd.Series(dtype=float)))
        if len(w) < MIN_WEEKS:
            continue
        move = w.diff() if d.kind == "rate" else np.log(w.where(w > 0)).diff()
        if int((move.iloc[-WEEKS:].abs() > 1e-9).sum()) < MIN_MOVES:        # the policy rate: a handful of steps in three years
            continue
        out[d.key] = move
    return pd.DataFrame(out)


def sensitivity(closes: pd.DataFrame, series: dict[str, pd.Series], weeks: int = WEEKS) -> pd.DataFrame:
    """One row per stock and driver: the stock's weekly return regressed on the driver's weekly change with the
    OSEBX return beside it. ``beta`` is the stock's move in per cent for the driver's ``step`` (+10 % for a price,
    +0.25 pp for a rate), ``t`` its t-value, ``corr`` the plain correlation, ``n`` the weeks used."""
    moves = driver_moves(series)
    if closes is None or closes.empty or moves.empty:
        return pd.DataFrame(columns=["code", "driver", "beta", "t", "corr", "n"])
    rets = np.log(closes.resample("W-FRI").last().where(lambda x: x > 0)).diff().iloc[-weeks:]
    moves = moves.reindex(rets.index)
    market = moves["osebx"].to_numpy() if "osebx" in moves else None
    R_ = rets.to_numpy()
    rows = []
    for key in moves.columns:
        d = BY_KEY[key]
        x = moves[key].to_numpy()
        with_market = key != "osebx" and market is not None
        base = ~np.isnan(x) & (~np.isnan(market) if with_market else True)
        scale = d.step if d.kind == "rate" else math.log1p(d.step / 100)           # the driver's stated step, in the regression's units
        for j, code in enumerate(rets.columns):
            y = R_[:, j]
            ok = base & ~np.isnan(y)
            n = int(ok.sum())
            if n < MIN_WEEKS:
                continue
            xs, ys = x[ok], y[ok]
            if xs.std() == 0 or ys.std() == 0:
                continue
            X = np.column_stack([np.ones(n), xs, market[ok]]) if with_market else np.column_stack([np.ones(n), xs])
            coef, *_ = np.linalg.lstsq(X, ys, rcond=None)
            resid = ys - X @ coef
            dof = n - X.shape[1]
            var = np.linalg.pinv(X.T @ X)[1, 1] * (resid @ resid / dof) if dof > 0 else 0.0
            se = math.sqrt(var) if var > 0 else None
            rows.append({"code": code, "driver": key, "beta": float(coef[1] * scale * 100), "t": float(coef[1] / se) if se else 0.0,
                         "corr": float(np.corrcoef(ys, xs)[0, 1]), "n": n})
    return pd.DataFrame(rows, columns=["code", "driver", "beta", "t", "corr", "n"])


@lru_cache(maxsize=2)
def _sensitivity_cached(stamp: str) -> pd.DataFrame:
    from osloquant.dashboard import odds as od

    return sensitivity(od.long_closes(), load())


def sensitivities() -> pd.DataFrame:
    """The sensitivity table for the store's stocks, recomputed when the prices or the macro feed change."""
    from osloquant.contract.api import get_coverage
    from osloquant.domain import Stock1dAdjKdata

    try:
        last = get_coverage(Stock1dAdjKdata)["last"]
    except Exception:  # noqa: BLE001
        last = None
    return _sensitivity_cached(f"{last}|{(fd.read(FEED) or {}).get('fetched_at')}")


def measurable(series: dict[str, pd.Series]) -> set[str]:
    """The drivers that have moved often enough for a sensitivity to mean something."""
    return set(driver_moves(series).columns)


def strength(t: float) -> str:
    a = abs(t)
    return "sterk" if a >= STRONG else "tydelig" if a >= FOLLOWS else "svak"


def for_stock(code: str, table: pd.DataFrame | None = None, series: dict[str, pd.Series] | None = None, limit: int = 5) -> list[dict]:
    """The drivers this stock has followed (|t| ≥ 2), strongest first, each with what the driver did the last month."""
    table = sensitivities() if table is None else table
    series = load() if series is None else series
    rows = table[(table["code"] == code) & (table["t"].abs() >= FOLLOWS) & ~table["driver"].isin(NOT_A_DRIVER)]
    out = []
    for r in rows.reindex(rows["t"].abs().sort_values(ascending=False).index).head(limit).to_dict("records"):
        d = BY_KEY[r["driver"]]
        out.append(r | {"name": d.name, "step": d.step, "kind": d.kind, "strength": strength(r["t"]), "cell": cell(d, series.get(d.key, pd.Series(dtype=float)))})
    return out


def sector_matrix(table: pd.DataFrame, groups: dict[str, str]) -> pd.DataFrame:
    """Per sector group and driver: the median t-value of its stocks and how many of them follow the driver."""
    if table.empty:
        return pd.DataFrame()
    t = table.assign(group=table["code"].map(groups)).dropna(subset=["group"])
    g = t.groupby(["group", "driver"])
    return pd.DataFrame({"t": g["t"].median(), "beta": g["beta"].median(), "follow": g["t"].apply(lambda s: int((s.abs() >= FOLLOWS).sum())), "n": g["t"].size()}).reset_index()


def most_sensitive(table: pd.DataFrame, driver: str, n: int = 6) -> list[dict]:
    rows = table[(table["driver"] == driver) & (table["t"].abs() >= FOLLOWS)]
    return rows.reindex(rows["t"].abs().sort_values(ascending=False).index).head(n).to_dict("records")


def step_text(d: Driver) -> str:
    return f"+{tall(d.step, 2)}{NBSP}pp" if d.kind == "rate" else f"+{tall(d.step, 0)}{NBSP}%"


def beta_text(beta: float) -> str:
    return (tall(beta, 1, sign=True) + f"{NBSP}%").replace("-", MINUS)
