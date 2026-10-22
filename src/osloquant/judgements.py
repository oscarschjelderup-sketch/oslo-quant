"""The judgement log: every call written down when it is made, never edited afterwards, and scored later.

A judgement is one row: the date, the price, the rating, the 12-month target, the bull and bear values, the
probabilities of the three scenarios and the kill criteria. A changed view is a new row, not an edit. Kill checks
(at a report: was a criterion breached, and what did I do) are rows too.

The log is a JSON-lines file in the home directory (``~/osloquant-home/judgements.jsonl``, private). Each row
carries the SHA-256 of its own content and of the row before it, so ``verify()`` finds any row that was changed,
removed or reordered after it was written. The chain does not stop someone from rewriting the whole file; it
makes doing so visible against any copy kept elsewhere (the head hash is printed after every write, and the
monthly routine records it).

``calibration()`` scores every judgement against what happened: the total return since the call (adjusted
prices, so dividends count), the excess over OSEBX and over the equal-weighted universe, whether the direction
was right, how far the price is from the target, whether it stayed inside the bear-bull band and, with
probabilities, a three-way Brier score of the scenario closest to the outcome. A call younger than its horizon
is scored provisionally and marked so.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

LOG_FILE = "judgements.jsonl"
GENESIS = "0" * 64
KINDS = ("judgement", "kill_check", "note")
RATINGS = ("BUY", "HOLD", "SELL")
REQUIRED = {
    "judgement": ("code", "date", "price", "rating", "target", "horizon_months"),
    "kill_check": ("code", "date", "criterion", "breached", "action"),
    "note": ("code", "date", "text"),
}


def home() -> Path:
    from osloquant.env import init_env, oq_env

    if not oq_env:
        init_env()
    return Path(oq_env["home"])


def log_path() -> Path:
    return home() / LOG_FILE


def _canonical(row: dict) -> str:
    body = {k: v for k, v in row.items() if k not in ("hash",)}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash(row: dict) -> str:
    return hashlib.sha256(_canonical(row).encode("utf-8")).hexdigest()


def read_log(path: Path | None = None) -> list[dict]:
    path = path or log_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass
class Verification:
    ok: bool
    rows: int
    head: str
    problems: list[str]


def verify(path: Path | None = None) -> Verification:
    rows = read_log(path)
    problems, prev = [], GENESIS
    for i, row in enumerate(rows):
        if row.get("seq") != i + 1:
            problems.append(f"row {i + 1}: sequence number {row.get('seq')} (rows removed or reordered?)")
        if row.get("prev") != prev:
            problems.append(f"row {i + 1}: does not follow the row before it")
        if row.get("hash") != _hash(row):
            problems.append(f"row {i + 1}: content changed after it was written")
        prev = row.get("hash", "")
    return Verification(not problems, len(rows), prev if rows else GENESIS, problems)


def _validate(kind: str, fields: dict) -> None:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    missing = [k for k in REQUIRED[kind] if fields.get(k) in (None, "")]
    if missing:
        raise ValueError(f"a {kind} needs {', '.join(missing)}")
    if kind == "judgement":
        if fields["rating"] not in RATINGS:
            raise ValueError(f"rating must be one of {RATINGS}")
        probs = [fields.get(k) for k in ("p_bear", "p_base", "p_bull")]
        if any(p is not None for p in probs):
            if any(p is None for p in probs) or abs(sum(probs) - 1) > 0.011:
                raise ValueError("p_bear, p_base and p_bull must all be given and sum to 1")
        bear, bull, target = fields.get("bear"), fields.get("bull"), fields["target"]
        if bear is not None and bull is not None and not bear <= target <= bull:
            raise ValueError("the target must lie between the bear and bull values")


def append(kind: str, fields: dict, path: Path | None = None, now: datetime | None = None) -> dict:
    """Write one row at the end of the log and return it. Earlier rows are never touched."""
    path = path or log_path()
    check = verify(path)
    if not check.ok:
        raise RuntimeError("the log does not verify; fix or restore it before writing: " + "; ".join(check.problems[:3]))
    fields = {k: v for k, v in fields.items() if v is not None}
    if "code" in fields:
        fields["code"] = str(fields["code"]).upper().removesuffix(".OL")
    _validate(kind, fields)
    row = {"seq": check.rows + 1, "kind": kind, "logged_at": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
           **fields, "prev": check.head}
    row["hash"] = _hash(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
    return row


def judgements(rows: list[dict] | None = None) -> list[dict]:
    rows = read_log() if rows is None else rows
    return [r for r in rows if r["kind"] == "judgement"]


def latest_by_code(rows: list[dict] | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in judgements(rows):
        out[r["code"]] = r
    return out


def from_book_entry(entry: dict, date: str | None = None, price: float | None = None) -> dict:
    """The judgement fields for a research-book entry (researchbook.yaml)."""
    return dict(
        code=entry["code"], name=entry.get("name"), date=str(date or entry.get("valuation_date")),
        price=float(price if price is not None else entry["price_at_valuation"]), rating=entry.get("rating"),
        target=entry.get("target"), horizon_months=int(entry.get("horizon_months", 12)), dcf=entry.get("dcf"),
        bear=entry.get("bear"), base=entry.get("base", entry.get("dcf")), bull=entry.get("bull"),
        p_bear=entry.get("p_bear"), p_base=entry.get("p_base"), p_bull=entry.get("p_bull"),
        kill=list(entry.get("kill", [])) or None, thesis=entry.get("thesis"), source=entry.get("source"),
    )


def _same_view(a: dict, b: dict) -> bool:
    keys = ("rating", "target", "bear", "base", "bull", "p_bear", "p_base", "p_bull", "date")
    return all(a.get(k) == b.get(k) for k in keys)


def sync_book(book: list[dict], path: Path | None = None) -> list[dict]:
    """Log every research-book entry whose view differs from the newest logged judgement for that code."""
    rows = read_log(path)
    latest = latest_by_code(rows)
    written = []
    for entry in book:
        if not entry.get("rating") or not entry.get("target") or not entry.get("price_at_valuation"):
            continue
        fields = from_book_entry(entry)
        if entry["code"] in latest and _same_view(latest[entry["code"]], fields):
            continue
        written.append(append("judgement", fields, path))
    return written


# ------------------------------------------------------------------------------------------------ calibration
@dataclass
class Prices:
    adjusted: pd.DataFrame            # adjusted closes (total-return basis), codes as columns
    raw: pd.DataFrame                 # quoted closes where stored
    index: pd.Series                  # OSEBX close

    def price_on(self, frame: pd.DataFrame, code: str, day: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
        if code not in frame.columns:
            return None
        s = frame[code].dropna()
        s = s[s.index <= day]
        return (s.index[-1], float(s.iloc[-1])) if len(s) else None


def load_prices(start=None) -> Prices:
    from osloquant.contract.api import get_data
    from osloquant.domain import Index1dKdata, Stock1dAdjKdata, Stock1dKdata

    def wide(schema):
        df = get_data(schema, columns=["code", "timestamp", "close"], start_timestamp=start)
        return df.pivot(index="timestamp", columns="code", values="close") if not df.empty else pd.DataFrame()

    idx = get_data(Index1dKdata, columns=["code", "timestamp", "close"], codes=["OSEBX"], start_timestamp=start)
    return Prices(wide(Stock1dAdjKdata), wide(Stock1dKdata), idx.set_index("timestamp")["close"] if not idx.empty else pd.Series(dtype=float))


def _ret(frame_or_series, start: pd.Timestamp, end: pd.Timestamp, code: str | None = None) -> float | None:
    s = frame_or_series[code].dropna() if code is not None else frame_or_series.dropna()
    a, b = s[s.index <= start], s[s.index <= end]
    if not len(a) or not len(b):
        return None
    return float(b.iloc[-1] / a.iloc[-1] - 1)


def score(j: dict, prices: Prices, asof: pd.Timestamp, kills: list[dict]) -> dict:
    """One judgement against what happened by ``asof`` (or by the end of its horizon, if that is earlier)."""
    start = pd.Timestamp(j["date"])
    horizon_end = start + pd.DateOffset(months=int(j.get("horizon_months", 12)))
    end = min(asof, horizon_end)
    final = asof >= horizon_end
    code = j["code"]
    out = {"seq": j["seq"], "code": code, "date": j["date"], "rating": j["rating"], "price": j["price"], "target": j["target"],
           "bear": j.get("bear"), "bull": j.get("bull"), "horizon_end": f"{horizon_end:%Y-%m-%d}", "scored_to": f"{end:%Y-%m-%d}",
           "final": final, "days": int((end - start).days)}
    adj_s, adj_e = prices.price_on(prices.adjusted, code, start), prices.price_on(prices.adjusted, code, end)
    raw_s, raw_e = prices.price_on(prices.raw, code, start), prices.price_on(prices.raw, code, end)
    if adj_s is None or adj_e is None or end <= start:
        out["status"] = "no prices yet"
        return out
    # the quoted (raw) series is recorded only on request and may lag the adjusted one: use it only on the same date
    same_s = raw_s is not None and raw_s[0] == adj_s[0]
    same_e = raw_e is not None and raw_e[0] == adj_e[0]
    base_close = raw_s[1] if same_s else adj_s[1]
    # total return from the call price: the adjusted series carries the dividends; the call price may differ from
    # that day's close
    out["tsr"] = adj_e[1] / adj_s[1] * base_close / j["price"] - 1
    factor = raw_s[1] / adj_s[1] if same_s else 1.0
    out["price_now"] = raw_e[1] if same_e else adj_e[1] * factor     # quoted price (approximate when the raw series lags)
    out["price_date"] = f"{adj_e[0]:%Y-%m-%d}"
    raw = (adj_e[0], out["price_now"])
    idx = _ret(prices.index, start, end) if len(prices.index) else None
    out["osebx"] = idx
    before = prices.adjusted[prices.adjusted.index <= start]
    out["ew"] = None
    if len(before):
        base, last = before.iloc[-1], prices.adjusted[prices.adjusted.index <= end].iloc[-1]
        both = base.notna() & last.notna()
        out["ew"] = float((last[both] / base[both] - 1).mean()) if both.any() else None
    out["excess_osebx"] = out["tsr"] - idx if idx is not None else None
    expected = {"BUY": 1, "HOLD": 0, "SELL": -1}[j["rating"]]
    rel = out["excess_osebx"] if out["excess_osebx"] is not None else out["tsr"]
    out["direction_hit"] = (rel > 0) if expected == 1 else (rel < 0) if expected == -1 else (abs(rel) < 0.10)
    out["vs_target"] = raw[1] / j["target"] - 1
    out["target_reached"] = (raw[1] >= j["target"]) if j["target"] >= j["price"] else (raw[1] <= j["target"])
    if j.get("bear") is not None and j.get("bull") is not None:
        out["in_band"] = j["bear"] <= raw[1] <= j["bull"]
    probs = [j.get(k) for k in ("p_bear", "p_base", "p_bull")]
    vals = [j.get("bear"), j.get("base"), j.get("bull")]
    if final and all(p is not None for p in probs) and all(v is not None for v in vals):
        nearest = int(np.argmin([abs(raw[1] - v) for v in vals]))
        out["scenario_hit"] = ["bear", "base", "bull"][nearest]
        out["brier"] = float(sum((p - (1.0 if i == nearest else 0.0)) ** 2 for i, p in enumerate(probs)))
    mine = [k for k in kills if k["code"] == code and start <= pd.Timestamp(k["date"]) <= end]
    out["kill_checks"] = len(mine)
    out["kills_breached"] = sum(bool(k["breached"]) for k in mine)
    out["kills_acted"] = sum(bool(k["breached"]) and str(k.get("action", "")).lower() not in ("held", "none", "nothing", "ignored") for k in mine)
    out["status"] = "final" if final else "provisional"
    return out


def calibration(rows: list[dict] | None = None, prices: Prices | None = None, asof: pd.Timestamp | None = None) -> tuple[pd.DataFrame, dict]:
    rows = read_log() if rows is None else rows
    js = judgements(rows)
    kills = [r for r in rows if r["kind"] == "kill_check"]
    if not js:
        return pd.DataFrame(), {"judgements": 0}
    first = min(pd.Timestamp(j["date"]) for j in js)
    prices = prices or load_prices(start=first - pd.Timedelta(days=10))
    asof = asof or pd.Timestamp.now().normalize()
    table = pd.DataFrame([score(j, prices, asof, kills) for j in js])
    scored = table[table.get("status", pd.Series(dtype=str)).isin(["final", "provisional"])] if "status" in table else table.iloc[0:0]
    final = scored[scored["status"] == "final"] if len(scored) else scored

    def stats(t: pd.DataFrame) -> dict:
        if not len(t):
            return {"n": 0}
        d = {"n": int(len(t)), "direction_hit_rate": float(t["direction_hit"].mean()),
             "mean_abs_vs_target": float(t["vs_target"].abs().mean()), "mean_vs_target": float(t["vs_target"].mean()),
             "mean_tsr": float(t["tsr"].mean())}
        if "excess_osebx" in t and t["excess_osebx"].notna().any():
            d["mean_excess_osebx"] = float(t["excess_osebx"].mean())
        if "in_band" in t and t["in_band"].notna().any():
            d["in_band_rate"] = float(t["in_band"].dropna().astype(bool).mean())
        if "brier" in t and t["brier"].notna().any():
            d["mean_brier"] = float(t["brier"].mean())
        return d

    summary = {"judgements": len(js), "asof": f"{asof:%Y-%m-%d}", "final": stats(final), "all_scored": stats(scored),
               "kill_checks": len(kills), "kills_breached": sum(bool(k["breached"]) for k in kills),
               "kills_acted": sum(bool(k["breached"]) and str(k.get("action", "")).lower() not in ("held", "none", "nothing", "ignored") for k in kills),
               "log_head": verify().head if rows is None else None}
    return table, summary


def _p(v, d=1, sign=True):
    if v is None or (isinstance(v, float) and v != v):
        return "–"
    return f"{v * 100:{'+' if sign else ''}.{d}f}%"


def report_markdown(table: pd.DataFrame, summary: dict, check: Verification | None = None) -> str:
    out = [f"# Calibration report – {summary.get('asof', '')}", ""]
    if check is not None:
        out.append(f"Log: {check.rows} rows, chain {'verifies' if check.ok else 'BROKEN: ' + '; '.join(check.problems[:3])}, head `{check.head[:16]}`")
        out.append("")
    if not summary.get("judgements"):
        return "\n".join(out + ["No judgements logged yet: `oq book sync` logs the research book."]) + "\n"
    for label, key in (("Final (horizon reached)", "final"), ("All scored, incl. provisional", "all_scored")):
        s = summary[key]
        out.append(f"## {label}: {s['n']} calls")
        if s["n"]:
            out.append(f"- Direction right (vs OSEBX): {_p(s['direction_hit_rate'], 0, False)}")
            out.append(f"- Price vs target at scoring: mean {_p(s['mean_vs_target'])}, mean absolute {_p(s['mean_abs_vs_target'], 1, False)}")
            out.append(f"- Mean total return {_p(s['mean_tsr'])}" + (f", excess vs OSEBX {_p(s['mean_excess_osebx'])}" if "mean_excess_osebx" in s else ""))
            if "in_band_rate" in s:
                out.append(f"- Inside the bear-bull band: {_p(s['in_band_rate'], 0, False)}")
            if "mean_brier" in s:
                out.append(f"- Scenario Brier score (0 = perfect, 0.67 = uniform guess): {s['mean_brier']:.2f}")
        out.append("")
    out.append(f"## Kill criteria: {summary['kill_checks']} checks logged, {summary['kills_breached']} breached, {summary['kills_acted']} acted on")
    out.append("")
    out.append("## Every call")
    out.append("| # | Code | Date | Rating | Price | TP | Now | TSR | vs OSEBX | vs TP | In band | Status |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in table.iterrows():
        out.append(f"| {r['seq']} | {r['code']} | {r['date']} | {r['rating']} | {r['price']:.2f} | {r['target']:g} | "
                   f"{r.get('price_now', float('nan')):.2f} | {_p(r.get('tsr'))} | {_p(r.get('excess_osebx'))} | {_p(r.get('vs_target'))} | "
                   f"{'' if pd.isna(r.get('in_band')) else ('yes' if r.get('in_band') else 'no')} | {r['status']} ({r['days']} d) |")
    out.append("")
    out.append("_Provisional rows are scored on the price so far; only final rows (12-month horizon reached) count as evidence. "
               "Direction for BUY/SELL is the sign of the excess return over OSEBX; HOLD is right within ±10 %._")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------ monthly routine
HEADS_FILE = "judgements-heads.txt"


def record_head(check: Verification, when: datetime | None = None) -> Path:
    """Append the log's head hash with a timestamp: a copy kept apart from the log, so a rewritten log shows."""
    p = home() / HEADS_FILE
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"{(when or datetime.now(UTC)).strftime('%Y-%m-%dT%H:%M:%SZ')} rows={check.rows} head={check.head}\n")
    return p


def heads_consistent(check: Verification) -> list[str]:
    """Every recorded head must still be the hash of the row it pointed at (the log only grows)."""
    p = home() / HEADS_FILE
    if not p.exists():
        return []
    rows = read_log()
    problems = []
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = dict(x.split("=", 1) for x in line.split()[1:])
        n, head = int(parts["rows"]), parts["head"]
        if n == 0:
            continue
        if n > len(rows) or rows[n - 1].get("hash") != head:
            problems.append(f"recorded head at row {n} ({line.split()[0]}) no longer matches the log")
    return problems


def monthly_markdown(book: list[dict], prices: Prices, table: pd.DataFrame, summary: dict, check: Verification,
                     head_problems: list[str], today: pd.Timestamp) -> str:
    out = [f"# Monthly routine – {today:%B %Y}", "",
           f"Judgement log: {check.rows} rows, chain {'verifies' if check.ok else 'BROKEN'}; recorded heads "
           f"{'consistent' if not head_problems else 'INCONSISTENT: ' + '; '.join(head_problems)}.", ""]
    out.append("## Status of every case in the research book")
    out.append("| Code | Rating | TP | Price | to TP | to bear | to bull | Since call | Next event | Kill checks logged |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    latest = latest_by_code()
    kills = [r for r in read_log() if r["kind"] == "kill_check"]
    for e in book:
        code = e["code"]
        got = prices.price_on(prices.raw, code, today) or prices.price_on(prices.adjusted, code, today)
        if not got:
            out.append(f"| {code} | {e.get('rating', '')} | {e.get('target', '')} | – | – | – | – | – | – | – |")
            continue
        px = got[1]
        j = latest.get(code)
        since = px / j["price"] - 1 if j else None
        upcoming = [ev for ev in e.get("events", []) if pd.Timestamp(ev["date"]) >= today]
        nxt = f"{pd.Timestamp(upcoming[0]['date']):%d %b} {upcoming[0]['what'][:40]}" if upcoming else "–"
        k = sum(1 for r in kills if r["code"] == code)
        tp, bear, bull = e.get("target"), e.get("bear"), e.get("bull")
        out.append(f"| {code} | {e.get('rating', '')} | {tp} | {px:.2f} | {_p(tp / px - 1) if tp else '–'} | "
                   f"{_p(bear / px - 1) if bear else '–'} | {_p(bull / px - 1) if bull else '–'} | {_p(since)} | {nxt} | {k} |")
    out.append("")
    out.append("## Kill criteria to check this month")
    for e in book:
        due = [ev for ev in e.get("events", []) if today - pd.Timedelta(days=31) <= pd.Timestamp(ev["date"]) <= today]
        if due:
            out.append(f"- **{e['code']}** had {', '.join(ev['what'][:50] for ev in due)}: check each criterion and log it with "
                       f"`oq book kill` (breached or intact, and what you did):")
            out += [f"  - {k}" for k in e.get("kill", [])]
    if out[-1] == "## Kill criteria to check this month":
        out.append("- no report fell in the last month")
    out.append("")
    out.append(report_markdown(table, summary, None).split("\n", 2)[2])
    return "\n".join(out) + "\n"
