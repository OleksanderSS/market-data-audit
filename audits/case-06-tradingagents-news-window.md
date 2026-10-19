# Audit case 6: TradingAgents — the news window closes after the market does

*An independent check of a public repository, done with the same instruments and rules this project uses on
its own data. TradingAgents is a widely used open-source multi-agent trading framework (Apache-2.0); this case
is about one timing choice in its backtest path, not about the quality of its agents.*

**Repository:** [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (about 111k stars on
13 Oct 2026). Issue filed with the numbers below: #1518.

> **Update, 16 October 2026 — fixed by the maintainers.** Issue #1518 was closed on 16 October; commit [`f5e3eae`](https://github.com/TauricResearch/TradingAgents/commit/f5e3eae) changes `memory/settlement.py` so that a decision is scored from the first close after its date. The text below is the audit as published before the fix.

**What happens.** For a run dated *d*, the news filter keeps an article when `start <= pub_dt < end + 1 day`, in UTC
(`dataflows/date_window.py::in_window`). That admits everything published until 00:00 UTC of *d+1* — 20:00 New
York in summer, three to four hours after the US close (00:00 UTC is 20:00 New York in summer, 19:00 in winter). The decision is then scored from the close of *d*
(`memory/settlement.py::fetch_returns`). News released after 16:00 New York on *d* is in the prompt, while the
market's reaction to it falls on *d+1*, inside the scored window. US earnings releases sit exactly there. The SEC
filings path has the same shape: it compares a filing *date* with the decision date, so a 10-Q accepted at 16:05 is
served to a decision made the same day.

**Why this matters.** The run reads the result and is then paid for the day the market reacts to it. Whether the model
reads the direction correctly is a separate question; the scored window contains a move the prompt already explains.

## Measured (predictions written before the run; record #702)

SEC EDGAR acceptance times and daily bars, 84 large US companies, 2015–2026.

| | |
|---|---|
| 8-K item 2.02 (earnings release) filings | 4,056 |
| …accepted after 16:00 New York on their filing date (all of them before 00:00 UTC, so inside the window) | **35.4%** (1,435); 93% of these between 16:00 and 16:59 |
| Next-day move after those events, abnormal \|close(d) → close(d+1)\| | **5.02 points**, against 1.20 on ordinary days of the same names: **4.2×** (over 1,433 of these events with price bars) |
| Share of the squared abnormal move over the 5-day holding window that falls on d+1 | **68%** |

**Control with a known answer.** Earnings released *before* the open (60% of filings) move on day *d* (2.5× ordinary)
and not on *d+1* (1.1×): their reaction is already in close(*d*), nothing leaks. After-close events show the mirror
image: *d* 1.1×, *d+1* 4.2×. The measurement separates the two cases, so the result is not a general "earnings days
are volatile" effect.

**A concrete case.** Nike, 1 Oct 2026: the earnings 8-K was accepted at 16:15 New York (20:15 UTC). Our own news capture
holds 62 Nike articles between 20:00 UTC and midnight UTC that day, among them a CNBC report of the shares sinking in
extended trading at 20:07 UTC. A run dated 1 Oct has them in the window and is scored from the 1 Oct close (35.15); the
next close was 33.87 (−3.6%).

## What a fix looks like

1. Cut news and filings at the decision time, not the calendar day: keep items published before 16:00 New York on *d*
   (exchange-calendar aware for other markets and early closes).
2. Or keep the calendar-day window and score from the next session (open or close of *d+1*).
3. For SEC data use the filing's acceptance time, not its date — and check which clock that field carries
   (see the "three clocks" note: one field, three time conventions).

## Method and limits

Filing times: EDGAR `acceptanceDateTime` after the clock repair of record #668. Daily bars: Yahoo, abnormal return
against the market. Event counting is by filing, one event per filing. Nothing here measures whether the agents'
decisions are good — only that the scored window contains information the prompt already had for about a third of
earnings events. The repository had fixed a neighbouring problem (an article stamped exactly at midnight, #1126); the
window up to midnight is by design, and the point is where the market close sits inside it.
