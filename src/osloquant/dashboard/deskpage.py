"""HTML for the desk (D41): today's run with its counts and data quality, the debate log per stock in the order it
happened, the veto statistic over time, and the blocks the stock page and the front page carry. Server-rendered like
the rest of the dashboard; nothing here computes a number – it shows what ``desk.py`` logged."""

from __future__ import annotations

import pandas as pd

from osloquant.dashboard import desk as dk
from osloquant.dashboard.dates import dato, klokke, stempel
from osloquant.dashboard.render import E, link, page

ROLE_LABEL = {"scout": "Speider", "filter": "Filter", "analyst": "Analytiker", "bear": "Bjørn", "reply": "Analytikeren svarer", "risk": "Risk", "desk": "Desk"}
ROLE_JOB = {"scout": "flagger det uvanlige i dag, med tall", "filter": "dreper det som ikke passer prosessen", "analyst": "hva markedet priser inn, odds, siste rapport mot caset",
            "bear": "minst tre grunner mot kjøp, hver med tall og kilde", "reply": "tilsvar med tall – eller grunnen står og er veto", "risk": "størrelse ved maks tap, sektorandel, hendelser"}
OUTCOME_CLASS = {"killed": "plain", "parked": "risk", "ready": "buy"}
INTRO = ("Seks roller går gjennom en aksje før du vurderer den, hver med én jobb og ett fast utdataformat: ingen rolle skriver fritekst, hvert funn er en påstand "
         "med tall, kilde og tidspunkt, og alt logges. Bjørnen må ha tre grunner; én grunn som ikke kan tilbakevises med tall er veto. Kjeden ender aldri i et kjøp "
         "– den ender i <b>klar for vurdering</b> (skjemaet åpnes forhåndsutfylt med debatten vedlagt), <b>parkert</b> (vetoet står) eller <b>drept</b> (filterets grunn). "
         "Papirpenger; beslutningen er din.")


def _chip(status: str | None, role: str) -> str:
    if status is None:
        return ""
    words = {("filter", "killed"): ("drept", "risk"), ("bear", "rebutted"): ("tilbakevist", "plain"), ("bear", "stands"): ("står – veto", "risk"),
             ("reply", "rebuts"): ("tilsvar med tall", "buy"), ("reply", "stands"): ("ingen tilsvar", "risk"), ("risk", "blocked"): ("blokkert", "risk"),
             ("desk", "killed"): ("drept", "plain"), ("desk", "parked"): ("parkert", "risk"), ("desk", "ready"): ("klar for vurdering", "buy")}
    w, c = words.get((role, status), (status, "plain"))
    return f'<span class="chip {c}">{E(w)}</span>'


def _marks(f: dk.Finding) -> str:
    return ("" if not f.est else ' <span class="chip plain">EST</span>') + ("" if not f.delayed else ' <span class="chip plain">forsinket/buffer</span>')


def log_table(sr: dk.StockRun) -> str:
    """The debate log, chronological: #, time, role, claim, number, source and data time, status."""
    rows = []
    for i, f in enumerate(sr.findings):
        ref = f' <span class="src">→ grunn #{f.ref + 1}</span>' if f.ref is not None else ""
        detail = f'<div class="src">«{E(f.detail[:240])}»</div>' if f.detail and f.role != "desk" else (f'<div class="src">{E(f.detail[:240])}</div>' if f.detail else "")
        rows.append(f'<tr class="r-{E(f.role)}"><td>{i + 1}</td><td class="src">{E(f.t[11:19] if len(f.t) >= 19 else f.t)}</td><td><b>{E(ROLE_LABEL.get(f.role, f.role))}</b></td>'
                    f'<td style="white-space:normal">{E(f.claim)}{ref}</td><td style="white-space:normal;text-align:left">{E(f.value)}{_marks(f)}{detail}</td>'
                    f'<td class="src" style="white-space:normal;text-align:left">{E(f.source)}<br>per {E(f.asof)}</td><td style="text-align:left">{_chip(f.status, f.role)}</td></tr>')
    return ('<table class="odds desklog"><thead><tr><th>#</th><th>Tid (UTC)</th><th>Rolle</th><th>Påstand</th><th>Tall</th><th>Kilde · tidspunkt for dataene</th><th>Status</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _style() -> str:
    return ('<style>table.desklog td, table.desklog th { vertical-align:top; } table.desklog tr.r-bear td { background:var(--risk-bg); } '
            'table.desklog tr.r-reply td { background:var(--info-bg); } table.desklog tr.r-desk td { font-weight:600; border-top:2px solid var(--accent); } '
            '.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:12px; margin:8px 0 12px; } '
            '.tile { border-top:2px solid var(--accent); padding:6px 0; } .tile .v { font-size:24px; font-weight:700; } .tile .l { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.4px; }</style>')


def stock_section(sr: dk.StockRun, run: dk.DeskRun, static: bool = False, full: bool = True) -> str:
    L = link(sr.code, f"{sr.name} ({sr.code})", static)
    price = f'Kurs {sr.price:.2f} ({E(sr.price_date or "")}, forsinket)' if sr.price else 'Ingen kurs i lageret'
    head = (f'<h2 id="{E(sr.code)}">{L} · {E(sr.group)} <span class="chip {OUTCOME_CLASS.get(sr.outcome, "plain")}">{E(dk.OUTCOME_LABEL.get(sr.outcome, sr.outcome))}</span></h2>'
            f'<div class="sub">{price}' + (f' · kursmål {sr.target:g}' if sr.target else '') + (f' · kill-nivå {sr.kill:g} ({E(sr.kill_source or "")})' if sr.kill else '') + '.</div>')
    why = f'<div class="{"err" if sr.outcome != "ready" else "ok"}"><b>{E(dk.OUTCOME_LABEL.get(sr.outcome, ""))}:</b> {E(sr.reason) if sr.reason else "alle grunner tilbakevist med tall, ingen grense brutt – skjemaet åpnes forhåndsutfylt."}</div>'
    act = ""
    if not static:
        if sr.outcome == "ready":
            act = f'<p><a class="chip buy" style="padding:8px 16px;font-size:13px" href="/stock/{E(sr.code)}?desk={E(run.run_id)}#judge">Åpne vurderingsskjemaet for {E(sr.code)} forhåndsutfylt, med debatten vedlagt →</a></p>'
        else:
            act = (f'<p class="src">Vurderingen er likevel din: <a href="/stock/{E(sr.code)}?desk={E(run.run_id)}#judge">åpne skjemaet med denne loggen vedlagt</a> '
                   f'– den merkes med desk-kjøringen og grunnen over.</p>')
    body = log_table(sr) if full else f'<p class="src">{len(sr.findings)} funn – <a href="/desk/run/{E(run.run_id)}/{E(sr.code)}">hele debattloggen</a>.</p>'
    return head + why + act + body


def short_reason(text: str | None) -> str:
    """The deciding finding in one line: runs stored before 5 Nov 2026 carried the bear's source list in the text."""
    t = (text or "").split("; kildene gjennomgått")[0]
    return t[:200]


def quality_html(run: dk.DeskRun) -> str:
    items = "".join(f'<li>{"✓" if q["ok"] else "✗"} {E(q["what"])}: {E(str(q["asof"])[:19])}' + (f' – {E(q["note"])}' if q.get("note") else "") + '</li>' for q in run.data_quality)
    bad = sum(not q["ok"] for q in run.data_quality)
    return f'<details{" open" if bad else ""}><summary>Datakvalitet: {len(run.data_quality) - bad} av {len(run.data_quality)} kilder i orden</summary><ul>{items}</ul></details>'


def run_header(run: dk.DeskRun, static: bool = False) -> str:
    share = run.killed / run.flagged if run.flagged else None
    tiles = [("Skannet", run.scanned), ("Flagget", run.flagged), ("Drept", run.killed), ("Debattert", run.debated), ("Parkert", run.parked), ("Klar", run.ready)]
    t = "".join(f'<div class="tile"><div class="v">{v}</div><div class="l">{E(k)}</div></div>' for k, v in tiles)
    when = stempel(run.finished_at)
    def row(s: dk.StockRun) -> str:
        log = "" if static else f'<a href="/desk/run/{E(run.run_id)}/{E(s.code)}">logg</a>'
        return (f'<tr><td>{link(s.code, s.code, static)}</td><td>{E(s.name)}</td><td>{E(s.group)}</td><td><span class="chip {OUTCOME_CLASS.get(s.outcome, "plain")}">{E(dk.OUTCOME_LABEL.get(s.outcome, ""))}</span></td>'
                f'<td style="white-space:normal;text-align:left">{E(short_reason(s.reason)) or "–"}</td><td>{log}</td></tr>')

    rows = "".join(row(s) for s in sorted(run.stocks, key=lambda s: (dk.OUTCOMES.index(s.outcome) if s.outcome in dk.OUTCOMES else 9, s.code)))
    turnover = f"{float(run.config.get('min_turnover_nok', 0)):,.0f}".replace(",", " ")
    return (f'<div class="tiles">{t}</div>'
            f'<div class="sub">Kjørt {E(when)} ({E(run.trigger)}) på sluttkursene fra {E(run.session)}. '
            + (f'Filteret drepte {share * 100:.0f} % av det speideren flagget (målet er 90 %). ' if share is not None else '')
            + f'Grenser: volum ≥ {run.config.get("volume_ratio")}x · bevegelse mot sektor ≥ {float(run.config.get("move_vs_sector", 0)) * 100:.0f} pp · omsetning ≥ NOK {turnover} · '
              f'rapport innen {run.config.get("report_within_days")} d · sektorandel ≤ {float(run.config.get("max_group_share", 0)) * 100:.0f} % (dashboard.yaml, desk:).</div>'
            + quality_html(run)
            + ('<table><thead><tr><th>Aksje</th><th>Navn</th><th>Sektorgruppe</th><th>Utfall</th><th>Avgjørende funn</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>'
               if run.stocks else '<p class="empty">Speideren flagget ingenting i dag: ingen volum, bevegelse, signal, melding, innsidehandel eller shortendring over grensene.</p>'))


def _pc(x, d: int = 0, sign: bool = False) -> str:
    return "–" if x is None else f"{x * 100:{'+' if sign else ''}.{d}f} %"


def stats_html(st: dict) -> str:
    def col(b: dict) -> str:
        return (f'<td>{b["right"]}</td><td>{b["wrong"]}</td><td>{b["neither"]}</td><td>{b["pending"]}</td><td>{b["unscorable"]}</td>'
                f'<td><b>{_pc(b["share_right"])}</b> <span class="src">av {b["decided"]} avgjorte</span></td>')
    v, th = st["veto"], st["through"]
    verdict = ("ingen avgjorte vetoer ennå – tallet finnes ikke før kursen har nådd kursmål eller kill-nivå etter en kjøring" if not v["decided"] else
               f'vetoene traff i {v["share_right"] * 100:.0f} % av {v["decided"]} avgjorte tilfeller' + (f'; av aksjene desken slapp gjennom nådde {th["share_right"] * 100:.0f} % av {th["decided"]} kill-nivået først' if th["decided"] else "")
               + (" – vetoene har så langt ikke skilt seg fra det som slapp gjennom" if th["decided"] and v["share_right"] is not None and th["share_right"] is not None and v["share_right"] <= th["share_right"] else ""))
    rows = "".join(f'<tr><td>{dato(r["session"])}</td><td>{E(r["code"])}</td><td>{E("veto" if r["group"] == "veto" else "sluppet gjennom")}</td><td style="white-space:normal;text-align:left">{E(str(r.get("veto_kind") or ""))} {E(str(r.get("reason") or "")[:90])}</td>'
                   f'<td>{E(r["result"])}</td><td>{r["sessions"]}</td><td>{_pc(r["change"], 1, True)}</td></tr>' for r in st["rows"][::-1][:200])
    return (f'<p><b>{E(verdict)}.</b></p>'
            '<table class="odds"><thead><tr><th></th><th>Kill-nivå først (veto rett)</th><th>Kursmål først (veto feil)</th><th>Ingen av dem</th><th>Vinduet ikke ferdig</th><th>Ikke målbart</th><th>Andel rett</th></tr></thead>'
            f'<tbody><tr><td>Bjørnens veto</td>{col(v)}</tr><tr><td>Sluppet gjennom (klar)</td>{col(th)}</tr></tbody></table>'
            f'<div class="src">Regel: første daglige sluttkurs (justert, lageret) på eller forbi kill-nivået eller kursmålet innen {st["horizon"]} økter etter kjøringen avgjør; '
            'uten kursmål eller kill-nivå er et veto ikke målbart. Et veto på en aksje som så nådde kill-nivået først, regnes som rett – også om den steg først. '
            'Sammenligningsraden er aksjene desken slapp gjennom til skjemaet, målt likt. Det er dette tallet, og bare dette, som avgjør om desken er verdt noe.</div>'
            + (f'<details><summary>{len(st["rows"])} tilfeller</summary><table class="odds"><thead><tr><th>Kjøring</th><th>Aksje</th><th>Gruppe</th><th>Veto</th><th>Resultat</th><th>Økter</th><th>Kurs siden</th></tr></thead><tbody>{rows}</tbody></table></details>' if st["rows"] else ""))


def desk_page(latest_run: dk.DeskRun | None, runs: list[dict], stats: dict, today: pd.Timestamp, static: bool = False, msg: dict | None = None) -> str:
    roles = "".join(f'<li><b>{E(ROLE_LABEL[r])}</b> – {E(ROLE_JOB[r])}</li>' for r in ("scout", "filter", "analyst", "bear", "reply", "risk"))
    body = [_style(), f'<h1>Desk <span class="code">{dato(today, weekday=True)}</span></h1>', f'<div class="lead">{INTRO}</div>', f'<details><summary>De seks rollene</summary><ul>{roles}</ul></details>']
    if msg:
        body += [f'<div class="err">{E(m)}</div>' for m in msg.get("errors", [])] + [f'<div class="ok">{E(m)}</div>' for m in msg.get("ok", [])]
    body.append('<h2>Dagens kjøring</h2><div class="card">' + (run_header(latest_run, static) if latest_run else '<p class="empty">Ingen kjøring lagret ennå. Den daglige kjøringen går etter børsslutt (oq desk run --daily, i signalvakt-oppgaven); én aksje kjøres under.</p>') + '</div>')
    if not static:
        body.append('<h2>Kjør desk på én aksje</h2><div class="card"><form method="post" action="/desk/run" style="display:flex;gap:8px;align-items:center">'
                    '<input name="code" placeholder="Ticker, f.eks. SATS" style="padding:6px 8px;border:1px solid var(--line);border-radius:2px;font:inherit;width:180px">'
                    '<button class="go" type="submit" style="margin:0">Kjør desk</button></form>'
                    '<div class="src">Aksjen tvinges gjennom alle seks rollene selv om speideren ikke flagget noe. Kjøringen lagres under ~/osloquant-home/desk/ (privat) og rører ikke research book eller vurderingsloggen.</div></div>')
    body.append(f'<h2>Statistikk over tid: traff vetoene?</h2><div class="card">{stats_html(stats)}</div>')
    if runs:
        lst = "".join(f'<li>{dato(r["session"])} · kl. {klokke(r["finished_at"])} · {E(r["trigger"])}: skannet {r["scanned"]}, drept {r["killed"]}, debattert {r["debated"]}, parkert {r["parked"]}, klar {r["ready"]}'
                      + ("" if static else f' – <a href="/desk/run/{E(r["run_id"])}">åpne</a>') + '</li>' for r in runs[:60])
        body.append(f'<h2>Tidligere kjøringer ({len(runs)})</h2><div class="card"><ul class="news">{lst}</ul></div>')
    return page("Desk", "/desk", "\n".join(body), static=static)


def run_page(run: dk.DeskRun) -> str:
    body = [_style(), f'<h1>Desk-kjøring <span class="code">{E(run.run_id)}</span></h1>', '<div class="card">' + run_header(run) + '</div>']
    body += [stock_section(s, run, full=False) for s in run.stocks]
    return page(f"Desk {run.session}", "/desk", "\n".join(body))


def stock_log_page(run: dk.DeskRun, sr: dk.StockRun) -> str:
    body = [_style(), f'<div class="src"><a href="/desk">Desk</a> · <a href="/desk/run/{E(run.run_id)}">kjøring {E(run.run_id)}</a> · sluttkurser {E(run.session)}</div>',
            f'<h1>Debattlogg <span class="code">{E(sr.code)}</span></h1>', stock_section(sr, run, full=True)]
    return page(f"Desk {sr.code}", "/desk", "\n".join(body))


def attached_html(run: dk.DeskRun, sr: dk.StockRun) -> str:
    """The debate attached above the judgement form when it was opened from a run."""
    return (f'<h2>Desken om {E(sr.code)} ({E(run.session)}, {E(run.trigger)}) <span class="chip {OUTCOME_CLASS.get(sr.outcome, "plain")}">{E(dk.OUTCOME_LABEL.get(sr.outcome, ""))}</span></h2>'
            f'<div class="card">{_style()}' + (f'<div class="err"><b>{E(dk.OUTCOME_LABEL.get(sr.outcome, ""))}:</b> {E(sr.reason)}</div>' if sr.outcome != "ready" else "")
            + log_table(sr) + f'<div class="src">Vedlegges raden i vurderingsloggen som desk_run = {E(run.run_id)}. <a href="/desk/run/{E(run.run_id)}/{E(sr.code)}">Loggen alene</a>.</div></div>')


def stock_block(code: str, runs: list[dict], static: bool = False) -> str:
    """On the stock page: the runs that went through the stock, and the button that runs the desk on it."""
    def row(r: dict) -> str:
        log = "" if static else f'<a href="/desk/run/{E(r["run_id"])}/{E(code)}">logg</a>'
        return (f'<tr><td>{dato(r["session"])}</td><td class="src">kl. {klokke(r["finished_at"])} · {E(r["trigger"])}</td><td><span class="chip {OUTCOME_CLASS.get(r["outcome"], "plain")}">{E(dk.OUTCOME_LABEL.get(r["outcome"], ""))}</span></td>'
                f'<td style="white-space:normal;text-align:left">{E(short_reason(r.get("reason")) or "–")}</td><td>{log}</td></tr>')

    rows = "".join(row(r) for r in runs[:12])
    table = (f'<table><thead><tr><th>Sluttkurs</th><th>Kjørt</th><th>Utfall</th><th>Avgjørende funn</th><th></th></tr></thead><tbody>{rows}</tbody></table>' if rows
             else '<p class="empty">Desken har ikke gått gjennom denne aksjen ennå.</p>')
    form = ("" if static else f'<form method="post" action="/desk/run" style="margin-top:8px"><input type="hidden" name="code" value="{E(code)}">'
            f'<button class="go" type="submit" style="margin:0">Kjør desk på {E(code)}</button> <span class="src">seks roller, debattlogg, ingen handel – resultatet lagres og vises her og på Desk-siden.</span></form>')
    return f'<h2>Desk</h2><div class="card">{table}{form}</div>'


def front_block(s: dict | None, static: bool = False) -> str:
    """One block on the front page: today's run in one line, with the codes that came through and were parked."""
    if not s:
        return ('<h2>Desk i dag</h2><div class="card"><p class="empty">Ingen desk-kjøring for denne sluttkursen ennå (oq desk run --daily går etter børsslutt).</p>'
                + ('' if static else '<div class="src"><a href="/desk">Desk-siden</a>: kjør én aksje, se statistikken.</div>') + '</div>')
    L = lambda c: link(c, c, static)  # noqa: E731
    qual = (f' · <span class="k">{len(s["quality_bad"])} kilder med problem</span>' if s.get("quality_bad") else " · datakvalitet i orden")
    return (f'<h2>Desk i dag</h2><div class="card"><p style="margin:4px 0"><b>Skannet {s["scanned"]}, flagget {s["flagged"]}, drept {s["killed"]}, debattert {s["debated"]}, '
            f'parkert {s["parked"]}, klar {s["ready"]}.</b> <span class="src">kl. {klokke(s["finished_at"])} ({E(s["trigger"])}){qual}</span></p>'
            + (f'<div>Klar for vurdering: {", ".join(L(c) for c in s["ready_codes"])}.</div>' if s["ready_codes"] else "")
            + (f'<div class="src">Parkert: {", ".join(L(c) for c in s["parked_codes"])}.</div>' if s["parked_codes"] else "")
            + ('' if static else f'<div class="src"><a href="/desk/run/{E(s["run_id"])}">Hele kjøringen</a> · <a href="/desk">Desk-siden og statistikken</a>.</div>') + '</div>')
