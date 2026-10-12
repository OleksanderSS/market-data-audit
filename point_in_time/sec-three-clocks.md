# One timestamp field, three clocks: SEC `acceptanceDateTime`

**Who should read this:** anyone who joins SEC filings to prices by the time a filing became public, using
`data.sec.gov/submissions/CIK##########.json`.

## What we saw

The field `acceptanceDateTime` always ends in `Z`, which says UTC. In fetches made between September and
October 2026 it did not always mean UTC. Comparing each value with the EDGAR filing index page, where
"Accepted" is printed in New York time, we found three readings of the same field:

| Reading | Example (EDGAR page → JSON) | Effect on a backtest |
|---|---|---|
| True UTC | Apple 8-K, accepted 16:30:28 New York → `20:30:28Z` | correct |
| New York time labelled `Z` | Alphabet Form 4, accepted 17:01:42 New York → `17:01:42Z` read as 13:01:42 New York | **4–5 h early: the filing looks public before the close — look-ahead** |
| UTC plus the New York offset | Apple 8-K, accepted 16:30:28 New York → `00:30:28Z` next day | 4–5 h late: evening filings move to the next session |

The clock changed from day to day (filings stored before 18 September were true UTC, 21 September–5 October
late, 6–9 October true again, some 11–18 September early) and **between companies in the same minute**: in one
fetch of 100 companies on 10 October, 230 responses carried UTC-plus-offset, 89 true UTC and 68 could not be
classified. Date-only values — midnight New York, `04:00Z` or `05:00Z` — were shifted by the same rule.

## How big it was in one real table

Of 618,904 stored filings (1996–2026): 553,572 correct, **3,262 early** (all from 2026: 424B2 2,752, FWP 220,
Form 4 69, 424B3 69, Form 144 32, 13G/A 27, 8-K 16), 2,912 late, 59,158 not classifiable from their own
response. The early rows are the dangerous ones: a feature built at the close would have seen them.

## How it is handled now

1. **Detect the clock of each response, not of the source.** Every filing must fall inside EDGAR's acceptance
   window (06:00–22:00 New York) and not after its own filing date. Each candidate reading is scored by the
   share of filings that break those two rules; a reading is accepted only if it breaks ≤ 3% **and** beats the
   next reading by ≥ 2 points on ≥ 10 filings. On 10 October the right reading broke 0.9% (Apple) and 0.03%
   (JPMorgan); the wrong ones 18–93%.
2. **Unclear → no time, not a guessed time.** If no reading wins, the collector stores the date without a
   time, and the feature builder treats the filing as public from the next day.
3. **Anchor:** the EDGAR filing index page. Four known answers and three random filings matched to the second.
4. **Test that fails on the old code:** three cases (JSON with the offset, New York time labelled `Z`,
   date-only midnight) — red before the fix, green after.

## Our own forecasts, scored

Before the repair we wrote down the expected shares: early 0.1–5% (**hit**, 0.53%); late 1–3% (**miss**,
0.47%); unclassifiable < 1% (**miss**, 9.6%). Two of our own repair plans were stopped by the control before
they wrote anything — both would have "fixed" correct rows from 1996–2008.

## The rule we took from it

A time zone label is a claim, not a fact. Any timestamp that decides *when* something became public is checked
against an independent page that prints the time in words, per response, every night.
