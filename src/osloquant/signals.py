"""Signal watch: technical signals of the Investtech kind, each tagged with its measured odds, and the research book.

Investtech-style signals (a breakout above resistance, a new 52-week high, a rising trend channel, a death cross)
are popular because they are easy to see. Whether they pay is an empirical question, so this module measures
them on the store's own history before it raises an alert: every alert carries the signal's average forward
excess return over the equal-weighted universe (10, 20 and 60 sessions after the signal, entry at the next open)
and the hit rate, from ``oq signals score``. The honest summary of that scorecard on 2010-2026 is that no BUY
signal has an edge after a 0.5 % round trip over 20 sessions; the SELL-side signals (a breakdown below the
60-day low, a death cross) carry more information than the buys. The watch therefore has two jobs:

- a timing and risk layer on fundamental cases (the research book, ``~/osloquant-home/researchbook.yaml``: the
  companies with a written case, their target price, bear value and the dates that will test the case), and
- a daily scan of the universe, written as a digest and, on Windows, raised as a toast notification.

Nothing here trades or advises; it reports what the bars did and what such bars have meant before.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

BUY, RISK, INFO = "BUY", "RISK", "INFO"
HORIZONS = (10, 20, 60)
ROUND_TRIP_COST = 0.005
VOLUME_RATIO = 1.5
CHANNEL_DAYS = 120
CHANNEL_SLOPE = 0.20          # annualised log-slope that counts as a rising (or, negated, falling) channel
DRAWDOWN = -0.10
ODDS_FILE = "resources/signal_odds.yaml"
BOOK_FILE = "researchbook.yaml"


# ------------------------------------------------------------------------------------------------ indicators
def rsi(close: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def channel_slope(close: pd.DataFrame, n: int = CHANNEL_DAYS) -> pd.DataFrame:
    """Annualised slope of a log-price regression over the last ``n`` sessions: the trend channel's direction."""
    x = np.arange(n, dtype=float)
    xm = x.mean()
    denom = ((x - xm) ** 2).sum()
    y = np.log(close)
    return y.rolling(n).apply(lambda s: ((x - xm) * (s - s.mean())).sum() / denom, raw=True) * 252


def channel_position(close: pd.DataFrame, n: int = CHANNEL_DAYS) -> pd.DataFrame:
    """Where the price sits in its regression channel: 0 = on the floor, 1 = on the ceiling (clipped)."""
    x = np.arange(n, dtype=float)
    xm = x.mean()
    denom = ((x - xm) ** 2).sum()

    def pos(s: np.ndarray) -> float:
        y = np.log(s)
        b = ((x - xm) * (y - y.mean())).sum() / denom
        a = y.mean() - b * xm
        resid = y - (a + b * x)
        width = resid.max() - resid.min()
        return 0.5 if width <= 0 else float(np.clip((resid[-1] - resid.min()) / width, 0, 1))

    return close.rolling(n).apply(pos, raw=True)


def indicators(P: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    C, H, L, V = P["close"], P["high"], P["low"], P["volume"]
    return dict(
        hi20=H.rolling(20).max().shift(1),
        hi60=H.rolling(60).max().shift(1),
        hi250=H.rolling(250).max().shift(1),
        lo60=L.rolling(60).min().shift(1),
        vol20=V.rolling(20).mean(),
        ma20=C.rolling(20).mean(),
        ma60=C.rolling(60).mean(),
        rsi=rsi(C),
        slope=channel_slope(C),
        dd60=C / H.rolling(60).max() - 1,
    )


def _edge(state: pd.DataFrame) -> pd.DataFrame:
    """True on the first session a state holds (the state yesterday was False or unknown)."""
    return state & ~state.shift(1).fillna(False).astype(bool)


def signal_frames(P: dict[str, pd.DataFrame], ind: dict[str, pd.DataFrame] | None = None) -> dict[str, tuple[str, pd.DataFrame]]:
    """Every signal as (kind, boolean frame): True on the session the signal fires."""
    ind = ind or indicators(P)
    C, V = P["close"], P["volume"]
    volconf = V > VOLUME_RATIO * ind["vol20"]
    rising = (ind["slope"] > CHANNEL_SLOPE) & (C > ind["ma20"])
    falling = (ind["slope"] < -CHANNEL_SLOPE) & (C < ind["ma20"])
    frames = {
        "Breakout 60d high + volume": (BUY, (C > ind["hi60"]) & volconf),
        "Breakout 20d high + volume": (BUY, (C > ind["hi20"]) & volconf),
        "New 52-week high": (BUY, C > ind["hi250"]),
        "Rising channel entry": (BUY, _edge(rising)),
        "Golden cross MA 20/60": (INFO, (ind["ma20"] > ind["ma60"]) & (ind["ma20"].shift(1) <= ind["ma60"].shift(1))),
        "Breakdown below 60d low": (RISK, C < ind["lo60"]),
        "Death cross MA 20/60": (RISK, (ind["ma20"] < ind["ma60"]) & (ind["ma20"].shift(1) >= ind["ma60"].shift(1))),
        "Drawdown 10% from 60d high": (RISK, _edge(ind["dd60"] < DRAWDOWN)),
        "Falling channel entry": (RISK, _edge(falling)),
    }
    return {k: (kind, f.fillna(False).astype(bool)) for k, (kind, f) in frames.items()}


# ------------------------------------------------------------------------------------------------ data
def load_panel(start=None, codes: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Adjusted daily bars from the store as wide frames, one per column, codes as columns."""
    from osloquant.contract.api import get_data
    from osloquant.domain import Stock1dAdjKdata

    df = get_data(
        Stock1dAdjKdata,
        columns=["code", "timestamp", "open", "high", "low", "close", "volume"],
        start_timestamp=start,
        codes=codes,
    )
    if df.empty:
        return {k: pd.DataFrame() for k in ("open", "high", "low", "close", "volume")}
    df = df.dropna(subset=["close"]).sort_values(["code", "timestamp"])
    return {k: df.pivot(index="timestamp", columns="code", values=k) for k in ("open", "high", "low", "close", "volume")}


def stock_names() -> dict[str, str]:
    from osloquant.contract.api import get_data
    from osloquant.domain import Stock

    df = get_data(Stock, columns=["code", "name"])
    return dict(zip(df["code"], df["name"], strict=True)) if not df.empty else {}


# ------------------------------------------------------------------------------------------------ odds
def odds_path() -> Path:
    return Path(str(resources.files("osloquant").joinpath(ODDS_FILE)))


def load_odds(path: Path | None = None) -> dict:
    path = path or odds_path()
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def scorecard(P: dict[str, pd.DataFrame], horizons=HORIZONS) -> pd.DataFrame:
    """Forward returns after every signal: entry at the next open, exit at the close ``h`` sessions after the
    signal; excess = minus the equal-weighted universe over the same window. One row per signal."""
    C, opens = P["close"], P["open"]
    n_days = len(C)
    fwd = {h: C.shift(-h) / opens.shift(-1) - 1 for h in horizons}
    ew = {h: fwd[h].mean(axis=1) for h in horizons}
    rows = []
    for name, (kind, sig) in signal_frames(P).items():
        row: dict = dict(signal=name, kind=kind, events=int(sig.values.sum()), per_month=float(sig.values.sum() / max(n_days / 21, 1)))
        for h in horizons:
            raw = fwd[h].where(sig).stack().dropna()
            exc = fwd[h].sub(ew[h], axis=0).where(sig).stack().dropna()
            row[f"raw{h}"] = float(raw.mean()) if len(raw) else np.nan
            row[f"exc{h}"] = float(exc.mean()) if len(exc) else np.nan
            row[f"hit{h}"] = float((exc > 0).mean()) if len(exc) else np.nan
            row[f"t{h}"] = float(exc.mean() / exc.std() * np.sqrt(len(exc))) if len(exc) > 2 and exc.std() > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("signal")


def write_odds(table: pd.DataFrame, start: str, end: str, universe: int, path: Path | None = None) -> Path:
    path = path or odds_path()
    doc = {
        "measured": {"from": start, "to": end, "stocks": universe, "entry": "next open", "excess": "vs equal-weighted universe",
                     "round_trip_cost": ROUND_TRIP_COST},
        "signals": {
            name: {k: (None if v != v else round(float(v), 4)) for k, v in row.items() if k != "kind"} | {"kind": row["kind"]}
            for name, row in table.to_dict("index").items()
        },
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------------------------ scan
@dataclass(frozen=True)
class Alert:
    code: str
    name: str
    signal: str
    kind: str
    session: str
    price: float
    detail: str
    #: measured odds of this signal type: excess return over 20 and 60 sessions, hit rate (fractions)
    exc20: float | None = None
    exc60: float | None = None
    hit20: float | None = None


def _fmt_odds(a: Alert) -> str:
    if a.exc20 is None:
        return "no odds measured"
    return f"exc {a.exc20 * 100:+.1f}% / {a.exc60 * 100:+.1f}% (20/60 d), hit {a.hit20 * 100:.0f}%"


def scan(P: dict[str, pd.DataFrame], asof: pd.Timestamp | None = None, names: dict[str, str] | None = None,
         odds: dict | None = None) -> list[Alert]:
    """The signals that fired on the newest session (or on ``asof``), with their odds."""
    if P["close"].empty:
        return []
    ind = indicators(P)
    frames = signal_frames(P, ind)
    day = P["close"].index[-1] if asof is None else P["close"].index[P["close"].index <= pd.Timestamp(asof)][-1]
    names = names or {}
    odds = load_odds() if odds is None else odds
    sig_odds = odds.get("signals", {})
    alerts = []
    for sname, (kind, f) in frames.items():
        if day not in f.index:
            continue
        for code in f.columns[f.loc[day].values]:
            price = float(P["close"].at[day, code])
            detail = _detail(sname, code, day, P, ind)
            o = sig_odds.get(sname, {})
            alerts.append(Alert(code, names.get(code, code), sname, kind, f"{day:%Y-%m-%d}", price, detail,
                                o.get("exc20"), o.get("exc60"), o.get("hit20")))
    order = {BUY: 0, RISK: 1, INFO: 2}
    return sorted(alerts, key=lambda a: (order[a.kind], a.signal, a.code))


def _detail(sname: str, code: str, day: pd.Timestamp, P: dict, ind: dict) -> str:
    C, V = P["close"], P["volume"]
    px = C.at[day, code]
    vr = V.at[day, code] / ind["vol20"].at[day, code] if ind["vol20"].at[day, code] else np.nan
    if sname.startswith("Breakout 60d"):
        return f"close {px:.2f} above the 60-day high {ind['hi60'].at[day, code]:.2f}; volume {vr:.1f}x the 20-day average"
    if sname.startswith("Breakout 20d"):
        return f"close {px:.2f} above the 20-day high {ind['hi20'].at[day, code]:.2f}; volume {vr:.1f}x the 20-day average"
    if sname.startswith("New 52"):
        return f"close {px:.2f} above the 250-day high {ind['hi250'].at[day, code]:.2f}"
    if "channel" in sname:
        return f"120-day channel slope {ind['slope'].at[day, code] * 100:+.0f}%/yr; RSI {ind['rsi'].at[day, code]:.0f}"
    if "cross" in sname:
        return f"MA20 {ind['ma20'].at[day, code]:.2f} vs MA60 {ind['ma60'].at[day, code]:.2f}"
    if sname.startswith("Breakdown"):
        return f"close {px:.2f} below the 60-day low {ind['lo60'].at[day, code]:.2f}"
    if sname.startswith("Drawdown"):
        return f"{ind['dd60'].at[day, code] * 100:.1f}% below the 60-day high"
    return ""


def status(P: dict[str, pd.DataFrame], code: str) -> dict:
    """Where one stock stands on the newest session: price, changes, channel, distances to the recent extremes."""
    C, H, L = P["close"], P["high"], P["low"]
    if code not in C.columns:
        return {"code": code, "sessions": 0}
    c = C[code].dropna()
    day = c.index[-1]
    px = float(c.iloc[-1])
    n = len(c)
    out: dict = {"code": code, "session": f"{day:%Y-%m-%d}", "price": px, "sessions": n,
                 "chg_1d": float(c.iloc[-1] / c.iloc[-2] - 1) if n > 1 else None,
                 "chg_5d": float(c.iloc[-1] / c.iloc[-6] - 1) if n > 5 else None,
                 "chg_20d": float(c.iloc[-1] / c.iloc[-21] - 1) if n > 20 else None,
                 "hi60": float(H[code].dropna().iloc[-60:].max()) if n >= 2 else None,
                 "lo60": float(L[code].dropna().iloc[-60:].min()) if n >= 2 else None,
                 "rsi": float(rsi(c.to_frame()).iloc[-1, 0]) if n > 15 else None,
                 "ma20": float(c.rolling(20).mean().iloc[-1]) if n >= 20 else None,
                 "ma60": float(c.rolling(60).mean().iloc[-1]) if n >= 60 else None}
    if n >= CHANNEL_DAYS:
        out["slope"] = float(channel_slope(c.to_frame()).iloc[-1, 0])
        out["channel_pos"] = float(channel_position(c.to_frame()).iloc[-1, 0])
    else:
        out["slope"] = out["channel_pos"] = None
    return out


def trend_words(st: dict) -> str:
    if st.get("slope") is None:
        return f"too short a history for a channel ({st.get('sessions', 0)} sessions)"
    s, p = st["slope"], st["channel_pos"]
    direction = "rising" if s > CHANNEL_SLOPE else "falling" if s < -CHANNEL_SLOPE else "sideways"
    where = "near the floor" if p < 0.25 else "near the ceiling" if p > 0.75 else "mid-channel"
    return f"{direction} 120-day channel ({s * 100:+.0f}%/yr), price {where}"


# ------------------------------------------------------------------------------------------------ research book
def home() -> Path:
    from osloquant.env import init_env, oq_env

    if not oq_env:
        init_env()
    return Path(oq_env["home"])


def book_path() -> Path:
    return home() / BOOK_FILE


def load_book(path: Path | None = None) -> list[dict]:
    path = path or book_path()
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = doc.get("entries", doc if isinstance(doc, list) else [])
    for e in entries:
        e["code"] = str(e["code"]).upper().removesuffix(".OL")
    return entries


def book_lines(entry: dict, st: dict, alerts: list[Alert], today: pd.Timestamp) -> list[str]:
    """The digest lines for one research-book company."""
    code = entry["code"]
    lines = [f"### {entry.get('name', code)} ({code}) – {entry.get('rating', '?')} TP {entry.get('target', '?')}"]
    if not st.get("price"):
        lines.append("- no bars in the store yet")
        return lines
    px = st["price"]
    tp, bear, bull, dcf = entry.get("target"), entry.get("bear"), entry.get("bull"), entry.get("dcf")
    bits = [f"price {px:.2f} ({st['session']})"]
    if st.get("chg_1d") is not None:
        bits.append(f"{st['chg_1d'] * 100:+.1f}% today")
    if st.get("chg_20d") is not None:
        bits.append(f"{st['chg_20d'] * 100:+.1f}% 20d")
    p0 = entry.get("price_at_valuation")
    if p0:
        bits.append(f"{(px / p0 - 1) * 100:+.1f}% since the case ({entry.get('valuation_date', '')} at {p0})")
    lines.append("- " + "; ".join(bits))
    val = []
    if tp:
        val.append(f"upside to TP {tp}: {(tp / px - 1) * 100:+.0f}%")
    if bear:
        val.append(f"bear {bear}: {(bear / px - 1) * 100:+.0f}%")
    if bull:
        val.append(f"bull {bull}: {(bull / px - 1) * 100:+.0f}%")
    if dcf:
        val.append(f"DCF {dcf}")
    if val:
        lines.append("- " + "; ".join(val))
    tech = [trend_words(st)]
    if st.get("hi60"):
        tech.append(f"{(px / st['hi60'] - 1) * 100:+.1f}% vs 60d high, {(px / st['lo60'] - 1) * 100:+.1f}% vs 60d low")
    if st.get("rsi") is not None:
        tech.append(f"RSI {st['rsi']:.0f}")
    lines.append("- " + "; ".join(tech))
    mine = [a for a in alerts if a.code == code]
    for a in mine:
        lines.append(f"- **{a.kind}: {a.signal}** – {a.detail} ({_fmt_odds(a)})")
    for ev in entry.get("events", []):
        when = pd.Timestamp(ev["date"])
        days = (when.normalize() - today.normalize()).days
        if days >= -1:
            lines.append(f"- {ev['what']}: {when:%d %b %Y} ({'today' if days == 0 else f'in {days} days' if days > 0 else 'yesterday'})")
    for k in entry.get("kill", []):
        lines.append(f"- watch: {k}")
    return lines


# ------------------------------------------------------------------------------------------------ digest
def digest(P: dict[str, pd.DataFrame], alerts: list[Alert], book: list[dict], names: dict[str, str] | None = None,
           today: pd.Timestamp | None = None, odds: dict | None = None) -> str:
    today = today or pd.Timestamp.now().normalize()
    session = alerts[0].session if alerts else (f"{P['close'].index[-1]:%Y-%m-%d}" if not P["close"].empty else "?")
    odds = load_odds() if odds is None else odds
    out = [f"# Signal watch – session {session}", ""]
    out.append("## Research book")
    if not book:
        out.append("- no research book yet (~/osloquant-home/researchbook.yaml)")
    for entry in book:
        out += book_lines(entry, status(P, entry["code"]), alerts, today) + [""]
    buys = [a for a in alerts if a.kind == BUY]
    risks = [a for a in alerts if a.kind == RISK]
    infos = [a for a in alerts if a.kind == INFO]
    out.append(f"## Alerts across the universe – {len(buys)} buy-type, {len(risks)} risk, {len(infos)} info")
    for title, group in (("Buy-type signals", buys), ("Risk signals", risks), ("Info", infos)):
        if not group:
            continue
        out.append(f"### {title}")
        for a in group:
            out.append(f"- {a.code} {a.name}: **{a.signal}** at {a.price:.2f} – {a.detail} ({_fmt_odds(a)})")
        out.append("")
    m = odds.get("measured", {})
    if m:
        out.append(f"_Odds: average excess return over the equal-weighted universe after this kind of signal, entry at the next open, "
                   f"measured {m.get('from')} to {m.get('to')} on {m.get('stocks')} stocks; a round trip costs ~{ROUND_TRIP_COST * 100:.1f} %. "
                   f"No buy signal has had an edge after costs over 20 sessions; use them as timing on a case, and the risk signals as risk._")
    return "\n".join(out) + "\n"


def signals_dir() -> Path:
    d = home() / "signals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_digest(text: str, alerts: list[Alert], session: str) -> tuple[Path, Path]:
    d = signals_dir()
    md = d / f"{session}.md"
    md.write_text(text, encoding="utf-8")
    (d / "latest.md").write_text(text, encoding="utf-8")
    js = d / "latest.json"
    js.write_text(json.dumps({"session": session, "alerts": [asdict(a) for a in alerts]}, indent=1, ensure_ascii=False), encoding="utf-8")
    return md, js


def summary_line(alerts: list[Alert], book: list[dict], P: dict[str, pd.DataFrame]) -> str:
    """One line for a notification: the research-book prices and the alert counts."""
    parts = []
    for e in book:
        st = status(P, e["code"])
        if st.get("price"):
            chg = f" {st['chg_1d'] * 100:+.1f}%" if st.get("chg_1d") is not None else ""
            tp = e.get("target")
            parts.append(f"{e['code']} {st['price']:.2f}{chg}" + (f" (TP {tp}: {(tp / st['price'] - 1) * 100:+.0f}%)" if tp else ""))
    buys = sum(a.kind == BUY for a in alerts)
    risks = sum(a.kind == RISK for a in alerts)
    mine = [a for a in alerts if any(a.code == e["code"] for e in book)]
    tail = f"{buys} buy-type, {risks} risk alerts" + (f"; on the book: {', '.join(f'{a.code} {a.signal}' for a in mine)}" if mine else "")
    return " | ".join(parts + [tail])


# ------------------------------------------------------------------------------------------------ notification
_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$title = [IO.File]::ReadAllText('{title}', [Text.Encoding]::UTF8)
$body = [IO.File]::ReadAllText('{body}', [Text.Encoding]::UTF8)
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$nodes = $xml.GetElementsByTagName('text')
$nodes.Item(0).AppendChild($xml.CreateTextNode($title)) | Out-Null
$nodes.Item(1).AppendChild($xml.CreateTextNode($body)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$appId = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""


def notify(title: str, body: str) -> bool:
    """A Windows toast notification. Returns False (and prints why) where it cannot be shown."""
    if sys.platform != "win32":
        print("notify: not on Windows, no toast", file=sys.stderr)
        return False
    tmp = Path(tempfile.mkdtemp(prefix="oq-toast-"))
    try:
        (tmp / "title.txt").write_text(title, encoding="utf-8")
        (tmp / "body.txt").write_text(body[:400], encoding="utf-8")
        script = tmp / "toast.ps1"
        script.write_text(_TOAST.format(title=str(tmp / "title.txt"), body=str(tmp / "body.txt")), encoding="utf-8")
        done = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True, text=True, timeout=60,
        )
        if done.returncode != 0:
            print(f"notify: toast failed: {done.stderr.strip()[:300]}", file=sys.stderr)
            return False
        return True
    except (OSError, subprocess.SubprocessError) as e:
        print(f"notify: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    finally:
        for p in tmp.glob("*"):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
