# Audit case 2: FinRL's Dow 30 list — how much "beating the Dow" the list earns by itself

*An independent check of a public repository, done with the same instruments and rules this project uses on
its own data. FinRL is a widely used, actively maintained open-source framework (MIT); this case is about one
data choice in its default configuration, not about the quality of its agents.*

**Repository:** [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) (16.5k stars).
In `finrl/config.py` agents train on **2014-01-06 to 2025-12-31**; `finrl/config_tickers.py` gives the universe
as `DOW_30_TICKER` — and that list is the Dow Jones Industrial Average **as of 8 November 2024**: it includes
Amazon (joined February 2024), Nvidia and Sherwin-Williams (joined November 2024), and leaves out the names
they replaced. Agents are then compared with the Dow.

**Why this matters.** A list chosen today and back-tested over the past is a list of winners: the companies
that did badly left the index and are not in it. Any strategy that trades the list — including "hold all 30" —
inherits that advantage before it makes a single decision.

## Measured (pre-registered before the run)

| | 2014–2025, a year |
|---|---|
| **L** — FinRL's 30 names, equal weight, rebalanced daily | **+16.87%** |
| **P** — the Dow as it actually was on each day, equal weight | **+12.39%** |
| **Premium of the list alone, L − P** | **+4.48 points a year** (a lower bound — see below) |
| **F** — the Dow of January 2014, frozen (mirror: no hindsight) | +12.89%, i.e. F − P = +0.50 |

The list beats the index-as-it-was in **10 of 12 years**. In 2025 the two are identical (0.00) — after
8 November 2024 the real Dow *is* FinRL's list, which doubles as a check that the measurement is wired
correctly. The frozen 2014 list, which knows nothing of the future, shows almost no premium; the premium comes
from knowing who would be in the index in 2024.

**A lower bound, and a second data trap.** Walgreens Boots Alliance was a Dow member from June 2018 to
February 2024 and lost roughly two-thirds of its value in that time. Its price history is **no longer served by
Yahoo Finance at all** (delisted in 2025). The index-as-it-was above therefore leaves Walgreens out for those
years, which flatters P; the true premium of the list is larger than 4.48 points. Anyone rebuilding a historical
index from a free source meets the same silent survivorship.

## What a fix looks like

1. Use point-in-time index membership (the constituents as of each date), not today's list.
2. Keep delisted companies' prices — from a source that retains them — for the years they were members.
3. Report agents against the same point-in-time universe, so the benchmark and the strategy start from the
   same knowledge.

## Method and limits

Membership: Wikipedia, *Historical components of the Dow Jones Industrial Average* (saved for the audit), mapped
from company names to tickers; known-answer control — the snapshot of 8 Nov 2024 equals `DOW_30_TICKER`,
30 of 30. Prices: daily adjusted closes (Yahoo). Equal weight is used for both L and P so that only the
*choice of names* differs; the Dow itself is price-weighted. Nothing here measures FinRL's agents — only what the
universe gives them for free.
