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
from osloquant.dashboard.dates import dato

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
        for ev in c.events if (v or c.kill) else []:
            d = pd.Timestamp(ev["date"])
            if today - pd.Timedelta(days=EVENT_LOOKBACK) <= d <= today and not _since_view(c, d):
                items.append(Item(c.code, "kill-check", f"{c.name}: {ev['what'][:70]}",
                                  f"{dato(d, False)} – check the {len(c.kill)} kill criteria and log each (breached or intact, and what you did).", 0))
        if lp is None or not v:
            continue
        px, day = lp
        tp, bear, bull, p0 = v.get("target"), v.get("bear"), v.get("bull"), v.get("price")
        if tp and ((tp >= (p0 or 0) and px >= tp) or (tp < (p0 or 0) and px <= tp)):
            items.append(Item(c.code, "re-rate", f"{c.name} reached the target {tp:g}", f"price {px:.2f} ({dato(day, False)}); set a new view or close the case.", 1))
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
                              "; ".join(f"{k['criterion']}: {k['status']}" for k in hot) + " – read the analysis on the stock page and log a kill check.",
                              0 if trig else 1))
    return items


PRE_REPORT_DAYS = 14          # a report this close asks for a view logged before it
PRE_REPORT_FRESH = 30         # a view dated within this many days before the report counts as "before the report"
_REPORT_WORDS = ("report", "rapport", "results", "resultat", "q1", "q2", "q3", "q4", "quarter", "kvartal", "interim", "half-year", "halvår")


def pre_report_items(cases: list[bk.Case], today: pd.Timestamp, days: int = PRE_REPORT_DAYS) -> list[Item]:
    """A research-book report date within ``days`` days and no judgement dated in the ``PRE_REPORT_FRESH`` days before
    it: the view must be on record before the numbers come, or the calibration measures hindsight (D22)."""
    items = []
    for c in cases:
        if not c.view and c.claude_view:
            continue                     # a company only Claude has a view on: listed on the coverage page, not nagged here
        for ev in c.events:
            d = pd.Timestamp(ev["date"])
            if not (today <= d <= today + pd.Timedelta(days=days)) or not any(w in str(ev["what"]).lower() for w in _REPORT_WORDS):
                continue
            views = [r["date"] for r in c.history if r["kind"] == "judgement"]
            fresh = [v for v in views if pd.Timestamp(v) >= d - pd.Timedelta(days=PRE_REPORT_FRESH)]
            if fresh:
                continue
            last = max(views) if views else None
            left = (d - today).days
            items.append(Item(c.code, "pre-report", f"{c.name}: log your view before the report on {dato(d, False)} ({left} d)",
                              (f"The last view is from {last}; " if last else "No view is logged; ")
                              + f"a view dated after the report would be scored with hindsight. {ev['what'][:70]}", 0 if left <= 3 else 1))
    return items


POST_REPORT_DAYS = 45         # a report this far back still asks for a view dated after it


def last_report(c: bk.Case, today: pd.Timestamp, days: int = POST_REPORT_DAYS) -> tuple[pd.Timestamp, str] | None:
    """The newest report date that has passed within ``days`` days: a report the reader summarised, a report the
    after-report loop downloaded (D39), or a research-book event with report words. (date, what) or None."""
    from osloquant.dashboard import afterreport as ar
    from osloquant.dashboard import reports as rp

    found = []
    s = rp.latest(c.code)
    if s:
        found.append((pd.Timestamp(s["published"][:10]), f"Q{s['quarter']} {s['year']} report"))
    found += [(d, what) for d, what, _ in ar._downloaded(c.code)]
    for ev in c.events:
        d = pd.Timestamp(ev["date"])
        if d <= today and any(w in str(ev.get("what", "")).lower() for w in _REPORT_WORDS):
            found.append((d, ev["what"]))
    found = [(d, w) for d, w in found if (today - d).days <= days]
    return max(found, key=lambda x: x[0]) if found else None


def post_report_items(cases: list[bk.Case], today: pd.Timestamp, days: int = POST_REPORT_DAYS) -> list[Item]:
    """A report has passed and no judgement is dated on or after it: the view on record predates the numbers, so it
    is not the view the calibration should score from here. Asks for a re-assessment (D29)."""
    items = []
    for c in cases:
        lr = last_report(c, today, days)
        if not lr or not c.view:
            continue
        d, what = lr
        if any(r["kind"] in ("judgement", "update") and pd.Timestamp(r["date"][:10]) >= d for r in c.history):
            continue                     # a view, or an update of its probabilities (D48), dated after the report
        items.append(Item(c.code, "post-report", f"{c.name}: the view of {c.view.get('date')} predates the report of {dato(d, False)}",
                          f"{what[:80]} is out ({(today - d).days} d ago) and the view has not been re-logged since. Re-assess and log the view "
                          "(even if unchanged) – until then the research book carries a pre-report view.", 1))
    return items


def report_tp_items(cases: list[bk.Case], today: pd.Timestamp) -> list[Item]:
    """A research report (reports_pdf) newer than the view whose target or rating differs from it, with no judgement
    logged since the report: the report does not change the research book – a decision does."""
    from osloquant.dashboard import reportpdf as rpdf

    items = []
    for c in cases:
        if not c.view:
            continue
        m = rpdf.tp_mismatch(rpdf.latest(c.code), c.view, c.history)
        if m:
            items.append(Item(c.code, "report-tp", f"{c.name}: rapporten av {m['report_date']} sier {m['report_tp']:g} ({m['report_rating'] or '–'}), "
                              f"vurderingen din {m['view_tp']:g} ({m['view_rating'] or '–'}, {m['view_date']})",
                              f"Avvik {m['diff'] * 100:+.0f} %. Les rapporten ({m['file']}) og logg en ny vurdering – også om du holder på {m['view_tp']:g}; "
                              "skriv i begrunnelsen hvorfor du avviker fra eller følger rapporten.", 1))
    return items


FORECAST_DAYS = 14            # a report this near asks for the quarterly forecast (D52)
REVIEW_WINDOW = 21            # the last three weeks of a quarter ask for the error review (D49)


def habit_items(cases: list[bk.Case], today: pd.Timestamp, rows: list[dict] | None = None, cal_doc: dict | None = None) -> list[Item]:
    """The loops of 5 Nov 2026 as decision items, so they are done rather than built: the probability update after a
    report (D48), the quarterly forecast before one (D52), the head of analysis's undecided proposals (D50) and, in
    the last three weeks of a quarter, the error review of views older than 90 days (D49)."""
    from osloquant.dashboard import chief as ch
    from osloquant.dashboard import forecasts as fc
    from osloquant.dashboard import review as rv
    from osloquant.dashboard import updates as up

    rows = jg.read_log() if rows is None else rows
    names = {c.code: c.name for c in cases}
    items = []
    for p in up.pending(rows, cases, today, cal_doc):
        t = p["trigger"]
        items.append(Item(p["code"], "update", f"{names.get(p['code'], p['code'])}: har sannsynligheten endret seg etter {t['what'][:50]} ({t['date']})?",
                          f"Vurderingen #{p['view_seq']} er eldre enn rapporten. Svar på aksjesiden – også «uendret» med én setning (Tetlock: små, hyppige oppdateringer)."
                          + (f" {p['days']} dager uten svar teller som «ikke oppdatert»." if p["overdue"] else ""), 0 if p["overdue"] else 1))
    own = {c.code for c in cases if c.view}
    for code in sorted(own):
        r = fc.upcoming(code, cases, today)
        if not r or (pd.Timestamp(r["date"]) - today).days > FORECAST_DAYS:
            continue
        if any(f["report"]["date"] == r["date"] for f in fc.forecasts(rows, code)):
            continue
        left = (pd.Timestamp(r["date"]) - today).days
        items.append(Item(code, "forecast", f"{names.get(code, code)}: logg kvartalsprognosen før rapporten {r['date']} ({left} d)",
                          "Et 80 %-intervall for omsetning eller EBITDA – rapportleseren gir fasiten, og kalibreringen får et svar på uker i stedet for et år.", 1))
    from osloquant.dashboard import variant as vrt

    for d in vrt.due(cases, today):
        items.append(Item(d["code"], "catalyst", f"{d['name']}: skjedde katalysatoren innen {d['by']}?",
                          f"«{d['catalyst'][:90]}» ({d['days']} d siden). Logg en kill-sjekk eller en ny vurdering – Klarman: datoen er en del av sikkerhetsmarginen.", 1))
    runs = ch.latest_runs(1)
    if runs:
        live = ch.proposals(runs[-1]["results"], ch.read_decisions())["live"]
        if live:
            items.append(Item("", "chief", f"Analysesjefen: {len(live)} forslag venter på godkjenning eller avvisning",
                              f"Øverst: {live[0]['text'][:110]} – kjøringen av {runs[-1]['date']}.", 2))
    q_end = (today + pd.offsets.QuarterEnd(0)).normalize()
    if (q_end - today).days <= REVIEW_WINDOW:
        done = {r["ref_seq"] for r in rv.reviews(rows, rv.quarter(today))}
        due = [j for j in jg.judgements(rows, jg.DEFAULT_ANALYST) if (today - pd.Timestamp(j["date"])).days >= 90 and j["seq"] not in done]
        if due:
            items.append(Item("", "review", f"Feilgjennomgang {rv.quarter(today)}: {len(due)} vurderinger venter",
                              f"Største avvik først, de samme spørsmålene hver gang (Dalio, Duke, Klein). Kvartalet slutter {dato(q_end, False)}.", 1))
    return items


def merge_items(*groups: list[Item]) -> list[Item]:
    """One list, most urgent first; a code with a post-report item drops its 'moved 10 %' re-assess item, since the
    post-report item already asks for the same thing with the better reason, and a code with an update question (D48)
    drops its post-report item – answering the update is the lighter way to put the view on record after the report."""
    items = [i for g in groups for i in g]
    post = {i.code for i in items if i.kind == "post-report"}
    upd = {i.code for i in items if i.kind == "update"}
    items = [i for i in items if not (i.kind == "re-assess" and i.code in post) and not (i.kind == "post-report" and i.code in upd)]
    return sorted(items, key=lambda i: (i.urgency, i.code))


def upcoming(cases: list[bk.Case], today: pd.Timestamp, days: int = UPCOMING_DAYS) -> list[dict]:
    """The next ``days`` days: the research book's own events (with the kill criteria to check when close), then the
    issuers' financial calendars and Norges Bank from the calendar feed, without repeating a date the book has."""
    from osloquant.dashboard import calendar as cal

    out = []
    for c in cases:
        for ev in c.events:
            d = pd.Timestamp(ev["date"])
            if today <= d <= today + pd.Timedelta(days=days):
                out.append({"code": c.code, "name": c.name, "date": d, "what": ev["what"],
                            "kill": c.kill if (d - today).days <= KILL_SOON_DAYS else [], "source": None})
    for e in cal.events(cases, today=today, days=days):
        if e["kind"] == "case" or e.get("duplicate_of_case_event"):
            continue
        out.append({"code": e.get("code"), "name": e["name"], "date": e["date"], "what": e["what"], "kill": [], "source": e["source"].split(" (")[0]})
    return sorted(out, key=lambda e: e["date"])


def target_moves(snap: mk.Snapshot, cases: list[bk.Case], today: pd.Timestamp | None = None) -> list[dict]:
    """Every case's price against its view: since the view, distance to target, bear and bull, and the date of a
    report that has passed since the view was logged (``stale_report``), if any."""
    out = []
    for c in cases:
        lp, v = mk.last_price(snap, c.code), c.view
        if not lp or not v or not v.get("price"):
            continue
        px, day = lp
        lr = last_report(c, today if today is not None else pd.Timestamp(day).normalize())
        stale = lr[0] if lr and v.get("date") and pd.Timestamp(str(v["date"])[:10]) < lr[0] else None
        out.append({"code": c.code, "name": c.name, "price": px, "date": day, "rating": v.get("rating"), "target": v.get("target"),
                    "since": px / v["price"] - 1, "to_tp": v["target"] / px - 1 if v.get("target") else None,
                    "to_bear": v["bear"] / px - 1 if v.get("bear") else None, "to_bull": v["bull"] / px - 1 if v.get("bull") else None,
                    "view_date": v.get("date"), "view_source": c.view_source, "stale_report": stale})
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
