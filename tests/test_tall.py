"""Numbers in one Norwegian form (docs/forbedring/endringer.md E12, DECISIONS D61): what the last pass changes, and
everything it must leave alone."""

from __future__ import annotations

import pytest

from osloquant.dashboard.tall import MINUS, NBSP, THIN, heltall, norske_tall, prosent, tall

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home


@pytest.mark.parametrize(("before", "after"), [
    ("+14.5%", f"+14,5{NBSP}%"),
    ("-2.8%", f"{MINUS}2,8{NBSP}%"),
    ("WACC EST 9.5 %", f"WACC EST 9,5{NBSP}%"),
    ("100%", f"100{NBSP}%"),
    ("kurs 45.50 (9. nov. 2026)", "kurs 45,50 (9. nov. 2026)"),
    ("R = 1.25", "R = 1,25"),
    ("USD/NOK 9.410", "USD/NOK 9,410"),
    ("0.005", "0,005"),
    ("var 45.50.", "var 45,50."),
    ("(-0.6%)", f"({MINUS}0,6{NBSP}%)"),
    ("-0.00 R", "0,00 R"),                       # negative zero is zero (funn #117)
    ("-0.0%", f"0,0{NBSP}%"),
    ("-0", "0"),
    ("15.5x", "15,5x"),                          # a unit of up to three letters may be glued on
    ("NOK 3.2m", "NOK 3,2m"),
    ("+0.4 pp", "+0,4 pp"),
    ("P/E 15.5 x", "P/E 15,5 x"),
])
def test_a_number_is_written_the_norwegian_way(before, after):
    assert norske_tall(before) == after


@pytest.mark.parametrize("same", [
    "TradingView Lightweight Charts™ 5.2.1",     # a version
    "http://127.0.0.1:8060/",                     # an address
    "09.11.2026",                                 # a date
    "9. nov. 2026",
    "2026-11-09",                                 # the date pass's business; the hyphens are not minus signs
    "Toolkit v3.0",
    "SATS_Research_Report_2026-11-02.pdf",
    "side 10-20",                                 # a range
    "T-1",
    "kill-nivå",
    "0,25 prosentpoeng",                          # already Norwegian
    f"6 230,1{NBSP}%",
    "–0,3",                                      # an en dash someone chose
    "E4–E6",
    "D58",
    "Apache-2.0",                                 # a licence name, not a number
    "1,234,567 rader",                            # thousands are grouped where they are written, not guessed here
    "9,410",                                      # a rate with three decimals: a second pass must not read it as thousands
    "SATS2026.pdf og v2.5beta",
    "",
])
def test_what_is_not_a_number_is_left_alone(same):
    assert norske_tall(same) == same


def test_tags_fields_scripts_and_code_are_never_touched_but_hover_text_is():
    page = ('<div class="v-1.5" data-x="2.50" title="avkastning +28.3% siden 1.5 år">+28.3%</div>'
            '<input name="target" value="130.5"><textarea>0.25 og 12.5%</textarea>'
            '<script>var a = 1.5; b = "12.5%";</script><style>.a{line-height:1.45}</style>'
            '<code>oq sizing --risk 0.5</code><a href="/aksje/AAA?x=1.5">kurs 12.50</a>'
            '<select><option value="0.5">0.5</option></select>')
    out = norske_tall(page)
    assert f'title="avkastning +28,3{NBSP}% siden 1,5 år">+28,3{NBSP}%</div>' in out
    assert 'class="v-1.5" data-x="2.50"' in out and '<input name="target" value="130.5">' in out
    assert "<textarea>0.25 og 12.5%</textarea>" in out and '<script>var a = 1.5; b = "12.5%";</script>' in out
    assert ".a{line-height:1.45}" in out and "<code>oq sizing --risk 0.5</code>" in out
    assert '<a href="/aksje/AAA?x=1.5">kurs 12,50</a>' in out
    assert '<option value="0.5">0.5</option>' in out            # a form's own values are sent back as written


def test_the_single_value_helpers():
    assert tall(1234.5) == f"1{THIN}234,50" and tall(-0.25) == f"{MINUS}0,25" and tall(3.14159, 1, sign=True) == "+3,1"
    assert tall(-0.001) == "0,00" and tall(None) == "–" and tall(float("nan")) == "–"
    assert heltall(305610) == f"305{THIN}610" and heltall(7) == "7"
    assert prosent(0.145) == f"+14,5{NBSP}%" and prosent(-0.028) == f"{MINUS}2,8{NBSP}%" and prosent(0.5, 0, sign=False) == f"50{NBSP}%"
    assert prosent(None) == "–"


def test_every_page_runs_the_pass(app):  # noqa: F811
    client, _ = app
    for url in ("/", "/sectors", "/aksje/AAA/oversikt", "/aksje/AAA/teknisk", "/coverage", "/screen", "/health", "/calibration"):
        html = client.get(url).get_data(as_text=True)
        body = norske_tall(html)
        assert body == html, f"{url} still has numbers in the English form"       # the pass is idempotent and already applied
    front = client.get("/sectors").get_data(as_text=True)
    assert f"{NBSP}%" in front
