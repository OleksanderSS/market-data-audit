# Where market data lies: an audit of a forecasting pipeline

A one-person research project: a 7-stage pipeline that collects US equity data (prices, SEC filings, FRED
macro series, news, options, analyst estimates) and tests whether any of it forecasts returns.

**The headline result is negative, and it is the point of this repository.** After realistic trading costs no
strategy beat doing nothing. What the project did produce is a set of data defects that would have made
the opposite look true, each found, measured and fixed with a test that fails on the old code.

This repository is a curated extract. The full working repository (1,174 commits, Ukrainian-language
research log) is private; the excerpts here are unchanged apart from removed paths and credentials.

## Findings

| # | What was wrong | How big | How it was proved |
|---|---|---|---|
| 1 | **Look-ahead in SEC fundamentals.** `filed` is a date with no time; stored as midnight, it let the model see a filing on the morning of the day it was filed. | 46% of 10-K/10-Q facts were visible before EDGAR accepted the filing (filings index: 43%). | Acceptance timestamps joined by accession number: 99.98% matched; control — filings accepted before 17:15 New York must fall on `filed` — 99.87%. |
| 2 | **The same shape in three sources.** Any date without a time of day turned out to leak the same way. | 3 sources. | Now the first check run on every new source. |
| 3 | **Survivorship bias.** The 105 stocks were chosen knowing which companies survived. | Long the list, short the market, no model: +6.9% a year, Sharpe 1.22, t = 6.3 (1996–2023). | Any signal is measured against this bar, not against zero. |
| 4 | **Tails deleted.** A cleaning step dropped every bar more than 3σ from its moving average. | 14,598 real price moves — crisis days, earnings days, overnight gaps. | 98–99% of the dropped moves persisted afterwards, so they were real, not bad ticks. |
| 5 | **Wrong model type.** Three-class targets (−1/0/1) were inferred as regression. | 308 models trained and scored by R². | Target type is now read from the target registry, not guessed from the values. |
| 6 | **What costs really are.** | 63% of friction was per-share commission; with it removed, the book turns positive and still trails buy-and-hold fourfold. | Cost model decomposed term by term. |

## How the work is verified

- **Pre-registration.** Before any measurement that could move a threshold, the rule, the forecast and a
  known-answer control are committed to the instrument file. The commit hash proves the order.
- **Known-answer controls.** Every instrument runs beside a case whose answer is known; a control that only
  just passes is counted as failed.
- **Nightly gate.** An unattended run every night: 889 contract tests, a ratchet that fails on any new unit-test
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
| `verification/nightly_gate.py`, `test_nightly_gate_report.py` | the nightly run and its report (the report itself is written in Ukrainian) |
| `verification/test_no_env_value_is_tracked.py` | no value from the local `.env` may sit in a tracked file, with a planted-key control |

These are excerpts: they import modules of the private repository and do not run on their own. They are
copied unchanged, except for one local folder path in `nightly_gate.py`.

Stack: Python, DuckDB, pandas, scikit-learn, pytest.
