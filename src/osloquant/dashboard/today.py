"""What changed and what needs a decision: the logic behind the dashboard's front page ("I dag").

Every item says why it is there and links to the stock. The rules (DECISIONS.md, dashboard):

- a report or other event of a research-book company in the last 3 days with no kill check or new judgement logged
  since → check the kill criteria and log them;
- price at or beyond the target, below the bear value or above the bull value → re-rate;
- price moved 10 % or more since the current judgement, towards or away from the target → re-assess;
- a risk signal fired today on a research-book or watched company → look;
- a current view older than its horizon (12 months) → renew or retire it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import market as mk

STATE_FILE = "dashboard_state.json"
MOVE = 0.10
EVENT_LOOKBACK = 3
UPCOMING_DAYS = 30
KILL_SOON_DAYS = 14


@dataclass
class Item:
    code: str
    kind: str          # "kill-check", "re-rate", "re-assess", "risk-signal", "stale-view", "announcement"
    title: str
    detail: str
    urgency: int       # 0 = most urgent


def state_path():
    return jg.home() / STATE_FILE


def load_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    state_path().write_text(json.dumps(state, indent=1), encoding="utf-8")


def _since_view(c: bk.Case, day: pd.Timestamp) -> list[dict]:
    return [r for r in c.history if pd.Timestamp(r.get("logged_at", r.get("date"))[:10]) >= day and r["kind"] in ("kill_check", "judgement")]


def decisions(snap: mk.Snapshot, cases: list[bk.Case], alerts: list[sg.Alert], today: pd.Timestamp,
              watch: list[dict] | None = None) -> list[Item]:
    items: list[Item] = []
    watched = {w["code"] for w in (watch or []) if not w.get("moved_to_book")}
    for c in cases:
        lp = mk.last_price(snap, c.code)
        v = c.view
        for ev in c.events:
            d = pd.Timestamp(ev["date"])
            if today - pd.Timedelta(days=EVENT_LOOKBACK) <= d <= today and not _since_view(c, d):
                items.append(Item(c.code, "kill-check", f"{c.name}: {ev['what'][:70]}",
                                  f"{d:%d %b} – check the {len(c.kill)} kill criteria and log each (breached or intact, and what you did).", 0))
        if lp is None or not v:
            continue
        px, day = lp
        tp, bear, bull, p0 = v.get("target"), v.get("bear"), v.get("bull"), v.get("price")
        if tp and ((tp >= (p0 or 0) and px >= tp) or (tp < (p0 or 0) and px <= tp)):
            items.append(Item(c.code, "re-rate", f"{c.name} reached the target {tp:g}", f"price {px:.2f} ({day:%d %b}); set a new view or close the case.", 1))
        if bear and px <= bear:
            items.append(Item(c.code, "re-rate", f"{c.name} is at or below the bear value {bear:g}", f"price {px:.2f}: the bear case has happened – was it the scenario, or is the case broken?", 0))
        if bull and px >= bull:
            items.append(Item(c.code, "re-rate", f"{c.name} is at or above the bull value {bull:g}", f"price {px:.2f}: re-rate the case.", 1))
        if p0:
            move = px / p0 - 1
            if abs(move) >= MOVE:
                toward = (move > 0) == (tp is not None and tp > p0)
                items.append(Item(c.code, "re-assess", f"{c.name} {move * 100:+.0f}% since the view of {v.get('date')}",
                                  f"{p0:g} → {px:.2f}, {'towards' if toward else 'away from'} the target {tp:g}: re-assess and log the view (even if unchanged).", 1))
        try:
            age = (today - pd.Timestamp(v.get("date"))).days
        except (TypeError, ValueError):
            age = 0
        if age > 30 * int(v.get("horizon_months") or 12):
            items.append(Item(c.code, "stale-view", f"{c.name}: the view is {age} days old", "past its horizon – renew or retire it.", 2))
    book_codes = {c.code for c in cases}
    for a in alerts:
        if a.kind == sg.RISK and (a.code in book_codes or a.code in watched):
            items.append(Item(a.code, "risk-signal", f"{a.name}: {a.signal}", f"{a.detail}. Historically: {sg._fmt_odds(a)}.", 2))
    return sorted(items, key=lambda i: (i.urgency, i.code))


REPORT_DAYS = 21


def report_items(cases: list[bk.Case], today: pd.Timestamp, days: int = REPORT_DAYS) -> list[Item]:
    """A quarterly report read in the last ``days`` days with a kill criterion triggered or nearer, and no judgement or
    kill check dated on or after the report."""
    from osloquant.dashboard import reports as rp

    items = []
    for c in cases:
        s = rp.latest(c.code)
        if not s:
            continue
        pub = pd.Timestamp(s["published"][:10])
        if (today - pub).days > days:
            continue
        hot = [k for k in s["kill"] if k["status"].startswith(("triggered", "intact, nearer"))]
        answered = [r for r in c.history if r["kind"] in ("judgement", "kill_check") and r["date"] >= s["published"][:10]]
        if hot and not answered:
            trig = [k for k in hot if k["status"] == "triggered"]
            items.append(Item(c.code, "report", f"{c.name}: Q{s['quarter']} {s['year']} report – {len(trig)} kill criteria over the line, "
                              f"{len(hot) - len(trig)} nearer",
                              "; ".join(f"{k['criterion'][:60]}: {k['status']}" for k in hot) + " – read the analysis on the stock page and log a kill check.",
                              0 if trig else 1))
    return items


def upcoming(cases: list[bk.Case], today: pd.Timestamp, days: int = UPCOMING_DAYS) -> list[dict]:
    out = []
    for c in cases:
        for ev in c.events:
            d = pd.Timestamp(ev["date"])
            if today <= d <= today + pd.Timedelta(days=days):
                out.append({"code": c.code, "name": c.name, "date": d, "what": ev["what"],
                            "kill": c.kill if (d - today).days <= KILL_SOON_DAYS else []})
    return sorted(out, key=lambda e: e["date"])


def target_moves(snap: mk.Snapshot, cases: list[bk.Case]) -> list[dict]:
    """Every case's price against its view: since the view, distance to target, bear and bull."""
    out = []
    for c in cases:
        lp, v = mk.last_price(snap, c.code), c.view
        if not lp or not v or not v.get("price"):
            continue
        px, day = lp
        out.append({"code": c.code, "name": c.name, "price": px, "date": day, "rating": v.get("rating"), "target": v.get("target"),
                    "since": px / v["price"] - 1, "to_tp": v["target"] / px - 1 if v.get("target") else None,
                    "to_bear": v["bear"] / px - 1 if v.get("bear") else None, "to_bull": v["bull"] / px - 1 if v.get("bull") else None,
                    "view_date": v.get("date"), "view_source": c.view_source})
    return out


def signals_since(snap: mk.Snapshot, last_seen: str | None, max_sessions: int = 10) -> tuple[list[sg.Alert], list[str]]:
    """Alerts on every session after ``last_seen`` (at most ``max_sessions``), newest first, and the sessions covered."""
    C = snap.panel["close"]
    if C.empty:
        return [], []
    days = list(C.index)
    if last_seen:
        days = [d for d in days if d > pd.Timestamp(last_seen)]
    days = days[-max_sessions:] or list(C.index[-1:])
    odds = sg.load_odds().get("signals", {})
    ind = sg.indicators(snap.panel)                 # computed once for all sessions (the channel fit is slow)
    frames = sg.signal_frames(snap.panel, ind)
    order = {sg.BUY: 0, sg.RISK: 1, sg.INFO: 2}
    alerts: list[sg.Alert] = []
    for d in reversed(days):
        today_alerts = []
        for sname, (kind, f) in frames.items():
            for code in f.columns[f.loc[d].values]:
                o = odds.get(sname, {})
                today_alerts.append(sg.Alert(code, snap.names.get(code, code), sname, kind, f"{d:%Y-%m-%d}",
                                             float(snap.panel["close"].at[d, code]), sg._detail(sname, code, d, snap.panel, ind),
                                             o.get("exc20"), o.get("exc60"), o.get("hit20")))
        alerts += sorted(today_alerts, key=lambda a: (order[a.kind], a.signal, a.code))
    return alerts, [f"{d:%Y-%m-%d}" for d in days]
