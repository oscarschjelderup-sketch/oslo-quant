"""The head of analysis (DECISIONS D50): a weekly routine that measures the set-up against thirty rules taken from how
the best investors and forecasters work (docs/natt/beste-praksis.md), and proposes the next improvement.

Each rule has a source, a metric computed from what the system already holds (the judgement log and its scored table,
the research book, the light cases, the data health, the sizing limits, the reviews and updates), a target and the
direction that is better. A rule is *ok*, *brudd* (off target), *for lite data* (fewer observations than it needs –
said, not hidden) or *ikke målt* (the data the metric needs does not exist yet). A rule off target, or one that cannot
be measured for lack of forecasts, yields a proposal from a fixed catalogue: what to change, why (with the numbers),
the expected effect on the rule's metric and the effort. Proposals are ranked by how far the rule is from its target,
weighted by whether it is about better decisions or stricter measurement, and halved for every proposal of the same
rule Oscar has rejected.

Oscar approves or rejects each proposal on /chief, with a reason. The decisions are appended to
``~/osloquant-home/chief/decisions.jsonl`` (private, append-only). An approved proposal goes to the backlog and is not
proposed again; a rejected one is not proposed again unless the rule's metric has worsened by at least a tenth since
the rejection (the evidence changed) – and never if the reason was "aldri". Nothing here changes a rule, a target, a
kill criterion, a probability or a calculation: the system proposes, with evidence, and Oscar decides (the night brief
of 5 Nov 2026). A run is written to ``chief/run-YYYY-MM-DD.json`` by ``oq chief run --write``.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from osloquant import judgements as jg

E = html.escape
CHIEF_DIR = "chief"
DECISIONS_FILE = "decisions.jsonl"
D46_SINCE = "2026-11-05"          # the day the pre-mortem, own-probability and anchoring fields entered the form
WORSE_BY = 0.10                   # a rejected proposal returns when its rule's metric is 10 % further from target
REASON_KINDS = ("ikke nå", "uenig", "aldri")


@dataclass
class Ctx:
    """Everything a rule may read; built once per run (``build_ctx``) and passed to pure metric functions."""
    rows: list[dict]
    table: pd.DataFrame
    today: pd.Timestamp
    cases: list = field(default_factory=list)
    universe: list[dict] = field(default_factory=list)
    lightcases: dict = field(default_factory=dict)
    health: list[str] = field(default_factory=list)
    sizing: dict | None = None
    update_scoring: dict = field(default_factory=dict)
    reviews: dict = field(default_factory=dict)


def _views(c: Ctx, since: str | None = None) -> list[dict]:
    return [r for r in jg.judgements(c.rows, jg.DEFAULT_ANALYST) if since is None or str(r["date"])[:10] >= since]


def _share(items: list, pred) -> tuple[float | None, int]:
    return (sum(1 for x in items if pred(x)) / len(items), len(items)) if items else (None, 0)


def _final(c: Ctx) -> pd.DataFrame:
    t = c.table
    if not len(t) or "status" not in t:
        return t.iloc[0:0] if len(t) else t
    return t[(t["status"] == "final") & (t["analyst"] == jg.DEFAULT_ANALYST)]


def _probs(r):
    return [r.get(k) for k in ("p_bear", "p_base", "p_bull")]


def _ev(r) -> float | None:
    p, v = _probs(r), [r.get("bear"), r.get("base"), r.get("bull")]
    if any(x is None for x in p + v):
        return None
    return sum(float(a) * float(b) for a, b in zip(p, v, strict=True))


# ------------------------------------------------------------------------------------------------ the metrics
def m_premortem(c):
    from osloquant.dashboard import discipline as dsc
    return _share(_views(c, D46_SINCE), lambda r: not dsc.premortem_problems(r.get("premortem")))


def m_own_probs(c):
    from osloquant.dashboard import discipline as dsc
    return _share(_views(c), lambda r: bool(dsc.process_items(r)["own_probs"]))


def m_brier(c):
    f = _final(c)
    b = f["brier"].dropna() if len(f) and "brier" in f else []
    return (float(b.mean()), len(b)) if len(b) else (None, 0)


def m_forecasts_per_quarter(c):
    since = c.today - pd.Timedelta(days=91)
    n = sum(1 for r in c.rows if jg.analyst_of(r) == jg.DEFAULT_ANALYST and r.get("kind") in ("judgement", "update", "forecast")
            and pd.Timestamp(str(r["date"])[:10]) >= since)
    return float(n), n


def m_updates_answered(c):
    sc = c.update_scoring or {}
    answered = sc.get("answered", 0)
    overdue = len(sc.get("overdue") or [])
    n = answered + overdue
    return (answered / n, n) if n else (None, 0)


def m_update_steps(c):
    us = [r for r in c.rows if r.get("kind") == "update" and r.get("changed") and r.get("prior")]
    steps = [max(abs(float(a) - float(b)) for a, b in zip(_probs(u), u["prior"], strict=True)) for u in us if None not in u["prior"]]
    return _share(steps, lambda s: s <= 0.15)


def m_base_rate_run(c):
    vs = [r for r in _views(c, D46_SINCE) if r.get("rating") in ("BUY", "SELL")]
    return _share(vs, lambda r: bool(r.get("base_rate")))


def m_base_rate_reasoned(c):
    flagged = [r for r in _views(c) if (r.get("base_rate") or {}).get("flags")]
    return _share(flagged, lambda r: bool((r.get("base_rate") or {}).get("reason")))


def m_priced_in_seen(c):
    vs = _views(c)
    return _share(vs, lambda r: "seen_implied" in (r.get("checklist") or []))


def m_margin_of_safety(c):
    buys = [r for r in _views(c) if r.get("rating") == "BUY" and _ev(r) is not None]
    return _share(buys, lambda r: _ev(r) >= 1.2 * float(r["price"]))


def m_downside_first(c):
    buys = [r for r in _views(c) if r.get("rating") == "BUY"]
    return _share(buys, lambda r: r.get("bear") is not None and r.get("kill_level") is not None)


def m_kill_numeric(c):
    return _share(_views(c), lambda r: any(re.search(r"\d", str(k)) for k in r.get("kill") or []))


def m_kill_checks(c):
    f = c.table
    if not len(f) or "kill_checks" not in f:
        return None, 0
    own = f[(f["analyst"] == jg.DEFAULT_ANALYST) & (f["days"].fillna(0) >= 90)] if "days" in f else f.iloc[0:0]
    return _share(list(own["kill_checks"]), lambda k: k > 0)


def m_kills_acted(c):
    ks = [r for r in c.rows if r.get("kind") == "kill_check" and r.get("breached") and jg.analyst_of(r) == jg.DEFAULT_ANALYST]
    return _share(ks, lambda k: str(k.get("action", "")).lower() not in ("", "held", "none", "nothing", "ignored"))


def m_process(c):
    from osloquant.dashboard import discipline as dsc
    s = [dsc.process_score(r)["score"] for r in _views(c)]
    s = [x for x in s if x is not None]
    return (sum(s) / len(s), len(s)) if s else (None, 0)


def m_reviewed(c):
    from osloquant.dashboard import review as rv
    its = [i for i in rv.items(c.rows, c.table, c.today) if (c.today - pd.Timestamp(i["date"])).days >= 90]   # a view needs a quarter behind it
    return _share(its, lambda i: bool(i["review"]))


def m_foresight(c):
    s = c.reviews or {}
    return (s.get("foresight_rate"), s.get("failed", 0))


def m_inversion(c):
    full = [u for u in c.universe if u.get("level") == "full"]
    return _share(full, lambda u: bool(u.get("inversion")))


def m_bear_heard(c):
    buys = [r for r in _views(c) if r.get("rating") == "BUY"]
    return _share(buys, lambda r: bool(r.get("desk_run")) or "new_argument" in (r.get("checklist") or []))


def m_blind(c):
    vs = [r for r in _views(c) if r.get("saw_claude") is not None]
    return _share(vs, lambda r: r.get("saw_claude") is False)


def m_not_anchored(c):
    re_rated = [r for r in _views(c) if r.get("anchor")]
    return _share(re_rated, lambda r: not (r["anchor"] or {}).get("kind") or bool(r.get("anchor_reason")))


def m_not_herding(c):
    with_c = [r for r in _views(c) if r.get("consensus_target")]
    return _share(with_c, lambda r: abs(float(r["target"]) / float(r["consensus_target"]) - 1) >= 0.05)


def m_circle(c):
    f = _final(c)
    if not len(f):
        return None, 0
    groups = {}
    for _, t in f.iterrows():
        g = next((u["group"] for u in c.universe if u["code"] == t["code"]), "Other")
        groups.setdefault(g, []).append(bool(t["direction_hit"]))
    judged = {g: v for g, v in groups.items() if len(v) >= 3}
    if not judged:
        return None, len(f)
    return float(sum(sum(v) / len(v) >= 0.4 for v in judged.values()) / len(judged)), len(f)


def m_sizing(c):
    if not c.sizing:
        return 0.0, 1
    buys = [r for r in _views(c) if r.get("rating") == "BUY"]
    return _share(buys, lambda r: r.get("position_shares") is not None) if buys else (1.0, 1)


def m_shared_drivers(c):
    from osloquant.dashboard import portfolio as pf

    groups = {u["code"]: u["group"] for u in c.universe}
    ex = pf.exposure(c.cases, groups)
    return float(len(ex.get("shared_drivers") or {})), max(len(pf.open_views(c.cases)), 1)


def m_data_quality(c):
    from osloquant.dashboard import lightcase as lcm
    covered = [u for u in c.universe if u.get("level") in ("full", "light")]
    return _share(covered, lambda u: (lcm.quality(c.lightcases[u["code"]])["grade"] if c.lightcases.get(u["code"]) else "C") in ("A", "B"))


def m_read_report(c):
    return _share(_views(c), lambda r: "read_report" in (r.get("checklist") or []))


def m_band(c):
    f = _final(c)
    b = f["in_band"].dropna() if len(f) and "in_band" in f else []
    return (float(pd.Series(b).astype(bool).mean()), len(b)) if len(b) else (None, 0)


def m_beat_flat(c):
    f = _final(c)
    b = f["beat_flat"].dropna() if len(f) and "beat_flat" in f else []
    return (float(pd.Series(b).astype(bool).mean()), len(b)) if len(b) else (None, 0)


def m_sample(c):
    n = len(_final(c))
    return float(n), max(n, 1)


def m_health(c):
    return float(len(c.health)), 1


@dataclass
class Rule:
    id: str
    title: str
    source: str
    measure: str
    fn: object
    target: float
    better: str              # "high" or "low"
    min_n: int
    kind: str                # "beslutning" or "måling"
    proposal: str
    effect: str
    effort: str


RULES = [
    Rule("R01", "Pre-mortem på hver vurdering", "Gary Klein (HBR 2007); Annie Duke", "andel vurderinger siden D46 med tre pre-mortem-grunner", m_premortem, 1.0, "high", 1, "beslutning",
         "Pre-mortem mangler på vurderinger: sjekk at skjemaet brukes, ikke CLI-en, og les grunnene ved neste kill-sjekk", "R01 til 100 %", "S"),
    Rule("R02", "Egne sannsynligheter, ikke malens", "Philip Tetlock (granularitet)", "andel vurderinger med sannsynligheter som ikke er malens 25/50/25 (eller er avkrysset som egne)", m_own_probs, 0.9, "high", 2, "måling",
         "Skriv scenariosannsynlighetene selv før modellen åpnes, og la Toolkit-malen stå tom for sannsynligheter", "R02 mot 90 %; Brier måler deg, ikke malen", "S"),
    Rule("R03", "Kalibrert: lav Brier på avsluttede vurderinger", "Tetlock / Good Judgment", "snitt Brier (tre scenarier), avsluttede vurderinger", m_brier, 0.5, "low", 10, "måling",
         "Brier er over 0,5: se pålitelighetsdiagrammet og om bear/bull-sannsynlighetene er for små", "R03 under 0,5", "M"),
    Rule("R04", "Mange prognoser med rask fasit", "Tetlock (tilbakemelding); Mauboussin (utvalgsstørrelse)", "vurderinger, oppdateringer og kvartalsprognoser siste 91 dager", m_forecasts_per_quarter, 12, "high", 0, "måling",
         "For få prognoser til å måle deg på: logg et 80 %-intervall for neste rapports omsetning og EBITDA på aksjesiden (D52) for hvert dekket selskap", "R04 fra få til 12+ per kvartal; kalibrering på måneder, ikke år", "M"),
    Rule("R05", "Oppdater når ny informasjon kommer", "Tetlock (oppdatering)", "andel rapporter etter et syn som er besvart innen 14 dager", m_updates_answered, 0.9, "high", 1, "måling",
         "Rapporter uten svar på «har sannsynligheten endret seg?»: svar på aksjesiden, også når svaret er «uendret»", "R05 mot 90 %", "S"),
    Rule("R06", "Oppdater i små steg", "Tetlock (superforecasters endrer lite og ofte)", "andel endrede oppdateringer der ingen sannsynlighet flyttet seg mer enn 15 pp", m_update_steps, 0.8, "high", 3, "beslutning",
         "Store sprang i sannsynlighetene: del oppdateringen i mindre steg og skriv hvorfor nyheten er så sterk", "R06 mot 80 %", "S"),
    Rule("R07", "Base rate før eget estimat", "Kahneman (outside view); Mauboussin (Base Rate Book)", "andel BUY/SELL siden D46 med base rate-sjekk på raden", m_base_rate_run, 1.0, "high", 1, "beslutning",
         "Base rate-sjekken mangler på vurderinger: koble Toolkit-estimatene til skjemaet for selskapet (publiser rapporten)", "R07 til 100 %", "M"),
    Rule("R08", "Estimat utenfor 80-persentilen må begrunnes", "Mauboussin (base rates)", "andel flaggede estimater med skriftlig begrunnelse", m_base_rate_reasoned, 1.0, "high", 1, "beslutning",
         "Flaggede estimater uten begrunnelse: skriv hva som skiller selskapet fra de 80 % som ikke klarte det", "R08 til 100 %", "S"),
    Rule("R09", "Vit hva prisen krever før du er uenig", "Mauboussin (Expectations Investing); Marks (andre-ordens tenkning)", "andel vurderinger der «hva markedet priser inn» er krysset av", m_priced_in_seen, 1.0, "high", 1, "beslutning",
         "Vurderinger uten å ha sett hva prisen krever: gå via «Før du kjøper»", "R09 til 100 %", "S"),
    Rule("R10", "Sikkerhetsmargin", "Seth Klarman; Graham/Buffett", "andel BUY der sannsynlighetsvektet verdi er minst 20 % over kursen", m_margin_of_safety, 1.0, "high", 1, "beslutning",
         "BUY uten 20 % sikkerhetsmargin i egne scenarioer: krev margin eller kall det HOLD", "R10 til 100 %", "S"),
    Rule("R11", "Nedsiden først", "Klarman; Buffett («regel nr. 1»)", "andel BUY med bear-verdi og kill-nivå", m_downside_first, 1.0, "high", 1, "beslutning",
         "BUY uten definert nedside: bear-verdi og kill-nivå før kursmål", "R11 til 100 %", "S"),
    Rule("R12", "Kill-kriterier med tall", "Annie Duke (Quit: kill criteria)", "andel vurderinger med minst ett kill-kriterium som har et tall", m_kill_numeric, 1.0, "high", 1, "beslutning",
         "Kill-kriterier uten tall kan ikke sjekkes: skriv terskelen", "R12 til 100 %", "S"),
    Rule("R13", "Kill-sjekk etter rapportene", "Duke; Dalio (feillogg)", "andel vurderinger eldre enn 90 dager med minst én kill-sjekk", m_kill_checks, 1.0, "high", 1, "måling",
         "Vurderinger uten kill-sjekk: logg en etter hver rapport", "R13 til 100 %", "S"),
    Rule("R14", "Brutt kill-kriterium gir handling", "Duke (pre-commitment)", "andel brutte kill-kriterier fulgt av handling", m_kills_acted, 1.0, "high", 1, "beslutning",
         "Brutte kill-kriterier uten handling: selg, eller skriv nytt syn med ny begrunnelse", "R14 til 100 %", "S"),
    Rule("R15", "God prosess, uavhengig av utfall", "Annie Duke (resulting)", "snitt prosesspoeng på vurderingene (D46)", m_process, 0.7, "high", 1, "beslutning",
         "Prosesspoenget er lavt: se hvilke punkter som oftest mangler på kalibreringssiden", "R15 mot 70 %", "S"),
    Rule("R16", "Feilgjennomgang hvert kvartal", "Ray Dalio (Principles)", "andel vurderinger eldre enn 90 dager gjennomgått dette kvartalet", m_reviewed, 1.0, "high", 1, "måling",
         "Kvartalets feilgjennomgang er ikke gjort: /review, største avvik først", "R16 til 100 %", "S"),
    Rule("R17", "Forutså du feilen?", "Gary Klein (pre-mortem etterpå)", "andel mislykkede caser der feilen sto i pre-mortem", m_foresight, 0.5, "high", 3, "måling",
         "Feilene står sjelden i pre-mortem: skriv pre-mortem fra bear-scenarioet og kill-kriteriene, ikke generelt", "R17 mot 50 %", "S"),
    Rule("R18", "Inverter: hva gir et tap på 30 %", "Charlie Munger", "andel fulle caser med en inversjonsliste fra modellen", m_inversion, 1.0, "high", 1, "beslutning",
         "Fulle caser uten inversjon: bygg «hva må gå galt for −30 %» fra modellens følsomheter", "R18 til 100 %", "M"),
    Rule("R19", "Hør bjørnen før du kjøper", "Munger (argumentér motsatt side); Klarman", "andel BUY med desk-kjøring eller nytt motargument krysset av", m_bear_heard, 1.0, "high", 1, "beslutning",
         "BUY uten at bjørnen er hørt: kjør desken på aksjen før skjemaet", "R19 til 100 %", "S"),
    Rule("R20", "Skriv blindt før andres syn", "Kahneman (uavhengige vurderinger)", "andel syn skrevet før Claudes, der Claude har et", m_blind, 0.8, "high", 2, "måling",
         "Mange syn skrevet etter Claudes: skriv ditt først", "R20 mot 80 %", "S"),
    Rule("R21", "Ikke ankre til eget kursmål", "Tversky og Kahneman (ankring)", "andel nye kursmål som ikke bare fulgte kursen (eller er begrunnet)", m_not_anchored, 1.0, "high", 1, "beslutning",
         "Kursmål som følger kursen: start fra modellen, ikke fra forrige kursmål", "R21 til 100 %", "S"),
    Rule("R22", "Ikke flokk", "Howard Marks (andre-ordens tenkning)", "andel kursmål mer enn 5 % fra konsensus (der konsensus er logget)", m_not_herding, 0.5, "high", 2, "beslutning",
         "Kursmålene ligger tett på konsensus: hva vet du som markedet ikke priser?", "R22 mot 50 %", "S"),
    Rule("R23", "Hold deg i sirkelen av kompetanse", "Warren Buffett", "andel sektorgrupper (≥ 3 avsluttede) med treffsikkerhet ≥ 40 %", m_circle, 1.0, "high", 3, "beslutning",
         "En sektorgruppe ligger under 40 % treff: dekk den lett, ikke fullt, til treffet er bedre", "R23 til 100 %", "M"),
    Rule("R24", "Overlev halene: størrelse etter tap ved kill-nivå", "Nassim Taleb; Klarman", "sizing-grenser satt og hver BUY størrelsesberegnet", m_sizing, 1.0, "high", 1, "beslutning",
         "Ingen sizing-grenser i dashboard.yaml: sett papirsum og maks tap – desken blokkerer alt uten dem", "R24 til 100 %", "S"),
    Rule("R25", "Ikke samme risiko to ganger", "Ray Dalio (ukorrelerte innsatser)", "antall delte kill-drivere i boken (D27)", m_shared_drivers, 0.0, "low", 1, "beslutning",
         "Flere caser deler kill-driver: les dem som én innsats", "R25 til 0", "S"),
    Rule("R26", "Gode data før beslutning", "Tetlock / Duke (garbage in)", "andel dekkede selskaper med lett case av kvalitet A eller B", m_data_quality, 0.9, "high", 1, "måling",
         "Mange lette caser har kvalitet C: kjør oq case build --all --refresh etter rapportsesongen", "R26 mot 90 %", "S"),
    Rule("R27", "Les rapporten selv", "Buffett (les primærkildene)", "andel vurderinger med «lest siste rapport» krysset av", m_read_report, 1.0, "high", 1, "beslutning",
         "Vurderinger uten lest rapport: les den før skjemaet", "R27 til 100 %", "S"),
    Rule("R28", "Båndet holder det det lover", "Tetlock (kalibrerte intervaller)", "andel avsluttede vurderinger der kursen endte i bear–bull-båndet", m_band, 0.8, "high", 5, "måling",
         "Båndet er for smalt: bear og bull bør fange ~80 % av utfallene", "R28 mot 80 %", "S"),
    Rule("R29", "Slå «kursen står stille»", "Mauboussin (flaks mot dyktighet: sammenlign med en enkel referanse)", "andel avsluttede der kursmålet var nærmere enn dagens kurs", m_beat_flat, 0.5, "high", 5, "måling",
         "Kursmålene slår ikke «kursen står stille»: krymp kursmålet mot kursen eller logg HOLD oftere", "R29 over 50 %", "M"),
    Rule("R30", "Nok utfall til å skille dyktighet fra flaks", "Michael Mauboussin (The Success Equation)", "antall avsluttede vurderinger (mål: 20)", m_sample, 20, "high", 0, "måling",
         "For få avsluttede vurderinger: flere syn med kortere horisont, eller kvartalsprognoser (R04)", "R30 mot 20", "M"),
]


# ------------------------------------------------------------------------------------------------ evaluation
def evaluate(c: Ctx) -> list[dict]:
    out = []
    for r in RULES:
        try:
            value, n = r.fn(c)
        except Exception as e:  # noqa: BLE001 – one rule's failure is reported, not hidden
            out.append({"id": r.id, "status": "feil", "error": f"{type(e).__name__}: {e}", "value": None, "n": 0})
            continue
        if value is None:
            status = "ikke målt" if n == 0 else "for lite data"
        elif n < r.min_n:
            status = "for lite data"
        else:
            ok = value >= r.target if r.better == "high" else value <= r.target
            status = "ok" if ok else "brudd"
        gap = None
        if value is not None:
            gap = (r.target - value) if r.better == "high" else (value - r.target)
            scale = abs(r.target) if r.target else 1.0
            gap = max(gap, 0) / scale
        out.append({"id": r.id, "status": status, "value": value, "n": n, "gap": gap})
    return out


def rule(rule_id: str) -> Rule:
    return next(r for r in RULES if r.id == rule_id)


def decisions_path() -> Path:
    return jg.home() / CHIEF_DIR / DECISIONS_FILE


def read_decisions(path: Path | None = None) -> list[dict]:
    p = path or decisions_path()
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def decide(proposal_id: str, decision: str, reason: str, reason_kind: str | None, metric_at: float | None, today: str | None = None,
           path: Path | None = None) -> dict:
    """Append Oscar's decision on one proposal. Earlier decisions are never touched."""
    if decision not in ("godkjent", "avvist"):
        raise ValueError("decision is godkjent or avvist")
    if len((reason or "").strip()) < 5:
        raise ValueError("give a reason (it is what the routine learns from)")
    if decision == "avvist" and reason_kind not in REASON_KINDS:
        raise ValueError(f"a rejection says why: {', '.join(REASON_KINDS)}")
    rule_id = proposal_id.split(":")[0]
    if rule_id not in {r.id for r in RULES}:
        raise ValueError(f"no rule {rule_id}")
    row = {"proposal": proposal_id, "rule": rule_id, "decision": decision, "reason": reason.strip(), "reason_kind": reason_kind if decision == "avvist" else None,
           "metric_at": metric_at, "date": today or datetime.now().strftime("%Y-%m-%d"), "logged_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    p = path or decisions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _worse(now: dict, at: float | None, r: Rule) -> bool:
    """Has the rule's metric moved at least WORSE_BY further from its target since the rejection?"""
    if now.get("value") is None or at is None:
        return False
    if r.better == "high":
        return now["value"] < at - WORSE_BY * max(abs(at), abs(r.target), 1e-9)
    return now["value"] > at + WORSE_BY * max(abs(at), abs(r.target), 1e-9)


def proposals(results: list[dict], decisions: list[dict]) -> dict:
    """The ranked proposals, the backlog (approved) and what is held back and why."""
    by = {d["proposal"]: d for d in decisions}                    # the newest decision per proposal wins
    rejections: dict[str, int] = {}
    for d in decisions:
        if d["decision"] == "avvist":
            rejections[d["rule"]] = rejections.get(d["rule"], 0) + 1
    live, held, backlog = [], [], []
    for res in results:
        r = rule(res["id"])
        if res["status"] != "brudd":
            continue
        pid = f"{r.id}:1"
        d = by.get(pid)
        if d and d["decision"] == "godkjent":
            backlog.append({"id": pid, "rule": r.id, "date": d["date"], "reason": d["reason"]})
            continue
        if d and d["decision"] == "avvist":
            if d.get("reason_kind") == "aldri":
                held.append({"id": pid, "rule": r.id, "why": f"avvist {d['date']} («aldri»): {d['reason']}"})
                continue
            if not _worse(res, d.get("metric_at"), r):
                held.append({"id": pid, "rule": r.id, "why": f"avvist {d['date']} ({d.get('reason_kind')}): {d['reason']} – kommer tilbake hvis målet blir minst 10 % verre"})
                continue
        weight = (1.0 if r.kind == "beslutning" else 0.9) * (0.5 ** rejections.get(r.id, 0))
        gap = res["gap"] if res.get("gap") is not None else 1.0
        live.append({"id": pid, "rule": r.id, "title": r.title, "source": r.source, "text": r.proposal, "effect": r.effect, "effort": r.effort,
                     "why": _why(r, res), "score": round(weight * gap / {"S": 1, "M": 2, "L": 3}[r.effort], 4), "metric": res.get("value"),
                     "returned": bool(d)})
    live.sort(key=lambda x: -x["score"])
    return {"live": live, "held": held, "backlog": backlog}


def _fmt(r: Rule, v) -> str:
    if v is None:
        return "–"
    if r.id in ("R03",):
        return f"{v:.3f}"
    if r.id in ("R04", "R25", "R30"):
        return f"{v:.0f}"
    return f"{v * 100:.0f} %"


def _why(r: Rule, res: dict) -> str:
    if res["status"] in ("ikke målt", "for lite data"):
        return f"{r.measure}: {_fmt(r, res.get('value'))} (n = {res['n']}) – {res['status']}"
    return f"{r.measure}: {_fmt(r, res['value'])} mot mål {_fmt(r, r.target)} (n = {res['n']})"


def run(c: Ctx, decisions: list[dict] | None = None) -> dict:
    res = evaluate(c)
    props = proposals(res, read_decisions() if decisions is None else decisions)
    counts = {s: sum(x["status"] == s for x in res) for s in ("ok", "brudd", "for lite data", "ikke målt", "feil")}
    return {"date": f"{c.today:%Y-%m-%d}", "results": res, "counts": counts, **props,
            "overdue_updates": [{"code": p["code"], "trigger": p["trigger"], "days": p["days"]} for p in (c.update_scoring or {}).get("overdue") or []],
            "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}


def run_path(day: str) -> Path:
    return jg.home() / CHIEF_DIR / f"run-{day}.json"


def write_run(doc: dict) -> Path:
    p = run_path(doc["date"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def latest_runs(n: int = 2) -> list[dict]:
    d = jg.home() / CHIEF_DIR
    files = sorted(d.glob("run-*.json"))[-n:] if d.exists() else []
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def build_ctx(today: pd.Timestamp | None = None) -> Ctx:
    """The live context from the home directory and the store (reads only)."""
    from osloquant.dashboard import book as bk
    from osloquant.dashboard import calendar as cal
    from osloquant.dashboard import coverage as cv
    from osloquant.dashboard import datahealth as dh
    from osloquant.dashboard import feeds as fd
    from osloquant.dashboard import lightcase as lcm
    from osloquant.dashboard import market as mk
    from osloquant.dashboard import review as rv
    from osloquant.dashboard import sizing
    from osloquant.dashboard import updates as up

    today = today or pd.Timestamp.now().normalize()
    rows = jg.read_log()
    table, _ = jg.calibration(rows)
    snap = mk.snapshot()
    cases = bk.cases()
    uni = cv.universe(snap, cases, bk.watchlist(), today)
    lcs = {u["code"]: lcm.load(u["code"]) for u in uni}
    from osloquant.dashboard import inversion as iv

    by_code = {c.code: c for c in cases}
    for u in uni:
        if u["level"] == "full":
            inv = iv.for_case(by_code.get(u["code"]), u.get("price"))
            u["inversion"] = bool(inv and not inv.get("error"))
    try:
        health = dh.problems(dh.overview(snap.panel["close"], cases, snap.asof))
    except Exception as e:  # noqa: BLE001
        health = [f"data health could not run: {type(e).__name__}"]
    return Ctx(rows=rows, table=table, today=today, cases=cases, universe=uni, lightcases=lcs, health=health, sizing=sizing.config(),
               update_scoring=up.scoring(rows, table, today, cases, fd.read(cal.CAL_FEED)), reviews=rv.summary(rows))


# ------------------------------------------------------------------------------------------------ page
def page_html(doc: dict, prev: dict | None, stored: bool, msg: dict | None = None) -> str:
    prev_v = {r["id"]: r.get("value") for r in (prev or {}).get("results", [])}
    rows = []
    for res in doc["results"]:
        r = rule(res["id"])
        cls_ = {"ok": "t", "brudd": "k", "feil": "k"}.get(res["status"], "src")
        pv = prev_v.get(res["id"])
        trend = "" if pv is None or res.get("value") is None else f'{_fmt(r, pv)} → '
        rows.append(f'<tr><td>{E(r.id)}</td><td><b>{E(r.title)}</b><div class="src">{E(r.source)}</div></td><td class="src">{E(r.measure)}</td>'
                    f'<td>{trend}<b>{_fmt(r, res.get("value"))}</b></td><td>{"≥" if r.better == "high" else "≤"} {_fmt(r, r.target)}</td>'
                    f'<td>{res["n"]}</td><td class="{cls_}">{E(res["status"])}</td></tr>')
    props = []
    for i, p in enumerate(doc["live"], 1):
        r = rule(p["rule"])
        props.append(f'<div class="item"><span class="tag u{0 if i == 1 else 1}">#{i}</span><b>{E(p["text"])}</b>'
                     f'<div class="why">Regel {E(p["rule"])} «{E(p["title"])}» ({E(p["source"])}). Hvorfor: {E(p["why"])}. Forventet effekt: {E(p["effect"])}. '
                     f'Innsats: {E(p["effort"])}.{" Kommer tilbake fordi målet er blitt verre siden avvisningen." if p["returned"] else ""}</div>'
                     f'<form method="post" action="/chief/decide" class="judge" style="display:grid;grid-template-columns:1fr 160px 140px 120px;gap:8px;align-items:end">'
                     f'<input type="hidden" name="proposal" value="{E(p["id"])}"><input type="hidden" name="metric_at" value="{"" if p["metric"] is None else p["metric"]}">'
                     '<div><label>Grunn (påkrevd)</label><input name="reason" minlength="5"></div>'
                     '<div><label>Hvis avvist</label><select name="reason_kind"><option value="">–</option>' + "".join(f"<option>{k}</option>" for k in REASON_KINDS) + '</select></div>'
                     '<button class="go" name="decision" value="godkjent" type="submit">Godkjenn</button><button class="go" name="decision" value="avvist" type="submit" '
                     'style="background:var(--risk)">Avvis</button></form></div>')
    backlog = "".join(f'<li>{E(b["id"])} – {E(rule(b["rule"]).title)} (godkjent {E(b["date"])}: {E(b["reason"])})</li>' for b in doc["backlog"]) or "<li class=empty>tom</li>"
    held = "".join(f'<li>{E(h["id"])} – {E(rule(h["rule"]).title)}: {E(h["why"])}</li>' for h in doc["held"]) or "<li class=empty>ingen</li>"
    over = ", ".join(f'{E(o["code"])} ({o["days"]} d)' for o in doc.get("overdue_updates") or []) or "ingen"
    notes = "".join(f'<div class="err">{E(m)}</div>' for m in (msg or {}).get("errors", [])) + "".join(f'<div class="ok">{E(m)}</div>' for m in (msg or {}).get("ok", []))
    c = doc["counts"]
    return ('<h1>Analysesjefen</h1><div class="sub">Hver uke: oppsettet målt mot 30 regler fra de beste investorene og prognosemakerne, og et forslag til neste forbedring. '
            'Systemet foreslår; du godkjenner eller avviser, med grunn. Ingenting endres av seg selv.</div>' + notes
            + f'<div class="card"><p><b>{E(doc["date"])}</b>{"" if stored else " (beregnet nå, ikke lagret – oq chief run --write lagrer ukens kjøring)"}: '
            f'{c["ok"]} ok, {c["brudd"]} brudd, {c["for lite data"]} for lite data, {c["ikke målt"]} ikke målt{", " + str(c["feil"]) + " feil" if c["feil"] else ""}. '
            f'Ikke oppdatert etter rapport (Tetlock): {over}.</p></div>'
            + f'<h2>Forslag, rangert</h2><div class="card">{"".join(props) or "<p class=empty>ingen regel er utenfor målet</p>"}'
            '<div class="src">Rangering: avstand fra målet × vekt (beslutning 1,0, måling 0,9) × 0,5 per tidligere avvisning av samme regel ÷ innsats (S 1, M 2, L 3). '
            'Et avvist forslag kommer ikke tilbake før målet er minst 10 % verre – og aldri om grunnen var «aldri». Beslutningene lagres i ~/osloquant-home/chief/decisions.jsonl.</div></div>'
            + f'<div class="grid2"><div class="card"><h3>Godkjent – venter på bygging</h3><ul>{backlog}</ul></div><div class="card"><h3>Holdt tilbake</h3><ul>{held}</ul></div></div>'
            '<h2>De 30 reglene</h2><div class="card"><table class="odds"><thead><tr><th>#</th><th>Regel og kilde</th><th>Måles som</th><th>Nå</th><th>Mål</th><th>n</th><th>Status</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table><div class="src">Reglene og kildene: docs/natt/beste-praksis.md. «For lite data» betyr at målingen finnes, men har færre observasjoner enn regelen trenger.</div></div>')

