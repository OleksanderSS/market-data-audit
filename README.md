# Where market data lies: an audit of a forecasting pipeline

A one-person research project: a 7-stage pipeline that collects US equity data (prices, SEC filings, FRED
macro series, news, options, analyst estimates) and tests whether any of it forecasts returns.

**The headline result is negative, and it is the point of this repository.** After realistic trading costs no
strategy beat doing nothing. What the project did produce is a set of data defects that would have made
the opposite look true, each found, measured and fixed with a test that fails on the old code.

This repository is a curated extract. The full working repository (1,391 commits, Ukrainian-language
research log) is private; the excerpts here are unchanged apart from removed paths and credentials.

## Findings

| # | What was wrong | How big | How it was proved |
|---|---|---|---|
| 1 | **Look-ahead in SEC fundamentals.** `filed` is a date with no time; stored as midnight, it let the model see a filing on the morning of the day it was filed. | 46% of 10-K/10-Q facts were visible before EDGAR accepted the filing (filings index: 43%). | Acceptance timestamps joined by accession number: 99.98% matched; control — filings accepted before 17:15 New York must fall on `filed` — 99.87%. |
| 2 | **The same shape in three sources.** Any date without a time of day turned out to leak the same way. | 3 sources. | Now the first check run on every new source. |
| 3 | **Survivorship bias.** The 105 stocks were chosen knowing which companies survived. | Long the list, short the market, no model: +6.9% a year, Sharpe 1.22, t = 6.3 (1996–2023). | Any signal is measured against this bar, not against zero. |
| 4 | **Tails deleted.** A cleaning step dropped every bar more than 3σ from its moving average. | 14,598 real price moves — crisis days, earnings days, overnight gaps. | 98–99% of the dropped moves persisted afterwards, so they were real, not bad ticks. |
| 5 | **Wrong model type.** Three-class targets (−1/0/1) were inferred as regression. | 308 models trained and scored by R². | Target type is now read from the target registry, not guessed from the values. |
| 6 | **Commission priced on the wrong price.** The per-share fee ($0.0035) was computed on Yahoo's *adjusted* close, which is split- and dividend-adjusted backwards — on old bars far below the price actually traded (Apple 2013: 32×). | Commission per round trip overstated ~5× (9.7 bp vs 2.0 bp on 363k bars matched to traded prices; 6× for 1996–2005); its share of friction falls from the 63% first reported to ≤ 38%. The negative headline survives: even a commission-free book trailed buy-and-hold fourfold. | Re-priced against unadjusted Quandl WIKI prices; known-answer control — Apple's 7:1 and 4:1 splits must give a price ratio of 28–34 (measured 32.5). |

## Audits of other people's backtests

**I audit backtests for others** — what I check, what I need and prices: [SERVICE.md](SERVICE.md).

The same instruments, applied to public code. Each case is pre-registered, reports every notebook or strategy it read (not only the broken ones), and counts a defect only with a measured effect.

| Case | Repository | Headline |
|---|---|---|
| [1](audits/case-01-stock-prediction-models.md) | huseinzol05/Stock-Prediction-Models (9.5k stars) | 24 trading agents all trained and scored on one year of GOOG (+33.4% buy-and-hold). The measured agent: +36.4% on that year, −2.5% on the 98 sessions it never saw (buy-and-hold −2.0%). |
| [2](audits/case-02-finrl-ticker-list.md) | AI4Finance-Foundation/FinRL (16.5k stars) | Trains on 2014–2025 with the Dow's membership of November 2024. The list alone beats the index as it was by +4.48 points a year (a lower bound), in 10 of 12 years. |
| [3](audits/case-03-ml4t-data-claims.md) | stefan-jansen/machine-learning-for-trading (21.3k stars) | Two data claims tested. WIKI prices "survivorship-bias free": **holds** — a company that died is held 0.85 times as often as one that lived. Restated SEC facts "dated to the later document": **not for income numbers** — 92% come from a later filing than their date, 2.6% with a different figure (AT&T revenue −22%, Tesla net income +23%). Neither changes a published result: no case study trades that panel. |

## Studies

| Study | Headline |
|---|---|
| [Today's S&P 500 list, backtested](survivorship/sp500-todays-list.md) | A backtest on today's 503 members beats the index as it was (dead members included) by **+5.1 points a year in 2018–2026 and +5.6 in 2013–2017** (t 6.8 and 5.6, every year). Split: the list knows the winners (+3.1 / +5.4) and skips the index's turnover (+2.0 / +0.2). Pre-registered, four known-answer controls; a first attempt's failed mirror is reported, not hidden. |
| [Prediction-market calibration](prediction_markets/README.md) | Long shots priced 2–15 cents a week before close win 5.0% of the time at a price of 6.2% on Polymarket (real money, 1,102 contracts, clustered z +1.92) and 5.1% at 6.5% on Manifold (play money, z +1.93): the favourite–longshot bias, the same size on both. Pre-registered, four known-answer controls. |
| [Revised macro data, backtested as if known](revisions/fred-first-print-vs-revised.md) | A feature built from today's FRED is not the one a trader saw: 25 industry growth lines (G.17) ranked from the revised data agree with the first print at a rank correlation of **0.53**; for 18 headline series the direction of the monthly change differs in **about one month in seven** (one in five for industrial production, durable-goods orders, continuing claims). Pre-registered, four known-answer controls; the headline correlation I first pre-registered (0.955) is carried by 2020 and is reported as such. |

## How the work is verified

- **Pre-registration.** Before any measurement that could move a threshold, the rule, the forecast and a
  known-answer control are committed to the instrument file. The commit hash proves the order.
- **Known-answer controls.** Every instrument runs beside a case whose answer is known; a control that only
  just passes is counted as failed.
- **Nightly gate.** An unattended run every night: 939 contract tests, a ratchet that fails on any new unit-test
  failure, collection health for each data source, and a morning report.
- **Own forecasts are scored.** Each predicted effect size is written down first and scored afterwards; on
  the latest day 5 of 9 were right, and every miss on size underestimated the leak.

## How it was built

I did not write this code by hand. I designed the pipeline, the measurements and the acceptance criteria, and
directed AI coding agents (Claude Code, Gemini, Codex) to implement them; I reviewed every change through
tests and controls. The skill on show is specification and verification, not typing.

## One measurement, start to finish

Finding 1 began as one line from a second reviewer: SEC filings may be visible to the model before they
were public. The instrument `point_in_time/sec_acceptance_clock_530.py` first had to settle which clock the
acceptance timestamps are on, and its docstring keeps the whole record:

| Time (03.10) | Commit | What happened |
|---|---|---|
| 12:16 | `008209c2` | Rule, forecast and control committed: the right clock puts ≤ 1% of acceptances outside EDGAR's 06:00–22:00 New York window. My forecast: the timestamps are New York time. |
| — | — | First run: **STOPPED by the rule.** Outside the window — UTC reading 2.08%, New York reading 25.31%. Neither under 1%, and my forecast was wrong by a factor of twelve. The 1% was not moved. |
| 12:18 | `550174cd` | Attempt 2 of 2, committed before running: not a softer threshold but a different known answer — EDGAR dates anything accepted after 17:30 New York to the next business day. |
| 13:58 | `07720502` | Clock settled (literal UTC). 43% of filings were visible to the daily bar before acceptance; fix and tests committed. |
| 16:55 → 17:36 | `0d8e0b1e` → `5d95d930` | Same procedure for the 10-K/10-Q facts: 46%. |

Commit hashes refer to the private working repository.

## Map

| Path | What it shows |
|---|---|
| `point_in_time/sec_acceptance_clock_530.py` | the instrument above: rule, forecast, control and both attempts in its docstring |
| `point_in_time/corporate_filings_enricher.py`, `test_corporate_filings_are_events.py` | the fix for filings: an event becomes known at its acceptance second, not at midnight |
| `point_in_time/fundamentals_filed_clock_535.py` | the same check for 10-K/10-Q facts |
| `point_in_time/fundamentals_enricher.py`, `test_fundamentals_enricher_is_point_in_time.py` | the fix for fundamentals, and the tests that were red on the old code |
| `survivorship/what_survivorship_is_worth_in_our_own_data.py` | finding 3: what the hand-picked universe is worth with no model at all |
| `revisions/revision_distance_catalog_628.py`, `test_revision_distance_catalog_628.py` | the revisions catalog: first print against today's vintage, with its known-answer tests |
| `verification/nightly_gate.py`, `test_nightly_gate_report.py` | the nightly run and its report (the report itself is written in Ukrainian) |
| `verification/test_no_env_value_is_tracked.py` | no value from the local `.env` may sit in a tracked file, with a planted-key control |

These are excerpts: they import modules of the private repository and do not run on their own. They are
copied unchanged, except for one local folder path in `nightly_gate.py`.

Stack: Python, DuckDB, pandas, scikit-learn, pytest.
