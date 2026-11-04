"""Inversion (DECISIONS D51), after Munger – "invert, always invert": for every full case, what has to go wrong for a
30 % loss from today's price, read from the model's own sensitivity tables, never from free text.

The Toolkit workbook carries two DCF grids the dashboard can read without Excel (cached values, ``openpyxl``):

- *growth × margin* (Sensitivity table 3): value per share when the annual volume / like-for-like growth and the
  EBITDA margin are shifted by whole percentage points in every forecast year, the base case in the corner;
- *terminal growth × WACC* (table 1): value per share at other discount rates and long-run growth.

The loss line is 70 % of the last close in the store. Along each axis alone (the other at the base) the shift that
reaches it is interpolated between grid points – never extrapolated: a line the grid does not reach is reported as
"not within the table" with the grid's edge. The cheapest combinations inside the grid are listed too, measured in
grid steps. The result says what the model says, at the model's date; the price is the store's (delayed).
"""

from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path

E = html.escape
LOSS = 0.30


def read_grids(xlsx: str | Path, cmap: str | Path) -> dict:
    """Both grids from the workbook: {name: {rows, cols, values, row_label, col_label, base}} plus the model's dates."""
    import openpyxl

    m = json.loads(Path(cmap).read_text(encoding="utf8"))
    s, cells = m["sens"], m["cells"]
    wb = openpyxl.load_workbook(Path(xlsx), data_only=True, read_only=True)
    ws = wb["Sensitivity"]

    def grid(hdr: int, rows: list[int]) -> dict:
        cols, c = [], 4
        while (v := ws.cell(hdr, c).value) is not None and isinstance(v, (int, float)):
            cols.append(float(v))
            c += 1
        rlabels = [float(ws.cell(r, 3).value) for r in range(rows[0], rows[1] + 1)]
        vals = [[ws.cell(r, 4 + j).value for j in range(len(cols))] for r in range(rows[0], rows[1] + 1)]
        return {"rows": rlabels, "cols": cols, "values": [[float(x) if isinstance(x, (int, float)) else None for x in row] for row in vals],
                "corner": ws.cell(hdr, 3).value}

    def cell(key):
        sh, ref = key.split("|")[0], cells[key]
        return wb[sh][ref].value

    out = {"growth_margin": grid(s["t3_hdr"], s["t3_rows"]) | {"row_label": "vekst (pp per år)", "col_label": "EBITDA-margin (pp)", "kind": "shift"},
           "g_wacc": grid(s["t1_hdr"], s["t1_rows"]) | {"row_label": "langsiktig vekst", "col_label": "WACC", "kind": "level"}}
    out["dcf_ps"] = cell("DCF|dcf_ps")
    out["wacc"] = cell("WACC|wacc")
    out["model_date"] = str(cell("Inputs|val_date"))[:10]
    out["model_price"] = cell("Inputs|price")
    wb.close()
    return out


def _cross(xs: list[float], ys: list[float], level: float) -> float | None:
    """The x where the piecewise-linear line through (xs, ys) first reaches ``level`` going away from the base, or None."""
    for (x0, y0), (x1, y1) in zip(zip(xs, ys, strict=True), list(zip(xs, ys, strict=True))[1:], strict=False):
        if y0 is None or y1 is None:
            continue
        if (y0 - level) * (y1 - level) <= 0 and y0 != y1:
            return x0 + (level - y0) * (x1 - x0) / (y1 - y0)
    return None


def _axis(values: list[float | None], labels: list[float], base_i: int, level: float) -> dict:
    """From the base point outwards in the direction that lowers the value: the label where the value reaches level."""
    down = list(range(base_i, -1, -1)) if (values[0] or 0) < (values[-1] or 0) else list(range(base_i, len(values)))
    xs, ys = [labels[i] for i in down], [values[i] for i in down]
    x = _cross(xs, ys, level)
    return {"at": x, "edge": xs[-1], "edge_value": ys[-1]}


def invert(g: dict, price: float, loss: float = LOSS) -> dict:
    """What it takes, in the model, to be worth ``(1 - loss) x price``."""
    level = price * (1 - loss)
    out = {"price": price, "level": level, "loss": loss, "model_date": g.get("model_date"), "dcf_ps": g.get("dcf_ps"), "single": [], "combos": []}
    gm = g["growth_margin"]
    r0, c0 = gm["rows"].index(0.0) if 0.0 in gm["rows"] else len(gm["rows"]) // 2, gm["cols"].index(0.0) if 0.0 in gm["cols"] else len(gm["cols"]) // 2
    col = [gm["values"][i][c0] for i in range(len(gm["rows"]))]
    row = gm["values"][r0]
    for name, vals, labels, base_i in (("vekst", col, gm["rows"], r0), ("EBITDA-margin", row, gm["cols"], c0)):
        a = _axis(vals, labels, base_i, level)
        out["single"].append({"driver": name, "unit": "pp", "shift": a["at"], "edge": a["edge"], "edge_value": a["edge_value"]})
    tw = g["g_wacc"]
    gi = min(range(len(tw["rows"])), key=lambda i: abs(tw["rows"][i] - 0.02)) if tw["rows"] else 0
    wi = min(range(len(tw["cols"])), key=lambda j: abs(tw["cols"][j] - (g.get("wacc") or tw["cols"][len(tw["cols"]) // 2])))
    a = _axis(tw["values"][gi], tw["cols"], wi, level)
    out["single"].append({"driver": "WACC", "unit": "level", "shift": a["at"], "edge": a["edge"], "edge_value": a["edge_value"], "base": tw["cols"][wi]})
    a = _axis([tw["values"][i][wi] for i in range(len(tw["rows"]))], tw["rows"], gi, level)
    out["single"].append({"driver": "langsiktig vekst", "unit": "level", "shift": a["at"], "edge": a["edge"], "edge_value": a["edge_value"], "base": tw["rows"][gi]})
    steps_r = (gm["rows"][1] - gm["rows"][0]) or 1
    steps_c = (gm["cols"][1] - gm["cols"][0]) or 1
    for i, dg in enumerate(gm["rows"]):
        for j, dm in enumerate(gm["cols"]):
            v = gm["values"][i][j]
            if v is not None and v <= level and (dg < 0 or dm < 0):
                out["combos"].append({"growth": dg, "margin": dm, "value": v, "steps": abs(dg / steps_r) + abs(dm / steps_c)})
    out["combos"] = sorted(out["combos"], key=lambda x: (x["steps"], -x["value"]))[:3]
    return out


def for_case(c, price: float | None) -> dict | None:
    """The inversion of a book case with a model, or None (no model, no price); {"error": ...} when the model cannot be read."""
    model = getattr(c, "model", None) if c else None
    if not model or not model.get("xlsx") or not model.get("map") or not price:
        return None
    x, m = Path(model["xlsx"]).expanduser(), Path(model["map"]).expanduser()
    if not x.exists() or not m.exists():
        return {"error": f"model file not found: {x if not x.exists() else m}"}
    try:
        return invert(_grids_cached(str(x), str(m), x.stat().st_mtime, m.stat().st_mtime), price) | {"file": x.name}
    except Exception as e:  # noqa: BLE001 – a model without the tables is reported, not hidden
        return {"error": f"the sensitivity tables could not be read: {type(e).__name__}: {e}"}


@lru_cache(maxsize=16)
def _grids_cached(x: str, m: str, _mx: float, _mm: float) -> dict:
    """The grids per workbook version (the file times are part of the key, so a rebuilt model is read again)."""
    return read_grids(x, m)


def _pp(v) -> str:
    return f"{v * 100:+.1f} pp"


def block_html(inv: dict | None, code: str) -> str:
    if not inv:
        return ""
    if inv.get("error"):
        return f'<h2>Invertering: hva gir et tap på 30 %?</h2><div class="card"><p class="err">{E(inv["error"])}</p></div>'
    items = []
    for s in inv["single"]:
        if s["shift"] is None:
            edge = _pp(s["edge"]) if s["unit"] == "pp" else f'{s["edge"] * 100:.1f} %'
            items.append(f'<li>{E(s["driver"])} alene: <b>ikke innenfor tabellen</b> (ved {edge} er verdien {s["edge_value"]:.1f})</li>')
        elif s["unit"] == "pp":
            items.append(f'<li>{E(s["driver"])} alene: <b>{_pp(s["shift"])}</b> i hvert prognoseår, alt annet som i basis</li>')
        else:
            items.append(f'<li>{E(s["driver"])} alene: <b>{s["shift"] * 100:.2f} %</b> (basis {s["base"] * 100:.2f} %)</li>')
    combos = "".join(f'<li>vekst {_pp(x["growth"])} og EBITDA-margin {_pp(x["margin"])} sammen: verdi {x["value"]:.1f}</li>' for x in inv["combos"]) or "<li class=empty>ingen innenfor tabellen</li>"
    return (f'<h2>Invertering: hva gir et tap på 30 %?</h2><div class="card"><p>Munger: snu problemet. Fra kursen {inv["price"]:.2f} til <b>{inv["level"]:.2f}</b> '
            f'(−30 %) må ett av dette skje i modellen ({E(code)}, {E(inv.get("file", ""))}, verdsatt {E(str(inv["model_date"]))}, DCF {inv["dcf_ps"]:.1f}):</p>'
            f'<ul>{"".join(items)}</ul><h3>Billigste kombinasjoner i tabellen</h3><ul>{combos}</ul>'
            '<div class="src">Fra modellens følsomhetstabeller (Sensitivity 1 og 3 i Toolkit-arbeidsboken), lineært interpolert mellom tabellpunkter – aldri ekstrapolert. '
            'Modellverdier er estimater (EST); kursen er siste sluttkurs i lageret (Yahoo, forsinket). Er en av linjene det bear-scenarioet ditt allerede beskriver? '
            'Da er det pre-mortem-punktet.</div></div>')
