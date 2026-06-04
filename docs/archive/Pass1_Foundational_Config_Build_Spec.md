# Pass 1 — Foundational Config Layer + Strategy Genericization
## Build Spec

**For Claude Code.** This pass introduces a foundational config layer that
every strategy reads at runtime from the active ruleset. Strategy files lose
their LucidFlex-specific defaults and become generic. New strategies built
after this are born consuming the foundational config correctly.

Read `backend/CLAUDE.md`, `frontend/CLAUDE.md`, and
`Command_Center_Backtest_Engine_Design.md` first.

---

## 0. Communication rules (carried from all prior milestones)

- Plain English replies. No code blocks unless I ask.
- One clear question with concrete options when you need input.
- Update CLAUDE.md in the same session as approved changes.
- This is NOT a new milestone (M5 is reserved for stacking). Call this
  "Pass 1 — Foundational Config" in any commit messages or doc references.

---

## 1. What Pass 1 delivers (acceptance checklist)

- [ ] `rulesets` table gains all foundational config fields (per §2).
- [ ] All existing rulesets (4 LucidFlex rows + the personal example +
  whatever the user has seeded in the meantime) are backfilled with sensible
  foundational values.
- [ ] Each strategy `.cs` file is renamed to drop firm-specific suffixes
  (`ORB_LucidFlex.cs` → `ORB.cs` etc.).
- [ ] Foundational parameters are removed as `[NinjaScriptProperty]` defaults
  from the strategy files. They remain as parameters NinjaScript needs to
  compile, but their values come from the runtime config, not the file's
  defaults.
- [ ] Backend dispatcher in `services/vps_client.py` (or wherever runs the
  backtest) injects foundational values from the active ruleset into the
  strategy_params dict before sending to the VPS agent.
- [ ] Strategy scanner is updated to tag each parameter as either
  `strategy_logic` or `foundational`. Optimizer only exposes `strategy_logic`
  params in the param grid.
- [ ] Daily profit lock-in behavior is implemented: when cumulative day P&L
  hits `lock_pct × target`, risk per trade is halved for the rest of the day.
  One-way ratchet. Resets at start of next day.
- [ ] All existing M1/M2/M3/M4 backtests still work — re-running one against
  LucidFlex produces identical results to pre-Pass 1 (inputs are the same,
  just sourced from the ruleset instead of strategy defaults).
- [ ] Both CLAUDE.md files updated.

---

## 2. Foundational config — fields to add to the rulesets table

### Schema additions

Add these columns to the `rulesets` table:

```sql
-- Capital and risk
ALTER TABLE rulesets ADD COLUMN risk_per_trade_pct REAL;
ALTER TABLE rulesets ADD COLUMN max_consecutive_losses INTEGER;

-- Trading hours and days
ALTER TABLE rulesets ADD COLUMN earliest_entry_time_et TEXT;     -- "HH:MM" format, null = no restriction
ALTER TABLE rulesets ADD COLUMN latest_entry_time_et TEXT;       -- "HH:MM" format, null = no restriction
ALTER TABLE rulesets ADD COLUMN days_of_week_allowed TEXT;        -- JSON array: ["mon","tue","wed","thu","fri"]

-- Daily goals and lock-in
ALTER TABLE rulesets ADD COLUMN daily_profit_target INTEGER;     -- USD, null = no target
ALTER TABLE rulesets ADD COLUMN daily_profit_lock_pct REAL;      -- 0.0-1.0, null = no lock-in

-- Execution (already exist for some; add if missing)
ALTER TABLE rulesets ADD COLUMN default_commission_per_side REAL;
ALTER TABLE rulesets ADD COLUMN default_slippage_ticks INTEGER;
```

Fields that already exist from M3 and don't need re-adding:
- `account_size`
- `daily_loss_cap`
- `weekly_loss_cap`
- `force_flat_time_et`
- `max_contracts` (JSON)
- `min_trading_days`
- `allowed_instruments` (JSON)

### Backfill the existing rulesets

For each existing ruleset, set sensible defaults:

**LucidFlex 50k Eval, LucidFlex 100k Eval, LucidFlex 50k Funded, LucidFlex 100k Funded:**
- `risk_per_trade_pct`: 0.5
- `max_consecutive_losses`: 3
- `earliest_entry_time_et`: "09:30"
- `latest_entry_time_et`: "15:00"
- `days_of_week_allowed`: `["mon","tue","wed","thu","fri"]`
- `daily_profit_target`: $1,500 (eval) / null (funded) — eval has a target,
  funded does not require one
- `daily_profit_lock_pct`: 0.80 (only set if target is set)
- `default_commission_per_side`: 2.25
- `default_slippage_ticks`: 1

**personal_futures_10k_example:**
- `risk_per_trade_pct`: 1.0
- `max_consecutive_losses`: 3
- `earliest_entry_time_et`: "09:30"
- `latest_entry_time_et`: "15:00"
- `days_of_week_allowed`: `["mon","tue","wed","thu","fri"]`
- `daily_profit_target`: 150
- `daily_profit_lock_pct`: 0.80
- `default_commission_per_side`: 2.25
- `default_slippage_ticks`: 1

For any other rulesets the user has seeded since M3, use the LucidFlex eval
defaults as a starting point. The user can adjust later via the UI or DB.

### Validation rules

- `daily_profit_lock_pct` must be between 0.0 and 1.0 if set.
- `daily_profit_lock_pct` is ignored if `daily_profit_target` is null. Add
  a small validator that warns (doesn't fail) if lock_pct is set without
  target.
- `days_of_week_allowed` must be a subset of `["mon","tue","wed","thu","fri","sat","sun"]`.
- Times in `earliest_entry_time_et`, `latest_entry_time_et`, `force_flat_time_et`
  must be valid "HH:MM" in 24-hour format if set.

---

## 3. Strategy file genericization

### What changes per strategy file

For each strategy file (currently `ORB_LucidFlex.cs`, `VWAP_MR_LucidFlex.cs`,
`Momentum_LucidFlex.cs`):

**1. Rename the file:**
- `ORB_LucidFlex.cs` → `ORB.cs`
- `VWAP_MR_LucidFlex.cs` → `VWAP_MR.cs`
- `Momentum_LucidFlex.cs` → `Momentum.cs`

The class name inside also changes (drop `_LucidFlex`).

**2. Strip LucidFlex-specific defaults from foundational parameters.**

Identify parameters in each file that correspond to foundational config
(account size, max daily loss, risk pct, force flat time, etc.). These
parameters STAY in the file (NinjaScript needs them to compile and accept
runtime values) but their default values are removed or set to obviously-
placeholder values like 0 or -1.

The strategy's logic must NOT silently fall back to a default if the runtime
config doesn't provide a value. If the backend dispatcher forgets to inject
something, the strategy should fail loudly, not run with hidden defaults.

**3. Add a tag/category to each NinjaScriptProperty.**

Use the existing NinjaScript `Category` attribute. Two categories:

```csharp
[NinjaScriptProperty]
[Category("Strategy Logic")]
public int ORMinutes { get; set; }    // tunable by optimizer

[NinjaScriptProperty]
[Category("Foundational")]
public int AccountSize { get; set; }   // comes from ruleset
```

The strategy scanner reads these categories. Optimizer UI only shows
"Strategy Logic" params in the param grid. "Foundational" params are
documented but never exposed to the user for tuning.

**4. Add the daily profit lock-in behavior.**

Each strategy needs new internal state and logic:

```csharp
// New internal state
private double _dayStartEquity;
private double _dailyPnl;
private bool _lockInActive;
private double _currentRiskMultiplier;  // 1.0 normally, 0.5 when locked in

// At start of each new day (in OnBarUpdate when date changes):
_dayStartEquity = currentEquity;
_dailyPnl = 0;
_lockInActive = false;
_currentRiskMultiplier = 1.0;

// Before each trade entry, check lock-in:
if (DailyProfitTarget > 0 && DailyProfitLockPct > 0) {
    double lockThreshold = DailyProfitTarget * DailyProfitLockPct;
    if (_dailyPnl >= lockThreshold && !_lockInActive) {
        _lockInActive = true;
        _currentRiskMultiplier = 0.5;
        Print($"Daily profit lock-in activated at ${_dailyPnl}. Risk halved.");
    }
}

// Position sizing uses _currentRiskMultiplier:
double riskDollars = AccountSize * RiskPerTradePct * _currentRiskMultiplier;
```

If `_dailyPnl >= DailyProfitTarget`, stop trading entirely for the day
(separate from lock-in).

Also add the `MaxConsecutiveLosses` check:

```csharp
private int _consecutiveLosses;

// On each trade close:
if (trade.Pnl < 0) _consecutiveLosses++;
else _consecutiveLosses = 0;

// Before entry:
if (MaxConsecutiveLosses > 0 && _consecutiveLosses >= MaxConsecutiveLosses) {
    // Stop trading for the day
    return;
}
```

And `DaysOfWeekAllowed`:

```csharp
// Pass days as a comma-separated string param, parse internally
private bool IsDayAllowed(DateTime date) {
    string today = date.DayOfWeek.ToString().Substring(0, 3).ToLower();
    return DaysOfWeekAllowed.Split(',').Contains(today);
}
```

And `EarliestEntryTime` / `LatestEntryTime`:

```csharp
private bool IsWithinTradingHours(DateTime time) {
    TimeSpan currentTime = time.TimeOfDay;
    TimeSpan earliest = TimeSpan.Parse(EarliestEntryTimeET);
    TimeSpan latest = TimeSpan.Parse(LatestEntryTimeET);
    return currentTime >= earliest && currentTime <= latest;
}
```

These checks gate every entry attempt. If any fails, no trade.

---

## 4. Backend dispatcher — runtime config injection

### Where it lives

`services/vps_client.py` (or equivalent — the module that builds the
backtest request payload before sending to the VPS agent).

### What changes

Currently the dispatcher sends `strategy_params` from the user's request to
the VPS agent. After Pass 1, it merges in foundational config from the
chosen ruleset:

```python
def build_backtest_request(strategy, user_params, ruleset, instrument, ...):
    # User-provided strategy logic params
    final_params = dict(user_params)
    
    # Inject foundational config from the active ruleset
    final_params.update({
        "AccountSize": ruleset.account_size,
        "RiskPerTradePct": ruleset.risk_per_trade_pct,
        "MaxDailyLoss": ruleset.daily_loss_cap,
        "MaxConsecutiveLosses": ruleset.max_consecutive_losses,
        "EarliestEntryTimeET": ruleset.earliest_entry_time_et,
        "LatestEntryTimeET": ruleset.latest_entry_time_et,
        "ForceFlatTimeET": ruleset.force_flat_time_et,
        "DaysOfWeekAllowed": ",".join(ruleset.days_of_week_allowed),
        "DailyProfitTarget": ruleset.daily_profit_target or 0,
        "DailyProfitLockPct": ruleset.daily_profit_lock_pct or 0.0,
        "CommissionPerSide": ruleset.default_commission_per_side,
        "SlippageTicks": ruleset.default_slippage_ticks,
    })
    
    return BacktestRequest(
        strategy_class=strategy.class_name,
        strategy_params=final_params,
        ...
    )
```

User-provided params (the strategy logic ones from the optimizer or backtest
modal) override foundational params if there's a name collision — but with
the Category-based tagging, the UI prevents the user from specifying
foundational params in the first place.

### Edge case: multi-ruleset evaluation

When a single backtest run is evaluated against multiple rulesets (the
existing M1 "one backtest, N verdicts" pattern), foundational config from
the PRIMARY ruleset gets injected. Other rulesets are only used for
evaluation, not for runtime injection. **The primary ruleset is whichever
the user selected in the Run Backtest modal.**

Document this clearly in `backend/CLAUDE.md`. Users can't run "the same
backtest against LucidFlex AND Apex simultaneously with both rulesets'
hours" — they'd run two separate backtests, each with the appropriate
foundational config.

---

## 5. Strategy scanner update

`services/strategy_scanner.py` (or wherever the scanner lives) reads the
NinjaScript `Category` attribute and tags each param:

```python
# In the scanner output:
{
    "param_name": "ORMinutes",
    "param_type": "int",
    "default": 15,
    "range": [5, 60],
    "category": "strategy_logic"   # or "foundational"
}
```

The frontend uses `category` to decide whether to show the param in the
Backtest Modal's "Parameters" section. Foundational params are hidden.

The Optimize Modal also reads category — only `strategy_logic` params get
the optimization grid UI.

---

## 6. Frontend changes

### Backtest Modal

- "Parameters" section only shows `strategy_logic` params.
- A new readonly "Foundational config (from ruleset)" section shows the
  injected values for transparency. Read-only display. User can see what
  account size, risk pct, hours, etc. will be applied — but can't change
  them here. To change them, they edit the ruleset.

### Optimize Modal

- Param grid only includes `strategy_logic` params.
- Same readonly section showing foundational config.

### Ruleset Detail / Edit page

- New form fields for the new foundational config fields.
- Grouped into sections matching the schema groups (Capital, Hours,
  Daily Goals, Execution).
- Validation: lock_pct between 0-1, times in HH:MM, days subset of valid.

---

## 7. Backend file changes (additions and updates)

```
backend/
├── routers/
│   └── rulesets.py            ← Update: add new fields to schema + validation
├── services/
│   ├── vps_client.py          ← Update: inject foundational from ruleset
│   ├── strategy_scanner.py    ← Update: read Category attribute
│   ├── lab_db.py              ← Update: schema migration + backfill
│   └── (existing)
└── (existing)
```

---

## 8. Strategy file changes

```
ninjascript/strategies/                         ← or wherever they live on VPS
├── ORB.cs                                       ← renamed from ORB_LucidFlex.cs
├── VWAP_MR.cs                                   ← renamed from VWAP_MR_LucidFlex.cs
└── Momentum.cs                                  ← renamed from Momentum_LucidFlex.cs
```

Each file gets the changes per §3.

After the rename, re-deploy to VPS. Recompile in NT8. The old class names
won't exist anymore — any existing backtest registered against `ORB_LucidFlex`
needs its `class_name` field updated to `ORB`. This is a one-time
migration in the strategies table.

---

## 9. Build order

Strict. Stop and report after each:

1. **Schema migration + backfill.** Add the new columns to rulesets table.
   Backfill all existing rulesets with sensible defaults per §2. Verify
   the migration works on a copy of `lab.db` before committing.

2. **One strategy at a time — start with ORB.** Rename the file, strip
   defaults, add Category attributes, add the new behavioral logic
   (lock-in, max consecutive losses, day-of-week, hours). Compile in
   NT8 on the VPS. Verify it runs without errors.

3. **Update the strategy scanner** to read Category attributes. Re-scan
   ORB. Verify the scanner output correctly tags `strategy_logic` vs
   `foundational` params.

4. **Update the backend dispatcher** to inject foundational config from
   the active ruleset. Smoke test: run a backtest with ORB on MNQ against
   LucidFlex 50k Eval. The result should match a pre-Pass-1 backtest of
   the same configuration. **If results differ, something is wrong with
   the injection — debug before continuing.**

5. **Update the frontend** to hide foundational params from the Backtest
   Modal and Optimize Modal, and to show the readonly "Foundational config"
   section. Update the Ruleset Detail page to expose the new fields for
   editing.

6. **Repeat steps 2 for VWAP_MR and Momentum.** Same rename, same
   Category tagging, same behavioral additions.

7. **End-to-end test.** Run each of the three strategies against LucidFlex
   50k Eval and against `personal_futures_10k_example`. Verify:
   - Backtests run successfully against both rulesets
   - Results differ between the two rulesets (because account size, risk
     pct, etc. differ)
   - Lock-in behavior triggers when daily P&L crosses `lock_pct × target`
   - Max consecutive losses stops trading after threshold
   - Day-of-week filter excludes weekend trades (if any)
   - Hours filter excludes pre/post-market trades

8. **Update CLAUDE.md files.** Document the foundational config layer,
   the Category-based scanning, the dispatcher injection pattern, and
   the lock-in behavior.

After step 8, stop. Bring me back:
- Confirmation all three strategies run cleanly against both rulesets
- A screenshot of the new readonly foundational config section in the
  Backtest Modal
- A screenshot of the Ruleset Detail page showing the new editable fields
- Anything that felt wrong, slow, or surprising

---

## 10. What NOT to do in Pass 1

- Don't add news blackout windows. Deferred.
- Don't add dynamic risk scaling beyond the simple lock-in (50% halving).
  More complex scaling is M6's job.
- Don't change M4's regime classification logic. Pass 1 is orthogonal to
  regime work.
- Don't try to handle "trailing stop" or other strategy-specific mechanics
  in foundational config. Those stay strategy-level.
- Don't auto-fill the daily profit target for personal rulesets. It's
  optional — the user sets it themselves on a per-ruleset basis.
- Don't change the optimizer's regime filter behavior. That's M4 territory.

---

## 11. Update CLAUDE.md at the end

**backend/CLAUDE.md additions:**
- The foundational config layer: which fields, what they mean, where they
  come from (ruleset)
- The Category-based parameter tagging convention
- The dispatcher injection pattern in `vps_client.py`
- The "primary ruleset" rule for multi-ruleset evaluation
- Schema additions to `rulesets` table

**frontend/CLAUDE.md additions:**
- Readonly "Foundational config" section in Backtest Modal and Optimize Modal
- Updated Ruleset Detail / Edit page with the new fields
- Validation rules for the new fields

**Design doc** (`Command_Center_Backtest_Engine_Design.md`):
- Add a "Pass 1 — Foundational Config" section to the retrospective
- Note that strategies are now generic; class names no longer reference firms
- Note the Category-based scanning model

---

## End of Pass 1 spec

After Pass 1 ships:
- All three existing strategies are generic
- The same `.cs` file runs against any ruleset with the right config
  injected at runtime
- New strategies you write from now on are born generic — no LucidFlex
  defaults to strip out later
- Daily profit lock-in is implemented as a foundational behavior
- The platform is ready for the next phase: strategy improvements (regime
  filter on ORB, then full pipeline re-validation)
