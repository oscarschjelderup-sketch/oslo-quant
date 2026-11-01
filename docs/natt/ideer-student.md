# "I dag" front page - student read, five minutes before a lecture

Method: read the saved snapshot top to bottom as a first-time five-minute visitor. Layout only; no company figures quoted.

## 1. Is it clear what to DO, how many, in what order?

"What" and "how many": yes. "Order" and "how long": no.
- Count: the red-bordered card right under the title says "Dette krever en vurdering fra deg (2)". The (2) answers how many.
- Order: nothing says "do this first". Order is only implied by list position and by small uppercase tags ("report", "re-assess"). The tags name the type of work, not urgency; the student cannot tell whether item 2 can wait.
- Verbs: "read the analysis on the stock page and log a kill check" and "re-assess and log the view (even if unchanged)" do give an action. But each item links to the stock page, not to the logging form.
- Fail: h1 reads "I dag Friday 30 Oct 2026" while the page was generated two days later. "I dag" is really "latest close", which makes the reader doubt everything below.
- Fail: a grey "Static snapshot written by the evening job..." line sits above the h1 and pushes content down. Developer text.
- Fail: the first item's reason sentence is cut off mid-clause (a stray "i:" where the base-case clause should end, then "triggered - read ..."). Looks like a bug and costs trust.
- Fail: no time estimate, no total.

## 2. Noise vs missing

Noise for five minutes:
- "Nye signaler siden sist (31)": about 30 dense rows spanning four days, with repeated names and odds chips ("+x% / +y% - hit z% - n N"). Longest block on the page.
- Green "buy" colouring on signal chips, while the footnote at the bottom of that block says no buy signal has paid after costs. Colour contradicts caveat.
- The unexplained "book" chip is the only link to the user's own names and is lost among 30 rows.
- Source lines under every card, the footer, "(delayed)" in the sub line.
- The research-book table has 9 columns; a student needs about 3.

Missing:
- An explicit "nothing to do today - go to class" state.
- Time per item and a total.
- A direct "log it" link per item.
- A one-line "since yesterday" summary. "siden sist" never says since when.
- A done/not-done state, so a later revisit shows "1 of 2 left".
- A staleness banner when the data date is not the last trading day.
- Priority words (first / can wait).

## 3. Wording, language, jargon

- Mixed language: nav and h2 headings are Norwegian ("Kommende datoer", "Børsmeldinger", "Innsidere og short"); tags, item text, dates ("Friday") and notes are English. It reads as unfinished, not deliberate. Pick one language for headings and body; English finance terms are fine in either.
- Jargon to decode when tired: "kill criteria over the line, 0 nearer" ("nearer" is unclear), "kill check", "re-assess and log the view", "To bear / To bull", "TP", "hit" and "n" in odds chips, "excess return over the equal-weighted universe", 20d/60d, RSI, MA20/MA60, NIBD/EBITDAaL, LFL.
- Good model: the plain heading "Dette krever en vurdering fra deg" and the empty-state sentence in the insider block.

## 4. Sections ranked for a five-minute visit

1. Decision card (2 items) - the whole point.
2. Kommende datoer - short, "what is next"; the collapsible kill-criteria list is a good pattern.
3. Research book table - useful as status, too wide.
4. Børsmeldinger - only if tied to a decision item.
5. Innsidere og short - short, reassuring when empty.
6. Header sub line (newest close, signal dates) - trust only.
7. Nye signaler (31) - lowest value, highest volume.
8. Footer.

## 5. Improvements (small, buildable)

1. Real date + data date. Show today's date and "data: last close <date>"; amber banner if stale. Solves: "I dag" mislabel. Test: weekend snapshot shows banner, nobody asks "is this today?". Effort S.
2. Summary line atop decision card: "2 things, about 6 min: 1) ... 2) ...". Solves: count, order and time at a glance. Test: reader states all three within 5 s. Effort S.
3. Number items and replace tags with plain words ("Do first - trigger fired", "Can wait - price drift"). Solves: no order cue. Test: test reader picks the right first item without reading the body. Effort S.
4. Per-item time estimate stored per decision type. Solves: no time cue. Test: every type has one; compare to actual logged time after a month. Effort S.
5. "Log it" button deep-linking to the judgement form with ticker and type pre-filled. Solves: extra clicks between reading and logging. Test: front page to saved log in 1-2 clicks. Effort M.
6. All-clear state: with 0 items show "Nothing to do today - go to class" plus next date from the calendar block. Solves: empty-state ambiguity. Test: empty fixture renders that text. Effort S.
7. "Since yesterday" strip, one line: new decisions, resolved, closes moved, news on followed names, or "no change". Solves: no change summary. Test: strip present on every load, never longer than one line. Effort M.
8. Close the signals block by default with a one-line summary ("31 new, 2 on your names"); show only followed-name signals expanded. Solves: dominant noise. Test: phone page height drops by more than half; followed-name signals still visible. Effort S.
9. Fix the cut-off reason sentence and add a snapshot test that no item text ends mid-clause. Solves: garbled first item. Test: test fails on old text, passes on new. Effort S.
10. Move the "Static snapshot..." line to the footer. Solves: dev text above the h1. Test: first screen starts with the h1. Effort S.
11. Done-today ticks, persisted. Solves: revisit shows stale list. Test: after logging, card shows the new count without manual refresh. Effort M.
12. Language pass plus glossary tooltips (TP, kill check, bear/bull, odds chip). Solves: mixed language and jargon. Test: a non-author reads the first screen aloud without asking a term. Effort M.
13. Compact 3-column research-book view with a details expander. Solves: 9-column width. Test: fits 375 px without horizontal scroll. Effort M.
14. Neutral grey odds chips unless the measured edge after costs is positive. Solves: green styling contradicts own caveat. Test: no green chip on a signal without positive after-cost edge. Effort S.
