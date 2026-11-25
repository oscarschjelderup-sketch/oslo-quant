"""External feeds for the dashboard, fetched by `oq dashboard --refresh` (and the evening task) into a private cache
(``~/osloquant-home/feeds/*.json``). Pages only read the cache, so a page never waits on the network and every item
carries the source and the time it was fetched. Only headlines and links are stored from news feeds – never text.

The endpoints and their terms are documented in docs/dashboard/data-sources.md; each fetcher here uses only what that
note verified.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from osloquant import judgements as jg

FEEDS = ("announcements", "rates", "fx", "salmon", "brent", "news", "shorts", "insiders", "calendar", "macro")
UA = "oslo-quant private dashboard (personal, non-commercial)"


def cache_dir() -> Path:
    d = jg.home() / "feeds"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read(name: str) -> dict | None:
    try:
        return json.loads((cache_dir() / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write(name: str, doc: dict) -> None:
    doc = {**doc, "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (cache_dir() / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def _age(doc: dict | None) -> str:
    if not doc or not doc.get("fetched_at"):
        return "ikke hentet"
    from osloquant.dashboard.dates import stempel

    return f"hentet {stempel(doc['fetched_at'])}"


# ------------------------------------------------------------------------------------------------ readers (pages)
def announcements(codes: list[str], days: int = 7) -> dict | None:
    doc = read("announcements")
    if not doc:
        return None
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    items = [a for a in doc.get("items", []) if a["code"] in codes and a["time"][:10] >= cutoff]
    return {"items": sorted(items, key=lambda a: a["time"], reverse=True), "source": f"{doc.get('source', '')}; {_age(doc)}"}


# How headlines name a company, where the listed name is not how the press writes it. Matching is case-sensitive on
# whole words, and the longer names of other companies are removed first ("Aker BP" is not news about "Aker").
NEWS_KEYS = {
    "NAS": ["Norwegian"], "HAUTO": ["Höegh Autoliners", "Høegh Autoliners"], "WWI": ["Wilh. Wilhelmsen"],
    "KOG": ["Kongsberg Gruppen", "Kongsberg"], "OUTLT": ["Outlet Group"], "LSG": ["Lerøy"], "AUSS": ["Austevoll"],
    "PROT": ["Protector"], "HEX": ["Hexagon"], "NOD": ["Nordic Semiconductor", "Nordic Semi"], "PEN": ["Panoro"],
    "SOFF": ["Solstad"], "BORR": ["Borr Drilling", "Borr"], "OET": ["Okeanis"], "MPCC": ["MPC Container"],
    "SNI": ["Stolt-Nielsen"], "DOFG": ["DOF"], "SALM": ["SalMar", "Salmar"], "AKRBP": ["Aker BP"], "VAR": ["Vår Energi"],
}


# Names that contain a universe company's name but are another company: a headline with one of these is not about ours.
NEWS_NOT = {"KOG": ["Kongsberg Maritime", "Kongsberg kommune", "Kongsberg Automotive"], "NAS": ["Norwegian Cruise", "Norwegian Property"],
            "AKER": ["Aker BP", "Aker Solutions", "Aker Carbon", "Aker Horizons", "Aker Brygge"], "DNB": ["DNB Markets", "DNB Carnegie"]}


def news_keys(code: str, name: str) -> list[str]:
    return NEWS_KEYS.get(code, [name or code])


def mentions(title: str, code: str, names: dict[str, str]) -> bool:
    """Does a headline name this company? `names` is the universe (code -> name), used to strip longer names."""
    import re

    keys = news_keys(code, names.get(code, code))
    for other_name in NEWS_NOT.get(code, ()):
        title = title.replace(other_name, " ")
    for other, oname in names.items():
        if other == code:
            continue
        for ok in news_keys(other, oname):
            if any(k in ok and len(ok) > len(k) for k in keys):
                title = title.replace(ok, " ")
    return any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", title) for k in keys)


def company_news(code: str, name: str, names: dict[str, str] | None = None) -> dict | None:
    """Announcements for the company plus media headlines that name it (see `mentions`)."""
    ann, news = read("announcements"), read("news")
    if not ann and not news:
        return None
    names = names or {code: name}
    items = [{**a, "kind": "børsmelding"} for a in (ann or {}).get("items", []) if a["code"] == code]
    for n in (news or {}).get("items", []):
        if mentions(n["title"], code, names):
            items.append({**n, "kind": n.get("outlet", "news")})
    items = sorted(items, key=lambda a: a["time"], reverse=True)[:25]
    srcs = "; ".join(s for s in (ann and f"{ann.get('source')} ({_age(ann)})", news and f"{news.get('source')} ({_age(news)})") if s)
    return {"items": items, "source": srcs + ". Headlines and links only."}


def _value(doc: dict | None, label: str, fmt: str) -> dict | None:
    if not doc or doc.get("error") or doc.get("value") is None:
        return {"label": label, "value": "unavailable", "source": (doc or {}).get("error") or "not fetched (oq dashboard --refresh)"}
    from osloquant.dashboard.dates import dato

    return {"label": label, "value": fmt.format(doc["value"]) + (f" ({dato(doc['date'])})" if doc.get("date") else ""),
            "source": f"{doc.get('source', '')}, {_age(doc)}" + ("; delayed" if doc.get("delayed") else "")}


def sector_drivers() -> dict[str, list[dict]]:
    rates, fx, salmon, brent = read("rates"), read("fx"), read("salmon"), read("brent")
    pr = rates and {"value": rates.get("policy_rate"), "date": rates.get("policy_date"), "source": rates.get("source"),
                    "fetched_at": rates.get("fetched_at"), "error": rates.get("error")}
    y10 = rates and {"value": rates.get("gov10y"), "date": rates.get("gov10y_date"), "source": rates.get("source"),
                     "fetched_at": rates.get("fetched_at"), "error": rates.get("error")}
    usd = fx and {"value": fx.get("USDNOK"), "date": fx.get("date"), "source": fx.get("source"), "fetched_at": fx.get("fetched_at"), "error": fx.get("error")}
    eur = fx and {"value": fx.get("EURNOK"), "date": fx.get("date"), "source": fx.get("source"), "fetched_at": fx.get("fetched_at"), "error": fx.get("error")}
    i44 = fx and fx.get("I44") is not None and {"value": fx.get("I44"), "date": fx.get("I44_date"), "source": fx.get("source"), "fetched_at": fx.get("fetched_at")}
    krone = [_value(i44, "Kronekursindeks I44 (høyere = svakere krone)", "{:.2f}")] if i44 else []
    unavailable = lambda label, why: {"label": label, "value": "not free", "source": why}  # noqa: E731
    return {
        "Energy": [_value(brent, "Brent", "USD {:.2f}/bbl"), _value(usd, "USD/NOK", "{:.3f}")],
        "Shipping": [unavailable("Freight rates (Baltic indices, TCE)", "licensed by the Baltic Exchange – not available free"),
                     _value(usd, "USD/NOK", "{:.3f}")],
        "Seafood": [_value(salmon, "Salmon export price (fresh, whole)", "NOK {:.2f}/kg"), _value(eur, "EUR/NOK", "{:.3f}"), *krone],
        "Finance": [_value(pr, "Policy rate", "{:.2f}%"), _value(y10, "10-year government bond", "{:.2f}%")],
        "Industrials & materials": [_value(usd, "USD/NOK", "{:.3f}"), _value(eur, "EUR/NOK", "{:.3f}"), *krone],
        "Consumer, telecom & real estate": [_value(pr, "Policy rate", "{:.2f}%")],
        "Technology & renewables": [_value(y10, "10-year government bond", "{:.2f}%"), _value(usd, "USD/NOK", "{:.3f}")],
        "Investment companies": [_value(y10, "10-year government bond", "{:.2f}%")],
    }


def followed_codes() -> list[str]:
    """Research-book companies and watched ones: the feeds that cost a request per company are fetched for these only."""
    from osloquant.dashboard import book as bk

    codes = [c.code for c in bk.cases()] + [w["code"] for w in bk.watchlist() if not w.get("moved_to_book")]
    return sorted(set(codes))


# ------------------------------------------------------------------------------------------------ fetchers (refresh)
def refresh(codes: list[str] | None = None) -> dict[str, str]:
    """Fetch every feed into the cache; returns feed -> 'ok' or the error. A failed feed keeps its old cache."""
    from osloquant.dashboard import calendar as cal
    from osloquant.dashboard import insiders as ins
    from osloquant.dashboard import sources as src

    out = {}
    year = datetime.now(UTC).year
    for name, fn in (("announcements", lambda: fetch_announcements(codes or [])), ("rates", fetch_rates), ("fx", fetch_fx),
                     ("salmon", fetch_salmon), ("brent", fetch_brent), ("news", fetch_news), ("shorts", ins.fetch_shorts),
                     ("insiders", lambda: ins.fetch(codes or [], start_year=year, log=lambda s: None)),
                     ("calendar", lambda: cal.fetch_financial_calendars(followed_codes())), ("macro", fetch_macro)):
        try:
            write(name, src.timed(src.FEED_KEY.get(name, name), fn))
            out[name] = "ok"
        except Exception as e:  # noqa: BLE001 – one feed down must not stop the others; the attempt is in the run log
            out[name] = _scrub(f"{type(e).__name__}: {e}", fred_key()[0])[:200]
    return out


RETRY_PAUSES = (2.0, 5.0)        # seconds before the second and third attempt
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _open(req, timeout: int) -> bytes:
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 – fixed https URLs below
        return r.read()


def _get(url: str, method: str = "GET", timeout: int = 20, pauses: tuple[float, ...] | None = None) -> bytes:
    """One request with up to three attempts. A network error, a timeout, a 429 or a 5xx is tried again after a pause;
    any other HTTP status (404: no such page) is an answer and is raised at once."""
    import time
    import urllib.error

    pauses = RETRY_PAUSES if pauses is None else pauses
    for attempt in range(len(pauses) + 1):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"},
                                     data=b"" if method == "POST" else None)
        try:
            return _open(req, timeout)
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == len(pauses):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == len(pauses):
                raise
        time.sleep(pauses[attempt])
    raise RuntimeError("unreachable")


NEWSWEB = "https://api3.oslo.oslobors.no/v1/newsreader"
ANN_DAYS, ANN_KEEP_DAYS = 14, 120


def days_to_fetch(fetched_at: str | None, today, most: int = ANN_DAYS) -> int:
    """How many calendar days back a list must go: the days since the last good fetch plus one of overlap, at most
    ``most``. Fetched yesterday evening gives 2 (today and yesterday), not 14."""
    try:
        last = datetime.strptime(str(fetched_at), "%Y-%m-%dT%H:%M:%SZ").date()
    except ValueError:
        return most
    return max(2, min(most, (today - last).days + 2))


# Corporate events read off the announcement titles we fetch anyway (D60, funn D13). Bonds are not shares.
_NOT_SHARES = r"(?i)\b(bonds?|obligasjon\w*|notes due|green bond|certificates?|sertifikat\w*|warrants?|etn|etf)\b"
CORPORATE = (
    ("ny på børsen", r"(?i)admission to trading|admitted to trading|opptak til handel|first day of (trading|listing)|første (handels|noterings)dag|approved for listing|listing on (euronext )?(oslo børs|expand|growth)"),
    ("avnotering", r"(?i)delisting|strykning|removal from trading|last day of trading|siste (handels|noterings)dag|compulsory acquisition|tvangsinnløsning"),
    ("navn eller ticker", r"(?i)change of (company )?name|name change|navneendring|endring av (selskaps)?navn|new ticker|ny ticker|change of ticker|ticker change"),
    ("fisjon eller fusjon", r"(?i)\bdemerger\b|\bspin-?off\b|\bfisjon\w*|\bmerger\b|\bfusjon\w*"),
    ("splitt eller spleis", r"(?i)share split|reverse (share )?split|aksjesplitt|aksjespleis|\bspleis\b|consolidation of shares"),
    ("emisjon", r"(?i)private placement|rights issue|rettet emisjon|fortrinnsrettsemisjon|\bemisjon\b|share capital increase|kapitalforhøyelse|subsequent offering|reparasjonsemisjon"),
)
CORPORATE_KEEP_DAYS = 120


def corporate_kind(title: str) -> str | None:
    """What kind of corporate event a title announces, or None. A bond listing is not a share listing."""
    import re

    if not title or re.search(_NOT_SHARES, title):
        return None
    for kind, pattern in CORPORATE:
        if re.search(pattern, title):
            return kind
    return None


#: how far a listing has come, read from the title; the first two mean the share is trading
LISTING_STAGE = (
    ("første handelsdag", r"(?i)first day of (trading|listing)|første (handels|noterings)dag"),
    ("tatt opp til handel", r"(?i)admitted to trading|tatt opp til handel"),
    ("godkjent for notering", r"(?i)approved for (listing|admission)|godkjent for (notering|opptak)"),
    ("søknad om opptak til handel", r"(?i)received application|mottatt søknad|application for admission|søknad om opptak"),
    ("notering varslet", r"(?i)intends to apply|plans to (apply|list)|contemplated|subsequent listing|planlegger|vurderer notering"),
)
LISTED = ("første handelsdag", "tatt opp til handel")
_EXCHANGE = r"(?i)^(euronext|oslo børs|oslo bors)"


def listing_stage(title: str) -> str | None:
    import re

    return next((stage for stage, pattern in LISTING_STAGE if re.search(pattern, title or "")), None)


def company_from_title(title: str) -> str | None:
    """The company a listing announcement is about, read from the title. The exchange publishes these itself, so the
    issuer field says «Oslo Børs» and the ticker field «-»."""
    import re

    t = (title or "").strip()
    m = re.search(r"(?i)(?:admission to trading|opptak til handel|first day of (?:trading|listing)|første (?:handels|noterings)dag|approved for listing)\s*[-–:]\s*(.+)$", t)
    if m:
        return m.group(1).strip() or None
    if ":" in t:
        head = t.split(":", 1)[0].strip()
        if 2 < len(head) <= 70 and not re.search(_EXCHANGE, head):
            return head
    m = re.match(r"(?i)(.+?)\s+(?:intends to|plans to|has applied|applies for|to apply|søker om|har søkt|planlegger)\b", t)
    if m and not re.search(_EXCHANGE, m.group(1)):
        return m.group(1).strip()
    parts = [p.strip() for p in re.split(r"\s+[-–]\s+", t) if p.strip()]
    if len(parts) > 1:
        named = [p for p in (parts[0], parts[-1]) if not re.search(_EXCHANGE, p) and not listing_stage(p)]
        return named[0] if named else None
    return None


def corporate_subject(e: dict) -> str:
    """Who a corporate event is about: the ticker when there is one, otherwise the company named in the title."""
    code = (e.get("code") or "").strip()
    if code and code not in ("-", "–"):
        return code
    return company_from_title(e.get("title", "")) or e.get("issuer") or "ukjent selskap"


def corporate_events(days: int = CORPORATE_KEEP_DAYS, now: datetime | None = None) -> list[dict]:
    """The corporate events in the announcement cache from the last ``days`` days, newest first."""
    doc = read("announcements") or {}
    cutoff = f"{(now or datetime.now(UTC)) - timedelta(days=days):%Y-%m-%d}"
    return sorted((e for e in doc.get("corporate", []) if e.get("time", "")[:10] >= cutoff), key=lambda e: e["time"], reverse=True)


def fetch_announcements(codes: list[str], days: int = ANN_DAYS) -> dict:
    """NewsWeb list, one POST per calendar day (a day is far below the ~600-message cap), filtered to the universe.
    Stores title, time, category and the NewsWeb link – never the body. Merged with the cache, kept 120 days."""
    want = {c.upper() for c in codes}
    today = datetime.now(UTC).date()
    old = read("announcements") or {}
    items = {a["id"]: a for a in old.get("items", [])}
    corporate = {e["id"]: e for e in old.get("corporate", [])}
    days = days_to_fetch(old.get("fetched_at"), today, days) if items else days
    for i in range(days):
        d = f"{today - timedelta(days=i):%Y-%m-%d}"
        doc = json.loads(_get(f"{NEWSWEB}/list?fromDate={d}&toDate={d}", method="POST"))
        for m in doc.get("data", {}).get("messages", []):
            code = (m.get("issuerSign") or "").upper()
            kind = corporate_kind(m.get("title", ""))
            if kind and (code in want or kind == "ny på børsen"):       # a new listing matters also outside the universe
                corporate[m["messageId"]] = {"id": m["messageId"], "code": code, "issuer": m.get("issuerName"), "title": m.get("title", ""),
                                             "time": m.get("publishedTime", ""), "kind": kind, "in_universe": code in want,
                                             "url": f"https://newsweb.oslobors.no/message/{m['messageId']}"}
            if want and code not in want:
                continue
            cat = (m.get("category") or [{}])[0]
            items[m["messageId"]] = {"id": m["messageId"], "code": code, "issuer": m.get("issuerName"), "title": m.get("title", ""),
                                     "time": m.get("publishedTime", ""), "category": cat.get("category_en") or cat.get("category_no") or "",
                                     "url": f"https://newsweb.oslobors.no/message/{m['messageId']}"}
    cutoff = f"{today - timedelta(days=ANN_KEEP_DAYS):%Y-%m-%d}"
    kept = sorted((a for a in items.values() if a["time"][:10] >= cutoff), key=lambda a: a["time"], reverse=True)
    corp = sorted((e for e in corporate.values() if e["time"][:10] >= f"{today - timedelta(days=CORPORATE_KEEP_DAYS):%Y-%m-%d}"),
                  key=lambda e: e["time"], reverse=True)
    return {"items": kept, "corporate": corp, "source": "Oslo Børs NewsWeb (real time; private use only)"}


NORGES_BANK = "https://data.norges-bank.no/api/data"


def _nb_last(flow_key: str) -> list[dict]:
    """The last observation of each series in a Norges Bank SDMX query, from its ';'-separated CSV."""
    rows = list(csv.DictReader(io.StringIO(_get(f"{NORGES_BANK}/{flow_key}?format=csv&lastNObservations=1&locale=en").decode("utf-8-sig")),
                               delimiter=";"))
    if not rows:
        raise ValueError(f"no observations for {flow_key}")
    return rows


def fetch_rates() -> dict:
    pr = _nb_last("IR/B.KPRA.SD.R")[-1]
    y10 = _nb_last("GOVT_GENERIC_RATES/B.10Y.GBON")[-1]
    return {"policy_rate": float(pr["OBS_VALUE"]), "policy_date": pr["TIME_PERIOD"], "gov10y": float(y10["OBS_VALUE"]),
            "gov10y_date": y10["TIME_PERIOD"], "source": "Norges Bank (NLOD), daily, not live"}


def fetch_fx() -> dict:
    rows = {r["BASE_CUR"]: r for r in _nb_last("EXR/B.USD+EUR.NOK.SP")}
    out = {"USDNOK": float(rows["USD"]["OBS_VALUE"]), "EURNOK": float(rows["EUR"]["OBS_VALUE"]),
           "date": rows["USD"]["TIME_PERIOD"], "source": "Norges Bank (NLOD), daily fixing ~16:00 CET, not live"}
    try:        # the import-weighted krone index (D63): one more series from the same open API; its failure never costs the rates above
        i44 = _nb_last("EXR/B.I44.NOK.SP")[-1]
        out["I44"], out["I44_date"] = float(i44["OBS_VALUE"]), i44["TIME_PERIOD"]
    except Exception as e:  # noqa: BLE001
        out["errors"] = [f"I44: {type(e).__name__}"]
    return out


SSB_SALMON = SSB_SALMON_URL = ("https://data.ssb.no/api/pxwebapi/v2/tables/03024/data?lang=en&outputFormat=csv"
              "&valueCodes%5BVareGrupper2%5D=01&valueCodes%5BContentsCode%5D=Kilopris&valueCodes%5BTid%5D=top(3)")


def fetch_salmon() -> dict:
    """SSB table 03024: export price of fresh farmed salmon, NOK/kg, weekly (an export price, not the spot price)."""
    rows = list(csv.reader(io.StringIO(_get(SSB_SALMON).decode("utf-8-sig"))))
    head, vals = rows[0], rows[1]
    weeks = [h.split()[-1] for h in head[1:]]  # "Kilopris 2026U42" -> "2026U42"
    last = weeks[-1]
    return {"value": float(vals[-1]), "date": f"week {int(last.split('U')[1])} {last.split('U')[0]}",
            "history": dict(zip(weeks, [float(v) for v in vals[1:]], strict=True)),
            "source": "SSB table 03024 (CC BY 4.0), weekly export price, published Wednesdays"}


def fetch_brent() -> dict:
    import yfinance as yf

    h = yf.Ticker("BZ=F").history(period="10d", interval="1d")["Close"].dropna()
    if h.empty:
        raise ValueError("Yahoo returned no BZ=F closes")
    return {"value": round(float(h.iloc[-1]), 2), "date": f"{h.index[-1]:%Y-%m-%d}", "delayed": True,
            "source": "Yahoo Finance BZ=F (Brent futures), daily close"}


# ------------------------------------------------------------------------------------------------ the macro feed (D65)
MACRO_NB = {"styringsrente": "IR/B.KPRA.SD.R", "stat3m": "GOVT_GENERIC_RATES/B.3M.TBIL", "stat10y": "GOVT_GENERIC_RATES/B.10Y.GBON",
            "usdnok": "EXR/B.USD.NOK.SP", "eurnok": "EXR/B.EUR.NOK.SP", "i44": "EXR/B.I44.NOK.SP"}
MACRO_YAHOO = {"brent": "BZ=F", "gass_ttf": "TTF=F", "aluminium": "ALI=F", "kobber": "HG=F", "us10y": "^TNX", "vix": "^VIX"}
MACRO_OBS = 800                      # a little over three years of business days: what the sensitivity needs
POWER_AREA, POWER_DAYS_PER_RUN, POWER_KEEP = "NO2", 14, 800


def _nb_history(flow_key: str, n: int = MACRO_OBS) -> dict:
    rows = list(csv.DictReader(io.StringIO(_get(f"{NORGES_BANK}/{flow_key}?format=csv&lastNObservations={n}&locale=en").decode("utf-8-sig")), delimiter=";"))
    pts = [(r["TIME_PERIOD"], float(r["OBS_VALUE"])) for r in rows if r.get("OBS_VALUE") not in (None, "")]
    if not pts:
        raise ValueError(f"no observations for {flow_key}")
    return {"t": [p[0] for p in pts], "v": [p[1] for p in pts]}


def _yahoo_histories(symbols: dict[str, str]) -> dict[str, dict]:
    import yfinance as yf

    df = yf.download(list(symbols.values()), period="3y", interval="1d", progress=False, auto_adjust=False)["Close"]
    out = {}
    for key, sym in symbols.items():
        s = df[sym].dropna() if sym in df else None
        if s is not None and len(s):
            out[key] = {"t": [f"{d:%Y-%m-%d}" for d in s.index], "v": [round(float(v), 4) for v in s.tolist()]}
    return out


def _salmon_history(weeks: int = 160) -> dict:
    """SSB table 03024, the weekly export price, dated on the Friday of its week."""
    from datetime import date as _date

    url = SSB_SALMON_URL.replace("top(3)", f"top({weeks})")
    rows = list(csv.reader(io.StringIO(_get(url).decode("utf-8-sig"))))
    head, vals = rows[0], rows[1]
    t, v = [], []
    for h, x in zip(head[1:], vals[1:], strict=True):
        label = h.split()[-1]                      # "2026U42"
        try:
            t.append(_date.fromisocalendar(int(label[:4]), int(label.split("U")[1]), 5).isoformat())
            v.append(float(x))
        except ValueError:
            continue
    if not t:
        raise ValueError("no salmon prices from SSB")
    return {"t": t, "v": v}


def _power_history(old: dict | None, today=None) -> dict:
    """The day-ahead price in one Norwegian price area as a daily mean in øre/kWh, built a few days at a time: one
    small request per day, at most fourteen a run, so the history grows without leaning on a free service."""
    today = today or datetime.now(UTC).date()
    have = dict(zip((old or {}).get("t", []), (old or {}).get("v", []), strict=False))
    want = [today - timedelta(days=i) for i in range(POWER_DAYS_PER_RUN) if f"{today - timedelta(days=i):%Y-%m-%d}" not in have]
    for d in want:
        try:
            hours = json.loads(_get(f"https://www.hvakosterstrommen.no/api/v1/prices/{d:%Y}/{d:%m-%d}_{POWER_AREA}.json", pauses=()))
        except Exception:  # noqa: BLE001, S112 – a day that is not published yet, or a hole: the next run asks again
            continue
        prices = [h["NOK_per_kWh"] for h in hours if h.get("NOK_per_kWh") is not None]
        if prices:
            have[f"{d:%Y-%m-%d}"] = round(100 * sum(prices) / len(prices), 2)
    if not have:
        raise ValueError("no power prices")
    days = sorted(have)[-POWER_KEEP:]
    return {"t": days, "v": [have[d] for d in days]}


# ------------------------------------------------------------------------------------------------ FRED (St. Louis Fed)
FRED = "https://api.stlouisfed.org/fred"
#: the notice the FRED API terms require wherever the data is shown
FRED_NOTICE = "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."
FRED_TERMS = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"
#: driver key -> FRED series id. Only series without a copyright line: the terms leave third-party data to its owner
#: («notes contain the word 'Copyright'»), and the fetch reads the notes every run, so a series that gains one is dropped.
MACRO_FRED = {"us2y": "DGS2", "fed": "DFEDTARU", "dollar": "DTWEXBGS"}       # ECBDFR is marked «Copyright» (ECB): not used
#: US releases that move rates, the krone and Oslo Børs, by FRED release id; the dates FRED publishes ahead are kept
FRED_RELEASES = {10: "KPI i USA", 50: "Sysselsetting i USA (Employment Situation)", 53: "BNP i USA"}
FRED_RELEASE_DAYS = 120


def fred_key() -> tuple[str | None, str]:
    """The owner's FRED key and its state: ``ok``, ``mangler`` or ``feil format``. Read from the environment variable
    FRED_API_KEY or from keys/fred.txt in the private home; never from the repository, never written anywhere."""
    import os
    import re

    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        p = jg.home() / "keys" / "fred.txt"
        try:
            key = p.read_text(encoding="utf-8-sig").strip() if p.exists() else ""
        except OSError:
            key = ""
    if not key:
        return None, "mangler"
    return (key, "ok") if re.fullmatch(r"[0-9A-Za-z]{32}", key) else (None, "feil format")


def _scrub(text: str, key: str | None) -> str:
    """A text that may end up in a feed, a log or a page, with the key taken out."""
    return str(text).replace(key, "<nøkkel>") if key else str(text)


def _fred(path: str, key: str, **params) -> dict:
    from urllib.parse import urlencode

    return json.loads(_get(f"{FRED}/{path}?{urlencode({**params, 'api_key': key, 'file_type': 'json'})}"))


def _fred_history(series_id: str, key: str, start: str) -> dict:
    meta = (_fred("series", key, series_id=series_id).get("seriess") or [{}])[0]
    if "copyright" in str(meta.get("notes", "")).lower():
        raise PermissionError(series_id)
    obs = _fred("series/observations", key, series_id=series_id, observation_start=start).get("observations") or []
    pts = [(o["date"], float(o["value"])) for o in obs if o.get("value") not in (None, "", ".")]
    if not pts:
        raise ValueError(f"no observations for {series_id}")
    return {"t": [p[0] for p in pts], "v": [p[1] for p in pts]}


def _fred_releases(key: str, today) -> list[dict]:
    """The coming release dates of the US numbers in FRED_RELEASES, from FRED's release calendar."""
    end = today + timedelta(days=FRED_RELEASE_DAYS)
    out = []
    for rid, what in FRED_RELEASES.items():
        doc = _fred("release/dates", key, release_id=rid, realtime_start=f"{today:%Y-%m-%d}", realtime_end="9999-12-31",
                    include_release_dates_with_no_data="true", sort_order="asc", limit=60)
        out += [{"date": r["date"], "release_id": rid, "what": what} for r in doc.get("release_dates") or []
                if f"{today:%Y-%m-%d}" <= r.get("date", "") <= f"{end:%Y-%m-%d}"]
    return sorted(out, key=lambda r: (r["date"], r["release_id"]))


def _fred_reason(e: Exception, key: str | None) -> tuple[str, bool]:
    """What went wrong, in words that carry no key, and whether FRED rejected the key itself."""
    import urllib.error

    if isinstance(e, PermissionError):
        return "opphavsrett i serienotatet – ikke brukt (FRED-vilkårene)", False
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            body = ""
        if e.code in (400, 401, 403) and "api_key" in body:
            return f"FRED avviste nøkkelen (HTTP {e.code})", True
        return f"HTTP {e.code}", False
    return _scrub(type(e).__name__, key), False


def _fetch_fred(today) -> tuple[dict, list[str], list[dict] | None, dict]:
    """FRED's part of the macro feed: the series in MACRO_FRED and the US release dates. Without a key nothing is asked
    and nothing is an error – the page says what a key would add. A rejected key stops at the first request."""
    key, state = fred_key()
    info = {"key": state, "series": [], "refused": []}
    if not key:
        return {}, [], None, info
    start = f"{today - timedelta(days=round(MACRO_OBS * 7 / 5) + 30):%Y-%m-%d}"
    got, errors = {}, []
    for k, sid in MACRO_FRED.items():
        try:
            got[k] = _fred_history(sid, key, start)
        except Exception as e:  # noqa: BLE001
            text, rejected = _fred_reason(e, key)
            if rejected:
                info["key"] = "avvist"
                return {}, [f"FRED: {text}"], None, info
            if isinstance(e, PermissionError):
                info["refused"].append(k)
            errors.append(f"{k}: {text}")
    releases = None
    try:
        releases = _fred_releases(key, today)
    except Exception as e:  # noqa: BLE001
        errors.append(f"FRED-kalender: {_fred_reason(e, key)[0]}")
    info["series"] = sorted(got)
    return got, [_scrub(x, key) for x in errors], releases, info


SSB_CALENDAR = "https://www.ssb.no/en/kommende-publiseringer"
#: the SSB statistics the macro calendar follows: short name on SSB's page -> what the dashboard calls it
SSB_STATS = {"kpi": "KPI (konsumprisindeksen)", "aku": "Arbeidsledighet (AKU)", "knr": "BNP (nasjonalregnskapet)",
             "doi": "Detaljomsetning (varehandelsindeksen)"}
_EN_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september",
                                           "october", "november", "december"), 1)}
_NO_MONTHS = ("januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "desember")


def ssb_period(text: str) -> str:
    """SSB's period line in Norwegian: «Figures for November 2026» -> «tall for november 2026», «Figures for 3rd quarter
    2026» -> «tall for 3. kvartal 2026». Anything else is kept as printed."""
    import re

    t = (text or "").strip()
    m = re.fullmatch(r"(?i)figures for (\w+) (\d{4})", t)
    if m and m.group(1).lower() in _EN_MONTHS:
        return f"tall for {_NO_MONTHS[_EN_MONTHS[m.group(1).lower()] - 1]} {m.group(2)}"
    m = re.fullmatch(r"(?i)figures for (\d)(?:st|nd|rd|th) quarter (\d{4})", t)
    if m:
        return f"tall for {m.group(1)}. kvartal {m.group(2)}"
    m = re.fullmatch(r"(?i)figures for (\d{4})", t)
    if m:
        return f"tall for {m.group(1)}"
    return t


def parse_ssb_calendar(page: str) -> list[dict]:
    """The coming releases of the statistics in SSB_STATS, from the JSON SSB embeds in its upcoming-releases page. The
    month number there is zero-based (11 = December). Raises ValueError when the page has no release data, so a
    changed page is an error on the data-health page and not an empty calendar."""
    import re

    dec, out, seen, found = json.JSONDecoder(), [], set(), False
    for m in re.finditer(r'\{"id":\s*\d+,\s*"name":', page or ""):
        try:
            obj, _ = dec.raw_decode(page, m.start())
        except ValueError:
            continue
        v = obj.get("variant") or {}
        if not isinstance(v, dict) or "monthNumber" not in v:
            continue
        found = True
        short = obj.get("shortName")
        if short not in SSB_STATS:
            continue
        try:
            day = datetime(int(v["year"]), int(v["monthNumber"]) + 1, int(v["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        key = (short, f"{day:%Y-%m-%d}", v.get("period"))
        if key in seen:
            continue
        seen.add(key)
        url = obj.get("statisticsPageUrl") or ""
        out.append({"date": f"{day:%Y-%m-%d}", "stat": short, "what": SSB_STATS[short], "period": ssb_period(v.get("period", "")),
                    "url": ("https://www.ssb.no" + url) if url.startswith("/") else (url or SSB_CALENDAR)})
    if not found:
        raise ValueError("SSB-siden hadde ingen publiseringsdata")
    return sorted(out, key=lambda r: (r["date"], r["stat"]))


def fetch_ssb_calendar() -> list[dict]:
    return parse_ssb_calendar(_get(SSB_CALENDAR).decode("utf-8", "replace"))


def fetch_macro() -> dict:
    """The history of every macro driver (dashboard/macro.py). A source that fails keeps its series from the cache and is
    named in ``errors``; the feed fails only when nothing at all could be fetched."""
    before = read("macro") or {}
    old = dict(before.get("series") or {})
    series, errors = {}, []
    fred_series, fred_errors, releases, fred_info = _fetch_fred(datetime.now(UTC).date())
    series.update(fred_series)
    errors += fred_errors
    for k in fred_info["refused"]:                    # a series with a copyright line is not kept from an earlier run either
        old.pop(k, None)
    for key, flow in MACRO_NB.items():
        try:
            series[key] = _nb_history(flow)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{key}: {type(e).__name__}")
    try:
        got = _yahoo_histories(MACRO_YAHOO)
        series.update(got)
        errors += [f"{k}: ingen data fra Yahoo" for k in MACRO_YAHOO if k not in got]
    except Exception as e:  # noqa: BLE001
        errors.append(f"Yahoo: {type(e).__name__}")
    for key, fn in (("laks", _salmon_history), ("kraft_no2", lambda: _power_history(old.get("kraft_no2")))):
        try:
            series[key] = fn()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{key}: {type(e).__name__}")
    ssb = None
    try:
        ssb = fetch_ssb_calendar()
    except Exception as e:  # noqa: BLE001
        errors.append(f"SSB-kalenderen: {type(e).__name__}")
    if not series:
        raise RuntimeError("; ".join(errors) or "no macro series")
    for key, s in old.items():                       # what could not be fetched now is kept as it was, and said to be old
        series.setdefault(key, s)
    uses_fred = any(k in series for k in MACRO_FRED)
    return {"series": series, "errors": errors, "fred": fred_info,
            "releases": releases if releases is not None else before.get("releases") or [],
            "ssb_releases": ssb if ssb is not None else before.get("ssb_releases") or [],
            "source": "Norges Bank (NLOD), Yahoo Finance (forsinket), SSB tabell 03024 og publiseringskalenderen (CC BY 4.0), hvakosterstrommen.no (ENTSO-E)"
                      + (", FRED (St. Louis Fed)" if uses_fred else "")}


RSS = (("E24", "https://e24.no/rss2/"), ("DN", "https://services.dn.no/api/feed/rss/"),
       ("Finansavisen", "https://ws.finansavisen.no/api/articles.rss"), ("NRK", "https://www.nrk.no/nyheter/siste.rss"))
NEWS_KEEP_DAYS = 14


def fetch_news() -> dict:
    """Headlines from the media RSS feeds: title, link, time and outlet only – the description and text are dropped.
    Merged with the cache (Finansavisen's feed holds only 10 items) and kept 14 days. A feed that fails is skipped
    and named in `errors`."""
    from email.utils import parsedate_to_datetime
    from xml.etree import ElementTree as ET

    items = {n["link"]: n for n in (read("news") or {}).get("items", [])}
    errors = []
    for outlet, url in RSS:
        try:
            root = ET.fromstring(_get(url))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{outlet}: {type(e).__name__}")
            continue
        for it in root.iter("item"):
            title, link, pub = it.findtext("title"), it.findtext("link"), it.findtext("pubDate")
            if not (title and link and pub):
                continue
            try:
                t = parsedate_to_datetime(pub).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (TypeError, ValueError):
                continue
            items[link] = {"title": title.strip(), "link": link.strip(), "time": t, "outlet": outlet}
    if len(errors) == len(RSS):
        raise RuntimeError("; ".join(errors))
    cutoff = f"{datetime.now(UTC) - timedelta(days=NEWS_KEEP_DAYS):%Y-%m-%d}"
    kept = sorted((n for n in items.values() if n["time"][:10] >= cutoff), key=lambda n: n["time"], reverse=True)
    return {"items": kept, "errors": errors, "source": "RSS: " + ", ".join(o for o, _ in RSS) + " (headlines and links only)"}
