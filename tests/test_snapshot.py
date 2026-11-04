"""The static copy of the dashboard (D44): every reachable page written with relative links, forms off, a banner, the
front page twice (idag.html and index.html), never inside the repository, and the signals never marked seen.
Synthetic store and a temporary home only."""

from __future__ import annotations

import pytest

from osloquant.dashboard import server
from osloquant.dashboard import snapshot as sn

from .test_dashboard import app  # noqa: F401  (fixture)


def test_the_copy_holds_every_reachable_page_with_relative_links(app, tmp_path, monkeypatch):  # noqa: F811
    client, _ = app
    seen_flags = []
    real = server.today_context
    monkeypatch.setattr(server, "today_context", lambda mark_seen=True, **kw: seen_flags.append(mark_seen) or real(mark_seen=mark_seen, **kw))
    res = sn.write(tmp_path / "copy", app=client.application, stamp="04.11.2026 kl. 14:00")
    out = tmp_path / "copy"
    assert res["failed"] == {} and res["pages"] > 5 and seen_flags == [False]               # the front page did not mark signals seen
    for f in ("idag.html", "index.html", "stock-AAA.html", "coverage.html", "screen.html", "desk.html", "plotly.min.js"):
        assert (out / f).exists(), f
    front = (out / "idag.html").read_text(encoding="utf-8")
    assert 'href="stock-AAA.html"' in front and 'href="coverage.html"' in front and 'href="/' not in front
    assert "Statisk kopi</b> av dashbordet, tatt 04.11.2026 kl. 14:00" in front and "b.disabled=true" in front and 'action="go"' in front
    stock = (out / "stock-AAA.html").read_text(encoding="utf-8")
    assert 'src="plotly.min.js"' in stock and "127.0.0.1" not in stock and 'action="#"' in stock


def test_cdn_mode_loads_plotly_from_cdnjs_and_copies_nothing_big(app, tmp_path):  # noqa: F811
    client, _ = app
    res = sn.write(tmp_path / "copy", app=client.application, cdn=True)
    ver = sn.plotly_version()
    assert ver and res["plotly"] == f"https://cdnjs.cloudflare.com/ajax/libs/plotly.js/{ver}/plotly.min.js"
    assert not (tmp_path / "copy" / "plotly.min.js").exists()
    assert res["plotly"] in (tmp_path / "copy" / "stock-AAA.html").read_text(encoding="utf-8")


def test_the_copy_is_never_written_inside_the_repository(app):  # noqa: F811
    client, _ = app
    with pytest.raises(ValueError, match="inside the repository"):
        sn.write(sn.REPO / "copy-of-the-book", app=client.application)
    assert not (sn.REPO / "copy-of-the-book").exists()


def test_file_names_are_flat_and_the_write_routes_are_not_copied():
    assert sn.fname("/") == "idag.html" and sn.fname("/stock/SATS/pretrade") == "stock-SATS-pretrade.html"
    assert sn.fname("/reports/sats/SATS_Research_Report_2026-11-02.pdf") == "reports/SATS/SATS_Research_Report_2026-11-02.pdf"
    assert sn.fname("/stock/SATS/judge") is None and sn.fname("/go?code=X") is None and sn.fname("/report/SATS/123.pdf") is None
