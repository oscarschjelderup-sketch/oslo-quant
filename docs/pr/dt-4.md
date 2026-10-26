# Part 4: position size in the judgement form

## Summary

- `dashboard/sizing.py`: for a BUY view, the paper position the limits allow with the kill level as the stop –
  the smallest of max loss / loss per share, max position, free paper sum and (optional) a total-loss cap across open
  BUY views; the binding limit is named (D19). Loss per share = price − kill level + the 0.5 % round trip.
- The judgement form shows the largest allowed size, the position's value and share of the paper sum and the loss if
  the kill level is reached, as the kill level and size are typed. The server checks again and refuses a position over
  any limit – nothing is written. With a sizing config a BUY needs a kill level.
- The row stores the position, its value, the loss at the kill level and the limits used; the history table shows it.
- Limits live in the private `~/osloquant-home/dashboard.yaml`. Paper only: nothing is bought, no account is stepped.

## Test plan

- [x] `pytest tests/test_sizing.py`: the smallest limit binds and is named, a loss over the limit is refused with the
      allowed maximum, the form writes the size and writes nothing when refused, HOLD/SELL and no config get no size,
      open positions reduce the free sum, the total-loss cap.
- [x] `tests/test_dashboard.py`: the stock page shows the sizing box; a POST over the limit is a 400 and writes
      nothing; a POST without a size gets the largest allowed size.
- [x] In the browser, on a stock page with an example kill level typed in (not submitted): the largest allowed size,
      bound by the max loss, matched a hand calculation; a size above it showed the loss at the kill level in red with
      "over the limit". On a copy of the home directory, a POST over the limit was refused (400) and a POST without a size
      was written with the largest allowed size; the real judgement log was unchanged (SHA-256). Screenshots outside the repo.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
