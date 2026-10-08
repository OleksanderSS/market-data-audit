"""Are long shots overpriced on Polymarket (real money)? (#592, attempt 1 of 2)

Pre-registered in `docs/preregistration/2026-10-07_polymarket_longshot_592.md`, committed before
this instrument and before any fetch (8ca76e13). The same test as #587 (Manifold, play money, Р90).
Raw responses are stored BEFORE any computation:

    --fetch     keyset pages of closed markets (volume >= $10 000, start >= 2024-01-01, 100 a page,
                up to 100 pages) and, for every market that passes the filters, the Yes token's price
                history over [T - 3 days, T], T = min(end, closed) - 7 days
                -> data/diagnostic_fetches/polymarket_592/<stamp>/
    (default)   analysis from the latest saved fetch, no network

Long-shot bin p in [0.02, 0.15): B = mean p - share YES; the RULE z is event-clustered,
SE_cl = sqrt(sum over events (sum(p - y) - n B)^2) / N; z_cl >= 1.645 (within 0.10 -> not passed).
Guard first, from prices only: MDE = 2.80 sqrt(mean p(1-p) / N) > 0.030 or < 100 events -> stop.
K1 outcomes ~ Bernoulli(p), 200 draws: z_cl >= 1.645 in <= 10%. K2 long shots ~ Bernoulli(p - 0.05):
found in >= 80%. K3 bin [0.45, 0.55]: share YES in [0.40, 0.60]. K4 no price point after T (must be 0).

    python -u scripts/diagnostics/polymarket_longshot_592.py --fetch
    python -u scripts/diagnostics/polymarket_longshot_592.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "data" / "diagnostic_fetches" / "polymarket_592"
GAMMA, CLOB = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
DAY = 86_400
PAGES, PAGE, PAUSE = 100, 100, 0.15
LONG, FAV, MID = (0.02, 0.15), (0.85, 0.98), (0.45, 0.55)
MDE_MAX, MIN_EVENTS, Z_RULE, Z_EDGE, SEED = 0.030, 100, 1.645, 0.10, 592


def get(url: str, params: dict) -> bytes:
    import requests
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=60, headers={"User-Agent": "research"})
            r.raise_for_status()
            return r.content
        except Exception:  # noqa: BLE001 -- retried, then raised
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def ts(s: str | None) -> int | None:
    if not s:
        return None
    s = s.replace(" ", "T").replace("Z", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    return int(datetime.fromisoformat(s).timestamp())


def resolution(m: dict) -> float | None:
    try:
        prices = json.loads(m.get("outcomePrices") or "null")
    except ValueError:
        return None
    return {("1", "0"): 1.0, ("0", "1"): 0.0}.get(tuple(prices or ()))


def eligible(m: dict) -> int | None:
    """T, or None if the pre-registered filters drop the market."""
    if m.get("outcomes") != '["Yes", "No"]' or resolution(m) is None:
        return None
    if m.get("umaResolutionStatus") != "resolved" or m.get("negRiskOther"):
        return None
    ends = [x for x in (ts(m.get("endDate")), ts(m.get("closedTime"))) if x]
    start = ts(m.get("startDate"))
    if not ends or start is None:
        return None
    T = min(ends) - 7 * DAY
    return T if T >= start + DAY else None


def yes_token(m: dict) -> str | None:
    toks = json.loads(m.get("clobTokenIds") or "[]")
    return toks[0] if toks else None


def fetch() -> None:
    out = HOME / time.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True)
    markets, cursor = [], None
    for k in range(PAGES):
        params = {"limit": PAGE, "closed": "true", "volume_num_min": 10000, "start_date_min": "2024-01-01"}
        if cursor:
            params["after_cursor"] = cursor
        raw = get(f"{GAMMA}/markets/keyset", params)
        (out / f"keyset_{k:03d}.json").write_bytes(raw)
        page = json.loads(raw)
        markets += page["markets"]
        cursor = page.get("next_cursor")
        if k % 10 == 0:
            print(f"  page {k}: {len(page['markets'])}, total {len(markets)}", flush=True)
        time.sleep(PAUSE)
        if not cursor or len(page["markets"]) < PAGE:
            break
    hist = out / "history"
    hist.mkdir()
    todo = [(m["id"], yes_token(m), eligible(m)) for m in markets if eligible(m) and yes_token(m)]
    print(f"markets {len(markets)}, eligible before the price {len(todo)}", flush=True)
    for n, (mid, tok, T) in enumerate(todo, 1):
        raw = get(f"{CLOB}/prices-history", {"market": tok, "startTs": T - 3 * DAY, "endTs": T, "fidelity": 60})
        (hist / f"{mid}.json").write_bytes(raw)
        time.sleep(PAUSE)
        if n % 250 == 0:
            print(f"  history {n}/{len(todo)}", flush=True)
    print(f"saved -> {out.relative_to(ROOT)}")


def z_cluster(p: np.ndarray, y: np.ndarray, ev: np.ndarray) -> tuple[float, float]:
    B = p.mean() - y.mean()
    g = pd.DataFrame({"r": p - y, "ev": ev}).groupby("ev")["r"].agg(["sum", "count"])
    se = np.sqrt(((g["sum"] - g["count"] * B) ** 2).sum()) / len(p)
    return B, (B / se if se > 0 else 0.0)


def price_at(points: list[dict], T: int) -> tuple[float | None, int]:
    """Last point with t <= T; the second value counts points after T (K4: must be 0 used)."""
    before = [q for q in points if int(q["t"]) <= T]
    after = len(points) - len(before)
    if not before:
        return None, after
    return float(max(before, key=lambda q: int(q["t"]))["p"]), after


def analyse() -> int:
    src = sorted(d for d in HOME.iterdir() if d.is_dir() and (d / "history").exists())[-1]
    markets = [m for f in sorted(src.glob("keyset_*.json")) for m in json.loads(f.read_bytes())["markets"]]
    rows, no_price, after_T, near_T = [], 0, 0, 0
    for m in markets:
        T = eligible(m)
        f = src / "history" / f"{m['id']}.json"
        if not T or not f.exists():
            continue
        points = json.loads(f.read_bytes()).get("history", [])
        p, after = price_at(points, T)
        after_T += after
        if p is None:
            no_price += 1
            continue
        last = max(int(q["t"]) for q in points if int(q["t"]) <= T)
        near_T += T - last <= 3600
        ev = (m.get("events") or [{}])[0].get("id") or f"m{m['id']}"
        rows.append({"id": m["id"], "event": ev, "p": p, "yes": resolution(m), "question": m.get("question", "")[:80]})
    df = pd.DataFrame(rows)
    print(f"source {src.relative_to(ROOT)}; markets {len(markets)}, with a price at T {len(df)}, no price {no_price}")
    print(f"K4: points after T returned by the API {after_T} (none used by construction); "
          f"last point within 1 h of T: {near_T}/{len(df)}")
    lo = df[(df["p"] >= LONG[0]) & (df["p"] < LONG[1])]
    p, y, ev = lo["p"].to_numpy(), lo["yes"].to_numpy(), lo["event"].to_numpy()
    mde = 2.80 * np.sqrt((p * (1 - p)).mean() / len(p))
    n_ev = lo["event"].nunique()
    print(f"long-shot bin {LONG}: N {len(p)}, events {n_ev}, MDE {mde:.4f}")
    if mde > MDE_MAX or n_ev < MIN_EVENTS:
        print(f"GUARD: MDE {mde:.4f} (max {MDE_MAX}), events {n_ev} (min {MIN_EVENTS}) -> НЕДОСТАТНЯ СИЛА; B not computed")
        return 2
    rng = np.random.default_rng(SEED)
    k1 = np.mean([z_cluster(p, (rng.random(len(p)) < p).astype(float), ev)[1] >= Z_RULE for _ in range(200)])
    k2 = np.mean([z_cluster(p, (rng.random(len(p)) < np.clip(p - 0.05, 0, 1)).astype(float), ev)[1] >= Z_RULE
                  for _ in range(200)])
    mid = df[(df["p"] >= MID[0]) & (df["p"] <= MID[1])]
    k3 = mid["yes"].mean()
    print(f"K1 null: z_cl >= {Z_RULE} in {k1:.0%} -> {'PASS' if k1 <= 0.10 else 'FAIL'}")
    print(f"K2 planted -0.05: found in {k2:.0%} -> {'PASS' if k2 >= 0.80 else 'FAIL'}")
    print(f"K3 bin {MID}: N {len(mid)}, share YES {k3:.3f} -> {'PASS' if 0.40 <= k3 <= 0.60 else 'FAIL'}")

    B, z = z_cluster(p, y, ev)
    z_bin = B / (np.sqrt((p * (1 - p)).sum()) / len(p))
    print(f"\nLONG SHOTS: mean p {p.mean():.4f}, share YES {y.mean():.4f}, B {B:+.4f}, z_cl {z:+.2f} "
          f"({n_ev} events; binomial z {z_bin:+.2f})")
    fav = df[(df["p"] > FAV[0]) & (df["p"] <= FAV[1])]
    print(f"MIRROR favourites {FAV}: N {len(fav)}, mean p {fav['p'].mean():.4f}, share YES {fav['yes'].mean():.4f}, "
          f"YES - p {fav['yes'].mean() - fav['p'].mean():+.4f}")
    print("calibration (bins of 0.1):")
    df["bin"] = np.minimum((df["p"] * 10).astype(int), 9)
    for bn, gg in df.groupby("bin"):
        print(f"  {bn / 10:.1f}-{(bn + 1) / 10:.1f}: N {len(gg):5d}  events {gg['event'].nunique():4d}  "
              f"mean p {gg['p'].mean():.3f}  share YES {gg['yes'].mean():.3f}")
    if abs(z - Z_RULE) <= Z_EDGE:
        verdict = "НЕ ПРОЙДЕНО (впритул)"
    else:
        verdict = "ТАК: аутсайдери переоцінені" if z >= Z_RULE else "НІ: переоцінки аутсайдерів не видно"
    print(f"VERDICT: {verdict} (B {B:+.4f}, z_cl {z:+.2f}, MDE {mde:.4f})")
    df.to_csv(ROOT / "diagnostic_reports" / "polymarket_longshot_592.csv", index=False)
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    if ap.parse_args().fetch:
        fetch()
        return 0
    return analyse()


if __name__ == "__main__":
    sys.exit(main())
