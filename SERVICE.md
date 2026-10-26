# Backtest audit — does your result survive the data?

Most backtests that show a profit are measuring something other than the strategy: a lucky period, a list of
companies chosen with hindsight, a price the trade could never have got. Free tools now check the statistics of
overfitting (deflated Sharpe, PBO). This audit checks what they do not: **the data and the time line the
backtest stands on.**

## What I check

| Family | What goes wrong | Example from my own pipeline or a public case |
|---|---|---|
| **Look-ahead in time stamps** | A date without a time of day lets the model see a filing, a news item or a bar before the market could | 46% of SEC filing facts were visible before EDGAR accepted them ([finding 1](README.md)) |
| **Survivorship in the universe** | Today's index list tested on the past is a list of winners | FinRL's Dow 30 list earns **+4.48 points a year** over the real index by itself ([case 2](audits/case-02-finrl-ticker-list.md)); today's S&P 500 list, **+5.1 to +5.6** ([study](survivorship/sp500-todays-list.md)) |
| **Survivorship in the source** | Free data sources drop dead companies entirely | Yahoo no longer serves a single day of Walgreens, a Dow member 2018–2024 |
| **Training = testing** | The strategy is scored on the period it was fitted to | 24 agents trained and scored on one year of GOOG; out of sample the "profit" disappears ([case 1](audits/case-01-stock-prediction-models.md)) |
| **Revised data as if known** | Macro series downloaded today carry revisions the trader never saw | Direction of the monthly change differs from the first print in one month in seven across 18 FRED series; a G.17 industry signal agrees with its first print at 0.53 ([study](revisions/fred-first-print-vs-revised.md)); a public panel dates AT&T's restated revenue (−22%) to the original filing ([case 3](audits/case-03-ml4t-data-claims.md)) |
| **Costs on the wrong price** | Commission or slippage priced on adjusted prices, or not at all | Commission overstated 5× on adjusted closes ([finding 6](README.md)) |
| **Fills on the deciding bar** | The trade is filled at the close that produced the signal | A standard check in every audit: the result with a one-bar delay |

Every finding comes with a **measured effect** — your result as shown, then the same strategy with one thing
fixed. A defect I cannot measure is reported as such and not counted. Before running, I write down what I am
looking for and what I expect; the report says which expectations failed, including mine.

## What I need from you — five questions before any work

1. **The decision and the deadline** — what you will do differently depending on the result, and by when.
2. **One headline claim** — the number or statement you rely on (a return, a Sharpe, "no look-ahead").
3. **The minimum to reproduce it** — the code and how to run it, the data or where it comes from.
4. **Your right to share it** — that you may pass this code and data to a third party, and how long I may keep
   them (deleted after delivery unless agreed otherwise).
5. **In and out of scope** — what the report covers and what it does not.

If the first two have no answer yet, we start with a short call instead of a quote.

## What you get

- A report in the format of the [sample report](audits/sample-report.md): the decision it supports, a verdict in
  one paragraph, a table of findings each marked **Measured**, **Read in code** or **Not measured**, the denominator
  next to every headline number, the controls with a known answer, and how to check the fix.
- The result out of sample, with costs, with a one-bar delay, against buy-and-hold, where these apply.
- The scripts that reproduce every number.

## Scope and price

- **Free sample — one public backtest.** You pick one public repository that runs on public data. I run five fixed
  checks: time-of-day look-ahead, universe survivorship, price type and costs, a one-bar delay, train/test overlap
  and temporal leakage. This is a standard first set, not a guarantee of finding every kind of error, and the
  report states the result even when nothing is found. You get a 1–2 page report within 5 working days of the
  choice, with one round of questions. If the code does not run or needs private data, the sample is a desk review
  of the description and says so. One sample per firm. I may publish the report naming the public repository; your
  firm is not named without separate written consent.
- **Pilot — $150 fixed**, one private strategy, for the first three clients (permission to publish an anonymised case).
- **Standard — $300–500**, one strategy: the five checks above plus the out-of-sample result, costs on traded prices
  and a one-bar delay, with reproducing scripts. Paid data, if needed, is quoted and agreed in writing before I buy
  it; extra work beyond the agreed scope only with your prior consent.
- Turnaround: counted from receiving runnable code and data (for a desk review, from agreeing the description and
  scope), 3–5 working days; a desk review from a description alone measures effects only where public data allows.

## Contact

alexanderdovgulya@gmail.com

*I am not an investment adviser, and an audit is not a recommendation to trade or not to trade.*
