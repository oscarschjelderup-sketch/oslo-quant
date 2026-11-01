# Case review – buildable ideas for the tool and the analysis routine

Method: a two-role read of the two private cases (the fitness case and the retail IPO case) – first as a sell-side
analyst asking what is missing, then as a sceptical investor building the case against. The review itself is
private. What follows is only the generic, buildable part: things the tool or the routine should do differently,
with what each solves, how we would know it works, and effort (S/M/L). No company figures, targets, thresholds or
scenario values appear here.

## What the review found, in one paragraph

Both cases are well built where the toolkit forces structure (reverse DCF, scenarios, one lease basis, an audit
with written reasons). The gaps are in the loop *after* publication: the thing being monitored is not the thing the
value depends on; two copies of the kill list exist and disagree; a criterion can be "triggered" from the day it
is written without anyone being asked to act; a reported KPI is compared with a model that never says which
currency or window it meant; and the one slide that explains the price (what the existing business is worth vs
what is paid for growth) is a side calculation rather than the front page.

## Ideas

1. **One kill list, generated.** Make the workbook's thesis sheet the single source and generate the research-book
   and dashboard entries from it (or the reverse), with a gate that fails when the two diverge in variable,
   direction, threshold or window. Solves: two lists per case that drift apart and are read by different tools.
   Test: `oq book check` reports zero divergences for every case; editing a threshold in one place changes the
   dashboard's next reading. Effort S.

2. **Kill-or-signpost test.** For each criterion, re-run the model with the criterion's threshold substituted into
   the matching driver (the what-if runner already does this for ad-hoc cases) and record whether the rating
   flips. Criteria that do not flip the rating are demoted to "signpost" automatically and shown in a separate
   block. Solves: lists that mix thesis-ending variables with things that merely hurt. Test: every criterion on the
   kill list carries a stored "rating at threshold" and it is not the current rating. Effort M.

3. **Inception check.** When a case is logged, evaluate every criterion on the last actual year *and* on the latest
   LTM reading. Refuse to log a criterion that is already breached, or require a written note explaining why it is
   still a criterion. Solves: a criterion that reads "triggered" from day one and trains everyone to ignore it.
   Test: the judgement-log writer rejects a fixture case with a pre-breached criterion; the calibration report
   shows no criterion in "triggered" state at its own logging date. Effort S.

4. **Window and seasonality per criterion.** Each criterion declares its window (quarter y/y, LTM, fiscal year) and
   the reader stores a seasonal band from the company's own quarterly history. "Triggered" requires the declared
   window; single-quarter readings outside the band are shown as "seasonal" not "nearer". Solves: quarterly
   ratios that swing several points within a year being compared with an annual threshold. Test: replaying the
   fitness case's stored readings produces no false "triggered" on a quarter-only reading; the status string
   names the window. Effort M.

5. **Currency-adjusted KPI capture.** The report reader extracts the "currency adjusted" figures that Nordic
   issuers print in brackets alongside reported growth, stores both, and lets a criterion pick which one it
   tests. The vs-case table gets a translation line (reported minus adjusted). Solves: a price/mix criterion that
   can fire on an exchange-rate move while the underlying is intact. Test: for a report with both figures the
   summary JSON carries both; a criterion declared as "local currency" is evaluated on the adjusted number.
   Effort M.

6. **Quarterly phasing of the annual model.** Split the first forecast year into quarters using the company's own
   seasonality, so the dashboard can show YTD actual vs YTD case and "what the remaining quarter(s) must deliver to
   hit the case". Solves: comparing LTM actuals with a calendar-year forecast and guessing whether "ahead" is
   real. Test: the vs-case table shows a required run-rate for the remaining quarters, and after the final quarter
   the implied full year equals the model's. Effort M.

7. **Guidance and framework facts from the report text.** Extract structured facts that are text, not tables:
   committed openings, store/club targets, leverage range, payout floor, dividend policy wording, programme sizes.
   Diff them quarter to quarter and against the case's `META`/targets block; flag a change as a "re-assess" item.
   Solves: a company changing its capital-allocation framework or pipeline without the case noticing, because
   the reader only parses key-figure tables. Test: a fixture pair of reports with a changed range produces one
   flagged diff with the two sentences side by side. Effort M.

8. **Company-compiled consensus archive.** Where the issuer publishes a compiled consensus before each report, store
   it with the actual and compute a surprise history; feed its EBITDA/EBIT lines into the Consensus sheet where
   the free source has only revenue and EPS. Solves: "n.a." consensus rows and no record of whether the company
   beats or misses on the lines the case depends on. Test: the Consensus sheet has no "n.a." on EBITDA for a
   covered company; the stock page shows a surprise series with at least four points. Effort S.

9. **Cohort evidence field for the ramp curve.** The location engine's maturity curve must cite a source (company
   vintage disclosure, peer disclosure, or "assumed – concept younger than one maturity cycle"). When the
   source is "assumed", the audit flags it and the bear scenario is required to include a slower ramp. Solves:
   a roll-out valued on a maturity curve nobody has observed, as in the retail IPO case's new concept. Test: the
   audit shows a MISSING for a case with no ramp source; a case with "assumed" cannot pass the gate unless the
   bear's ramp differs from the base's. Effort S.

10. **"What the price pays for" page, generated.** Generalise the sum-of-the-parts runner (existing estate, then
    each growth leg and each large project added back) into a standard output: a bar from estate value to full
    value with the share price marked. Add a gate rule: if the estate value alone is below the price, the case
    must name the evidence for the growth legs on page one. Solves: the most decision-relevant decomposition
    living in a side JSON. Test: both cases render the page from their data modules without case-specific code;
    the gate rule fires on a fixture where estate < price and no evidence block exists. Effort M.

11. **Pre-mortem block.** A mandatory prep-page section: "It is twelve months later and the call was wrong because
    …" – three causes, each mapped to a criterion or a signpost and to a what-if run that shows the value at that
    outcome. The audit marks it MISSING when absent. Solves: scenario stories that describe worlds but never
    name the failure path from today's numbers. Test: audit B-series has a new check; the prep page renders the
    three causes with their linked what-if values. Effort S.

12. **Ownership and bridge consistency check.** An audit check that compares stated subsidiary ownership (data
    module or prospectus table) with the minority deduction in the bridge and the minority share of forecast
    profit; flags any material subsidiary below 100% with a zero minority share. Solves: an open ownership
    question sitting in a code comment while the equity value assumes full ownership. Test: a fixture with a partly owned
    operating subsidiary and zero minority share produces a FLAG that needs a written reason. Effort S.

13. **Quarterly reverse-DCF series.** Re-solve the market-implied margin, growth and WACC at every price update
    and after every report, and store the series. Show "gap to our base" over time on the stock page. Solves: the
    best page in both cases being a one-off snapshot, so nobody sees whether the market is moving toward or away
    from the view. Test: the stock page shows at least one point per price update; the calibration report can cite
    the implied-margin gap at logging and today. Effort S.

14. **Translation sensitivity for multi-currency operators.** When more than a quarter of revenue is outside the
    reporting currency, the stress block adds a translation shock applied to revenue and to the cost base
    separately, and the data module must state the FX assumption behind any "lower cost inflation" input.
    Solves: an FX assumption hidden inside a cost-inflation number. Test: the stress report lists the translation
    case for such companies and omits it for single-currency ones; the audit flags a cost-inflation input
    commented as FX-driven without a stated rate. Effort M.

15. **Kill checks into the judgement log automatically.** Each dashboard reading writes a kill-check row (criterion,
    reading, status, "acted / not acted" default empty) to the log, and the front page's decision card is not
    cleared until the author fills the action field. Solves: the calibration report showing zero kill checks
    while the dashboard has produced several "triggered" states. Test: after a reading the log has one row per
    criterion; calibration counts them; an unfilled action keeps the item on the decision card. Effort S.

16. **Event calendar from the report.** Parse the next report date, AGM/EGM dates, dividend ex-dates, programme end
    dates and lock-up expiries into the research-book events, replacing passed events. Solves: event lists that
    go stale the day after the report. Test: no event in the research book is older than today after the evening
    job runs; the next report date is present for every covered name. Effort S.

17. **Peer-set quality line.** Show dispersion of the peer multiples, the value with the extremes dropped, and the
    share of peers from outside the company's own sector; require a written reason when non-sector peers are a
    majority. Solves: a peer weight that looks precise while one outlier drives the range. Test: the Comps
    sheet shows the trimmed value next to the median; the audit flags a majority non-sector set without a
    reason. Effort S.

18. **Management "promised vs delivered" table.** A standard appendix built from stored guidance facts (idea 7)
    across reports: target, date set, latest reading, status. Solves: a case that cites management ambitions with
    no record of how earlier ambitions fared. Test: the table renders for any company with at least two stored
    reports; each row links to the report page it came from. Effort M.

## Suggested order

Start with the cheap ones that fix the monitoring loop (1, 3, 15, 16), then the ones that change what is measured
(2, 4, 5), then the pages that change how a case is argued (10, 11, 13). Ideas 6, 7, 9, 12, 14, 17, 18 can follow as
each case is next updated.
