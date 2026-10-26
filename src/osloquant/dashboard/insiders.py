"""Primary-insider trades from Oslo Børs NewsWeb (category 1102, "Managers' transaction") and net short positions
from Finanstilsynet's short sale register – fetched into the private cache, read by the dashboard, and measured.

NewsWeb's terms allow private use only: the cache (``~/osloquant-home/feeds/insiders.json``) holds each
notification's title, time, link and its text, and stays on this machine. The study's aggregate numbers are ours.

A notification is classified from its text: ``buy`` (open-market purchase), ``sell``, ``subscription`` (shares
subscribed in an issue), ``programme`` (share programmes, options, awards, matching shares, dividend reinvestment),
``company`` (the company buying or selling its own shares), ``other`` (loans, pledges, derivatives such as TRS,
gifts, inheritance, transfers between own companies) or
``unknown``. Only ``buy`` and ``sell`` enter the study; everything else is shown but not measured.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from osloquant.dashboard import feeds as fd
from osloquant.signals import ROUND_TRIP_COST as COST

CATEGORY = 1102
NEWSWEB = fd.NEWSWEB
SSR = "https://ssr.finanstilsynet.no/api/v2/instruments"
PAUSE = 0.35            # seconds between NewsWeb requests: one notification body per request, so be gentle


# ------------------------------------------------------------------------------------------------ classification
_PROGRAMME = r"(programm|program\b|\blti\b|\brsus?\b|\bpsus?\b|matching share|\baward|\bgrant|incentive|insentiv|bonus|option|opsjon|" \
             r"exercis|innl[øo]s|\butøv|\bvest(ing|ed|s)?\b|dividend reinvest|scrip|share saving|aksjespar|employee|ansatte)"
_OTHER = r"(\btrs\b|total return swap|\bpledg|\bpant(satt|sett|ed)?\b|\bloans?\b|\blån\b|\blånt|\blend|\bgift|\bgave\b|inherit|\barv\b|" \
         r"transferr|transfer of|overf[øo]r|\bforward|\bfutures?\b|derivat|\bswaps?\b|collateral|security interest|\bconver(t|sion)|konverter)"
_SUBSCRIPTION = r"(subscri|\btegnet|\btegning|private placement|rettet emisjon|rights issue|fortrinnsrett)"
_COMPANY = r"(own shares|egne aksjer|treasury shares|buy-?back|tilbakekjøp)"     # the company trading its own shares
_BUY = r"(\bbought\b|\bbuys?\b|purchas|\bacquir|\bkjøp|ervervet|\berverv)"
_SELL = r"(\bsold\b|\bsells?\b|\bsale\b|dispos|divest|\bsolgt|\bsalg\b|\bselger\b|avhend)"


def classify(title: str, body: str, issuer: str | None = None) -> tuple[str, str]:
    """The side of a notification and the words that decided it. ``issuer`` (e.g. "Hexagon Composites ASA") catches
    the company itself as the buyer or seller."""
    text = f"{title} {body}".lower()
    text = re.sub(r"\s+", " ", text)
    if issuer:
        name = re.escape(re.sub(r"\s+(asa|limited|ltd\.?|plc|se|ab)$", "", issuer.lower().strip()))
        m = re.search(rf"\b{name}(?: asa| limited| ltd\.?)? (?:has )?(?:today |on [^,.]{{1,30}} )?(bought|purchased|acquired|sold|kjøpt|solgt)", text)
        if m:
            return "company", m.group(0)
    for side, pat in (("company", _COMPANY), ("programme", _PROGRAMME), ("other", _OTHER), ("subscription", _SUBSCRIPTION)):
        m = re.search(pat, text)
        if m:
            return side, m.group(0)
    buy, sell = re.search(_BUY, text), re.search(_SELL, text)
    if buy and sell:
        return "unknown", f"both '{buy.group(0)}' and '{sell.group(0)}'"
    if buy:
        return "buy", buy.group(0)
    if sell:
        return "sell", sell.group(0)
    return "unknown", ""


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


# ------------------------------------------------------------------------------------------------ fetching
def cache_name() -> str:
    return "insiders"


def load() -> dict:
    return fd.read(cache_name()) or {"items": {}, "fetched_years": {}}


def _list(code: str, start: date, end: date) -> list[dict]:
    """All category-1102 messages for one issuer between two dates; windows are halved while NewsWeb overflows."""
    url = f"{NEWSWEB}/list?issuer={code}&category={CATEGORY}&fromDate={start:%Y-%m-%d}&toDate={end:%Y-%m-%d}"
    doc = json.loads(fd._get(url, method="POST"))["data"]
    if doc.get("overflow") and (end - start).days > 1:
        mid = start + (end - start) / 2
        return _list(code, start, mid) + _list(code, mid + timedelta(days=1), end)
    return doc.get("messages", [])


def _pick(messages: list[dict]) -> list[dict]:
    """Issuers often publish one notification twice (Norwegian and English) in the same minute: keep one per minute,
    preferring the English title, so the study does not count an event twice."""
    groups: dict[tuple, list[dict]] = {}
    for m in messages:
        groups.setdefault((m.get("issuerSign"), m["publishedTime"][:16]), []).append(m)
    out = []
    for ms in groups.values():
        ms = sorted(ms, key=lambda m: (bool(re.search(r"[æøåÆØÅ]", m["title"])), m["messageId"]))
        out.append(ms[0])
    return out


def fetch(codes: list[str], start_year: int = 2010, today: date | None = None, log=print, save_every: int = 100) -> dict:
    """Fill the cache with every notification for ``codes`` since ``start_year``. Resumable: years already listed are
    listed again only for the current year, and a body already in the cache is never fetched again."""
    today = today or datetime.now(UTC).date()
    doc = load()
    items, years = doc["items"], doc["fetched_years"]
    new = 0
    for code in codes:
        for y in range(start_year, today.year + 1):
            key = f"{code}:{y}"
            if years.get(key) and y < today.year:
                continue
            msgs = _pick(_list(code, date(y, 1, 1), min(date(y, 12, 31), today)))
            time.sleep(PAUSE)
            for m in msgs:
                mid = str(m["messageId"])
                if mid in items:
                    continue
                full = json.loads(fd._get(f"{NEWSWEB}/message?messageId={mid}"))["data"]["message"]
                time.sleep(PAUSE)
                body = _text(full.get("body", ""))
                side, why = classify(m["title"], body, m.get("issuerName"))
                items[mid] = {"id": int(mid), "code": code, "issuer": m.get("issuerName"), "title": m["title"],
                              "time": m["publishedTime"], "url": f"https://newsweb.oslobors.no/message/{mid}",
                              "body": body[:4000], "attachments": [a.get("name") for a in full.get("attachments") or []],
                              "side": side, "why": why}
                new += 1
                if new % save_every == 0:
                    fd.write(cache_name(), {**doc, "source": "Oslo Børs NewsWeb, category 1102 (private use only)"})
                    log(f"  {new} new notifications cached (at {code} {y})")
            years[key] = True
        log(f"{code}: done ({sum(1 for i in items.values() if i['code'] == code)} notifications)")
    fd.write(cache_name(), {**doc, "source": "Oslo Børs NewsWeb, category 1102 (private use only)"})
    return doc


def reclassify() -> dict:
    """Apply the current classifier to the cached texts (after the rules change), without fetching."""
    doc = load()
    for it in doc["items"].values():
        it["side"], it["why"] = classify(it["title"], it.get("body", ""), it.get("issuer"))
    fd.write(cache_name(), doc)
    return doc


def fetch_shorts() -> dict:
    """Finanstilsynet's public short positions (≥ 0.5 %, the last two years), per issuer, daily."""
    data = json.loads(fd._get(SSR))
    return {"instruments": data, "source": "Finanstilsynet, short sale register (public positions ≥ 0.5 %, last two years)"}


# The register names issuers its own way; checked by hand on 23 Oct 2026 against its issuer list. A code that is not
# here had no public short position (≥ 0.5 %) in the register's two-year window then.
SSR_NAMES = {
    "EQNR": "EQUINOR", "AKRBP": "AKER BP", "VAR": "VÅR ENERGI ASA", "DNO": "DNO", "PEN": "PANORO ENERGY", "TGS": "TGS ASA",
    "AKSO": "AKER SOLUTIONS", "BORR": "BORR DRILLING LIMITED", "DOFG": "DOF GROUP ASA", "ARCH": "ARCHER", "HAFNI": "HAFNIA LIMITED",
    "OET": "OKEANIS ECO TANKERS", "BWLPG": "BW LPG", "SNI": "STOLT-NIELSEN", "WAWI": "WALLENIUS WILHELMSEN",
    "HAUTO": "HOEGH AUTOLINERS ASA", "MPCC": "MPC CONTAINER SHIPS", "MOWI": "MOWI", "SALM": "SALMAR", "BAKKA": "BAKKAFROST",
    "GSF": "GRIEG SEAFOOD", "NHY": "NORSK HYDRO", "YAR": "YARA INTERNATIONAL", "ELK": "ELKEM", "BRG": "BORREGAARD",
    "TOM": "TOMRA SYSTEMS", "HEX": "HEXAGON COMPOSITES", "ORK": "ORKLA", "EPR": "EUROPRIS", "KID": "KID", "SATS": "SATS",
    "NAS": "NORWEGIAN AIR SHUTTLE", "NOD": "NORDIC SEMICONDUCTOR", "BOUV": "BOUVET", "AUTO": "AUTOSTORE HOLDINGS LTD.",
    "NEL": "NEL", "SCATC": "SCATEC ASA",
}


def shorts(code: str, doc: dict | None = None) -> dict | None:
    """The register's history for one stock: the total public short in % of shares by date (oldest first) and the
    holders on the newest date. None when the stock is not in the register."""
    doc = doc if doc is not None else (fd.read("shorts") or {})
    name = SSR_NAMES.get(code)
    inst = next((i for i in doc.get("instruments", []) if i.get("issuerName") == name), None) if name else None
    if not inst:
        return None
    ev = sorted(inst.get("events", []), key=lambda e: e["date"])
    series = [(e["date"][:10], float(e.get("shortPercent") or 0)) for e in ev]
    last = ev[-1] if ev else {}
    holders = sorted(((p["positionHolder"], float(p["shortPercent"])) for p in last.get("activePositions", [])), key=lambda x: -x[1])
    return {"isin": inst.get("isin"), "series": series, "now": series[-1][1] if series else 0.0, "date": series[-1][0] if series else None,
            "holders": holders, "fetched_at": doc.get("fetched_at"), "source": doc.get("source", "")}


def short_change(s: dict, days: int) -> float | None:
    """Change in the total public short over ``days`` calendar days (percentage points)."""
    if not s or not s["series"]:
        return None
    cut = (datetime.strptime(s["date"], "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    before = [v for d, v in s["series"] if d <= cut]
    return s["now"] - (before[-1] if before else 0.0)


def short_moves(codes, days: int = 7, min_pp: float = 0.25) -> list[dict]:
    """Followed stocks whose public short moved at least ``min_pp`` points in ``days`` days (or appeared/vanished)."""
    doc = fd.read("shorts") or {}
    out = []
    for c in codes:
        s = shorts(c, doc)
        if not s:
            continue
        ch = short_change(s, days)
        recent = s["date"] and s["date"] >= (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        if ch is not None and abs(ch) >= min_pp and recent:
            out.append({"code": c, "now": s["now"], "change": ch, "date": s["date"], "holders": s["holders"][:3]})
    return out


# ------------------------------------------------------------------------------------------------ the study
STUDY_HORIZONS = (20, 60, 120, 250)


def events(items, side: str = "buy", sessions: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """One event per stock and publication day (several insiders on one day are one event), with the entry session:
    the first session that opens after the notification was published (Oslo time; before 09:00 = the same day)."""
    rows = []
    for it in items:
        if it["side"] != side:
            continue
        t = pd.Timestamp(it["time"]).tz_convert("Europe/Oslo")
        rows.append({"code": it["code"], "day": t.normalize().tz_localize(None), "before_open": t.hour < 9, "id": it["id"]})
    if not rows:
        return pd.DataFrame(columns=["code", "day", "entry", "notifications"])
    df = pd.DataFrame(rows).groupby(["code", "day"]).agg(before_open=("before_open", "all"), notifications=("id", "count")).reset_index()
    if sessions is not None:
        pos_same = sessions.searchsorted(df["day"], side="left")
        pos_next = sessions.searchsorted(df["day"], side="right")
        same_ok = (pos_same < len(sessions)) & (sessions[np.minimum(pos_same, len(sessions) - 1)] == df["day"]) & df["before_open"]
        pos = np.where(same_ok, pos_same, pos_next)
        df["entry_pos"] = pos
        df = df[df["entry_pos"] < len(sessions)].copy()
        df["entry"] = sessions[df["entry_pos"]]
    return df


def study(P: dict[str, pd.DataFrame], items, horizons=STUDY_HORIZONS, cost: float = COST, start: str = "2010-01-01") -> dict:
    """Excess return after insider buys and sells: entry at the open of the entry session, exit at the close ``h``
    sessions later, minus the equal-weighted return of the 64 stocks over the same window; also after a round trip.
    t-statistics use one average per calendar month (events in the same month are not independent)."""
    C = P["close"].loc[start:]
    sessions = C.index
    cv, ov = C.to_numpy(dtype=float), P["open"].loc[start:].to_numpy(dtype=float)
    col = {c: j for j, c in enumerate(C.columns)}
    out = {}
    items = list(items)
    for side in ("buy", "sell"):
        ev = events(items, side, sessions)
        ev = ev[ev["code"].isin(col)]
        res = {"events": int(len(ev)), "stocks": int(ev["code"].nunique()) if len(ev) else 0,
               "first": f"{ev['entry'].min():%Y-%m-%d}" if len(ev) else None, "last": f"{ev['entry'].max():%Y-%m-%d}" if len(ev) else None}
        for h in horizons:
            ex, months = [], []
            for _, e in ev.iterrows():
                i, j = int(e["entry_pos"]), col[e["code"]]
                if i + h - 1 >= len(sessions) or not np.isfinite(ov[i, j]) or not np.isfinite(cv[i + h - 1, j]):
                    continue
                raw = cv[i + h - 1, :] / ov[i, :] - 1
                bench = np.nanmean(raw)
                ex.append(raw[j] - bench)
                months.append(f"{sessions[i]:%Y-%m}")
            ex = np.array(ex)
            if not len(ex):
                res[f"h{h}"] = {"n": 0}
                continue
            by_month = pd.Series(ex).groupby(months).mean()
            t = float(by_month.mean() / by_month.std(ddof=1) * np.sqrt(len(by_month))) if len(by_month) > 2 and by_month.std(ddof=1) > 0 else None
            res[f"h{h}"] = {"n": int(len(ex)), "months": int(len(by_month)), "mean_excess": round(float(ex.mean()), 4),
                            "median_excess": round(float(np.median(ex)), 4), "hit": round(float((ex > 0).mean()), 4),
                            "net_of_cost": round(float(ex.mean() - cost), 4), "t_month": None if t is None else round(t, 2)}
        out[side] = res
    return out


# ------------------------------------------------------------------------------------------------ readers (pages)
def recent(codes: set[str] | list[str], days: int = 7, sides=("buy", "sell", "subscription")) -> list[dict]:
    cutoff = f"{datetime.now(UTC) - timedelta(days=days):%Y-%m-%d}"
    items = load()["items"].values()
    return sorted((i for i in items if i["code"] in codes and i["time"][:10] >= cutoff and i["side"] in sides),
                  key=lambda i: i["time"], reverse=True)


def for_code(code: str, limit: int = 15) -> list[dict]:
    items = [i for i in load()["items"].values() if i["code"] == code]
    return sorted(items, key=lambda i: i["time"], reverse=True)[:limit]
