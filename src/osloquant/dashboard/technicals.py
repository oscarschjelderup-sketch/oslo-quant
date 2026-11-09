"""Technical indicators for the stock page's «Teknisk» tab: moving averages, RSI, MACD and volume against its own
averages, computed from the store's daily closes. Every row carries a value and, where the indicator is one of the
signals measured in ``resources/signal_odds.yaml``, that signal's measured odds after cost and the number of historical
cases. No row carries a buy, sell or neutral label: the dashboard never labels (DECISIONS D57)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from osloquant import signals as sg
from osloquant.dashboard.dates import dato


@dataclass
class Row:
    label: str
    value: str
    detail: str = ""
    #: the measured signal this row relates to, or None when nothing in signal_odds.yaml measures it
    signal: str | None = None
    #: whether that signal's condition holds on the newest session (the odds then apply to today)
    active: bool | None = None
    odds: dict = field(default_factory=dict)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def _odds_for(signal: str | None, odds_doc: dict | None) -> dict:
    if not signal:
        return {}
    o = ((odds_doc or {}).get("signals") or {}).get(signal) or {}
    r = o.get("robustness") or {}
    return {"exc20": o.get("exc20"), "exc60": o.get("exc60"), "hit20": o.get("hit20"), "n": o.get("events"), "grade60": r.get("grade60"),
            "cost": ((odds_doc or {}).get("measured") or {}).get("round_trip_cost", 0.005)}


def _last_cross(a: pd.Series, b: pd.Series) -> tuple[str | None, pd.Timestamp | None]:
    """The newest session where ``a`` crossed ``b``: ('over' | 'under', date)."""
    both = pd.concat([a, b], axis=1).dropna()
    if both.empty:
        return None, None
    d = (both.iloc[:, 0] > both.iloc[:, 1]).astype(int).diff().dropna()
    ev = d[d != 0]
    if ev.empty:
        return None, None
    return ("over" if ev.iloc[-1] > 0 else "under"), ev.index[-1]


def _pct(v: float | None, d: int = 1) -> str:
    return "–" if v is None or v != v else f"{v * 100:+.{d}f} %"


def rows(close: pd.Series, volume: pd.Series | None, high: pd.Series | None = None, odds_doc: dict | None = None) -> list[Row]:
    """Every indicator row for one stock from its daily closes (and volume / high where given), newest session last."""
    c = close.dropna()
    if len(c) < 2:
        return []
    px = float(c.iloc[-1])
    odds_doc = odds_doc if odds_doc is not None else sg.load_odds()
    out: list[Row] = []
    # moving averages: value, distance from the price; the 20/60 cross is the only measured pair
    for n in (20, 50, 200):
        if len(c) >= n:
            ma = float(c.rolling(n).mean().iloc[-1])
            out.append(Row(f"SMA {n}", f"{ma:.2f}", f"kursen {_pct(px / ma - 1)} fra snittet"))
        else:
            out.append(Row(f"SMA {n}", "–", f"for kort historikk ({len(c)} økter)"))
    if len(c) >= 60:
        ma20, ma60 = c.rolling(20).mean(), c.rolling(60).mean()
        side, when = _last_cross(ma20.dropna(), ma60.dropna())
        above = float(ma20.iloc[-1]) > float(ma60.iloc[-1])
        signal = "Golden cross MA 20/60" if above else "Death cross MA 20/60"
        out.append(Row("MA 20/60", f"{float(ma20.iloc[-1]):.2f} / {float(ma60.iloc[-1]):.2f}",
                       (f"MA20 {'over' if above else 'under'} MA60" + (f" siden {dato(when)}" if when is not None else "")),
                       signal=signal, active=when is not None and (c.index[-1] - when).days <= 10, odds=_odds_for(signal, odds_doc)))
    # RSI and MACD: values only – not measured as signals
    if len(c) > 15:
        r = float(sg.rsi(c.to_frame()).iloc[-1, 0])
        out.append(Row("RSI 14", f"{r:.0f}", "0–100; Wilder-glatting"))
    if len(c) >= 35:
        line, sig, hist = macd(c)
        out.append(Row("MACD 12/26/9", f"{float(line.iloc[-1]):.2f}", f"signallinje {float(sig.iloc[-1]):.2f}, histogram {float(hist.iloc[-1]):+.2f}"))
    # the measured price signals as state rows: 52-week high, 60-day high/low, drawdown, channel
    if high is not None and len(high.dropna()) >= 250:
        h250 = float(high.dropna().iloc[-251:-1].max())
        out.append(Row("52 ukers høy", f"{h250:.2f}", f"kursen {_pct(px / h250 - 1)} fra toppen", signal="New 52-week high", active=px > h250,
                       odds=_odds_for("New 52-week high", odds_doc)))
    if high is not None and len(high.dropna()) >= 61:
        h60 = float(high.dropna().iloc[-61:-1].max())
        out.append(Row("60 dagers høy", f"{h60:.2f}", f"kursen {_pct(px / h60 - 1)} fra toppen; bruddet er målt sammen med volum over 1,5 × snittet",
                       signal="Breakout 60d high + volume", active=px > h60 and _volume_confirms(volume), odds=_odds_for("Breakout 60d high + volume", odds_doc)))
        dd = px / float(high.dropna().iloc[-60:].max()) - 1
        out.append(Row("Fall fra 60 dagers høy", _pct(dd), "signalet er målt ved første dag under −10 %", signal="Drawdown 10% from 60d high", active=dd < sg.DRAWDOWN,
                       odds=_odds_for("Drawdown 10% from 60d high", odds_doc)))
    if len(c) >= 61:
        lo60 = float(c.iloc[-61:-1].min())
        out.append(Row("60 dagers lav", f"{lo60:.2f}", f"kursen {_pct(px / lo60 - 1)} fra bunnen", signal="Breakdown below 60d low", active=px < lo60,
                       odds=_odds_for("Breakdown below 60d low", odds_doc)))
    if len(c) >= sg.CHANNEL_DAYS:
        slope = float(sg.channel_slope(c.to_frame()).iloc[-1, 0])
        pos = float(sg.channel_position(c.to_frame()).iloc[-1, 0])
        rising, falling = slope > sg.CHANNEL_SLOPE, slope < -sg.CHANNEL_SLOPE
        signal = "Rising channel entry" if rising else "Falling channel entry" if falling else None
        out.append(Row("Kanal 120 d", f"{slope * 100:+.0f} %/år", f"kursen {pos * 100:.0f} % opp i kanalen (0 = gulv, 100 = tak); "
                       + ("stigende" if rising else "fallende" if falling else "sidelengs"), signal=signal, active=bool(signal), odds=_odds_for(signal, odds_doc)))
    # volume against its own averages
    if volume is not None:
        v = volume.reindex(c.index).dropna()
        if len(v) >= 5:
            today = float(v.iloc[-1])
            parts = []
            for lab, n in (("1 u", 5), ("1 m", 21), ("3 m", 63), ("1 år", 250)):
                if len(v) > n:
                    avg = float(v.iloc[-n - 1:-1].mean())
                    parts.append(f"{lab} {today / avg:.2f}×" if avg else f"{lab} –")
            out.append(Row("Volum mot snitt", f"{today:,.0f}".replace(",", " "), "dagens volum delt på snittet over " + " · ".join(parts)))
    return out


def _volume_confirms(volume: pd.Series | None) -> bool:
    if volume is None:
        return False
    v = volume.dropna()
    if len(v) < 21:
        return False
    return float(v.iloc[-1]) > sg.VOLUME_RATIO * float(v.iloc[-21:-1].mean())
