"""Reads a case's toolkit workbook (Equity Research Toolkit) for the stock page: the reverse DCF ("what the market
prices in"), the DCF value and the model date. The paths come from the research book entry's ``model`` key
(``{xlsx: ..., map: ...}``); nothing is copied out of the private case except what the page shows locally."""

from __future__ import annotations

import json
from pathlib import Path


def reverse_dcf(model: dict | None) -> dict | None:
    if not model or not model.get("xlsx") or not model.get("map"):
        return None
    xlsx, cmap = Path(model["xlsx"]).expanduser(), Path(model["map"]).expanduser()
    if not xlsx.exists() or not cmap.exists():
        return {"error": f"model file not found: {xlsx if not xlsx.exists() else cmap}"}
    import openpyxl

    cells = json.loads(cmap.read_text(encoding="utf8"))["cells"]
    wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=False)
    v = lambda key: wb[key.split("|")[0]][cells[key]].value  # noqa: E731
    out = {k: v(f"Reverse_DCF|{k}") for k in ("rd_m_last", "rd_m_last_ours", "rd_m_last_ref", "rd_cagr", "rd_cagr_ours",
                                                "rd_cagr_ref", "rd_wacc", "rd_wacc_ours", "rd_k")}
    out.update(price=v("Inputs|price"), price_date=v("Inputs|price_date"), dcf=v("DCF|dcf_ps"), tp=v("DCF|tp"),
               rating=v("DCF|rating"), wacc=v("WACC|wacc"), model_date=v("Inputs|val_date"), file=str(xlsx.name))
    return out
