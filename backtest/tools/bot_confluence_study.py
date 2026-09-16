"""bot_confluence_study.py — would a kill-zone, 08:00-09:30, VWAP or opening-range filter have made
the two LIVE bots' trades better, once the number of filters tried has been paid for?

A STUDY: it replays the bots and scores filters on their trade lists; it changes neither bot. Built
on `killzone_study.py` / `ny_open_scalp_study.py` (the M1 grid, the kill zones and opening range
from `engines/sessions/`, VWAP from `engines/vwap/`) and the lab's own replay seam
(`backtest.replay.build_strategy`) — nothing re-derived.

THE ASK (the user, 2026-09-15): "find some sort of confluence with kill zone or the 8-9:30 am that
can make my current trades more profitable or even reducing losing trades."

THE TRADES — each live bot replayed with ITS LIVE INSTANCE CONFIG: every `strategy_params` field in
`algos/markets/fx/instances/<key>/config.json` that exists on the strategy's config is applied, and
any that does not is printed. PU Prime `XAUUSD.p` cached bars (server pinned, no MT5 needed),
`puprime_ecn` costs (flat spread 0.12, $1/side/lot, measured swap), $10,000, warm-up 1,000 bars,
one position — the bots' own rules.
  sos_fade_demo     M15, plus its re-entry fill feed (`run_dual`) when the config asks for it
  extreme_leg_demo  M5
  Explore window 2020-01-01 -> 2025-08-31 only.

THE FEATURES — at each trade's entry time, New York clock, from M1 bars through the engines:
  PRE      entry 08:00-09:29 NY on a weekday (the user's "8-9:30")
  KZ       entry inside any of the three kill zones (read off SessionEngine)
  MORNING  entry 08:00-10:59 NY on a weekday
  NY       entry 08:00-16:59 NY on a weekday
  VWAP     the entry price is on the trade's side of VWAP (as of the last M1 bar before entry);
           unknown when VWAP cannot be computed, and then no VWAP filter touches the trade
  IN_OR    a weekday entry 09:35-16:59 NY whose price sits inside that day's opening range

THE FILTERS — 11 per bot, 22 in all, each a set of trades it REMOVES:
  skip-inside and keep-only-inside for PRE, KZ, MORNING and NY (8); skip VWAP-against;
  skip VWAP-with; skip IN_OR. Scored only if it removes at least 10 trades and at most half.

GATES — fixed before any bot trade was looked at
  1 BOTH HALVES  the removed trades lose net R in each half of explore (split 2022-11-01).
  2 LUCK  their t (mean net R / its standard error — a good filter removes a NEGATIVE t) must be
          below the 5th percentile of the most negative t any of the 22 filters reaches when each
          bot's features are shuffled across its own trades (5,000 shuffles, seed fixed) — the
          family's best when the features carry no information.
  3 TEST  survivors only, ONCE: the removed trades lose net R on 2018-09-14 -> 2019-12-31.
  ⚠ Removing a trade frees the bot's one slot, so a real replay with the filter could take a setup
    this list never shows. A survivor's total is an estimate until the bot is replayed with the
    filter inside it.

TEST PLAN — declared 2026-09-15 AFTER the explore run and BEFORE any test-set bar was loaded
  No filter passed gate 1, so no filter goes to the test set. What explore DID show is a SIZING
  question rather than a filter: the SOS Fade bot's trades entered 08:00-10:59 NY averaged +1.85R
  (71 trades) against +0.36R for the rest (132). It was found by LOOKING, so it is a hypothesis,
  and it gets ONE check on data nobody has looked at, through `--spend-test-set`:
  C3 SOS FADE MORNING  the SOS Fade bot's own trades 2018-09-14 -> 2019-12-31, its M15 and M5 bars
       rebuilt UP from the cached M1 (identical to the broker's bars on all 401,787 M5 and 133,933
       M15 bars of explore; re-checked on a slice before use, and refused if not). Trades entered
       08:00-10:59 NY on a weekday must earn more net R per trade than the rest AND be net
       positive. PASS = both.
       ⚠ A SCREEN: about 40 trades are expected, so a pass is weak support and a fail says the
         explore gap did not carry — neither is proof.

MEASURED 2026-09-15 — PU Prime XAUUSD.p, puprime_ecn
  EXPLORE: SOS Fade 203 trades +178.5R, extreme leg 97 trades +38.1R; 0 of 22 filters pass gate 1
    — every window and both VWAP sides hold net-winning trades for both bots. C3 reference: morning
    71 trades +1.848R each against 132 at +0.358R, z +1.64.
  TEST SET, spent once: the SOS Fade bot 27 trades -13.0R; C3 morning 10 trades -0.737R each
    against 17 at -0.332R -> FAIL. Record: backtest/notes/tools.md.

Usage (from the repo root, with command-center/backend/.venv/bin/python):
  python backtest/tools/bot_confluence_study.py
  python backtest/tools/bot_confluence_study.py --spend-test-set   # ONCE — C3 only
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import killzone_study as K  # noqa: E402
import ny_open_scalp_study as N  # noqa: E402

from backtest.data.resample import resample_up  # noqa: E402
from backtest.data.source import BarSource  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402
from backtest.replay.build import build_strategy  # noqa: E402

SERVER = "PUPrime-Demo"
SYMBOL = "XAUUSD.p"
BOTS = {  # instance key -> (package, primary timeframe in minutes)
    "sos_fade_demo": ("strategies.python.sos_fade", 15),
    "extreme_leg_demo": ("strategies.python.extreme_leg", 5),
}
CAPITAL, WARMUP = 10_000.0, 1000
SPLIT = pd.Timestamp("2022-11-01")
WINDOWS = {"PRE": (8 * 60, 9 * 60 + 30), "MORNING": (8 * 60, 11 * 60), "NY": (8 * 60, 17 * 60)}
FILTERS = [(how, w) for w in ("PRE", "KZ", "MORNING", "NY") for how in ("skip", "only")] + [
    ("skip", "VWAP_AGAINST"),
    ("skip", "VWAP_WITH"),
    ("skip", "IN_OR"),
]
MIN_REMOVED = 10
SHUFFLES, Q = 5000, 0.05
SEED = 20260917


# ─────────────────────────────── replay ───────────────────────────────


def live_config(key: str, cfg_cls):
    """The bot's live config: every instance `strategy_params` field the config declares."""
    params = json.loads((ROOT / "algos/markets/fx/instances" / key / "config.json").read_text())
    params = params["strategy_params"]
    fields = {f.name for f in dataclasses.fields(cfg_cls)}
    use = {k: v for k, v in params.items() if k in fields}
    ignored = sorted(k for k in params if k not in fields and not k.startswith("_"))
    return cfg_cls(**use), ignored


def replay(key: str, start: str, end: str, m1: pd.DataFrame | None = None) -> pd.DataFrame:
    """The bot's closed trades. Bars are the broker's own cached bars, or — with `m1` — those M1
    bars resampled UP (the test set has no cached M5/M15; see `check_rebuilt`)."""
    pkg, tf = BOTS[key]
    spec = importlib.import_module(pkg).LAB_STRATEGY
    cfg, ignored = live_config(key, spec["config"])
    src = BarSource(server=SERVER)

    def load(minutes: int) -> pd.DataFrame:
        if m1 is not None:
            return resample_up(m1, minutes, 1)
        return src.load(SYMBOL, str(minutes), start, end)

    df = load(tf)
    strat = build_strategy(
        spec["strategy"], cfg, initial_capital=CAPITAL, cost_profile=PROFILES["puprime_ecn"]
    )
    t0 = time.time()
    fill_tf = int(getattr(cfg, "exec_sec_fill_tf_min", 0) or 0)
    if getattr(cfg, "exec_secondary", False):
        strat.run_dual(df, load(fill_tf), warmup=WARMUP)
        how = f"M{tf} + M{fill_tf} re-entry feed"
    else:
        strat.run(df, warmup=WARMUP)
        how = f"M{tf}"
    rows = []
    for t in strat.execution.trades:
        ms = int(getattr(t, "entry_ms", 0) or 0)
        ts = pd.Timestamp(ms, unit="ms") if ms else df.index[min(t.entry_index, len(df) - 1)]
        rows.append(
            dict(
                entry=ts, dir=int(t.dir), r=float(t.r), price=float(t.entry_price),
                costs=float(t.costs_usd), kind=getattr(t, "kind", "primary"),
            )
        )  # fmt: skip
    tr = pd.DataFrame(rows)
    print(
        f"  {key}: {how}, {len(df):,} bars {start} -> {end}: {len(tr)} trades, "
        f"{tr.r.sum():+.1f}R net, costs ${-tr.costs.sum():,.0f} charged"
        + (f"; instance fields NOT on the config: {ignored}" if ignored else "")
        + f" ({time.time() - t0:.0f}s)"
    )
    return tr


# ─────────────────────────────── features ───────────────────────────────


def features(tr: pd.DataFrame, tp: K.Tape, lv: N.Levels, zones: list) -> pd.DataFrame:
    t = pd.DatetimeIndex(tr.entry)
    ny = t.tz_localize("UTC").tz_convert(K.S.NY)
    minute = np.asarray(ny.hour * 60 + ny.minute)
    weekday = np.asarray(ny.weekday < 5)
    out = pd.DataFrame(index=tr.index)
    for name, (a, b) in WINDOWS.items():
        out[name] = weekday & (minute >= a) & (minute < b)
    out["KZ"] = weekday & np.any([(minute >= s) & (minute < s + d) for _, s, d in zones], axis=0)
    j = np.searchsorted(tp.raw.index.to_numpy(), t.to_numpy(), side="left") - 1
    vw = np.where(j >= 0, lv.bar_vwap[np.clip(j, 0, None)], np.nan)
    known = np.isfinite(vw)
    with_ = np.where(tr.dir > 0, tr.price > vw, tr.price < vw)
    out["VWAP_WITH"] = known & with_
    out["VWAP_AGAINST"] = known & ~with_
    date = np.asarray(ny.tz_localize(None).normalize(), dtype="datetime64[ns]")
    d = np.searchsorted(tp.days, date)
    d_ok = (d < len(tp.days)) & (tp.days[np.clip(d, 0, len(tp.days) - 1)] == date)
    dd = np.clip(d, 0, len(tp.days) - 1)
    hi, lo = np.where(d_ok, lv.orh[dd], np.nan), np.where(d_ok, lv.orl[dd], np.nan)
    after = weekday & (minute >= lv.windows["OR5"][0]) & (minute < 17 * 60)
    with np.errstate(invalid="ignore"):
        out["IN_OR"] = after & (tr.price >= lo) & (tr.price <= hi)
    out["vwap_known"] = known
    return out


def masks(ft: pd.DataFrame) -> np.ndarray:
    """[filter, trade] -> True where that filter removes the trade."""
    m = []
    for how, w in FILTERS:
        col = ft[w].to_numpy(bool)
        m.append(col if how == "skip" else ~col)
    return np.array(m)


def score(M: np.ndarray, r: np.ndarray, first: np.ndarray) -> dict:
    """Per filter: removed count, total, halves, mean and t of the removed trades."""
    n = M.sum(axis=1)
    # Elementwise, never `@`: Apple Accelerate's matmul raises spurious floating-point warnings
    # on a bool-by-float product, which read like a data fault in the log.
    tot = (M * r).sum(axis=1)
    h1 = ((M & first) * r).sum(axis=1)
    h2 = tot - h1
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = tot / n
        var = ((M * (r - mean[:, None]) ** 2).sum(axis=1)) / (n - 1)
        t = np.where((n > 1) & (var > 0), mean / np.sqrt(var / n), 0.0)
    size_ok = (n >= MIN_REMOVED) & (n <= len(r) / 2)
    return dict(n=n, tot=tot, h1=h1, h2=h2, mean=mean, t=t, ok=size_ok & (h1 < 0) & (h2 < 0))


def max_dd(r: np.ndarray) -> float:
    eq = np.cumsum(r)
    return float(np.max(np.maximum.accumulate(np.concatenate(([0.0], eq)))[1:] - eq, initial=0.0))


# ─────────────────────────────── C3 and the test set ───────────────────────────────


def c3(tr: pd.DataFrame, ft: pd.DataFrame) -> dict:
    """C3 — SOS Fade trades entered 08:00-10:59 NY against the rest (see TEST PLAN)."""
    m, r = ft["MORNING"].to_numpy(bool), tr.r.to_numpy()
    a, b = r[m], r[~m]
    z = math.nan
    if len(a) > 1 and len(b) > 1:
        z = (a.mean() - b.mean()) / math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    ma = float(a.mean()) if len(a) else math.nan
    mb = float(b.mean()) if len(b) else math.nan
    return dict(
        n_m=len(a), mean_m=ma, tot_m=float(a.sum()), n_o=len(b), mean_o=mb, tot_o=float(b.sum()),
        z=z, passed=bool(len(a) > 0 and len(b) > 0 and ma > mb and a.sum() > 0),
    )  # fmt: skip


def c3_line(c: dict) -> str:
    return (
        f"08:00-10:59 NY {c['n_m']} trades {c['mean_m']:+.3f}R each ({c['tot_m']:+.1f}R) against "
        f"the rest {c['n_o']} trades {c['mean_o']:+.3f}R each ({c['tot_o']:+.1f}R), z {c['z']:+.2f}"
    )


def check_rebuilt(start: str = "2020-01-01", end: str = "2020-07-01") -> None:
    """Bars rebuilt UP from M1 must equal the broker's own bars, or the test set is refused."""
    m1 = K.load_1m(start, end)
    src = BarSource(server=SERVER)
    last = (pd.Timestamp(end) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    for tf in (5, 15):
        rs, ca = resample_up(m1, tf, 1), src.load(SYMBOL, str(tf), start, last)
        px = ["open", "high", "low", "close"]
        if not rs.index.equals(ca.index) or not np.array_equal(rs[px].values, ca[px].values):
            raise RuntimeError(
                f"M{tf} rebuilt from M1 differs from the broker's bars on {start}-{end}"
            )
    print(f"CHECK — M5 and M15 rebuilt from M1 equal the broker's own bars on {start} -> {end}")


def test_plan() -> None:
    """The ONE pre-declared test-set run: C3 on the SOS Fade bot's 2018-09-14 -> 2019-12-31 trades."""
    check_rebuilt()
    m1 = K.load_1m(*K.TEST_SET, volume=True)
    tr = replay("sos_fade_demo", K.TEST_SET[0], K.TEST_SET[1], m1=m1)
    tr = tr[(tr.entry >= K.TEST_SET[0]) & (tr.entry < K.TEST_SET[1])].reset_index(drop=True)
    tp = K.build_tape(m1, hold=N.HOLD)
    ft = features(tr, tp, N.levels(tp), K.kill_zones())
    c = c3(tr, ft)
    print(f"\nC3 on the TEST SET {K.TEST_SET[0]} -> {K.TEST_SET[1]} (spent): {c3_line(c)}")
    print(f"  -> {'PASS' if c['passed'] else 'FAIL'}")


# ─────────────────────────────── main ───────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="backtest/reports/bot_confluence_study")
    ap.add_argument("--spend-test-set", action="store_true")
    a = ap.parse_args()
    if a.spend_test_set:
        test_plan()
        return
    t_all = time.time()
    start, end = K.EXPLORE[0], "2025-08-31"
    zones = K.kill_zones()
    print("replaying the live bots (explore window):")
    trades = {k: replay(k, start, end) for k in BOTS}
    tp = K.build_tape(K.load_1m(*K.EXPLORE, volume=True), hold=N.HOLD)
    lv = N.levels(tp)
    rng = np.random.default_rng(SEED)
    per, feats, real_rows = {}, {}, []
    for key, tr in trades.items():
        tr = tr[(tr.entry >= start) & (tr.entry < K.EXPLORE[1])].reset_index(drop=True)
        ft = features(tr, tp, lv, zones)
        M, r = masks(ft), tr.r.to_numpy()
        first = (tr.entry < SPLIT).to_numpy()
        per[key] = (M, r, first)
        feats[key] = (tr, ft)
        sc = score(M, r, first)
        base = dict(n=len(r), tot=r.sum(), dd=max_dd(r))
        print(
            f"\n{key}: {base['n']} trades, {base['tot']:+.1f}R, max drawdown {base['dd']:.1f}R, "
            f"win {np.mean(r > 0) * 100:.0f}%  |  VWAP known on {int(ft.vwap_known.sum())}; "
            f"PRE {int(ft.PRE.sum())}, KZ {int(ft.KZ.sum())}, MORNING {int(ft.MORNING.sum())}, "
            f"NY {int(ft.NY.sum())}, VWAP-with {int(ft.VWAP_WITH.sum())}, IN_OR {int(ft.IN_OR.sum())}"
        )
        print(
            f"  {'filter':<20} {'removes':>7} {'their R':>8} {'avg':>7} {'t':>6} {'1st½':>7} "
            f"{'2nd½':>7} {'new total':>9} {'new DD':>7}  gate1"
        )
        for i, (how, w) in enumerate(FILTERS):
            keep = ~M[i]
            row = dict(
                bot=key, filter=f"{how} {w}", removed=int(sc["n"][i]), removed_r=sc["tot"][i],
                removed_avg=sc["mean"][i], t=sc["t"][i], h1=sc["h1"][i], h2=sc["h2"][i],
                new_total=r[keep].sum(), new_dd=max_dd(r[keep]), gate1=bool(sc["ok"][i]),
            )  # fmt: skip
            real_rows.append(row)
            print(
                f"  {row['filter']:<20} {row['removed']:>7} {row['removed_r']:>+8.1f} "
                f"{row['removed_avg']:>+7.3f} {row['t']:>+6.2f} {row['h1']:>+7.1f} {row['h2']:>+7.1f} "
                f"{row['new_total']:>+9.1f} {row['new_dd']:>7.1f}  {' Y' if row['gate1'] else ' .'}"
            )
    # gate 2: the family's best under shuffled features, both bots together
    best = np.full(SHUFFLES, np.inf)
    for s in range(SHUFFLES):
        lows = []
        for M, r, first in per.values():
            p = rng.permutation(len(r))
            sc = score(M, r[p], first[p])
            if sc["ok"].any():
                lows.append(sc["t"][sc["ok"]].min())
        if lows:
            best[s] = min(lows)
    q = float(np.quantile(best, Q))
    for row in real_rows:
        row["beats_luck"] = bool(row["gate1"] and row["t"] < q)
    passed = [r for r in real_rows if r["beats_luck"]]
    real_best = min((r["t"] for r in real_rows if r["gate1"]), default=math.inf)
    print(
        f"\nLUCK BAR — {SHUFFLES} shuffles of each bot's features across its own trades (seed {SEED}): "
        f"the family's most negative t has median {np.median(best[np.isfinite(best)]):+.2f}, 5th "
        f"percentile {q:+.2f}; shuffles where no filter passes gate 1: "
        f"{int(np.sum(~np.isfinite(best)))}"
    )
    print(
        f"  real: {sum(r['gate1'] for r in real_rows)} filters pass gate 1; the best t "
        f"{real_best:+.2f} is matched or beaten by {np.mean(best <= real_best) * 100:.1f}% of shuffles"
    )
    print(f"  FILTERS PAST BOTH GATES: {len(passed)}")
    for r in passed:
        print(
            f"    {r['bot']} {r['filter']}: removes {r['removed']} trades worth {r['removed_r']:+.1f}R"
        )
    if not passed:
        print("  Nothing earned the test set; it stays UNSPENT.")
    print(
        f"\nC3 reference on explore (already seen — the hypothesis came from here): "
        f"{c3_line(c3(*feats['sos_fade_demo']))}"
    )
    K.write_csv(Path(a.out) / "filters.csv", real_rows)
    print(f"\ncsv: {a.out}/  ({time.time() - t_all:.0f}s)")


if __name__ == "__main__":
    main()
