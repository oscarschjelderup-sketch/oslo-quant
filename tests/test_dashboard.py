"""The dashboard: the judgement form appends exactly one row and can never change an old one, the watchlist moves
companies into the book, every page renders from a synthetic store, the feed parsers read the verified formats
offline, and no private file is tracked by git."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import market as mk
from osloquant.dashboard import server
from osloquant.dashboard import testdata as tdata

from .helpers import business_days

REPO = Path(__file__).resolve().parents[1]
GOOD = {"rating": "BUY", "target": "130", "rationale": "Margins recover as the price increases stick; cheap on 2027.",
        "kill": "Gross margin below 40%\nNet debt above 3x EBITDA", "bear": "80", "base": "125", "bull": "160",
        "p_bear": "0.25", "p_base": "0.5", "p_bull": "0.25", "horizon": "12",
        "premortem_1": "Fictional reason one: prices stopped rising", "premortem_2": "Fictional reason two: costs grew faster", "premortem_3": "Fictional reason three: a competitor cut prices"}


def _snapshot() -> mk.Snapshot:
    rng = np.random.default_rng(0)
    n = 300
    dates = business_days(n, "2025-08-01")
    close = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n))) for c in ("AAA", "BBB", "CCC")}, index=dates)
    panel = dict(open=close.shift(1).fillna(close), high=close * 1.01, low=close * 0.99, close=close,
                 volume=pd.DataFrame(1000.0, index=dates, columns=close.columns))
    return mk.Snapshot(panel, {"AAA": "Alpha", "BBB": "Beta Shipping", "CCC": "Gamma"},
                       {"AAA": "Seafood", "BBB": "Other shipping", "CCC": "Banks & insurance"}, dates[-1])


@pytest.fixture
def app(monkeypatch, home):
    snap = _snapshot()
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    sg.book_path().write_text(
        "entries:\n  - code: AAA\n    name: Alpha\n    rating: BUY\n    valuation_date: 2026-01-05\n    price_at_valuation: 100\n"
        "    target: 120\n    bear: 70\n    bull: 150\n    events:\n      - {date: 2026-12-01, what: Q4 report}\n"
        "    kill:\n      - margin below 10%\n", encoding="utf-8")
    a = server.create_app()
    a.testing = True
    return a.test_client(), snap


def _rows():
    return jg.read_log() if jg.log_path().exists() else []


# ------------------------------------------------------------------------------------------------ the form
def test_form_needs_a_rationale_and_a_kill_criterion(app):
    client, _ = app
    for missing in ("rationale", "kill", "rating", "target"):
        r = client.post("/stock/BBB/judge", data={**GOOD, missing: ""})
        assert r.status_code == 400, missing
    r = client.post("/stock/BBB/judge", data={**GOOD, "rationale": "cheap"})
    assert r.status_code == 400 and "at least 20 characters" in r.get_data(as_text=True)
    r = client.post("/stock/BBB/judge", data={**GOOD, "p_bull": "0.5"})
    assert r.status_code == 400 and "sum to" in r.get_data(as_text=True)
    assert _rows() == []
    assert "BBB" not in [e["code"] for e in sg.load_book()]


def test_form_appends_one_row_at_the_server_price_and_date(app):
    client, snap = app
    r = client.post("/stock/BBB/judge", data={**GOOD, "date": "2020-01-01", "price": "1", "seq": "1"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/stock/BBB?logged=1")
    (row,) = _rows()
    last = float(snap.panel["close"]["BBB"].iloc[-1])
    assert row["code"] == "BBB" and row["seq"] == 1 and row["source"] == "dashboard"
    assert row["price"] == pytest.approx(last, abs=1e-4) and row["price_date"] == f"{snap.asof:%Y-%m-%d}"
    assert row["date"] == pd.Timestamp.now().strftime("%Y-%m-%d")         # typed date and price are ignored
    assert row["thesis"] == GOOD["rationale"] and row["kill"] == ["Gross margin below 40%", "Net debt above 3x EBITDA"]
    assert "BBB" in [e["code"] for e in sg.load_book()]                      # a new company joins the book
    assert jg.verify().ok
    page = client.get("/stock/BBB?logged=1").get_data(as_text=True)
    assert "Logged as row #1" in page and GOOD["rationale"] in page


def test_old_rows_cannot_be_overwritten(app):
    client, _ = app
    assert client.post("/stock/AAA/judge", data=GOOD).status_code == 303
    first = jg.log_path().read_bytes()
    book_before = sg.book_path().read_text(encoding="utf-8")
    assert client.post("/stock/AAA/judge", data={**GOOD, "rating": "HOLD", "target": "110", "bear": "", "base": "",
                                                  "bull": "", "p_bear": "", "p_base": "", "p_bull": ""}).status_code == 303
    now = jg.log_path().read_bytes()
    assert now.startswith(first) and len(now.splitlines()) == 2                 # the old row is byte-for-byte intact
    assert sg.book_path().read_text(encoding="utf-8") == book_before            # AAA was in the book: yaml untouched
    assert bk.case("AAA").view["rating"] == "HOLD" and bk.case("AAA").view_source == "log #2"
    # no route can edit or delete: the only writes are the two POSTs
    writes = {(r.rule, m) for r in client.application.url_map.iter_rules() for m in r.methods - {"GET", "HEAD", "OPTIONS"}}
    assert writes == {("/stock/<code>/judge", "POST"), ("/watchlist", "POST"), ("/desk/run", "POST"),    # the desk writes only its own log (D41)
                      ("/stock/<code>/update", "POST"),                                          # an update row appended to the log (D48)
                      ("/review/<int:seq>", "POST"),                                             # a review row appended to the log (D49)
                      ("/chief/decide", "POST")}                                                 # Oscar's decision on a proposal, its own log (D50)
    for method in ("put", "delete", "patch"):
        assert getattr(client, method)("/stock/AAA/judge").status_code == 405
    # an edited log is found, and nothing more can be written to it
    lines = jg.log_path().read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["target"] = 999.0
    jg.log_path().write_text("\n".join([json.dumps(row), lines[1]]) + "\n", encoding="utf-8")
    r = client.post("/stock/AAA/judge", data=GOOD)
    assert r.status_code == 400 and len(jg.log_path().read_text(encoding="utf-8").splitlines()) == 2


# ------------------------------------------------------------------------------------------------ watchlist
def test_watchlist_add_and_move_into_the_book(app):
    client, _ = app
    assert client.post("/watchlist", data={"code": "ccc.ol", "note": "bank, cheap"}).status_code == 200
    assert client.post("/watchlist", data={"code": "CCC", "note": "again"}).status_code == 400
    assert client.post("/watchlist", data={"code": "../x", "note": ""}).status_code == 400
    assert [w["code"] for w in bk.watchlist()] == ["CCC"]
    assert client.post("/stock/CCC/judge", data=GOOD).status_code == 303
    (w,) = bk.watchlist()
    assert w["moved_to_book"] and w["judgement"] == 1
    assert "CCC" in [e["code"] for e in sg.load_book()]
    assert client.post("/watchlist", data={"code": "CCC", "note": "watch again"}).status_code == 200  # allowed once moved


# ------------------------------------------------------------------------------------------------ pages
def test_every_page_renders_and_labels_its_sources(app):
    client, _ = app
    t = pd.Timestamp.now("UTC").strftime("%Y-%m-%dT06:00:00Z")
    fd.write("news", {"items": [{"title": "Alpha henter penger", "link": "https://e24.no/x", "time": t, "outlet": "E24"}], "source": "RSS"})
    fd.write("announcements", {"items": [{"id": 9, "code": "AAA", "title": "Q3 report", "time": t, "category": "",
                                          "url": "https://newsweb.oslobors.no/message/9"}], "source": "NewsWeb"})
    stock = client.get("/stock/AAA").get_data(as_text=True)
    assert "https://e24.no/x" in stock and "message/9" in stock and "T06:00:00Z" not in stock
    for url in ("/", "/sectors", "/stock/AAA", "/stock/BBB", "/calibration", "/watchlist"):
        r = client.get(url)
        assert r.status_code == 200, url
        text = r.get_data(as_text=True)
        assert "delayed" in text, url
    assert "Dette krever en vurdering fra deg" in client.get("/").get_data(as_text=True)
    sectors = client.get("/sectors").get_data(as_text=True)
    assert "not free" in sectors and "Baltic" in sectors                      # freight is said to be unavailable
    assert client.get("/go?code=aaa.ol").headers["Location"].endswith("/stock/AAA")
    assert client.get("/stock/..%2Fetc").status_code == 404


def test_static_front_page_does_not_mark_signals_seen(app, tmp_path):
    from osloquant.dashboard import today as td

    out = server.write_static_today(tmp_path / "latest.html")
    assert out.exists() and "Dette krever en vurdering fra deg" in out.read_text(encoding="utf-8")
    assert "last_seen_session" not in td.load_state()
    app[0].get("/")
    assert td.load_state()["last_seen_session"]


# ------------------------------------------------------------------------------------------------ feeds, offline
def test_headline_matching_strips_longer_names():
    names = {"AKER": "Aker", "AKRBP": "Aker BP", "ODF": "Odfjell", "ODL": "Odfjell Drilling", "SATS": "SATS", "NAS": "Norwegian Air Shuttle"}
    assert fd.mentions("Aker kjøper mer", "AKER", names)
    assert not fd.mentions("Aker BP øker produksjonen", "AKER", names)
    assert fd.mentions("Aker BP øker produksjonen", "AKRBP", names)
    assert not fd.mentions("Odfjell Drilling vinner kontrakt", "ODF", names)
    assert not fd.mentions("Ny rentesats fra banken", "SATS", names)
    assert fd.mentions("Norwegian flyr mer", "NAS", names)


def test_feed_parsers_read_the_verified_formats(monkeypatch):
    nb = {"IR/B.KPRA.SD.R": "FREQ;TIME_PERIOD;OBS_VALUE\nB;2026-10-21;4.5\n",
          "GOVT_GENERIC_RATES/B.10Y.GBON": "FREQ;TIME_PERIOD;OBS_VALUE\nB;2026-10-21;4.528\n",
          "EXR/B.USD+EUR.NOK.SP": "FREQ;BASE_CUR;TIME_PERIOD;OBS_VALUE\nB;USD;2026-10-21;9.3573\nB;EUR;2026-10-21;10.512\n"}
    now = pd.Timestamp.now("UTC").floor("min")
    pub = now.tz_convert("Europe/Oslo").strftime("%a, %d %b %Y %H:%M:%S %z")

    def rss(url):
        return (f'<?xml version="1.0"?><rss><channel><item><title>Equinor: sterke tall</title><link>{url}a</link>'
                f'<pubDate>{pub}</pubDate><description>Full ingress here</description></item></channel></rss>').encode()

    newsweb = {"data": {"messages": [
        {"messageId": 1, "issuerSign": "EQNR", "issuerName": "Equinor ASA", "title": "Q3 results", "publishedTime": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT06:00:00Z"),
         "category": [{"category_en": "HALF YEARLY FINANCIAL REPORTS"}]},
        {"messageId": 2, "issuerSign": "XYZ", "title": "not ours", "publishedTime": "2026-10-22T06:00:00Z", "category": []}]}}

    def fake_get(url, method="GET", timeout=20):
        if "norges-bank" in url:
            return next(v for k, v in nb.items() if f"/{k}?" in url).encode()
        if "ssb.no" in url:
            return b'"VareGrupper2","Kilopris 2026U40","Kilopris 2026U41","Kilopris 2026U42"\n"01",73.80,72.55,74.05\n'
        if "newsreader" in url:
            assert method == "POST"
            return json.dumps(newsweb).encode()
        return rss(url)

    monkeypatch.setattr(fd, "_get", fake_get)
    assert fd.fetch_rates()["policy_rate"] == 4.5 and fd.fetch_rates()["gov10y"] == 4.528
    fx = fd.fetch_fx()
    assert fx["USDNOK"] == 9.3573 and fx["EURNOK"] == 10.512 and fx["date"] == "2026-10-21"
    s = fd.fetch_salmon()
    assert s["value"] == 74.05 and s["date"] == "week 42 2026"
    ann = fd.fetch_announcements(["EQNR"], days=1)
    assert [a["code"] for a in ann["items"]] == ["EQNR"] and ann["items"][0]["url"].endswith("/message/1")
    news = fd.fetch_news()
    e24 = next(n for n in news["items"] if n["outlet"] == "E24")
    assert len(news["items"]) == 4 and news["errors"] == []
    assert e24 == {"title": "Equinor: sterke tall", "link": "https://e24.no/rss2/a", "time": f"{now:%Y-%m-%dT%H:%M:%SZ}", "outlet": "E24"}
    assert "ingress" not in json.dumps(news)                                   # headlines and links only


# ------------------------------------------------------------------------------------------------ privacy
PRIVATE_NAMES = ("researchbook.yaml", "judgements.jsonl", "judgements-heads.txt", "watchlist.yaml", "dashboard_state.json",
                 "calibration.md")


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    return out.splitlines()


def test_no_private_file_is_tracked():
    tracked = _tracked()
    for f in tracked:
        assert Path(f).name not in PRIVATE_NAMES, f
        assert not f.startswith(("feeds/", "signals/", "monthly/", "desk/", "chief/")), f


def test_no_tracked_file_holds_the_private_research_book():
    """Run where a frozen copy of the real book exists (private test data, never the live file): no kill criterion,
    model file name or a case's target, bear and bull values together on one line (the shape of a copied fixture) is
    in any tracked file."""
    real = tdata.default_dir() / "researchbook.yaml"
    if not real.exists():
        pytest.skip("no frozen research-book copy on this machine")
    import yaml

    entries = (yaml.safe_load(real.read_text(encoding="utf-8")) or {}).get("entries", [])
    needles = [k for e in entries for k in e.get("kill", []) if len(k) > 15]
    needles += [Path(p).name for e in entries for p in (e.get("model") or {}).values()]
    assert needles
    import re

    figures = [[f"{float(e[k]):g}" for k in ("target", "bear", "bull")] for e in entries if all(e.get(k) for k in ("target", "bear", "bull"))]
    for f in _tracked():
        p = REPO / f
        if p.suffix.lower() in {".png", ".jpg", ".ico", ".xlsx", ".db", ".parquet", ".lock"} or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for n in needles:
            assert n not in text, f"{n!r} found in {f}"
        for line in text.splitlines():
            for fig in figures:
                assert not all(re.search(rf"(?<![\w.]){re.escape(x)}(?![\w.])", line) for x in fig), f"case figures {fig} in {f}: {line[:80]}"


# ------------------------------------------------------------------------------------------------ phase 3: the habit
def test_evening_digest_writes_the_front_page_and_falls_back(monkeypatch, home):
    from typer.testing import CliRunner

    from osloquant import cli
    from osloquant.dashboard import server as srv

    snap = _snapshot()
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    monkeypatch.setattr(cli, "_signals_panel", lambda codes=None: snap.panel)
    runner = CliRunner(env={"COLUMNS": "200"})
    r = runner.invoke(cli.app, ["signals", "digest", "--quiet"])
    assert r.exit_code == 0, r.output
    latest = (sg.signals_dir() / "latest.html").read_text(encoding="utf-8")
    assert "Dette krever en vurdering fra deg" in latest and "http://127.0.0.1:8060/" in latest

    def broken(last_seen=None):
        raise RuntimeError("no store")

    monkeypatch.setattr(srv, "static_today_html", broken)
    r = runner.invoke(cli.app, ["signals", "digest", "--quiet"])
    assert r.exit_code == 0 and "classic page" in r.output
    latest = (sg.signals_dir() / "latest.html").read_text(encoding="utf-8")
    assert "<title>Signal watch" in latest                                    # the evening digest is still written


def test_weekly_lists_a_missed_judgement_until_one_is_logged(monkeypatch, home):
    from osloquant.dashboard import weekly

    snap = _snapshot()
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    end = snap.asof
    px = float(snap.panel["close"]["AAA"].iloc[-1])
    p0 = round(px / 1.3, 2)                                                   # 30 % above the view's price all week
    sg.book_path().write_text(
        f"entries:\n  - code: AAA\n    name: Alpha\n    rating: BUY\n    valuation_date: 2025-09-01\n    price_at_valuation: {p0}\n"
        f"    target: {round(px * 2, 2)}\n    bear: {round(p0 * 0.5, 2)}\n    bull: {round(px * 3, 2)}\n    kill:\n      - margin below 10%\n",
        encoding="utf-8")
    s = weekly.summary(end)
    missed = [m for m in s["missed"] if m["code"] == "AAA" and m["kind"] == "re-assess"]
    assert missed and missed[0]["date"] <= f"{end:%Y-%m-%d}"
    assert "Judgements that should have been made" in weekly.to_markdown(s)
    bk.write_judgement("AAA", "Alpha", {**GOOD, "target": round(px * 1.2, 2), "bear": None, "base": None, "bull": None,
                                        "p_bear": None, "p_base": None, "p_bull": None, "kill": ["margin below 10%"]},
                       px, f"{end:%Y-%m-%d}", mk.PRICE_SOURCE, today=f"{end:%Y-%m-%d}")
    s = weekly.summary(end)
    assert not [m for m in s["missed"] if m["code"] == "AAA" and m["kind"] == "re-assess"]
    assert s["logged"] == []                                                  # logged today, not in that past week
    md, html, _ = weekly.write(end)
    assert md.parent == jg.home() / "weekly" and "Vurderinger som burde vært gjort" in html.read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------ outcome odds (part 1)
def test_stock_page_shows_outcome_odds_with_the_reality_check(app, monkeypatch):
    from osloquant.dashboard import odds

    client, snap = app
    monkeypatch.setattr(odds, "long_closes", lambda: snap.panel["close"])
    odds._case_odds_cached.cache_clear()
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert "Utfallsodds" in page and "realitetssjekk, ikke en prognose" in page
    assert "Break-even" in page and "stedfortreder" in page                 # no kill level yet: the bear value stands in
    assert "Simulering" in page and "Historiske tilfeller" in page and "Tilfeller" in page


def test_the_kill_level_is_stored_and_must_sit_on_the_right_side(app):
    client, snap = app
    px = float(snap.panel["close"]["BBB"].iloc[-1])
    bad = client.post("/stock/BBB/judge", data={**GOOD, "kill_level": f"{px * 1.1:.2f}"})
    assert bad.status_code == 400 and "kill level must be below the price" in bad.get_data(as_text=True)
    assert client.post("/stock/BBB/judge", data={**GOOD, "kill_level": f"{px * 0.8:.2f}"}).status_code == 303
    (row,) = jg.read_log()
    assert row["kill_level"] == pytest.approx(round(px * 0.8, 2))


# ------------------------------------------------------------------------------------------------ position size (part 4)
def test_the_form_sizes_a_buy_and_refuses_a_loss_over_the_limit(app, home):
    import yaml

    from osloquant.dashboard import sizing

    client, snap = app
    (home / sizing.CONFIG).write_text(yaml.safe_dump({"sizing": {"paper_capital": 100000, "max_loss": 2000, "max_position": 0.25}}), encoding="utf-8")
    page = client.get("/stock/BBB").get_data(as_text=True)
    assert "Posisjonsstørrelse" in page and "et gulv, ikke et tak" in page and 'name="position_shares"' in page
    px = float(snap.panel["close"]["BBB"].iloc[-1])
    kill = round(px * 0.9, 2)
    r = client.post("/stock/BBB/judge", data={**GOOD, "bear": "", "bull": "", "base": "", "p_bear": "", "p_base": "", "p_bull": "",
                                              "kill_level": kill, "position_shares": "100000"})
    assert r.status_code == 400 and "above your limit" in r.get_data(as_text=True)
    assert not jg.log_path().exists() or jg.read_log() == []
    r = client.post("/stock/BBB/judge", data={**GOOD, "bear": "", "bull": "", "base": "", "p_bear": "", "p_base": "", "p_bull": "",
                                              "kill_level": kill})
    assert r.status_code == 303
    (row,) = jg.read_log()
    assert row["position_shares"] > 0 and row["loss_at_kill"] <= 2000


# ------------------------------------------------------------------------------------------------ benchmarks (night: D21)
def test_consensus_target_needs_a_source_and_the_calibration_page_shows_benchmarks(app):
    client, snap = app
    r = client.post("/stock/BBB/judge", data={**GOOD, "consensus_target": "140"})
    assert r.status_code == 400 and "needs its source" in r.get_data(as_text=True)
    r = client.post("/stock/BBB/judge", data={**GOOD, "consensus_target": "140", "consensus_source": "IR page, 2026-10-22"})
    assert r.status_code == 303
    (row,) = jg.read_log()
    assert row["consensus_target"] == 140.0 and row["consensus_source"] == "IR page, 2026-10-22"
    page = client.get("/calibration").get_data(as_text=True)
    assert "Er jeg bedre enn referansene?" in page and "kursen står stille" in page
    assert "Oppgitt sannsynlighet mot det som skjedde" in page and "pending" in page       # no final call yet: plot withheld


# ------------------------------------------------------------------------------------------------ before the report (night: D22)
def test_a_report_in_ten_days_asks_for_a_view_logged_before_it(home):
    from osloquant.dashboard import today as td

    today = pd.Timestamp("2026-11-02")
    hist = [{"kind": "judgement", "date": "2026-09-20", "logged_at": "2026-09-20T10:00:00Z", "rating": "BUY", "target": 54}]
    c = bk.Case("XYZ", "Xyz", {"rating": "BUY", "target": 54}, "log #1", [{"date": "2026-11-12", "what": "Q3 2026 report"}], ["x"], None, hist)
    items = td.pre_report_items([c], today)
    assert len(items) == 1 and items[0].kind == "pre-report" and "12 Nov" in items[0].title and items[0].urgency == 1
    c.history.append({"kind": "judgement", "date": "2026-10-20", "logged_at": "2026-10-20T10:00:00Z", "rating": "BUY", "target": 54})
    assert td.pre_report_items([c], today) == []                                      # a view within 30 days of the report
    far = bk.Case("XYZ", "Xyz", None, "log", [{"date": "2026-12-20", "what": "Q4 report"}], [], None, [])
    assert td.pre_report_items([far], today) == []                                     # more than 10 days away
    soon = bk.Case("XYZ", "Xyz", None, "log", [{"date": "2026-11-04", "what": "Q3 report"}], [], None, [])
    assert td.pre_report_items([soon], today)[0].urgency == 0


def test_a_buy_with_a_kill_criterion_already_triggered_needs_an_acknowledgement(app):
    import json

    client, snap = app
    d = home_dir = jg.home() / "reports" / "BBB"
    d.mkdir(parents=True)
    (home_dir / "1.summary.json").write_text(json.dumps({"code": "BBB", "message_id": 1, "title": "BBB Q3 2026 report", "published": "2026-10-27T06:00:00Z",
        "year": 2026, "quarter": 3, "url": "x", "pdf": "1.pdf", "figures": {}, "metrics": {}, "previous": None, "consensus": None, "case": {},
        "kill": [{"criterion": "Gross margin below 40%", "metric": "gm", "op": "<", "threshold": 0.40, "now": 0.38, "previous": 0.41, "status": "triggered"}],
        "analysed_at": "2026-10-27T07:00:00Z"}), encoding="utf-8")
    page = client.get("/stock/BBB").get_data(as_text=True)
    assert "allerede over streken" in page and 'name="ack_triggered"' in page
    r = client.post("/stock/BBB/judge", data=GOOD)
    assert r.status_code == 400 and "already over the line" in r.get_data(as_text=True)
    assert not jg.log_path().exists() or jg.read_log() == []
    r = client.post("/stock/BBB/judge", data={**GOOD, "ack_triggered": "1"})
    assert r.status_code == 303
    (row,) = jg.read_log()
    assert row["triggered_at_entry"] and "Gross margin" in row["triggered_at_entry"][0]
    assert "logget med utløst kill-kriterium" in client.get("/stock/BBB").get_data(as_text=True)
    # a HOLD is not a bet on the case: no acknowledgement needed
    assert client.post("/stock/BBB/judge", data={**GOOD, "rating": "HOLD"}).status_code == 303


# ------------------------------------------------------------------------------------------------ five minutes before a lecture (night)
def test_front_page_says_what_to_do_first_and_how_old_the_data_is(app, monkeypatch):
    from osloquant.dashboard import render as rd
    from osloquant.dashboard import today as td

    client, snap = app
    page = client.get("/").get_data(as_text=True)
    assert "Siste sluttkurs:" in page and "I dag" in page
    assert "Static snapshot" not in page.split("<h1>")[0]                         # nothing above the heading
    # a direct render with decisions: numbered, ordered, timed; without: the all-clear
    items = [td.Item("AAA", "re-assess", "Alpha +12% since the view", "re-assess and log the view", 1),
             td.Item("BBB", "kill-check", "Beta: Q3 report", "check the 3 kill criteria", 0)]
    ctx = dict(decisions=sorted(items, key=lambda i: i.urgency), upcoming=[], moves=[], alerts=[], sessions=["2026-10-30"],
               asof=pd.Timestamp("2026-10-30"), today=pd.Timestamp("2026-11-01"), book_codes={"AAA", "BBB"}, price_label="x", announcements=None)
    html = rd.today_page(ctx)
    assert "2 ting, omtrent" in html and "1. Gjør først" in html and "2. I dag" in html
    assert html.index("BBB") < html.index("AAA")                                     # urgency 0 first
    assert "eldre enn siste virkedag" not in html                                     # Friday close read on a Sunday is not stale
    ctx["asof"] = pd.Timestamp("2026-10-28")
    assert "eldre enn siste virkedag" in rd.today_page(ctx)
    ctx["decisions"] = []
    ctx["upcoming"] = [{"code": "BBB", "name": "Beta", "date": pd.Timestamp("2026-11-12"), "what": "Q3 report", "kill": []}]
    html = rd.today_page(ctx)
    assert "Ingenting krever en vurdering i dag" in html and "Neste dato: 12 Nov" in html


def test_signals_on_other_stocks_are_folded_and_chips_are_neutral(app):
    from osloquant import signals as sg
    from osloquant.dashboard import render as rd

    client, snap = app
    a = sg.Alert("CCC", "Gamma", "New 52-week high", sg.BUY, "2026-10-30", 100.0, "above the 250-day high", 0.0003, 0.0056, 0.47)
    b = sg.Alert("AAA", "Alpha", "New 52-week high", sg.BUY, "2026-10-30", 100.0, "above the 250-day high", 0.0003, 0.0056, 0.47)
    ctx = dict(decisions=[], upcoming=[], moves=[], alerts=[a, b], sessions=["2026-10-30"], asof=pd.Timestamp("2026-10-30"),
               today=pd.Timestamp("2026-10-31"), book_codes={"AAA"}, price_label="x", announcements=None)
    html = rd.today_page(ctx)
    assert "1 på dine aksjer" in html and "<details><summary>1 signaler på andre aksjer" in html
    assert html.index("Alpha") < html.index("<details>")                             # own stocks open, others folded
    assert 'class="chip  odds"' in html or 'class="chip buy odds"' not in html         # a D-grade signal is not green


# ------------------------------------------------------------------------------------------------ after the report (night: D29)
def test_a_passed_report_with_no_view_after_it_asks_for_a_re_assessment(home, monkeypatch):
    from osloquant.dashboard import reports as rp
    from osloquant.dashboard import today as td

    monkeypatch.setattr(rp, "latest", lambda code: None)
    today = pd.Timestamp("2026-11-20")
    hist = [{"kind": "judgement", "date": "2026-10-08", "logged_at": "2026-10-08T10:00:00Z", "rating": "BUY", "target": 54}]
    c = bk.Case("XYZ", "Xyz", {"rating": "BUY", "target": 54, "date": "2026-10-08", "price": 40}, "log #1",
                [{"date": "2026-11-12", "what": "Q3 2026 report – first after the listing"}], ["x"], None, hist)
    assert td.last_report(c, today) == (pd.Timestamp("2026-11-12"), "Q3 2026 report – first after the listing")
    items = td.post_report_items([c], today)
    assert len(items) == 1 and items[0].kind == "post-report" and "12 Nov" in items[0].title and items[0].urgency == 1
    # a kill check after the report is not a view; a judgement is
    c.history.append({"kind": "kill_check", "date": "2026-11-13", "logged_at": "2026-11-13T10:00:00Z"})
    assert len(td.post_report_items([c], today)) == 1
    c.history.append({"kind": "judgement", "date": "2026-11-14", "logged_at": "2026-11-14T10:00:00Z", "rating": "HOLD", "target": 50})
    assert td.post_report_items([c], today) == []
    # a report the reader summarised counts too, and an old one does not
    monkeypatch.setattr(rp, "latest", lambda code: {"published": "2026-10-27T06:00:00Z", "quarter": 3, "year": 2026, "kill": []})
    fresh = bk.Case("ABC", "Abc", {"rating": "BUY", "target": 10, "date": "2026-10-06", "price": 9}, "log #1", [], [], None,
                    [{"kind": "judgement", "date": "2026-10-06", "logged_at": "2026-10-06T10:00:00Z", "rating": "BUY", "target": 10}])
    assert td.last_report(fresh, today) == (pd.Timestamp("2026-10-27"), "Q3 2026 report")
    assert td.post_report_items([fresh], pd.Timestamp("2027-01-15")) == []                 # 80 days on: no longer nagging
    # the merged list keeps one re-assessment per code
    move = td.Item("ABC", "re-assess", "Abc +11% since the view", "...", 1)
    merged = td.merge_items([move], td.post_report_items([fresh], today))
    assert [i.kind for i in merged] == ["post-report"]
    assert [i.kind for i in td.merge_items([move], [])] == ["re-assess"]
