"""How far is the feature a backtest builds from REVISED FRED data from the feature that was KNOWABLE? (#628)

Pre-registration: docs/preregistration/2026-10-10_revision_distance_catalog_628.md (rules, bands, controls).

WHY. On 10.10 the Г4 signal (3-month growth of 25 industry lines of the Fed's G.17) built on today's FRED
vintage agreed with the same signal built on first prints at a median cross-sectional rank correlation of
0.53 (control: the newest archived G.17 release against FRED today, 0.961). A backtest on revised data tests
a different signal from the one that could have been traded. This catalog asks the same of the headline
series a backtest takes from FRED, using the vintages the nightly collector already stores (`fred_data`,
realtime_start / realtime_end intervals) -- no traffic.

FOR EACH OBSERVATION d (pure parts below are unit-tested):
  first   the value of d in the EARLIEST vintage that contains d, and the value of the previous observation p
          IN THAT SAME vintage -> the change a trader saw on the day d was first published;
  latest  the values of d and p in today's vintage (realtime_end 9999-12-31).
  feature log(x_d / x_p) for quantities, x_d - x_p for rates and indices (`DIFF`).
Eligible d: first published after the series' earliest stored vintage (so the first vintage really is the
first print), d >= 1997-01-01, first published on or before 2024-12-31.
Per series: n, corr(first, latest), sign agreement (pairs where neither is 0), revision share
sd(latest - first) / sd(latest), mirror corr(first_t, latest_{t+1}).

    python -u scripts/diagnostics/revision_distance_catalog_628.py      # read-only DB, one line + JSON
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "trading_data.duckdb"
OUT = ROOT / "diagnostic_reports" / "revision_distance_catalog_628.json"
RUNS = ROOT / "data" / "revision_628" / "runs.jsonl"

CONTROLS = ("FEDFUNDS", "GS2", "GS10")            # monthly averages of market rates: never revised
DIFF = {"FEDFUNDS", "GS2", "GS10", "UNRATE", "UMCSENT", "NFCI"}
# pre-registered bands for corr(first, latest); written before the first run on real data
BANDS = {
    "FEDFUNDS": (0.999, 1.0), "GS2": (0.999, 1.0), "GS10": (0.999, 1.0),
    "UNRATE": (0.85, 0.97), "UMCSENT": (0.95, 1.0), "NFCI": (0.50, 0.85),
    "INDPRO": (0.70, 0.88), "CPIAUCSL": (0.90, 0.98), "PPIACO": (0.90, 0.98), "DSPIC96": (0.40, 0.70),
    "PAYEMS": (0.65, 0.85), "MANEMP": (0.65, 0.85), "HOUST": (0.85, 0.95), "GDP": (0.65, 0.85),
    "RSAFS": (0.60, 0.85), "PCEPILFE": (0.55, 0.80), "PCEPI": (0.80, 0.93), "DGORDER": (0.85, 0.95),
    "PERMIT": (0.90, 0.98), "ICSA": (0.93, 0.99), "CCSA": (0.85, 0.97),
}
FIRST_OBS = "1997-01-01"
LAST_PUBLISHED = "2024-12-31"
OPEN_END = "9999-12-31"


# ---------------------------------------------------------------- pure parts (unit-tested)
def value_at(rows: pd.DataFrame, date: str, vintage: str) -> float:
    """Value of observation `date` in the vintage valid on `vintage`: the row that STARTED last on or before it.

    Not `realtime_start <= v <= realtime_end`: `fred_data` does not close an interval when a newer vintage
    arrives (10.10, first run of this file died on it: NFCI 1 498 dates, RSAFS 140, GDP 22 with several open
    rows of different values), so `realtime_end` there means "open when collected", not "superseded at"."""
    r = rows[(rows["date"] == date) & (rows["realtime_start"] <= vintage)]
    return float(r.loc[r["realtime_start"].idxmax(), "value"]) if len(r) else float("nan")


def feature(x_d: float, x_p: float, diff: bool) -> float:
    if not (math.isfinite(x_d) and math.isfinite(x_p)):
        return float("nan")
    if diff:
        return x_d - x_p
    return math.log(x_d / x_p) if x_d > 0 and x_p > 0 else float("nan")


def pairs(rows: pd.DataFrame, diff: bool, first_obs: str = FIRST_OBS,
          last_published: str = LAST_PUBLISHED) -> pd.DataFrame:
    """(date, first, latest) for every eligible observation of one series."""
    rows = rows.dropna(subset=["value"])
    earliest_vintage = rows["realtime_start"].min()
    first_pub = rows.groupby("date")["realtime_start"].min()
    latest = rows.sort_values("realtime_start").groupby("date")["value"].last()   # newest vintage per date
    dates = sorted(latest.index)
    prev = dict(zip(dates[1:], dates[:-1]))
    out = []
    for d in dates:
        v = first_pub.get(d)
        if d not in prev or v is None or v <= earliest_vintage or d < first_obs or v > last_published:
            continue
        p = prev[d]
        f = feature(value_at(rows, d, v), value_at(rows, p, v), diff)
        l = feature(float(latest[d]), float(latest[p]), diff)
        out.append((d, f, l))
    return pd.DataFrame(out, columns=["date", "first", "latest"]).dropna()


def metrics(pr: pd.DataFrame) -> dict:
    f, l = pr["first"].to_numpy(), pr["latest"].to_numpy()
    if len(f) < 24:
        return {"n": int(len(f))}
    nz = (f != 0) & (l != 0)
    return {"n": int(len(f)),
            "corr": float(np.corrcoef(f, l)[0, 1]),
            "sign_agree": float(np.mean(np.sign(f[nz]) == np.sign(l[nz]))) if nz.any() else float("nan"),
            "revision_share": float(np.std(l - f) / np.std(l)) if np.std(l) > 0 else float("nan"),
            "mirror": float(np.corrcoef(f[:-1], l[1:])[0, 1])}


def verdict(res: dict[str, dict]) -> dict:
    k1 = all(res.get(c, {}).get("corr", 0) >= 0.999 for c in CONTROLS)
    rest = [s for s in res if s not in CONTROLS and "corr" in res[s]]
    k2 = (np.mean([res[s]["mirror"] < res[s]["corr"] for s in rest]) >= 0.9) if rest else False
    hits = [s for s in rest if s in BANDS and BANDS[s][0] <= res[s]["corr"] <= BANDS[s][1]]
    return {"K1_controls_unrevised": bool(k1), "K2_mirror_below_own": bool(k2),
            "bands_hit": f"{len(hits)}/{len(rest)}",
            "median_corr": float(np.median([res[s]["corr"] for s in rest])) if rest else float("nan"),
            "median_sign_agree": float(np.median([res[s]["sign_agree"] for s in rest])) if rest else float("nan")}


# ---------------------------------------------------------------- reading
def load(con, sid: str) -> pd.DataFrame:
    df = con.execute("SELECT realtime_start, realtime_end, date, value FROM fred_data WHERE series_id = ?",
                     [sid]).df()
    df["value"] = pd.to_numeric(df["value"].replace(".", np.nan), errors="coerce")
    df["realtime_end"] = df["realtime_end"].fillna(OPEN_END)
    return df


def main() -> int:
    import duckdb
    con = duckdb.connect(str(DB), read_only=True)
    try:
        res = {sid: metrics(pairs(load(con, sid), sid in DIFF)) for sid in BANDS}
    finally:
        con.close()
    v = verdict(res)
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    attempt = sum(1 for _ in RUNS.open(encoding="utf-8")) + 1 if RUNS.exists() else 1
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"attempt": attempt, "at": dt.datetime.now().isoformat(timespec="seconds"),
                            "verdict": v}, ensure_ascii=False) + "\n")
    OUT.write_text(json.dumps({"attempt": attempt, "series": res, "verdict": v}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    ok = v["K1_controls_unrevised"] and v["K2_mirror_below_own"]
    print(f"спроба {attempt}: K1 {v['K1_controls_unrevised']}, K2 {v['K2_mirror_below_own']}; "
          f"{'КАТАЛОГ' if ok else 'БЕЗ ВЕРДИКТУ (контроль)'}: медіана кореляції {v['median_corr']:.3f}, "
          f"збіг знака {v['median_sign_agree']:.3f}, смуги {v['bands_hit']}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # the report must say NOT MEASURED, never stay silent
        print(f"НЕ ВИМІРЯНО: {type(e).__name__}: {e}")
        sys.exit(2)
