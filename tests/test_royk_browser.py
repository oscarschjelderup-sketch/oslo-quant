"""The smoke test (improvement pass 10 Nov 2026): start the dashboard, open every page and every stock tab for two
stocks in a real browser, and fail on a console error, a server error, an empty main field, or the words a broken
template leaves behind. It also checks the two rules of the visual system that only a browser can see: text columns
read from the left and number columns line up on the right, and numbers are in the Norwegian form.

Runs on a synthetic store and a temp home. Skips when the machine has no Chromium browser; the CI runner has Chrome,
and ``websockets`` comes with yfinance."""

from __future__ import annotations

import re

import pytest

from . import browser
from .test_pricechart_browser import (  # noqa: F401  the browser, and the dashboard served on a free port
    TABS,
    chrome,
    live,
)

pytestmark = pytest.mark.skipif(not browser.find(), reason="no Chromium browser (Edge, Chrome or Chromium) on this machine")

PAGES = ("/", "/sectors", "/calendar", "/health", "/calibration", "/funds", "/coverage", "/screen", "/watchlist", "/chief", "/review", "/desk")
SUBS = ("resultat", "balanse", "kontantstrom", "segmenter", "utbytte")
BROKEN = re.compile(r"(?<![\w.])(undefined|NaN|nan|None|\[object Object\]|Traceback|Internal Server Error)(?!\w)")
# what the page looks like to a person: its main text, the tables and cards that are empty, and whether it scrolls sideways
PROBE = """(function(){var w=document.querySelector('.wrap')||document.body;var nav=document.querySelector('nav.top');
var foot=document.querySelector('.foot');var t=w.innerText||'';
return {text:t, body:t.length-(nav?nav.innerText.length:0)-(foot?foot.innerText.length:0), h1:(document.querySelector('h1,.stockbar')||{}).innerText||'',
emptyState:!!document.querySelector('.wrap p.empty, .wrap td.empty'),
emptyCards:Array.from(document.querySelectorAll('.card')).filter(function(c){return c.offsetParent!==null&&c.innerText.trim().length<3&&!c.querySelector('canvas,svg,img,.js-plotly-plot')}).length,
sideways:document.documentElement.scrollWidth>document.documentElement.clientWidth+2, status:(document.title||'')};})()"""


def _urls() -> list[str]:
    out = list(PAGES)
    for code in ("AAA", "BBB"):                          # one with a case and a view, one without
        out += [f"/aksje/{code}/{t}" for t in TABS] + [f"/aksje/{code}/regnskap/{s}" for s in SUBS] + [f"/stock/{code}/pretrade"]
    return out


def test_every_page_opens_with_content_and_without_a_console_error(chrome, live):  # noqa: F811
    base, _ = live
    problems = []
    for url in _urls():
        p = chrome.page()
        try:
            p.goto(base + url, width=1280, height=900)
            p.eval("new Promise(function(r){setTimeout(r, 250)})")
            got = p.eval(PROBE)
            for e in p.errors():
                problems.append(f"{url}: console {e[:160]}")
            if "Noe gikk galt" in got["text"] or "Siden finnes ikke" in got["text"]:
                problems.append(f"{url}: the error page")
            if got["body"] < 200 and not got["emptyState"]:         # a short page is fine when it says what is missing and what to do
                problems.append(f"{url}: the main field is empty ({got['body']} characters) and says nothing about why")
            if not got["h1"].strip():
                problems.append(f"{url}: no heading")
            if got["emptyCards"]:
                problems.append(f"{url}: {got['emptyCards']} empty card(s)")
            if got["sideways"]:
                problems.append(f"{url}: the page scrolls sideways at 1280 px")
            bad = sorted({m.group(1) for m in BROKEN.finditer(got["text"])})
            if bad:
                problems.append(f"{url}: {', '.join(bad)} in the visible text")
        finally:
            p.close()
    assert not problems, "\n" + "\n".join(problems)


def _align(p, table_selector: str) -> list[str]:
    """The computed alignment of each cell in the first body row of a table."""
    return p.eval(f"(function(){{var t=document.querySelector({table_selector!r});if(!t||!t.tBodies.length||!t.tBodies[0].rows.length)return null;"
                  "return Array.from(t.tBodies[0].rows[0].cells).map(function(c){return getComputedStyle(c).textAlign})})()")


def test_text_columns_read_from_the_left_and_number_columns_line_up_on_the_right(chrome, live):  # noqa: F811
    base, _ = live
    p = chrome.page()
    try:
        p.goto(base + "/health")
        cells = _align(p, "#kilder table")                # Kilde, Status, Sist hentet, Sist forsøkt, Feil, Skal hentes, Merknad, Tall som påvirkes
        assert cells is not None and cells[0] in ("left", "start") and cells[1] in ("left", "start") and cells[5] in ("left", "start")
        assert cells[4] in ("right", "end")               # «Feil» is a count
        head = p.eval("Array.from(document.querySelector('#kilder table').tHead.rows[0].cells).map(function(c){return getComputedStyle(c).textAlign})")
        assert head[0] in ("left", "start") and head[4] in ("right", "end")
        p.goto(base + "/sectors")
        got = p.eval("(function(){var t=document.querySelector('table');var r=t.tBodies[0].rows[0];"
                     "return Array.from(r.cells).map(function(c){return [c.innerText.trim(), getComputedStyle(c).textAlign]})})()")
        assert got[0][1] in ("left", "start")             # the ticker
        pct = [a for text, a in got if text.endswith("%")]
        assert pct and all(a in ("right", "end") for a in pct)
    finally:
        p.close()


def test_numbers_and_words_on_the_front_page_are_norwegian(chrome, live):  # noqa: F811
    base, _ = live
    p = chrome.page()
    try:
        p.goto(base + "/")
        text = p.eval("document.querySelector('.wrap').innerText")
        for english in ("reached the target", "days old", "past its horizon", "log your view before", "predates the report", "no new signals",
                        "can die from the same driver", "stale-view", "re-assess", "pre-report"):
            assert english not in text, english
        assert not re.search(r"\d\.\d+\s?%", text)          # no «12.5%» anywhere a person reads
        p.goto(base + "/sectors")
        text = p.eval("document.querySelector('.wrap').innerText")
        assert re.search(r"\d,\d\s%", text) and not re.search(r"\d\.\d+\s?%", text)
    finally:
        p.close()
