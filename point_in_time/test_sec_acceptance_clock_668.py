"""SEC serves `acceptanceDateTime` on three clocks under one `Z` (#668); what we store must be true UTC.

Known answers, read from EDGAR filing pages on 10.10 ("Accepted", New York time):
Apple 8-K 0000320193-26-000018 -- 30.07.2026 16:30:28 (true 20:30:28Z), served that day as 00:30:28Z of the 31st;
JPM 424B2 0001628280-26-xxxxx  -- 14.09.2026 16:44:21, stored by us as 16:44:21Z (New York wall time, 4 h EARLY).
The synthetic response below repeats that shape: 60 filings between 07:00 and 21:00 New York, written under
each clock, must come out of `run` as the same true instants.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pandas as pd
import pytest

from src.data.collectors import sec_clock
from src.data.collectors.sec_filings_collector import SECFilingsCollector

NY = "America/New_York"


def _truth() -> pd.DatetimeIndex:
    days = pd.bdate_range("2026-08-03", periods=60)
    hours = [6 + (i * 5) % 16 for i in range(60)]   # 06..21 New York, as EDGAR's day
    local = [pd.Timestamp(d) + pd.Timedelta(hours=h, minutes=13, seconds=i)
             for i, (d, h) in enumerate(zip(days, hours))]
    return pd.DatetimeIndex(local).tz_localize(NY).tz_convert("UTC")


def _served(truth: pd.DatetimeIndex, clock: str) -> list[str]:
    if clock == "utc":
        t = truth
    elif clock == "ny_wall":
        t = truth.tz_convert(NY).tz_localize(None).tz_localize("UTC")
    else:  # utc_plus_ny: the true instant plus New York's offset
        off = [-x.utcoffset() for x in truth.tz_convert(NY)]
        t = pd.DatetimeIndex([a + b for a, b in zip(truth, off)])
    return [x.strftime(sec_clock.FMT) for x in t]


def _response(clock: str) -> dict:
    tr = _truth()
    return {"name": "APPLE INC.", "filings": {"recent": {
        "accessionNumber": [f"0000320193-26-{i:06d}" for i in range(len(tr))],
        "filingDate": [x.tz_convert(NY).strftime("%Y-%m-%d") for x in tr],
        "acceptanceDateTime": _served(tr, clock),
        "form": ["8-K"] * len(tr),
        "items": [["2.02"]] * len(tr)}, "files": []}}


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._d


class _Client:
    def __init__(self, data):
        self._d = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        return _Resp(self._d)


class _Factory:
    def __init__(self, data):
        self._d = data

    async def get_http_client(self):
        return _Client(self._d)


class _DB:
    def __init__(self):
        self.stored = None

    def filter_new_records(self, table, df):
        return df

    def upsert(self, table, df, unique_on=None):
        self.stored = df.copy()


def _collector(data) -> tuple[SECFilingsCollector, _DB]:
    c = SECFilingsCollector.__new__(SECFilingsCollector)
    c.configs = {"table_name": "sec_filings", "params": {"period": "120d"}}
    c.submissions_url_template = "https://data.sec.gov/submissions/CIK{cik}.json"
    c.hash_keys = ["accessionNumber", "cik"]
    c.http_client_factory = _Factory(data)
    c.db_manager = _DB()
    c._check_sec_cache = lambda *a, **k: None
    c._update_sec_cache = lambda *a, **k: None
    c._get_valid_ciks = lambda tickers: {"AAPL": "0000320193"}
    return c, c.db_manager


@pytest.mark.parametrize("clock", ["utc", "ny_wall", "utc_plus_ny"])
def test_every_served_clock_is_stored_as_true_utc(clock):
    c, db = _collector(_response(clock))
    asyncio.run(c.run(["AAPL"], run_date=datetime(2026, 10, 30)))
    assert db.stored is not None and len(db.stored) == 60
    want = [x.strftime(sec_clock.FMT) for x in _truth()]
    got = db.stored.sort_values("accessionNumber")["acceptanceDateTime"].tolist()
    assert got == want, f"{clock}: first stored {got[:2]} vs true {want[:2]}"
    assert sec_clock.detect(_served(_truth(), clock), _response(clock)["filings"]["recent"]["filingDate"]) == clock


def test_the_apple_filing_of_30_07_served_late_reads_true():
    """The 10.10 control: 00:30:28Z of the 31st under `utc_plus_ny` is 20:30:28Z of the 30th."""
    assert sec_clock.to_true_utc(["2026-07-31T00:30:28.000Z"], "utc_plus_ny") == ["2026-07-30T20:30:28.000Z"]
    assert sec_clock.to_true_utc(["2026-01-30T02:30:33.000Z"], "utc_plus_ny") == ["2026-01-29T21:30:33.000Z"]
    assert sec_clock.to_true_utc(["2026-09-14T16:44:21.000Z"], "ny_wall") == ["2026-09-14T20:44:21.000Z"]
    # a date without an hour is shifted by SEC too: NKE 22.04.1999, EDGAR "00:00:00", stored 04:00Z, served 08:00Z
    assert sec_clock.to_true_utc(["1999-04-22T08:00:00.000Z"], "utc_plus_ny") == ["1999-04-22T04:00:00.000Z"]


def test_an_undecidable_response_stores_no_hour_not_a_guess():
    """Too few filings to tell and no run clock: the hour is unknown (None), a bare date too."""
    rows = [{"ticker": "X", "acceptanceDateTime": "2026-09-14T16:44:21.000Z", "_acceptance_clock": None},
            {"ticker": "X", "acceptanceDateTime": "2026-09-14T00:00:00.000Z", "_acceptance_clock": None}]
    out = SECFilingsCollector._to_true_clock(rows)
    assert out[0]["acceptanceDateTime"] is None
    assert out[1]["acceptanceDateTime"] is None
    assert all("_acceptance_clock" not in r for r in out)
