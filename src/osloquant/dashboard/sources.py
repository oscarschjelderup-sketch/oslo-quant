"""Every data source the dashboard reads, in one place (improvement pass 10 Nov 2026, D60): what it is, how fresh it
should be, which numbers lean on it, and what happened the last times it was fetched.

Two things were missing before. A failed fetch left no trace outside a log file, because a failed feed keeps its old
cache and the cache's own "fetched" time. And a table's age was the age of its newest row, so one fresh stock hid
sixty-three stale ones. Here every attempt is written to ``feeds/_runs.json`` (the last 60 per source), the store's
tables are measured per stock, and a source is one of four things: ok, stale («utdatert»), failed («feilet») or never
fetched («aldri hentet»). The front page and the data-health page read the same list.

A daily source is stale when it has not been fetched since the last session's close. Oslo Børs' holidays are known
here, so the morning after 17 May is not a false alarm.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from osloquant.dashboard import feeds as fd
from osloquant.dashboard.dates import dato, dato_tid

RUNS_FILE = "_runs.json"
KEEP = 60                    # attempts kept per source
CLOSE_HOUR = 16.5            # Oslo Børs closes 16:25; a fetch after 16:30 has the day's close
DUE_HOUR = 18.5              # the evening job starts 17:45 and takes ten minutes: from 18:30 today's close is expected
WEEKLY_DAYS = 8


@dataclass(frozen=True)
class Source:
    key: str
    name: str                # what a person calls it
    origin: str              # where it comes from
    kind: str                # "table" (the store) or "feed" (a cache file)
    cadence: str             # "daily" or "weekly"
    affects: str             # the numbers that lean on it
    ref: str                 # the schema name or the feed name


SOURCES: tuple[Source, ...] = (
    Source("prices_adj", "Justerte kurser", "Yahoo Finance", "table", "daily", "alle kurser, avkastning, signaler, odds og kursgrafen", "Stock1dAdjKdata"),
    Source("prices_raw", "Noterte kurser", "Yahoo Finance", "table", "daily", "børsverdi, P/E, direkteavkastning og kalibreringens «nå»-kurs", "Stock1dKdata"),
    Source("finance", "Regnskap", "Yahoo Finance", "table", "weekly", "P/E, EV/EBIT, marginer, lett case og «Prisen krever»", "IncomeStatement"),
    Source("index", "Indekser (OSEBX)", "Yahoo Finance", "table", "daily", "sammenligning mot indeksen, meravkastning og kalibrering", "Index1dKdata"),
    Source("announcements", "Børsmeldinger", "Oslo Børs NewsWeb", "feed", "daily", "meldingslisten på «I dag» og aksjesiden, rapportvarslene", "announcements"),
    Source("insiders", "Innsidehandler", "Oslo Børs NewsWeb", "feed", "daily", "Eiere-fanen, innsidelisten på «I dag» og markørene i kursgrafen", "insiders"),
    Source("calendar", "Finanskalender", "Oslo Børs NewsWeb", "feed", "weekly", "Kalender, «Neste rapport» og påminnelsene før en rapport", "calendar"),
    Source("rates", "Styringsrente og 10 års stat", "Norges Bank", "feed", "daily", "sektordriverne for finans, eiendom og teknologi", "rates"),
    Source("fx", "USD/NOK og EUR/NOK", "Norges Bank", "feed", "daily", "sektordriverne for energi, shipping, sjømat og industri", "fx"),
    Source("brent", "Brent", "Yahoo Finance", "feed", "daily", "sektordriveren for energi", "brent"),
    Source("salmon", "Laksepris", "SSB tabell 03024", "feed", "weekly", "sektordriveren for sjømat", "salmon"),
    Source("shorts", "Shortposisjoner", "Finanstilsynet", "feed", "daily", "Eiere-fanen og shortendringene på «I dag»", "shorts"),
    Source("news", "Nyhetsoverskrifter", "RSS: E24, DN, Finansavisen, NRK", "feed", "daily", "nyhetslisten på aksjesiden", "news"),
    Source("macro", "Makroserier", "Norges Bank, Yahoo Finance, SSB, hvakosterstrommen.no", "feed", "daily",
           "makrostripen, makrosiden og følsomheten per aksje", "macro"),
    Source("consensus", "Konsensus før rapport", "MFN (Modular Finance)", "event", "event", "konsensus-kolonnen i rapportanalysen (bare der den er registrert)", "consensus"),
)
BY_KEY = {s.key: s for s in SOURCES}
FEED_KEY = {s.ref: s.key for s in SOURCES if s.kind == "feed"}
TABLE_KEY = {"Stock1dAdjKdata": "prices_adj", "Stock1dKdata": "prices_raw", "Index1dKdata": "index", "IncomeStatement": "finance",
             "BalanceSheet": "finance", "CashFlowStatement": "finance", "FinanceFactor": "finance"}
STATE_NO = {"ok": "ok", "partial": "delvis", "stale": "utdatert", "failed": "feilet", "never": "aldri hentet"}
EXPECTED_NO = {"daily": "hver børsdag etter stengetid", "weekly": "minst én gang i uken", "event": "når en ny rapport leses"}


# ------------------------------------------------------------------------------------------------ sessions and holidays
def _easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    j, k = divmod(c, 4)
    m = (a + 11 * h) // 319
    r = (2 * e + 2 * j - k - h + m + 32) % 7
    n = (h - m + r + 90) // 25
    return date(year, n, (h - m + r + n + 19) % 32)


def holidays(year: int) -> set[date]:
    """The weekdays Oslo Børs is closed: the public holidays plus Christmas Eve and New Year's Eve."""
    e = _easter(year)
    return {date(year, 1, 1), e - timedelta(days=3), e - timedelta(days=2), e + timedelta(days=1), date(year, 5, 1), date(year, 5, 17),
            e + timedelta(days=39), e + timedelta(days=50), date(year, 12, 24), date(year, 12, 25), date(year, 12, 26), date(year, 12, 31)}


def is_session(day: pd.Timestamp) -> bool:
    return day.dayofweek < 5 and day.date() not in holidays(day.year)


def expected_session(now: pd.Timestamp) -> pd.Timestamp:
    """The newest session whose close should be in the store at ``now`` (Oslo time, naive)."""
    day = now.normalize()
    if (now - day) < pd.Timedelta(hours=DUE_HOUR):
        day -= pd.Timedelta(days=1)
    while not is_session(day):
        day -= pd.Timedelta(days=1)
    return day


def oslo_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Europe/Oslo").tz_localize(None)


def _oslo(iso: str | None) -> pd.Timestamp | None:
    """A stored UTC stamp («2026-11-09T21:50:59Z») as naive Oslo time."""
    if not iso:
        return None
    try:
        return pd.Timestamp(iso).tz_convert("Europe/Oslo").tz_localize(None) if pd.Timestamp(iso).tzinfo else pd.Timestamp(iso)
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------------------------------------ the run log
def _runs_path():
    return fd.cache_dir() / RUNS_FILE


def runs() -> dict:
    try:
        return json.loads(_runs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record_run(key: str, ok: bool, error: str | None = None, seconds: float | None = None, n: int | None = None, note: str | None = None,
               now: datetime | None = None) -> None:
    """One attempt at a source: appended to the run log. Never raises – a log that cannot be written must not stop a fetch."""
    try:
        doc = runs()
        entry = doc.setdefault(key, {"runs": []})
        t = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
        run = {"t": t, "ok": bool(ok)}
        if error:
            run["error"] = str(error)[:300]
        if seconds is not None:
            run["s"] = round(float(seconds), 1)
        if n is not None:
            run["n"] = int(n)
        if note:
            run["note"] = str(note)[:300]
        entry["runs"] = (entry.get("runs") or [])[-(KEEP - 1):] + [run]
        entry["last_attempt"] = t
        if ok:
            entry["last_ok"] = t
            entry.pop("last_error", None)
        else:
            entry["last_error"] = run.get("error") or "ukjent feil"
        _runs_path().write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001, S110
        pass


def timed(key: str, fn, count=None):
    """Run ``fn`` as one attempt at ``key``: its time and outcome go in the run log, and the exception is raised again."""
    t0 = time.monotonic()
    try:
        out = fn()
    except Exception as e:
        record_run(key, False, f"{type(e).__name__}: {e}", time.monotonic() - t0)
        raise
    note, n = None, None
    if isinstance(out, dict):
        note = "; ".join(out["errors"]) if out.get("errors") else None
        n = len(out["items"]) if isinstance(out.get("items"), list | dict) else None
    record_run(key, True, None, time.monotonic() - t0, count(out) if count else n, note=("delvis: " + note) if note else None)
    return out


# ------------------------------------------------------------------------------------------------ the store, per stock
_table_cache: dict[str, tuple[float, dict]] = {}
TABLE_TTL = 60.0


def table_last(schema_name: str) -> dict[str, pd.Timestamp]:
    """The newest row's date per code in a store table. Cached for a minute: the front page asks on every load.
    For the statements the date is the period (``report_date``): their ``timestamp`` is the period plus an assumed
    publication lag, which lies in the future for the newest quarter."""
    hit = _table_cache.get(schema_name)
    if hit and time.monotonic() - hit[0] < TABLE_TTL:
        return hit[1]
    from sqlalchemy import func, select

    import osloquant.domain as dm
    from osloquant.contract.api import get_session

    schema = getattr(dm, schema_name)
    table = schema.__table__
    try:
        with get_session(schema.default_provider(), data_schema=schema) as session:
            col = table.c.report_date if "report_date" in table.c else table.c.timestamp
            rows = session.execute(select(table.c.code, func.max(col)).group_by(table.c.code)).all()
        out = {code: pd.Timestamp(last) for code, last in rows if code and last is not None}
    except Exception:  # noqa: BLE001 – an empty or missing table is an answer too
        out = {}
    _table_cache[schema_name] = (time.monotonic(), out)
    return out


def clear_cache() -> None:
    _table_cache.clear()


def _table_status(src: Source, now: pd.Timestamp, run: dict) -> dict:
    last = table_last(src.ref)
    if not last:
        return {"state": "never", "detail": "tabellen er tom", "data_to": None}
    newest = max(last.values())
    expected = expected_session(now)
    if src.key == "prices_raw":
        adj = table_last("Stock1dAdjKdata")
        behind = sorted(c for c, d in last.items() if c in adj and d < adj[c]) + sorted(c for c in adj if c not in last)
        if behind:
            oldest = min((last[c] for c in behind if c in last), default=None)
            n = len(set(last) | set(adj))
            return {"state": "stale", "data_to": newest, "behind": behind,
                    "detail": f"{len(behind)} av {n} aksjer ligger etter de justerte kursene" + (f" – eldste slutter {dato(oldest)}" if oldest is not None else "")
                              + ". Kjør oq record --raw."}
        return {"state": "ok" if newest >= expected else "stale", "data_to": newest, "detail": f"{len(last)} aksjer til {dato(newest)}"
                + ("" if newest >= expected else f" – siste børsdag var {dato(expected)}")}
    if src.key == "finance":
        behind = sorted(c for c, d in last.items() if d < newest)
        ok_at = _oslo(run.get("last_ok"))
        detail = f"{len(last)} selskaper, nyeste periode slutter {dato(newest)}"
        if behind:
            detail += f"; {len(behind)} har ikke den perioden ennå ({', '.join(behind[:6])}{' …' if len(behind) > 6 else ''})"
        if ok_at is None:
            return {"state": "never" if not run else "failed", "data_to": newest, "behind": behind,
                    "detail": detail + ". Ingen henting er registrert – kjør oq record --finance (ukeoppgaven gjør det fra nå)."}
        fresh = now - ok_at <= pd.Timedelta(days=WEEKLY_DAYS)
        return {"state": "ok" if fresh else "stale", "data_to": newest, "behind": behind,
                "detail": detail + ("" if fresh else f". Ikke hentet siden {dato_tid(ok_at, True)} – kjør oq record --finance.")}
    behind = sorted(c for c, d in last.items() if d < newest)
    state = "ok" if newest >= expected else "stale"
    detail = f"{len(last)} {'aksjer' if src.key == 'prices_adj' else 'serier'} til {dato(newest)}"
    if newest < expected:
        detail += f" – siste børsdag var {dato(expected)}. Kjør oq record."
    elif behind and src.key == "prices_adj":
        state = "partial"
        detail += f"; {len(behind)} uten siste sluttkurs ({', '.join(behind[:6])})"
    return {"state": state, "data_to": newest, "behind": behind, "detail": detail}


def _feed_status(src: Source, now: pd.Timestamp, run: dict) -> dict:
    doc = fd.read(src.ref)
    ok_at = _oslo(run.get("last_ok") or (doc or {}).get("fetched_at"))
    if doc is None or ok_at is None:
        return {"state": "never" if not run.get("last_error") else "failed", "detail": "ingen data i cachen – kjør oq dashboard --refresh", "data_to": None}
    if src.cadence == "daily":
        due = expected_session(now) + pd.Timedelta(hours=CLOSE_HOUR)
        fresh = ok_at >= due
        late = f"ikke hentet siden {dato_tid(ok_at, True)} – skulle vært hentet etter stengetid {dato(due)}"
    else:
        fresh = now - ok_at <= pd.Timedelta(days=WEEKLY_DAYS)
        late = f"ikke hentet siden {dato_tid(ok_at, True)} – eldre enn {WEEKLY_DAYS} dager"
    last_run = (run.get("runs") or [{}])[-1]
    note = last_run.get("note") if last_run.get("ok") else None
    items = doc.get("items")
    n = len(items) if isinstance(items, list | dict) else None
    day = str(doc.get("date") or "")
    detail = (late if not fresh else (f"{n} rader" if n is not None else (("uke" + day[4:] if day.startswith("week ") else f"siste verdi {dato(day)}") if day else "")))
    state = "ok" if fresh else "stale"
    if fresh and note:
        state, detail = "partial", note
    return {"state": state, "detail": detail, "data_to": ok_at}


def status(now: pd.Timestamp | None = None) -> list[dict]:
    """One dict per source: state, when it last worked, when it was last tried, the error, the failure count, the
    numbers it affects."""
    now = now if now is not None else oslo_now()
    log = runs()
    out = []
    for src in SOURCES:
        run = log.get(src.key) or {}
        if src.kind == "event":         # fetched only when a report is read: never stale, but a failed attempt shows
            last = (run.get("runs") or [{}])[-1]
            st = {"state": "ok", "detail": last.get("note") or ("ingen forsøk registrert" if not run else "")}
        else:
            st = _table_status(src, now, run) if src.kind == "table" else _feed_status(src, now, run)
        attempt, ok_at = _oslo(run.get("last_attempt")), _oslo(run.get("last_ok"))
        if src.kind == "feed" and ok_at is None:
            ok_at = _oslo((fd.read(src.ref) or {}).get("fetched_at"))
        all_runs = run.get("runs") or []
        failing = bool(all_runs) and not all_runs[-1].get("ok")          # the newest attempt failed: the data shown is older
        state = st["state"]
        if failing and (state != "never" or src.kind == "event"):
            state = "failed"
        recent = (run.get("runs") or [])[-30:]
        out.append({"key": src.key, "name": src.name, "origin": src.origin, "kind": src.kind, "cadence": src.cadence, "expected": EXPECTED_NO[src.cadence],
                    "affects": src.affects, "state": state, "state_no": STATE_NO[state], "detail": st.get("detail") or "", "behind": st.get("behind") or [],
                    "last_ok": ok_at, "last_attempt": attempt, "error": run.get("last_error") if failing else None,
                    "runs": len(recent), "fails": sum(not r.get("ok") for r in recent)})
    return out


# ------------------------------------------------------------------------------------------------ one source against another
FX_TOLERANCE = 0.015          # Norges Bank fixes at 14:15 CET, Yahoo closes later: a normal day is well inside 1.5 %
PRICE_TOLERANCE = 0.005       # the adjusted series ends on the quoted close, so the last two must agree


def cross_checks(fx_table: dict[str, pd.Series] | None = None, adj_last: dict | None = None, raw_last: dict | None = None) -> list[dict]:
    """Where two sources give the same number, compare them (funn D12). Each row: what, the two values with their
    sources, the difference, the limit, and whether it is over. A check that cannot be made says why."""
    out = []
    fx = fd.read("fx") or {}
    if fx_table is None:
        from osloquant.recorders.yahoo.cleaning import fx_rates

        fx_table = fx_rates()
    for ccy, key in (("USD", "USDNOK"), ("EUR", "EURNOK")):
        nb, day = fx.get(key), fx.get("date")
        series = fx_table.get(ccy)
        row = {"what": f"{ccy}/NOK", "a_source": "Norges Bank", "b_source": "Yahoo Finance", "limit": FX_TOLERANCE, "a": nb, "b": None, "diff": None, "date": day, "over": False, "note": ""}
        if nb is None or not day:
            row["note"] = "Norges Bank-kursen er ikke hentet"
        elif series is None or pd.Timestamp(day) not in series.index:
            row["note"] = f"lageret har ingen Yahoo-kurs for {dato(day)}"
        else:
            row["b"] = float(series.loc[pd.Timestamp(day)])
            row["diff"] = row["b"] / float(nb) - 1
            row["over"] = abs(row["diff"]) > FX_TOLERANCE
        out.append(row)
    if adj_last is None or raw_last is None:
        adj_last, raw_last = _last_closes("Stock1dAdjKdata"), _last_closes("Stock1dKdata")
    both = [(c, adj_last[c], raw_last[c]) for c in adj_last if c in raw_last and adj_last[c][0] == raw_last[c][0] and raw_last[c][1]]
    off = sorted(((c, a[1] / r[1] - 1) for c, a, r in both if abs(a[1] / r[1] - 1) > PRICE_TOLERANCE), key=lambda x: -abs(x[1]))
    out.append({"what": "Siste sluttkurs, justert mot notert", "a_source": "justert tabell", "b_source": "notert tabell", "limit": PRICE_TOLERANCE, "a": None, "b": None,
                "diff": off[0][1] if off else (0.0 if both else None), "date": None, "over": bool(off),
                "note": (f"{len(off)} av {len(both)} aksjer avviker: " + ", ".join(f"{c} {d * 100:+.1f} %" for c, d in off[:6])) if off
                        else (f"{len(both)} aksjer med samme siste dato stemmer" if both else "ingen aksjer har samme siste dato i begge tabeller – de noterte kursene ligger etter")})
    return out


def _last_closes(schema_name: str) -> dict[str, tuple[pd.Timestamp, float]]:
    """code -> (date, close) of the newest row in a price table."""
    import osloquant.domain as dm
    from osloquant.contract.api import get_data

    try:
        df = get_data(getattr(dm, schema_name), columns=["code", "timestamp", "close"], start_timestamp=pd.Timestamp.now().normalize() - pd.Timedelta(days=45))
    except Exception:  # noqa: BLE001
        return {}
    if df is None or df.empty:
        return {}
    last = df.dropna(subset=["close"]).sort_values("timestamp").groupby("code").tail(1)
    return {r.code: (pd.Timestamp(r.timestamp), float(r.close)) for r in last.itertuples()}


def cross_html(rows: list[dict]) -> str:
    from osloquant.dashboard.render import E

    def num(x, d=3):
        return "–" if x is None else f"{x:.{d}f}"

    def diff(r):
        return "–" if r["diff"] is None else f'{r["diff"] * 100:+.2f} %'

    body = "".join(
        f'<tr><td class="l">{E(r["what"])}' + (f' <span class="src">{dato(r["date"])}</span>' if r["date"] else "") + '</td>'
        f'<td>{num(r["a"])} <span class="src">{E(r["a_source"])}</span></td><td>{num(r["b"])} <span class="src">{E(r["b_source"])}</span></td>'
        f'<td>{diff(r)}</td><td>{r["limit"] * 100:.1f} %</td>'
        f'<td class="l {"st-bad" if r["over"] else "st-ok"}">{"over grensen" if r["over"] else ("ikke sammenlignet" if r["diff"] is None else "innenfor")}</td>'
        f'<td class="l" style="white-space:normal">{E(r["note"])}</td></tr>' for r in rows)
    return ('<div class="card" id="kildekontroll"><h3>Kontroll mellom kilder</h3><table class="odds"><thead><tr><th class="l">Tall</th><th>Kilde A</th><th>Kilde B</th><th>Avvik</th>'
            f'<th>Grense</th><th class="l">Status</th><th class="l">Merknad</th></tr></thead><tbody>{body}</tbody></table>'
            '<div class="src">Der to kilder gir samme tall, sammenlignes de hver gang siden åpnes. Valuta: Norges Banks fixing 14:15 mot Yahoos sluttkurs samme dag, '
            'så et lite avvik er normalt. Kurs: den justerte serien ender på den noterte sluttkursen, så siste kurs skal være lik. Utbytter kontrolleres mot NewsWeb i kortet under.</div></div>')


def cross_lines(rows: list[dict]) -> list[str]:
    return [f"kildekontroll: {r['what']} avviker {r['diff'] * 100:+.2f} % mellom {r['a_source']} og {r['b_source']} (grense {r['limit'] * 100:.1f} %)"
            + (f" – {r['note']}" if r["note"] else "") for r in rows if r["over"]]


def not_ok(sts: list[dict]) -> list[dict]:
    """The sources the reader must know about before reading a number: stale, failed or never fetched."""
    return [s for s in sts if s["state"] in ("stale", "failed", "never")]


def problem_lines(sts: list[dict]) -> list[str]:
    out = []
    for s in sts:
        if s["state"] == "ok":
            continue
        why = s["error"] if s["state"] == "failed" and s["error"] else s["detail"]
        out.append(f"{s['name']} ({s['origin']}): {s['state_no']}" + (f" – {why}" if why else ""))
    return out


# ------------------------------------------------------------------------------------------------ html
def banner_html(sts: list[dict], static: bool = False) -> str:
    """The front page's warning: every source that is not ok, when it last worked, and the numbers it affects."""
    from osloquant.dashboard.render import E

    bad = not_ok(sts)
    if not bad:
        return ""
    items = []
    # feeds that are stale for the same reason – the evening job did not run – are one line, not nine
    late = [s for s in bad if s["kind"] == "feed" and s["state"] == "stale" and s["last_ok"] is not None]
    groups: dict[str, list[dict]] = {}
    for s in late:
        groups.setdefault(f"{s['last_ok']:%Y-%m-%d %H}", []).append(s)
    grouped = {id(s) for g in groups.values() if len(g) >= 3 for s in g}
    for g in groups.values():
        if len(g) < 3:
            continue
        oldest = min(s["last_ok"] for s in g)
        items.append(f'<li><b>{len(g)} kilder er ikke hentet siden {dato_tid(oldest, True)}</b> – kveldsoppgaven har ikke kjørt etter siste børsdag: '
                     f'{E(", ".join(s["name"] for s in g))}. <span class="src">Påvirker {E("; ".join(s["affects"] for s in g))}.</span></li>')
    for s in bad:
        if id(s) in grouped:
            continue
        when = f"sist hentet {dato_tid(s['last_ok'], True)}" if s["last_ok"] is not None else "aldri hentet"
        why = (f"siste forsøk {dato_tid(s['last_attempt'], True)} feilet: {s['error']}" if s["state"] == "failed" and s["error"] else s["detail"])
        items.append(f'<li><b>{E(s["name"])}</b> ({E(s["origin"])}) – {E(s["state_no"])}: {E(why.rstrip("."))}{"" if s["kind"] == "table" else " (" + E(when) + ")"}. '
                     f'<span class="src">Påvirker {E(s["affects"])}.</span></li>')
    more = "" if static else ' <a href="/health">Datahelse</a> viser alle kildene.'
    return (f'<div class="warn" id="kilder-varsel"><b>{len(bad)} {"datakilde er" if len(bad) == 1 else "datakilder er"} ikke oppdatert.</b> '
            f'Tallene under kan være eldre enn de ser ut.{more}<ul>{"".join(items)}</ul></div>')


def table_html(sts: list[dict]) -> str:
    """The data-health page's «Kilder» card."""
    from osloquant.dashboard.render import E

    def when(t):
        return dato_tid(t, True) if t is not None else "–"

    fails = lambda s: f'{s["fails"]} av {s["runs"]}' if s["runs"] else "–"  # noqa: E731
    rows = "".join(
        f'<tr><td class="l"><b>{E(s["name"])}</b><div class="src">{E(s["origin"])}</div></td>'
        f'<td class="l {"st-bad" if s["state"] in ("stale", "failed", "never") else ("st-warn" if s["state"] == "partial" else "st-ok")}">{E(s["state_no"])}</td>'
        f'<td class="l">{when(s["last_ok"])}</td><td class="l">{when(s["last_attempt"])}</td>'
        f'<td>{fails(s)}</td><td class="l">{E(s["expected"])}</td>'
        f'<td class="l" style="white-space:normal">{E(s["error"] or s["detail"])}</td><td class="l" style="white-space:normal">{E(s["affects"])}</td></tr>'
        for s in sts)
    return ('<div class="card" id="kilder"><h3>Kilder</h3><table class="odds"><thead><tr><th class="l">Kilde</th><th class="l">Status</th><th class="l">Sist hentet</th>'
            '<th class="l">Sist forsøkt</th><th title="Mislykkede forsøk av de siste 30">Feil</th><th class="l">Skal hentes</th><th class="l">Merknad</th>'
            f'<th class="l">Tall som påvirkes</th></tr></thead><tbody>{rows}</tbody></table>'
            '<div class="src">Kveldsoppgaven henter alt hver børsdag 17:45 og 21:45, regnskapet hver søndag. «Sist forsøkt» er nyere enn «Sist hentet» når siste forsøk feilet – '
            'da vises de gamle tallene fortsatt. En daglig kilde er utdatert når den ikke er hentet siden forrige børsdags stengetid (helligdager er regnet med). '
            'Tabellene i lageret måles per aksje, ikke på nyeste rad.</div></div>')
