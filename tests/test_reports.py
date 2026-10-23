"""The report reader: numbers written with spaces as thousands separators, key-figure rows checked against their
printed change, income-statement rows read against their header, last twelve months, consensus and kill status –
synthetic everywhere, and on SATS's real reports (frozen copies, private) where they exist."""

from __future__ import annotations

import json
import shutil

import pytest

from osloquant import judgements as jg
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import reports as rp
from osloquant.dashboard import testdata as tdata


def test_numbers_with_space_separators():
    assert rp.partitions(["1", "442", "1", "393"], 2) == [[1442.0, 1393.0]]
    assert sorted(rp.partitions(["615", "580"], 2)) == [[615.0, 580.0]]
    assert rp.partitions(["615", "580"], 1) == [[615580.0]]
    assert rp.partitions(["-1", "085", "-1", "029", "-2", "055"], 3) == [[-1085.0, -1029.0, -2055.0]]
    assert rp.partitions(["085"], 1) == []                        # a group of three cannot start a number


def test_key_row_uses_the_printed_change_to_split_numbers():
    row = rp.read_key_row("EBITDA 615 580 6% 1 141 1 073 6%", "EBITDA")
    assert (row["q"], row["q_ly"], row["ytd"], row["ytd_ly"]) == (615, 580, 1141, 1073)
    row = rp.read_key_row("Net debt 1 087 1 229 -11 % 1 087 1 229 -11 %", "Net debt")
    assert row["q"] == 1087 and row["q_chg_printed"] == pytest.approx(-0.11)
    assert rp.read_key_row("EBITDA before impact of IFRS 16 2 0 n.a. 14 20 -31 %", "EBITDA before impact of IFRS 16")["q"] == 2


def test_income_statement_rows_skip_note_references():
    cols = rp.pl_columns("Notes Q2 2026 Q2 2025 YTD 2026 YTD 2025 2025")
    assert cols == ["Q2 2026", "Q2 2025", "YTD 2026", "YTD 2025", "2025"]
    row = rp.read_pl_row("Revenue 2 1 442 1 393 2 925 2 788 5 509", "Revenue", cols)
    assert row == {"Q2 2026": 1442, "Q2 2025": 1393, "YTD 2026": 2925, "YTD 2025": 2788, "2025": 5509}
    row = rp.read_pl_row("Depreciation and amortization 6, 7, 8 -297 -306 -603 -606 -1 217", "Depreciation and amortization", cols)
    assert row["2025"] == -1217


def test_last_twelve_months():
    assert rp.ltm({"YTD 2026": 2925, "YTD 2025": 2788, "2025": 5509}, 2026, 2) == 5646
    assert rp.ltm({"Q1 2026": 1483, "Q1 2025": 1395, "2025": 5509}, 2026, 1) == 5597
    assert rp.ltm({"2025": 5509, "2024": 5064}, 2025, 4) == 5509
    assert rp.ltm({"YTD 2026": 1}, 2026, 2) is None


def test_kill_status():
    rule = {"op": ">", "value": 0.40}
    assert rp.kill_status(rule, 0.41, 0.39) == "triggered"
    assert rp.kill_status(rule, 0.395, 0.39) == "intact, nearer"
    assert rp.kill_status(rule, 0.38, 0.39) == "intact, further away"
    assert rp.kill_status({"op": "<", "value": 0.03}, 0.033, 0.05) == "intact, nearer"
    assert rp.kill_status(rule, None, 0.39) == "not measurable from the report"


def test_consensus_release_is_parsed(monkeypatch):
    html = ("<html><body><div>X – Consensus estimates Q3 2026</div><div>2026-10-22 15:00:00</div>"
            "<p>Estimates compiled by Modular Finance on behalf of X.</p><p>Number of contributors: 5 (all updated)</p>"
            "<table><tr><td>KPI (MNOK, unless otherwise specified)</td><td>Q3 2026E</td></tr>"
            "<tr><td>Total revenue</td><td>1,324</td></tr><tr><td>EBITDA before impact of IFRS 16</td><td>227</td></tr>"
            "<tr><td>Earnings per share (NOK)</td><td>0.63</td></tr><tr><td>Members (T)</td><td>762</td></tr></table>"
            "<p>More consensus estimates can be found on the company's webpage</p></body></html>")
    monkeypatch.setattr(fd, "_get", lambda url, method="GET", timeout=20: html.encode())
    c = rp.fetch_consensus("x", 2026, 3)
    assert c["values"] == {"revenue": 1324.0, "ebitda_pre16": 227.0, "eps": 0.63, "members_k": 762.0}
    assert c["contributors"] == 5 and c["published"] == "2026-10-22 15:00"
    monkeypatch.setattr(fd, "_get", lambda url, method="GET", timeout=20: b"<html>nothing for that quarter</html>")
    assert rp.fetch_consensus("x", 2026, 4) is None


def test_report_period_and_detection():
    assert rp.period_of("SATS ASA Q2 2026: Growth, margin expansion") == (2026, 2)
    assert rp.period_of("Annual Report 2025") is None


# ------------------------------------------------------------------------------------------------ frozen real reports
SPEC = {"key": {"revenue": "Total revenues", "ebitda_pre16": "EBITDA before impact of IFRS 16", "ebit_pre16": "EBIT before impact of IFRS 16",
                "net_debt": "Net debt", "clubs": "Clubs", "members_k": r"Members \(.000\)", "arpm": r"ARPM \(NOK/month\)"},
        "pl": {"revenue": "Revenue", "personnel": "Personnel expenses"}}
needs_reports = pytest.mark.skipif(not tdata.available("reports/SATS/679780.pdf"), reason="no frozen SATS reports on this machine (private)")


@needs_reports
def test_real_sats_reports_read_the_same_every_time(home):
    src = tdata.default_dir() / "reports" / "SATS"
    dst = jg.home() / "reports" / "SATS"
    dst.mkdir(parents=True, exist_ok=True)
    for mid in (665220, 679780):
        for ext in ("pdf", "json"):
            shutil.copy2(src / f"{mid}.{ext}", dst / f"{mid}.{ext}")
    q4 = rp.analyse("SATS", 665220, SPEC, None, [], consensus=None)
    (dst / "665220.summary.json").write_text(json.dumps(q4), encoding="utf-8")
    s = rp.analyse("SATS", 679780, SPEC, None, ["a", "b"], previous=q4, consensus=None)
    f = s["figures"]
    assert (s["year"], s["quarter"]) == (2026, 2)
    assert {k: f[k]["value"] for k in SPEC["key"]} == {"revenue": 1442, "ebitda_pre16": 313, "ebit_pre16": 260, "net_debt": 1068,
                                                       "clubs": 270, "members_k": 744, "arpm": 635}
    assert all(f[k]["page"] == 4 and f[k]["checked"] == "matches the printed change" for k in SPEC["key"])
    assert f["pl_personnel"]["columns"] == {"Q2 2026": 498, "Q2 2025": 491, "YTD 2026": 1085, "YTD 2025": 1029, "2025": 2055}
    m = s["metrics"]
    assert m["revenue_ltm"]["value"] == 5646
    assert round(m["personnel_pct_ltm"]["value"], 4) == round(2111 / 5646, 4)
    assert m["ebit_pre16_ltm"]["value"] == 652 + 477 - 401                      # FY 2025 from the Q4 report
    assert round(m["arpm_yoy"]["value"], 4) == round(635 / 621 - 1, 4)
    assert [k["status"] for k in s["kill"]] == ["not machine-checkable: read the report"] * 2


@needs_reports
def test_real_consensus_release_parses(monkeypatch):
    html = (tdata.default_dir() / "mfn" / "sats-q2-2026.html").read_bytes()
    monkeypatch.setattr(fd, "_get", lambda url, method="GET", timeout=20: html)
    c = rp.fetch_consensus("sats", 2026, 2)
    assert c["values"] == {"revenue": 1437.0, "ebitda": 609.0, "ebitda_pre16": 302.0, "profit": 181.0, "eps": 0.92, "members_k": 747.0}
    assert c["contributors"] == 7 and c["published"] == "2026-08-11 14:00"
