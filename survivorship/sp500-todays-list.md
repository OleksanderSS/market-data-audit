# Today's S&P 500 list, backtested: +5 points a year that no strategy earned

A backtest that takes today's S&P 500 constituents and tests them on the past holds, in the past, the
companies that later won — the ones that joined the index after rising — and none of the ones that died or
were dropped. This measures how much that list earns **by itself**, against the index as it actually was on
each date, dead members included.

## Result

Three equal-weight books, rebalanced monthly (decision on the last trading day, entry at the next month's
first open, exit at the open a month later; a company that stops trading returns to its last bar; a failure
traded over the counter runs to the end of its series):

- **L** — today's list: the 503 members of 18 Aug 2026;
- **P** — the index on each date, every member that later left included;
- **F** — the index of the first date, frozen (no knowledge of the future).

| Window | L | P | F | **L − P** | = L − F (the list knows the winners) | + F − P (the list skips the index's turnover) | t | Years L > P |
|---|---|---|---|---|---|---|---|---|
| Apr 2018 – Sep 2026 | 16.28% | 11.17% | 13.15% | **+5.11** | +3.12 | +1.98 | 6.8 | 9 of 9 |
| Jan 2013 – Oct 2017 | 20.19% | 14.60% | 14.75% | **+5.60** | +5.44 | +0.15 | 5.6 | 5 of 5 |

Annual returns; differences in points a year. The index loses by turnover because it deletes what fell and adds
what already rose; a backtest on today's list never pays that.

## Known-answer controls (all passed on the first run, both windows)

| Control | What it must show | 2018–2026 | 2013–2017 |
|---|---|---|---|
| Identity | list := the index on each date → L − P exactly 0 | 0 | 0 |
| Oracle | list := top 10% by the same month's return (look-ahead) → huge | +435 | +292 |
| Start identity | list := the index of the first date → L − F exactly 0 | 0 | 0 |
| Null | 200 random halves of the first date's index vs F: median within ±0.5, ≤ 10% beyond ±3 | +0.43, 0% | +0.01, 0% |

The null on 2018–2026 passed close to its limit (0.43 of 0.5); read that window's split with this caveat.
A first attempt used a different mirror — "the frozen index should equal the index as it was" — and failed it
(F − P +1.98 against a ±1.5 limit). The premise was wrong, not the data: the index's own turnover costs it.
That attempt is not reported as a result; the split above is attempt 2, pre-registered after it.

## Data and limits

- Membership on each date from a public membership history (github.com/fja05680/sp500, MIT; one file, no second
  source for the composition).
- Prices: survivors from Yahoo; the 164 members that truly left in 2018–2026 (191 exits minus 27 renamings) from
  Tiingo, with ticker aliases taken only from independent sources (SEC filings, a renaming dictionary) — never
  from Tiingo's own answers. 12 of the 164 have no usable series (8 acquired companies whose ticker was later reused): their
  member-months count as unpriced. 2013–2017: Quandl WIKI, dead members included; 61 of today's names have no
  WIKI series (including winners that traded then: ANET, AXON, BX, CDW), so +5.60 is a lower bound.
- Equal weights, not capitalisation; no costs (both books rebalance the same way).
- What I predicted before the 2013–2017 run: L − P +2 to +5 (it was +5.60 — wrong, too low), L − F +1 to +4
  (+5.44 — wrong), F − P −0.5 to +2 (right), 60–120 names without prices (61 — right).

## For a backtest you run

The same check takes any ticker list: your universe against the index as it was, split into the two parts
above. See [SERVICE.md](../SERVICE.md).
