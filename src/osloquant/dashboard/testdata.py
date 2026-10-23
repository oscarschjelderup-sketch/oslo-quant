"""A frozen copy of real data, so the tests of the outcome odds, the report reader and the insider study give the
same answer every time. It lives outside the repository (``~/osloquant-home/testdata/<date>``, or
``$OSLOQUANT_TESTDATA``): Yahoo's prices and NewsWeb's texts are for private use and are not redistributed. The tests
that need it skip where it is absent (CI); the synthetic tests run everywhere.

    oq freeze-testdata --end 2026-10-22     # write the copy (prices up to that session, the caches, the reports)
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd

from osloquant import judgements as jg
from osloquant import signals as sg

DEFAULT = "2026-10-22"


def default_dir() -> Path:
    env = os.environ.get("OSLOQUANT_TESTDATA")
    return Path(env) if env else Path.home() / "osloquant-home" / "testdata" / DEFAULT


def freeze(dest: Path | None = None, end: str = DEFAULT, panel: bool = True, feeds: tuple[str, ...] = ("insiders", "shorts"),
           reports: bool = True) -> Path:
    dest = dest or default_dir()
    dest.mkdir(parents=True, exist_ok=True)
    if panel:
        P = {k: v.loc[:end] for k, v in sg.load_panel(start="2010-01-01").items()}
        pd.to_pickle(P, dest / "panel.pkl")
        (dest / "names.json").write_text(json.dumps(sg.stock_names(), ensure_ascii=False, indent=1), encoding="utf-8")
    for name in feeds:
        src = jg.home() / "feeds" / f"{name}.json"
        if src.exists():
            shutil.copy2(src, dest / f"{name}.json")
    if reports:
        src = jg.home() / "reports"
        if src.exists():
            shutil.copytree(src, dest / "reports", dirs_exist_ok=True)
    (dest / "README.txt").write_text(
        f"Frozen real data for oslo-quant tests (prices to {end}). Private: Yahoo Finance and Oslo Børs NewsWeb data, "
        "personal use only. Never commit.\n", encoding="utf-8")
    return dest


def load_panel(src: Path | None = None) -> dict[str, pd.DataFrame]:
    return pd.read_pickle((src or default_dir()) / "panel.pkl")


def load_json(name: str, src: Path | None = None) -> dict:
    return json.loads(((src or default_dir()) / f"{name}.json").read_text(encoding="utf-8"))


def available(*files: str, src: Path | None = None) -> bool:
    d = src or default_dir()
    return all((d / f).exists() for f in (files or ("panel.pkl",)))
