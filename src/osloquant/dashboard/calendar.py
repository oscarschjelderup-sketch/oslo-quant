"""The event calendar: report dates and meetings from the issuers' own financial-calendar announcements on NewsWeb,
the research book's events, and Norges Bank's rate decisions – one list with a source and a fetch time on every
date (DECISIONS D26).

NewsWeb issuers publish "Financial calendar" messages in a fixed form: "DD.MM.YYYY - Quarterly Report - Q3". The
fetcher takes the newest such message per followed company (one list request and one message request each) and
keeps the parsed dates in the private feed cache. Norges Bank's dates come from a resource file with the page they
were copied from and the day they were read; if the file is missing, the page says so instead of guessing.
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


def norges_bank_meetings() -> dict | None:
    p = resources.files("osloquant").joinpath("resources/norges_bank_meetings.yaml")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or None
    except (OSError, FileNotFoundError):
        return None


def events(cases, watch: list[dict] | None = None, today: pd.Timestamp | None = None, days: int = 120) -> list[dict]:
    """Every dated thing in the next ``days`` days, oldest first: research-book events, the issuers' financial
    calendars for research-book and watched companies, Norges Bank rate decisions. Each has ``source``."""
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
    nb = norges_bank_meetings()
    for d in (nb or {}).get("dates", []):
        ts = pd.Timestamp(d["date"])
        if today <= ts <= end:
            out.append({"date": ts, "code": None, "name": "Norges Bank", "what": d.get("what", "rate decision"), "kind": "rates",
                        "source": f"{nb.get('source', 'Norges Bank')} (read {nb.get('read', '?')})"})
    return sorted(out, key=lambda e: (e["date"], e["kind"]))


def page_html(evs: list[dict], today: pd.Timestamp, cal_doc: dict | None, nb: dict | None, static: bool = False) -> str:
    from osloquant.dashboard.render import E, link, page

    rows = []
    for e in evs:
        who = link(e["code"], e["name"], static) if e.get("code") else E(e["name"])
        src = E(e["source"]) + (f' · <a href="{E(e["url"])}" target="_blank" rel="noopener">melding</a>' if e.get("url") else "")
        flag = ' <span class="src">(also in the research book)</span>' if e.get("duplicate_of_case_event") else ""
        cls = {"rates": "info", "report": "warn-t", "case": "k"}.get(e["kind"], "")
        rows.append(f'<tr><td><b>{dato(e["date"], short_weekday=True)}</b></td><td>{(e["date"] - today).days} d</td><td class="{cls}">{E(e["kind"])}</td><td>{who}</td>'
                    f'<td style="white-space:normal">{E(e["what"])}{flag}</td><td class="src" style="white-space:normal">{src}</td></tr>')
    body = ('<h1>Kalender</h1><div class="sub">Rapportdatoer fra selskapenes egne finanskalendere på NewsWeb, datoene i research book, og Norges Banks '
            'rentebeslutninger – de neste 120 dagene.</div>'
            '<div class="card"><table class="odds"><thead><tr><th>Dato</th><th>Om</th><th>Type</th><th>Hvem</th><th>Hva</th><th>Kilde</th></tr></thead>'
            f'<tbody>{"".join(rows) or "<tr><td colspan=6 class=empty>nothing in the next 120 days</td></tr>"}</tbody></table></div>')
    comp = (cal_doc or {}).get("companies") or {}
    missing = [c for c, v in comp.items() if not v.get("events")]
    notes = [f'Finanskalendere hentet {E(stempel((cal_doc or {}).get("fetched_at")))} for {len(comp)} selskaper'
             + (f'; ingen kalendermelding funnet for {E(", ".join(missing))}' if missing else "") + "." if cal_doc else
             "Finanskalendere ikke hentet ennå (oq dashboard --refresh)."]
    if nb:
        notes.append(f'Norges Bank: {len(nb.get("dates", []))} datoer fra {E(str(nb.get("source")))}, lest {E(str(nb.get("read")))}.')
    else:
        notes.append("Norges Banks møtedatoer: ikke tilgjengelig – kildefilen mangler (resources/norges_bank_meetings.yaml). Ingen datoer er gjettet.")
    notes.append("Ex-dividend-datoer er ikke med: NewsWeb melder dem først på selve dagen, og forhåndsmeldingene har ingen fast form.")
    return page("Kalender", "/calendar", body + '<div class="src">' + " ".join(notes) + '</div>', static=static)
