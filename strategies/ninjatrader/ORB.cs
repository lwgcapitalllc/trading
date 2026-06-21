// Opening Range Breakout
//
// Strategy logic:
//   OR period  : first ORMinutes of session starting 09:30 ET (wick-to-wick high/low)
//   Long entry : a BULLISH body closes above OR high. The break candle does not
//                count on its own (it can reverse like a wick) — ConfirmationCloses
//                more consecutive bullish closes must follow. 0 = enter on the break.
//   Short entry: mirror — bearish body closes below OR low + confirmations
//   Stop       : opposite (far) side of OR
//   Target     : entry ± RiskReward × stop distance (true R:R, default 1:2)
//   One long + one short per day (or one total if OneTradePer = true)
//
// Gated-layer rules (docs/LWG_Strategy_Framework.md, docs/dynamic_sizing_engine.md):
//   NO STRATEGY KNOWS HOW TO MANAGE RISK. ORB proposes setups at UNIT size (1 contract).
//   It does NOT size, halt on losses, stop at a profit target, lock in profit, or count
//   consecutive losses — those decisions belong to the dynamic sizing & gating engine,
//   which sizes and grades the run OFFLINE from the per-trade record this strategy emits.
//
//   ORB keeps only what is part of its edge: the entry signal, the stop, the target, and
//   the time rules that define WHEN the setup is valid (force-flat, entry hours, allowed
//   days). It emits one row per closed trade — the runner→engine contract — to
//   engine_trades.csv: index, entry/exit time + price, direction, stop_distance,
//   point_value, commission_per_side, exit_reason. The NT8 agent ships that file; the
//   engine (services/sizing_engine.py via sizing_pipeline.py) reads it and decides size.
//
//   strategy_results.csv is still written, but it is now a UNIT-SIZE (1-contract) raw
//   reference only — the engine's sized daily P&L is authoritative for grading.
//
// Foundational config (commission, hours, allowed days) is injected at runtime from the
// active ruleset. Placeholder defaults (-1 / empty string) cause the strategy to refuse all
// trades rather than silently use wrong values.
//
// Install: copy to Documents/NinjaTrader 8/bin/Custom/Strategies/
//          Compile in NT8 (F5), then attach in Strategy Analyzer.

#region Using declarations
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Globalization;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class ORB : Strategy
    {
        // ── Foundational parameters (injected from active ruleset at runtime) ──
        // Only cost + time facts remain. Account size, risk %, daily-loss, profit-target,
        // halt-fraction, lock-in and consecutive-loss params were removed — the engine owns
        // every one of those decisions now (see header).

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Commission/Side ($)", Order = 1)]
        public double CommissionPerSide { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Force Flat Time ET (HH:MM)", Order = 2)]
        public string ForceFlatTimeET { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Earliest Entry Time ET (HH:MM, empty = none)", Order = 3)]
        public string EarliestEntryTimeET { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Latest Entry Time ET (HH:MM, empty = none)", Order = 4)]
        public string LatestEntryTimeET { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Days of Week Allowed (mon,tue,...  empty = all)", Order = 5)]
        public string DaysOfWeekAllowed { get; set; }

        // ── Strategy Logic parameters (tunable by optimizer) ─────────────────

        [NinjaScriptProperty]
        [Range(5, 60)]
        [Category("Strategy Logic")]
        [Display(Name = "Opening Range Minutes", Order = 1)]
        public int ORMinutes { get; set; }

        [NinjaScriptProperty]
        [Range(0.5, 5.0)]
        [Category("Strategy Logic")]
        [Display(Name = "Risk : Reward (× stop distance)", Order = 2)]
        public double RiskReward { get; set; }

        [NinjaScriptProperty]
        [Range(0, 5)]
        [Category("Strategy Logic")]
        [Display(Name = "Confirmation Closes (after break)", Order = 3)]
        public int ConfirmationCloses { get; set; }

        [NinjaScriptProperty]
        [Category("Strategy Logic")]
        [Display(Name = "One Trade Per Day (long OR short)", Order = 4)]
        public bool OneTradePer { get; set; }

        // Every proposed trade is exactly this size. The engine resizes offline.
        private const int UnitSize = 1;

        // ── Intraday state ────────────────────────────────────────────────────

        private double   orHigh, orLow;
        private bool     orSet;
        private bool     longDone, shortDone;
        private int      buyCloses, sellCloses;
        private bool     dayAllowed;
        private DateTime currentDay = DateTime.MinValue;

        // ── Open-trade tracking (to build the per-trade record on exit) ───────

        private double   pendingEntryPrice;
        private DateTime pendingEntryTime;
        private double   pendingStopPrice;
        private int      pendingQty;
        private int      pendingDir;

        // ── Per-trade record rows (the runner→engine contract) ────────────────

        private readonly List<string> tradeRows = new List<string>();
        private int recordIndex;

        // ── Unit-size performance accumulators (strategy_results.csv only) ────

        private double cumulativePnl;
        private double peakPnl;
        private double maxDrawdown;
        private double grossWins;
        private double grossLosses;
        private int    winCount;
        private int    tradeCount;

        // ── Cached time boundaries ─────────────────────────────────────────────

        private TimeSpan tSessionOpen;
        private TimeSpan tOrEnd;
        private TimeSpan tForceFlat;
        private TimeSpan tEarliestEntry;
        private TimeSpan tLatestEntry;
        private bool     _hasEarliestEntry;
        private bool     _hasLatestEntry;
        private bool     _configValid;

        // ─────────────────────────────────────────────────────────────────────

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description                  = "Opening Range Breakout (unit size; engine sizes & grades)";
                Name                         = "ORB";
                Calculate                    = Calculate.OnBarClose;
                IsExitOnSessionCloseStrategy = false;
                BarsRequiredToTrade          = 1;
                EntriesPerDirection          = 1;
                EntryHandling                = EntryHandling.UniqueEntries;

                // Foundational — placeholder values. Dispatcher injects from active ruleset.
                // Strategy refuses to trade if required fields remain at placeholder values.
                CommissionPerSide   = -1;
                ForceFlatTimeET     = "";
                EarliestEntryTimeET = "";     // empty = no restriction
                LatestEntryTimeET   = "";     // empty = no restriction
                DaysOfWeekAllowed   = "";     // empty = all days allowed

                // Strategy logic — real defaults used by optimizer
                ORMinutes          = 15;
                RiskReward         = 2.0;
                ConfirmationCloses = 1;
                OneTradePer        = false;
            }
            else if (State == State.Configure)
            {
                _configValid = ValidateConfig();
                if (!_configValid) return;

                tSessionOpen = new TimeSpan(9, 30, 0);
                tOrEnd       = tSessionOpen.Add(TimeSpan.FromMinutes(ORMinutes));
                tForceFlat   = TimeSpan.Parse(ForceFlatTimeET);

                _hasEarliestEntry = !string.IsNullOrWhiteSpace(EarliestEntryTimeET);
                _hasLatestEntry   = !string.IsNullOrWhiteSpace(LatestEntryTimeET);
                if (_hasEarliestEntry) tEarliestEntry = TimeSpan.Parse(EarliestEntryTimeET);
                if (_hasLatestEntry)   tLatestEntry   = TimeSpan.Parse(LatestEntryTimeET);
            }
            else if (State == State.Terminated)
            {
                WriteTradeRecords();
                WriteSummary();
            }
        }

        private bool ValidateConfig()
        {
            if (CommissionPerSide < 0)
            {
                Print("ORB: CommissionPerSide not injected by dispatcher — no trades will be placed.");
                return false;
            }
            if (string.IsNullOrWhiteSpace(ForceFlatTimeET))
            {
                Print("ORB: ForceFlatTimeET not injected by dispatcher — no trades will be placed.");
                return false;
            }
            return true;
        }

        protected override void OnBarUpdate()
        {
            if (!_configValid) return;
            if (BarsInProgress != 0) return;

            TimeSpan tod     = Time[0].TimeOfDay;
            DateTime barDate = Time[0].Date;

            // ── Day boundary ───────────────────────────────────────────────────
            if (barDate != currentDay)
            {
                currentDay = barDate;
                orHigh     = double.MinValue;
                orLow      = double.MaxValue;
                orSet      = false;
                longDone   = false;
                shortDone  = false;
                buyCloses  = 0;
                sellCloses = 0;

                dayAllowed = IsDayAllowed(barDate);
            }

            if (!dayAllowed) return;

            // ── Force flat (intraday-only rule — part of the setup, kept) ──────
            if (tod >= tForceFlat)
            {
                if (Position.MarketPosition != MarketPosition.Flat)
                {
                    ExitLong("ForceFlat",  "ORB_Long");
                    ExitShort("ForceFlat", "ORB_Short");
                }
                return;
            }

            // ── Accumulate opening range ───────────────────────────────────────
            if (tod >= tSessionOpen && tod < tOrEnd)
            {
                orHigh = Math.Max(orHigh, High[0]);
                orLow  = Math.Min(orLow,  Low[0]);
                return;
            }

            // ── Finalise OR on first bar after OR period ───────────────────────
            if (!orSet)
            {
                if (tod >= tOrEnd && orHigh > orLow) orSet = true;
                else return;
            }

            // Entry hours gate (part of the setup window — kept)
            if (_hasEarliestEntry && tod < tEarliestEntry) return;
            if (_hasLatestEntry   && tod > tLatestEntry)   return;

            if (Position.MarketPosition != MarketPosition.Flat) return;

            double close = Close[0];
            double open  = Open[0];

            // Confirmation count — a BODY must close beyond the range IN the trade's
            // direction. The first such close is the break candle; on its own it can
            // reverse like a wick, so it does not qualify. We need ConfirmationCloses
            // more consecutive direction-matched closes after it (needCloses total).
            // Any non-confirming bar resets that side's count.
            bool bullClose = close > orHigh && close > open;   // bullish body above OR high
            bool bearClose = close < orLow  && close < open;   // bearish body below OR low
            buyCloses  = bullClose ? buyCloses  + 1 : 0;
            sellCloses = bearClose ? sellCloses + 1 : 0;
            int needCloses = ConfirmationCloses + 1;           // +1 = the break candle, which doesn't count

            // ── Long breakout ──────────────────────────────────────────────────
            if (!longDone && buyCloses >= needCloses)
            {
                longDone = true;
                if (!(OneTradePer && shortDone))
                {
                    double stop = orLow;                       // far side of the range
                    double risk = close - stop;
                    if (risk > 0)
                    {
                        double target = close + RiskReward * risk;
                        SetStopLoss("ORB_Long",     CalculationMode.Price, stop,   false);
                        SetProfitTarget("ORB_Long", CalculationMode.Price, target);
                        EnterLong(0, UnitSize, "ORB_Long");
                        pendingDir       = 1;
                        pendingQty       = UnitSize;
                        pendingStopPrice = stop;
                    }
                }
            }
            // ── Short breakout ─────────────────────────────────────────────────
            else if (!shortDone && sellCloses >= needCloses)
            {
                shortDone = true;
                if (!(OneTradePer && longDone))
                {
                    double stop = orHigh;                      // far side of the range
                    double risk = stop - close;
                    if (risk > 0)
                    {
                        double target = close - RiskReward * risk;
                        SetStopLoss("ORB_Short",     CalculationMode.Price, stop,   false);
                        SetProfitTarget("ORB_Short", CalculationMode.Price, target);
                        EnterShort(0, UnitSize, "ORB_Short");
                        pendingDir       = -1;
                        pendingQty       = UnitSize;
                        pendingStopPrice = stop;
                    }
                }
            }
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId,
            double price, int quantity, MarketPosition marketPosition,
            string orderId, DateTime time)
        {
            if (execution.Order == null) return;

            switch (execution.Order.OrderAction)
            {
                case OrderAction.Buy:
                case OrderAction.SellShort:
                    pendingEntryPrice = price;
                    pendingEntryTime  = time;
                    break;

                case OrderAction.Sell:
                case OrderAction.BuyToCover:
                    if (pendingEntryPrice > 0 && pendingQty > 0)
                    {
                        double pv         = Instrument.MasterInstrument.PointValue;
                        double stopDist   = Math.Abs(pendingEntryPrice - pendingStopPrice);
                        string exitReason = execution.Order.Name;

                        RecordTrade(pendingEntryTime, time, pendingDir,
                                    pendingEntryPrice, price, stopDist, pv, exitReason);

                        // Unit-size P&L — strategy_results.csv reference only, drives nothing.
                        double gross    = (price - pendingEntryPrice) * pendingDir * quantity * pv;
                        double costs    = CommissionPerSide * 2 * quantity;
                        double tradePnl  = gross - costs;
                        cumulativePnl  += tradePnl;

                        tradeCount++;
                        if (tradePnl > 0) { grossWins += tradePnl; winCount++; }
                        else              { grossLosses += tradePnl; }

                        if (cumulativePnl > peakPnl) peakPnl = cumulativePnl;
                        double dd = peakPnl - cumulativePnl;
                        if (dd > maxDrawdown) maxDrawdown = dd;

                        pendingEntryPrice = 0;
                        pendingQty        = 0;
                        pendingDir        = 0;
                        pendingStopPrice  = 0;
                    }
                    break;
            }
        }

        // Append one row to the per-trade record (the runner→engine contract).
        // Columns: index,entry_time,exit_time,direction,entry_price,exit_price,
        //          stop_distance,point_value,commission_per_side,exit_reason
        private void RecordTrade(DateTime entryTime, DateTime exitTime, int dir,
            double entryPrice, double exitPrice, double stopDist, double pointValue,
            string exitReason)
        {
            recordIndex++;
            string row = string.Format(CultureInfo.InvariantCulture,
                "{0},{1},{2},{3},{4},{5},{6},{7},{8},\"{9}\"\r\n",
                recordIndex,
                entryTime.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture),
                exitTime.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture),
                dir == 1 ? "Long" : "Short",
                entryPrice, exitPrice, stopDist, pointValue, CommissionPerSide,
                (exitReason ?? "").Replace("\"", "'"));
            tradeRows.Add(row);
        }

        // Write the per-trade record file the engine consumes. Mirrors the strategy_results.csv
        // pattern: header written once if the file is absent, rows appended. The NT8 agent
        // clears engine_trades.csv before each run and ships it after (single instrument/run).
        private void WriteTradeRecords()
        {
            if (tradeRows.Count == 0) return;
            try
            {
                string dir  = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "NinjaTrader 8");
                string path = Path.Combine(dir, "engine_trades.csv");

                if (!File.Exists(path))
                    File.WriteAllText(path,
                        "index,entry_time,exit_time,direction,entry_price,exit_price," +
                        "stop_distance,point_value,commission_per_side,exit_reason\r\n");

                StringBuilder sb = new StringBuilder();
                foreach (string r in tradeRows) sb.Append(r);
                File.AppendAllText(path, sb.ToString());
            }
            catch { }
        }

        // Unit-size run summary — reference only. The engine's sized run is authoritative.
        private void WriteSummary()
        {
            try
            {
                double net    = grossWins + grossLosses;
                double pf     = grossLosses != 0 ? grossWins / Math.Abs(grossLosses) : 0;
                double winPct = tradeCount > 0 ? (double)winCount / tradeCount * 100.0 : 0;

                string dir  = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "NinjaTrader 8");
                string path = Path.Combine(dir, "strategy_results.csv");

                if (!File.Exists(path))
                    File.WriteAllText(path,
                        "Strategy,Instrument,NetPnL,MaxDD,ProfitFactor,WinPct,Trades\r\n");

                File.AppendAllText(path, string.Format(CultureInfo.InvariantCulture,
                    "{0},{1},{2:F2},{3:F2},{4:F4},{5:F1},{6}\r\n",
                    Name, Instrument.MasterInstrument.Name,
                    net, maxDrawdown, pf, winPct, tradeCount));
            }
            catch { }
        }

        // Returns true if trading is allowed on the given date.
        // An empty DaysOfWeekAllowed string means all days are permitted.
        private bool IsDayAllowed(DateTime date)
        {
            if (string.IsNullOrWhiteSpace(DaysOfWeekAllowed)) return true;
            string today = date.DayOfWeek.ToString().Substring(0, 3).ToLower();
            return DaysOfWeekAllowed.Split(',').Any(d => d.Trim() == today);
        }
    }
}
