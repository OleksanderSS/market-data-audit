# Sample audit report — what a client receives

> **This is a sample.** It is built from a public case ([case 6](case-06-tradingagents-news-window.md), TradingAgents,
> Apache-2.0), not from client data, to show the format of a paid report. The "client" is hypothetical; every number is
> real and comes from the measurement behind case 6.

## 1. The decision this audit supports

| | |
|---|---|
| **Client's decision** | Whether to keep using the framework's backtest score to select agent configurations before a paper-trading launch |
| **Deadline** | before the launch date the client named |
| **Headline claim checked** | "The scored return of a run dated *d* reflects only information available at the decision time on *d*" |
| **Code and data received** | public repository at commit 1394a3f; no client data needed — the check uses SEC EDGAR acceptance times and daily bars |
| **Out of scope** | whether the agents read the direction of the news correctly; the quality of any configuration |

## 2. Verdict in one paragraph

**The claim does not hold for about a third of earnings events.** The news window of a run dated *d* closes at 00:00 UTC
of *d+1* — three to four hours after the US close — while the score is taken from the close of *d*. Earnings released
after the close are in the prompt, and the market's reaction to them (4.2× an ordinary day) lands inside the scored
window. **Recommended decision: fix, then re-run** the selection; scores from the current window should not be used to
compare configurations. *(Status at delivery: the maintainers fixed it upstream in
[`f5e3eae`](https://github.com/TauricResearch/TradingAgents/commit/f5e3eae) after the issue with these numbers.)*

## 3. Findings

Each line carries its status: **Measured** (a number from a script, with a control), **Read in code** (seen in the
source, effect not measured), **Not measured** (a question this audit did not answer).

| # | Finding | Where | Effect on the headline | Status |
|---|---|---|---|---|
| 1 | News window admits items until 00:00 UTC of *d+1*; score starts at close(*d*) | `dataflows/date_window.py::in_window`, `memory/settlement.py::fetch_returns` | 35.4% of earnings releases fall inside the window after the close; their next-day move is 5.02 points vs 1.20 on ordinary days (**4.2×**) | **Measured** |
| 2 | Of the squared move over the 5-day scored window, day *d+1* carries | same | **68%** — most of what is scored is the reaction to news already in the prompt | **Measured** |
| 3 | SEC filings compared by date, not acceptance time: a 10-Q accepted at 16:05 is served to a decision the same day | SEC filings path, `filed <= as_of_date` | same mechanism as #1; size not separated from #1 | **Read in code** |
| 4 | Whether the agents exploit the leaked news (direction of decisions) | — | unknown; the audit shows the window *contains* the answer, not that the model *uses* it | **Not measured** |

**Denominator, next to every headline number:** 4,056 earnings 8-K filings (item 2.02), 84 large US companies,
2015–2026; 1,435 inside the after-close window, **1,433 of them with price bars** (62 companies); 2,419 before-open
events as the control; ordinary-day baseline over 562,739 company-sessions. The 2 window events without bars are
excluded, not zero-filled.

## 4. Controls — why this is not "earnings days are volatile"

| Control | Known answer | Result |
|---|---|---|
| Before-open releases (60% of filings) | react on *d*, not on *d+1* | *d* 2.52×, *d+1* 1.14× — as expected |
| After-close releases (the window) | mirror image: quiet *d*, loud *d+1* | *d* 1.11×, *d+1* 4.18× — as expected |
| Significance | over per-company means (events of one company are not independent) | t = 8.4 over 62 companies |

Predictions were written before the run (window share 30–36%, ratio 2.5–4.5×, *d+1* share 0.45–0.75); all three held.
One attempt.

## 5. What a fix looks like, and how to check it

1. Cut news and filings at the decision time (16:00 New York, exchange-calendar aware), **or** keep the calendar window
   and score from the next session.
2. Use acceptance time, not filing date, for SEC data — and check which clock the field carries
   ([three clocks](../point_in_time/sec-three-clocks.md)).
3. **Re-check after the fix:** the after-close share inside the window must fall from 35.4% to 0%, and the *d+1* ratio
   of scored events to about 1.1× (the before-open control level).

## 6. Reproduction

A paid report ships with the scripts that produce every number in sections 3–4, the raw fetched inputs, and the exact
commands. For this public sample the measurement script is not part of this repository.

## 7. Limits

One framework, one mechanism, daily bars; large US companies only. The effect size is the size of the *opportunity*
to leak, not of the leak in the client's results — that needs the client's own run logs (finding 4).
