"""Research reports (PDF) on the stock page.

The Equity Research Toolkit writes a report per company and edition; its builder copies the PDF, the estimates snapshot
(``estimates_<date>.json``: target, rating, price, DCF value and the estimate rows) and a small ``meta_<date>.json`` into
``~/osloquant-home/cases/reports_pdf/<CODE>/``. This module lists them, reads the latest estimates against the previous
edition, and says when a report's target differs from the view in the research book – which is a decision to take, not a
number to copy (DECISIONS, rapporter 2026-11-02). Nothing here writes except :func:`publish`, which only adds files.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from osloquant import judgements as jg

FNAME = re.compile(r"^(?P<code>[A-Z0-9]+)_Research_Report_(?P<date>\d{4}-\d{2}-\d{2})\.pdf$")
SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.pdf$")
EST_ROWS = (("rev", "Revenue", 0), ("ebitdaal", "EBITDA after leases", 0), ("ebit_adj", "EBIT adj.", 0), ("eps", "EPS", 2))
TP_TOL = 0.5          # NOK; a report target this close to the view's target is the same target


def root() -> Path:
    return jg.home() / "cases" / "reports_pdf"


def folder(code: str) -> Path:
    return root() / code.upper()


def safe_name(name: str) -> bool:
    return bool(SAFE.match(name or "")) and ".." not in name


def publish(code: str, pdf: Path, estimates: Path | None = None, meta: dict | None = None) -> Path:
    """Copy a report and its estimates snapshot into the home folder (add-only; an existing file of the same name is
    replaced only if the new one differs). Returns the folder."""
    code = code.upper()
    m = FNAME.match(Path(pdf).name)
    if not m or m.group("code") != code:
        raise ValueError(f"the file name must be {code}_Research_Report_YYYY-MM-DD.pdf, got {Path(pdf).name}")
    d = folder(code)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, d / Path(pdf).name)
    if estimates is not None:
        shutil.copyfile(estimates, d / f"estimates_{m.group('date')}.json")
    if meta is not None:
        (d / f"meta_{m.group('date')}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return d


def _json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pages_of(pdf: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:  # noqa: BLE001 – a page count is a convenience, never a reason to fail
        return None


def entries(code: str) -> list[dict]:
    """Every report for ``code``, newest first, with what its sidecar files say."""
    d = folder(code)
    if not d.exists():
        return []
    out = []
    for pdf in sorted(d.glob("*.pdf")):
        m = FNAME.match(pdf.name)
        if not m:
            continue
        date = m.group("date")
        est = _json(d / f"estimates_{date}.json") or {}
        meta = _json(d / f"meta_{date}.json") or {}
        out.append({"code": code.upper(), "date": date, "file": pdf.name, "path": pdf, "size_kb": round(pdf.stat().st_size / 1024),
                    "tp": est.get("tp"), "rating": est.get("rating"), "price": est.get("price"), "price_date": est.get("price_date"),
                    "dcf": est.get("dcf_ps"), "model_date": est.get("model_date"), "estimates": est or None,
                    "kind": meta.get("kind"), "title": meta.get("title"), "pages": meta.get("pages") or pages_of(pdf),
                    "gate_ok": meta.get("gate_ok"), "built": meta.get("built"), "url": f"/reports/{code.upper()}/{pdf.name}"})
    return sorted(out, key=lambda e: e["date"], reverse=True)


def latest(code: str) -> dict | None:
    e = entries(code)
    return e[0] if e else None


def revision(ents: list[dict]) -> dict | None:
    """The newest edition against the one before it: target, rating, price, DCF and the first three estimate years of
    revenue, EBITDA after leases, EBIT adj. and EPS – old, new and the change. None with fewer than two editions."""
    withest = [e for e in ents if e.get("estimates")]
    if len(withest) < 2:
        return None
    new, old = withest[0]["estimates"], withest[1]["estimates"]
    rows = []
    ny, oy = new.get("years") or [], old.get("years") or []
    for key, label, dec in EST_ROWS:
        nv, ov = (new.get("rows") or {}).get(key) or [], (old.get("rows") or {}).get(key) or []
        for i, y in enumerate(ny[:3]):
            n = nv[i] if i < len(nv) else None
            o = ov[oy.index(y)] if y in oy and oy.index(y) < len(ov) else None
            chg = (n / o - 1) if isinstance(n, (int, float)) and isinstance(o, (int, float)) and o else None
            rows.append({"label": label, "year": y, "new": n, "old": o, "chg": chg, "dec": dec})
    return {"new_date": withest[0]["date"], "old_date": withest[1]["date"], "rows": rows,
            "tp": (old.get("tp"), new.get("tp")), "rating": (old.get("rating"), new.get("rating")),
            "price": (old.get("price"), new.get("price")), "dcf": (old.get("dcf_ps"), new.get("dcf_ps"))}


def tp_mismatch(entry: dict | None, view: dict | None, history: list[dict] | None = None) -> dict | None:
    """The newest report's target against the research-book view when the report is newer than the view and no
    judgement has been logged on or after the report date. A differing target or rating is a decision to take."""
    if not entry or not view or not view.get("target") or entry.get("tp") is None:
        return None
    vdate = str(view.get("date") or "")[:10]
    if vdate and entry["date"] < vdate:
        return None
    if any(r.get("kind") == "judgement" and str(r.get("date", ""))[:10] >= entry["date"] for r in (history or [])):
        return None
    tp_r, tp_v = float(entry["tp"]), float(view["target"])
    same_tp = abs(tp_r - tp_v) < TP_TOL
    same_rating = (entry.get("rating") or view.get("rating")) == view.get("rating")
    if same_tp and same_rating:
        return None
    return {"report_tp": tp_r, "report_date": entry["date"], "report_rating": entry.get("rating"), "file": entry["file"], "url": entry["url"],
            "view_tp": tp_v, "view_date": vdate, "view_rating": view.get("rating"), "diff": tp_r / tp_v - 1}


# ------------------------------------------------------------------------------------------------ html
def block_html(code: str, ents: list[dict], rev: dict | None, mismatch: dict | None) -> str:
    from osloquant.dashboard.render import E, cls, pct

    if not ents:
        return ('<h2>Rapporter</h2><div class="card"><p class="empty">Ingen rapport for selskapet ennå.</p>'
                f'<div class="src">Rapportbyggeren i Equity Research Toolkit legger PDF og estimater i ~/osloquant-home/cases/reports_pdf/{E(code)}/ ved bygg '
                '(build_report.py). Første rapport viser estimatene; den andre viser revisjonen mot den første.</div></div>')
    rows = "".join(
        f'<tr><td><a href="{E(e["url"])}" target="_blank" rel="noopener">{E(e["date"])}</a></td><td>{E(e.get("kind") or "–")}</td>'
        f'<td>{E(e.get("rating") or "–")}</td><td>{_g(e.get("tp"))}</td><td>{_n(e.get("dcf"), 1)}</td>'
        f'<td>{_px(e)}</td>'
        f'<td>{e["pages"] if e.get("pages") else "–"}</td><td>{"✓" if e.get("gate_ok") else ("–" if e.get("gate_ok") is None else "✗")}</td>'
        f'<td class="src">{E(e["file"])} · {e["size_kb"]} kB</td></tr>' for e in ents)
    table = ('<table class="odds"><thead><tr><th>Dato</th><th>Utgave</th><th>Syn</th><th>Kursmål</th><th>DCF</th><th>Kurs (dato)</th><th>Sider</th><th>Port</th><th>Fil</th></tr></thead>'
             f'<tbody>{rows}</tbody></table>')
    mm = ""
    if mismatch:
        mm = (f'<div class="warn"><b>Rapporten av {E(mismatch["report_date"])} har kursmål {mismatch["report_tp"]:g} ({E(mismatch["report_rating"] or "")}) – '
              f'vurderingen i research book sier {mismatch["view_tp"]:g} ({E(mismatch["view_rating"] or "")}, {E(mismatch["view_date"])}).</b> '
              f'Avvik {pct(mismatch["diff"])}. Rapporten endrer ikke research book: logg en ny vurdering i skjemaet under (også om du holder på {mismatch["view_tp"]:g}) '
              'og skriv hvorfor du avviker fra rapporten, eller følger den.</div>')
    rv = ""
    if rev:
        rrows = "".join(f'<tr><td>{E(r["label"])}</td><td>{r["year"]}</td><td>{_n(r["old"], r["dec"])}</td><td>{_n(r["new"], r["dec"])}</td>'
                        f'<td class="{cls(r["chg"])}">{pct(r["chg"])}</td></tr>' for r in rev["rows"] if r["new"] is not None or r["old"] is not None)
        head = (f'Kursmål {_n(rev["tp"][0], 0)} → <b>{_n(rev["tp"][1], 0)}</b> ({E(rev["rating"][0] or "")} → {E(rev["rating"][1] or "")}), '
                f'DCF {_n(rev["dcf"][0], 1)} → {_n(rev["dcf"][1], 1)}, kurs {_n(rev["price"][0], 2)} → {_n(rev["price"][1], 2)}.')
        rv = (f'<h3 style="margin-top:12px">Siste estimat mot forrige ({E(rev["old_date"])} → {E(rev["new_date"])})</h3><p>{head}</p>'
              '<table class="odds"><thead><tr><th>Linje</th><th>År</th><th>Forrige</th><th>Siste</th><th>Endring</th></tr></thead>'
              f'<tbody>{rrows}</tbody></table><div class="src">Estimater merket EST i rapporten; NOKm, EPS i NOK. Fra estimates_&lt;dato&gt;.json ved siden av PDF-ene.</div>')
    return (f'<h2>Rapporter</h2><div class="card">{mm}{table}{rv}'
            '<div class="src">PDF-ene åpnes fra ~/osloquant-home/cases/reports_pdf/ (privat). Kursmål, DCF og kurs fra rapportens estimatfil; «Port» = byggeporten '
            '(verify_dcf, audit, case gate, stress) bestått da rapporten ble bygget.</div></div>')


def _g(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else "–"


def _px(e: dict) -> str:
    from osloquant.dashboard.render import E

    return f'{e["price"]:.2f} ({E(str(e.get("price_date") or "")[:10])})' if isinstance(e.get("price"), (int, float)) else "–"


def _n(v, d=0) -> str:
    if not isinstance(v, (int, float)):
        return "–"
    return f"{v:,.{d}f}".replace(",", " ")
