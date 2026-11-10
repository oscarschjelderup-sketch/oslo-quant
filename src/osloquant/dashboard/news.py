"""News that matters first (D67). The dashboard already fetched announcements (Oslo Børs NewsWeb) and headlines (RSS);
it showed them by the clock. A list by the clock cannot be read in ten seconds, so every item gets a weight and the
list is sorted by it.

The weight is a sum of three things a person would look at, each visible as a reason beside the headline:

1. **What kind of item it is.** Inside information, a report or a corporate event (share issue, demerger, delisting)
   weighs most; a flagging or an insider trade less; a routine buy-back notice least. The kind is read from NewsWeb's
   own category and from the title.
2. **What the price did that session**, measured against the stock's own daily moves over the sixty sessions before:
   a move of 2.5 standard deviations says more than the headline does.
3. **Whether the company is in the research book or on the watchlist.**

Only titles and links are used and shown. Nothing is fetched here; the module reads the feed caches. A weight is a
sorting key, not a signal: it says «read this first», never «buy» or «sell».
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pandas as pd

from osloquant.dashboard import feeds as fd
from osloquant.dashboard.dates import dato
from osloquant.dashboard.tall import tall

#: NewsWeb's categories (as the feed stores them, upper case) -> (weight, the kind a person reads)
CATEGORY = {
    "INSIDE INFORMATION": (5, "innsideinformasjon"),
    "HALF YEAR FINANCIAL REPORT": (5, "rapport"), "ANNUAL FINANCIAL AND AUDIT REPORTS": (5, "rapport"), "INTERIM REPORT": (5, "rapport"),
    "MAJOR SHAREHOLDINGS NOTIFICATION": (3, "flagging"),
    "MANAGERS’ TRANSACTION": (3, "innsidehandel"), "MANAGERS' TRANSACTION": (3, "innsidehandel"),
    "PROSPECTUS / ADMISSION DOCUMENT": (3, "prospekt"),
    "EX DATE": (2, "eks-dato"),
    "ADDITIONAL REGULATED INFORMATION REQUIRED TO BE DISCLOSED UNDER THE LAWS OF A MEMBER STATE": (2, "børsmelding"),
    "NON-REGULATORY PRESS RELEASES": (2, "pressemelding"),
    "TOTAL NUMBER OF VOTING RIGHTS AND CAPITAL": (1, "kapital"),
    "ACQUISITION OR DISPOSAL OF AN ISSUER'S OWN SHARES": (1, "egne aksjer"), "ACQUISITION OR DISPOSAL OF AN ISSUER’S OWN SHARES": (1, "egne aksjer"),
    "ADJUSTMENT OF INTEREST RATE": (0, "obligasjonsrente"),
}
REPORT_TITLE = re.compile(r"(?i)\b(q[1-4]|[1-4]q|first|second|third|fourth|1st|2nd|3rd|4th|første|andre|tredje|fjerde)[ -]?(quarter|kvartal)?\b.*\b(results?|resultat\w*|report|rapport)\b"
                          r"|\b(results?|resultat\w*) for (the )?(first|second|third|fourth|q[1-4])|kvartalsrapport|quarterly report|annual report|årsrapport")
ROUTINE_TITLE = re.compile(r"(?i)buy-?back|tilbakekj[øo]p|share repurchase|invitation to|invitasjon til|presentation of|presentasjon av|financial calendar|finansiell kalender")
MEDIA_WEIGHT = 2
BOOK_BONUS, WATCH_BONUS = 2, 1
VOL_WINDOW = 60
TOP, MIDDLE = 6, 4          # weight at or above: shown as «viktig», «verdt å lese»


def kind_of(item: dict) -> tuple[int, str]:
    """The base weight and the kind of one announcement or headline."""
    if item.get("outlet"):
        return MEDIA_WEIGHT, str(item["outlet"])
    title = item.get("title", "")
    corp = fd.corporate_kind(title)
    if corp:
        return 5, corp
    w, kind = CATEGORY.get(str(item.get("category") or "").upper().strip(), (2, "børsmelding"))
    if REPORT_TITLE.search(title) and not ROUTINE_TITLE.search(title):
        w, kind = max(w, 5), "rapport"
    if ROUTINE_TITLE.search(title):
        w = min(w, 1)
    return w, kind


def session_of(stamp: str, index: pd.DatetimeIndex) -> pd.Timestamp | None:
    """The trading session an item belongs to: the day it was published, or the next session when it came after the
    close (16:30 Oslo time) or on a day without trading."""
    try:
        t = pd.Timestamp(stamp)
        t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert("Europe/Oslo")
    except (ValueError, TypeError):
        return None
    day = t.normalize().tz_localize(None)
    if (t.hour, t.minute) >= (16, 30):
        day += pd.Timedelta(days=1)
    later = index[index >= day]
    return later[0] if len(later) else None


def reaction(closes: pd.Series | None, session: pd.Timestamp | None) -> dict | None:
    """The session's return and how unusual it was: the return divided by the standard deviation of the sixty daily
    returns before it. None when the session is not in the store yet or the history is too short."""
    if closes is None or session is None:
        return None
    c = closes.dropna()
    if session not in c.index:
        return None
    i = c.index.get_loc(session)
    if i < 21:
        return None
    rets = c.pct_change()
    sd = float(rets.iloc[max(1, i - VOL_WINDOW):i].std())
    r = float(rets.iloc[i])
    return {"ret": r, "z": abs(r) / sd if sd > 0 else 0.0, "session": session}


def weigh(item: dict, closes: pd.Series | None = None, in_book: bool = False, watched: bool = False) -> dict:
    """One item with its weight, its kind and the reasons a person can read."""
    base, kind = kind_of(item)
    reasons, w = [], base
    react = reaction(closes, session_of(item.get("time", ""), closes.dropna().index)) if closes is not None and len(closes.dropna()) else None
    if react and react["z"] >= 1.5:
        bump = 3 if react["z"] >= 4 else 2 if react["z"] >= 2.5 else 1
        w += bump
        reasons.append(f'kursen {tall(react["ret"] * 100, 1, sign=True)} % den dagen, {tall(react["z"], 1)} ganger et vanlig dagsutslag')
    if in_book:
        w += BOOK_BONUS
        reasons.append("i research book")
    elif watched:
        w += WATCH_BONUS
        reasons.append("på overvåkningslisten")
    return {**item, "weight": w, "base": base, "kind_no": kind, "reasons": reasons, "react": react,
            "level": 3 if w >= TOP else 2 if w >= MIDDLE else 1, "url": item.get("url") or item.get("link") or ""}


def _dedupe(items: list[dict]) -> list[dict]:
    """Issuers publish the same message in Norwegian and English in the same minute: keep one per company and minute,
    the Norwegian one when there is a choice (the page is Norwegian)."""
    groups: dict[tuple, list[dict]] = {}
    for it in items:
        groups.setdefault((it.get("code"), str(it.get("time", ""))[:16], bool(it.get("outlet"))), []).append(it)
    out = []
    for g in groups.values():
        g.sort(key=lambda x: (not re.search(r"[æøåÆØÅ]", x.get("title", "")), str(x.get("id", ""))))
        out.append(g[0])
    return out


def collect(codes: set[str] | list[str], names: dict[str, str], days: int = 3, now: datetime | None = None) -> list[dict]:
    """Announcements for ``codes`` and media headlines that name one of them, from the last ``days`` days."""
    codes = set(codes)
    cutoff = f"{(now or datetime.now(UTC)) - timedelta(days=days):%Y-%m-%dT%H:%M}"
    items = [dict(a) for a in (fd.read("announcements") or {}).get("items", []) if a.get("code") in codes and a.get("time", "") >= cutoff]
    for n in (fd.read("news") or {}).get("items", []):
        if n.get("time", "") < cutoff:
            continue
        for code in codes:
            if fd.mentions(n.get("title", ""), code, names):
                items.append({**n, "code": code})
                break
    return _dedupe(items)


def ranked(snap, codes: set[str] | list[str], book: set[str] = frozenset(), watch: set[str] = frozenset(), days: int = 3, limit: int | None = None,
           now: datetime | None = None) -> list[dict]:
    """The items for ``codes``, heaviest first, newest first among equals."""
    C = snap.panel["close"]
    out = [weigh(it, C[it["code"]] if it["code"] in C.columns else None, it["code"] in book, it["code"] in watch) for it in collect(codes, snap.names, days, now)]
    out.sort(key=lambda x: (x["weight"], x.get("time", "")), reverse=True)
    return out[:limit] if limit else out


def by_day(snap, code: str, days: int = 120, extra: list[dict] | None = None, now: datetime | None = None) -> list[dict]:
    """The stock's items grouped by trading session, newest session first, each with what the price did that session."""
    C = snap.panel["close"]
    closes = C[code] if code in C.columns else None
    items = [weigh(it, closes) for it in collect({code}, snap.names, days, now)] + list(extra or [])
    index = closes.dropna().index if closes is not None else pd.DatetimeIndex([])
    groups: dict[pd.Timestamp, list[dict]] = {}
    for it in items:
        day = session_of(it.get("time", ""), index) if len(index) else None
        if day is None:
            try:
                day = pd.Timestamp(str(it.get("time", ""))[:10])
            except ValueError:
                continue
        groups.setdefault(day, []).append(it)
    out = []
    for day in sorted(groups, reverse=True):
        its = sorted(groups[day], key=lambda x: (x.get("weight", 0), x.get("time", "")), reverse=True)
        out.append({"day": day, "items": its, "react": reaction(closes, day) if closes is not None else None})
    return out


def chart_events(snap, code: str, days: int = 400, now: datetime | None = None) -> list[dict]:
    """The stock's weighty announcements for the price chart: what happened when the price moved."""
    C = snap.panel["close"]
    closes = C[code] if code in C.columns else None
    out = []
    for it in collect({code}, snap.names, days, now):
        if it.get("outlet"):
            continue
        w = weigh(it, closes)
        if w["base"] >= 3 or (w["react"] and w["react"]["z"] >= 2.5):
            out.append({"time": w["time"], "title": w["title"], "kind_no": w["kind_no"], "react": w["react"]})
    return out


# ------------------------------------------------------------------------------------------------ html
def _when(stamp: str) -> str:
    try:
        t = pd.Timestamp(stamp)
        t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert("Europe/Oslo")
        return f"{dato(t, False)} {t:%H:%M}"
    except (ValueError, TypeError):
        return ""


def item_html(it: dict, with_code: bool = True, static: bool = False) -> str:
    from osloquant.dashboard.render import E, link

    title = (f'<a href="{E(it["url"])}" target="_blank" rel="noopener">{E(it.get("title", ""))}</a>' if it.get("url") else E(it.get("title", "")))
    who = (f'<b>{link(it["code"], static=static)}</b> ' if with_code and it.get("code") else "")
    why = f'<span class="why">{E(" · ".join(it["reasons"]))}</span>' if it.get("reasons") else ""
    return (f'<li data-k="{"nyheter" if it.get("outlet") else "borsmelding"}"><span class="nwhen">{_when(it.get("time", ""))}</span>'
            f'<span>{who}{title}<div class="nmeta"><span class="nkind k{it.get("level", 1)}" title="Vekt {it.get("weight", 0)}: type {it.get("base", 0)}'
            f'{", pluss kursreaksjon og om du følger aksjen" if it.get("weight", 0) > it.get("base", 0) else ""}">{E(it.get("kind_no", ""))}</span>{why}</div></span></li>')


def list_html(items: list[dict], empty: str, with_code: bool = True, static: bool = False) -> str:
    if not items:
        return f'<p class="empty">{empty}</p>'
    return f'<ul class="nlist">{"".join(item_html(it, with_code, static) for it in items)}</ul>'


def source_line() -> str:
    from osloquant.dashboard.dates import stempel

    ann, news = fd.read("announcements") or {}, fd.read("news") or {}
    got = lambda d: stempel(d["fetched_at"]) if d.get("fetched_at") else "ikke hentet"  # noqa: E731
    return (f'Børsmeldinger: Oslo Børs NewsWeb (hentet {got(ann)}). Overskrifter: E24, DN, Finansavisen og NRK via RSS (hentet {got(news)}); bare overskrift og lenke. '
            'Rekkefølgen er en vekt av type melding, kursbevegelsen den dagen målt mot aksjens egne dagsutslag, og om du følger aksjen. '
            'Vekten sier hva som bør leses først, ikke hva som bør gjøres.')


def front_html(snap, book: set[str], watch: set[str], static: bool = False, now: datetime | None = None) -> str:
    """The front page's news: the heaviest items for the followed stocks, then the heaviest in the rest of the universe."""
    followed = set(book) | set(watch)
    mine = ranked(snap, followed, book, watch, days=3, now=now) if followed else []
    top, rest_mine = mine[:6], mine[6:]
    others = [x for x in ranked(snap, set(snap.names) - followed, days=2, now=now) if x["weight"] >= MIDDLE][:8]
    empty = ("Ingen børsmelding eller overskrift om aksjene du følger de siste tre dagene." if followed
             else "Ingen aksjer i research book eller på overvåkningslisten ennå – legg til en under Overvåkning, så vises nyhetene deres her.")
    more = (f'<details><summary>{len(rest_mine)} til om aksjene du følger</summary>{list_html(rest_mine, "", static=static)}</details>' if rest_mine else "")
    other = (f'<details><summary>{len(others)} viktige meldinger om andre aksjer i universet (siste to dager)</summary>{list_html(others, "", static=static)}</details>'
             if others else "")
    return (f'<h2 id="nyheter">Nyheter som betyr noe ({len(mine)} om aksjene du følger)</h2><div class="card">{list_html(top, empty, static=static)}{more}{other}'
            f'<div class="src">{source_line()}</div></div>')


def day_html(groups: list[dict], empty: str) -> str:
    """The stock page's news, one block per session with what the price did."""
    from osloquant.dashboard.render import E

    if not groups:
        return f'<p class="empty">{empty}</p>'
    out = []
    for g in groups:
        r = g["react"]
        move = ""
        if r:
            cls = "up" if r["ret"] > 0 else "down" if r["ret"] < 0 else ""
            big = f' · {tall(r["z"], 1)} ganger et vanlig dagsutslag' if r["z"] >= 1.5 else ""
            move = f'<span class="move {cls}" title="Sluttkurs mot forrige sluttkurs, justert; Yahoo via lageret, forsinket">kurs {tall(r["ret"] * 100, 1, sign=True)} %</span><span class="src">{E(big)}</span>'
        out.append(f'<div class="nday">{dato(g["day"], False, weekday=True)}{move}</div>{list_html(g["items"], "", with_code=False)}')
    return "".join(out)
