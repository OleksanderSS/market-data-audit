# Audit case 8: FinGPT-Forecaster — quarterly figures matched by quarter end, not by publication

*An independent check of a public repository, done with the same instruments and rules this project uses on
its own data. FinGPT is a widely used open-source financial language-model project; this case is about one data
choice in the Forecaster's prompt construction, not about the quality of the model.*

**Repository:** [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT). Issue filed with the
numbers below: #280.

**What happens.** `fingpt/FinGPT_Forecaster/data.py::get_basics` keys Finnhub's quarterly `basic_financials` series by
`period` — the fiscal quarter's **end** date — and for each row takes the latest period with
`Start(i−2) <= period < End(i)`. No publication date appears anywhere in the selection. `prompt.py::get_all_prompts`
then writes those figures into the prompt of the row being predicted, as "reported at {period}", under "Based on all
the information before {start_date}… prediction for next week". The inference path does the same for any past date
(`data_infererence_fetch.py:69` keeps `basic['period'] <= curday`).

Companies publish a quarter two to six weeks after it ends. A quarter that ended 0–14 days before the prediction week
is in the prompt while it is still unpublished; when the release falls inside the predicted week, the prompt holds the
numbers that move the label.

## Measured (record #704)

SEC EDGAR filing times and daily bars, 84 large US companies, 2015–2026. We replicated the weekly windows of
`get_returns` and the selection of `get_basics`; the quarter end comes from the 10-Q/10-K report date.

| | |
|---|---|
| Quarters | 3,770; median 27 days from quarter end to the earnings release (8-K item 2.02) |
| Prompt weeks that receive a quarter's basics | 11,310; in **98.5%** of them the quarter had not been released by the Friday close before the prediction week (99.4% for the DOW30 names) |
| Quarters whose release falls **inside** the predicted week | **16.9%** (19.9% for DOW30) |
| Those weeks, mean \|weekly abnormal return\| | **1.85×** an ordinary week (t = 11.1 over 635 events, 3.5 over per-company means); 1.27× on the DOW30 subset (236 events, 18 names) |

**Controls behave as they should:** the week before the release 0.98×, the week after 0.95× — the excess sits exactly
on the release week, not on earnings-season names in general.

So nearly every training and test prompt that carries basics shows figures the market did not yet have, and about one
quarter in six puts the release itself inside the label window. The model is fine-tuned on these prompts, and the test
split is built the same way, so the flaw is in both halves.

## What a fix looks like

Select a quarter by when it became **public**, not when it ended: keep a period only if its filing or earnings-release
time is before the decision point — the 10-Q/10-K or 8-K 2.02 `acceptanceDateTime` from SEC EDGAR, or Finnhub's
earnings-calendar date — and label the figures with that date.

## Method and limits

Event counting is by quarter, one event per release. The DOW30 ratio (1.27×) is smaller than the 84-name ratio (1.85×)
and is reported beside it, not instead of it. Nothing here measures whether the model's forecasts are good — only that
the prompt it is trained and tested on contains unpublished figures for almost every row.
