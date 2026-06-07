# TASK: NT8 path + naming refactor

**Goal:** Two cleanups in one pass:
1. Move `algos/markets/futures/lucid_flex/tools/` → `algos/nt8/` (the tools are generic, not LucidFlex-specific)
2. Rename `vps_backtest_runner.py` → `nt8_backtest_runner.py` and `vps_compile_runner.py` → `nt8_compile_runner.py` (MT5 also runs on the VPS — `vps_` prefix is ambiguous)

The `algos/markets/` tree is NOT going away — `crypto/` and `fx/` live there. Only `futures/lucid_flex/` becomes empty and gets deleted.

---

## Step 1 — Git moves

```bash
mkdir -p algos/nt8

git mv algos/markets/futures/lucid_flex/tools/nt8_agent.py          algos/nt8/nt8_agent.py
git mv algos/markets/futures/lucid_flex/tools/vps_backtest_runner.py algos/nt8/nt8_backtest_runner.py
git mv algos/markets/futures/lucid_flex/tools/vps_compile_runner.py  algos/nt8/nt8_compile_runner.py
git mv algos/markets/futures/lucid_flex/tools/setup_agent_task.py    algos/nt8/setup_agent_task.py
git mv algos/markets/futures/lucid_flex/tools/run_all.py             algos/nt8/run_all.py
git mv algos/markets/futures/lucid_flex/tools/analyze.py             algos/nt8/analyze.py
git mv algos/markets/futures/lucid_flex/tools/deploy.py              algos/nt8/deploy.py
git mv algos/markets/futures/lucid_flex/tools/debug_sa_display.py    algos/nt8/debug_sa_display.py
git mv algos/markets/futures/lucid_flex/tools/backtest_config.json   algos/nt8/backtest_config.json

# Remove the now-empty dirs
rmdir algos/markets/futures/lucid_flex/tools
rmdir algos/markets/futures/lucid_flex
rmdir algos/markets/futures
```

---

## Step 2 — Code changes in `algos/nt8/nt8_agent.py`

Five places:

**Line ~295 (docstring):**
```
# old: Launch vps_compile_runner.py as a subprocess
# new: Launch nt8_compile_runner.py as a subprocess
```

**Line ~301:**
```python
# old
runner = SCRIPT_DIR / "vps_compile_runner.py"
# new
runner = SCRIPT_DIR / "nt8_compile_runner.py"
```

**Lines ~561, ~624, ~689 (three identical occurrences):**
```python
# old
runner = str(SCRIPT_DIR / "vps_backtest_runner.py")
# new
runner = str(SCRIPT_DIR / "nt8_backtest_runner.py")
```

**Line ~1222 (comment):**
```
# old: logic from vps_backtest_runner.
# new: logic from nt8_backtest_runner.
```

**Line ~1242 (import):**
```python
# old
from vps_backtest_runner import _build_opt_grid_map, _set_range_in_grid, _match_display_name
# new
from nt8_backtest_runner import _build_opt_grid_map, _set_range_in_grid, _match_display_name
```

---

## Step 3 — Code changes in `algos/nt8/nt8_backtest_runner.py`

**Lines ~12 and ~17 (module docstring, two self-references):**
```
# old: python vps_backtest_runner.py --job-id ...
# new: python nt8_backtest_runner.py --job-id ...

# old: python vps_backtest_runner.py [--config ...]
# new: python nt8_backtest_runner.py [--config ...]
```

---

## Step 4 — Code changes in `algos/nt8/setup_agent_task.py`

**Line ~5 (docstring):**
```
# old: python3 markets/futures/lucid_flex/tools/setup_agent_task.py
# new: python3 algos/nt8/setup_agent_task.py
```

**Line ~27:**
```python
# old
AGENT_WIN = r"C:\trading\algos\markets\futures\lucid_flex\tools\nt8_agent.py"
# new
AGENT_WIN = r"C:\trading\algos\nt8\nt8_agent.py"
```

---

## Step 5 — Code changes in `algos/nt8/run_all.py`

**Line ~19 (docstring):**
```
# old: This SSHes to VPS and runs vps_backtest_runner.py via pywinauto.
# new: This SSHes to VPS and runs nt8_backtest_runner.py via pywinauto.
```

**Line ~137:**
```python
# old
tools_win = r"C:\trading\algos\markets\futures\lucid_flex\tools"
# new
tools_win = r"C:\trading\algos\nt8"
```

**Line ~138:**
```python
# old
runner_win = rf"{tools_win}\vps_backtest_runner.py"
# new
runner_win = rf"{tools_win}\nt8_backtest_runner.py"
```

**Line ~142:**
```python
# old
local_runner = os.path.join(SCRIPT_DIR, "vps_backtest_runner.py")
# new
local_runner = os.path.join(SCRIPT_DIR, "nt8_backtest_runner.py")
```

**Line ~146:**
```python
# old
for local, fname in [(local_runner, "vps_backtest_runner.py"),
# new
for local, fname in [(local_runner, "nt8_backtest_runner.py"),
```

---

## Step 6 — `command-center/backend/services/strategy_scanner.py`

**Line ~58:**
```python
# old
/ "algos" / "markets" / "futures" / "lucid_flex" / "tools" / "backtest_config.json"
# new
/ "algos" / "nt8" / "backtest_config.json"
```

---

## Step 7 — `command-center/backend/tests/test_strategies.py` (2 places)

Both occurrences (~line 99 and ~line 131):
```python
# old
futures_dir = tmp_path / "algos" / "markets" / "futures" / "lucid_flex"
# new
nt8_dir = tmp_path / "algos" / "nt8"
```
(Also update any downstream uses of `futures_dir` in those test functions to `nt8_dir`.)

---

## Step 8 — `command-center/backend/tests/test_integration.py`

**Line ~9:**
```
# old: cd C:\\trading\\algos\\markets\\futures\\lucid_flex\\tools
# new: cd C:\\trading\\algos\\nt8
```

---

## Step 9 — Doc updates

**`algos/README.md` (~line 82):**
```
# old: │       ├── vps_backtest_runner.py ← pywinauto NT8 Strategy Analyzer automation
# new: Update the tree to show algos/nt8/ instead of algos/markets/futures/lucid_flex/tools/
#      and rename vps_backtest_runner.py → nt8_backtest_runner.py in the description
```

**`command-center/CLAUDE.md` (2 occurrences in the feature status table):**
- `vps_backtest_runner.run_native_optimize_mode` → `nt8_backtest_runner.run_native_optimize_mode`
- `run_native_walkforward_mode()` in `vps_backtest_runner.py` → `nt8_backtest_runner.py`

**`command-center/backend/CLAUDE.md` (3 occurrences):**
- Section heading: `## NT8 Strategy Analyzer UI automation (vps_backtest_runner.py)` → `(nt8_backtest_runner.py)`
- `vps_backtest_runner.run_native_optimize_mode` → `nt8_backtest_runner.run_native_optimize_mode`
- `vps_compile_runner.py` → `nt8_compile_runner.py`

**`docs/LWG_Speed_Game_Plan.md` (~line 88):**
```
# old: NT8: nt8_agent.py / vps_backtest_runner.py
# new: NT8: nt8_agent.py / nt8_backtest_runner.py
```

**`docs/LWG_Project_State_Snapshot.md` (~line 28):**
```
# old: vps_compile_runner.py — pywinauto subprocess: ...
# new: nt8_compile_runner.py — pywinauto subprocess: ...
```

**`scripts/README.md` (~line 40):**
```
# old: python3 algos/markets/futures/lucid_flex/tools/setup_agent_task.py
# new: python3 algos/nt8/setup_agent_task.py
```

**`docs/audit/TRADER_MIGRATION_AUDIT.md`:**
Update all four rows that reference `algos/markets/futures/lucid_flex/tools/` to `algos/nt8/`.

**`docs/archive/` (lower priority — archive docs, update for accuracy):**
- `Command_Center_Backtest_Engine_Design.md`: two path refs → `algos/nt8/nt8_agent.py`
- `Pass2.5_Strategy_Location_Cleanup.md`: multiple refs to the old path

---

## Step 10 — Commit and push

```bash
git add -A
git commit -m "refactor: move NT8 tools to algos/nt8/, rename vps_ prefix to nt8_

algos/markets/futures/lucid_flex/tools/ → algos/nt8/
vps_backtest_runner.py → nt8_backtest_runner.py
vps_compile_runner.py  → nt8_compile_runner.py

The vps_ prefix was ambiguous once mt5_agent.py also ran on the VPS.
The lucid_flex path was a legacy artifact — these tools serve all NT8
strategies regardless of prop firm."

git push
```

---

## Step 11 — VPS: recreate the Task Scheduler task

The `LucidFlexAgent` schtask has the old path baked in. After pushing:

```bash
# Pull the new layout on VPS
ssh forexvps "cd C:\trading && git pull origin main"

# Delete the old task
ssh forexvps "schtasks /delete /tn LucidFlexAgent /f"

# Recreate it from the new location
ssh forexvps "python C:\trading\algos\nt8\setup_agent_task.py"

# Verify it registered
ssh forexvps "schtasks /query /tn LucidFlexAgent"
```

---

## Step 12 — Verify

```bash
# NT8 agent still starts
ssh forexvps "schtasks /run /tn LucidFlexAgent"
# Wait ~10s, then check health
curl http://localhost:8000/system/health
# NT8 dot should go green within 30s
```

---

## What does NOT change

- `algos/markets/crypto/` and `algos/markets/fx/` — untouched
- `mt5_agent.py` on VPS — lives in `C:\trading\algos\` root, separate task (`MT5AgentRDP`)
- All backend router/service code in `command-center/backend/` — no path refs to `lucid_flex/tools/`
- Strategy source files — already live in `strategies/ninjatrader/` (moved in Pass 2.5)
