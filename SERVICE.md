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
| **Revised data as if known** | Macro series downloaded today carry revisions the trader never saw | Direction of the monthly change differs from the first print in one month in seven across 18 FRED series; a G.17 industry signal agrees with its first print at 0.53 ([study](revisions/fred-first-print-vs-revised.md)) |
| **Costs on the wrong price** | Commission or slippage priced on adjusted prices, or not at all | Commission overstated 5× on adjusted closes ([finding 6](README.md)) |
| **Fills on the deciding bar** | The trade is filled at the close that produced the signal | A standard check in every audit: the result with a one-bar delay |

Every finding comes with a **measured effect** — your result as shown, then the same strategy with one thing
fixed. A defect I cannot measure is reported as such and not counted. Before running, I write down what I am
looking for and what I expect; the report says which expectations failed, including mine.

## What I need from you

- The code (repository or archive) and how to run it.
- The data it uses, or where it comes from.
- The result you are relying on (return, Sharpe, a chart).

## What you get

- A report in the format of the public cases: a table of findings, each with where it is in the code and how
  much it changes the result; the result out of sample, with costs, with a one-bar delay, against buy-and-hold.
- The scripts that reproduce every number.

## Scope and price

- **Pilot — $150 fixed**, one strategy, for the first three clients (in exchange for permission to publish an
  anonymised case).
- **Standard — $300–500**, one strategy, depending on the data involved (one asset vs a universe of stocks,
  daily vs intraday).
- Turnaround: typically 3–5 working days from receiving runnable code and data.

## Contact

alexanderdovgulya@gmail.com

*I am not an investment adviser, and an audit is not a recommendation to trade or not to trade.*
