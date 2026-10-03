"""SEC filings are events with dates, not prose with a mood.

They were classified as a news source and fed into the news frame, where the
alias list said `filing_date` and the table said `filingDate`, so 24,365
dated, ticker-tagged filings were discarded every run over one capital letter.

Renaming the column would have been the wrong fix. A filing carries `form` and
`primaryDocDescription` -- codes like "10-Q" -- so the sentiment model would
return a number for the string "10-Q" and that number would be noise wearing
the label of sentiment. What a filing is: a company told the regulator
something on a date.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.enrichers.corporate_filings_enricher import (
    CorporateFilingsEnricher,
)


def _bars(ticker, dates):
    return pd.DataFrame({
        "datetime": pd.to_datetime(dates),
        "ticker": [ticker] * len(dates),
        "close": np.arange(len(dates), dtype=float),
    })


def _filings(rows):
    return pd.DataFrame(rows, columns=["ticker", "filingDate", "form"])


@pytest.fixture
def enricher():
    return CorporateFilingsEnricher({"window_days": 30})


def test_a_bar_before_any_filing_reports_absence_not_zero(enricher):
    """The mistake that put a neutral 0.0 in front of every gate in this system."""
    bars = _bars("AAPL", ["2026-01-10"])
    out = enricher._enrich_impl(bars, sec_filings=_filings([("AAPL", "2026-03-01", "8-K")]))

    assert out["filing_data_available"].iloc[0] == 0
    assert pd.isna(out["filing_days_since_last"].iloc[0])
    assert pd.isna(out["filing_count_30d"].iloc[0])


def test_recency_is_counted_from_the_filing_date(enricher):
    bars = _bars("AAPL", ["2026-03-11"])
    out = enricher._enrich_impl(bars, sec_filings=_filings([("AAPL", "2026-03-01", "8-K")]))

    # a filingDate with no acceptance hour is known from the next day (#530)
    assert out["filing_days_since_last"].iloc[0] == 9
    assert out["filing_data_available"].iloc[0] == 1


def test_the_window_counts_only_what_fell_inside_it(enricher):
    filings = _filings([
        ("AAPL", "2026-01-05", "8-K"),   # 65 days before the bar
        ("AAPL", "2026-03-01", "8-K"),
        ("AAPL", "2026-03-05", "10-Q"),
    ])
    out = enricher._enrich_impl(_bars("AAPL", ["2026-03-11"]), sec_filings=filings)

    assert out["filing_count_30d"].iloc[0] == 2
    assert out["filing_material_30d"].iloc[0] == 1     # the 8-K only
    assert out["filing_periodic_30d"].iloc[0] == 1     # the 10-Q only


def test_a_filing_belongs_to_one_company(enricher):
    filings = _filings([("NVDA", "2026-03-01", "8-K"), ("NVDA", "2026-03-02", "8-K")])
    out = enricher._enrich_impl(_bars("AAPL", ["2026-03-11"]), sec_filings=filings)

    assert out["filing_data_available"].iloc[0] == 0


def test_a_bar_never_sees_a_filing_from_its_own_future(enricher):
    filings = _filings([("AAPL", "2026-03-20", "8-K")])
    out = enricher._enrich_impl(_bars("AAPL", ["2026-03-10", "2026-03-25"]), sec_filings=filings)

    assert out["filing_data_available"].tolist() == [0, 1]
    assert out["filing_days_since_last"].iloc[1] == 4   # known 03-21 (#530)


def test_a_filing_accepted_after_the_close_is_not_in_that_days_bars(enricher):
    """REGISTER #530. `filingDate` floored to 00:00 handed a filing to every bar
    of its day: 42.86% of stored filings were accepted at or after 16:00 New
    York on their filingDate. `acceptanceDateTime` is true UTC (#530 measured
    it against EDGAR's 17:30 rule), so a bar sees a filing from that second on.
    """
    filings = pd.DataFrame({
        "ticker": ["AAPL"], "form": ["8-K"],
        "filingDate": ["2026-07-15"],
        "acceptanceDateTime": ["2026-07-15T20:31:05.000Z"],   # 16:31 New York
    })
    bars = _bars("AAPL", ["2026-07-15 00:00", "2026-07-15 13:30", "2026-07-15 19:45",
                          "2026-07-15 20:45", "2026-07-16 00:00"])
    out = enricher._enrich_impl(bars, sec_filings=filings)
    seen = dict(zip(out["datetime"].astype(str), out["filing_data_available"]))
    assert seen["2026-07-15 00:00:00"] == 0, "the daily bar of the filing day read it"
    assert seen["2026-07-15 13:30:00"] == 0, "the open bar read a filing accepted at 16:31"
    assert seen["2026-07-15 19:45:00"] == 0, "the last 15m bar before acceptance read it"
    assert seen["2026-07-15 20:45:00"] == 1, "a bar after the acceptance second must see it"
    assert seen["2026-07-16 00:00:00"] == 1, "the next day's bar must see it"


def test_a_filing_without_an_hour_is_known_the_next_day(enricher):
    """No acceptance time, or a bare date stored as 00:00:00 New York (11,816
    old rows), is a day with no hour: known from filingDate + 1, as #523."""
    filings = pd.DataFrame({
        "ticker": ["AAPL", "NVDA"], "form": ["8-K", "8-K"],
        "filingDate": ["2026-07-15", "2026-07-15"],
        "acceptanceDateTime": ["2026-07-15T04:00:00.000Z", None],  # midnight NY, missing
    })
    bars = pd.concat([_bars("AAPL", ["2026-07-15 13:30", "2026-07-16 00:00"]),
                      _bars("NVDA", ["2026-07-15 13:30", "2026-07-16 00:00"])], ignore_index=True)
    out = enricher._enrich_impl(bars, sec_filings=filings)
    assert out["filing_data_available"].tolist() == [0, 1, 0, 1]


def test_a_new_york_bar_is_compared_in_utc(enricher):
    """A tz-aware bar must be converted, not stripped: 16:45 New York is 20:45 UTC,
    after a 16:31 acceptance; stripping the zone would read it as 16:45 UTC."""
    filings = pd.DataFrame({"ticker": ["AAPL"], "form": ["8-K"], "filingDate": ["2026-07-15"],
                            "acceptanceDateTime": ["2026-07-15T20:31:05.000Z"]})
    bars = pd.DataFrame({"datetime": pd.DatetimeIndex(["2026-07-15 16:15", "2026-07-15 16:45"],
                                                      tz="America/New_York"),
                         "ticker": ["AAPL", "AAPL"]})
    out = enricher._enrich_impl(bars, sec_filings=filings)
    assert out["filing_data_available"].tolist() == [0, 1]


def test_report_date_is_refused_as_the_event_time():
    """`reportDate` is the period covered; using it backdates every disclosure."""
    frame = pd.DataFrame({"ticker": ["AAPL"], "reportDate": ["2026-03-31"], "form": ["10-Q"]})
    assert CorporateFilingsEnricher._date_column(frame) is None

    frame["filingDate"] = ["2026-05-02"]
    assert CorporateFilingsEnricher._date_column(frame) == "filingDate"


def test_bars_come_back_unchanged_when_there_are_no_filings(enricher):
    bars = _bars("AAPL", ["2026-03-11"])
    out = enricher._enrich_impl(bars, sec_filings=pd.DataFrame())
    assert list(out.columns) == list(bars.columns)


def test_bars_come_back_unchanged_without_a_ticker_column(enricher):
    bars = _bars("AAPL", ["2026-03-11"]).drop(columns=["ticker"])
    out = enricher._enrich_impl(bars, sec_filings=_filings([("AAPL", "2026-03-01", "8-K")]))
    assert "filing_days_since_last" not in out.columns


def test_rows_keep_their_own_values_when_tickers_interleave(enricher):
    """The as-of merge sorts by time; results must land back on the right row."""
    bars = pd.DataFrame({
        "datetime": pd.to_datetime(
            ["2026-03-11", "2026-03-11", "2026-03-12", "2026-03-12"]
        ),
        "ticker": ["AAPL", "NVDA", "NVDA", "AAPL"],
    })
    filings = _filings([("AAPL", "2026-03-01", "8-K"), ("NVDA", "2026-03-09", "10-Q")])
    out = enricher._enrich_impl(bars, sec_filings=filings)

    by_row = dict(zip(zip(out["ticker"], out["datetime"].dt.day),
                      out["filing_days_since_last"]))
    # each filing known the day after its filingDate (#530)
    assert by_row[("AAPL", 11)] == 9
    assert by_row[("NVDA", 11)] == 1
    assert by_row[("NVDA", 12)] == 2
    assert by_row[("AAPL", 12)] == 10


def test_the_feature_names_it_declares_are_the_ones_it_adds(enricher):
    bars = _bars("AAPL", ["2026-03-11"])
    out = enricher._enrich_impl(bars, sec_filings=_filings([("AAPL", "2026-03-01", "8-K")]))
    for name in enricher.get_feature_names():
        assert name in out.columns, name


def test_the_collection_window_reaches_the_daily_frame():
    """A feature that is enabled but empty is worth no more than one switched off.

    The collector was set to `period: 60d`. That covered the 15m frame
    completely -- Yahoo serves only 58 days of intraday bars -- and the 1d and
    1h frames by roughly 8%, which is exactly backwards: a 10-Q moves a daily
    bar and means nothing on a 15-minute one.

    The window costs nothing to widen. `_fetch_filings_for_ticker` makes one
    request per ticker for `filings.recent`, which the SEC fills with up to
    1000 filings, and then discards the ones outside the window in Python. So
    60d was throwing away rows already downloaded.

    This pins the window against the daily frame so the two cannot drift apart
    again without a test saying so.
    """
    import io
    from datetime import datetime

    import yaml

    from src.data.collectors.sec_filings_collector import SECFilingsCollector

    config = yaml.safe_load(io.open("src/config/collectors.yaml", encoding="utf-8"))
    collectors = config.get("collectors", config)
    period = collectors["sec_filings"]["params"]["period"]

    run_date = datetime(2026, 8, 22)
    start = SECFilingsCollector._calculate_start_date(None, period, run_date)
    days = (run_date - start).days

    assert days >= 365, (
        f"SEC filings are collected for {days} days ({period!r}). The daily "
        "frame spans about two years, so filing features would be null for "
        f"{100 * (1 - days / 730):.0f}% of it. Widening the window costs no "
        "extra requests -- the response is already fetched and then filtered."
    )
