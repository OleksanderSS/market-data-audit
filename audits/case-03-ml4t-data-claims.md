# Audit case 3: "Machine Learning for Trading" — two data claims, one holds

*An independent check of a public repository, done with the same instruments and rules this project uses on
its own data. The repository is the code of a widely read book, shared openly under MIT; this case tests two
statements the code makes about its own data. One holds and one does not, and neither changes a published
result of the book. Both outcomes are reported.*

**Repository:** [stefan-jansen/machine-learning-for-trading](https://github.com/stefan-jansen/machine-learning-for-trading)
(21.3k stars, 3rd edition), read at commit
[`24849f7`](https://github.com/stefan-jansen/machine-learning-for-trading/tree/24849f728c98b8b12d4b7d1c140d7d44e0321332)
(9 October 2026). Each claim was pre-registered before its instrument ran: the rule, a forecast of my own, a
known-answer control, and what each outcome would mean.

## Summary

| # | The claim in the code | Verdict | Measured |
|---|---|---|---|
| 1 | The US equity prices (Quandl WIKI, 3,199 companies) are "survivorship-bias free … including delisted stocks". | **Holds** | WIKI holds a company that died in 2013–2018 about as often as one that lived: 31.5% against 37.1%, a ratio of **0.85** (threshold for "holds": 0.80). |
| 2 | In the SEC fundamentals panel, a restated fact is dated to the later filing, so the dates err on the safe side. | **Does not hold for income numbers** | 92% of income numbers come from a later filing than their date; 7 of the 270 that could be compared (**2.6%**) differ from what the dated filing reported — median change 2.1%, largest 22–23%. |

## Claim 1 — WIKI is free of survivorship bias: holds

`load_us_equities()` ([`data/equities/loader.py`, line 133](https://github.com/stefan-jansen/machine-learning-for-trading/blob/24849f728c98b8b12d4b7d1c140d7d44e0321332/data/equities/loader.py#L133))
describes WIKI as survivorship-bias free. WIKI never covered the whole market, so the right test is not whether
it holds dead companies but whether it holds them **as often as living ones**.

| | Companies | Held by WIKI | Share |
|---|---|---|---|
| Stocks delisted 01.2013 – 02.2018 | 1,649 | 520 | 0.315 |
| Stocks alive at WIKI's end (03.2018), listed by 2017 | 5,738 | 2,128 | 0.371 |
| **Ratio, dead / alive** | | | **0.85** |

Controls: 98.8% of the S&P 500 members of February 2018 are matched to WIKI (threshold 95%); the dead count
reproduces an earlier, independent measurement (520); two random halves of the living give a ratio of 0.996.
**My forecast was wrong:** I expected 0.42–0.57, i.e. a source that drops the dead. It does not — it covers
about a third of the market, dead and alive alike. The claim stands.

## Claim 2 — restated facts are dated to the later filing: not for income numbers

The book's notebook on XBRL fundamentals explains the long tail of its filing-lag histogram this way: a fact
restated in a later filing is "dated to the later document", which is conservative
([chapter 4, `04_sec_xbrl_fundamentals`, line 298](https://github.com/stefan-jansen/machine-learning-for-trading/blob/24849f728c98b8b12d4b7d1c140d7d44e0321332/04_fundamental_alternative_data/04_sec_xbrl_fundamentals.py#L298)).

The panel builder ([`data/equities/fundamentals/xbrl_download.py`, lines 214 and 237](https://github.com/stefan-jansen/machine-learning-for-trading/blob/24849f728c98b8b12d4b7d1c140d7d44e0321332/data/equities/fundamentals/xbrl_download.py#L214))
keeps **one row per company and period end**. The row's filing — and with it `announcement_date` — is taken
from the first concept fetched, total assets. Revenue, operating income and net income are then written into
that row from the SEC Frames API, which returns each figure from the **latest** filing that reported the
period — for a quarter, usually the next year's 10-Q, where it appears as a comparative. So the statement is
true for total assets and not for the income numbers: those carry the date of the original report even when
they come from a later one.

**Step 1 — where the numbers come from.** The book's default panel (20 companies, 2022–2024):
347 of 377 income numbers (**92%**) come from a filing other than the one whose date the row carries, 344 of
them from a later year. Across every company in the Frames data the share is 83%. Known-answer control:
Apple's March-2022 quarterly net income is served from a 2023 filing.

**Step 2 — whether the number changed.** A later filing usually repeats the original figure, and then the
date is harmless. Each pair was compared with the figure in the filing the row is dated to (SEC
`companyconcept`):

| Numbers from a later filing | 347 |
|---|---|
| No data at SEC (empty answer twice: KO, V, ABT) | 63 — set aside |
| Compared | 284 |
| Same figure (within 0.5%) | 263 |
| **Changed** | **7** — 2.6% of the 270 that could be compared; median change 2.1% |
| Not in the dated filing under that tag | 14 — 3 of them dated *later* than the figure's source (the safe side); 11 not resolved |

The changed figures, as a backtest on this panel would see them on the original filing date:

| Company, item, quarter | In the filing of that date | In the panel | Change |
|---|---|---|---|
| AT&T, revenue, Q1 2022 | $38.1 bn | $29.7 bn | −22.0% |
| Tesla, net income, Q1 2024 | $1.13 bn | $1.39 bn | +23.1% |
| Tesla, net income, Q2 2024 | $1.48 bn | $1.40 bn | −5.3% |
| Pfizer, revenue, Q1–Q3 2023 | $18.28 / 12.73 / 13.23 bn | $18.49 / 13.01 / 13.49 bn | +1.1% to +2.1% |
| AT&T, operating income, Q1 2022 | $5.64 bn | $5.54 bn | −1.8% |

AT&T's revenue is the figure restated after the WarnerMedia spin-off of April 2022; on the date it is filed
under, the market had the $38.1 bn figure.

Controls: pairs whose figure comes from the dated filing itself — 30 of 30 the same; Apple's March-2022 net
income, $25.01 bn in both. **The first attempt was void and is reported:** SEC returned empty files for three
companies and my code counted them as "not in the filing" (24.8%); the second attempt, registered before it
ran, fetched empty files again and set them aside. **My forecast was wrong again:** I expected 5–20% changed;
it is 2.6%.

**The pre-registered measure** — changed, or not in the dated filing at all — is 7.5% (2.6% + 4.9%) against a
threshold of 5%, so by the rule written before the run the defect is material. The breakdown is stricter than
the rule: the 11 unresolved figures are not counted as look-ahead here. The dated filing has no figure under
that tag; whether the company had published it in another form on that date was not measured.

## What this changes for the book: nothing published

- Of the repository's 1,213 Python files, two read the panel: the chapter 4 notebook and chapter 8's factor
  construction, which the book itself labels "scaffolding", not real-data factor values. Neither case study on
  US equities trades it: one uses price-derived features only, the other a published characteristics panel
  (Chen, Pelger and Zhu) that lags accounting data by six months.
- `announcement_date` is a date with no time of day. In my own pipeline 46% of 10-K/10-Q facts were accepted
  after the close of their filing date, so a same-day close fill leaks. The book joins on the filing date
  inclusively, but its own point-in-time chapter states that a close-of-day signal can be acted on no earlier
  than the **next open** — under that rule an after-close filing is safe. Checked; no finding.
- The notebook's as-of query sorts "an original filing and a later restatement" of the same quarter so the
  restatement wins — with one row per period end, that case never arises in this panel; the restated number
  is already in the original row.

## What a fix looks like

1. Key the panel by (company, period end, **filing**), one row per fact as each filing reported it — the SEC
   `companyfacts` endpoint gives every filing's figure with its accession number.
2. Date each figure by its own filing's acceptance time, not the date of another concept's filing.
3. For as-of queries, take the latest *filing* known on the date, then the latest period within it.

## Method and limits

Instruments, rules and forecasts were committed before each run; attempt counters are kept. The WIKI check
uses a listings store with delisting dates (asset type Stock) matched on ticker, so renamed companies count as
not held — this understates WIKI's coverage of the living and biases the ratio *up*, against my forecast. The
XBRL check covers the book's default 20 companies, 2022–2024, three income concepts. Nothing here measures the
book's models — only what its data tells them.
