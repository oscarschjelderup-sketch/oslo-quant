# Part 2: quarterly report analysis

## Summary

- `dashboard/reports.py`: finds a research-book company's quarterly report on NewsWeb, downloads the PDF, reads the
  configured rows of the key-figure table and the income statement, and compares them with the previous quarter, the
  same quarter last year, the published consensus (SATS: Modular Finance via MFN) and the case model's assumptions for
  the year (EST). Kill criteria with a measurable threshold are marked triggered / nearer / further / unchanged; the
  rest are listed as not machine-checkable. No generated text: numbers, pages, formulas and links (D17).
- Stock page: "Siste kvartalsrapport" with the three comparisons and the kill table; the PDF served locally.
- Front page: a report from the last 21 days with a criterion triggered or nearer, unanswered by a judgement or kill
  check dated after it, is listed under "Dette krever en vurdering fra deg".
- `oq dashboard --refresh` (and the evening task) reads new reports. `pypdf` added as a dependency.
- What to read and the kill thresholds live in the private `~/osloquant-home/reports.yaml`.

## On SATS's four latest reports

All 28 key figures matched their printed change, and consensus was found for all four quarters. What the comparisons show stays on the private dashboard.

## Test plan

- [x] `pytest tests/test_reports.py`: thousands separators, key rows split by the printed change, note references,
      the income-statement header, last twelve months, kill status, consensus parsing; on the frozen SATS reports
      (private), Q2 2026's figures, LTM and the Q4-based EBIT LTM read the same every time.
- [x] Dashboard run, SATS page opened and screenshotted (outside the repo).
- [ ] SATS Q3 2026 (27 Oct): one-off scheduled task reads and checks it that morning.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
