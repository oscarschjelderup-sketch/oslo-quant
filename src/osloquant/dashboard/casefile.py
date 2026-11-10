"""Reads a case's toolkit workbook (Equity Research Toolkit) for the stock page: the reverse DCF ("what the market
prices in"), the DCF value and the model date. The paths come from the research book entry's ``model`` key
(``{xlsx: ..., map: ...}``); nothing is copied out of the private case except what the page shows locally."""

from __future__ import annotations

import json
from pathlib import Path

NUMBERS = ("rd_m_last", "rd_m_last_ours", "rd_m_last_ref", "rd_cagr", "rd_cagr_ours", "rd_cagr_ref", "rd_wacc", "rd_wacc_ours", "rd_k",
           "price", "dcf", "tp", "wacc")


def _number(v):
    """A cell as a number, or None. The Toolkit sheet itself writes text ("n.a.", "outside range") in a number cell when
    the price lies outside its solver tables, and a workbook saved without cached values has None everywhere."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        return None if v != v else float(v)
    return None


def reverse_dcf(model: dict | None) -> dict | None:
    """The reverse DCF and the DCF value from the case's workbook, or ``{"error": ...}`` when it cannot be read. Every
    key in ``NUMBERS`` is a float or None; the text a number cell held instead is kept in ``notes`` for the card."""
    if not model or not model.get("xlsx") or not model.get("map"):
        return None
    xlsx, cmap = Path(model["xlsx"]).expanduser(), Path(model["map"]).expanduser()
    if not xlsx.exists() or not cmap.exists():
        return {"error": f"modellfilen finnes ikke: {xlsx if not xlsx.exists() else cmap}"}
    try:
        import openpyxl

        cells = json.loads(cmap.read_text(encoding="utf8"))["cells"]
        wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=False)
    except Exception as e:  # noqa: BLE001 – a private file in any state must not take the stock page down
        return {"error": f"modellfilen {xlsx.name} kunne ikke leses ({type(e).__name__}: {str(e)[:120]})"}
    keys = {k: f"Reverse_DCF|{k}" for k in ("rd_m_last", "rd_m_last_ours", "rd_m_last_ref", "rd_cagr", "rd_cagr_ours", "rd_cagr_ref", "rd_wacc",
                                             "rd_wacc_ours", "rd_k")}
    keys.update(price="Inputs|price", price_date="Inputs|price_date", dcf="DCF|dcf_ps", tp="DCF|tp", rating="DCF|rating", wacc="WACC|wacc",
                model_date="Inputs|val_date")
    missing = [k for k, key in keys.items() if key not in cells or key.split("|")[0] not in wb.sheetnames]
    if missing:
        return {"error": f"kartet {cmap.name} mangler {', '.join(missing)} – modellen og kartet hører ikke sammen"}
    try:
        raw = {k: wb[key.split("|")[0]][cells[key]].value for k, key in keys.items()}
    except Exception as e:  # noqa: BLE001
        return {"error": f"modellfilen {xlsx.name} kunne ikke leses ({type(e).__name__}: {str(e)[:120]})"}
    out = {k: (_number(v) if k in NUMBERS else v) for k, v in raw.items()}
    out["notes"] = {k: str(v) for k, v in raw.items() if k in NUMBERS and isinstance(v, str) and v.strip()}
    out["file"] = str(xlsx.name)
    return out
