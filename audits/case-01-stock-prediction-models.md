# Audit case 1: "Stock-Prediction-Models" — where the trading agents' profit comes from

*An independent audit of a public repository, done with the same instruments and rules this project uses on
its own pipeline. The author shared the code openly under Apache-2.0; this is not a criticism of the effort,
which is educational and clearly labelled as such, but a worked example of what a backtest has to show before
a number in it means anything.*

**Repository:** [huseinzol05/Stock-Prediction-Models](https://github.com/huseinzol05/Stock-Prediction-Models)
(9.5k stars, last change April 2023), folder `agent/` — 24 notebooks of trading agents (turtle, moving
average, Q-learning family, actor-critic, evolution strategies, neuro-evolution), each ending in a chart titled
"total gains … total investment …%".

**Method, fixed before reading the code** (pre-registration committed first): five families of defects, the
same ones found in my own pipeline — look-ahead, evaluation on training data, missing costs, an asset chosen
with hindsight, parameters fitted to the reported period. A defect counts as a finding only with a measured
effect: the author's result, then the same strategy with one thing fixed. All 24 notebooks are reported, not
only those with a problem.

## Findings

| # | What is the case | Where | Effect, measured |
|---|---|---|---|
| 1 | **One stock, one year.** Every agent trades Alphabet (GOOG) from 2 Nov 2016 to 1 Nov 2017 — a year in which simply holding the stock returned **+33.4%**. | 24 of 24 notebooks read `dataset/GOOG-year.csv` | Any agent that is mostly long "profits". No buy-and-hold comparison is shown. |
| 2 | **Trained and scored on the same days.** The agent is trained for hundreds of iterations on the year and then evaluated on the same year. | 24 of 24 | Evolution-strategy agent, code unchanged, 10 seeds: **+36.4%** median on the training year (range +31.9 to +39.0) vs **+33.4%** buy-and-hold. On the **98 sessions that followed** (2 Nov 2017 – 27 Mar 2018, never seen): **−2.5%** median (range −8.6 to +3.2) vs buy-and-hold **−2.0%**. |
| 3 | **No trading costs.** No commission, spread or slippage anywhere ("cost" in the code is the network's loss function). | 0 of 24 notebooks model a cost | 0.1% per trade: training year −1.3 points; out of sample −3.05% median. Small here only because the agents trade one share at a time. |
| 4 | **One run shown.** The reported figure is a single draw of a random training procedure. | all learning agents | Across 10 seeds the training-year result spans +31.9% to +39.0%, and the out-of-sample result spans −8.6% to +3.2%. |
| 5 | **Cash-only accounting.** Shares still held at the end are not valued, so an agent ending long looks like a loss. | evaluation loop | Latent: in the 10 runs measured the agent held nothing at the end, so the effect here was 0. |
| 6 | **Decision and fill on the same close.** The action on day *t* is computed from day *t*'s close and filled at that same close. | all agents | A mild form of look-ahead; not measured in this case. |

**What the profit is.** The chart's "total gains" is, almost entirely, Alphabet's good year. On the training
year the agent adds about 3 points over holding the stock; on the following months it adds nothing (a median
0.5 points worse than holding, before costs).

## A finding I withdrew

Reading a filtered view of one notebook, I first concluded that its "total investment %" reported only the
last trade. Checking all 24 notebooks showed the total is recomputed correctly before it is returned; the line
had been hidden by my own filter. The claim was withdrawn before publication. A check that can catch its own
false accusations is part of the method, not a footnote to it.

## What a fix looks like

1. Train on one period, report on a later one the model never saw — and say which is which.
2. Put buy-and-hold of the same asset beside every result.
3. Charge a cost on every trade, on the price actually traded.
4. Run the random parts many times and report the spread, not one draw.
5. Test on more than one asset, chosen before seeing results.

## Reproduce

The measurement script runs the notebook's own agent classes unchanged and only replaces the data and the
evaluation around them; out-of-sample prices are Quandl WIKI (frozen March 2018). Numbers above are from
10 seeds (0–9), population 15, 500 iterations, window 30 — the notebook's settings.

---

*Scope: one notebook measured in depth (evolution strategy, numpy only); the other 23 were read, not run —
most need TensorFlow 1.x. The findings that apply to all 24 (one asset and year, no out-of-sample period, no
costs) are read from the code, not inferred.*
