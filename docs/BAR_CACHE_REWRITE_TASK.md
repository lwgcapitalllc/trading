# TASK — the bar store rewrites its whole file to add one day

**Written 2026-09-17, for a fresh session. Nothing here is started.** Paste this file's "The ask"
into a new session, or open the file and say "do this".

---

## The ask

Make a price-bar load whose window ends TODAY stop costing a full rewrite of the symbol's whole
cached file. Measure it before and after, on the real cache, and change no behaviour that decides
what a backtest is measured on.

Start with `/spec`. This touches shared lab data, so it is not a tidy-up.

---

## What is measured, and where the time goes

Measured 2026-09-17 on the Mac, driving the Command Center's account page (one account, one symbol,
XAUUSD.p):

| Step | Time |
|---|---|
| Whole page answer | **51.0s** |
| The two bar loads inside it | **41.4s** |
| Of that, writing the cache back | **26.0s** (two saves) |
| Of that, pandas `to_csv` alone | **19.2s** |
| Reading the box over SSH | 2.9s |
| Everything else | ~7s |

The same profile again after the fix. The profiling script is four lines — time
`routers/bots._account_history`, then `cProfile` the `build_history` call and sort by cumulative.

## Why it happens

- A window ending today is **never fully covered**, on purpose: `covered_spans` will not mark today,
  because a day still filling looks exactly like a complete one. That rule is correct and must
  stay. `backtest/data/source.py::_load_base` says so in its own comment.
- So every such load has one gap — today — fetches it, and calls `BarCache.save`.
- `BarCache.save` (`backtest/data/cache.py`) is a **read-modify-write of the entire file**: load the
  whole symbol/timeframe CSV, merge, write it all back atomically. Adding one day to a multi-year
  M1 file therefore costs the whole file, twice per page (M15 and M1).
- It is not only this page. **Every backtest, sweep and chart that reaches today pays it.**

## Constraints — do not trade these away

1. **Coverage may never claim more than the bars on disk.** The bars and the coverage record are
   written as ONE operation under `cache_lock` for that reason; a window between them strands
   missing bars behind a cache HIT permanently. `_load_base` explains it.
2. **Never mark today as covered.**
3. **`save` MERGES, never overwrites** — a one-day tail pull must not be able to delete years of
   bars. Two processes fetching the same range is merely wasteful today; keep that true.
4. **The write stays atomic AND stays under the lock.** Both were needed: 2026-08-06 measured a
   mid-timestamp splice and ~31,000 rows lost from the middle of a file. See `backtest/data/atomic.py`.
5. **A stale feed version still overwrites rather than merges** (`is_stale`), so bad data is not
   laundered into a file stamped current.
6. **No bar values may change.** Same bars in, same bars out, same order, same dedup rule
   (incoming wins on a duplicate timestamp).

## Routes worth weighing (pick one and say why)

- **Append-only tail write.** When every incoming bar is newer than the file's last timestamp,
  append instead of rewriting. The common case by far. Needs the same lock, an atomic append, and a
  fallback to the full merge whenever the incoming frame overlaps or predates the tail.
- **Partition the file** (per year or per month). Adding today rewrites one small partition. Bigger
  change: `load`, `is_stale`, the meta sidecar and the lock all move with it, and every existing
  cache file needs a migration that cannot lose a bar.
- **A faster whole-file format** (Parquet/Feather). Cheapest to reason about, still O(file) per
  write, and changes what a human can open with a text editor.
- **Do nothing to the store; cache higher up.** Already done for the account page (a memo plus
  background loading, `command-center/backend/services/account_history.py`). It does NOT help
  backtests, which is why this task exists.

## How to prove it

- **Before/after timings** from the same profile, on the real cache, quoted in the commit.
- **Byte-identical output:** take a cache file, run the old and new paths over the same fetch, and
  compare the resulting frames exactly — not just row counts.
- **The concurrency case:** two processes saving overlapping ranges at once end with every bar from
  both and no splice. The 2026-08-06 incident is the shape to reproduce deliberately.
- **A crash between the bars and the coverage record** still leaves coverage no wider than the bars.
- **Watch each new test go RED** for the right reason (`/prove`), and say in its docstring what
  mutation turned it red.
- `scripts/run_all_tests.sh` before pushing — this is lab data every backtest reads.

## Files

- `backtest/data/cache.py` — `BarCache.save`, `merge`, `load`, `is_stale`, the meta sidecar
- `backtest/data/source.py` — `_load_base`, the gap loop, `_market_was_shut`
- `backtest/data/atomic.py` — why both the lock and the atomic write are needed
- `backtest/data/coverage.py` (or wherever `covered_spans` lives) — the never-mark-today rule
- `backtest/notes/broker-data.md` — the owning notes file for this area
- Consumer that first exposed it: `command-center/backend/services/account_history.py`

## Out of scope

- The Command Center's account page. It is already fast and its workaround stays either way.
- The never-mark-today rule, the history-floor measurement, and anything about which bars a run is
  entitled to.
