"""fft_confluence_study.py — do the FFT bot's BEST trades share anything the indicator can see, and
does any indicator part not yet tried on FFT raise profit or cut drawdown?

A STUDY: it replays the FFT bot and scores features on its trade list; it changes nothing in the bot.

THE ASK (the user, 2026-09-22): "Did we find any similarity with the best setups — the ones that had
the least drawdown and went to TP fastest. Look at all aspects and utilize everything my indicator
has to offer to see if we have any extra tools we can use to increase profits or minimize drawdown."

FROZEN BEFORE ANY FEATURE WAS COMPUTED (2026-09-22). Nothing below was chosen after a result.

THE TRADES — the bot as the lab replays it: PU Prime `XAUUSD.p` 1m, 2020-01-01 -> 2026-09-22,
`puprime_ecn` with bid/ask fills, commission and swap, 5%, every shipped setting except the sweep
size at 1x (sizing changes no trade and no R). One position.
  DEV     entries before 2025-09-01          RECENT  entries from 2025-09-01
  ⚠ There is NO untouched gold hold-out for FFT: 2018-09 -> 2019-12 was spent on 2026-09-21. So a
    pass here is a LEAD for the demo and the forward log, never a proven rule.

ALREADY TESTED ON FFT AND NOT RE-TESTED HERE (backtest/notes/fft_ledger.md): session times, kill
zones, news, day of week, the 15m / 5m / 1h structure counts, the sniper zone, a 5m gap inside the
zone, the pullback's path, the prior counter-run, wider and tighter stops, break-even, TP choices,
re-entry after a stop. The sweep label is shipped as sizing and is shown for reference only.

PART A — WHAT THE BEST TRADES LOOK LIKE (description only, no verdicts)
  heat   = worst move against the trade before it closed, in R (0 = never went against it)
  CLEAN  = reached TP2 with heat <= 0.30R          FAST = reached TP2 within 30 minutes of the fill
  Each feature's share among CLEAN winners, the other winners and the losers.

PART B — NINE INDICATOR FEATURES never tried on FFT, each known BEFORE the fill minute:
  OB    a same-side 5m order block overlaps the entry-to-stop zone (61.8 to 1.0), active at the last
        closed 5m candle before the fill minute
  VWAP  a buy fills below the session VWAP, a sell above it (VWAP as of the 1m bar before the fill)
  POC   the Asia session's point of control sits between the entry and the stop
  DIV   a same-direction regular RSI divergence confirmed on the 1m between the leg's extreme and
        the fill
  EQT   an active opposite-side equal level (equal highs for a buy) between the entry and TP2
  EQS   an active same-side equal level (equal lows for a buy) between the entry and 0.5R past the
        stop
  CDL   a with-trade reversal candle pattern on any of the last 3 closed 5m candles before the fill
  TRND  the last completed day's market-condition label is TRENDING
  HVOL  the last completed day's market-condition label is HIGH_VOLATILITY
  Two uses each — SIZE: the feature's trades at 1.5x (exact in R) — SKIP: the feature's trades
  dropped (an ESTIMATE: a real replay could take a setup the freed slot allows).
  GATE 1 LUCK   the t of mean R (feature vs rest) on DEV must beat the 95th percentile of the
                family's largest |t| when all nine labels are shuffled together across DEV trades
                (5,000 shuffles, seed 7) — the best a feature does when features carry nothing.
  GATE 2 BOTH   the same sign on RECENT, and — SIZE: return per drawdown better in BOTH windows;
                SKIP: total R higher in BOTH windows.
  Mean heat is reported beside each feature (feature vs rest).

PART C — A TIME EXIT (not an indicator part; the other half of "fastest to TP"):
  still open N minutes after the fill -> exit at that minute's 1m close, the trade's own costs in R
  carried over. N in {15, 30, 60, 120}. PASS = higher total R, a smaller worst drawdown AND a better
  return per drawdown, in BOTH windows. ⚠ An estimate: an earlier exit frees the slot sooner.
MEASURED 2026-09-22 (187 trades: 153 dev, 34 recent; win 71.1%, +0.148R):
  A  65 clean winners, 42 fast, 30 both. Winners and losers both take ~1 hour (median 59 / 60 min).
     Clean winners vs losers: SWEEP 37% vs 17% (already sized 1.5x), EQT 11% vs 0%, DIV 31% vs 20%.
  B  NOTHING clears the luck bar (pooled t, bar 2.78): EQT 1.97, VWAP -1.50, POC 1.40, the rest
     under 0.5. HVOL never occurs on a trade's prior day. ⚠ As first run with the frozen WELCH t,
     EQT "passed" SIZE (t 7.22 vs 3.46) — the statistic, not the feature (see `tstat`).
     EQT is the one LEAD: 11 trades in 6.7 years, 11 winners, heat 0.22R vs 0.55R, 6 of them
     sweeps (already 1.5x). Chance of 10/10 in DEV from a random 10: 3%; across nine features ~1 in 4.
  C  FAIL — every cut lowers total R: dev +23.2R held vs +1.7 / +6.1 / +11.0 / +14.3R at
     15 / 30 / 60 / 120 min; recent +4.5R vs +1.5 / 0.0 / -0.3 / +2.0R.

PART D — THE EQT LEAD ON OTHER MARKETS (`--market`), FROZEN 2026-09-22 BEFORE ANY RUN:
  The FFT bot itself, every shipped rule, on PU Prime 1m `EURUSD_p` and `NAS100`, 2020-01-01 ->
  2026-09-22, COST-FREE (neither market's costs are measured), raw bars as the lab replays them.
  EQT exactly as in part B. Test: mean R with EQT minus without, one-sided permutation p (10,000
  shuffles, seed 7). HOLDS on a market at a gain > 0 and p < 0.05; CONFIRMED when it holds on
  both, or p < 0.0125 on one with the same sign on the other — the bar the three earlier leads
  were held to (fft_ledger.md). Run once per market; the result is written up whatever it says.
  MEASURED 2026-09-22 — NOT CONFIRMED. EURUSD 237 trades, -0.062R (the ledger's -0.062R: the
  method reproduces), EQT 4 trades, 2 won, -0.13R vs the rest, p 0.58. NAS100 247 trades, +0.062R,
  EQT 7 trades, 6 won, +0.33R vs the rest, p 0.13 — the lead's direction, not past the bar.

PART E — MORE DEPTH FOR THE EQUAL-LEVEL LEAD (`--depth`), FROZEN 2026-09-22 BEFORE ANY RUN.
  The user: "I want to test that more ... I just need more depth." The bot takes ~1.5 of these a
  year on gold, so depth comes from the touches it does NOT take and from other markets.
  UNIT  every FIRST 61.8 touch `fft_first_touch_study.py` records (cleaned PU Prime 1m, COST-FREE,
        counted after its 31-day warm-up), scored at the bot's bracket — entry 61.8, stop 1.0,
        TP2 38.2: R = reward/risk on a win, -1 on a loss, the study's own walk.
  EQ    the bot's label exactly: `feat_5m` on the study's own cleaned bars at the touch minute.
  CELLS the bot's four gates — 15m with the trade, 1m against and clean, first 5m leg, leg not
        across a closure — 16 cells. Shuffles move EQ labels only WITHIN a cell (10,000, seed 7),
        so EQ touches cannot win merely by sitting in easier cells. Test statistic: mean R with EQ
        minus without; one-sided p.
  E1  GOLD 2020-01-01 -> 2026-09-22, only the touches FFT does NOT trade (any gate failed) — the 10
      trades that found the lead are excluded by construction. PASS: gain > 0 and p < 0.05.
  E2  NINE MORE MARKETS, all first touches, 2020-01-01 -> 2026-09-22 (or the broker's floor):
      XAGUSD.p EURUSD.p NAS100 GBPUSD.p USDJPY.p AUDUSD.p DJ30 GER40 UK100. POOLED, shuffles within
      market x cell. PASS: pooled gain > 0 at p < 0.05 AND gain > 0 on at least 6 of the 9.
  E3  GOLD 2018-09-14 -> 2019-12-31, ONCE (FFT's reserved window; EQ never looked at there): all
      first touches. Supporting only — PASS: gain > 0.
  Reported beside each: the touches passing ALL FFT gates with EQ (the would-be setup's own
  trades) — count and win rate. CONFIRMED only if E1 and E2 both pass.
  MEASURED 2026-09-22 — NOT CONFIRMED: E1 FAILS, so no E2 result can confirm it.
  E1  gold's 69 untraded EQ touches win 58.0% vs 62.3% without, -0.071R, p 0.82. EQ is no better
      in ANY gate group (15m against 55% vs 61%; 1m not ready 62.5% vs 62.8%; later leg 56% vs 63%).
  E2  FAILS on p: pooled 9 markets 31,630 touches, EQ 661 win 64.9% vs 61.7%, +0.049R, p 0.097;
      gain > 0 on 7 of 9 (UK100 +0.292R p 0.01 from its 2023-08-25 floor, USDJPY +0.094R, DJ30
      +0.086R, NAS100 +0.079R, EURUSD, silver, AUDUSD ~0; GBPUSD -0.022R, GER40 -0.014R).
      A small general tilt, suggestive and unproven — nothing like the 10/10.
  E3  gold 2018-19: 12 EQ touches win 83% vs 60%, +0.383R, p 0.02 — the one supporting window.
  The would-be setup's OWN trades out of sample (all FFT gates + EQ, all nine markets and gold
  2018-19): 39 of 58 won (67%) — TP2 breaks even at ~62% before costs. About FFT's usual edge;
  the 10/10 on gold 2020-26 was most likely a streak.
"""

from __future__ import annotations  # noqa: E402

import argparse  # noqa: E402
import pickle  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
for _p in (
    ROOT,
    ROOT / "engines",
    ROOT / "strategies" / "python",
    ROOT / "command-center" / "backend",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SPLIT = "2025-09-01"
FEATURES = ["OB", "VWAP", "POC", "DIV", "EQT", "EQS", "CDL", "TRND", "HVOL"]
PARAMS = {
    "exec_longs": True,
    "exec_shorts": True,
    "size_mode": "Risk % of equity",
    "exec_risk_pct": 5,
    "fixed_qty": 1,
    "sweep_risk_x": 1.0,
    "max_bos": 0,
    "req_15m": True,
    "skip_15m_overextended": False,
    "only_sweep": False,
    "req_1m_against": True,
    "skip_closure_legs": True,
    "stop_level": "1.0",
    "target": "TP2 38.2",
    "second_touch": False,
    "fill_profile": "",
}
SPEC = {
    "broker_profile": "puprime_ecn",
    "cost_layers": ["bid_ask_fills", "commission", "swap"],
    "commission_per_side": 1.0,
    "slippage_ticks": 0,
    "max_lots": 100.0,
}
START, END = "2020-01-01", "2026-09-22"
SPREAD = (
    0.12  # puprime_ecn XAUUSD, measured (backtest/CLAUDE.md) — a short's market exit buys the ask
)


def bars() -> pd.DataFrame:
    from services import python_runner as pr

    from backtest.data.source import BarSource

    return BarSource(server=pr.bar_server(SPEC)).load("XAUUSD.p", 1, START, END)


def trades(df: pd.DataFrame) -> pd.DataFrame:
    """The bot, replayed the way the lab replays it, each trade paired with its touch record."""
    from services import python_runner as pr

    from backtest.replay import build_strategy

    _, entry = pr._resolve("FftStrategy")
    s = build_strategy(
        entry["strategy"],
        pr._build_config(entry["config"], PARAMS, "XAUUSD.p"),
        initial_capital=10_000.0,
        cost_profile=pr._cost_profile(SPEC),
        max_lots=pr._max_lots(SPEC),
    )
    pr._replay("study", s, df, len(df))
    tr = sorted(s.execution.trades, key=lambda t: t.entry_ms)
    tc = sorted((u for u in s.touches if u.traded), key=lambda u: u.ts_ms)
    assert len(tr) == len(tc) and all(u.dir == t.dir for u, t in zip(tc, tr)), "trade/touch pairing"
    rows = []
    for t, u in zip(tr, tc):
        lv = u.levels
        rows.append(
            dict(
                entry_ms=t.entry_ms,
                exit_ms=t.exit_ms,
                dir=t.dir,
                entry=t.entry_price,
                stop=lv["1.0"],
                tp2=lv["TP2"],
                zero=lv["TP3"],
                r=t.r,
                risk_usd=t.risk_usd,
                costs_usd=t.costs_usd,
                reason=t.exit_reason,
                heat=abs(t.mae_usd) / t.risk_usd,
                mins=(t.exit_ms - t.entry_ms) / 60_000,
                SWEEP=bool(u.swept),
            )
        )
    tb = pd.DataFrame(rows)
    tb["t"] = pd.to_datetime(tb.entry_ms, unit="ms")
    tb["recent"] = tb.t >= SPLIT
    return tb


def _ms(ix) -> np.ndarray:
    return ix.values.astype("datetime64[ms]").astype(np.int64)


def feat_5m(df: pd.DataFrame, tb: pd.DataFrame) -> pd.DataFrame:
    """OB, EQT, EQS, CDL — the 5m engines as MPC Jarvis runs them, read at the last 5m candle that
    CLOSED before the fill minute."""
    from candlesticks import CHART_PRESET, CandlestickEngine
    from equal_highs_lows import EqualHighsLowsEngine
    from order_blocks import OrderBlockEngine

    m5 = (
        df.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    starts = _ms(m5.index)
    last = np.searchsorted(starts, tb.entry_ms.values - 300_000, side="right") - 1
    need = {}
    for k, i in enumerate(last):
        need.setdefault(int(i), []).append(k)
    ob, eq, cs = OrderBlockEngine(), EqualHighsLowsEngine(), CandlestickEngine(**dict(CHART_PRESET))
    pats = []  # (index, direction) of every with-direction pattern
    snap = {}
    o, h, l, c = (m5[x].values for x in ("open", "high", "low", "close"))
    for i in range(len(m5)):
        eo = ob.update(i, o[i], h[i], l[i], c[i])
        ee = eq.update(i, h[i], l[i], c[i])
        ec = cs.update(i, o[i], h[i], l[i], c[i])
        for p in ec.detected:
            if p.direction:
                pats.append((i, p.direction))
        if i in need:
            snap[i] = (
                [(b.bottom, b.top) for b in eo.active_bull],
                [(b.bottom, b.top) for b in eo.active_bear],
                list(ee.active_eqh),
                list(ee.active_eql),
            )
    pat_ix = np.array([p[0] for p in pats])
    pat_dir = np.array([p[1] for p in pats])
    out = []
    for k, row in tb.iterrows():
        bull, bear, eqh, eql = snap[int(last[k])]
        d, e, s, t2 = row.dir, row.entry, row.stop, row.tp2
        risk = abs(e - s)
        lo, hi = min(e, s), max(e, s)
        blocks = bull if d == 1 else bear
        f_ob = any(b <= hi and t >= lo for b, t in blocks)
        if d == 1:
            f_eqt = any(e < p <= t2 for p in eqh)
            f_eqs = any(s - 0.5 * risk <= p < e for p in eql)
        else:
            f_eqt = any(t2 <= p < e for p in eql)
            f_eqs = any(e < p <= s + 0.5 * risk for p in eqh)
        w = (pat_ix <= last[k]) & (pat_ix > last[k] - 3) & (pat_dir == d)
        out.append(dict(OB=f_ob, EQT=f_eqt, EQS=f_eqs, CDL=bool(w.any())))
    return pd.DataFrame(out, index=tb.index)


def feat_1m(df: pd.DataFrame, tb: pd.DataFrame) -> pd.DataFrame:
    """VWAP, POC, DIV — the 1m engines, run over the three days before each fill (VWAP re-anchors
    daily, the Asia profile needs one closed session, RSI settles in a few hundred bars) and read at
    the 1m bar BEFORE the fill minute. Unknown (engine not formed) is NaN, never False."""
    from rsi_divergence import RsiDivergenceEngine
    from session_volume_profile import SvpEngine
    from vwap import VwapEngine

    ms = _ms(df.index)
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    v = df["volume"].values if "volume" in df else np.full(len(df), np.nan)
    out = []
    for _, row in tb.iterrows():
        fill = int(np.searchsorted(ms, row.entry_ms))
        a = int(np.searchsorted(ms, row.entry_ms - 3 * 86_400_000))
        vw, svp, rsi = VwapEngine(), SvpEngine(), RsiDivergenceEngine()
        d = row.dir
        ext = None
        divs = []
        vwv = poc = None
        for j in range(a, fill):
            vwv = vw.update(j, int(ms[j]), h[j], l[j], c[j], v[j]).value
            poc = svp.update(j, int(ms[j]), o[j], h[j], l[j], c[j], v[j]).poc
            for dv in rsi.update(j, h[j], l[j], c[j]).detected:
                if dv.is_bullish == (d == 1):
                    divs.append(j)
            if (h[j] >= row.zero - 1e-9) if d == 1 else (l[j] <= row.zero + 1e-9):
                ext = j
        e, s = row.entry, row.stop
        f_vwap = np.nan if vwv is None else float((e < vwv) if d == 1 else (e > vwv))
        f_poc = np.nan if poc is None else float(min(e, s) <= poc <= max(e, s))
        f_div = float(ext is not None and any(j > ext for j in divs))
        out.append(dict(VWAP=f_vwap, POC=f_poc, DIV=f_div))
    return pd.DataFrame(out, index=tb.index)


def feat_regime(tb: pd.DataFrame) -> pd.DataFrame:
    """The last COMPLETED day's label from the app's own map (a day's label uses that whole day)."""
    from services.backtest_runner import build_date_regime_map

    try:
        mp = build_date_regime_map("XAUUSD.p", "2019-12-01", END, runner="python")
    except Exception as exc:  # cannot ask is not "no label": both columns go unknown, and say so
        print(f"regime map could not be built: {exc}")
        mp = {}
    if not mp:
        print("regime labels UNKNOWN for every trade — TRND and HVOL are not scored")
        return pd.DataFrame({"TRND": np.nan, "HVOL": np.nan}, index=tb.index)
    days = sorted(mp)
    lab = []
    for t in tb.t:
        i = np.searchsorted(days, t.strftime("%Y-%m-%d")) - 1
        lab.append(mp[days[i]] if i >= 0 else "UNKNOWN")
    lab = pd.Series(lab, index=tb.index)
    unk = lab.eq("UNKNOWN")
    return pd.DataFrame(
        {
            "TRND": np.where(unk, np.nan, lab.eq("TRENDING")),
            "HVOL": np.where(unk, np.nan, lab.eq("HIGH_VOLATILITY")),
        },
        index=tb.index,
    )


def dd(x: np.ndarray) -> float:
    cum = np.cumsum(x)
    return float(-(cum - np.maximum.accumulate(np.maximum(cum, 0))).min()) if len(x) else 0.0


def tstat(a: np.ndarray, b: np.ndarray) -> float:
    """POOLED-variance t. 🔴 The plan froze a WELCH t, and on the first run it misfired: FFT's R is
    two-valued (+0.6 at TP2, -1 at the stop), so a small group with no loser has ~zero spread and
    Welch divides by it — EQT's 10 winners scored t 7.22 and cleared a luck bar the same flaw had
    inflated to 3.46. Pooled, the spread comes from both groups: EQT 1.97 against a bar of 2.78."""
    if len(a) < 2 or len(b) < 2:
        return np.nan
    sp = np.sqrt(
        ((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2)
    )
    return (a.mean() - b.mean()) / (sp * np.sqrt(1 / len(a) + 1 / len(b)))


def book(r: np.ndarray, w: np.ndarray) -> tuple:
    x = r * w
    d = dd(x)
    return x.sum(), d, (x.sum() / d if d > 0 else np.inf)


def time_exit(df: pd.DataFrame, tb: pd.DataFrame, n: int) -> np.ndarray:
    ms = _ms(df.index)
    c = df["close"].values
    out = tb.r.values.copy()
    for k, row in tb.iterrows():
        cut = row.entry_ms + n * 60_000
        if row.exit_ms <= cut:
            continue
        j = int(np.searchsorted(ms, cut, side="right")) - 1
        px = c[j] + (SPREAD if row.dir == -1 else 0.0)
        risk = abs(row.entry - row.stop)
        out[k] = row.dir * (px - row.entry) / risk - row.costs_usd / row.risk_usd
    return out


def market(symbol: str, shuffles: int = 10_000) -> None:
    """PART D — the bot on another market, cost-free, and the EQT lead's frozen test."""
    from services import python_runner as pr

    from backtest.replay import build_strategy

    path = ROOT / "backtest" / "cache" / "PUPrime_Demo" / f"{symbol}__M1.csv"
    df = pd.read_csv(path, parse_dates=["time"]).set_index("time")
    df = df[(df.index >= START) & (df.index < pd.Timestamp(END) + pd.Timedelta(days=1))].astype(
        float
    )
    df = df[~df.index.duplicated()].sort_index()
    _, entry = pr._resolve("FftStrategy")
    params = {k: v for k, v in PARAMS.items()}
    s = build_strategy(
        entry["strategy"],
        pr._build_config(entry["config"], params, symbol),
        initial_capital=10_000.0,
        timeframe_minutes=1,
    )
    pr._replay("study", s, df, len(df))
    tr = sorted(s.execution.trades, key=lambda t: t.entry_ms)
    tc = sorted((u for u in s.touches if u.traded), key=lambda u: u.ts_ms)
    assert len(tr) == len(tc) and all(u.dir == t.dir for u, t in zip(tc, tr)), "trade/touch pairing"
    tb = pd.DataFrame(
        [
            dict(
                entry_ms=t.entry_ms,
                dir=t.dir,
                entry=t.entry_price,
                stop=u.levels["1.0"],
                tp2=u.levels["TP2"],
                r=t.r,
            )
            for t, u in zip(tr, tc)
        ]
    )
    ft = feat_5m(df, tb)
    on = ft.EQT.values.astype(bool)
    r = tb.r.values
    gain = r[on].mean() - r[~on].mean() if on.any() and (~on).any() else np.nan
    rng = np.random.default_rng(7)
    k = int(on.sum())
    null = (
        np.array(
            [
                (lambda m: r[m].mean() - r[~m].mean())(
                    np.isin(np.arange(len(r)), rng.choice(len(r), k, replace=False))
                )
                for _ in range(shuffles)
            ]
        )
        if 0 < k < len(r)
        else np.array([np.nan])
    )
    p = float((null >= gain).mean()) if np.isfinite(gain) else np.nan
    print(
        f"{symbol}: {len(tb)} trades, win {(r > 0).mean():.1%}, avgR {r.mean():+.3f} | EQT {k} trades "
        f"avgR {r[on].mean() if k else float('nan'):+.3f} (win {(r[on] > 0).mean() if k else float('nan'):.0%}) "
        f"vs {r[~on].mean():+.3f} — gain {gain:+.3f}R, one-sided p {p:.4f}, "
        f"{'HOLDS' if gain > 0 and p < 0.05 else 'does not hold'}"
    )


TP2 = ("61.8", "1.0", "TP2 38.2")
DEPTH_MARKETS = [
    "XAGUSD_p",
    "EURUSD_p",
    "NAS100",
    "GBPUSD_p",
    "USDJPY_p",
    "AUDUSD_p",
    "DJ30",
    "GER40",
    "UK100",
]
# The broker's MEASURED 1-minute floor where it is later than START (history_floors.json).
DEPTH_START = {"UK100": "2023-08-25"}


def touch_table(cache_symbol: str, start: str, end: str, holdout: bool = False) -> pd.DataFrame:
    """PART E's unit: every first 61.8 touch the study records, with its TP2 R, its gate cell and
    the bot's EQ label on the study's own cleaned bars."""
    sys.path.insert(0, str(ROOT / "backtest" / "tools"))
    import fft_first_touch_study as S
    from loaded_level_study import clean_reopens

    S.SYMBOL = cache_symbol
    touches, _, raw, _ = S.run(start, end, holdout)
    clean, _ = clean_reopens(raw)
    count_from = pd.Timestamp(start) + pd.Timedelta(days=S.WARMUP_DAYS)
    first = [
        t for t in touches if t["kind"] == "first" and TP2 in t["res"] and t["t"] >= count_from
    ]
    rows = []
    for t in first:
        res = t["res"][TP2]
        rows.append(
            dict(
                entry_ms=int(t["t"].value // 10**6),
                dir=int(t["d"]),
                entry=t["lv"]["E1"],
                stop=t["lv"]["1.0"],
                tp2=t["lv"]["TP2"],
                r=(res["reward"] / res["risk"]) if res["win"] else -1.0,
                win=bool(res["win"]),
                g15=bool(t["g15"]),
                g1=bool(t["g1dir"] and t["g1clean"]),
                leg0=t["nbos"] == 0,
                open_=not t["weekend"],
            )
        )
    tb = pd.DataFrame(rows)
    tb["EQ"] = feat_5m(clean, tb).EQT.values.astype(bool)
    tb["gated"] = tb.g15 & tb.g1 & tb.leg0 & tb.open_
    tb["cell"] = (
        tb.g15.astype(int) * 8
        + tb.g1.astype(int) * 4
        + tb.leg0.astype(int) * 2
        + tb.open_.astype(int)
    )
    tb["market"] = cache_symbol
    return tb


def strat_test(tb: pd.DataFrame, shuffles: int = 10_000, by=("market", "cell")) -> tuple:
    """Mean R with EQ minus without, and its one-sided p with EQ labels shuffled within cells."""
    r = tb.r.values
    eq = tb.EQ.values
    if eq.sum() == 0 or (~eq).sum() == 0:
        return np.nan, np.nan
    obs = r[eq].mean() - r[~eq].mean()
    groups = [np.asarray(ix) for ix in tb.groupby(list(by)).indices.values()]
    rng = np.random.default_rng(7)
    hits = 0
    lab = eq.copy()
    for _ in range(shuffles):
        for g in groups:
            lab[g] = rng.permutation(eq[g])
        hits += (r[lab].mean() - r[~lab].mean()) >= obs
    return obs, hits / shuffles


def depth_line(name: str, tb: pd.DataFrame, shuffles: int) -> float:
    gain, p = strat_test(tb, shuffles)
    e, n = tb[tb.EQ], tb[~tb.EQ]
    g = tb[tb.gated & tb.EQ]
    print(
        f"  {name:22s} {len(tb):6d} touches | EQ {len(e):4d} win {e.win.mean():5.1%} {e.r.mean():+.3f}R"
        f" vs {n.win.mean():5.1%} {n.r.mean():+.3f}R | gain {gain:+.3f}R p {p:.4f}"
        f" | all-gates EQ {len(g):3d} win {g.win.mean() if len(g) else float('nan'):5.1%}"
    )
    return gain


def depth(shuffles: int) -> None:
    out = ROOT / "backtest" / "reports" / "fft_depth"
    out.mkdir(parents=True, exist_ok=True)

    def cached(name, *args, **kw):
        f = out / f"{name}.pkl"
        if f.exists():
            return pickle.load(open(f, "rb"))
        tb = touch_table(*args, **kw)
        pickle.dump(tb, open(f, "wb"))
        return tb

    print("PART E — cost-free, TP2, first touches; shuffles within gate cells")
    gold = cached("XAUUSD_p", "XAUUSD_p", START, END)
    e1 = gold[~gold.gated]
    print("E1 gold, touches FFT does NOT trade:")
    g1 = depth_line("XAUUSD.p ungated", e1, shuffles)
    depth_line("XAUUSD.p gated (ref)", gold[gold.gated], 1000)
    print("E2 nine more markets:")
    tabs, pos = [], 0
    for m in DEPTH_MARKETS:
        try:
            tb = cached(m, m, DEPTH_START.get(m, START), END)
        except SystemExit as e:
            print(f"  {m:22s} not run — {e}")
            continue
        pos += depth_line(m, tb, shuffles) > 0
        tabs.append(tb)
    pooled = pd.concat(tabs, ignore_index=True)
    gp = depth_line(f"POOLED {len(tabs)} markets", pooled, shuffles)
    print(f"  gain > 0 on {pos} of {len(tabs)} markets")
    print("E3 gold 2018-09-14 -> 2019-12-31 (once):")
    old = cached("XAUUSD_p_2018_19", "XAUUSD_p", "2018-09-14", "2020-01-01", holdout=True)
    depth_line("XAUUSD.p 2018-19", old, shuffles)
    _ = (g1, gp)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(ROOT / "backtest" / "reports" / "fft_confluence.pkl"))
    ap.add_argument("--shuffles", type=int, default=5000)
    ap.add_argument("--market", help="PART D only: EURUSD_p or NAS100 (a PU Prime M1 cache name)")
    ap.add_argument("--depth", action="store_true", help="PART E: the equal-level lead, deeper")
    a = ap.parse_args()
    if a.depth:
        depth(a.shuffles)
        return
    if a.market:
        market(a.market)
        return
    df = bars()
    cp = Path(a.cache)
    if cp.exists():
        tb = pickle.load(open(cp, "rb"))
    else:
        tb = trades(df)
        tb = tb.join(feat_5m(df, tb)).join(feat_1m(df, tb)).join(feat_regime(tb))
        cp.parent.mkdir(parents=True, exist_ok=True)
        pickle.dump(tb, open(cp, "wb"))
    win = tb.reason.eq("target")
    print(
        f"{len(tb)} trades ({(~tb.recent).sum()} dev, {tb.recent.sum()} recent), "
        f"win {win.mean():.1%}, avgR {tb.r.mean():+.3f}"
    )

    # ── PART A
    clean = win & (tb.heat <= 0.30)
    fast = win & (tb.mins <= 30)
    print(
        f"\nPART A — clean {clean.sum()}, fast {fast.sum()}, both {(clean & fast).sum()}, "
        f"winners {win.sum()}, losers {(~win).sum()}"
    )
    print(
        f"  winners heat median {tb.heat[win].median():.2f}R, minutes median {tb.mins[win].median():.0f}"
        f" | losers minutes median {tb.mins[~win].median():.0f}"
    )
    print(f"  {'':6s} {'clean':>7s} {'other win':>9s} {'losers':>7s}   known")
    for f in ["SWEEP"] + FEATURES:
        x = tb[f].astype(float)
        sh = [np.nanmean(x[m]) for m in (clean, win & ~clean, ~win)]
        print(f"  {f:6s} {sh[0]:7.0%} {sh[1]:9.0%} {sh[2]:7.0%}   {x.notna().sum()}")

    # ── PART B
    dev = ~tb.recent
    X = np.column_stack([tb[f].astype(float).values for f in FEATURES])
    r = tb.r.values

    def tstats(Xd, rd):
        out = []
        for j in range(Xd.shape[1]):
            m = Xd[:, j]
            ok = ~np.isnan(m)
            on = ok & (m == 1)
            off = ok & (m == 0)
            out.append(tstat(rd[on], rd[off]) if 10 <= on.sum() <= ok.sum() - 10 else np.nan)
        return np.array(out)

    Xd, rd = X[dev.values], r[dev.values]
    t_dev = tstats(Xd, rd)
    rng = np.random.default_rng(7)
    mx = np.empty(a.shuffles)
    for i in range(a.shuffles):
        mx[i] = np.nanmax(np.abs(tstats(Xd[rng.permutation(len(Xd))], rd)))
    bar = np.quantile(mx, 0.95)
    print(
        f"\nPART B — luck bar |t| {bar:.2f} (95th pct of the family max over {a.shuffles} shuffles)"
    )
    print(
        f"  {'':6s} {'dev n':>5s} {'dev avgR on/off':>17s} {'t':>6s} {'rec n':>5s} {'rec avgR on/off':>17s}"
        f" {'heat on/off':>11s}  SIZE 1.5x ret/DD dev, rec (base)    SKIP total dev, rec (base)"
    )
    base = {w: book(r[m.values], np.ones(m.sum())) for w, m in (("dev", dev), ("rec", tb.recent))}
    verdict = []
    for j, f in enumerate(FEATURES):
        m = X[:, j]
        line = f"  {f:6s}"
        cells = {}
        for w, sel in (("dev", dev.values), ("rec", tb.recent.values)):
            ok = sel & ~np.isnan(m)
            on, off = ok & (m == 1), ok & (m == 0)
            cells[w] = (
                on.sum(),
                r[on].mean() if on.any() else np.nan,
                r[off].mean() if off.any() else np.nan,
            )
            wgt = np.where(np.nan_to_num(m[sel]) == 1, 1.5, 1.0)
            cells[w + "_size"] = book(r[sel], wgt)[2]
            cells[w + "_skip"] = r[sel][np.nan_to_num(m[sel]) != 1].sum()
        hon = tb.heat.values[(m == 1)].mean() if (m == 1).any() else np.nan
        hoff = tb.heat.values[(m == 0)].mean() if (m == 0).any() else np.nan
        sign_ok = np.sign(cells["dev"][1] - cells["dev"][2]) == np.sign(
            cells["rec"][1] - cells["rec"][2]
        )
        luck = abs(t_dev[j]) > bar if not np.isnan(t_dev[j]) else False
        up = t_dev[j] > 0
        size_ok = (
            luck
            and up
            and sign_ok
            and cells["dev_size"] > base["dev"][2]
            and cells["rec_size"] > base["rec"][2]
        )
        skip_ok = (
            luck
            and not up
            and sign_ok
            and cells["dev_skip"] > base["dev"][0]
            and cells["rec_skip"] > base["rec"][0]
        )
        verdict.append((f, size_ok, skip_ok))
        print(
            f"{line} {cells['dev'][0]:5d} {cells['dev'][1]:+8.3f}/{cells['dev'][2]:+.3f} {t_dev[j]:6.2f}"
            f" {cells['rec'][0]:5d} {cells['rec'][1]:+8.3f}/{cells['rec'][2]:+.3f} {hon:5.2f}/{hoff:4.2f}"
            f"  {cells['dev_size']:5.1f}, {cells['rec_size']:4.1f} ({base['dev'][2]:.1f}, {base['rec'][2]:.1f})"
            f"      {cells['dev_skip']:+6.1f}, {cells['rec_skip']:+5.1f} ({base['dev'][0]:+.1f}, {base['rec'][0]:+.1f})"
        )
    print("  PASS:", [f"{f} {'SIZE' if s else 'SKIP'}" for f, s, k in verdict if s or k] or "none")

    # ── PART C
    print("\nPART C — time exit (total R / worst DD / per DD), dev | recent")
    for n in (None, 15, 30, 60, 120):
        rr = r if n is None else time_exit(df, tb, n)
        bd, br = (
            book(rr[dev.values], np.ones(dev.sum())),
            book(rr[tb.recent.values], np.ones(tb.recent.sum())),
        )
        print(
            f"  {'hold' if n is None else f'{n:>3d} min':8s} {bd[0]:+6.1f} / {bd[1]:4.1f} / {bd[2]:4.1f}"
            f"  |  {br[0]:+5.1f} / {br[1]:4.1f} / {br[2]:4.1f}"
        )


if __name__ == "__main__":
    main()
