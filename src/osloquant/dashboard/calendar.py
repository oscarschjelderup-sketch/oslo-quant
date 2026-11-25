"""The event calendar: report dates and meetings from the issuers' own financial-calendar announcements on NewsWeb,
the research book's events, the rate meetings of Norges Bank, the Fed and the ECB, and the releases of SSB and of the
US (FRED) – one list with a source and a fetch time on every date (DECISIONS D26, D71).

NewsWeb issuers publish "Financial calendar" messages in a fixed form: "DD.MM.YYYY - Quarterly Report - Q3". The
fetcher takes the newest such message per followed company (one list request and one message request each) and
keeps the parsed dates in the private feed cache. The central banks' dates come from resource files with the page they
were copied from and the day they were read; if a file is missing, the page says so instead of guessing. SSB's and the
US release dates come with the macro feed.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from importlib import resources

import pandas as pd
import yaml

from osloquant.dashboard import feeds as fd
from osloquant.dashboard.dates import dato, stempel

CAL_FEED = "calendar"
_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s*[-–]\s*(.+?)(?=\s+\d{2}\.\d{2}\.\d{4}\s*[-–]|\s+FINANCIAL YEAR|\s+This information|$)", re.I)
_YEAR = re.compile(r"FINANCIAL YEAR\s+(\d{4})", re.I)


def parse_financial_calendar(text: str) -> list[dict]:
    """Dates and what happens on them, from the body of a NewsWeb financial-calendar message."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()
    out = []
    for m in _DATE.finditer(text):
        d, mo, y, what = m.groups()
        try:
            day = datetime(int(y), int(mo), int(d))
        except ValueError:
            continue
        out.append({"date": f"{day:%Y-%m-%d}", "what": what.strip().rstrip(".")})
    return sorted(out, key=lambda e: e["date"])


def fetch_financial_calendars(codes: list[str], days_back: int = 400) -> dict:
    """The newest financial-calendar message per company, parsed. Companies without one are listed as such."""
    today = datetime.now(UTC).date()
    out = {"companies": {}, "source": "Oslo Børs NewsWeb, the issuers' own 'Financial calendar' announcements (private use only)"}
    for code in codes:
        url = f"{fd.NEWSWEB}/list?issuer={code}&fromDate={today - timedelta(days=days_back):%Y-%m-%d}&toDate={today:%Y-%m-%d}"
        msgs = json.loads(fd._get(url, method="POST"))["data"].get("messages", [])
        cal = [m for m in msgs if re.search(r"(?i)financial calendar|finansiell kalender", m["title"])]
        if not cal:
            out["companies"][code] = {"message_id": None, "published": None, "events": []}
            continue
        newest = max(cal, key=lambda m: m["publishedTime"])
        body = json.loads(fd._get(f"{fd.NEWSWEB}/message?messageId={newest['messageId']}"))["data"]["message"].get("body", "")
        out["companies"][code] = {"message_id": newest["messageId"], "published": newest["publishedTime"], "events": parse_financial_calendar(body),
                                  "url": f"https://newsweb.oslobors.no/message/{newest['messageId']}"}
    return out


#: key, the name the dashboard shows, the resource file with the dates
BANKS = (("norges_bank", "Norges Bank", "norges_bank_meetings.yaml"), ("fed", "Fed", "fed_meetings.yaml"), ("ecb", "ESB", "ecb_meetings.yaml"))
#: a meeting file whose last date is closer than this needs the next year from the bank's page
REFILL_DAYS = 90
#: «Feds møteplan»: the bank's name as an owner
OWNER = {"norges_bank": "Norges Banks", "fed": "Feds", "ecb": "ESBs"}
KIND_LABEL = {"rates": "rentemøte", "release": "tallslipp", "report": "rapport", "case": "research book", "company": "selskap"}


def bank_meetings(key: str) -> dict | None:
    fname = next((f for k, _, f in BANKS if k == key), None)
    if not fname:
        return None
    p = resources.files("osloquant").joinpath(f"resources/{fname}")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or None
    except (OSError, FileNotFoundError):
        return None


def norges_bank_meetings() -> dict | None:
    return bank_meetings("norges_bank")


def all_meetings() -> dict[str, dict | None]:
    """Every bank's meeting file (None where it is missing). Norges Bank goes through norges_bank_meetings()."""
    return {k: norges_bank_meetings() if k == "norges_bank" else bank_meetings(k) for k, _, _ in BANKS}


def releases(doc: dict | None = None) -> list[dict]:
    """The release dates in the macro feed: SSB's calendar and the US releases from FRED's calendar."""
    doc = fd.read("macro") if doc is None else doc
    out = []
    for r in (doc or {}).get("ssb_releases") or []:
        out.append({"date": r["date"], "name": "Norge", "what": f'{r["what"]}' + (f' ({r["period"]})' if r.get("period") else ""),
                    "source": "SSBs publiseringskalender (CC BY 4.0)", "url": r.get("url")})
    for r in (doc or {}).get("releases") or []:
        out.append({"date": r["date"], "name": "USA", "what": r["what"], "source": "FRED-kalenderen (St. Louis Fed)"})
    return out


def refill_notes(today: pd.Timestamp, meetings: dict | None = None) -> list[str]:
    """One line per bank whose meeting file is missing or runs out within REFILL_DAYS."""
    out = []
    for key, name, fname in BANKS:
        doc = (meetings or all_meetings()).get(key)
        if not doc:
            out.append(f"{name}: kildefilen mangler (resources/{fname})")
            continue
        last = max((pd.Timestamp(d["date"]) for d in doc.get("dates") or []), default=None)
        if last is None or last < today + pd.Timedelta(days=REFILL_DAYS):
            out.append(f"{name}: siste møte i filen er {dato(last) if last is not None else 'ingen'} – fyll på fra {doc.get('source')}")
    return out


def events(cases, watch: list[dict] | None = None, today: pd.Timestamp | None = None, days: int = 120, macro: dict | None = None) -> list[dict]:
    """Every dated thing in the next ``days`` days, oldest first: research-book events, the issuers' financial
    calendars for research-book and watched companies, the rate meetings of Norges Bank, the Fed and the ECB, and the
    releases of SSB and of the US. Each has ``source``. ``macro``: the macro feed (read from the cache when None)."""
    today = (today or pd.Timestamp.now()).normalize()
    end = today + pd.Timedelta(days=days)
    names = {c.code: c.name for c in cases}
    book_codes = set(names)
    out = []
    for c in cases:
        for ev in c.events:
            d = pd.Timestamp(ev["date"])
            if today <= d <= end:
                out.append({"date": d, "code": c.code, "name": c.name, "what": ev["what"], "source": "research book", "kind": "case"})
    cal = fd.read(CAL_FEED) or {}
    for code, entry in (cal.get("companies") or {}).items():
        for ev in entry.get("events", []):
            d = pd.Timestamp(ev["date"])
            if today <= d <= end:
                what = ev["what"]
                dup = any(x["code"] == code and x["date"] == d and x["kind"] == "case" for x in out)
                out.append({"date": d, "code": code, "name": names.get(code, code), "what": what, "kind": "report" if re.search(r"(?i)report|rapport", what) else "company",
                            "source": f"finanskalender på NewsWeb ({dato(str(entry.get('published', ''))[:10])})", "url": entry.get("url"), "in_book": code in book_codes,
                            "duplicate_of_case_event": dup})
    meetings = all_meetings()
    for key, name, _ in BANKS:
        doc = meetings.get(key)
        for d in (doc or {}).get("dates", []):
            ts = pd.Timestamp(d["date"])
            if today <= ts <= end:
                out.append({"date": ts, "code": None, "name": name, "bank": key, "what": d.get("what", "rentebeslutning"), "kind": "rates",
                            "source": f"{OWNER[key]} møteplan (lest {dato(str(doc.get('read', '')))})", "url": doc.get("source")})
    for r in releases(macro):
        ts = pd.Timestamp(r["date"])
        if today <= ts <= end:
            out.append({"date": ts, "code": None, "name": r["name"], "what": r["what"], "kind": "release", "source": r["source"], "url": r.get("url")})
    return sorted(out, key=lambda e: (e["date"], e["kind"]))


def macro_week(evs: list[dict], today: pd.Timestamp, days: int = 7) -> list[dict]:
    """The rate meetings and releases of the next ``days`` days, for the front page."""
    return [e for e in evs if e["kind"] in ("rates", "release") and today <= e["date"] <= today + pd.Timedelta(days=days)]


def week_html(evs: list[dict], today: pd.Timestamp, static: bool = False) -> str:
    """«Makro de neste sju dagene» on the front page: rate meetings first on a day, then releases."""
    from osloquant.dashboard.render import E

    items = "".join(
        f'<li><b>{dato(e["date"], False, short_weekday=True)}</b> ({(e["date"] - today).days} d) '
        f'{E(e["name"])}: {E(e["what"])} <span class="src">({E(e["source"].split(" (")[0])})</span></li>' for e in evs)
    return ('<h2 id="makro-uke">Makro de neste sju dagene</h2><div class="card"><ul class="news">'
            + (items or '<li class="empty">ingen rentemøter eller tallslipp de neste sju dagene</li>') + '</ul>'
            '<div class="src">Rentemøter: Norges Banks, Feds og ESBs publiserte møteplaner. Tallslipp: SSBs publiseringskalender (KPI, AKU, BNP, '
            'detaljomsetning) og FRED-kalenderen (USA). '
            + ('Alt som kommer står på <a href="/makro#kalender">Makro</a>.' if not static else 'Alt som kommer står på makrosiden.') + '</div></div>')


def page_html(evs: list[dict], today: pd.Timestamp, cal_doc: dict | None, nb: dict | None, static: bool = False, meetings: dict | None = None) -> str:
    from osloquant.dashboard.render import E, link, page

    rows = []
    for e in evs:
        who = link(e["code"], e["name"], static) if e.get("code") else E(e["name"])
        label = "melding" if e["kind"] in ("report", "company") else "kilde"
        src = E(e["source"]) + (f' · <a href="{E(e["url"])}" target="_blank" rel="noopener">{label}</a>' if e.get("url") else "")
        flag = ' <span class="src">(står også i research book)</span>' if e.get("duplicate_of_case_event") else ""
        cls = {"rates": "info", "report": "warn-t", "case": "k"}.get(e["kind"], "")
        rows.append(f'<tr><td><b>{dato(e["date"], short_weekday=True)}</b></td><td>{(e["date"] - today).days} d</td><td class="{cls}">{E(KIND_LABEL.get(e["kind"], e["kind"]))}</td><td>{who}</td>'
                    f'<td style="white-space:normal">{E(e["what"])}{flag}</td><td class="src" style="white-space:normal">{src}</td></tr>')
    body = ('<h1>Kalender</h1><div class="sub">Rapportdatoer fra selskapenes egne finanskalendere på NewsWeb, datoene i research book, rentemøtene i '
            'Norges Bank, Fed og ESB, og tallslipp fra SSB og USA – de neste 120 dagene.</div>'
            '<div class="card"><table class="odds"><thead><tr><th>Dato</th><th>Om</th><th>Type</th><th>Hvem</th><th>Hva</th><th>Kilde</th></tr></thead>'
            f'<tbody>{"".join(rows) or "<tr><td colspan=6 class=empty>ingenting de neste 120 dagene</td></tr>"}</tbody></table></div>')
    comp = (cal_doc or {}).get("companies") or {}
    missing = [c for c, v in comp.items() if not v.get("events")]
    notes = [f'Finanskalendere hentet {E(stempel((cal_doc or {}).get("fetched_at")))} for {len(comp)} selskaper'
             + (f'; ingen kalendermelding funnet for {E(", ".join(missing))}' if missing else "") + "." if cal_doc else
             "Finanskalendere ikke hentet ennå (oq dashboard --refresh)."]
    meetings = dict(meetings) if meetings is not None else all_meetings()
    meetings["norges_bank"] = nb
    for key, name, fname in BANKS:
        doc = meetings.get(key)
        if doc:
            notes.append(f'{name}: {len(doc.get("dates", []))} møtedatoer fra {E(str(doc.get("source")))}, lest {E(dato(str(doc.get("read", ""))))}.')
        else:
            notes.append(f"{OWNER[key]} møtedatoer: ikke tilgjengelig – kildefilen mangler (resources/{fname}). Ingen datoer er gjettet.")
    refill = [x for x in refill_notes(today, meetings) if "mangler" not in x]
    if refill:
        notes.append('<span class="st-warn">Møteplanen må fylles på: ' + E("; ".join(refill)) + ".</span>")
    notes.append("Tallslipp: SSBs publiseringskalender (KPI, AKU, BNP, detaljomsetning; CC BY 4.0) og FRED-kalenderen (USA), hentet med makrofeeden.")
    notes.append("Ex-dividend-datoer er ikke med: NewsWeb melder dem først på selve dagen, og forhåndsmeldingene har ingen fast form.")
    return page("Kalender", "/calendar", body + '<div class="src">' + " ".join(notes) + '</div>', static=static)
