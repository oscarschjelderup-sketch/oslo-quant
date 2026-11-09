"""The desk (DECISIONS D41): six roles go through a stock before Oscar judges it, each with one job and a fixed output,
hard hand-offs between them, a mandatory counter-argument, and a log of everything. Paper only, nothing trades, and the
chain never ends in a buy: it ends in **klar for vurdering** (the judgement form opens prefilled with the debate
attached), **parkert** (a bear reason the data could not rebut, or a Risk block) or **drept** (the filter's reason).

The structure is taken from a six-bot trading desk seen on social media – one job per role, hand-offs, an obligatory
bear, log all of it. The content is not: no memecoins, no intraday, no automatic orders, and no language model. Every
role is a set of rules over data the dashboard already holds – the store's prices, the signals with their measured odds,
NewsWeb announcements, primary-insider notifications, Finanstilsynet's short register, the report reader, the research
book and the judgement log, the toolkit model's reverse DCF, the light cases, the calibration page's error patterns.

A role never writes free text. Its output is a list of findings; a finding is a fixed claim (``CLAIMS``), a number, a
source and the time of the data, and is refused without them. Estimates are marked EST, cached and delayed data say so.

The roles, in order:

1. **Scout** – every stock in the store: volume against its 60-session average, the day's move against its sector
   group, a signal today, a new announcement, an insider notification, a move in the short register.
2. **Filter** – kills what does not fit the process: no case and not watched, turnover below the limit, a report inside
   ``report_within_days`` with the previous one not dealt with, a kill criterion already triggered, the price through
   the view's kill level.
3. **Analyst** – what the market prices in against the view (reverse DCF, light case, the toolkit report), the outcome
   odds at 3, 6 and 12 months, the latest report against the case, the distance to the target and the kill level.
4. **Bear** – at least ``MIN_BEAR_REASONS`` reasons against buying, each with a number and a source; fewer stop the chain.
5. **Reply** – every bear reason gets a rule-based rebuttal with numbers or stands; one that stands is a veto.
6. **Risk** – the position at the maximum loss with the kill level as the stop, the sector group's share of the paper
   sum after the buy, the dated events before the horizon; blocks over the limits in ``dashboard.yaml``.

Runs are written append-only under ``~/osloquant-home/desk/`` (private) and never to the research book or the
judgement log. The only statistic that decides whether the desk is worth anything is kept honestly: how often the
Bear's veto was followed by the price reaching the kill level before the target (``veto_stats``).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import market as mk
from osloquant.dashboard.dates import dato

# ------------------------------------------------------------------------------------------------ constants
ROLES = ("scout", "filter", "analyst", "bear", "reply", "risk", "desk")
OUTCOMES = ("killed", "parked", "ready")
OUTCOME_LABEL = {"killed": "drept", "parked": "parkert", "ready": "klar for vurdering"}
MIN_BEAR_REASONS = 3                   # fixed by the brief, not a config key
MAX_BEAR_REASONS = 8
DESK_DIR = "desk"
RUN_ID = re.compile(r"^\d{8}T\d{6}-(daily|manual)(-\d+)?$")
CONFIG_KEY = "desk"
DEFAULTS = {
    "volume_ratio": 2.0,               # Scout: today's volume / 60-session average
    "move_vs_sector": 0.03,            # Scout: |day's move − sector-group median|, fraction
    "min_turnover_nok": 2_000_000,     # Filter: median daily turnover over 20 sessions
    "report_within_days": 5,           # Filter: a report this close with the previous one not dealt with kills
    "max_group_share": 0.50,           # Risk: share of the paper sum in one sector group after the buy
    "veto_horizon_sessions": 60,       # veto statistics: window after the run
    "insider_days": 90,                # Bear: window for insider sells
    "short_min_pct": 0.5,              # Bear: a public short at or above this is a reason
}
PRICE_SRC = mk.PRICE_SOURCE
SIGNAL_SRC = "signalskanner (oq signals); odds målt 2010–2026 på dagens 64 aksjer (signal_odds.yaml)"

#: the fixed claims – a finding's claim is looked up here, never written by a role
CLAIMS = {
    # scout
    "vol": "Volum mot 60-dagers snitt",
    "move": "Kursbevegelse mot sektorgruppen (1 dag)",
    "signal": "Nytt signal i dag",
    "announcement": "Ny børsmelding",
    "insider": "Innsidehandel meldt",
    "short": "Endring i shortregisteret (7 d)",
    "quiet": "Ingenting uvanlig i dag",
    # filter
    "no_case": "Ingen case og ikke på overvåkning",
    "liquidity": "Omsetning under grensen",
    "report_unread": "Rapport innen få dager, forrige ikke behandlet",
    "kill_triggered": "Kill-kriterium allerede utløst i siste rapport",
    "kill_level_crossed": "Kursen er gjennom kill-nivået",
    "passed": "Passerer filteret",
    # analyst
    "implied_margin": "Markedet priser inn EBIT-margin (reverse DCF) mot mitt syn",
    "implied_growth": "Markedet priser inn omsetningsvekst (reverse DCF) mot mitt syn",
    "implied_light": "Hva kursen krever (lett case)",
    "report_tp": "Siste rapport (Toolkit) mot synet i boken",
    "odds_sim": "Utfallsodds, simulering: kursmål først / kill først / ingen",
    "odds_hist": "Utfallsodds, historiske tilfeller: kursmål først / kill først / ingen",
    "breakeven": "Reward/risk og break-even-andel",
    "report_kill": "Kill-kriterium i siste rapportlesing",
    "report_text_kill": "Kill-kriterier rapportleseren ikke kan sjekke",
    "report_vs_case": "Siste rapport (LTM) mot casens forutsetninger",
    "report_metric": "Nøkkeltall i siste rapport mot året før",
    "distance": "Avstand til kursmål og kill-nivå",
    "no_view": "Ingen vurdering med kursmål i boken",
    # bear (and reply, same keys)
    "bear_value": "Bear-caset i egen vurdering",
    "kill_nearer": "Kill-kriterium nærmere terskelen i siste rapport",
    "metric_down": "Nøkkeltall svakere enn året før",
    "sector": "Sektorrisiko i papirporteføljen",
    "pattern": "Mitt feilmønster fra kalibreringen",
    "risk_signal": "Risikosignal med målte odds",
    "short_pos": "Shortposisjon i registeret",
    "insider_sell": "Innsidesalg i vinduet",
    "implied": "Kursen krever mer enn dagens drift leverer (lett case)",
    "claude": "Claudes syn er lavere",
    "odds": "Oddsene favoriserer kill-nivået",
    "multiple": "Prises over sektorgruppen",
    "too_few": "Færre enn tre grunner med tall – prosessen stopper",
    # risk
    "size": "Posisjon ved maks tap, kill-nivå som stopp",
    "group_share": "Andel av papirsummen i samme sektorgruppe etter kjøp",
    "group_loss": "Tap ved kill i samme gruppe etter kjøp",
    "total_loss": "Samlet tap ved kill, alle åpne syn",
    "events": "Daterte hendelser før horisonten",
    "no_limits": "Ingen grenser i dashboard.yaml",
    "no_kill": "Ingen kill-nivå og ingen bear-verdi",
    # desk
    "killed": "Drept av filteret",
    "parked": "Parkert",
    "ready": "Klar for vurdering",
}
#: what the reply tests for each bear reason (the claim of the reply finding)
REPLIES = {
    "bear_value": "Forventet verdi med egne sannsynligheter mot kursen",
    "kill_nearer": "Avstand til terskelen",
    "metric_down": "LTM mot casens estimat for året",
    "sector": "Felles kill-driver med de åpne synene",
    "pattern": "Mønsteret mot situasjonen nå",
    "risk_signal": "Signalets 60-dagers intervall og grad",
    "short_pos": "Shortens retning siste 30 dager",
    "insider_sell": "Innsidekjøp mot innsidesalg i vinduet",
    "implied": "Casemodellens reverse DCF mot den lette casen",
    "claude": "Claudes syn mot siste rapport",
    "odds": "Kursmål-først-andel mot break-even",
    "multiple": "DCF-verdi i casemodellen mot kursen",
}
BEAR_RANK = {"kill_nearer": 0, "metric_down": 1, "claude": 2, "implied": 3, "multiple": 3, "odds": 4, "risk_signal": 5, "short_pos": 5,
             "insider_sell": 5, "sector": 6, "pattern": 6, "bear_value": 8}
_DIGIT = re.compile(r"\d")


# ------------------------------------------------------------------------------------------------ data model
@dataclass
class Finding:
    """One structured point: a fixed claim (by ``kind``), a number, a source and the time of the data. Refused without
    them – no role writes free text. ``detail`` carries a quotation from a source (a criterion, a title), never prose."""

    role: str
    kind: str
    value: str
    source: str
    asof: str
    t: str = ""
    status: str | None = None          # filter: killed · bear: rebutted / stands · reply: rebuts / stands · risk: blocked
    ref: int | None = None             # a reply points at the index of the bear finding it answers
    est: bool = False
    delayed: bool = False
    detail: str = ""

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")
        if self.kind not in CLAIMS:
            raise ValueError(f"unknown claim {self.kind!r}: a role may only make the claims in CLAIMS")
        for k in ("value", "source", "asof"):
            if not str(getattr(self, k) or "").strip():
                raise ValueError(f"a finding needs a {k} ({self.role}/{self.kind})")
        if not _DIGIT.search(self.value):
            raise ValueError(f"a finding's value must carry a number ({self.role}/{self.kind}: {self.value!r})")

    @property
    def claim(self) -> str:
        return REPLIES[self.kind] if self.role == "reply" else CLAIMS[self.kind]


@dataclass
class StockRun:
    code: str
    name: str
    group: str
    price: float | None
    price_date: str | None
    target: float | None
    kill: float | None
    kill_source: str | None
    findings: list[Finding] = field(default_factory=list)
    outcome: str | None = None
    reason: str = ""                   # the deciding finding, as "claim: value"
    stage: str = "scout"
    veto: int | None = None            # index of the standing bear finding
    prefill: dict | None = None        # the judgement form's fields when ready

    def by_role(self, role: str) -> list[Finding]:
        return [f for f in self.findings if f.role == role]


@dataclass
class DeskRun:
    run_id: str
    session: str
    trigger: str
    started_at: str
    finished_at: str = ""
    scanned: int = 0
    flagged: int = 0
    killed: int = 0
    debated: int = 0
    parked: int = 0
    ready: int = 0
    data_quality: list[dict] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    stocks: list[StockRun] = field(default_factory=list)

    def stock(self, code: str) -> StockRun | None:
        return next((s for s in self.stocks if s.code == code), None)


# ------------------------------------------------------------------------------------------------ config and storage
def config() -> dict:
    """The desk's limits: ``DEFAULTS`` overridden by the ``desk:`` section of ~/osloquant-home/dashboard.yaml."""
    p = jg.home() / "dashboard.yaml"
    user = {}
    if p.exists():
        user = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get(CONFIG_KEY) or {}
    return {**DEFAULTS, **{k: v for k, v in user.items() if k in DEFAULTS}}


def desk_dir() -> Path:
    d = jg.home() / DESK_DIR
    (d / "runs").mkdir(parents=True, exist_ok=True)
    return d


def run_path(run_id: str) -> Path:
    if not RUN_ID.match(run_id):
        raise ValueError(f"not a run id: {run_id!r}")
    return desk_dir() / "runs" / f"{run_id}.json"


def save(run: DeskRun) -> Path:
    """Write the run as its own file and one index line; an existing run file is never overwritten."""
    p = run_path(run.run_id)
    if p.exists():
        raise FileExistsError(f"run {run.run_id} already exists; runs are append-only")
    p.write_text(json.dumps(asdict(run), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    line = {"run_id": run.run_id, "session": run.session, "trigger": run.trigger, "finished_at": run.finished_at,
            "scanned": run.scanned, "flagged": run.flagged, "killed": run.killed, "debated": run.debated, "parked": run.parked, "ready": run.ready,
            "stocks": {s.code: {"outcome": s.outcome, "reason": s.reason[:160], "price": s.price, "target": s.target, "kill": s.kill,
                                "veto_kind": s.findings[s.veto].kind if s.veto is not None else None} for s in run.stocks}}
    with (desk_dir() / "index.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return p


def index() -> list[dict]:
    p = desk_dir() / "index.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_run(run_id: str) -> DeskRun | None:
    try:
        p = run_path(run_id)
    except ValueError:
        return None
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    stocks = [StockRun(**{**s, "findings": [Finding(**f) for f in s["findings"]]}) for s in d.pop("stocks")]
    return DeskRun(**d, stocks=stocks)


def latest(session: str | None = None, trigger: str | None = None) -> dict | None:
    """The newest index line, optionally for one session (the newest close) or one trigger."""
    rows = [r for r in index() if (session is None or r["session"] == session) and (trigger is None or r["trigger"] == trigger)]
    return rows[-1] if rows else None


def runs_for(code: str) -> list[dict]:
    """Every run that went through ``code``, newest first, with its outcome."""
    out = []
    for r in index():
        s = r["stocks"].get(code)
        if s:
            out.append({"run_id": r["run_id"], "session": r["session"], "trigger": r["trigger"], "finished_at": r["finished_at"], **s})
    return out[::-1]


# ------------------------------------------------------------------------------------------------ the inputs
class Inputs:
    """Everything a run reads, read once. Pages and roles never touch the network."""

    def __init__(self, snap: mk.Snapshot | None = None, today: pd.Timestamp | None = None, now: datetime | None = None):
        from osloquant.dashboard import calendar as cal
        from osloquant.dashboard import coverage as cv
        from osloquant.dashboard import feeds as fd
        from osloquant.dashboard import insiders as ins
        from osloquant.dashboard import sizing
        from osloquant.dashboard import today as td

        self.snap = snap or mk.snapshot()
        self.today = (today or pd.Timestamp.now()).normalize()
        self.now = now or datetime.now(UTC)
        self.session = f"{self.snap.asof:%Y-%m-%d}"
        self.cfg = config()
        self.sizing = sizing.config()
        self.cases = bk.cases()
        self.by_code = {c.code: c for c in self.cases}
        self.watchlist = bk.watchlist()
        self.watched = {w["code"] for w in self.watchlist if not w.get("moved_to_book")}
        self.rows = jg.read_log()
        self.groups = {c: self.snap.group(c) for c in self.snap.names}
        for c in self.by_code:
            self.groups.setdefault(c, self.snap.group(c))
        self.levels = {r["code"]: r["level"] for r in cv.universe(self.snap, self.cases, self.watchlist, self.today)}
        self.alerts, _ = td.signals_since(self.snap, None, max_sessions=10)
        self.alerts_today = [a for a in self.alerts if a.session == self.session]
        codes = set(self.snap.names) | set(self.by_code) | self.watched
        doc = fd.read("announcements")            # filtered on the session's date, not the wall clock, so a run reproduces
        since = f"{self.snap.asof - pd.Timedelta(days=5):%Y-%m-%d}"
        self.announcements = ({"items": sorted((a for a in doc.get("items", []) if a["code"] in codes and a["time"][:10] >= since), key=lambda a: a["time"], reverse=True),
                               "source": f"{doc.get('source', '')}; {fd._age(doc)}"} if doc else None)
        self.insiders = ins.load()
        self.insider_doc_age = fd._age(self.insiders) if self.insiders.get("fetched_at") else "never fetched"
        self.shorts_doc = fd.read("shorts") or {}
        self.events = cal.events(self.cases, self.watchlist, today=self.today, days=400)
        self.odds_file = sg.load_odds().get("signals", {})
        C = self.snap.panel["close"]
        self._d1 = (C.iloc[-1] / C.iloc[-2] - 1) if len(C) > 1 else pd.Series(dtype=float)
        self.group_median = {g: float(np.nanmedian([self._d1[c] for c in C.columns if self.groups.get(c) == g and c in self._d1.index and np.isfinite(self._d1[c])] or [np.nan]))
                             for g in set(self.groups.values())}
        self._patterns: dict | None = None
        self.data_quality = self._quality()

    def _quality(self) -> list[dict]:
        from osloquant.dashboard import feeds as fd

        out = []
        expected = self.today - pd.Timedelta(days=1)
        while expected.weekday() >= 5:
            expected -= pd.Timedelta(days=1)
        stale = self.snap.asof.normalize() < expected
        C = self.snap.panel["close"]
        missing = int(C.iloc[-1].isna().sum()) if len(C) else 0
        out.append({"what": "kurser (lageret, Yahoo, forsinket)", "asof": self.session, "ok": not stale,
                    "note": ("eldre enn siste virkedag – kjør oq record" if stale else "") + (f"; {missing} aksjer uten sluttkurs på {self.session}" if missing else "")})
        for name, label in (("announcements", "børsmeldinger (NewsWeb)"), ("insiders", "innsidehandler (NewsWeb 1102)"),
                            ("shorts", "shortregisteret (Finanstilsynet)"), ("calendar", "finanskalendere (NewsWeb)")):
            doc = fd.read(name)
            age = fd._age(doc) if doc else "ikke hentet"
            ok = bool(doc and doc.get("fetched_at") and (self.now - datetime.fromisoformat(doc["fetched_at"].replace("Z", "+00:00"))).days <= 3)
            out.append({"what": label, "asof": (doc or {}).get("fetched_at", "–"), "ok": ok, "note": age})
        out.append({"what": "grenser (dashboard.yaml: sizing + desk)", "asof": "–", "ok": bool(self.sizing),
                    "note": "ingen sizing-grenser: Risk kan ikke sette størrelse" if not self.sizing else f"maks tap NOK {float(self.sizing['max_loss']):,.0f}".replace(",", " ")})
        return out

    def patterns(self) -> dict | None:
        """The calibration page's error patterns (learn.error_patterns), computed once; None when it cannot be."""
        if self._patterns is None:
            from osloquant.dashboard import learn

            try:
                table, _ = jg.calibration(self.rows)
                if len(table):
                    prices = jg.load_prices(start=min(pd.Timestamp(j["date"]) for j in jg.judgements(self.rows)) - pd.Timedelta(days=10))
                    self._patterns = learn.error_patterns(self.rows, table, prices)
                else:
                    self._patterns = {"rows": [], "counts": {}, "n": 0, "n_wrong": 0}
            except Exception as e:  # noqa: BLE001 – the desk must not die with the calibration
                self._patterns = {"rows": [], "counts": {}, "n": 0, "n_wrong": 0, "error": f"{type(e).__name__}: {e}"}
        return self._patterns

    def last_price(self, code: str):
        return mk.last_price(self.snap, code)

    def stamp(self) -> str:
        return self.now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _nok(x) -> str:
    return f"{float(x):,.0f}".replace(",", " ")


def _insider_items(inp: Inputs, code: str) -> list[dict]:
    """The cached notifications for one stock that carry a code and a time (a malformed cache entry is skipped)."""
    return [i for i in inp.insiders.get("items", {}).values() if isinstance(i, dict) and i.get("code") == code and isinstance(i.get("time"), str) and len(i["time"]) >= 10]


def _pct(x, d=1, sign=True) -> str:
    return f"{x * 100:{'+' if sign else ''}.{d}f} %"


# ------------------------------------------------------------------------------------------------ 1. scout
def scout(inp: Inputs, code: str, forced: bool = False) -> list[Finding]:
    """What is unusual about ``code`` today, each with the number. ``forced`` (a manual run): a stock with nothing
    unusual still reports its numbers under "Ingenting uvanlig"."""
    from osloquant.dashboard import insiders as ins

    cfg, t = inp.cfg, inp.stamp()
    C, V = inp.snap.panel["close"], inp.snap.panel["volume"]
    out: list[Finding] = []
    if code not in C.columns:
        return out
    c = C[code].dropna()
    if c.empty or c.index[-1] != inp.snap.asof:
        return out                                   # no close on the newest session: nothing to compare
    v = V[code].reindex(c.index)
    vol_ratio = None
    if len(v) > 21 and np.isfinite(v.iloc[-1]):
        avg = float(v.iloc[-61:-1].mean())
        vol_ratio = float(v.iloc[-1]) / avg if avg and avg > 0 else None
    d1 = float(c.iloc[-1] / c.iloc[-2] - 1) if len(c) > 1 else None
    med = inp.group_median.get(inp.groups.get(code, "Other"))
    excess = d1 - med if d1 is not None and med is not None and np.isfinite(med) else None
    if vol_ratio is not None and vol_ratio >= cfg["volume_ratio"]:
        out.append(Finding("scout", "vol", f"{vol_ratio:.1f}x (i dag {_nok(v.iloc[-1])}, snitt 60 økter {_nok(v.iloc[-61:-1].mean())})", PRICE_SRC, inp.session, t, delayed=True))
    if excess is not None and abs(excess) >= cfg["move_vs_sector"]:
        out.append(Finding("scout", "move", f"{_pct(d1)} mot {inp.groups.get(code, 'Other')} median {_pct(med)} ({excess * 100:+.1f} pp)", PRICE_SRC, inp.session, t, delayed=True))
    for a in inp.alerts_today:
        if a.code == code:
            o = inp.odds_file.get(a.signal, {})
            odds = (f"meravkastning {_pct(o['exc20'])} / {_pct(o['exc60'])} (20/60 d), treff {o['hit20'] * 100:.0f} %, n {int(o.get('events') or 0)}"
                    if o.get("exc20") is not None else "0 målte odds")
            out.append(Finding("scout", "signal", f"{a.signal} ({a.kind}): {a.detail}; {odds}", SIGNAL_SRC, a.session, t, delayed=True, detail=a.signal))
    prev = c.index[-2] if len(c) > 1 else c.index[-1]
    ann = inp.announcements
    if ann:
        items = [x for x in ann["items"] if x["code"] == code and x["time"][:10] > f"{prev:%Y-%m-%d}"]
        if items:
            a0 = items[0]
            out.append(Finding("scout", "announcement", f"{len(items)} melding(er) siden {dato(prev, False)}; siste «{a0['title'][:90]}» ({a0.get('category') or 'ukjent kategori'})",
                               f"NewsWeb (buffer; {ann['source']})", a0["time"], t, delayed=True, detail=a0["title"]))
    cutoff = f"{inp.snap.asof - pd.Timedelta(days=3):%Y-%m-%d}"
    mine = sorted((i for i in _insider_items(inp, code) if i["time"][:10] >= cutoff and i.get("side") in ("buy", "sell", "subscription")),
                  key=lambda i: i["time"], reverse=True)
    if mine:
        i0 = mine[0]
        out.append(Finding("scout", "insider", f"{len(mine)} melding(er) siste 3 d; siste {i0['side']} ({i0.get('why', '?')}): «{str(i0.get('title', ''))[:80]}»",
                           f"NewsWeb kategori 1102 (buffer, {inp.insider_doc_age})", i0["time"], t, delayed=True, detail=str(i0.get("title", ""))))
    s = ins.shorts(code, inp.shorts_doc)
    if s:
        ch = ins.short_change(s, 7)
        if ch is not None and abs(ch) >= 0.25:
            out.append(Finding("scout", "short", f"{ch:+.2f} pp til {s['now']:.2f} % av aksjene ({s['date']})",
                               f"Finanstilsynets shortregister (buffer hentet {str(s.get('fetched_at'))[:10]})", s["date"] or inp.session, t, delayed=True))
    if not out and forced:
        out.append(Finding("scout", "quiet", f"volum {vol_ratio:.1f}x 60-dagers snitt; dag {_pct(d1) if d1 is not None else '–'} mot sektor {_pct(med) if med is not None and np.isfinite(med) else '–'}"
                           if vol_ratio is not None else f"{len(c)} økter; dag {_pct(d1) if d1 is not None else '0 %'}", PRICE_SRC, inp.session, t, delayed=True))
    return out


# ------------------------------------------------------------------------------------------------ 2. filter
def _next_report(inp: Inputs, code: str) -> dict | None:
    from osloquant.dashboard.today import _REPORT_WORDS

    for e in inp.events:
        if e.get("code") == code and e["date"] >= inp.today and (e["kind"] == "report" or any(w in str(e["what"]).lower() for w in _REPORT_WORDS)):
            return e
    return None


def filter_role(inp: Inputs, code: str) -> list[Finding]:
    """Kills what does not fit the process; every kill names its rule and number. Empty of kills = "passed"."""
    from osloquant.dashboard import coverage as cv
    from osloquant.dashboard import today as td

    cfg, t = inp.cfg, inp.stamp()
    c = inp.by_code.get(code)
    v = (c.view if c else None) or {}
    out: list[Finding] = []
    level = inp.levels.get(code, "none")
    has_case = bool(c and (c.view or c.claude_view or c.history))            # a logged view is a case even without a light case or a model
    if level == "none" and not has_case:
        out.append(Finding("filter", "no_case", f"dekning: {cv.LEVEL_LABEL[level]} (0 vurderinger i boken, 0 lett case, ikke på overvåkning)",
                           "dekningsnivået lest av filene: researchbook.yaml, judgements.jsonl, cases/, watchlist.yaml", inp.session, t, status="killed"))
    C, V = inp.snap.panel["close"], inp.snap.panel["volume"]
    turnover = None
    if code in C.columns:
        tv = (C[code] * V[code]).dropna().iloc[-20:]
        turnover = float(tv.median()) if len(tv) and np.isfinite(tv.median()) else None
    if turnover is not None and turnover < float(cfg["min_turnover_nok"]):
        out.append(Finding("filter", "liquidity", f"median omsetning 20 økter NOK {_nok(turnover)} < grense NOK {_nok(cfg['min_turnover_nok'])}",
                           PRICE_SRC + " (sluttkurs × volum)", inp.session, t, status="killed", delayed=True))
    nxt = _next_report(inp, code)
    if nxt and (nxt["date"] - inp.today).days <= int(cfg["report_within_days"]) and c:
        prev = td.last_report(c, inp.today, days=400)
        if prev:
            d, what = prev
            done = [r for r in c.history if r["kind"] in ("judgement", "kill_check") and str(r.get("date", ""))[:10] >= f"{d:%Y-%m-%d}"]
            if not done:
                out.append(Finding("filter", "report_unread", f"rapport {dato(nxt['date'], False)} om {(nxt['date'] - inp.today).days} d; forrige ({dato(d, False)}: {what[:40]}) har 0 vurderinger/kill-sjekker etter seg",
                                   f"{nxt['source']}; vurderingsloggen", f"{nxt['date']:%Y-%m-%d}", t, status="killed", detail=str(nxt["what"])))
    for hit in bk.triggered_now(code) if c else []:
        out.append(Finding("filter", "kill_triggered", hit if _DIGIT.search(hit) else f"{hit} (1 kriterium utløst)", "rapportleseren (siste rapportlesing)", inp.session, t,
                           status="killed", detail=hit))
    lp = inp.last_price(code)
    kl = v.get("kill_level")
    if lp and kl and v.get("rating") == "BUY" and lp[0] <= float(kl):
        out.append(Finding("filter", "kill_level_crossed", f"kurs {lp[0]:.2f} ≤ kill-nivå {float(kl):g} ({_pct(lp[0] / float(kl) - 1)})", f"vurdering {v.get('date')}; {PRICE_SRC}",
                           inp.session, t, status="killed", delayed=True))
    if not out:
        cover = cv.LEVEL_LABEL[level] if level != "none" else "vurdering i boken uten lett case"
        to = f"omsetning NOK {_nok(turnover)}/dag (median 20 økter)" if turnover is not None else "omsetning ukjent (0 volumdata i lageret)"
        out.append(Finding("filter", "passed", f"dekning: {cover}; {to}; 0 utløste kriterier", "dekningsnivå, lageret, rapportleseren", inp.session, t))
    return out


# ------------------------------------------------------------------------------------------------ 3. analyst
class Ctx:
    """What the analyst found, kept for the bear, the reply and risk."""

    def __init__(self):
        self.rdcf = None
        self.lc = None
        self.rep = None            # reader summary
        self.pub = None            # published toolkit report (reportpdf)
        self.odds = None
        self.breakeven = None
        self.px = None
        self.kill = None
        self.kill_source = None
        self.view: dict = {}
        self.case = None


def analyst(inp: Inputs, code: str, ctx: Ctx) -> list[Finding]:
    from osloquant.dashboard import lightcase as lcm
    from osloquant.dashboard import odds as od
    from osloquant.dashboard import reportpdf as rpdf
    from osloquant.dashboard import reports as rp
    from osloquant.dashboard.casefile import reverse_dcf

    t = inp.stamp()
    c = inp.by_code.get(code)
    v = (c.view if c else None) or {}
    ctx.case, ctx.view = c, v
    lp = inp.last_price(code)
    px = lp[0] if lp else None
    ctx.px = px
    out: list[Finding] = []
    if c and c.model:
        try:
            ctx.rdcf = reverse_dcf(c.model)
        except Exception as e:  # noqa: BLE001 – a broken workbook is reported, not fatal
            ctx.rdcf = {"error": f"{type(e).__name__}: {e}"}
    rd = ctx.rdcf if ctx.rdcf and not ctx.rdcf.get("error") else None
    if rd:
        src = f"casemodellen {rd.get('file')} (modelldato {str(rd.get('model_date'))[:10]}; kurs {rd.get('price')} per {str(rd.get('price_date'))[:10]}; Toolkit, privat)"
        if rd.get("rd_m_last") is not None:
            out.append(Finding("analyst", "implied_margin", f"markedet {_pct(rd['rd_m_last'], 1, False)} · mitt {_pct(rd['rd_m_last_ours'], 1, False) if rd.get('rd_m_last_ours') is not None else '–'}"
                               f" · siste faktiske {_pct(rd['rd_m_last_ref'], 1, False) if rd.get('rd_m_last_ref') is not None else '–'}", src, str(rd.get("model_date"))[:10], t, est=True))
        if rd.get("rd_cagr") is not None:
            out.append(Finding("analyst", "implied_growth", f"markedet {_pct(rd['rd_cagr'], 1, False)}/år · mitt {_pct(rd['rd_cagr_ours'], 1, False) if rd.get('rd_cagr_ours') is not None else '–'}"
                               f" · historikk {_pct(rd['rd_cagr_ref'], 1, False) if rd.get('rd_cagr_ref') is not None else '–'}", src, str(rd.get("model_date"))[:10], t, est=True))
    ctx.lc = lcm.load(code)
    if ctx.lc:
        rv = ctx.lc.get("reverse") or {}
        built = str(ctx.lc.get("built_at", ""))[:10]
        if ctx.lc.get("financial"):
            if rv.get("implied_roe") is not None:
                out.append(Finding("analyst", "implied_light", f"kursen betaler for ROE {_pct(rv['implied_roe'], 1, False)} for alltid (COE EST {_pct(rv.get('coe_est', 0), 0, False)}); har {_pct(rv.get('actual_roe') or 0, 0, False)}",
                                   f"lett case bygget {built} (Yahoo-regnskap; COE og vekst EST)", built, t, est=True, detail=str(rv.get("reads") or "")))
        elif rv.get("implied_g") is not None or rv.get("ev_vs_no_growth") is not None:
            g, vs = rv.get("implied_g"), rv.get("ev_vs_no_growth")
            out.append(Finding("analyst", "implied_light", f"evig vekst {_pct(g) + '/år' if g is not None else 'ikke løsbar (0)'} ved WACC EST {_pct(rv.get('wacc_est', 0), 1, False)}, "
                               f"ROIC {_pct(rv.get('roic') or 0, 0, False)}; EV {_pct(vs, 0) if vs is not None else '–'} mot null-vekst",
                               f"lett case bygget {built} (Yahoo-regnskap; WACC og vekst EST)", built, t, est=True, detail=str(rv.get("reads") or "")))
    ctx.pub = rpdf.latest(code)
    if ctx.pub and ctx.pub.get("tp") is not None:
        p = ctx.pub
        out.append(Finding("analyst", "report_tp", f"rapport {p['date']}: {p.get('rating') or '–'} TP {float(p['tp']):g}" + (f", DCF {float(p['dcf']):.1f}" if p.get("dcf") is not None else "")
                           + f"; boken: {v.get('rating') or 'ingen'} TP {float(v['target']):g}" if v.get("target") else f"rapport {p['date']}: {p.get('rating') or '–'} TP {float(p['tp']):g}; boken: 0 kursmål",
                           f"{p['file']} + estimates_{p['date']}.json (Toolkit, privat)", p["date"], t, est=True))
    if v.get("target") and px:
        kill, why = od.kill_level(v)
        ctx.kill, ctx.kill_source = kill, why
        if kill:
            try:
                ctx.odds = od.case_odds(code, float(v["target"]), kill, why)
            except Exception as e:  # noqa: BLE001 – odds need the long store; without it the analyst says so
                ctx.odds = None
                inp.data_quality.append({"what": f"utfallsodds {code}", "asof": inp.session, "ok": False, "note": f"{type(e).__name__}: {e}"})
        o = ctx.odds
        if o and not o.note:
            cell = lambda x: f"{x.target * 100:.0f}/{x.kill * 100:.0f}/{x.neither * 100:.0f}" if x and x.target == x.target else "–"  # noqa: E731
            src = f"odds.py: lagerets sluttkurser siden 2010 (Yahoo, forsinket), per {o.asof:%Y-%m-%d}; kill-nivå = {why}"
            out.append(Finding("analyst", "odds_sim", " · ".join(f"{lab} {cell(o.simulation.get(lab))}" for lab, _ in od.HORIZONS) + f" ({od.PATHS} baner, blokk {od.BLOCK} økter)", src, f"{o.asof:%Y-%m-%d}", t, delayed=True))
            out.append(Finding("analyst", "odds_hist", " · ".join(f"{lab} {cell(o.universe.get(lab))} (n {o.universe[lab].n})" for lab, _ in od.HORIZONS if lab in o.universe) + "; alle aksjer, like avstander i volatilitet",
                               src, f"{o.asof:%Y-%m-%d}", t, delayed=True))
            r_, be = od.breakeven(o.price, o.target, o.kill)
            ctx.breakeven = (r_, be)
            dec = decided_share(o.simulation.get("12 mnd"))
            out.append(Finding("analyst", "breakeven", f"R {r_:.2f}; kursmålet må nås først i minst {be * 100:.0f} % av de avgjorte tilfellene; simuleringen 12 mnd: "
                               + (f"{dec * 100:.0f} % av {o.simulation['12 mnd'].target * 100 + o.simulation['12 mnd'].kill * 100:.0f} % avgjorte" if dec is not None else "0 % avgjorte (ingen av nivåene nås)"),
                               src, f"{o.asof:%Y-%m-%d}", t))
        elif o and o.note:
            out.append(Finding("analyst", "odds_sim", f"ikke beregnet: {o.note} (0 baner)", "odds.py", inp.session, t))
    ctx.rep = rp.latest(code) if c else None
    s = ctx.rep
    if s:
        src = f"rapportleseren, Q{s.get('quarter')} {s.get('year')} ({str(s.get('published', ''))[:10]}; {s.get('pdf', '')})"
        texts = []
        for k in s.get("kill", []):
            now_, thr = k.get("now"), k.get("threshold")
            if k.get("metric") is None:
                texts.append(str(k.get("criterion", "")))
                continue
            val = (f"{k.get('status', '?')}: nå {now_:.4g} mot {k.get('op', '')} {thr:.4g}" if isinstance(now_, (int, float)) and isinstance(thr, (int, float))
                   else f"{k.get('status', '?')}; terskel {k.get('op', '')} {thr if thr is not None else 0}")
            out.append(Finding("analyst", "report_kill", val, src, str(s.get("published", ""))[:10], t, detail=str(k.get("criterion", ""))))
        if texts:
            out.append(Finding("analyst", "report_text_kill", f"{len(texts)} kriterier må leses manuelt", src, str(s.get("published", ""))[:10], t, detail=" | ".join(texts)))
        case_v = s.get("case") or {}
        m = s.get("metrics") or {}
        for key in ("revenue", "ebitda_pre16", "ebit_pre16", "ebitda", "ebit"):
            ltm = (m.get(f"{key}_ltm") or {}).get("value")
            est = case_v.get(key)
            if ltm is not None and est:
                out.append(Finding("analyst", "report_vs_case", f"{key}: LTM {_nok(ltm)} mot casens {s.get('year')}-estimat {_nok(est)} ({_pct(ltm / est - 1)})", src + f"; {case_v.get('_file', 'casemodellen')}",
                                   str(s.get("published", ""))[:10], t, est=True))
        yoy = [(k, d["value"]) for k, d in m.items() if k.endswith("_yoy") and isinstance(d.get("value"), (int, float))]
        if yoy:
            out.append(Finding("analyst", "report_metric", "; ".join(f"{k[:-4]} {_pct(val)} å/å" for k, val in yoy[:6]), src, str(s.get("published", ""))[:10], t))
    if v.get("target") and px:
        tp = float(v["target"])
        kill_txt = f"kill-nivå {ctx.kill:g} ({_pct(ctx.kill / px - 1)}; {ctx.kill_source})" if ctx.kill else "0 kill-nivå/bear-verdi"
        out.append(Finding("analyst", "distance", f"kursmål {tp:g} ({_pct(tp / px - 1)}); {kill_txt}; kurs {px:.2f} ({_pct(px / float(v['price']) - 1) if v.get('price') else '–'} siden synet)",
                           f"vurdering {v.get('date')} ({c.view_source if c else '–'}); {PRICE_SRC}", inp.session, t, delayed=True))
    else:
        n = sum(1 for r in inp.rows if r.get("code") == code and r["kind"] == "judgement")
        out.append(Finding("analyst", "no_view", f"{n} vurderinger logget på {code}; 0 kursmål i boken" + (f"; kurs {px:.2f}" if px else ""), "vurderingsloggen og research book", inp.session, t))
    return out


def decided_share(o) -> float | None:
    """The target's share of the decided simulated paths (target or kill reached), the number break-even is about."""
    if o is None or o.target != o.target or (o.target + o.kill) <= 0:
        return None
    return o.target / (o.target + o.kill)


# ------------------------------------------------------------------------------------------------ 4. bear
def bear(inp: Inputs, code: str, ctx: Ctx) -> list[Finding]:
    """Reasons against buying, each with a number and a source, strongest first, at most ``MAX_BEAR_REASONS`` and
    one per kind. Fewer than ``MIN_BEAR_REASONS`` ends in a single ``too_few`` finding."""
    from osloquant.dashboard import insiders as ins
    from osloquant.dashboard import learn
    from osloquant.dashboard import portfolio as pf

    t, cfg = inp.stamp(), inp.cfg
    c, v, px = ctx.case, ctx.view, ctx.px
    out: list[Finding] = []
    s = ctx.rep
    if s:
        src = f"rapportleseren, Q{s.get('quarter')} {s.get('year')} ({str(s.get('published', ''))[:10]})"
        hot = [k for k in s.get("kill", []) if str(k.get("status", "")).startswith(("triggered", "intact, nearer")) and isinstance(k.get("now"), (int, float)) and isinstance(k.get("threshold"), (int, float))]
        if hot:
            k = sorted(hot, key=lambda k: 0 if str(k["status"]).startswith("triggered") else 1)[0]
            out.append(Finding("bear", "kill_nearer", f"{k['status']}: nå {k['now']:.4g} mot {k.get('op', '')} {k['threshold']:.4g} (avstand {abs(k['now'] - k['threshold']):.4g})", src,
                               str(s.get("published", ""))[:10], t, detail=str(k.get("criterion", ""))))
        down = [(k, d["value"], d.get("how", "")) for k, d in (s.get("metrics") or {}).items() if k.endswith("_yoy") and isinstance(d.get("value"), (int, float)) and d["value"] < 0]
        if down:
            k, val, how = sorted(down, key=lambda x: x[1])[0]
            out.append(Finding("bear", "metric_down", f"{k[:-4]} {_pct(val)} mot samme kvartal året før ({how})", src, str(s.get("published", ""))[:10], t, detail=k[:-4]))
    cv = (c.claude_view if c else None) or {}
    if cv.get("target") and px and v.get("target") and (float(cv["target"]) < float(v["target"]) or (cv.get("rating") in ("SELL", "HOLD") and v.get("rating") == "BUY")):
        out.append(Finding("bear", "claude", f"Claude {cv.get('rating')} TP {float(cv['target']):g} ({_pct(float(cv['target']) / px - 1)}) {cv.get('date')}; boken {v.get('rating')} TP {float(v['target']):g}",
                           "vurderingsloggen (analyst: claude)", str(cv.get("date")), t, est=True, detail=str(cv.get("thesis") or "")[:220]))
    lc = ctx.lc
    if lc and not lc.get("financial"):
        rv = lc.get("reverse") or {}
        roic, wacc, g, vs = rv.get("roic"), rv.get("wacc_est"), rv.get("implied_g"), rv.get("ev_vs_no_growth")
        built = str(lc.get("built_at", ""))[:10]
        if roic is not None and wacc and roic < wacc:
            out.append(Finding("bear", "implied", f"ROIC {_pct(roic, 0, False)} < WACC EST {_pct(wacc, 1, False)}; EV {_pct(vs, 0) if vs is not None else '–'} mot null-vekst", f"lett case bygget {built} (WACC EST)", built, t, est=True, detail=str(rv.get("reads") or "")))
        elif g is not None and g > 0.02:
            out.append(Finding("bear", "implied", f"kursen krever {_pct(g)}/år vekst for alltid (langsiktig EST {_pct(0.02, 0, False)}); ROIC {_pct(roic or 0, 0, False)}", f"lett case bygget {built} (WACC EST)", built, t, est=True, detail=str(rv.get("reads") or "")))
        m, pe = lc.get("multiples") or {}, lc.get("peers") or {}
        if m.get("ev_ebit") and pe.get("ev_ebit") and m["ev_ebit"] > pe["ev_ebit"] * 1.15:
            out.append(Finding("bear", "multiple", f"EV/EBIT {m['ev_ebit']:.1f}x mot {pe.get('group', 'gruppe')}-median {pe['ev_ebit']:.1f}x (n {pe.get('n_ev_ebit', 0)})", f"lett case bygget {built} (Yahoo-regnskap)", built, t))
    elif lc and lc.get("financial"):
        m, pe = lc.get("multiples") or {}, lc.get("peers") or {}
        built = str(lc.get("built_at", ""))[:10]
        if m.get("pb") and pe.get("pb") and m["pb"] > pe["pb"] * 1.15:
            out.append(Finding("bear", "multiple", f"P/B {m['pb']:.2f}x mot {pe.get('group', 'gruppe')}-median {pe['pb']:.2f}x (n {pe.get('n_pb', 0)})", f"lett case bygget {built} (Yahoo-regnskap)", built, t))
    o = ctx.odds
    if o and not o.note and ctx.breakeven:
        sim = o.simulation.get("12 mnd")
        r_, be = ctx.breakeven
        dec = decided_share(sim)
        if dec is not None and dec < be:
            out.append(Finding("bear", "odds", f"12 mnd: kursmål først {dec * 100:.0f} % av de avgjorte banene (kill først {sim.kill * 100:.0f} %, kursmål {sim.target * 100:.0f} %, ingen {sim.neither * 100:.0f} %) "
                               f"< break-even {be * 100:.0f} % (R {r_:.2f}; {sim.n} baner)", f"odds.py på lagerets kurser siden 2010, per {o.asof:%Y-%m-%d}", f"{o.asof:%Y-%m-%d}", t, delayed=True))
    risk_alerts = [a for a in inp.alerts if a.code == code and a.kind == sg.RISK]
    if risk_alerts:
        a = risk_alerts[0]
        of = inp.odds_file.get(a.signal, {})
        rob = of.get("robustness") or {}
        lo, hi = of.get("lo60"), of.get("hi60")
        out.append(Finding("bear", "risk_signal", f"{a.signal} {a.session}: {a.detail}; meravkastning 60 d {_pct(of['exc60']) if of.get('exc60') is not None else '–'}"
                           + (f" [{lo * 100:+.1f}, {hi * 100:+.1f}]" if lo is not None and hi is not None else "") + f", grad {rob.get('grade60', '?')}, n {int(of.get('events') or 0)}",
                           SIGNAL_SRC, a.session, t, delayed=True, detail=a.signal))
    sh = ins.shorts(code, inp.shorts_doc)
    if sh and sh["now"] >= float(cfg["short_min_pct"]):
        ch30 = ins.short_change(sh, 30)
        out.append(Finding("bear", "short_pos", f"{sh['now']:.2f} % av aksjene short ({sh['date']}), {ch30:+.2f} pp 30 d; {len(sh['holders'])} posisjonshavere" if ch30 is not None else f"{sh['now']:.2f} % short ({sh['date']})",
                           f"Finanstilsynets shortregister (buffer hentet {str(sh.get('fetched_at'))[:10]})", sh["date"] or inp.session, t, delayed=True))
    days = int(cfg["insider_days"])
    cutoff = f"{inp.today - pd.Timedelta(days=days):%Y-%m-%d}"
    items = [i for i in _insider_items(inp, code) if i["time"][:10] >= cutoff]
    sells = sorted((i for i in items if i.get("side") == "sell"), key=lambda i: i["time"], reverse=True)
    if sells:
        out.append(Finding("bear", "insider_sell", f"{len(sells)} salgsmeldinger siste {days} d (siste {sells[0]['time'][:10]}: «{str(sells[0].get('title', ''))[:60]}»); {sum(i.get('side') == 'buy' for i in items)} kjøp",
                           f"NewsWeb kategori 1102 (buffer, {inp.insider_doc_age})", sells[0]["time"], t, delayed=True, detail=str(sells[0].get("title", ""))))
    group = inp.groups.get(code, "Other")
    ex = pf.exposure(inp.cases, inp.groups, inp.sizing)
    others = [x for x in ex["per_case"] if x["group"] == group and x["code"] != code]
    if others:
        my_drivers = {pf.driver_of(k)[0] for k in (c.kill if c else [])}
        shared = sorted({d for x in others for d in {y["driver"] for y in x["drivers"]} if d in my_drivers and d != "other"})
        loss = sum(x["loss_at_kill"] or 0 for x in others)
        out.append(Finding("bear", "sector", f"{len(others)} åpne BUY i {group} ({', '.join(x['code'] for x in others)}); tap ved kill NOK {_nok(loss)}"
                           + (f"; {len(shared)} felles kill-driver: {', '.join(shared)}" if shared else "; 0 felles kill-drivere"),
                           "vurderingsloggen (BUY-rader med posisjon), kill-driverne i kriteriene (D27)", inp.session, t, detail=",".join(shared)))
    ep = inp.patterns() or {}
    if ep.get("n_wrong"):
        p, cnt = max(ep["counts"].items(), key=lambda kv: (kv[1]["wrong"], kv[1]["all"]))
        if cnt["wrong"]:
            st = sg.status(inp.snap.panel, code)
            chg = st.get("chg_20d")
            out.append(Finding("bear", "pattern", f"{learn.PATTERN_WORDS.get(p, p)}: {cnt['wrong']} av {ep['n_wrong']} feilkall ({cnt['all']} av {ep['n']} kall)"
                               + (f"; kursen {_pct(chg)} siste 20 økter" if chg is not None else ""), "kalibreringssiden: learn.error_patterns på vurderingsloggen og lagerets kurser", inp.session, t, detail=p))
    if v.get("bear") and px:
        b = float(v["bear"])
        pb = v.get("p_bear")
        out.append(Finding("bear", "bear_value", f"bear {b:g} ({_pct(b / px - 1)}) med sannsynlighet {pb * 100:.0f} %" if pb is not None else f"bear {b:g} ({_pct(b / px - 1)}); sannsynlighet ikke satt (0 av 3)",
                           f"egen vurdering {v.get('date')}", str(v.get("date")), t, est=True))
    out.sort(key=lambda f: BEAR_RANK.get(f.kind, 9))
    out = out[:MAX_BEAR_REASONS]
    if len(out) < MIN_BEAR_REASONS:
        return out + [Finding("bear", "too_few", f"{len(out)} grunner med tall (krav {MIN_BEAR_REASONS})",
                              "desk-reglene over rapportleser, lett case, odds, signaler, shortregister, innsidere, porteføljen, kalibreringen og egen vurdering",
                              inp.session, t, status="stands")]
    return out


# ------------------------------------------------------------------------------------------------ 5. reply
def reply(inp: Inputs, code: str, ctx: Ctx, reasons: list[Finding], offset: int) -> list[Finding]:
    """A rule-based answer to every bear reason: ``rebuts`` with numbers, or ``stands``. ``offset`` is the index of the
    first bear finding in the stock's log, so each reply can point at the reason it answers."""
    from osloquant.dashboard import insiders as ins
    from osloquant.dashboard import learn  # noqa: F401 – pattern words
    from osloquant.dashboard import portfolio as pf

    t = inp.stamp()
    c, v, px = ctx.case, ctx.view, ctx.px
    out: list[Finding] = []
    for i, r in enumerate(reasons):
        k, ref = r.kind, offset + i
        src, val, ok = r.source, None, False
        if k == "too_few":
            continue
        if k == "bear_value":
            probs = [v.get(x) for x in ("p_bear", "p_base", "p_bull")]
            vals = [v.get(x) for x in ("bear", "base", "bull")]
            if all(p is not None for p in probs) and all(x is not None for x in vals) and px:
                ev = sum(float(p) * float(x) for p, x in zip(probs, vals, strict=True))
                ok = ev / px - 1 >= 0.10
                val = f"forventet verdi {ev:.1f} ({_pct(ev / px - 1)}) med p {float(probs[0]) * 100:.0f}/{float(probs[1]) * 100:.0f}/{float(probs[2]) * 100:.0f} %" + ("" if ok else " < +10 %")
            else:
                val = "0 av 3 sannsynligheter eller verdier satt – kan ikke regnes"
            src = f"egen vurdering {v.get('date')}"
        elif k == "kill_nearer":
            s = ctx.rep or {}
            kk = next((x for x in s.get("kill", []) if str(x.get("criterion", "")) == r.detail), None)
            if kk and str(kk.get("status", "")).startswith("triggered"):
                val = f"utløst: nå {kk['now']:.4g} mot {kk.get('op', '')} {kk['threshold']:.4g} – 0 tilsvar"
            elif kk and kk.get("threshold"):
                margin = abs(kk["now"] - kk["threshold"]) / abs(kk["threshold"])
                ok = margin >= 0.25
                val = f"avstand {margin * 100:.0f} % av terskelen (nå {kk['now']:.4g}, terskel {kk['threshold']:.4g}; krav ≥ 25 %)"
            else:
                val = "0 terskel å måle mot"
        elif k == "metric_down":
            s = ctx.rep or {}
            m, case_v = s.get("metrics") or {}, s.get("case") or {}
            key = r.detail
            ltm, est = (m.get(f"{key}_ltm") or {}).get("value"), case_v.get(key)
            if ltm is not None and est:
                ok = ltm >= 0.95 * est
                val = f"LTM {_nok(ltm)} er {ltm / est * 100:.0f} % av casens {s.get('year')}-estimat {_nok(est)} (krav ≥ 95 %)"
                src = f"{src}; {case_v.get('_file', 'casemodellen')} (EST)"
            else:
                val = f"0 case-estimat for {key} å måle LTM mot"
        elif k == "sector":
            ok = not r.detail
            group = inp.groups.get(code, "Other")
            ex = pf.exposure(inp.cases, inp.groups, inp.sizing)
            others = [x for x in ex["per_case"] if x["group"] == group and x["code"] != code]
            theirs = sorted({d["driver"] for x in others for d in x["drivers"]})
            mine = sorted({pf.driver_of(x)[0] for x in (c.kill if c else [])})
            val = (f"0 felles kill-drivere: mine {', '.join(mine) or '–'} mot deres {', '.join(theirs) or '–'}" if ok
                   else f"{len(r.detail.split(','))} felles driver ({r.detail}) med {', '.join(x['code'] for x in others)}: én risiko, ikke to")
            src = "kill-kriteriene i vurderingsloggen (driver lest av ordene eller taggen, D27)"
        elif k == "pattern":
            p = r.detail
            st = sg.status(inp.snap.panel, code)
            chg = st.get("chg_20d")
            if p == "early":
                ok = chg is not None and chg < 0.10
                val = f"kursen {_pct(chg) if chg is not None else '–'} siste 20 økter (mønsteret slår inn ved ≥ +10 %)"
            elif p == "late_out":
                ok = bool(v.get("kill_level"))
                val = f"kill-nivå {float(v['kill_level']):g} satt i synet" if ok else "0 kill-nivå i synet"
            elif p in ("kill_ignored", "no_kill_check"):
                n = len([x for x in (ctx.rep or {}).get("kill", []) if x.get("metric")])
                ok = n > 0
                val = f"{n} leserregler sjekker kriteriene maskinelt ved hver rapport"
            elif p == "guidance":
                from osloquant.dashboard.learn import _GUIDANCE

                hits = len(_GUIDANCE.findall(str(v.get("thesis") or "")))
                ok = hits == 0
                val = f"{hits} treff på guidance-ord i begrunnelsen"
            elif p == "consensus":
                ct = v.get("consensus_target")
                ok = not ct or abs(float(v["target"]) / float(ct) - 1) >= 0.05
                val = f"konsensus {float(ct):g} mot kursmål {float(v['target']):g} ({_pct(float(v['target']) / float(ct) - 1)})" if ct else "0 konsensusmål logget på synet"
            else:
                val = f"0 regel for mønsteret {p}"
            src = "synet i vurderingsloggen og lagerets kurser"
        elif k == "risk_signal":
            of = inp.odds_file.get(r.detail, {})
            rob = of.get("robustness") or {}
            lo, hi, g = of.get("lo60"), of.get("hi60"), rob.get("grade60")
            spans = lo is not None and hi is not None and lo <= 0 <= hi
            ok = g in ("C", "D") or spans
            val = f"grad {g or '?'}; 60 d intervall [{lo * 100:+.1f}, {hi * 100:+.1f}] {'inneholder' if spans else 'utenfor'} null" if lo is not None else f"grad {g or '?'}; 0 intervall målt"
            src = "signal_odds.yaml (D20/D23: grad A–D, bootstrap-intervall)"
        elif k == "short_pos":
            sh = ins.shorts(code, inp.shorts_doc)
            ch30 = ins.short_change(sh, 30) if sh else None
            ok = ch30 is not None and ch30 <= 0
            val = f"short {ch30:+.2f} pp siste 30 d ({'fallende/uendret' if ok else 'stigende'})" if ch30 is not None else "0 historikk i registeret"
        elif k == "insider_sell":
            days = int(inp.cfg["insider_days"])
            cutoff = f"{inp.today - pd.Timedelta(days=days):%Y-%m-%d}"
            items = [i for i in _insider_items(inp, code) if i["time"][:10] >= cutoff]
            buys, sells = sum(i.get("side") == "buy" for i in items), sum(i.get("side") == "sell" for i in items)
            ok = buys >= sells
            val = f"{buys} kjøp mot {sells} salg siste {days} d"
        elif k == "implied":
            rd = ctx.rdcf if ctx.rdcf and not ctx.rdcf.get("error") else None
            if rd and rd.get("rd_m_last") is not None and rd.get("rd_m_last_ours") is not None:
                ok = rd["rd_m_last"] < rd["rd_m_last_ours"]
                val = f"casemodellen: markedet priser {_pct(rd['rd_m_last'], 1, False)} margin, caset {_pct(rd['rd_m_last_ours'], 1, False)}"
                src = f"casemodellen {rd.get('file')} (Toolkit, privat; EST)"
            else:
                val = "0 full casemodell å tilbakevise med (bare lett case)"
        elif k == "claude":
            from osloquant.dashboard import today as td

            lr = td.last_report(c, inp.today, days=400) if c else None
            cv = (c.claude_view if c else None) or {}
            if lr and v.get("date"):
                d = lr[0]
                ok = str(cv.get("date"))[:10] < f"{d:%Y-%m-%d}" <= str(v.get("date"))[:10]
                val = f"Claudes syn {str(cv.get('date'))[:10]} mot rapporten {d:%Y-%m-%d}; synet i boken {str(v.get('date'))[:10]}" + (" – Claudes er fra før rapporten" if ok else " – begge er like ferske (0 rapporter mellom)")
            else:
                val = f"0 rapporter mellom synene ({str(cv.get('date'))[:10]} og {str(v.get('date'))[:10] if v.get('date') else 'ingen'})"
            src = "vurderingsloggen; rapportdatoer fra leseren, research book og finanskalenderen"
        elif k == "odds":
            o, (r_, be) = ctx.odds, ctx.breakeven
            dec = decided_share(o.simulation.get("12 mnd"))
            ok = dec is not None and dec >= be
            val = f"kursmål først {dec * 100:.0f} % av de avgjorte banene mot break-even {be * 100:.0f} % (R {r_:.2f})" if dec is not None else "0 avgjorte baner"
        elif k == "multiple":
            rd = ctx.rdcf if ctx.rdcf and not ctx.rdcf.get("error") else None
            if rd and rd.get("dcf") is not None and px:
                ok = float(rd["dcf"]) / px - 1 >= 0.10
                val = f"DCF {float(rd['dcf']):.1f} ({_pct(float(rd['dcf']) / px - 1)}) mot kursen {px:.2f} (krav ≥ +10 %)"
                src = f"casemodellen {rd.get('file')} (Toolkit, privat; EST)"
            else:
                val = "0 full casemodell med DCF-verdi"
        else:
            val = f"0 regel for {k}"
        out.append(Finding("reply", k, val, src, r.asof, t, status="rebuts" if ok else "stands", ref=ref, est=r.est))
        r.status = "rebutted" if ok else "stands"
    return out


# ------------------------------------------------------------------------------------------------ 6. risk
def risk(inp: Inputs, code: str, ctx: Ctx) -> tuple[list[Finding], dict | None]:
    """The position at the maximum loss, the sector group's share after the buy, the events before the horizon.
    Returns the findings and, when nothing blocks, the prefill for the judgement form."""
    from osloquant.dashboard import odds as od
    from osloquant.dashboard import pretrade as pt
    from osloquant.dashboard import sizing

    t, cfg, scfg = inp.stamp(), inp.cfg, inp.sizing
    c, v, px = ctx.case, ctx.view, ctx.px
    out: list[Finding] = []
    blocked = False
    if not scfg:
        out.append(Finding("risk", "no_limits", "0 grenser (sizing: paper_capital, max_loss, max_position mangler i ~/osloquant-home/dashboard.yaml)", "dashboard.yaml", inp.session, t, status="blocked"))
        return out, None
    kill, why = od.kill_level(v)
    size = None
    if not kill or not px:
        out.append(Finding("risk", "no_kill", f"0 kill-nivå og 0 bear-verdi i synet{' (0 kurs)' if not px else ''}: ingen størrelse", "vurderingsloggen", inp.session, t, status="blocked"))
        blocked = True
    elif kill >= px:
        out.append(Finding("risk", "size", f"kill-nivå {kill:g} ≥ kurs {px:.2f}: 0 aksjer ({why})", f"vurderingsloggen; {PRICE_SRC}", inp.session, t, status="blocked", delayed=True))
        blocked = True
    else:
        size = sizing.size(px, kill, scfg, code, inp.rows, group=inp.groups.get(code), groups=inp.groups)
        cap = float(scfg["paper_capital"])
        out.append(Finding("risk", "size", f"{size.shares} aksjer = NOK {_nok(size.value)} ({size.value / cap * 100:.1f} % av papirsummen); tap ved kill-nivå {kill:g} ({why}): NOK {_nok(size.loss_at_kill)} "
                           f"(grense NOK {_nok(scfg['max_loss'])}); bindende: {size.binding}; tap per aksje {size.loss_per_share:.2f}",
                           f"sizing.py med dashboard.yaml; {PRICE_SRC}", inp.session, t, status="blocked" if size.shares <= 0 else None, delayed=True))
        blocked = blocked or size.shares <= 0
        group = inp.groups.get(code, "Other")
        opened = sizing.open_positions(inp.rows, exclude=code)
        same = {k: r for k, r in opened.items() if inp.groups.get(k) == group}
        other_value = sum(float(r.get("position_value") or 0) for r in same.values())
        other_loss = sum(float(r.get("loss_at_kill") or 0) for r in same.values())
        share_after = (other_value + size.value) / cap
        over = share_after > float(cfg["max_group_share"]) + 1e-9
        out.append(Finding("risk", "group_share", f"{share_after * 100:.1f} % av papirsummen i {group} etter kjøp (før {other_value / cap * 100:.1f} %, {len(same)} åpne syn; grense {float(cfg['max_group_share']) * 100:.0f} %)",
                           "vurderingsloggen (BUY-rader med posisjon); dashboard.yaml desk.max_group_share", inp.session, t, status="blocked" if over else None))
        blocked = blocked or over
        if scfg.get("max_loss_per_group"):
            lim = float(scfg["max_loss_per_group"])
            la = other_loss + size.loss_at_kill
            out.append(Finding("risk", "group_loss", f"NOK {_nok(la)} tap ved kill i {group} etter kjøp (grense NOK {_nok(lim)})", "vurderingsloggen; dashboard.yaml sizing.max_loss_per_group",
                               inp.session, t, status="blocked" if la > lim + 1e-6 else None))
            blocked = blocked or la > lim + 1e-6
        if scfg.get("max_total_loss"):
            lim = float(scfg["max_total_loss"])
            la = size.open_loss + size.loss_at_kill
            out.append(Finding("risk", "total_loss", f"NOK {_nok(la)} samlet tap ved kill etter kjøp (grense NOK {_nok(lim)})", "vurderingsloggen; dashboard.yaml sizing.max_total_loss",
                               inp.session, t, status="blocked" if la > lim + 1e-6 else None))
            blocked = blocked or la > lim + 1e-6
    months = int(v.get("horizon_months") or 12)
    evs = pt.events_before_horizon(c, code, inp.today, months)
    out.append(Finding("risk", "events", f"{len(evs)} hendelser før horisonten ({months} mnd)" + ("; " + "; ".join(f"{dato(e['date'], False)} {e['name'] if not e.get('code') else ''} {str(e['what'])[:30]}".replace("  ", " ") for e in evs[:4]) if evs else ""),
                       "research book, finanskalendere på NewsWeb, Norges Banks møtekalender", inp.session, t))
    if blocked:
        return out, None
    pre = {"rating": v.get("rating") or "", "target": v.get("target"), "horizon": months, "bear": v.get("bear"), "base": v.get("base"), "bull": v.get("bull"),
           "p_bear": v.get("p_bear"), "p_base": v.get("p_base"), "p_bull": v.get("p_bull"), "kill_level": v.get("kill_level") or "",
           "kill_text": "\n".join(c.kill) if c else "", "position_shares": size.shares if size else "", "consensus_target": v.get("consensus_target"),
           "consensus_source": v.get("consensus_source") or ""}
    return out, pre


# ------------------------------------------------------------------------------------------------ the chain
def run_stock(inp: Inputs, code: str, forced: bool = False) -> StockRun | None:
    """One stock through the six roles. Returns None when the Scout found nothing (and the run is not forced)."""
    c = inp.by_code.get(code)
    lp = inp.last_price(code)
    sr = StockRun(code, inp.snap.names.get(code, c.name if c else code), inp.groups.get(code, "Other"), lp[0] if lp else None,
                  f"{lp[1]:%Y-%m-%d}" if lp else None, None, None, None)
    found = scout(inp, code, forced)
    if not found:
        return None
    sr.findings += found
    sr.stage = "filter"
    fl = filter_role(inp, code)
    sr.findings += fl
    kills = [f for f in fl if f.status == "killed"]
    if kills:
        return _end(sr, "killed", kills[0])
    sr.stage = "analyst"
    ctx = Ctx()
    sr.findings += analyst(inp, code, ctx)
    sr.target = float(ctx.view["target"]) if ctx.view.get("target") else None
    sr.kill, sr.kill_source = ctx.kill, ctx.kill_source
    sr.stage = "bear"
    offset = len(sr.findings)
    reasons = bear(inp, code, ctx)
    sr.findings += reasons
    real = [r for r in reasons if r.kind != "too_few" and _DIGIT.search(r.value)]
    if len(real) < MIN_BEAR_REASONS:
        # the hand-off rule, enforced by the chain and not only by the bear: no three numbered reasons, no debate
        if not any(r.kind == "too_few" for r in reasons):
            sr.findings.append(Finding("bear", "too_few", f"{len(real)} grunner med tall (krav {MIN_BEAR_REASONS})", "desk-kjeden", inp.session, inp.stamp(), status="stands"))
        sr.veto = next(i for i, f in enumerate(sr.findings) if f.kind == "too_few")
        return _end(sr, "parked", sr.findings[sr.veto])
    sr.stage = "reply"
    sr.findings += reply(inp, code, ctx, real, offset)
    standing = [i for i, f in enumerate(sr.findings) if f.role == "bear" and f.status == "stands"]
    if standing:
        sr.veto = standing[0]
        return _end(sr, "parked", sr.findings[sr.veto])
    sr.stage = "risk"
    rf, pre = risk(inp, code, ctx)
    sr.findings += rf
    blocked = [f for f in rf if f.status == "blocked"]
    if blocked:
        return _end(sr, "parked", blocked[0])
    sr.prefill = pre
    return _end(sr, "ready", None)


def _end(sr: StockRun, outcome: str, why: Finding | None) -> StockRun:
    assert outcome in OUTCOMES
    sr.outcome = outcome
    sr.reason = f"{why.claim}: {why.value}" if why else ""
    bears = [f for f in sr.findings if f.role == "bear" and f.kind != "too_few"]
    nreb = sum(f.status == "rebutted" for f in bears)
    nst = sum(f.status == "stands" for f in bears)
    t = sr.findings[-1].t if sr.findings else datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sr.findings.append(Finding("desk", outcome, f"{len(sr.findings)} funn; bjørnen {len(bears)} grunner, {nreb} tilbakevist, {nst} står; stoppet i {sr.stage}",
                               "desk-kjeden (ingen rolle kan ende i et kjøp)", sr.price_date or t[:10], t, status=outcome, detail=sr.reason))
    sr.stage = "done"
    return sr


def run(codes: list[str] | None = None, trigger: str = "daily", snap: mk.Snapshot | None = None, today: pd.Timestamp | None = None,
        now: datetime | None = None, write: bool = True) -> DeskRun:
    """The desk over every stock in the store (daily) or over ``codes`` (manual: each is forced through the chain).
    Writes the run under ~/osloquant-home/desk/ unless ``write`` is False. Never writes a judgement."""
    if trigger not in ("daily", "manual"):
        raise ValueError("trigger is daily or manual")
    inp = Inputs(snap, today, now)
    forced = bool(codes)
    universe = sorted(c for c in inp.snap.panel["close"].columns if c in inp.snap.names or c in inp.by_code) if not codes else [c.upper().removesuffix(".OL") for c in codes]
    base = f"{inp.now:%Y%m%dT%H%M%S}-{trigger}"
    run_id, n = base, 1
    while write and run_path(run_id).exists():                 # two runs in the same second: the second gets a suffix, nothing is overwritten
        n += 1
        run_id = f"{base}-{n}"
    out = DeskRun(run_id, inp.session, trigger, inp.stamp(), config={**inp.cfg, "sizing": inp.sizing or {}})
    for code in universe:
        try:
            sr = run_stock(inp, code, forced)
        except Exception as e:  # noqa: BLE001 – one stock's bad data must not stop the daily run; the failure is shown, not hidden
            inp.data_quality.append({"what": f"desk-feil for {code}", "asof": inp.session, "ok": False,
                                     "note": f"{type(e).__name__}: {e} – aksjen er ikke med i kjøringen"})
            continue
        if sr:
            out.stocks.append(sr)
    out.scanned = len(universe)
    out.flagged = sum(1 for s in out.stocks if any(f.role == "scout" and f.kind != "quiet" for f in s.findings))
    out.killed = sum(s.outcome == "killed" for s in out.stocks)
    out.debated = sum(any(f.role == "bear" for f in s.findings) for s in out.stocks)
    out.parked = sum(s.outcome == "parked" for s in out.stocks)
    out.ready = sum(s.outcome == "ready" for s in out.stocks)
    out.data_quality = inp.data_quality
    out.finished_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if now is None else inp.stamp()
    assert all(s.outcome in OUTCOMES for s in out.stocks)
    if write:
        save(out)
    return out


# ------------------------------------------------------------------------------------------------ the statistic
def veto_stats(closes: pd.DataFrame | None = None, horizon: int | None = None, rows: list[dict] | None = None, now: pd.Timestamp | None = None) -> dict:
    """How often the Bear's veto was followed by the price reaching the kill level before the target, within
    ``horizon`` sessions after the run – against the same count for the stocks the desk let through. Decided by the
    first daily close at or beyond a level (adjusted closes, as the odds). Honest by construction: pending windows are
    pending, runs without a kill level or a target are unscorable, and the comparison group is shown beside it."""
    from osloquant.dashboard import odds as od

    horizon = int(horizon or config()["veto_horizon_sessions"])
    rows = index() if rows is None else rows
    if closes is None:
        try:
            closes = od.long_closes()
        except Exception:  # noqa: BLE001 – no store: nothing to score against
            closes = pd.DataFrame()
    out = {"horizon": horizon, "veto": _bucket(), "through": _bucket(), "rows": []}
    for r in rows:
        for code, s in r["stocks"].items():
            group = "veto" if (s["outcome"] == "parked" and s.get("veto_kind") not in (None, "too_few")) else "through" if s["outcome"] == "ready" else None
            if not group:
                continue
            res = _after(closes, code, r["session"], s.get("price"), s.get("target"), s.get("kill"), horizon)
            out[group][res["result"]] += 1
            out["rows"].append({"run_id": r["run_id"], "session": r["session"], "code": code, "group": group, "veto_kind": s.get("veto_kind"), "reason": s.get("reason"), **res})
    for g in ("veto", "through"):
        b = out[g]
        decided = b["right"] + b["wrong"]
        b["decided"] = decided
        b["share_right"] = b["right"] / decided if decided else None
        b["n"] = sum(b[k] for k in ("right", "wrong", "neither", "pending", "unscorable"))
    return out


def _bucket() -> dict:
    return {"right": 0, "wrong": 0, "neither": 0, "pending": 0, "unscorable": 0}


def _after(closes: pd.DataFrame, code: str, session: str, price, target, kill, horizon: int) -> dict:
    if not price or not kill or not target or closes is None or code not in closes.columns:
        return {"result": "unscorable", "sessions": 0, "change": None}
    c = closes[code].dropna()
    base = c[c.index <= pd.Timestamp(session)]
    if base.empty:
        return {"result": "unscorable", "sessions": 0, "change": None}
    after = c[c.index > pd.Timestamp(session)].iloc[:horizon]
    if after.empty:
        return {"result": "pending", "sessions": 0, "change": None}
    rel = (after / float(base.iloc[-1])).to_numpy()[None, :]
    up, down = float(target) / float(price), float(kill) / float(price)
    if up < down:
        up, down = down, up                    # a SELL view: the kill level is above the price
    fp = od_first_passage(rel, up, down)
    change = float(after.iloc[-1] / base.iloc[-1] - 1)
    kill_first = fp == -1 if float(kill) < float(price) else fp == 1
    target_first = fp == 1 if float(kill) < float(price) else fp == -1
    if kill_first:
        return {"result": "right", "sessions": len(after), "change": change}
    if target_first:
        return {"result": "wrong", "sessions": len(after), "change": change}
    return {"result": "neither" if len(after) >= horizon else "pending", "sessions": len(after), "change": change}


def od_first_passage(rel, up, down) -> int:
    from osloquant.dashboard.odds import first_passage

    return int(first_passage(rel, up, down)[0])


# ------------------------------------------------------------------------------------------------ for the front page
def front_summary(session: str) -> dict | None:
    """The newest run for the newest close, as the front page shows it: counts, time, data quality."""
    r = latest(session)
    if not r:
        return None
    run = load_run(r["run_id"])
    bad = [q for q in (run.data_quality if run else []) if not q["ok"]]
    return {**r, "quality_bad": bad, "ready_codes": [c for c, s in r["stocks"].items() if s["outcome"] == "ready"],
            "parked_codes": [c for c, s in r["stocks"].items() if s["outcome"] == "parked"]}
