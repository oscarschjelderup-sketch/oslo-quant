"""Trading Goats: three of the paper accounts, exported as the document a public page reads.

beebots.tech shows three AI bees trading crypto with real money. This is the Oslo Børs version with play money:
three goats (the three billy goats Gruff) are three of the paper accounts in this store, a troll looks at them
every evening, and a page shows where they stand. Nothing here trades. The module only reads what the live and
intraday engines have stored and writes JSON.

The document (schema ``goats/1``) has six parts:

- ``meta``: the clock, the market phase, the totals, when the troll looks next;
- ``goats``: one entry per goat with its holdings, equity curve, latest decision and a status in plain words;
- ``herd``: every other paper account in the store, as a leaderboard;
- ``stream``: the latest signals and fills across the goats, newest first;
- ``gate``: the buy signals the filters refused on the latest session, and why;
- ``troll``: the troll's log, kept in ``~/osloquant-home/troll.json`` and written with ``oq goats troll``.

``oq goats --split DIR`` writes each part as its own file, which is how the page's store is fed, and
``oq goats --publish`` pushes the whole document to the ``goats`` branch of the repository, which is where the
GitHub Pages copy of the page reads it from.

A goat is one account at a time, but it has a lineage: when the troll rewrites a goat's rules
(``oq goats rewrite``), the account it followed keeps running in the herd under its old name, a new account is
added with the changed settings and the old account's value as its stake, and the goat follows the new one.
The goat's curve is the lineage stitched together, so a rewrite never resets its record.
"""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from osloquant.env import oq_env

SCHEMA = "goats/1"
MARKET_TIMEZONE = "Europe/Oslo"
#: continuous trading on Oslo Børs; the closing auction runs to 16:25
MARKET_OPEN, MARKET_CLOSE = time(9, 0), time(16, 20)
#: when the troll looks at the goats, Oslo time: after the evening job has stepped the daily accounts
REVIEW_TIME = time(18, 55)
#: an intraday goat that has not looked for this long while the market is open is dozing (the laptop sleeps)
DOZING_AFTER = pd.Timedelta(minutes=40)
#: at most this many points per equity curve
CURVE_POINTS = 400
STREAM_ITEMS = 80
GATE_ITEMS = 12
TROLL_ENTRIES = 60
ACCENTS = ("gold", "fjord", "rose")
TROLL_KINDS = ("intro", "verdict", "handsoff", "rewrite", "note")
BRANCH = "goats"

DEFAULT_CONFIG = """\
# The three goats the Trading Goats page follows. Each is one of the paper accounts in this store (live.yaml or
# intraday.yaml). Change the mapping here; the accounts themselves are never touched.
#
# id        the key the page stores the goat under (letters, digits, - and _)
# account   the paper account the goat follows now
# tagline   shown under the name
# accent    gold, fjord or rose: the goat's colour on the page
# story     one line on how the goat trades
# lineage   the accounts the goat followed before (written by `oq goats rewrite`; leave alone)
#
# rewrites                        how many times the troll has rewritten a goat's rules (kept by `oq goats rewrite`)
# min_sessions_between_rewrites   a goat's account must be at least this many sessions old before it can be rewritten

rewrites: 0
min_sessions_between_rewrites: 5

goats:
  - id: lillebukk
    name: Lillebukk
    tagline: the scalper
    account: daytrade_orb
    accent: gold
    story: The smallest. Trips over the bridge at the open, grabs what breaks out of the first half hour across all 63 names, and is back on the near bank before the close. Never sleeps on the far side.
  - id: mellombukk
    name: Mellombukk
    tagline: the calculated one
    account: intraday_breakout_slow
    accent: fjord
    story: Waits for a momentum name to clear its 60-bar high, then follows it with a trailing stop. Five slots, holds overnight for as long as the trend holds.
  - id: storebukk
    name: Storebukk
    tagline: the heavyweight
    account: live_momentum
    accent: rose
    story: Ten names with the strongest twelve-month momentum, bought at the open after the close that picked them. Rebalances monthly and butts nothing in a hurry.
"""


@dataclass
class GoatConfig:
    id: str
    name: str
    account: str
    tagline: str = ""
    accent: str = "gold"
    story: str = ""
    #: the accounts the goat followed before, oldest first: {account, from, to, value, why, changes}
    lineage: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"goat id {self.id!r}: letters, digits, - and _ only")
        if self.accent not in ACCENTS:
            raise ValueError(f"goat {self.id}: accent must be one of {', '.join(ACCENTS)}")

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
            "name": self.name,
            "tagline": self.tagline,
            "account": self.account,
            "accent": self.accent,
            "story": self.story,
        }
        if self.lineage:
            out["lineage"] = self.lineage
        return out


@dataclass
class GoatsConfig:
    goats: list[GoatConfig]
    rewrites: int = 0
    min_sessions_between_rewrites: int = 5
    path: Path | None = None
    created: bool = False

    def goat(self, goat_id: str) -> GoatConfig:
        for goat in self.goats:
            if goat.id == goat_id:
                return goat
        raise LookupError(f"no goat named {goat_id!r}; the goats are {', '.join(g.id for g in self.goats)}")


def home() -> Path:
    from osloquant.env import data_path

    data_path()  # makes sure the home exists
    return Path(oq_env["home"])


def config_path() -> Path:
    return home() / "goats.yaml"


def load_config(path: str | Path | None = None) -> GoatsConfig:
    """Read the goats, writing the default three first if there is no file."""
    path = Path(path) if path is not None else config_path()
    created = not path.exists()
    if created:
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    goats = [GoatConfig(**g) for g in raw.get("goats") or []]
    ids = [g.id for g in goats]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: two goats share an id")
    return GoatsConfig(
        goats=goats,
        rewrites=int(raw.get("rewrites", 0)),
        min_sessions_between_rewrites=int(raw.get("min_sessions_between_rewrites", 5)),
        path=path,
        created=created,
    )


def save_config(config: GoatsConfig) -> None:
    """Write the goats back. The explanatory header is kept; the entries are rewritten."""
    header = DEFAULT_CONFIG.split("\nrewrites:", 1)[0] + "\n"
    body = yaml.safe_dump(
        {
            "rewrites": config.rewrites,
            "min_sessions_between_rewrites": config.min_sessions_between_rewrites,
            "goats": [g.to_dict() for g in config.goats],
        },
        sort_keys=False,
        allow_unicode=True,
        width=1000,
    )
    path = config.path or config_path()
    path.write_text(header + "\n" + body, encoding="utf-8")


# -- clocks ---------------------------------------------------------------------------------------


def market_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz=MARKET_TIMEZONE).tz_localize(None)


def _at(day: pd.Timestamp, clock: time) -> pd.Timestamp:
    return day.normalize() + pd.Timedelta(hours=clock.hour, minutes=clock.minute)


def _next_weekday(day: pd.Timestamp) -> pd.Timestamp:
    day = day.normalize() + pd.Timedelta(days=1)
    while day.dayofweek >= 5:
        day += pd.Timedelta(days=1)
    return day


def market_phase(now: pd.Timestamp) -> dict:
    """Open or closed at ``now`` (Oslo time), and when it changes. Public holidays are not known here."""
    weekday = now.dayofweek < 5
    opens, closes = _at(now, MARKET_OPEN), _at(now, MARKET_CLOSE)
    if weekday and opens <= now < closes:
        return {"open": True, "label": "open", "closes_at": _iso(closes), "next_open": None}
    if weekday and now < opens:
        return {"open": False, "label": "before the open", "closes_at": None, "next_open": _iso(opens)}
    label = "closed" if weekday else "weekend"
    return {"open": False, "label": label, "closes_at": None, "next_open": _iso(_at(_next_weekday(now), MARKET_OPEN))}


def next_review(now: pd.Timestamp) -> pd.Timestamp:
    """The next evening the troll looks: today at the review time on a weekday, else the next weekday."""
    today = _at(now, REVIEW_TIME)
    if now.dayofweek < 5 and now < today:
        return today
    return _at(_next_weekday(now), REVIEW_TIME)


# -- small helpers --------------------------------------------------------------------------------


def _iso(value) -> str | None:
    if value is None or value is pd.NaT or (isinstance(value, float) and math.isnan(value)):
        return None
    return pd.Timestamp(value).isoformat(timespec="seconds")


def _utc(value) -> str | None:
    """A wall-clock time the engines logged in UTC (``decided_at``), marked as such so the page does not read it as Oslo time."""
    text = _iso(value)
    return None if text is None else text + "Z"


def _utc_now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").tz_localize(None).isoformat(timespec="seconds") + "Z"


def _num(value) -> float | None:
    """A plain float, or None for anything that is not a number."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) or math.isinf(out) else out


def clean(obj):
    """Make a nested structure JSON-safe: NaN to null, numpy scalars to Python ones, timestamps to ISO strings."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return _iso(obj)
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    return obj


def compact_series(series: pd.Series, limit: int = CURVE_POINTS) -> list[list]:
    """``[[time, value], ...]`` with at most ``limit`` points, the first and the last always kept."""
    series = series.dropna()
    if len(series) > limit:
        keep = np.unique(np.round(np.linspace(0, len(series) - 1, limit)).astype(int))
        series = series.iloc[keep]
    return [[_iso(t), round(float(v), 2)] for t, v in series.items()]


def held_since(orders: pd.DataFrame, entity_id: str) -> pd.Timestamp | None:
    """When the current holding of ``entity_id`` was opened: the first buy after the last time it was sold out."""
    if orders is None or orders.empty:
        return None
    rows = orders[(orders["entity_id"] == entity_id) & orders["order_type"].isin(("order_long", "order_close_long"))]
    if rows.empty:
        return None
    sells = rows.index[rows["order_type"] == "order_close_long"]
    buys = rows[rows["order_type"] == "order_long"]
    if len(sells):
        buys = buys[buys.index > sells[-1]]
    return None if buys.empty else pd.Timestamp(buys["timestamp"].iloc[0])


def status_for(
    kind: str,
    phase: dict,
    now: pd.Timestamp,
    *,
    holdings: int,
    slots: int | None,
    entries: int = 0,
    cap: int | None = None,
    day_trade: bool = False,
    last_poll: pd.Timestamp | None = None,
    watching: int = 0,
    last_session: pd.Timestamp | None = None,
    expected_session: pd.Timestamp | None = None,
) -> dict:
    """A goat's state in one word and one line. The words are the page's vocabulary; keep them."""
    names = f"{holdings} name{'s' if holdings != 1 else ''}"
    if kind == "daily":
        if last_session is not None and expected_session is not None and last_session < expected_session:
            return {
                "code": "BEHIND",
                "text": f"books stand at {last_session:%a %d %b} · the evening job has not run since",
            }
        if holdings:
            return {
                "code": "GRAZING",
                "text": f"{names} held · next decision at tonight's close"
                if phase["open"]
                else f"{names} held · decides again at the next close",
            }
        return {"code": "WAITING", "text": "cash only · decides at the next close"}
    if not phase["open"]:
        when = "at 09:00" if phase["label"] in ("before the open", "closed") else "on Monday"
        if day_trade:
            return {"code": "FLAT", "text": f"nothing held overnight · back on the bridge {when}"}
        if holdings:
            return {"code": "GRAZING", "text": f"{names} held overnight · next look {when}"}
        return {"code": "WAITING", "text": f"cash only · next look {when}"}
    if last_poll is not None and now - last_poll > DOZING_AFTER:
        return {"code": "DOZING", "text": f"last look {last_poll:%H:%M} · the laptop sleeps and the goat with it"}
    if day_trade and cap is not None and entries >= cap:
        return {"code": "BENCHED", "text": f"all {cap} entries used today · riding what it holds until the close"}
    if holdings:
        filled = f"{holdings} of {slots} slots" if slots else names
        return {"code": "GRAZING", "text": f"{filled} filled · watching {watching} names"}
    return {"code": "WATCHING", "text": f"{watching} names on the bridge · cash only"}


# -- the troll's log ------------------------------------------------------------------------------


def troll_path() -> Path:
    return home() / "troll.json"


def load_troll() -> dict:
    path = troll_path()
    if not path.exists():
        return {"rewrites": 0, "reviewed_at": None, "entries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("entries", [])
    return data


def add_troll_entry(
    text: str, kind: str = "verdict", goat: str | None = None, config: GoatsConfig | None = None, at: str | None = None
) -> dict:
    """Append one line to the troll's log and return it. ``goat`` must be one of the configured goats."""
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("the troll has to say something")
    if kind not in TROLL_KINDS:
        raise ValueError(f"kind must be one of {', '.join(TROLL_KINDS)}")
    if goat is not None:
        (config or load_config()).goat(goat)  # raises for an unknown goat
    entry = {"t": at or _utc_now_iso(), "kind": kind, "text": text}
    if goat:
        entry["goat"] = goat
    log = load_troll()
    log["entries"] = (log["entries"] + [entry])[-TROLL_ENTRIES:]
    log["reviewed_at"] = entry["t"]
    troll_path().write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    return entry


# -- reading the store ----------------------------------------------------------------------------


def _label(names: pd.DataFrame, entity_id: str) -> tuple[str, str]:
    if entity_id in names.index:
        return str(names.loc[entity_id, "code"]), str(names.loc[entity_id, "name"])
    return entity_id.split("_", 2)[-1], ""


def _side(order_type: str) -> str:
    return "buy" if order_type == "order_long" else "sell"


def _fill_items(goat_id: str, orders: pd.DataFrame, names: pd.DataFrame) -> list[dict]:
    if orders is None or orders.empty:
        return []
    trades = orders[orders["order_type"].isin(("order_long", "order_close_long"))]
    items = []
    for row in trades.itertuples():
        code, _ = _label(names, row.entity_id)
        reason = row.reason if isinstance(row.reason, str) else None
        price, shares = _num(row.order_price), _num(row.order_amount)
        items.append(
            {
                "t": _iso(row.timestamp),
                "at": _utc(row.decided_at),
                "goat": goat_id,
                "kind": "fill",
                "side": _side(row.order_type),
                "code": (reason.split(" ", 1)[0] if reason else _side(row.order_type).upper()),
                "stock": code,
                "price": price,
                "shares": shares,
                "value": price * shares if price is not None and shares is not None else None,
                "cost": _num(row.cost),
                "pnl": _num(row.profit),
                "pnl_pct": _num(row.profit_rate),
                "reason": reason,
                "forward": bool(_num(row.forward) == 1.0),
            }
        )
    return items


def _signal_items(goat_id: str, signals: pd.DataFrame, names: pd.DataFrame) -> list[dict]:
    if signals is None or signals.empty:
        return []
    items = []
    for row in signals.itertuples():
        code, _ = _label(names, row.entity_id)
        items.append(
            {
                "t": _iso(row.timestamp),
                "at": _utc(row.decided_at),
                "goat": goat_id,
                "kind": "signal",
                "code": row.code,
                "rule": row.rule,
                "stock": code,
                "price": _num(row.price),
                "reason": row.reason,
                "outcome": row.outcome,
            }
        )
    return items


def gate_items(signals: list[dict], limit: int = GATE_ITEMS) -> dict:
    """The buy signals the filters refused on the latest day that has any, newest first, one line per stock and reason."""
    refused = [
        s
        for s in signals
        if s["kind"] == "signal" and s["code"] == "BUY" and str(s.get("outcome", "")).startswith("skipped:")
    ]
    if not refused:
        return {"day": None, "items": []}
    day = max(s["t"][:10] for s in refused)
    seen, items = set(), []
    for s in sorted((s for s in refused if s["t"][:10] == day), key=lambda s: s["t"], reverse=True):
        why = s["outcome"].split(":", 1)[1].strip()
        key = (s["stock"], why)
        if key in seen:
            continue
        seen.add(key)
        items.append({"t": s["t"], "goat": s["goat"], "stock": s["stock"], "why": why})
        if len(items) >= limit:
            break
    return {"day": day, "items": items}


def _rules(kind: str, state: dict, cfg) -> dict:
    if kind == "daily":
        return {
            "kind": "daily",
            "signal": state.get("strategy"),
            "slots": getattr(cfg, "max_positions", None),
            "execution": "next open",
            "rebalance": "as the strategy decides",
        }
    rules = {
        "kind": "intraday",
        "signal": state.get("strategy"),
        "slots": getattr(cfg, "max_positions", None),
        "execution": "open of the bar starting when the order is sent",
    }
    if cfg is not None:
        watch = cfg.watchlist if isinstance(cfg.watchlist, str) else f"{len(cfg.watchlist)} codes"
        rules.update(
            {
                "watchlist": watch,
                "stop_loss": cfg.stop_loss,
                "take_profit": cfg.take_profit,
                "trailing_stop": cfg.trailing_stop,
                "flat_at_close": cfg.flat_at_close,
                "day_trade": cfg.day_trade,
                "exit_on_signal": cfg.exit_on_signal,
                "entry_window": cfg.entry_window,
                "max_entries_per_day": cfg.max_entries_per_day,
                "min_relative_volume": cfg.min_relative_volume,
                "min_range_to_cost": cfg.min_range_to_cost,
                "max_per_sector": cfg.max_per_sector,
                "cooldown_bars": cfg.cooldown_bars,
            }
        )
    return rules


@dataclass
class AccountFacts:
    """What one paper account contributes to a goat: read once, used for the goat and for the stream."""

    name: str
    kind: str
    state: dict
    summary: dict
    cfg: object | None
    equity: pd.Series
    fills: list[dict]
    signals: list[dict]

    def cut(self, until: str | None) -> None:
        """Keep only what happened up to ``until`` (an ISO time): the part of a lineage account the goat owned."""
        if not until:
            return
        limit = pd.Timestamp(until)
        self.equity = self.equity[self.equity.index <= limit]
        self.fills = [f for f in self.fills if f["t"] and pd.Timestamp(f["t"]) <= limit]
        self.signals = [s for s in self.signals if s["t"] and pd.Timestamp(s["t"]) <= limit]


def account_facts(name: str, goat_id: str, intraday_config, live_config) -> AccountFacts | None:
    from osloquant.contract.api import get_data
    from osloquant.intraday import engine as intraday
    from osloquant.live import engine as live
    from osloquant.trader.schemas import AccountStats
    from osloquant.trader.sim_account import PROVIDER

    state = intraday.load_state(name)  # both engines keep their state in the same table
    if state is None:
        return None
    kind = "intraday" if state.get("kind") == "intraday" else "daily"
    names = intraday.stock_names()
    if kind == "intraday":
        summary = intraday.account_summary(name, feed_delay=intraday_config.feed_delay)
        cfg = next((a for a in intraday_config.accounts if a.name == name), None)
        equity = summary["snapshots"]["all_value"] if not summary["snapshots"].empty else pd.Series(dtype=float)
    else:
        summary = live.account_summary(name)
        cfg = next((a for a in live_config.accounts if a.name == name), None)
        stats = get_data(AccountStats, provider=PROVIDER, filters=[AccountStats.trader_name == name], index="timestamp")
        equity = stats["all_value"] if not stats.empty else pd.Series(dtype=float)
    return AccountFacts(
        name=name,
        kind=kind,
        state=state,
        summary=summary,
        cfg=cfg,
        equity=equity,
        fills=_fill_items(goat_id, summary["orders"], names),
        signals=_signal_items(goat_id, summary.get("signals"), names) if kind == "intraday" else [],
    )


def goat_document(
    goat: GoatConfig, now: pd.Timestamp, phase: dict, intraday_config, live_config, expected: pd.Timestamp | None
) -> tuple[dict, list[dict]]:
    """One goat as the page shows it, plus its stream items (signals and fills) for the shared stream."""
    head = {
        "id": goat.id,
        "name": goat.name,
        "tagline": goat.tagline,
        "account": goat.account,
        "accent": goat.accent,
        "story": goat.story,
        "lineage": goat.lineage,
    }
    current = account_facts(goat.account, goat.id, intraday_config, live_config)
    if current is None:
        return {
            **head,
            "missing": True,
            "status": {"code": "MISSING", "text": f"no paper account named {goat.account} in the store"},
        }, []

    # the accounts the goat followed before, each cut at the moment it was handed over
    earlier: list[AccountFacts] = []
    for link in goat.lineage:
        facts = account_facts(link["account"], goat.id, intraday_config, live_config)
        if facts is not None:
            facts.cut(link.get("to"))
            earlier.append(facts)
    chain = earlier + [current]

    kind, summary, state, cfg = current.kind, current.summary, current.state, current.cfg
    orders = summary["orders"]
    peaks = state.get("peaks", {})

    holdings = []
    for h in summary["holdings"]:
        stop = target = None
        if kind == "intraday" and cfg is not None:
            levels = []
            if cfg.stop_loss:
                levels.append(h["average_price"] * (1 - cfg.stop_loss))
            if cfg.trailing_stop:
                levels.append(peaks.get(h["entity_id"], h["average_price"]) * (1 - cfg.trailing_stop))
            stop = max(levels) if levels else None
            target = h["average_price"] * (1 + cfg.take_profit) if cfg.take_profit else None
        holdings.append(
            {
                "stock": h["code"],
                "name": h["name"],
                "shares": _num(h["shares"]),
                "entry": _num(h["average_price"]),
                "mark": _num(h["last_price"]),
                "value": _num(h["value"]),
                "pnl": _num((h["last_price"] - h["average_price"]) * h["shares"]),
                "pnl_pct": _num(h["profit_rate"]),
                "since": _iso(held_since(orders, h["entity_id"])),
                "stop": _num(stop),
                "target": _num(target),
            }
        )

    pending = []
    for p in summary["pending"]:
        pending.append(
            {
                "side": p["side"],
                "stock": p["code"],
                "name": p["name"],
                "signal": p.get("signal", p["side"].upper()),
                "reason": p.get("reason"),
                "decided_on": _iso(p["decided_on"]),
            }
        )

    fills = [f for facts in chain for f in facts.fills]
    signals = [s for facts in chain for s in facts.signals]
    today = now.normalize()
    today_key = today.strftime("%Y-%m-%d")
    sells = [f for f in fills if f["side"] == "sell"]
    wins = [f for f in sells if (f["pnl"] or 0) > 0]
    equity = pd.concat([facts.equity for facts in chain]) if chain else pd.Series(dtype=float)
    equity = equity[~equity.index.duplicated(keep="last")].sort_index()
    stake = float(chain[0].summary["input_money"])
    start = chain[0].summary["start"]

    if kind == "intraday":
        entries = len(state.get("entries_today", [])) if state.get("entry_day") == today.isoformat() else 0
        coverage = summary["coverage"]
        today_doc = {
            "entries": entries,
            "cap": getattr(cfg, "max_entries_per_day", None),
            "signals": sum(1 for s in current.signals if s["t"] and s["t"][:10] == today_key),
            "fills": sum(1 for f in current.fills if f["t"] and f["t"][:10] == today_key),
            "looks_made": coverage["today_made"],
            "looks_due": coverage["today_due"],
            "looks_share": coverage["share"],
            "days_missed": len(coverage["days_missed"]),
        }
        last = current.signals[-1] if current.signals else None
        last_call = (
            None
            if last is None
            else {k: last[k] for k in ("t", "at", "code", "rule", "stock", "price", "reason", "outcome")}
        )
        status = status_for(
            kind, phase, now,
            holdings=len(holdings), slots=getattr(cfg, "max_positions", None), entries=entries, cap=getattr(cfg, "max_entries_per_day", None),
            day_trade=bool(getattr(cfg, "day_trade", False) or getattr(cfg, "flat_at_close", False)),
            last_poll=summary["last_poll"], watching=len(summary["watchlist"]),
        )  # fmt: skip
        last_seen = _iso(summary["last_poll"])
    else:
        session = summary["last_session"]
        today_doc = {
            "pending": len(pending),
            "fills": sum(1 for f in current.fills if f["t"] and f["t"][:10] == session.strftime("%Y-%m-%d")),
            "session": _iso(session),
        }
        if pending:
            p = summary["pending"][0]
            last_call = {
                "t": _iso(p["decided_on"]),
                "at": _utc(p["decided_at"]),
                "code": p["side"].upper(),
                "rule": state.get("strategy"),
                "stock": p["code"],
                "price": None,
                "reason": f"decided on the close of {pd.Timestamp(p['decided_on']):%d %b}",
                "outcome": "to be filled at the next open",
            }
        elif current.fills:
            f = current.fills[-1]
            last_call = {
                "t": f["t"],
                "at": f["at"],
                "code": f["side"].upper(),
                "rule": state.get("strategy"),
                "stock": f["stock"],
                "price": f["price"],
                "reason": f"filled at the open of {f['t'][:10]}",
                "outcome": "filled" + (" · logged before the open" if f["forward"] else " · logged late"),
            }
        else:
            last_call = None
        status = status_for(
            kind,
            phase,
            now,
            holdings=len(holdings),
            slots=getattr(cfg, "max_positions", None),
            last_session=session,
            expected_session=expected,
        )
        last_seen = _iso(session)

    value = float(summary["value"])
    doc = {
        **head,
        "missing": False,
        "kind": kind,
        "start": _iso(start),
        "last_seen": last_seen,
        "sessions": int(sum(f.summary["sessions"] for f in chain)),
        "input_money": stake,
        "value": value,
        "cash": _num(summary["cash"]),
        "pnl": value - stake,
        "pnl_pct": value / stake - 1 if stake else None,
        "benchmark_pct": _num(summary["benchmark_return"]),
        "universe_pct": _num(summary.get("universe_return")),
        "status": status,
        "holdings": holdings,
        "pending": pending,
        "rules": _rules(kind, state, cfg),
        "today": today_doc,
        "last_call": last_call,
        "fees": sum(_num(f.summary["costs_paid"]) or 0 for f in chain),
        "dividends": sum(_num(f.summary["dividends_received"]) or 0 for f in chain),
        "fills": len(fills),
        "forward_fills": sum(1 for f in fills if f["forward"]),
        "round_trips": len(sells),
        "win_rate": (len(wins) / len(sells)) if sells else None,
        "decisions": len(signals) if kind == "intraday" else len(fills) + len(pending),
        "feed_lag": _num(summary.get("feed_lag")),
        "equity": compact_series(equity),
        "trades": fills[-30:],
        "rewrites": len(goat.lineage),
    }
    return doc, signals + fills


def herd_items(exclude: set[str], intraday_config) -> list[dict]:
    """Every other paper account in the store, for the leaderboard."""
    from osloquant.intraday import engine as intraday
    from osloquant.live import engine as live

    items = []
    for name in live.live_account_names():
        if name in exclude:
            continue
        s = live.account_summary(name)
        items.append(
            {
                "account": name,
                "kind": "daily",
                "signal": s["strategy"],
                "start": _iso(s["start"]),
                "value": _num(s["value"]),
                "pnl_pct": _num(s["total_return"]),
                "benchmark_pct": _num(s["benchmark_return"]),
                "fills": int(s["fills"]),
                "holdings": len(s["holdings"]),
            }
        )
    for name in intraday.intraday_account_names():
        if name in exclude:
            continue
        s = intraday.account_summary(name, feed_delay=intraday_config.feed_delay)
        items.append(
            {
                "account": name,
                "kind": "intraday",
                "signal": s["strategy"],
                "start": _iso(s["start"]),
                "value": _num(s["value"]),
                "pnl_pct": _num(s["total_return"]),
                "benchmark_pct": _num(s["benchmark_return"]),
                "fills": int(s["fills"]),
                "holdings": len(s["holdings"]),
                "round_trips": int(s["round_trips"]),
                "win_rate": _num(s["win_rate"]),
            }
        )
    return sorted(items, key=lambda i: -(i["pnl_pct"] if i["pnl_pct"] is not None else -9))


def _osebx(now: pd.Timestamp) -> dict | None:
    from osloquant.domain import Index1dKdata

    df = Index1dKdata.query_data(
        entity_ids=["index_ol_OSEBX"],
        start_timestamp=now.normalize() - pd.Timedelta(days=30),
        columns=["timestamp", "close"],
    )
    if df is None or df.empty:
        return None
    df = df.sort_values("timestamp")
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    return {
        "last": _num(last["close"]),
        "date": _iso(last["timestamp"]),
        "change_pct": _num(last["close"] / prev["close"] - 1) if prev is not None else None,
    }


def export(config: GoatsConfig | None = None, now: pd.Timestamp | None = None) -> dict:
    """The whole document. A goat whose account is not in the store is reported as missing, not an error."""
    from osloquant.contract.api import get_coverage
    from osloquant.domain import Stock1dAdjKdata
    from osloquant.health import expected_session
    from osloquant.intraday import engine as intraday
    from osloquant.live import engine as live

    config = load_config() if config is None else config
    now = market_now() if now is None else now
    phase = market_phase(now)
    intraday_config = intraday.load_config()
    live_config = live.load_config()
    expected = expected_session(now)

    goats, stream = [], []
    for goat in config.goats:
        doc, items = goat_document(goat, now, phase, intraday_config, live_config, expected)
        goats.append(doc)
        stream += items

    ranked = sorted([g for g in goats if not g["missing"]], key=lambda g: -(g["pnl_pct"] or 0))
    leader = ranked[0]["value"] if ranked else None
    for rank, g in enumerate(ranked, start=1):
        g["rank"] = rank
        g["behind"] = _num(leader - g["value"]) if leader is not None and rank > 1 else 0.0

    stream.sort(key=lambda s: s.get("at") or s["t"] or "", reverse=True)
    live_goats = [g for g in goats if not g["missing"]]
    started = min((g["start"] for g in live_goats), default=None)
    try:
        newest_daily = get_coverage(Stock1dAdjKdata)["last"]
    except Exception:  # an empty store has no coverage
        newest_daily = None
    try:
        osebx = _osebx(now)
    except Exception:
        osebx = None
    troll = load_troll()
    troll["rewrites"] = config.rewrites

    followed = {g.account for g in config.goats} | {link["account"] for g in config.goats for link in g.lineage}
    generated_at = _utc_now_iso()
    meta = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "oslo_now": _iso(now),
        "market": phase,
        "troll": {
            "next_review": _iso(next_review(now)),
            "cadence": f"every weekday at {REVIEW_TIME:%H:%M} Oslo, after the evening job",
            "rewrites": config.rewrites,
        },
        "started": started,
        "day": int(len(pd.bdate_range(pd.Timestamp(started).normalize(), now.normalize()))) if started else 0,
        "goats": len(live_goats),
        "osebx": osebx,
        "totals": {
            "pnl": sum(g["pnl"] or 0 for g in live_goats),
            "fees": sum(g["fees"] or 0 for g in live_goats),
            "dividends": sum(g["dividends"] or 0 for g in live_goats),
            "fills": sum(g["fills"] for g in live_goats),
            "forward_fills": sum(g["forward_fills"] for g in live_goats),
            "decisions": sum(g["decisions"] for g in live_goats),
        },
        "costs": {
            "commission_rate": intraday_config.commission_rate,
            "commission_min": intraday_config.commission_min,
            "slippage": intraday_config.slippage,
            "broker": "Nordnet Mini price list, October 2026",
        },
        "feed": {
            "source": "Yahoo Finance",
            "delay_minutes": intraday_config.feed_delay.total_seconds() / 60,
            "lag_minutes": max((g["feed_lag"] for g in live_goats if g["feed_lag"] is not None), default=None),
            "newest_daily_session": _iso(newest_daily),
            "expected_session": _iso(expected),
        },
    }
    return clean(
        {
            "meta": meta,
            "goats": goats,
            "herd": {"generated_at": generated_at, "items": herd_items(followed, intraday_config)},
            "stream": {"generated_at": generated_at, "items": stream[:STREAM_ITEMS]},
            "gate": {"generated_at": generated_at, **gate_items(stream)},
            "troll": troll,
        }
    )


def default_out() -> Path:
    return home() / "goats.json"


def write(doc: dict, out: Path | None = None, split: Path | None = None) -> list[Path]:
    """Write the document to ``out`` and, with ``split``, one file per page document under it."""
    out = default_out() if out is None else Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    written = [out]
    if split is not None:
        split = Path(split)
        parts = {
            "meta/state": doc["meta"],
            "herd/latest": doc["herd"],
            "stream/latest": doc["stream"],
            "gate/latest": doc["gate"],
            "troll/log": doc["troll"],
        }
        for goat in doc["goats"]:
            parts[f"goats/{goat['id']}"] = goat
        for path, body in parts.items():
            target = split / f"{path}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(body, indent=1), encoding="utf-8")
            written.append(target)
    return written


# -- publishing to a branch -----------------------------------------------------------------------


def repo_root() -> Path:
    """The checkout this package was installed from (an editable install), or the current directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


def publish_branch(
    files: dict[str, Path],
    repo: Path | None = None,
    branch: str = BRANCH,
    remote: str = "origin",
    push: bool = True,
    message: str | None = None,
) -> str:
    """Put ``files`` (branch path -> local file) on ``branch`` as a single commit and force-push it.

    The branch carries no history: every publish is one fresh commit holding the current files, so the repository
    does not grow with the number of refreshes (the same way the oil repo publishes its quotes). Files already on
    the branch that are not in ``files`` are kept. Returns the commit id.
    """
    repo = repo_root() if repo is None else Path(repo)

    def git(*args: str, env: dict | None = None, check: bool = True) -> str:
        done = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, env={**os.environ, **(env or {})}
        )
        if check and done.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip() or done.stdout.strip()}")
        return done.stdout.strip()

    if push:
        git("fetch", "--quiet", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}", check=False)
    base = None
    for ref in (f"refs/remotes/{remote}/{branch}", f"refs/heads/{branch}"):
        if (
            subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo, capture_output=True).returncode
            == 0
        ):
            base = ref
            break

    with tempfile.TemporaryDirectory() as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        if base:
            git("read-tree", base, env=env)
        else:
            git("read-tree", "--empty", env=env)
        for path, source in files.items():
            blob = git("hash-object", "-w", str(Path(source).resolve()))
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
        tree = git("write-tree", env=env)
    message = message or f"goats: {', '.join(files)} at {_utc_now_iso()}"
    commit = git("commit-tree", tree, "-m", message)
    git("update-ref", f"refs/heads/{branch}", commit)
    if push:
        git("push", "--quiet", "--force", remote, f"refs/heads/{branch}:refs/heads/{branch}")
    return commit


# -- the rewrite flow -----------------------------------------------------------------------------


def parse_change(text: str) -> tuple[list[str], object]:
    """``"signal.lookback=40"`` -> ``(["signal", "lookback"], 40)``; values become int, float, bool, null or a list."""
    key, sep, raw = text.partition("=")
    if not sep or not key.strip():
        raise ValueError(f"{text!r}: write it as key=value, nested keys with dots (signal.lookback=40)")

    def one(value: str):
        value = value.strip()
        low = value.lower()
        if low in ("true", "yes", "on"):
            return True
        if low in ("false", "no", "off"):
            return False
        if low in ("null", "none", ""):
            return None
        for cast in (int, float):
            try:
                return cast(value)
            except ValueError:
                pass
        return value

    value = [one(v) for v in raw.split(",")] if "," in raw else one(raw)
    return key.strip().split("."), value


def _apply_change(target: dict, path: list[str], value) -> None:
    for key in path[:-1]:
        target = target.setdefault(key, {})
        if not isinstance(target, dict):
            raise ValueError(f"{'.'.join(path)}: {key} is not a mapping")
    if value is None:
        target.pop(path[-1], None)
    else:
        target[path[-1]] = value


def _account_source(account: str) -> tuple[str, Path, dict]:
    """Which file an account is configured in (intraday.yaml or live.yaml), and its entry as written there."""
    from osloquant.intraday import engine as intraday
    from osloquant.live import engine as live

    for kind, path in (("intraday", intraday.config_path()), ("daily", live.config_path())):
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in raw.get("accounts") or []:
            if entry.get("name") == account:
                return kind, path, entry
    raise LookupError(f"no account named {account!r} in intraday.yaml or live.yaml")


def sessions_since(start, now: pd.Timestamp) -> int:
    """Whole business days from ``start`` to ``now``: how old an account is, holidays counted as sessions."""
    start = pd.Timestamp(start).normalize()
    return max(int(len(pd.bdate_range(start, now.normalize())) - 1), 0)


def rewrite(
    goat_id: str,
    changes: list[str],
    why: str,
    config: GoatsConfig | None = None,
    name: str | None = None,
    now: pd.Timestamp | None = None,
    force: bool = False,
) -> dict:
    """Give a goat new rules: a new account with the changed settings, staked with the old account's value.

    The old account keeps running in the herd under its own name (accounts are never edited or restarted); the
    goat follows the new one from now on and its record continues through the lineage. Refused while the goat's
    current account is younger than ``min_sessions_between_rewrites`` sessions, unless ``force``.
    """
    from osloquant.intraday import engine as intraday
    from osloquant.live import engine as live

    config = load_config() if config is None else config
    now = market_now() if now is None else now
    goat = config.goat(goat_id)
    why = " ".join(str(why).split())
    if not why:
        raise ValueError("a rewrite needs a reason (--why)")
    parsed = [parse_change(c) for c in changes]
    if not parsed:
        raise ValueError("a rewrite changes at least one setting (--set key=value)")
    kind, path, entry = _account_source(goat.account)

    state = intraday.load_state(goat.account)
    started = pd.Timestamp(state["start"]) if state else now
    age = sessions_since(started, now)
    if age < config.min_sessions_between_rewrites and not force:
        raise PermissionError(
            f"{goat.name}'s account {goat.account} is {age} sessions old; the troll waits {config.min_sessions_between_rewrites} (use --force to overrule)"
        )
    value = float(state["account"]["all_value"]) if state else float(entry.get("input_money", 100_000))

    new = copy.deepcopy(entry)
    new_name = name or f"{goat.id}_v{len(goat.lineage) + 2}"
    existing = {a.name for a in intraday.load_config().accounts} | {a.name for a in live.load_config().accounts}
    if new_name in existing:
        raise ValueError(f"an account named {new_name!r} exists already; pick another with --name")
    new["name"] = new_name
    for key_path, val in parsed:
        if key_path == ["name"]:
            raise ValueError("the new account's name is set with --name")
        _apply_change(new, key_path, val)
    new["input_money"] = round(value)

    # append the new account to the same file; the file's accounts list is its last section
    stamp = f"{now:%Y-%m-%d %H:%M}"
    block = yaml.safe_dump([new], sort_keys=False, default_flow_style=None, width=1000, allow_unicode=True)
    addition = f"\n  # rewritten by the troll on {stamp} from {goat.account}: {why}\n" + "".join(
        "  " + line + "\n" for line in block.splitlines()
    )
    original = path.read_text(encoding="utf-8")
    if not original.rstrip().endswith(("}", ")")) and "accounts:" not in original:
        raise ValueError(f"{path} has no accounts list to add to")
    path.write_text(original.rstrip("\n") + "\n" + addition, encoding="utf-8")
    try:
        loader = intraday.load_config if kind == "intraday" else live.load_config
        loader(path)
    except Exception as e:
        path.write_text(original, encoding="utf-8")
        raise ValueError(f"the rewritten {path.name} did not load ({e}); nothing was changed") from e

    goat.lineage.append(
        {
            "account": goat.account,
            "from": _iso(started),
            "to": _iso(now),
            "value": round(value, 2),
            "why": why,
            "changes": {".".join(k): v for k, v in parsed},
        }
    )
    goat.account = new_name
    config.rewrites += 1
    save_config(config)
    settings = ", ".join(f"{'.'.join(k)} {v}" for k, v in parsed)
    entry_text = f"{goat.name}'s rules rewritten: {goat.lineage[-1]['account']} closed its book at NOK {value:,.0f}; {new_name} starts there with {settings}. {why}"
    log_entry = add_troll_entry(
        entry_text.replace(",", " ") if False else entry_text, kind="rewrite", goat=goat.id, config=config
    )
    return {
        "goat": goat.id,
        "old": goat.lineage[-1]["account"],
        "new": new_name,
        "value": value,
        "file": str(path),
        "entry": log_entry,
        "rewrites": config.rewrites,
    }
