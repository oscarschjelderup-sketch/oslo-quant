"""What is stale, missing or doubtful in the data the dashboard reads – one page, so no number is read without knowing
its age and its holes (DECISIONS D25).

Checked here: the price store (newest close per stock, gaps, long source gaps, split-sized moves), the adjustment
check against NewsWeb ex-dividend notices (cached by `oq data audit`, since it costs 64 NewsWeb calls), every feed
cache's age, the report reader per research-book company, the judgement log's chain, and the frozen test data.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard import feeds as fd
from osloquant.dashboard.dates import dato

FEED_MAX_AGE_DAYS = {"announcements": 3, "news": 3, "rates": 7, "fx": 7, "brent": 7, "salmon": 14, "shorts": 7, "insiders": 7, "calendar": 14}
GAP_RUN = 20                 # consecutive missing sessions that count as a source gap, not a thin day
BIG_MOVE = 0.25              # a daily move this large in the last 60 sessions is listed for a look


def price_health(closes: pd.DataFrame, asof: pd.Timestamp | None = None) -> dict:
    """Per stock: first and last close, whether it is stale, missing sessions in the last 250, long gaps, big moves."""
    asof = asof if asof is not None else (closes.index[-1] if len(closes.index) else pd.Timestamp.now().normalize())   # an empty store is not a crash
    rows = []
    for code in closes.columns:
        s = closes[code]
        first, last = s.first_valid_index(), s.last_valid_index()
        if first is None:
            rows.append({"code": code, "first": None, "last": None, "stale": True, "missing_250": None, "gaps": [], "big_moves": []})
            continue
        span = s.loc[first:last]
        na = span.isna()
        runs = []
        if na.any():
            start = None
            for d, v in na.items():
                if v and start is None:
                    start = d
                elif not v and start is not None:
                    n = int(na.loc[start:d].sum())
                    if n >= GAP_RUN:
                        runs.append((f"{start:%Y-%m-%d}", f"{d:%Y-%m-%d}", n))
                    start = None
        recent = s.iloc[-250:]
        chg = s.iloc[-61:].pct_change(fill_method=None)
        big = [(f"{d:%Y-%m-%d}", float(v)) for d, v in chg.items() if v == v and abs(v) >= BIG_MOVE]
        rows.append({"code": code, "first": f"{first:%Y-%m-%d}", "last": f"{last:%Y-%m-%d}", "stale": last < asof,
                     "missing_250": int(recent.loc[max(first, recent.index[0]):].isna().sum()), "gaps": runs, "big_moves": big})
    return {"asof": f"{asof:%Y-%m-%d}", "stocks": len(rows), "stale": [r["code"] for r in rows if r["stale"]],
            "with_gaps": [r["code"] for r in rows if r["gaps"]], "rows": rows}


def feed_health(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    out = []
    for name in fd.FEEDS:
        doc = fd.read(name)
        fetched = (doc or {}).get("fetched_at")
        age = None
        if fetched:
            age = (now - datetime.strptime(fetched, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)).total_seconds() / 86400
        limit = FEED_MAX_AGE_DAYS.get(name, 7)
        out.append({"feed": name, "fetched_at": fetched, "age_days": None if age is None else round(age, 1), "limit_days": limit,
                    "status": "never fetched" if age is None else ("stale" if age > limit else "ok"),
                    "items": len((doc or {}).get("items", [])) if isinstance((doc or {}).get("items"), list) else None,
                    "error": (doc or {}).get("error")})
    return out


def report_health(cases) -> list[dict]:
    from osloquant.dashboard import reports as rp

    specs = rp.specs()
    out = []
    for c in cases:
        spec = specs.get(c.code)
        s = rp.latest(c.code)
        wanted = set((spec or {}).get("key") or {}) | {f"pl_{k}" for k in ((spec or {}).get("pl") or {})}
        found = set((s or {}).get("figures") or {})
        out.append({"code": c.code, "spec": bool(spec), "latest": (s or {}).get("title"), "published": (s or {}).get("published", "")[:10] or None,
                    "missing": sorted(wanted - found) if s else sorted(wanted), "kill_rules": len((spec or {}).get("kill") or []),
                    "kill_texts": len(c.kill), "oscar_view": bool(c.view),
                    "status": "no spec" if not spec else ("no report read" if not s else ("rows missing" if wanted - found else "ok"))})
    return out


def log_health() -> dict:
    rows = jg.read_log() if jg.log_path().exists() else []
    check = jg.verify() if rows else None
    heads_ok = jg.heads_consistent(check) if check else []
    last = max((r.get("logged_at", "") for r in rows), default=None)
    return {"rows": len(rows), "chain_ok": None if check is None else check.ok, "problems": (check.problems if check else []) + list(heads_ok or []),
            "last_logged_at": last, "head": check.head[:16] if check else None}


def store_health() -> dict:
    from osloquant.contract.api import get_coverage
    from osloquant.domain import Index1dKdata, Stock1dAdjKdata, Stock1dKdata

    out = {}
    for name, schema in (("adjusted", Stock1dAdjKdata), ("raw", Stock1dKdata), ("index", Index1dKdata)):
        try:
            c = get_coverage(schema)
            out[name] = {"last": f"{c['last']:%Y-%m-%d}" if c.get("last") is not None else None, "entities": c.get("entities"), "rows": c.get("rows")}
        except Exception as e:  # noqa: BLE001 – an empty table must not take the page down
            out[name] = {"error": f"{type(e).__name__}: {e}"}
    return out


def testdata_health() -> dict:
    from osloquant.dashboard import testdata as tdata

    d = tdata.default_dir()
    return {"path": str(d), "present": d.exists(), "files": sorted(p.name for p in d.iterdir()) if d.exists() else [],
            "frozen_to": tdata.DEFAULT}


# ------------------------------------------------------------------------------------------------ the dividend audit (cached)
AUDIT_FILE = "data_health"
_AMT = re.compile(r"(?i)(?:ex[- ]?(?:dividend|utbytte)|eks[- ]?utbytte|exclusive (?:of )?dividend).{0,40}?(?:NOK|kr|USD|EUR)\s?(\d+(?:[.,]\d+)?)"
                  r"|(?:NOK|kr|USD|EUR)\s?(\d+(?:[.,]\d+)?).{0,40}?(?:ex[- ]?(?:dividend|utbytte)|eks[- ]?utbytte)")


def dividend_audit(closes_adj: pd.DataFrame, closes_raw: pd.DataFrame, codes: list[str] | None = None, since: str = "2010-01-01",
                   pause: float = 0.6, log=None) -> dict:
    """Every NewsWeb ex-dividend notice with an amount in its title, against Yahoo's adjustment factor (adjusted / raw
    close): a notice with no factor move within ±7 sessions is a dividend Yahoo did not adjust for. One POST per
    stock; run it with `oq data audit`, not on every refresh."""
    codes = codes or [c for c in closes_adj.columns if c in closes_raw.columns]
    fac = closes_adj / closes_raw.reindex(closes_adj.index)
    notices, failed = [], []
    for code in codes:
        try:
            doc = json.loads(fd._get(f"{fd.NEWSWEB}/list?issuer={code}&category=1101&fromDate={since}&toDate={datetime.now(UTC):%Y-%m-%d}", method="POST"))["data"]
        except Exception as e:  # noqa: BLE001
            failed.append(f"{code}: {type(e).__name__}")
            continue
        time.sleep(pause)
        j = fac[code].pct_change(fill_method=None) if code in fac else pd.Series(dtype=float)
        jumps = j[j.abs() > 0.0005].index
        seen = set()
        for m in doc.get("messages", []):
            mm = _AMT.search(m["title"])
            if not mm:
                continue
            d = pd.Timestamp(m["publishedTime"][:10])
            if d in seen:
                continue
            seen.add(d)
            amt = float((mm.group(1) or mm.group(2)).replace(",", "."))
            px = closes_raw[code].loc[:d].dropna() if code in closes_raw else pd.Series(dtype=float)
            px = float(px.iloc[-1]) if len(px) else float("nan")
            adjusted = bool(any(abs((d - x).days) <= 7 for x in jumps))
            notices.append({"code": code, "date": f"{d:%Y-%m-%d}", "amount": amt, "price": None if px != px else round(px, 2),
                            "yield": None if px != px or not px else round(amt / px, 4), "adjusted": adjusted, "url": f"https://newsweb.oslobors.no/message/{m['messageId']}"})
        if log:
            log(f"{code}: {len(seen)} ex-dividend notices")
    return {"since": since, "stocks": len(codes), "notices": len(notices), **summarise(notices), "failed": failed,
            "source": "Oslo Børs NewsWeb category 1101 vs Yahoo adjusted/raw close (private use)"}


SPLIT_SUSPECT = 0.15         # a "yield" this high means the amount predates a later split (Yahoo's raw table is split-adjusted backwards)


def summarise(notices: list[dict]) -> dict:
    """The missed notices and the missed yield per stock. A yield above 15 % is not a yield: the dividend was paid
    before a later split and Yahoo's raw close is already divided by the split, so it is listed but not summed."""
    missed = [n for n in notices if not n["adjusted"] and (n["yield"] or 0) > 0.003]
    for n in missed:
        n["yield_doubtful"] = bool((n["yield"] or 0) > SPLIT_SUSPECT)
    by_code: dict[str, float] = {}
    for n in missed:
        if not n["yield_doubtful"]:
            by_code[n["code"]] = round(by_code.get(n["code"], 0.0) + (n["yield"] or 0), 4)
    doubtful = sorted({n["code"] for n in missed if n["yield_doubtful"]})
    return {"missed": missed, "missed_yield_by_code": dict(sorted(by_code.items(), key=lambda kv: -kv[1])), "split_suspect_codes": doubtful}


def dividend_audit_cached() -> dict | None:
    return fd.read(AUDIT_FILE)


CASE_VIEW_AGE = 120        # days before a view is flagged as old on this page (the horizon rule lives in today.py)
CASE_PRICE_GAP = 0.10      # a light case built at a price this far from the store's last close is stale


def case_health(cases, closes: pd.DataFrame | None = None, today: pd.Timestamp | None = None) -> list[dict]:
    """Per research-book case with a view: the age of the view, the light case and the model file, and the places
    where two sources disagree – the report's target against the view, the light case's price against the store, a
    report dated after the view with no new judgement, a model file older than the newest report."""
    from osloquant.dashboard import lightcase as lcm
    from osloquant.dashboard import reportpdf as rpdf
    from osloquant.dashboard import reports as rp

    today = today or pd.Timestamp.now().normalize()
    out = []
    for c in cases:
        v = c.view
        if not v:
            continue
        issues = []
        vdate = pd.Timestamp(str(v.get("date"))[:10]) if v.get("date") else None
        age = (today - vdate).days if vdate is not None else None
        if age is not None and age > CASE_VIEW_AGE:
            issues.append(f"synet er {age} dager gammelt")
        last_px = None
        if closes is not None and c.code in closes and closes[c.code].dropna().size:
            last_px = float(closes[c.code].dropna().iloc[-1])
        lc = lcm.load(c.code)
        lc_built, lc_gap = None, None
        if lc:
            lc_built = str(lc.get("built_at", ""))[:10]
            lp = lc.get("price")
            if isinstance(lp, dict):
                lp = next((lp[k] for k in ("close", "value", "price", "last") if isinstance(lp.get(k), (int, float))), None)
            if isinstance(lp, (int, float)) and lp and last_px:
                lc_gap = last_px / float(lp) - 1
                if abs(lc_gap) > CASE_PRICE_GAP:
                    issues.append(f"lett case bygget på kurs {float(lp):.2f}, lageret sier {last_px:.2f} ({lc_gap * 100:+.0f} %)")
        else:
            issues.append("ingen lett case (oq case build)")
        ents = rpdf.entries(c.code)
        rep = ents[0] if ents else None
        mm = rpdf.tp_mismatch(rep, v, c.history)
        if mm:
            issues.append(f"rapporten {mm['report_date']} sier kursmål {mm['report_tp']:g}, synet {mm['view_tp']:g}")
        s = rp.latest(c.code)
        if s and vdate is not None and pd.Timestamp(str(s.get("published", ""))[:10]) > vdate and not any(
                r["kind"] == "judgement" and str(r.get("date", ""))[:10] >= str(s.get("published", ""))[:10] for r in c.history):
            issues.append(f"rapportleseren har Q{s.get('quarter')} {s.get('year')} ({str(s.get('published', ''))[:10]}) – nyere enn synet, ingen ny vurdering")
        model_date = None
        if c.model and c.model.get("xlsx"):
            p = Path(str(c.model["xlsx"])).expanduser()
            if p.exists():
                model_date = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
                if rep and rep["date"] > model_date:
                    issues.append(f"modellfilen i research book er fra {model_date}, rapporten fra {rep['date']}")
            else:
                issues.append("modellfilen i research book finnes ikke")
        from osloquant.dashboard import calendar as cal

        future = [e for e in c.events if pd.Timestamp(e["date"]) >= today]
        if not future and not any(e.get("code") == c.code for e in cal.events([c], today=today, days=200)):
            issues.append("ingen kommende dato i research book eller finanskalenderen")
        # price reconciliation at entry (ideer.md #24): the row's price against the store's close on its price date
        pdate = str(v.get("price_date") or v.get("date") or "")[:10]
        if closes is not None and c.code in closes and pdate and v.get("price"):
            ser = closes[c.code].dropna()
            on = ser[ser.index <= pd.Timestamp(pdate)]
            if len(on) and abs(float(on.index[-1].strftime("%Y-%m-%d") == pdate) - 1) < 0.5:
                close = float(on.iloc[-1])
                if abs(close / float(v["price"]) - 1) > 0.01:
                    issues.append(f"synet er logget til kurs {float(v['price']):.2f}, lagerets sluttkurs {pdate} er {close:.2f} ({(close / float(v['price']) - 1) * 100:+.1f} %)")
        from osloquant.dashboard import killlist as kl

        kr = kl.for_case(c)
        if kr:
            issues += [f"kill-listen: {i}" for i in kr["issues"]]
        out.append({"code": c.code, "name": c.name, "view_date": str(v.get("date") or "")[:10], "view_age": age, "lightcase_built": lc_built,
                    "lightcase_gap": lc_gap, "report_date": rep["date"] if rep else None, "report_tp": rep["tp"] if rep else None,
                    "model_date": model_date, "issues": issues})
    return out


def overview(closes: pd.DataFrame, cases, asof: pd.Timestamp | None = None) -> dict:
    return {"prices": price_health(closes, asof), "feeds": feed_health(), "reports": report_health(cases), "log": log_health(), "cases": case_health(cases, closes),
            "store": store_health(), "testdata": testdata_health(), "dividends": dividend_audit_cached(), "sources": _sources(),
            "corporate": fd.corporate_events(), "cross": _cross(),
            "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}


CORPORATE_ALERT_DAYS = 14


def _recent(events: list[dict], now: datetime | None = None) -> list[dict]:
    """The events of the last fortnight, newest first, one per company and kind: an issuer that publishes in two
    languages, or the exchange and the company both, is one event."""
    cutoff = f"{(now or datetime.now(UTC)) - pd.Timedelta(days=CORPORATE_ALERT_DAYS):%Y-%m-%d}"
    seen, out = set(), []
    for e in sorted((e for e in events if e.get("time", "")[:10] >= cutoff), key=lambda e: e["time"], reverse=True):
        key = (fd.corporate_subject(e).lower(), e["kind"])
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def _coming(e: dict) -> bool:
    """A listing that is applied for or announced, of a company outside the universe: nothing to check yet."""
    return e["kind"] == "ny på børsen" and not e.get("in_universe") and fd.listing_stage(e.get("title", "")) not in fd.LISTED


def corporate_lines(events: list[dict], now: datetime | None = None) -> list[str]:
    """One line per corporate event from the last fortnight that touches the universe: the universe is a fixed list and
    may need a look. A listing that has not happened yet is in ``coming_lines``."""
    out = []
    for e in _recent(events, now):
        if _coming(e):
            continue
        stage = fd.listing_stage(e.get("title", "")) if e["kind"] == "ny på børsen" else None
        out.append(f"{fd.corporate_subject(e)}: {e['kind']}" + (f", {stage}" if stage else "") + f" {dato(e['time'][:10], False)}"
                   + ("" if e.get("in_universe") else " (ikke i universet)"))
    return out


def coming_lines(events: list[dict], now: datetime | None = None) -> list[str]:
    """Companies on their way to the exchange: «Cetus Maritime Holdings Limited: søknad om opptak til handel 10. nov.»"""
    return [f"{fd.corporate_subject(e)}: {fd.listing_stage(e.get('title', '')) or 'notering omtalt'} {dato(e['time'][:10], False)}"
            for e in _recent(events, now) if _coming(e)]


def corporate_html(events: list[dict]) -> str:
    from osloquant.dashboard.render import E, link

    def who(e: dict) -> str:
        if e.get("in_universe"):
            return f'{link(e["code"])} <span class="src">{E(e.get("issuer") or "")}</span>'
        subject = fd.corporate_subject(e)
        via = e.get("issuer") or ""
        return E(subject) + (f' <span class="src">meldt av {E(via)}</span>' if via and via != subject else "")

    def what(e: dict) -> str:
        stage = fd.listing_stage(e.get("title", "")) if e["kind"] == "ny på børsen" else None
        return E("på vei til børsen" if _coming(e) else e["kind"]) + (f' <span class="src">{E(stage)}</span>' if stage else "")

    rows = "".join(f'<tr><td class="l">{dato(e["time"][:10])}</td><td class="l">{who(e)}</td><td class="l">{what(e)}</td>'
                   f'<td class="l" style="white-space:normal"><a href="{E(e["url"])}" target="_blank" rel="noopener">{E(e["title"][:140])}</a></td></tr>' for e in events)
    return ('<div class="card" id="selskapshendelser"><h3>Selskapshendelser (siste 120 dager)</h3><table class="odds"><thead><tr><th class="l">Dato</th><th class="l">Selskap</th>'
            f'<th class="l">Hva</th><th class="l">Børsmelding</th></tr></thead><tbody>{rows or "<tr><td colspan=4 class=empty>ingen funnet i børsmeldingene</td></tr>"}</tbody></table>'
            '<div class="src">Lest av titlene på børsmeldingene vi allerede henter (Oslo Børs NewsWeb): emisjon, splitt eller spleis, fisjon eller fusjon, navn- eller tickerendring, '
            'avnotering og nye selskaper tatt opp til handel. Obligasjoner er holdt utenfor. Universet er en fast liste: en ny notering, en avnotering eller en tickerendring betyr at '
            'listen bør oppdateres, og en splitt eller fisjon at kursene bør sjekkes mot en annen kilde. En tittel kan misforstås – åpne meldingen.</div></div>')


REPORT_STATUS_NO = {"ok": "ok", "no spec": "ingen spesifikasjon", "no report read": "ingen rapport lest", "rows missing": "rader mangler"}


def _cross() -> list[dict]:
    from osloquant.dashboard import sources as src

    try:
        return src.cross_checks()
    except Exception:  # noqa: BLE001 – a comparison that cannot be made must not take the page down
        import logging

        logging.getLogger("osloquant.dashboard").exception("cross checks failed")
        return []


def _sources() -> list[dict]:
    from osloquant.dashboard import sources as src

    try:
        return src.status()
    except Exception:  # noqa: BLE001 – the page must open even when the run log is unreadable
        import logging

        logging.getLogger("osloquant.dashboard").exception("source status failed")
        return []


def problems(ov: dict) -> list[str]:
    """One line per thing that should worry the reader, for the front page and the morning."""
    from osloquant.dashboard import sources as src

    out = src.problem_lines(ov.get("sources") or [])
    out += src.cross_lines(ov.get("cross") or [])
    corp = corporate_lines(ov.get("corporate") or [])
    if corp:
        out.append("selskapshendelser siste 14 dager – universet og kursene bør sjekkes: " + "; ".join(corp[:6]))
    p = ov["prices"]
    if p["stale"] and not any(s["key"] == "prices_adj" and s["state"] in ("stale", "partial") for s in ov.get("sources") or []):
        out.append(f"{len(p['stale'])} aksjer uten sluttkurs {dato(p['asof'])}: {', '.join(p['stale'][:8])}")
    for r in ov["reports"]:
        if r["status"] != "ok" and r.get("oscar_view", True):
            out.append(f"rapportleseren {r['code']}: {REPORT_STATUS_NO.get(r['status'], r['status'])}"
                       + (f" – {', '.join(r['missing'])}" if r["missing"] and r["status"] == "rows missing" else ""))
    lg = ov["log"]
    if lg["chain_ok"] is False or lg["problems"]:
        out.append("vurderingsloggen: " + "; ".join(lg["problems"][:2]))
    d = ov.get("dividends")
    if d is None:
        out.append("utbytterevisjonen er aldri kjørt (oq data audit)")
    elif d.get("missed"):
        out.append(f"{len(d['missed'])} ex-utbyttemeldinger uten Yahoo-justering ({', '.join(list(d['missed_yield_by_code'])[:5])})")
    if not ov["testdata"]["present"]:
        out.append("frosne testdata mangler: de deterministiske testene hopper over")
    for ch in ov.get("cases") or []:
        kills = [i for i in ch["issues"] if i.startswith("kill-listen:")]
        for i in ch["issues"]:
            if not i.startswith("kill-listen:"):
                out.append(f"{ch['code']}: {i}")
        if kills:                                             # one line, not one per divergence; the stock page lists them
            out.append(f"{ch['code']}: kill-listen spriker ({len(kills)} avvik – se aksjesiden)")
    return out


def _fmt_dt(s: str | None) -> str:
    from osloquant.dashboard.dates import stempel

    return stempel(s) if s else "–"


def page_html(ov: dict) -> str:
    from osloquant.dashboard.render import E, link, page, pct

    probs = problems(ov)
    head = ('<h1>Datahelse</h1><div class="sub">Hva som er utdatert, mangler eller ikke stemmer – før et tall leses av.</div>'
            + ('<div class="warn"><b>Ting å vite nå:</b><ul>' + "".join(f"<li>{E(x)}</li>" for x in probs) + '</ul></div>' if probs
               else '<div class="ok">Ingen kjente problemer i dataene akkurat nå.</div>'))
    st = ov["store"]
    store = ('<div class="card"><h3>Lageret</h3><ul class="kv">' + "".join(
        f'<li><b>{E(k)}</b>: ' + (f'siste {E(str(v.get("last")))}, {v.get("entities")} instrumenter, {v.get("rows")} rader' if "last" in v else E(v.get("error", ""))) + '</li>'
        for k, v in st.items()) + f'</ul><div class="src">Yahoo Finance daglige kurser, forsinket. Justert = utbytte reinvestert. Siste økt i lageret: {E(ov["prices"]["asof"])}.</div></div>')
    pr = ov["prices"]
    rows = "".join(
        f'<tr><td>{link(r["code"])}</td><td>{E(str(r["first"]))}</td><td class="{"k" if r["stale"] else ""}">{E(str(r["last"]))}{" (stale)" if r["stale"] else ""}</td>'
        f'<td>{r["missing_250"] if r["missing_250"] is not None else "–"}</td>'
        f'<td style="white-space:normal">{"; ".join(f"{a}→{b} ({n})" for a, b, n in r["gaps"]) or ""}</td>'
        f'<td style="white-space:normal">{"; ".join(f"{d} {v * 100:+.0f}%" for d, v in r["big_moves"]) or ""}</td></tr>'
        for r in pr["rows"] if r["stale"] or r["missing_250"] or r["gaps"] or r["big_moves"])
    prices = (f'<div class="card"><h3>Kurser: {pr["stocks"]} aksjer, {len(pr["stale"])} uten siste sluttkurs, {len(pr["with_gaps"])} med lange hull</h3>'
              '<table class="odds"><thead><tr><th>Aksje</th><th>Første</th><th>Siste</th><th>Mangler av siste 250</th><th>Hull ≥ 20 økter (fra→til, n)</th>'
              f'<th>Dagsbevegelser ≥ 25 % siste 60 økter</th></tr></thead><tbody>{rows or "<tr><td colspan=6 class=empty>none</td></tr>"}</tbody></table>'
              '<div class="src">Bare aksjer med noe å melde vises. Et hull er økter der andre aksjer handlet. Store bevegelser er ikke feil i seg selv – '
              'de er listet så de kan sjekkes mot en annen kilde.</div></div>')
    fe = "".join(f'<tr><td>{E(f["feed"])}</td><td class="{"k" if f["status"] != "ok" else ""}">{E(f["status"])}</td><td>{E(_fmt_dt(f["fetched_at"]))}</td>'
                 f'<td>{"–" if f["age_days"] is None else f["age_days"]}</td><td>{f["limit_days"]}</td><td>{"–" if f["items"] is None else f["items"]}</td><td class="src">{E(str(f.get("error") or ""))}</td></tr>'
                 for f in ov["feeds"])
    feeds = ('<div class="card"><h3>Feeds</h3><table class="odds"><thead><tr><th>Feed</th><th>Status</th><th>Hentet</th><th>Alder (d)</th><th>Grense</th><th>Rader</th><th></th></tr></thead>'
             f'<tbody>{fe}</tbody></table><div class="src">Hentes av oq dashboard --refresh og kveldsoppgaven. Grensen er dager før feeden regnes som utdatert.</div></div>')
    rp_rows = "".join(f'<tr><td>{link(r["code"])}</td><td class="l {"st-bad" if r["status"] != "ok" else "st-ok"}">{E(REPORT_STATUS_NO.get(r["status"], r["status"]))}</td><td>{E(str(r["latest"] or "–"))[:60]}</td>'
                      f'<td>{E(str(r["published"] or "–"))}</td><td style="white-space:normal">{E(", ".join(r["missing"]))}</td><td>{r["kill_rules"]} av {r["kill_texts"]}</td></tr>' for r in ov["reports"])
    reports = ('<div class="card"><h3>Rapportleseren</h3><table class="odds"><thead><tr><th>Case</th><th>Status</th><th>Siste rapport lest</th><th>Publisert</th>'
               f'<th>Rader ikke funnet</th><th>Kill-regler</th></tr></thead><tbody>{rp_rows or "<tr><td colspan=6 class=empty>ingen caser i research book</td></tr>"}</tbody></table>'
               '<div class="src">Spesifikasjon per selskap i ~/osloquant-home/reports.yaml; test en ny med oq reports dryrun.</div></div>')
    def _case_row(r: dict) -> str:
        age = f' ({r["view_age"]} d)' if r["view_age"] is not None else ""
        gap = f' ({r["lightcase_gap"] * 100:+.0f} %)' if r["lightcase_gap"] is not None else ""
        tp = f' (TP {r["report_tp"]:g})' if isinstance(r.get("report_tp"), (int, float)) else ""
        plain = [i for i in r["issues"] if not i.startswith("kill-listen:")]
        kills = [i for i in r["issues"] if i.startswith("kill-listen:")]
        items = "".join(f"<li>{E(i)}</li>" for i in plain)
        if kills:
            items += (f'<li><details><summary>kill-listen spriker: {len(kills)} avvik</summary><ul>'
                      + "".join(f"<li>{E(k.removeprefix('kill-listen: '))}</li>" for k in kills) + '</ul></details></li>')
        cell = f'<ul class="issues">{items}</ul>' if items else '<span class="t">ok</span>'
        return (f'<tr><td>{link(r["code"])}</td><td>{E(r["view_date"])}{age}</td><td>{E(r["lightcase_built"] or "–")}{gap}</td>'
                f'<td>{E(r["report_date"] or "–")}{tp}</td><td>{E(r["model_date"] or "–")}</td>'
                f'<td style="white-space:normal;text-align:left;font-weight:400">{cell}</td></tr>')

    ch_rows = "".join(_case_row(r) for r in ov.get("cases") or [])
    cases_html = ('<div class="card"><h3>Caser: alder og avvik mellom kilder</h3><table class="odds"><thead><tr><th>Case</th><th>Syn (alder)</th><th>Lett case (kurs mot lageret)</th>'
                  f'<th>Siste rapport (kursmål)</th><th>Modellfil</th><th>Avvik</th></tr></thead><tbody>{ch_rows or "<tr><td colspan=6 class=empty>ingen case med syn</td></tr>"}</tbody></table>'
                  '<div class="src">Synet: vurderingsloggen. Lett case: cases/&lt;KODE&gt;.json (Yahoo-regnskap). Rapport: cases/reports_pdf. Modellfil: regnearket research book peker på. '
                  'Et avvik er ikke en feil – det er et sted du ikke skal lese av ett tall uten å vite om det andre.</div></div>')
    lg = ov["log"]
    d = ov.get("dividends")
    if d is None:
        div = '<p class="empty">Ikke kjørt. <code>oq data audit</code> sjekker hver ex-utbyttemelding på NewsWeb siden 2010 mot Yahoos justeringer (64 kall, noen minutter).</p>'
    else:
        miss = "".join(f'<tr><td>{link(m["code"])}</td><td>{dato(m["date"])}</td><td>{m["amount"]:g}</td><td>{m["price"] if m["price"] is not None else "–"}</td>'
                       f'<td>{pct(m["yield"], 1, False)}{" (før en senere splitt – ikke en yield)" if m.get("yield_doubtful") else ""}</td>'
                       f'<td><a href="{E(m["url"])}" target="_blank" rel="noopener">NewsWeb</a></td></tr>' for m in d["missed"])
        susp = f' Beløp fra før en senere splitt ({E(", ".join(d.get("split_suspect_codes", [])))}) er listet, men ikke summert.' if d.get("split_suspect_codes") else ""
        div = (f'<p>{d["notices"]} ex-utbyttemeldinger med beløp siden {E(d["since"])} på {d["stocks"]} aksjer; <b>{len(d["missed"])}</b> uten Yahoo-justering '
               f'(yield over 0,3 %). Tapt yield per aksje (prosentpoeng): {E(", ".join(f"{k} {v * 100:.1f}" for k, v in list(d["missed_yield_by_code"].items())[:10]))}.{susp}</p>'
               f'<details><summary>Hver manglende melding</summary><table class="odds"><thead><tr><th>Aksje</th><th>Ex-dato</th><th>Beløp</th><th>Kurs</th><th>Yield</th><th></th></tr></thead>'
               f'<tbody>{miss}</tbody></table></details><div class="src">Hentet {E(_fmt_dt(d.get("fetched_at")))}. Et utbytte Yahoo ikke har justert for vises som et kursfall i den justerte serien: '
               'falske risikosignaler den dagen og lavere totalavkastning for aksjen det året. Nedre grense: utstedere som melder ex-datoer i andre kategorier fanges ikke.</div>')
    log_card = (f'<div class="grid2"><div class="card"><h3>Vurderingsloggen</h3><ul class="kv"><li><b>Rader</b>: {lg["rows"]}</li>'
                f'<li><b>Kjede</b>: {"verifiserer" if lg["chain_ok"] else ("BRUTT" if lg["chain_ok"] is False else "tom")}</li>'
                f'<li><b>Sist logget</b>: {E(_fmt_dt(lg["last_logged_at"]))}</li><li><b>Head</b>: {E(str(lg["head"] or "–"))}</li></ul>'
                + ("".join(f'<div class="err">{E(x)}</div>' for x in lg["problems"]) if lg["problems"] else "") + '</div>'
                f'<div class="card"><h3>Frosne testdata</h3><p>{"finnes" if ov["testdata"]["present"] else "<b>mangler</b>"} – {E(ov["testdata"]["path"])}, kurser til {E(ov["testdata"]["frozen_to"])}; '
                f'{len(ov["testdata"]["files"])} filer.</p><div class="src">De deterministiske testene (odds, intervaller, innsidestudien, SATS-rapportene) kjører på denne kopien og hopper over uten den.</div></div></div>')
    from osloquant.dashboard import sources as src

    kilder = src.table_html(ov["sources"]) if ov.get("sources") else store + feeds
    return page("Datahelse", "/health", head + kilder + (src.cross_html(ov["cross"]) if ov.get("cross") else "") + corporate_html(ov.get("corporate") or []) + cases_html + prices + reports + f'<div class="card"><h3>Utbytter: Yahoo mot NewsWeb</h3>{div}</div>' + log_card
                )
