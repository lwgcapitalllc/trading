// VWAP Mean Reversion
//
// Strategy logic:
//   Session-cumulative VWAP + volume-weighted std dev reset at 09:30 each day
//   Long signal : close < VWAP - EntryStd × σ   (stretched below)
//   Short signal: close > VWAP + EntryStd × σ   (stretched above)
//   Stop        : close ∓ StopExtension × σ      (further from VWAP)
//   Target      : close + TpFraction × (VWAP - close)  (fraction back to VWAP)
//   One trade per direction per day
//   Skip first MinBarsBeforeEntry bars of each session (VWAP needs time to stabilise)
//
// Foundational config (account size, risk, halt rules, hours) is injected at
// runtime from the active ruleset. Placeholder defaults (-1 / empty string)
// cause the strategy to refuse all trades rather than silently use wrong values.
//
// Install: copy to Documents/NinjaTrader 8/bin/Custom/Strategies/
//          Compile in NT8 (F5), then attach in Strategy Analyzer.

#region Using declarations
using System;
using System.IO;
using System.Linq;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class VWAP_MR : Strategy
    {
        // ── Foundational parameters (injected from active ruleset at runtime) ──

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Account Size ($)", Order = 1)]
        public double AccountSize { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Risk % per Trade", Order = 2)]
        public double RiskPerTradePct { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Max Daily Loss ($)", Order = 3)]
        public double MaxDailyLoss { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Daily Halt Fraction (0 = off)", Order = 4)]
        public double DailyHaltFraction { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Commission/Side ($)", Order = 5)]
        public double CommissionPerSide { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Force Flat Time ET (HH:MM)", Order = 6)]
        public string ForceFlatTimeET { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Max Consecutive Losses (0 = off)", Order = 7)]
        public int MaxConsecutiveLosses { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Earliest Entry Time ET (HH:MM, empty = none)", Order = 8)]
        public string EarliestEntryTimeET { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Latest Entry Time ET (HH:MM, empty = none)", Order = 9)]
        public string LatestEntryTimeET { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Days of Week Allowed (mon,tue,...  empty = all)", Order = 10)]
        public string DaysOfWeekAllowed { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Daily Profit Target ($, 0 = none)", Order = 11)]
        public double DailyProfitTarget { get; set; }

        [NinjaScriptProperty]
        [Category("Foundational")]
        [Display(Name = "Daily Profit Lock-In Pct (0 = off)", Order = 12)]
        public double DailyProfitLockPct { get; set; }

        // ── Strategy Logic parameters (tunable by optimizer) ─────────────────

        [NinjaScriptProperty]
        [Range(0.5, 5.0)]
        [Category("Strategy Logic")]
        [Display(Name = "Entry Std Dev Multiplier", Order = 1)]
        public double EntryStd { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 3.0)]
        [Category("Strategy Logic")]
        [Display(Name = "Stop Extension (× σ)", Order = 2)]
        public double StopExtension { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 2.0)]
        [Category("Strategy Logic")]
        [Display(Name = "TP Fraction (back to VWAP)", Order = 3)]
        public double TpFraction { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Category("Strategy Logic")]
        [Display(Name = "Min Bars Before Entry", Order = 4)]
        public int MinBarsBeforeEntry { get; set; }

        // ── Intraday state ────────────────────────────────────────────────────

        private bool     longDone, shortDone;
        private bool     tradingHalted;
        private bool     dayAllowed;
        private DateTime currentDay = DateTime.MinValue;
        private int      sessionBarCount;

        // Running cumulative sums for VWAP + σ (reset each day)
        private double cumTpv;    // Σ(tp × vol)
        private double cumVol;    // Σ(vol)
        private double cumTp2v;   // Σ(tp² × vol)

        // ── P&L tracking ──────────────────────────────────────────────────────

        private double cumulativePnl;
        private double dayStartPnl;
        private double pendingEntryPrice;
        private int    pendingQty;
        private int    pendingDir;

        // ── Lock-in and consecutive loss state ────────────────────────────────

        private bool   _lockInActive;
        private double _currentRiskMultiplier;
        private int    _consecutiveLosses;

        // ── Performance accumulators ──────────────────────────────────────────

        private double peakEquity;
        private double maxDrawdown;
        private double grossWins;
        private double grossLosses;
        private int    winCount;
        private int    tradeCount;

        // ── Cached time boundaries ─────────────────────────────────────────────

        private TimeSpan tSessionOpen;
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
                Description                  = "VWAP Mean Reversion";
                Name                         = "VWAP_MR";
                Calculate                    = Calculate.OnBarClose;
                IsExitOnSessionCloseStrategy = false;
                BarsRequiredToTrade          = 1;
                EntriesPerDirection          = 1;
                EntryHandling                = EntryHandling.UniqueEntries;

                // Foundational — placeholder values. Dispatcher injects from active ruleset.
                AccountSize          = -1;
                RiskPerTradePct      = -1;
                MaxDailyLoss         = -1;
                DailyHaltFraction    = 0;
                CommissionPerSide    = -1;
                ForceFlatTimeET      = "";
                MaxConsecutiveLosses = 0;
                EarliestEntryTimeET  = "";
                LatestEntryTimeET    = "";
                DaysOfWeekAllowed    = "";
                DailyProfitTarget    = 0;
                DailyProfitLockPct   = 0;

                // Strategy logic — real defaults used by optimizer
                EntryStd         = 2.0;
                StopExtension    = 1.0;
                TpFraction       = 1.0;
                MinBarsBeforeEntry = 20;
            }
            else if (State == State.Configure)
            {
                _configValid = ValidateConfig();
                if (!_configValid) return;

                tSessionOpen = new TimeSpan(9, 30, 0);
                tForceFlat   = TimeSpan.Parse(ForceFlatTimeET);

                _hasEarliestEntry = !string.IsNullOrWhiteSpace(EarliestEntryTimeET);
                _hasLatestEntry   = !string.IsNullOrWhiteSpace(LatestEntryTimeET);
                if (_hasEarliestEntry) tEarliestEntry = TimeSpan.Parse(EarliestEntryTimeET);
                if (_hasLatestEntry)   tLatestEntry   = TimeSpan.Parse(LatestEntryTimeET);

                peakEquity = AccountSize;
            }
            else if (State == State.Terminated)
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

                    File.AppendAllText(path, string.Format(
                        "{0},{1},{2:F2},{3:F2},{4:F4},{5:F1},{6}\r\n",
                        Name, Instrument.MasterInstrument.Name,
                        net, maxDrawdown, pf, winPct, tradeCount));
                }
                catch { }
            }
        }

        private bool ValidateConfig()
        {
            if (AccountSize <= 0)
            {
                Print("VWAP_MR: AccountSize not injected by dispatcher — no trades will be placed.");
                return false;
            }
            if (RiskPerTradePct <= 0)
            {
                Print("VWAP_MR: RiskPerTradePct not injected by dispatcher — no trades will be placed.");
                return false;
            }
            if (MaxDailyLoss <= 0)
            {
                Print("VWAP_MR: MaxDailyLoss not injected by dispatcher — no trades will be placed.");
                return false;
            }
            if (CommissionPerSide < 0)
            {
                Print("VWAP_MR: CommissionPerSide not injected by dispatcher — no trades will be placed.");
                return false;
            }
            if (string.IsNullOrWhiteSpace(ForceFlatTimeET))
            {
                Print("VWAP_MR: ForceFlatTimeET not injected by dispatcher — no trades will be placed.");
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
                currentDay             = barDate;
                longDone               = false;
                shortDone              = false;
                tradingHalted          = false;
                sessionBarCount        = 0;
                cumTpv                 = 0;
                cumVol                 = 0;
                cumTp2v                = 0;
                dayStartPnl            = cumulativePnl;
                _lockInActive          = false;
                _currentRiskMultiplier = 1.0;
                _consecutiveLosses     = 0;

                dayAllowed = IsDayAllowed(barDate);
            }

            if (!dayAllowed) return;

            // ── Force flat ─────────────────────────────────────────────────────
            if (tod >= tForceFlat)
            {
                if (Position.MarketPosition != MarketPosition.Flat)
                {
                    ExitLong("ForceFlat",  "VWAP_Long");
                    ExitShort("ForceFlat", "VWAP_Short");
                }
                return;
            }

            // Only process bars inside the session
            if (tod < tSessionOpen) return;

            // ── Update running VWAP accumulators ───────────────────────────────
            double tp  = (High[0] + Low[0] + Close[0]) / 3.0;
            double vol = Math.Max(Volume[0], 1.0);
            cumTpv  += tp * vol;
            cumVol  += vol;
            cumTp2v += tp * tp * vol;
            sessionBarCount++;

            if (sessionBarCount <= MinBarsBeforeEntry) return;

            double vwap     = cumTpv / cumVol;
            double variance = Math.Max(0.0, cumTp2v / cumVol - vwap * vwap);
            double sigma    = Math.Sqrt(variance);

            if (sigma <= 0) return;

            if (tradingHalted) return;

            double dayPnl = cumulativePnl - dayStartPnl;

            // Daily profit target reached
            if (DailyProfitTarget > 0 && dayPnl >= DailyProfitTarget) return;

            // Entry hours gate
            if (_hasEarliestEntry && tod < tEarliestEntry) return;
            if (_hasLatestEntry   && tod > tLatestEntry)   return;

            // Consecutive loss halt
            if (MaxConsecutiveLosses > 0 && _consecutiveLosses >= MaxConsecutiveLosses) return;

            // Fraction-of-daily-loss halt
            if (DailyHaltFraction > 0)
            {
                double dayLoss = dayStartPnl - cumulativePnl;
                if (dayLoss >= MaxDailyLoss * DailyHaltFraction)
                {
                    tradingHalted = true;
                    return;
                }
            }

            // Daily profit lock-in
            if (DailyProfitTarget > 0 && DailyProfitLockPct > 0 && !_lockInActive)
            {
                if (dayPnl >= DailyProfitLockPct * DailyProfitTarget)
                {
                    _lockInActive          = true;
                    _currentRiskMultiplier = 0.5;
                    Print($"VWAP_MR: Profit lock-in active at ${dayPnl:F2}. Risk halved for rest of day.");
                }
            }

            if (Position.MarketPosition != MarketPosition.Flat) return;

            double close = Close[0];

            // ── Long signal: close stretched below VWAP ────────────────────────
            if (!longDone && close < vwap - EntryStd * sigma)
            {
                longDone = true;
                double stop   = close - StopExtension * sigma;
                double target = close + TpFraction * (vwap - close);
                double dist   = close - stop;

                if (dist > 0 && target > close)
                {
                    int qty = CalcContracts(dist);
                    if (qty >= 1)
                    {
                        SetStopLoss("VWAP_Long",    CalculationMode.Price, stop,   false);
                        SetProfitTarget("VWAP_Long", CalculationMode.Price, target);
                        EnterLong(0, qty, "VWAP_Long");
                        pendingDir = 1;
                        pendingQty = qty;
                    }
                }
            }

            // ── Short signal: close stretched above VWAP ───────────────────────
            if (!shortDone && close > vwap + EntryStd * sigma)
            {
                shortDone = true;
                double stop   = close + StopExtension * sigma;
                double target = close + TpFraction * (vwap - close);
                double dist   = stop - close;

                if (dist > 0 && target < close)
                {
                    int qty = CalcContracts(dist);
                    if (qty >= 1)
                    {
                        SetStopLoss("VWAP_Short",    CalculationMode.Price, stop,   false);
                        SetProfitTarget("VWAP_Short", CalculationMode.Price, target);
                        EnterShort(0, qty, "VWAP_Short");
                        pendingDir = -1;
                        pendingQty = qty;
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
                    break;

                case OrderAction.Sell:
                case OrderAction.BuyToCover:
                    if (pendingEntryPrice > 0 && pendingQty > 0)
                    {
                        double pv    = Instrument.MasterInstrument.PointValue;
                        int    dir   = execution.Order.OrderAction == OrderAction.Sell ? 1 : -1;
                        double gross = (price - pendingEntryPrice) * dir * quantity * pv;
                        double costs = CommissionPerSide * 2 * quantity;
                        double tradePnl   = gross - costs;
                        cumulativePnl    += tradePnl;
                        pendingEntryPrice  = 0;
                        pendingQty         = 0;
                        pendingDir         = 0;

                        tradeCount++;
                        if (tradePnl > 0)
                        {
                            grossWins += tradePnl;
                            winCount++;
                            _consecutiveLosses = 0;
                        }
                        else
                        {
                            grossLosses += tradePnl;
                            _consecutiveLosses++;
                        }

                        double equity = AccountSize + cumulativePnl;
                        if (equity > peakEquity) peakEquity = equity;
                        double dd = peakEquity - equity;
                        if (dd > maxDrawdown) maxDrawdown = dd;
                    }
                    break;
            }
        }

        private bool IsDayAllowed(DateTime date)
        {
            if (string.IsNullOrWhiteSpace(DaysOfWeekAllowed)) return true;
            string today = date.DayOfWeek.ToString().Substring(0, 3).ToLower();
            return DaysOfWeekAllowed.Split(',').Any(d => d.Trim() == today);
        }

        private int CalcContracts(double stopDistPoints)
        {
            if (stopDistPoints <= 0) return 0;
            double equity     = AccountSize + cumulativePnl;
            double dollarRisk = equity * (RiskPerTradePct / 100.0) * _currentRiskMultiplier;
            double pv         = Instrument.MasterInstrument.PointValue;
            return Math.Max(0, (int)(dollarRisk / (stopDistPoints * pv)));
        }
    }
}
