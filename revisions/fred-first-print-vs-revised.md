# Revised macro data, backtested as if it was known: how far the feature moves

A backtest that downloads a macro series from FRED today gets the **latest revision** of every month. A
trader on the day got the **first print**. Revisions fold in information from the following months, so a
feature built on revised data is not the feature that could have been traded. This measures how far apart
the two are — before looking at any returns.

## Result

**1. A detailed industry signal is a different signal.** Three-month growth of 25 industrial-production lines
(the Fed's G.17), ranked across industries each month: the ranking from today's FRED and the ranking from the
first print agree at a **rank correlation of 0.53** (mean over months; median 0.54, 10th percentile 0.29; 252 months,
2003–2025). The revisions are 44% of the size of the signal itself (sd 0.037 against 0.085).

**2. Headline series point the wrong way about one month in seven.** For 18 headline series a backtest
typically takes from FRED, the direction of the monthly change in the first print and in today's revision
agree in a **median 85.9%** of months. Industrial production, durable-goods orders and continuing jobless
claims: 79–82% — about one month in five.

| Series | What it is | Observations | Direction agrees | Revision / change (sd) | Correlation (Pearson) |
|---|---|---|---|---|---|
| NFCI | Chicago Fed financial conditions (weekly) | 709 | 76.6% | 0.91 | 0.65 |
| DGORDER | durable-goods orders | 305 | 79.3% | 0.52 | 0.86 |
| CCSA | continuing jobless claims (weekly) | 798 | 79.3% | 0.29 | 0.96 |
| DSPIC96 | real disposable income | 335 | 80.6% | 0.18 | 0.98 |
| INDPRO | industrial production | 335 | 82.4% | 0.38 | 0.93 |
| RSAFS | retail sales | 282 | 84.0% | 0.28 | 0.96 |
| PERMIT | building permits | 304 | 85.1% | 0.44 | 0.92 |
| ICSA | initial jobless claims (weekly) | 813 | 85.6% | 0.33 | 0.96 |
| MANEMP | manufacturing employment | 335 | 85.7% | 0.16 | 0.99 |
| HOUST | housing starts | 335 | 86.1% | 0.40 | 0.93 |
| CPIAUCSL | consumer prices | 335 | 93.3% | 0.32 | 0.95 |
| PCEPI | PCE prices | 293 | 93.4% | 0.39 | 0.93 |
| PAYEMS | nonfarm payrolls | 335 | 94.9% | 0.09 | 1.00 |
| PCEPILFE | core PCE prices | 293 | 96.6% | 0.56 | 0.87 |
| PPIACO | producer prices | 335 | 96.6% | 0.20 | 0.98 |
| UNRATE | unemployment rate | 335 | 97.1% | 0.14 | 0.99 |
| GDP | nominal GDP (quarterly) | 111 | 97.3% | 0.31 | 0.95 |
| UMCSENT | Michigan sentiment | 317 | 100% | 0.01 | 1.00 |

Change: log change for quantities, difference for rates and indices; observations from 1997, first published by the end of 2024.
"Revision / change" is sd(revised − first print) / sd(revised).

**Do not read the last column.** The pre-registered correlation came out at a median of 0.955 — but 2020 carries
it: the pandemic months are so large that they dominate any Pearson correlation of macro changes. With ranks
instead the median is 0.844; Pearson without 2020–2021, 0.875; payrolls fall from 0.996 to 0.846 by rank, real
disposable income from 0.983 to 0.616. These two are diagnostics run after the rule, not results. The
direction-agreement column is pre-registered and not moved by a few extreme months, so it is the number this
page reports.

## Known-answer controls

| Control | What it must show | Result |
|---|---|---|
| Series that are never revised (fed funds, 2- and 10-year Treasury yields, monthly averages of market rates) | correlation ≥ 0.999 | 0.9999, 1.0000, 1.0000 |
| Mirror: first print against the *next* month's revision | below the series' own correlation in ≥ 90% of series | 18 of 18 |
| Instrument on synthetic data (unit tests, before the real run) | no revisions → exactly 1; first print = final + noise at a variance ratio of 0.5 → 1/√1.5 = 0.816 | 0.793–0.834 over 8 seeds |
| G.17: the newest archived release against FRED today | the same numbers from two sources → near 1 | 0.961 (75 pairs, median difference 0.0034) |

## What I predicted, and what this does not show

- Before the run: median Pearson 0.80–0.90 (**wrong**: 0.955), each series inside its own band (**9 of 18**),
  median direction agreement 0.80–0.92 (**right**: 0.859).
- **No returns were measured.** The page shows that the feature differs, not how much a backtest's profit
  changes. On the G.17 signal a test of that difference would have had a power of 0.12–0.36 (the signal itself
  is weak: information coefficient +0.011), so it was not run rather than run and reported as "no effect".
- The first run of the catalog stopped with an error before producing any number: our own vintage store does
  not close a vintage's interval when a newer one arrives, so one date can have several "open" values (the
  financial-conditions index: 1,498 dates). The rule was fixed — the value in vintage *v* is the row that
  started last on or before *v* — before the one counted attempt. Rules and bands were not changed.

## Data and limits

- Vintages: FRED/ALFRED real-time intervals as stored by the nightly collector; the first print of a month is
  the earliest stored vintage that contains it, and only months first published after the series' earliest
  stored vintage are used.
- G.17: the Fed's archive of release files; FRED series `IPG{NAICS}S` for the same 25 industries (5 of the 30
  have no FRED series).
- One revision path per series; seasonal-adjustment changes and benchmark revisions are inside "revision" and
  not separated.

## For a backtest you run

The same check takes any list of FRED series your strategy reads: first print against the version you
downloaded, per series, with the same controls. See [SERVICE.md](../SERVICE.md).
