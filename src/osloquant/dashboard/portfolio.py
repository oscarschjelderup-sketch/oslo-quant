"""The book seen as one thing: which sector groups the open views sit in, which drivers their kill criteria share,
and the loss at the kill levels summed per group and per driver (DECISIONS D27). The per-view loss limit treats two
views as independent; this page says when they are not.

A kill criterion's driver is read from an explicit tag at the end of the line ("... below 49% [margin]") or, without
one, inferred from its words. The inferred driver is shown as such so the author can overrule it.
"""

from __future__ import annotations

import re

DRIVERS = ("margin", "volume", "pricing", "rates", "fx", "leverage", "competition", "management", "demand", "regulation", "other")
_RULES = (                                   # order matters: "NIBD / EBITDA" is leverage, not margin
    ("leverage", r"debt|leverage|nibd|covenant|gearing|gjeld|equity ratio|cash conversion"),
    ("margin", r"margin|cost|personnel|opex|ebit|ebitda|lønn|kostnad"),
    ("volume", r"volume|growth|openings|open|store|club|members|lfl|like-for-like|roll-?out|pipeline|subscri|vekst|butikk"),
    ("pricing", r"price|pricing|arpm|mix|pris|yield"),
    ("rates", r"interest|rate|rente"),
    ("fx", r"\bfx\b|currency|nok|krone|valuta|sek|eur\b|usd"),
    ("competition", r"competit|market share|konkurr|entrant"),
    ("management", r"management|ceo|cfo|board|ledelse|guidance"),
    ("demand", r"demand|consumer|traffic|footfall|etterspørsel|churn"),
    ("regulation", r"regulat|tax|vat|mva|avgift|licen"),
)
_TAG = re.compile(r"\[(" + "|".join(DRIVERS) + r")\]\s*$", re.I)


def driver_of(criterion: str) -> tuple[str, str]:
    """(driver, how): 'tag' when written in brackets, 'inferred' from the words, 'other' when nothing matches."""
    m = _TAG.search(criterion or "")
    if m:
        return m.group(1).lower(), "tag"
    low = (criterion or "").lower()
    for d, pat in _RULES:
        if re.search(pat, low):
            return d, "inferred"
    return "other", "none"


def open_views(cases) -> list:
    return [c for c in cases if (c.view or {}).get("rating") == "BUY"]


def exposure(cases, groups: dict[str, str], config: dict | None = None) -> dict:
    """Sector groups and kill drivers across the open BUY views, with the loss at the kill levels where the log has
    positions (`loss_at_kill` on the newest row) and the paper sum from the sizing config."""
    views = open_views(cases)
    paper = float((config or {}).get("paper_capital") or 0) or None
    by_group: dict[str, dict] = {}
    by_driver: dict[str, dict] = {}
    per_case = []
    for c in views:
        g = groups.get(c.code, "Other")
        loss = float((c.view or {}).get("loss_at_kill") or 0)
        drivers = []
        for k in c.kill:
            d, how = driver_of(k)
            drivers.append({"criterion": k, "driver": d, "how": how})
            e = by_driver.setdefault(d, {"cases": set(), "criteria": 0, "loss": 0.0})
            e["cases"].add(c.code)
            e["criteria"] += 1
        for d in {x["driver"] for x in drivers}:
            by_driver[d]["loss"] += loss
        e = by_group.setdefault(g, {"cases": set(), "loss": 0.0})
        e["cases"].add(c.code)
        e["loss"] += loss
        per_case.append({"code": c.code, "name": c.name, "group": g, "loss_at_kill": loss or None, "drivers": drivers,
                         "position_value": (c.view or {}).get("position_value")})
    shared = {d: sorted(e["cases"]) for d, e in by_driver.items() if len(e["cases"]) >= 2}
    total_loss = sum(x["loss_at_kill"] or 0 for x in per_case)
    return {"views": len(views), "paper_capital": paper, "total_loss_at_kill": total_loss,
            "total_loss_share": (total_loss / paper) if paper else None,
            "groups": {g: {"cases": sorted(e["cases"]), "loss": e["loss"], "share": (e["loss"] / paper) if paper else None} for g, e in by_group.items()},
            "drivers": {d: {"cases": sorted(e["cases"]), "criteria": e["criteria"], "loss": e["loss"]} for d, e in by_driver.items()},
            "shared_drivers": shared, "per_case": per_case,
            "one_group": len(by_group) == 1 and len(views) >= 2}


def warnings(ex: dict) -> list[str]:
    out = []
    if ex["one_group"]:
        g = next(iter(ex["groups"]))
        out.append(f"All {ex['views']} open BUY views sit in one sector group ({g}).")
    for d, codes in ex["shared_drivers"].items():
        out.append(f"{len(codes)} views can die from the same driver – {d}: {', '.join(codes)}.")
    if ex["total_loss_share"] is not None and ex["total_loss_at_kill"]:
        out.append(f"Loss if every open view reaches its kill level: NOK {ex['total_loss_at_kill']:,.0f} = {ex['total_loss_share'] * 100:.1f} % of the paper sum "
                   "(the per-view limit does not add them up).")
    return [w.replace(",", " ") if "NOK" in w else w for w in out]


def block_html(ex: dict, static: bool = False) -> str:
    from osloquant.dashboard.render import E, link

    if not ex["views"]:
        return ""
    warn = warnings(ex)
    head = ('<div class="warn"><b>Boken som helhet:</b><ul>' + "".join(f"<li>{E(w)}</li>" for w in warn) + '</ul></div>' if warn
            else '<div class="ok">De åpne synene er spredt over mer enn én sektorgruppe og deler ingen kill-driver.</div>')
    rows = "".join(
        f'<tr><td>{link(c["code"], c["name"], static)}</td><td>{E(c["group"])}</td>'
        f'<td>{"–" if c["loss_at_kill"] is None else format(c["loss_at_kill"], ",.0f").replace(",", " ")}</td>'
        f'<td style="white-space:normal">' + ", ".join(f'{E(d["driver"])}{"*" if d["how"] == "inferred" else ""}' for d in c["drivers"]) + '</td></tr>'
        for c in ex["per_case"])
    drv = "".join(f'<tr><td>{E(d)}</td><td>{e["criteria"]}</td><td>{", ".join(link(c, c, static) for c in e["cases"])}</td>'
                  f'<td>{format(e["loss"], ",.0f").replace(",", " ") if e["loss"] else "–"}</td></tr>' for d, e in sorted(ex["drivers"].items(), key=lambda kv: -len(kv[1]["cases"])))
    return (f'<h2>Boken samlet: sektor og felles kill-drivere</h2><div class="card">{head}'
            '<div class="grid2"><div><table class="odds"><thead><tr><th>Case</th><th>Sektorgruppe</th><th>Tap ved kill (NOK)</th><th>Kill-drivere</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div><div><table class="odds"><thead><tr><th>Driver</th><th>Kriterier</th><th>Caser</th><th>Tap ved kill, sum</th></tr></thead>'
            f'<tbody>{drv}</tbody></table></div></div>'
            '<div class="src">* driver lest ut av ordene i kriteriet; skriv [margin], [volume], [pricing], [rates], [fx], [leverage], [competition], '
            '[management], [demand] eller [regulation] på slutten av et kill-kriterium for å sette den selv. Tap ved kill finnes bare for syn logget '
            'med posisjon i skjemaet. To syn som dør av samme driver er én risiko, ikke to.</div></div>')
