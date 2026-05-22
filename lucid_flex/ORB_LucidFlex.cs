// Opening Range Breakout — LucidFlex Prop Firm
//
// Rules:
//   OR period  : 09:30–09:45 ET (first ORMinutes of session)
//   Long entry : first bar closing above OR high after OR is set
//   Short entry: first bar closing below OR low after OR is set
//   Stop       : opposite side of OR
//   Target     : OR high/low ± TpMultiple × OR width
//   One long + one short allowed per day (or one total if OneTradePer = true)
//   Force flat : 15:30 ET
//   Daily halt : suspend new entries once day loss ≥ DailyHaltFraction × MaxDailyLoss
//
// Install: copy to Documents/NinjaTrader 8/bin/Custom/Strategies/
//          Compile in NT8 (F5), then attach in Strategy Analyzer.

#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class ORB_LucidFlex : Strategy
    {
        // ── Prop firm parameters ──────────────────────────────────────────────

        [NinjaScriptProperty]
        [Range(10000, 500000)]
        [Display(Name = "Account Size ($)", GroupName = "Prop Firm", Order = 1)]
        public double AccountSize { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 5.0)]
        [Display(Name = "Risk % per Trade", GroupName = "Prop Firm", Order = 2)]
        public double RiskPct { get; set; }

        [NinjaScriptProperty]
        [Range(500, 10000)]
        [Display(Name = "Max Daily Loss ($)", GroupName = "Prop Firm", Order = 3)]
        public double MaxDailyLoss { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 1.0)]
        [Display(Name = "Daily Halt Fraction", GroupName = "Prop Firm", Order = 4)]
        public double DailyHaltFraction { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 20.0)]
        [Display(Name = "Commission/Side ($)", GroupName = "Prop Firm", Order = 5)]
        public double CommissionPerSide { get; set; }

        // ── Strategy parameters ────────────────────────────────────────────────

        [NinjaScriptProperty]
        [Range(5, 60)]
        [Display(Name = "Opening Range Minutes", GroupName = "Strategy", Order = 1)]
        public int ORMinutes { get; set; }

        [NinjaScriptProperty]
        [Range(0.5, 5.0)]
        [Display(Name = "TP Multiple (× OR width)", GroupName = "Strategy", Order = 2)]
        public double TpMultiple { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "One Trade Per Day (long OR short)", GroupName = "Strategy", Order = 3)]
        public bool OneTradePer { get; set; }

        // ── Intraday state ─────────────────────────────────────────────────────

        private double   orHigh, orLow;
        private bool     orSet;
        private bool     longDone, shortDone;
        private bool     tradingHalted;
        private DateTime currentDay = DateTime.MinValue;

        // ── P&L tracking (for daily halt — separate from NT's own accounting) ─

        private double cumulativePnl;    // realised net P&L since start
        private double dayStartPnl;      // cumulativePnl at start of current day
        private double pendingEntryPrice;
        private int    pendingQty;
        private int    pendingDir;       // 1 = long, -1 = short

        // ── Cached time-of-day boundaries (avoid recompute each bar) ──────────

        private TimeSpan tSessionOpen;
        private TimeSpan tOrEnd;
        private TimeSpan tForceFlat;

        // ─────────────────────────────────────────────────────────────────────

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description                  = "Opening Range Breakout — LucidFlex Prop Firm";
                Name                         = "ORB_LucidFlex";
                Calculate                    = Calculate.OnBarClose;
                IsExitOnSessionCloseStrategy = false;   // we handle force-flat ourselves
                BarsRequiredToTrade          = 1;
                EntriesPerDirection          = 1;
                EntryHandling                = EntryHandling.UniqueEntries;

                // Defaults
                AccountSize       = 50000;
                RiskPct           = 0.5;
                MaxDailyLoss      = 2000;
                DailyHaltFraction = 0.6;
                CommissionPerSide = 2.25;
                ORMinutes         = 15;
                TpMultiple        = 1.5;
                OneTradePer       = false;
            }
            else if (State == State.Configure)
            {
                tSessionOpen = new TimeSpan(9, 30, 0);
                tOrEnd       = tSessionOpen.Add(TimeSpan.FromMinutes(ORMinutes));
                tForceFlat   = new TimeSpan(15, 30, 0);
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;

            TimeSpan tod     = Time[0].TimeOfDay;   // Time[0] = bar open time in NT8
            DateTime barDate = Time[0].Date;

            // ── Day boundary ───────────────────────────────────────────────────
            if (barDate != currentDay)
            {
                currentDay    = barDate;
                orHigh        = double.MinValue;
                orLow         = double.MaxValue;
                orSet         = false;
                longDone      = false;
                shortDone     = false;
                tradingHalted = false;
                dayStartPnl   = cumulativePnl;
            }

            // ── Force flat at 15:30 ────────────────────────────────────────────
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

            // ── Finalise OR on first bar after OR period ──────────────────────
            if (!orSet)
            {
                if (tod >= tOrEnd && orHigh > orLow)
                    orSet = true;
                else
                    return;
            }

            // ── Daily halt check ───────────────────────────────────────────────
            if (!tradingHalted)
            {
                double dayLoss = dayStartPnl - cumulativePnl;   // positive when losing
                if (dayLoss >= MaxDailyLoss * DailyHaltFraction)
                    tradingHalted = true;
            }
            if (tradingHalted) return;

            // Don't stack a new entry while in position
            if (Position.MarketPosition != MarketPosition.Flat) return;

            double orWidth = orHigh - orLow;
            double close   = Close[0];

            // ── Long breakout ──────────────────────────────────────────────────
            if (!longDone && close > orHigh)
            {
                longDone = true;    // mark regardless — don't chase on subsequent bars
                if (!(OneTradePer && shortDone))
                {
                    int qty = CalcContracts(orWidth);
                    if (qty >= 1)
                    {
                        double stop   = orLow;
                        double target = orHigh + TpMultiple * orWidth;
                        SetStopLoss("ORB_Long",    CalculationMode.Price, stop);
                        SetProfitTarget("ORB_Long", CalculationMode.Price, target);
                        EnterLong(0, qty, "ORB_Long");
                        pendingDir = 1;
                        pendingQty = qty;
                    }
                }
            }

            // ── Short breakout ─────────────────────────────────────────────────
            if (!shortDone && close < orLow)
            {
                shortDone = true;
                if (!(OneTradePer && longDone))
                {
                    int qty = CalcContracts(orWidth);
                    if (qty >= 1)
                    {
                        double stop   = orHigh;
                        double target = orLow - TpMultiple * orWidth;
                        SetStopLoss("ORB_Short",    CalculationMode.Price, stop);
                        SetProfitTarget("ORB_Short", CalculationMode.Price, target);
                        EnterShort(0, qty, "ORB_Short");
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
                        double pv  = Instrument.MasterInstrument.PointValue;
                        int    dir = (execution.Order.OrderAction == OrderAction.Sell) ? 1 : -1;
                        double gross = (price - pendingEntryPrice) * dir * quantity * pv;
                        double costs = CommissionPerSide * 2 * quantity;
                        cumulativePnl    += gross - costs;
                        pendingEntryPrice = 0;
                        pendingQty        = 0;
                        pendingDir        = 0;
                    }
                    break;
            }
        }

        // Floor(account_equity × risk_pct / (stop_dist_pts × point_value))
        private int CalcContracts(double stopDistPoints)
        {
            if (stopDistPoints <= 0) return 0;
            double equity     = AccountSize + cumulativePnl;
            double dollarRisk = equity * (RiskPct / 100.0);
            double pv         = Instrument.MasterInstrument.PointValue;
            return Math.Max(0, (int)(dollarRisk / (stopDistPoints * pv)));
        }
    }
}
