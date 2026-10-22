# Dashboard phase 2: the pages – `oq dashboard`

Builds on phase 1 (research and decisions). Starts with one command and runs only on this machine:

```
oq dashboard              # http://127.0.0.1:8060, opens the browser
oq dashboard --refresh    # fetch announcements, rates, FX, salmon price, Brent and headlines first
oq dashboard --refresh-only
oq dashboard --static PATH
```

## Pages

1. **I dag** – "Dette krever en vurdering fra deg" on top (kill check after a report, price at target/bear/bull,
   10 % move since the view, risk signal on a book or watched stock, stale view), then the research book against
   its targets, report dates in the next 30 days with the kill criteria to check, announcements for book and
   watched companies, and the signals that are new since the last visit with their measured odds.
2. **Sektorer** – all 64 stocks in 8 groups, heatmap of day / week / month / YTD, and each group's drivers with
   source and date: Brent, USD/NOK, EUR/NOK, salmon export price, policy rate, 10-year yield. Freight rates are
   shown as "not free" (Baltic Exchange licence).
3. **Aksjeside** – price chart with MA20/60 and volume, the view's TP/bear/bull drawn on it, key figures, active
   signals with odds and sample size, announcements and headlines (links only). For a research-book company: the
   current view on a bear–DCF–TP–bull ladder (EST), kill criteria, the reverse DCF read from the private model,
   and the full judgement history.
4. **Ny vurdering** – a form on every stock page. Writes one new hash-chained row to the judgement log; date and
   price are set by the server. Cannot be sent without a rationale and a kill criterion. No route edits or deletes.
5. **Kalibrering** – every call, per case and overall, final and provisional, plus kill checks.
6. **Overvåkning** – companies followed without a case; a view on the stock page moves one into the book.

## Data

From `docs/dashboard/data-sources.md`: NewsWeb (POST per day, private use only), Norges Bank (NLOD), SSB 03024
(CC BY 4.0), Yahoo BZ=F, RSS from E24 / DN / Finansavisen / NRK (headline, link, time only). All cached in
`~/osloquant-home/feeds`; pages never wait on the network. `openpyxl` added for the reverse DCF.

## Fixed on the way

- **Private case figures in public test data.** `tests/test_signals.py` (on `main`, already on GitHub since the
  signal-watch commit) used a private case's target, scenario values and DCF as fixture data. Replaced with made-up
  figures for a made-up company (commit "Tests: fictional research-book figures…", also on its own branch
  `private-data-fix` from `main`). The old figures stay in GitHub's history until it is rewritten – Oscar's call.
  `tests/test_judgements.py` (unpushed) had the same pattern and is fixed here. A new test now fails if any tracked
  file holds a research-book case's target, bear and bull on one line, a kill criterion or a model file name.
- The stock page read `url` from RSS items that carry `link` – it would have failed for any company in the news.
- Feed times are shown in Oslo time; the chart is readable in the dark theme; the odds badge shows `n`.

## Test plan

- [x] `pytest`: 299 passed (10 new in `tests/test_dashboard.py`): the form refuses a missing rationale, kill
      criterion, view or target and probabilities that do not sum to 1; a valid form appends exactly one row at the
      server's price and date (typed date/price ignored); a second view leaves the first row byte-for-byte intact;
      the only write routes are the two POSTs, PUT/DELETE/PATCH give 405; an edited log is detected and blocks
      writing; watchlist add / duplicate / move into the book; every page renders; feed parsers read the verified
      formats offline and store no article text; git tracks no private file; no tracked file contains a kill
      criterion or model file name from the private research book.
- [x] Ran the server and opened every page in a browser (screenshots kept outside the repo: they show private
      targets). Submitted the form in the browser against a **copy** of the home directory: row #3 written, rows
      #1–2 byte-identical, chain verifies, the real `judgements.jsonl` and `researchbook.yaml` unchanged (SHA-256).
      Watchlist → judgement moved MOWI into the copy's book by appending to the yaml.
- [x] `ruff check` clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
