# PM review of the research book: ideas for the tool

*Written by the overnight audit, 1 November 2026, from a read-only pass over the private research book, the judgement
log, the dashboard's sizing config and the price store. This page holds only the generic conclusions and feature
ideas; the case figures stay in the private review outside git.*

## What the review found, in general terms

The book is small (two written BUY cases) and both are Norwegian consumer companies in the same universe sector.
Looked at together rather than one at a time, three things stand out that no single-case page shows:

1. **Concentration the tool cannot see.** Every open view sits in one of the eight sector groups, and both have close
   to zero correlation with the Energy group that dominates an equal-weighted Oslo index proxy. The book is in effect
   a bet on the domestic consumer and against oil beta. Nothing in the dashboard says so.
2. **Shared kill drivers.** Read side by side, the two cases' kill criteria are mostly the same kinds of thing:
   operating margin (cost inflation), roll-out or like-for-like growth, and pricing power. One domestic
   household-demand shock (rates staying high, a weak krone feeding import costs, real incomes squeezed) would fire
   kill criteria in both cases at once. The per-view loss limit treats the two as independent.
3. **The sizing module and the kill criteria do not meet.** Kill criteria are fundamental (margins, store counts,
   leverage) and only become visible on report dates; the sizing module needs a price level. The judgement log holds
   no position rows yet, so the "loss at the kill level across open views" had to be computed hypothetically. The
   binding limit in every variant tried was the per-view max loss, never the position cap; the total-loss limit is
   off. With two views the per-view limit caps the total at twice itself, which is the right order of magnitude, but
   the limit says nothing about whether the two losses arrive together.

Two smaller hygiene findings: one case's valuation date is older than a report event that has already passed and no
new judgement row exists (the case is overdue for an update); and one case's book price differs by more than one per
cent from the store's adjusted close on the valuation date (the price source should be stated).

Correlation numbers for the newest listing rest on fewer than 30 daily bars; the tool should say that loudly
wherever it prints them.

## Feature ideas (what it solves / how we know it works / effort)

1. **Portfolio exposure page.** One page over all open views: count and equal-weight (later loss-weighted) share per
   sector group, and the book's beta and correlation to the equal-weighted universe, the Energy group, the Consumer
   group and the Finance group (a rates proxy), on 1y and 3y windows. *Solves:* concentration is invisible today.
   *Works when:* the current book shows 100 % in one group with a visible warning, and adding a view in another group
   moves the numbers. *Effort:* M.

2. **Shared-kill warning.** Tag every kill criterion with a driver from a fixed list (margin / volume growth / pricing /
   rates / FX / competition / leverage / management / consumer demand) when it is written. The book page lists the
   driver overlap between open views and warns when two BUY views share a driver. *Solves:* kills that fire together
   are the real risk the per-view limit ignores. *Works when:* the two current cases produce an overlap warning on
   margin and growth; two cases with disjoint drivers do not. *Effort:* S to M (tagging is a form field; the overlap
   table is a few lines).

3. **Bear stress across all views at once.** Total loss if every open view goes to its bear value, as a share of the
   paper sum, plus the probability that all views hit bear under an assumed thesis correlation (independent vs. a
   Gaussian copula with a slider for the correlation). *Solves:* the per-view limit assumes independence.
   *Works when:* the joint-bear probability rises visibly as the slider moves and the total loss matches the sum of
   the per-view losses. *Effort:* M.

4. **Loss caps per sector group and per driver.** Extend the sizing config with an optional cap on the loss at the kill
   levels summed per sector group and per kill driver, enforced in the same place as the existing limits.
   *Solves:* two views in one group can today use the whole loss budget. *Works when:* a second view in the same
   group is refused or cut when the cap is reached, and the refusal names the cap. *Effort:* S (same pattern as the
   existing total-loss limit).

5. **Correlation matrix of case stocks with sample-size badges.** Daily and weekly correlations among case stocks and
   the group proxies, each cell showing the number of observations, greyed out below a threshold (for instance 60
   daily or 26 weekly bars), with a peer-group proxy offered for short histories. *Solves:* a fresh listing produces
   numbers that look precise and are not. *Works when:* a stock listed weeks ago shows greyed cells and a named
   proxy. *Effort:* M.

6. **Kill calendar and fundamental-to-price mapping.** For each kill criterion, record the report date on which it can
   first be observed and the price that corresponds to the bear value; show a calendar where report dates of open
   views cluster. *Solves:* kills are fundamental and arrive on dates; the sizing module only knows prices.
   *Works when:* two reports in the same fortnight show as a cluster, and sizing can use the mapped level without
   retyping. *Effort:* M.

7. **Template-fingerprint check.** Flag when two or more cases carry identical scenario probabilities, near-identical
   target-to-price ratios or identical bear/bull asymmetry. *Solves:* identical distributions across unrelated
   companies are a sign the scenario machinery, not the company, set the numbers. *Works when:* the current book
   triggers it and a case with its own justified probabilities does not. *Effort:* S.

8. **Stale-case detector.** A badge when a view's valuation date is older than the most recent passed event in its
   event list and no newer judgement row exists. *Solves:* a case can quietly outlive its own report date.
   *Works when:* the overdue case in the current book is flagged on the book page and in the evening digest.
   *Effort:* S.

9. **Price reconciliation at entry.** Compare the book's price at valuation with the store's adjusted close on that date
   and flag a gap above one per cent, asking for the price source (intraday, unadjusted, other date). *Solves:* the
   return-since-valuation and the bear distance are otherwise computed from an inconsistent base. *Works when:* the
   current discrepancy is flagged and a matched price is not. *Effort:* S.

10. **Tail-behaviour table.** For each case stock, average return on the worst five per cent of market days (1y and
    3y) next to the market's and the sector group's average, plus the count of days two case stocks fell together by
    more than a threshold. *Solves:* "defensive" is a claim; this measures it. *Works when:* the table shows the
    existing cases' down-day behaviour with sample sizes. *Effort:* S.

11. **Un-modelled-driver checklist.** Each case must state its sensitivity to FX, rates and leverage even when the
    analyst judges it immaterial; a missing statement is flagged. *Solves:* a retailer that imports goods with no FX
    criterion, or a lease-heavy operator with no rates criterion, is a blind spot the kill list hides.
    *Works when:* the current cases show the missing statements until they are filled in. *Effort:* S.

12. **One macro scenario across all cases.** Define a named scenario (for instance: policy rate held higher for longer,
    weak krone, household demand down) with the analyst's own elasticities per case, and show which kill criteria
    would fire. *Solves:* the single event that hits the whole book is only in the PM's head. *Works when:* the
    scenario lists which criteria of which cases it crosses and the total loss at those kills. *Effort:* L.

Suggested order: 2, 3 and 1 first (they change what the book page says about risk), 8 and 9 as quick hygiene fixes,
then 4, 6, 5, 10, 7, 11, 12.
