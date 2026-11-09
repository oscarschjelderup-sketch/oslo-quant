"""Learning from my own calls (DECISIONS, rapporter 2026-11-02, part 3): the Brier score and the stated-probability
plot per case, and the error-pattern report – when a call was wrong, was it the same kind of wrong?

Patterns are rules on the log and the price path, never a reading of the text beyond a word match that is labelled as
such:

- ``early``        – a BUY that drew down 15 % or more from the call price inside its window (a SELL: ran up 15 %);
- ``late_out``     – the price crossed the kill level (or the bear value) and no judgement or kill check was logged
                     within ten sessions after the first cross;
- ``kill_ignored`` – a kill check in the window says breached and the action was none / held / ignored;
- ``no_kill_check``– a call scored for 90 days or more with no kill check at all;
- ``guidance``     – the rationale names management's guidance, ambition, CMD or target (word match – a question, not
                     a verdict);
- ``consensus``    – a consensus target was logged and the call's target sits within 5 % of it;
- ``anchored``     – the row's anchoring check (D46) found the target following the price or stuck after a big move.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard.dates import dato

DRAWDOWN = 0.15
LATE_SESSIONS = 10
MIN_DAYS_FOR_KILL_CHECK = 90
HERD = 0.05
_GUIDANCE = re.compile(r"guid|ambition|ambisjon|capital markets day|\bcmd\b|management'?s? target|ledelsens? mål|company target|selskapets mål", re.I)
PATTERN_WORDS = {"early": "for tidlig inn (≥ 15 % mot meg først)", "late_out": "for sent ut (kill-nivå krysset, ingen logging innen 10 økter)",
                 "kill_ignored": "kill-kriterium brutt og ignorert", "no_kill_check": "kill-kriteriene aldri sjekket", "guidance": "ankret til ledelsens guiding (ordtreff)",
                 "consensus": "kursmål innenfor 5 % av konsensus", "anchored": "kursmålet fulgte kursen eller sto fast (D46)"}


def by_case(table: pd.DataFrame, rel: dict | None, analyst: str = jg.DEFAULT_ANALYST) -> list[dict]:
    """Per company: calls, final calls, mean Brier (scenario, final only), direction hit rate, mean miss against the
    target, and the stated-vs-happened pairs from the reliability pass."""
    if not len(table):
        return []
    t = table[table["analyst"] == analyst] if "analyst" in table else table
    t = t[t["status"].isin(["final", "provisional"])] if "status" in t else t.iloc[0:0]
    pairs = (rel or {}).get("pairs") or []
    out = []
    for code, g in t.groupby("code"):
        fin = g[g["status"] == "final"]
        ps = [p for p in pairs if p["code"] == code]
        out.append({"code": code, "n": int(len(g)), "n_final": int(len(fin)),
                    "brier": float(fin["brier"].mean()) if "brier" in fin and fin["brier"].notna().any() else None,
                    "direction_hit": float(g["direction_hit"].mean()) if "direction_hit" in g and g["direction_hit"].notna().any() else None,
                    "abs_vs_target": float(g["vs_target"].abs().mean()) if "vs_target" in g and g["vs_target"].notna().any() else None,
                    "stated": float(np.mean([p["p"] for p in ps if p["happened"]])) if any(p["happened"] for p in ps) else None,
                    "pairs": ps})
    return sorted(out, key=lambda r: r["code"])


def _crossed(path: pd.Series, level: float, rating: str) -> pd.Timestamp | None:
    hit = path <= level if rating in ("BUY", "HOLD") else path >= level
    return hit[hit].index[0] if hit.any() else None


def patterns_for(j: dict, scored: dict, prices: jg.Prices, rows: list[dict]) -> list[str]:
    """The patterns one judgement shows (empty when none)."""
    found = []
    code, rating = j["code"], j["rating"]
    start, end = pd.Timestamp(j["date"]), pd.Timestamp(scored.get("scored_to") or j["date"])
    path = None
    if code in prices.adjusted:
        path = prices.adjusted[code].dropna()
        path = path[(path.index >= start) & (path.index <= end)]
    if path is not None and len(path) > 1:
        rel = path / float(j["price"]) - 1
        if rating == "BUY" and rel.min() <= -DRAWDOWN:
            found.append("early")
        if rating == "SELL" and rel.max() >= DRAWDOWN:
            found.append("early")
        kill = j.get("kill_level") or (j.get("bear") if rating != "SELL" else j.get("bull"))
        if kill:
            raw_factor = 1.0
            crossed = _crossed(path * raw_factor, float(kill), rating)
            if crossed is not None:
                later = [r for r in rows if r.get("code") == code and jg.analyst_of(r) == jg.analyst_of(j) and r["kind"] in ("judgement", "kill_check")
                         and crossed <= pd.Timestamp(str(r["date"])[:10]) <= crossed + pd.Timedelta(days=LATE_SESSIONS * 1.5)]
                if not later and (end - crossed).days > LATE_SESSIONS * 1.5:
                    found.append("late_out")
    checks = [r for r in rows if r["kind"] == "kill_check" and r.get("code") == code and jg.analyst_of(r) == jg.analyst_of(j)
              and start <= pd.Timestamp(str(r["date"])[:10]) <= end]
    if any(bool(r.get("breached")) and str(r.get("action", "")).lower() in ("", "held", "none", "nothing", "ignored") for r in checks):
        found.append("kill_ignored")
    if not checks and int(scored.get("days") or 0) >= MIN_DAYS_FOR_KILL_CHECK:
        found.append("no_kill_check")
    if _GUIDANCE.search(str(j.get("thesis") or "")):
        found.append("guidance")
    ct = j.get("consensus_target")
    if ct and abs(float(j["target"]) / float(ct) - 1) < HERD:
        found.append("consensus")
    if (j.get("anchor") or {}).get("kind"):
        found.append("anchored")                     # D46: the target followed the price, or stayed put after a big move
    return found


def error_patterns(rows: list[dict], table: pd.DataFrame, prices: jg.Prices, analyst: str = jg.DEFAULT_ANALYST) -> dict:
    """Every scored call with its patterns and whether it was wrong (direction against the benchmark, or a final call
    that missed its target on the wrong side). Counts per pattern among the wrong calls and among all."""
    if not len(table):
        return {"rows": [], "counts": {}, "n": 0, "n_wrong": 0}
    by_seq = {j["seq"]: j for j in jg.judgements(rows, analyst)}
    out = []
    for _, r in table.iterrows():
        j = by_seq.get(r["seq"])
        if not j or r.get("status") not in ("final", "provisional"):
            continue
        wrong = r.get("direction_hit") is False or (r.get("status") == "final" and r.get("target_reached") is False and (r.get("tsr") or 0) < 0)
        out.append({"seq": int(r["seq"]), "code": r["code"], "date": j["date"], "rating": j["rating"], "status": r["status"], "days": int(r.get("days") or 0),
                    "wrong": bool(wrong), "tsr": r.get("tsr"), "excess": r.get("excess_osebx"), "patterns": patterns_for(j, r.to_dict(), prices, rows)})
    counts = {}
    for p in PATTERN_WORDS:
        counts[p] = {"all": sum(p in x["patterns"] for x in out), "wrong": sum(p in x["patterns"] for x in out if x["wrong"])}
    return {"rows": out, "counts": counts, "n": len(out), "n_wrong": sum(x["wrong"] for x in out)}


# ------------------------------------------------------------------------------------------------ html
def _f2(v) -> str:
    return f"{v:.2f}" if v is not None else "–"


def by_case_html(bc: list[dict]) -> str:
    from osloquant.dashboard.render import link, pct

    if not bc:
        return ""
    rows = "".join(f'<tr><td>{link(r["code"])}</td><td>{r["n"]}</td><td>{r["n_final"]}</td><td>{_f2(r["brier"])}</td>'
                   f'<td>{pct(r["direction_hit"], 0, False) if r["direction_hit"] is not None else "–"}</td><td>{pct(r["abs_vs_target"], 1, False) if r["abs_vs_target"] is not None else "–"}</td>'
                   f'<td>{pct(r["stated"], 0, False) if r["stated"] is not None else "–"}</td></tr>' for r in bc)
    plot = ""
    pairs = [p for r in bc for p in r["pairs"]]
    if pairs:
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color="#9aa7b5", dash="dot"), name="perfekt", showlegend=False))
        for r in bc:
            if not r["pairs"]:
                continue
            fig.add_trace(go.Scatter(x=[p["p"] for p in r["pairs"]], y=[1.0 if p["happened"] else 0.0 for p in r["pairs"]], mode="markers",
                                     marker=dict(size=10), name=r["code"], text=[f'#{p["seq"]} {p["scenario"]}' for p in r["pairs"]]))
        fig.update_layout(height=300, margin=dict(l=40, r=20, t=20, b=40), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#5c6770"), xaxis=dict(title="Oppgitt sannsynlighet", range=[0, 1], tickformat=".0%"),
                          yaxis=dict(title="Skjedde (1) / skjedde ikke (0)", range=[-0.1, 1.1]))
        plot = fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})
    return ('<h2>Per case: Brier og oppgitt sannsynlighet mot utfall</h2><div class="card"><table class="odds"><thead><tr><th>Case</th><th>Vurderinger</th><th>Endelige</th>'
            f'<th>Brier (scenario)</th><th>Retning riktig</th><th>Bom mot kursmål, snitt</th><th>Oppgitt p for det som skjedde</th></tr></thead><tbody>{rows}</tbody></table>{plot}'
            '<div class="src">Brier per vurdering = sum over bear/base/bull av (oppgitt p − utfall)²; 0 er perfekt, 0.67 er å si en tredjedel om alt. Bare endelige vurderinger '
            '(horisonten passert) har et utfall. Punkter per case: hvert scenario i hver endelige vurdering, oppgitt p mot om det var scenarioet som lå nærmest sluttkursen.</div></div>')


def patterns_html(ep: dict) -> str:
    from osloquant.dashboard.render import E, cls, link, pct

    if not ep.get("n"):
        return ('<h2>Feilmønster</h2><div class="card"><p class="empty">Ingen vurdering er scoret ennå. Rapporten fylles etter hvert som vurderinger får kurser etter seg; '
                'den sier først noe med ti eller flere feil.</p></div>')
    cnt = "".join(f'<tr><td>{E(PATTERN_WORDS[p])}</td><td>{c["wrong"]} av {ep["n_wrong"]}</td><td>{c["all"]} av {ep["n"]}</td></tr>' for p, c in ep["counts"].items() if c["all"])
    rows = "".join(f'<tr><td>#{r["seq"]}</td><td>{link(r["code"])}</td><td>{dato(r["date"])}</td><td>{E(r["rating"])}</td><td>{E(r["status"])} ({r["days"]} d)</td>'
                   f'<td class="{cls(r["excess"])}">{pct(r["excess"])}</td><td>{("feil" if r["status"] == "final" else "feil så langt") if r["wrong"] else ("rett" if r["status"] == "final" else "rett så langt")}</td>'
                   f'<td style="white-space:normal">{", ".join(PATTERN_WORDS[p] for p in r["patterns"]) or "–"}</td></tr>' for r in ep["rows"])
    return (f'<h2>Feilmønster: {ep["n_wrong"]} feil av {ep["n"]} scorede vurderinger</h2><div class="card">'
            '<table class="odds"><thead><tr><th>Mønster</th><th>Blant feilene</th><th>Blant alle</th></tr></thead><tbody>' + (cnt or '<tr><td colspan=3 class=empty>ingen mønstre funnet</td></tr>') + '</tbody></table>'
            '<h3 style="margin-top:12px">Per vurdering</h3><table class="odds"><thead><tr><th>#</th><th>Case</th><th>Dato</th><th>Syn</th><th>Status</th><th>Mot OSEBX</th><th>Rett/feil</th><th>Mønstre</th></tr></thead>'
            f'<tbody>{rows}</tbody></table><div class="src">Feil = retningen mot OSEBX var gal, eller en endelig vurdering endte under kursen uten å nå målet. Mønstrene er regler på loggen og kursbanen '
            '(justerte sluttkurser, forsinket); «guiding» er et ordtreff i begrunnelsen og et spørsmål, ikke en dom. Provisoriske vurderinger kan snu.</div></div>')
