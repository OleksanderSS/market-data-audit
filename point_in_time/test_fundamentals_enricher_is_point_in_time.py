"""Value ratios must be built from what was on the record at the bar.

The first non-price features in this system. All 430 existing ones are derived
from price: measured 2026-08-23, the strongest reaches an out-of-sample IC of
0.046 and no model built from all of them beats it. So these matter -- and they
are worth nothing if they read the future.

Three ways they could, each with a test:

  the filing date   A June quarter reaches the SEC in August. Keyed on the
                    period it describes, it would appear six weeks early.
  the restatement   The same quarter is reported again by later filings; 1,972
                    of Apple's 2,939 facts are such repeats. A bar in 2019
                    reading a 2021 correction is reading the future.
  the span          NetIncomeLoss arrives for the quarter AND the year to date,
                    same end date, same filing. Mixing them multiplies earnings
                    by up to four, in a direction nothing downstream detects.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.enrichers.fundamentals_enricher import FundamentalsEnricher


@pytest.fixture
def enricher():
    return FundamentalsEnricher()


def _bars(dates, ticker="PRB", close=100.0):
    return pd.DataFrame({
        "ticker": [ticker] * len(dates),
        "datetime": pd.to_datetime(dates),
        "close": [close] * len(dates),
    })


def _fact(concept, value, filed, end, start=None, ticker="PRB"):
    return {
        "ticker": ticker, "concept": concept, "value": float(value),
        "filed": pd.Timestamp(filed), "period_end": pd.Timestamp(end),
        "period_start": pd.Timestamp(start) if start else pd.NaT,
    }


def test_a_bar_before_the_filing_sees_nothing(enricher):
    """The gap is real: Apple's shortest is 25 days, the median 216."""
    facts = pd.DataFrame([
        _fact("StockholdersEquity", 1_000, filed="2024-08-05", end="2024-06-30"),
        _fact("CommonStockSharesOutstanding", 100, filed="2024-08-05", end="2024-06-30"),
    ])
    out = enricher._enrich_impl(_bars(["2024-07-15", "2024-08-20"]), sec_fundamentals=facts)

    assert out["fund_data_available"].tolist() == [0, 1]
    assert pd.isna(out["fund_price_to_book"].iloc[0]), (
        "the July bar used a number filed in August"
    )
    assert pd.notna(out["fund_price_to_book"].iloc[1])


def test_a_bar_sees_the_original_not_the_later_restatement(enricher):
    """What was known THEN, not what is known now."""
    facts = pd.DataFrame([
        _fact("StockholdersEquity", 1_000, filed="2024-05-01", end="2024-03-31"),
        _fact("StockholdersEquity", 400, filed="2025-02-01", end="2024-03-31"),
        _fact("CommonStockSharesOutstanding", 100, filed="2024-05-01", end="2024-03-31"),
    ])
    out = enricher._enrich_impl(_bars(["2024-06-01", "2025-06-01"]), sec_fundamentals=facts)

    # close 100 x 100 shares = 10,000 market cap.
    assert out["fund_price_to_book"].iloc[0] == pytest.approx(10.0), (
        "the 2024 bar used the correction filed in 2025"
    )
    assert out["fund_price_to_book"].iloc[1] == pytest.approx(25.0)


def test_the_quarter_is_used_and_not_the_year_to_date(enricher):
    """Both end the same day and come from the same filing."""
    facts = pd.DataFrame([
        _fact("NetIncomeLoss", 1_072, filed="2024-08-05",
              end="2024-06-30", start="2024-04-01"),      # the quarter
        _fact("NetIncomeLoss", 3_698, filed="2024-08-05",
              end="2024-06-30", start="2023-10-01"),      # nine months
        _fact("StockholdersEquity", 10_000, filed="2024-08-05", end="2024-06-30"),
    ])
    out = enricher._enrich_impl(_bars(["2024-08-20"]), sec_fundamentals=facts)

    assert out["fund_return_on_equity"].iloc[0] == pytest.approx(1_072 / 10_000), (
        "the year-to-date figure was used; earnings would be ~3.5x too large"
    )


def test_negative_equity_does_not_become_a_cheap_looking_ratio(enricher):
    """Dividing by distress makes it rank as value; absent is the honest answer."""
    facts = pd.DataFrame([
        _fact("StockholdersEquity", -500, filed="2024-05-01", end="2024-03-31"),
        _fact("CommonStockSharesOutstanding", 100, filed="2024-05-01", end="2024-03-31"),
    ])
    out = enricher._enrich_impl(_bars(["2024-06-01"]), sec_fundamentals=facts)
    assert pd.isna(out["fund_price_to_book"].iloc[0])
    assert pd.isna(out["fund_debt_to_equity"].iloc[0])


def test_accounts_too_old_are_dropped_rather_than_carried_forever(enricher):
    """An unbounded carry-forward makes a flag measure the collected ERA.

    That mistake is already recorded here twice: `ffill` with no tolerance
    carried one reading forever, and `notna()` then measured when the data was
    gathered rather than what the bar knew.
    """
    facts = pd.DataFrame([
        _fact("StockholdersEquity", 1_000, filed="2020-05-01", end="2020-03-31"),
        _fact("CommonStockSharesOutstanding", 100, filed="2020-05-01", end="2020-03-31"),
    ])
    out = enricher._enrich_impl(_bars(["2020-06-01", "2024-06-01"]), sec_fundamentals=facts)

    assert out["fund_data_available"].tolist() == [1, 0]
    assert pd.isna(out["fund_price_to_book"].iloc[1]), (
        "four-year-old accounts were presented as current"
    )


def test_ratios_needing_no_price_survive_a_frame_without_one(enricher):
    facts = pd.DataFrame([
        _fact("AssetsCurrent", 2_000, filed="2024-05-01", end="2024-03-31"),
        _fact("LiabilitiesCurrent", 1_000, filed="2024-05-01", end="2024-03-31"),
    ])
    bars = _bars(["2024-06-01"]).drop(columns=["close"])
    out = enricher._enrich_impl(bars, sec_fundamentals=facts)

    assert out["fund_current_ratio"].iloc[0] == pytest.approx(2.0)
    assert pd.isna(out["fund_price_to_book"].iloc[0])


def test_missing_input_leaves_columns_absent_rather_than_wrong(enricher):
    out = enricher._enrich_impl(_bars(["2024-06-01"]), sec_fundamentals=None)
    for name in enricher.get_feature_names():
        assert name in out.columns
    assert out["fund_data_available"].iloc[0] == 0


def test_every_declared_feature_is_actually_added(enricher):
    facts = pd.DataFrame([
        _fact("StockholdersEquity", 1_000, filed="2024-05-01", end="2024-03-31"),
        _fact("Liabilities", 500, filed="2024-05-01", end="2024-03-31"),
        _fact("AssetsCurrent", 2_000, filed="2024-05-01", end="2024-03-31"),
        _fact("LiabilitiesCurrent", 1_000, filed="2024-05-01", end="2024-03-31"),
        _fact("CommonStockSharesOutstanding", 100, filed="2024-05-01", end="2024-03-31"),
        _fact("NetIncomeLoss", 200, filed="2024-05-01",
              end="2024-03-31", start="2024-01-01"),
    ])
    out = enricher._enrich_impl(_bars(["2024-06-01"]), sec_fundamentals=facts)
    for name in enricher.get_feature_names():
        assert name in out.columns, name
        assert pd.notna(out[name].iloc[0]), f"{name} came out empty on complete input"


def test_the_table_reaches_the_enricher_under_its_own_name():
    """Wiring, not arithmetic -- and this is where the last one broke.

    Stage 3 forwards every collected frame to enrichers as a kwarg named after
    its table, so `sec_fundamentals` arrives as `sec_fundamentals`. That holds
    only while nothing CLAIMS the table for a family: a family is concatenated
    into one shared frame and loses its name.

    `sec_filings` spent every run being claimed by `news`, where the date alias
    list said `filing_date` and the table said `filingDate`, so 24,365 dated
    filings were dropped over one capital letter.

    An explicit `data_type` in the collector's config beats everything else, so
    adding one here -- the class does declare `data_type = "fundamental"` --
    would silently collapse this table into a family.
    """
    import io

    import yaml

    from src.pipeline.stages.collection.orchestrator import classify_source_table

    config = yaml.safe_load(io.open("src/config/collectors.yaml", encoding="utf-8"))
    entry = config.get("collectors", config)["sec_fundamentals"]

    assert "data_type" not in entry, (
        "declaring data_type here makes the table a family, and a family is "
        "concatenated into a shared frame under another name"
    )
    assert classify_source_table("sec_fundamentals", entry) is None, (
        "something claimed sec_fundamentals; it must keep its own name so the "
        "enricher receives it as `sec_fundamentals`"
    )


def test_the_enricher_is_registered_in_both_places():
    """Registering in enrichment.yaml is not what turns an enricher on.

    corporate_filings sat registered and unused through a whole rebuild on
    2026-08-22 because `features.enabled_enrichers` is the switch and
    `enrichment.yaml` only supplies module and class.
    """
    import io

    import yaml

    def find(node, key):
        if isinstance(node, dict):
            if key in node:
                return node[key]
            for value in node.values():
                found = find(value, key)
                if found is not None:
                    return found
        return None

    enrichment = yaml.safe_load(io.open("src/config/enrichment.yaml", encoding="utf-8"))
    features = yaml.safe_load(io.open("src/config/features.yaml", encoding="utf-8"))

    registered = find(enrichment, "fundamentals")
    assert registered and registered.get("class") == "FundamentalsEnricher"
    assert (find(features, "enabled_enrichers") or {}).get("fundamentals") is True


def test_a_frame_with_a_non_default_index_is_not_realigned(enricher):
    """This is the one the other tests could never have caught.

    `_as_of` used to return a Series indexed by bar POSITION while the caller's
    frame carried its own index. `frame[col] - series` then aligned on index
    rather than position, pandas took the union, and 29,097 rows became 53,441.
    The 2026-08-23 rebuild died two and a half hours in on

        Length of values (53441) does not match length of index (29097)

    Every fixture above uses a default 0..n index, where alignment and position
    agree and the bug is invisible. Stage 3 hands over frames sliced by
    timeframe, whose index is anything but.
    """
    facts = pd.DataFrame([
        _fact("StockholdersEquity", 1_000, filed="2024-05-01", end="2024-03-31"),
        _fact("CommonStockSharesOutstanding", 100, filed="2024-05-01", end="2024-03-31"),
    ])
    bars = _bars(["2024-06-01", "2024-06-02", "2024-06-03"])
    bars.index = [7, 91, 4242]          # a real slice, not 0..n

    out = enricher._enrich_impl(bars, sec_fundamentals=facts)

    assert len(out) == 3, f"the frame grew to {len(out)} rows"
    assert list(out.index) == [7, 91, 4242], "the index was rebuilt"
    assert out["fund_data_available"].tolist() == [1, 1, 1]
    assert out["fund_price_to_book"].notna().all()


@pytest.mark.parametrize("tz", [None, "UTC"])
def test_both_tz_aware_and_naive_bars_are_handled(enricher, tz):
    """The batch stores datetimes in UTC; the fixtures above are naive.

    A step that only works for one of the two passes every test here and dies
    on the real frame -- which is exactly how the accumulation guard crashed
    the same rebuild, comparing datetime64[ns] against datetime64[ns, UTC].
    """
    facts = pd.DataFrame([
        _fact("AssetsCurrent", 2_000, filed="2024-05-01", end="2024-03-31"),
        _fact("LiabilitiesCurrent", 1_000, filed="2024-05-01", end="2024-03-31"),
    ])
    bars = _bars(["2024-06-01", "2024-06-02"])
    if tz:
        bars["datetime"] = bars["datetime"].dt.tz_localize(tz)

    out = enricher._enrich_impl(bars, sec_fundamentals=facts)
    assert len(out) == 2
    assert out["fund_current_ratio"].iloc[0] == pytest.approx(2.0)


def test_a_fact_is_not_in_the_bars_before_its_filing_was_accepted(enricher):
    """REGISTER #535. `filed` is a day: 46.21% of stored filings were accepted
    at or after 16:00 New York on it, and the midnight join handed them to the
    daily bar of that day and to its open bar. The acceptance second of the
    same accession in `sec_filings` (true UTC, #530) decides now."""
    facts = pd.DataFrame([
        {**_fact("StockholdersEquity", 1_000, filed="2024-08-05", end="2024-06-30"), "accession": "0001-24-1"},
        {**_fact("CommonStockSharesOutstanding", 100, filed="2024-08-05", end="2024-06-30"), "accession": "0001-24-1"},
    ])
    filings = pd.DataFrame({"accessionNumber": ["0001-24-1"],
                            "acceptanceDateTime": ["2024-08-05T20:15:00.000Z"]})   # 16:15 New York
    bars = _bars(["2024-08-05 00:00", "2024-08-05 13:30", "2024-08-05 19:45",
                  "2024-08-05 20:30", "2024-08-06 00:00"])
    out = enricher._enrich_impl(bars, sec_fundamentals=facts, sec_filings=filings)
    assert out["fund_data_available"].tolist() == [0, 0, 0, 1, 1]


def test_a_fact_whose_filing_has_no_acceptance_time_is_known_the_next_day(enricher):
    facts = pd.DataFrame([
        _fact("StockholdersEquity", 1_000, filed="2024-08-05", end="2024-06-30"),
        _fact("CommonStockSharesOutstanding", 100, filed="2024-08-05", end="2024-06-30"),
    ])
    out = enricher._enrich_impl(_bars(["2024-08-05 13:30", "2024-08-06 00:00"]), sec_fundamentals=facts)
    assert out["fund_data_available"].tolist() == [0, 1]
