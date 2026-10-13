# Ten data flaws that quietly break a backtest

*Each item was measured, not asserted: the number, what it was measured on, and a way to check your own pipeline. Items 1–6 and 9 come from public data or public repositories; items 7 and 8 are lessons from my own pipeline; item 10 is a plain fact about free data sources.*

## Why this page exists

Backtests rarely fail because the model was too simple. They fail because the data quietly handed the model answers from the future, dropped the losers before the model could see them, or erased the crisis days. Before asking which model was used, ask:
1. When did the model think this filing became public?
2. Were the losing companies in the universe on that day?
3. What happened to the tail events and the trading costs?
4. How many failed variations were tried before this curve appeared?

## The table

| # | Flaw | What I measured | Check it yourself |
|---|---|---|---|
| 1 | **One timestamp field, three clocks.** SEC's `submissions` feed marks `acceptanceDateTime` with `Z` (UTC), but in my 2026 fetches the same field carried true UTC, New York time labelled `Z` (4–5 h early), and UTC plus the New York offset (4–5 h late) — switching from day to day and between companies. | Of 618,904 stored filings, 3,262 were 4–5 h early and 2,912 were late. The clock of each response was detected from the EDGAR acceptance window and anchored on the filing page ("Accepted", New York time): 4 of 4 known answers and 3 of 3 random filings matched to the second. Example of the harmful case: an Alphabet Form 4 accepted at 17:01:42 New York read as `17:01:42Z` looks public at 13:01:42, before the close. | Compare a handful of timestamps with the filing page; plot the hour-of-day histogram per day. |
| 2 | **A date without an hour is midnight.** A 10-Q or 10-K accepted after the close still carries that day's date, so a panel keyed by date can contain information the market did not have yet. | On 3,968 10-Q/10-K filings by 87 large US companies, 2015–2026: about 47% were accepted at or after 16:00 New York time with the same-day date (46.7% strictly between 16:00 and 17:30; 47.4% for "16:00 or later"). Repairing the clock (flaw 1) changed only 6 of 3,968 times, so the share is not an artefact of it. Re-counting with the same rule gave 1,879 rows against the 1,881 first reported. | Join filings to prices on timestamp, not date; shift the panel one bar if you only have a date. |
| 3 | **A list of today's winners.** | FinRL's default Dow 30 list is the index as of 8 November 2024. Equal-weight, rebalanced daily, 2014–2025: +16.87% a year against +12.39% for the Dow as it was on each day — a premium of +4.48 points a year from the list alone, in 10 of 12 years. A frozen 2014 list (no hindsight) shows +0.50. 4.48 is a lower bound: Walgreens, a member 2018–2024 that lost roughly two-thirds of its value, is no longer served by Yahoo at all. | Rebuild the universe as it was on each date; if you cannot, say so next to the result. |
| 4 | **One asset, one year.** | All 24 trading-agent notebooks in a popular public repository trade Alphabet from 2 Nov 2016 to 1 Nov 2017, a year in which buy-and-hold returned +33.4%. No buy-and-hold comparison is shown. | Print the buy-and-hold number next to every chart. |
| 5 | **Trained and scored on the same days.** | An evolution-strategy agent, code unchanged, 10 seeds: +36.4% median on the training year against +33.4% for buy-and-hold; on the 98 sessions that followed (never seen) the median was −2.5%, with buy-and-hold at −2.0%. | Fix the cut date before you look at any result. |
| 6 | **Zero trading costs.** | 0 of 24 notebooks model a cost. With 0.1% per trade the training year loses 1.3 points and the unseen period −3.05% (median). | Add a cost, then ask whether the edge survives twice the cost. |
| 7 | **Many tries, no correction (my own pipeline).** | Of 261 candidate features, 0 survived a correction for the number of tries; the strongest, with a t-statistic of about −3.5 (computed with errors robust to autocorrelation; on its own it would look like a 3.5-sigma result), did not survive either. | Count every variant you tried, including the ones you dropped, and correct for that number. |
| 8 | **Deleting "outliers" deletes the crisis (my own pipeline).** | A rule removing bars beyond 3 sigma deleted 14,598 genuine bars (3,724 daily, 6,893 hourly, 3,981 fifteen-minute): crisis days, earnings days and most overnight gaps on the intraday frames, 98–99% of them real moves that stayed in the market. How much this moves any given result was not measured. | Look at what a cleaning rule removes before running it. |
| 9 | **A stable profile is knowledge for the risk desk, not for the follower.** | On 2.23 million public trades in 2,982 closed prediction-market questions, wallets that beat the market in the first half of their history did so in the second half too: rank correlation 0.196 between the two halves, against 0.006 when wallets are shuffled at random (a permutation null; the largest of the shuffles reached 0.066), z = 9.6 across 2,923 wallets. For a book that takes the other side of those trades, the top decile (by first-half behaviour) was 12.1% of turnover and 60% of the book's losses (before spread and fees). This identifies which accounts a broker should pass on to the market rather than take the other side of (the "A-book"); it is not evidence that following them makes money. | Split each account's history in time, not at random, and compare the two halves. |
| 10 | **Delisted companies vanish from free sources.** | 0 of 7 Japanese issuers delisted in my sample are served by Yahoo Finance; Walgreens (item 3) is the US case. | Before trusting a free source, test it on names you know have gone. |

## Five checks before you trust a backtest

1. **Clock:** does every timestamp state its timezone, and was it checked against an independent record?
2. **Universe:** is the list of assets built for each day, including names that later failed or were acquired?
3. **Out of sample:** is the evaluation period separated in time from selection, tuning and training?
4. **Costs:** are spreads, slippage and fees deducted from traded prices?
5. **Tries:** was the number of tested models and parameters recorded, and the result corrected for it?

Each flaw above can change a number without changing a line of the strategy: the data, the clock or the universe moved, not the code. Most of them make the number look better; for item 8 the direction was not measured. If you want a second pair of eyes on a backtest, the same checks can be run on yours.
