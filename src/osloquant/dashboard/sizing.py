"""Position size for a BUY judgement: how many shares a paper sum can hold when the kill level is the stop, and what
is lost if the kill level is reached. Paper only – nothing is bought; the size is stored in the judgement row.

    shares = min( floor(max loss / loss per share),          loss per share = price - kill level + round trip
                  floor(paper sum x max position / price),
                  floor(free paper sum / price) )            free = paper sum - open BUY positions in the log

The binding limit is named. A position whose loss at the kill level is above the limit is refused (the form says
why); so is a kill level at or above the price. The loss at the kill level is a floor, not a cap: a report or a gap
can open the price below it.

The limits are Oscar's, in ``~/osloquant-home/dashboard.yaml`` (private):

    sizing:
      paper_capital: 100000        # NOK
      max_loss: 2000               # NOK lost if the kill level is reached, per view
      max_position: 0.25           # share of the paper sum in one stock
      max_total_loss: 6000         # NOK, all open BUY views together (optional)

Without that file there is no sizing and no block.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import yaml

from osloquant import judgements as jg
from osloquant.signals import ROUND_TRIP_COST as COST

CONFIG = "dashboard.yaml"


def nok(x) -> str:
    return f"{float(x):,.0f}".replace(",", " ")


def config() -> dict | None:
    p = jg.home() / CONFIG
    if not p.exists():
        return None
    s = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sizing")
    return s if s and s.get("paper_capital") and s.get("max_loss") else None


def open_positions(rows: list[dict] | None = None, exclude: str | None = None) -> dict[str, dict]:
    """The newest judgement per stock that is a BUY with a position: its value and loss at the kill level."""
    latest = jg.latest_by_code(rows)
    return {c: r for c, r in latest.items() if c != exclude and r.get("rating") == "BUY" and r.get("position_shares")}


@dataclass
class Size:
    shares: int
    binding: str
    value: float
    loss_at_kill: float
    loss_per_share: float
    limits: dict
    free: float
    open_loss: float


def size(price: float, kill: float, cfg: dict, code: str | None = None, rows: list[dict] | None = None) -> Size:
    if not kill < price:
        raise ValueError(f"the kill level {kill:g} must be below the price {price:.2f} for a BUY")
    lps = price - kill + COST * price
    opened = open_positions(rows, exclude=code)
    used = sum(float(r.get("position_value") or 0) for r in opened.values())
    open_loss = sum(float(r.get("loss_at_kill") or 0) for r in opened.values())
    free = max(float(cfg["paper_capital"]) - used, 0.0)
    limits = {"max loss": math.floor(float(cfg["max_loss"]) / lps),
              "max position": math.floor(float(cfg["paper_capital"]) * float(cfg.get("max_position", 1.0)) / price),
              "free paper sum": math.floor(free / price)}
    if cfg.get("max_total_loss"):
        limits["total loss, all open views"] = math.floor(max(float(cfg["max_total_loss"]) - open_loss, 0) / lps)
    binding = min(limits, key=limits.get)
    n = max(limits[binding], 0)
    return Size(n, binding, round(n * price, 2), round(n * lps, 2), round(lps, 4), limits, round(free, 2), round(open_loss, 2))


def check(shares: int, price: float, kill: float, cfg: dict, code: str, rows: list[dict] | None = None) -> tuple[Size, list[str]]:
    """The largest allowed size and what is wrong with ``shares`` (empty = it can be written)."""
    s = size(price, kill, cfg, code, rows)
    problems = []
    if shares < 0:
        problems.append("the position cannot be negative")
    loss = shares * s.loss_per_share
    if loss > float(cfg["max_loss"]) + 1e-6:
        problems.append(f"the loss at the kill level would be NOK {nok(loss)}, above your limit of NOK {nok(cfg['max_loss'])} "
                        f"(dashboard.yaml); at most {s.limits['max loss']} shares")
    if shares > s.limits["max position"]:
        problems.append(f"{shares} shares is more than {float(cfg.get('max_position', 1)) * 100:.0f} % of the paper sum; at most {s.limits['max position']}")
    if shares > s.limits["free paper sum"]:
        problems.append(f"only NOK {nok(s.free)} of the paper sum is free; at most {s.limits['free paper sum']} shares")
    if "total loss, all open views" in s.limits and shares > s.limits["total loss, all open views"]:
        problems.append(f"all open views together would lose more than NOK {nok(cfg['max_total_loss'])} at their kill levels; "
                        f"at most {s.limits['total loss, all open views']} shares")
    return s, problems
