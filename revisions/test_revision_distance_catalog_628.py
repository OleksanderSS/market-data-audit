"""Known answers for the revision-distance catalog (#628) -- the instrument's null control, before the real run."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "diagnostics"))
import revision_distance_catalog_628 as C  # noqa: E402

END = C.OPEN_END


def _months(n: int, start: str = "1997-01-01") -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=n, freq="MS")]


def _vintaged(latest: np.ndarray, first: np.ndarray) -> pd.DataFrame:
    """Each month published once (first print) one month later, revised to `latest` two months later."""
    dates = _months(len(latest))
    rows = [("1996-12-15", END, "1996-12-01", float(latest[0]))]  # the earliest vintage: one older observation
    for i, d in enumerate(dates):
        pub = (pd.Timestamp(d) + pd.DateOffset(months=1)).strftime("%Y-%m-%d")
        rev = (pd.Timestamp(d) + pd.DateOffset(months=2)).strftime("%Y-%m-%d")
        if first[i] == latest[i]:
            rows.append((pub, END, d, latest[i]))
        else:
            rows.append((pub, (pd.Timestamp(rev) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), d, first[i]))
            rows.append((rev, END, d, latest[i]))
    return pd.DataFrame(rows, columns=["realtime_start", "realtime_end", "date", "value"])


def test_an_unrevised_series_agrees_exactly():
    rng = np.random.default_rng(0)
    lvl = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 120)))
    m = C.metrics(C.pairs(_vintaged(lvl, lvl), diff=False))
    assert m["n"] == 120 and abs(m["corr"] - 1) < 1e-12 and m["revision_share"] < 1e-12


def test_the_first_print_change_uses_the_previous_month_as_it_stood_then():
    """The change a trader saw = new first print minus the previous month AS PUBLISHED AT THAT TIME."""
    latest = np.array([100.0, 110.0, 120.0])
    first = np.array([100.0, 105.0, 125.0])
    pr = C.pairs(_vintaged(latest, first), diff=True)
    # Feb first print 105 published 03-01; Jan (100) unrevised -> 5. Mar first 125 published 04-01, when Feb had
    # already been revised to 110 (revision on 04-01) -> 15. Latest changes: 10 and 10.
    assert pr["first"].tolist() == [0.0, 5.0, 15.0] and pr["latest"].tolist() == [0.0, 10.0, 10.0]


def test_known_noise_gives_the_known_correlation():
    """Revision = independent noise with variance r x signal: corr -> 1 / sqrt(1 + r)."""
    rng = np.random.default_rng(1)
    n = 1500
    lat = 1000 + np.cumsum(rng.normal(0, 1, n))
    fst = lat + rng.normal(0, math.sqrt(0.5), n)       # first print = final level + independent error
    # the previous month is already revised when month d is first printed, so the first CHANGE is
    # true change + error_d: var ratio 0.5 -> corr 1/sqrt(1.5) = 0.816
    m = C.metrics(C.pairs(_vintaged(lat, fst), diff=True))
    assert abs(m["corr"] - 1 / math.sqrt(1.5)) < 0.04
    # the mirror: next month's change knows nothing; 335 eligible months -> se ~0.055, bound 3.5 se
    # (8 seeds on 10.10: -0.113 ... +0.020, mean -0.03)
    assert abs(m["mirror"]) < 0.2


def test_observations_already_in_the_earliest_vintage_are_not_first_prints():
    lvl = np.array([100.0, 101.0, 102.0])
    rows = _vintaged(lvl, lvl)
    rows.loc[rows["date"] == "1997-01-01", "realtime_start"] = "1996-12-15"   # now part of the earliest vintage
    assert "1997-01-01" not in C.pairs(rows, diff=True)["date"].tolist()


def test_the_verdict_needs_both_controls():
    good = {"corr": 1.0, "mirror": 0.0, "sign_agree": 1.0}
    res = {c: dict(good) for c in C.CONTROLS} | {"PAYEMS": {"corr": 0.8, "mirror": 0.1, "sign_agree": 0.9}}
    v = C.verdict(res)
    assert v["K1_controls_unrevised"] and v["K2_mirror_below_own"] and v["bands_hit"] == "1/1"
    res["GS10"]["corr"] = 0.99
    assert not C.verdict(res)["K1_controls_unrevised"]
    res["GS10"]["corr"] = 1.0
    res["PAYEMS"]["mirror"] = 0.9
    assert not C.verdict(res)["K2_mirror_below_own"]


def test_a_stale_open_end_does_not_hide_the_newer_vintage():
    """fred_data does not close a vintage's interval when a newer one arrives (10.10: NFCI 1 498 dates, RSAFS 140
    with several open rows of different values). The value at vintage v is the row that STARTED last before v."""
    rows = pd.DataFrame([("1996-12-15", END, "1996-12-01", 100.0),
                         ("1997-02-01", END, "1997-01-01", 101.0),     # first print, never closed
                         ("1997-03-01", END, "1997-01-01", 103.0),     # the revision, also open
                         ("1997-03-01", END, "1997-02-01", 104.0)],
                        columns=["realtime_start", "realtime_end", "date", "value"])
    pr = C.pairs(rows, diff=True)
    assert pr["first"].tolist() == [1.0, 1.0] and pr["latest"].tolist() == [3.0, 1.0]
