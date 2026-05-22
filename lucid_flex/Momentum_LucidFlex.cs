// Intraday Momentum Pullback — LucidFlex Prop Firm
//
// Rules:
//   20-period SMA as trend filter
//   Uptrend    : close > SMA and SMA rising
//   Pullback   : bar low ≤ SMA while uptrend is active (track lowest low)
//   Resumption : close > SMA after pullback → long signal
//   Stop       : pullback low
//   Target     : entry + RrRatio × (entry − stop)
//   Symmetric logic for downtrend / short
//   State machine resets at each new session day
//   Force flat : 15:30 ET
//   Daily halt : day loss ≥ DailyHaltFraction × MaxDailyLoss
//
// Install: copy to Documents/NinjaTrader 8/bin/Custom/Strategies/

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
    public class Momentum_LucidFlex : Strategy
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
        [Range(5, 100)]
        [Display(Name = "MA Period", GroupName = "Strategy", Order = 1)]
        public int MaPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.5, 10.0)]
        [Display(Name = "Reward:Risk Ratio", GroupName = "Strategy", Order = 2)]
        public double RrRatio { get; set; }

        // ── State machine ──────────────────────────────────────────────────────

        private enum TrendState { Seek, Uptrend, PullbackUp, Downtrend, PullbackDown }

        private TrendState trendState;
        private double     pullbackExt;    // lowest low (long) or highest high (short) during pullback
        private DateTime   currentDay = DateTime.MinValue;

        // ── Prop firm intraday state ───────────────────────────────────────────

        private bool   tradingHalted;
        private double cumulativePnl;
        private double dayStartPnl;
        private double pendingEntryPrice;
        private int    pendingQty;
        private int    pendingDir;

        // ── Cached boundary ────────────────────────────────────────────────────

        private TimeSpan tForceFlat;

        // ─────────────────────────────────────────────────────────────────────

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description                  = "Intraday Momentum Pullback — LucidFlex Prop Firm";
                Name                         = "Momentum_LucidFlex";
                Calculate                    = Calculate.OnBarClose;
                IsExitOnSessionCloseStrategy = false;
                BarsRequiredToTrade          = MaPeriod + 1;
                EntriesPerDirection          = 1;
                EntryHandling                = EntryHandling.UniqueEntries;

                AccountSize       = 50000;
                RiskPct           = 0.5;
                MaxDailyLoss      = 2000;
                DailyHaltFraction = 0.6;
                CommissionPerSide = 2.25;
                MaPeriod          = 20;
                RrRatio           = 2.0;
            }
            else if (State == State.Configure)
            {
                tForceFlat = new TimeSpan(15, 30, 0);
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < MaPeriod) return;   // need enough bars for SMA

            TimeSpan tod     = Time[0].TimeOfDay;
            DateTime barDate = Time[0].Date;

            // ── Day boundary: reset state machine ─────────────────────────────
            if (barDate != currentDay)
            {
                currentDay    = barDate;
                trendState    = TrendState.Seek;
                pullbackExt   = 0;
                tradingHalted = false;
                dayStartPnl   = cumulativePnl;
            }

            // ── Force flat at 15:30 ────────────────────────────────────────────
            if (tod >= tForceFlat)
            {
                if (Position.MarketPosition != MarketPosition.Flat)
                {
                    ExitLong("ForceFlat",  "MOM_Long");
                    ExitShort("ForceFlat", "MOM_Short");
                }
                return;
            }

            // ── Daily halt ─────────────────────────────────────────────────────
            if (!tradingHalted)
            {
                double dayLoss = dayStartPnl - cumulativePnl;
                if (dayLoss >= MaxDailyLoss * DailyHaltFraction)
                    tradingHalted = true;
            }
            if (tradingHalted) return;

            double ma      = SMA(MaPeriod)[0];
            double prevMa  = SMA(MaPeriod)[1];
            double close   = Close[0];
            double low     = Low[0];
            double high    = High[0];
            bool   rising  = ma > prevMa;
            bool   falling = ma < prevMa;

            // ── State machine ──────────────────────────────────────────────────

            switch (trendState)
            {
                case TrendState.Seek:
                    if (close > ma && rising)
                        trendState = TrendState.Uptrend;
                    else if (close < ma && falling)
                        trendState = TrendState.Downtrend;
                    break;

                case TrendState.Uptrend:
                    if (!rising)
                    {
                        trendState = TrendState.Seek;
                    }
                    else if (low <= ma)
                    {
                        trendState  = TrendState.PullbackUp;
                        pullbackExt = low;
                    }
                    break;

                case TrendState.PullbackUp:
                    pullbackExt = Math.Min(pullbackExt, low);   // track deepest low
                    if (!rising)
                    {
                        trendState = TrendState.Seek;
                        pullbackExt = 0;
                    }
                    else if (close > ma && Position.MarketPosition == MarketPosition.Flat)
                    {
                        // Resumption — generate long signal
                        double stop = pullbackExt;
                        double risk = close - stop;
                        if (risk > 0)
                        {
                            double target = close + RrRatio * risk;
                            int    qty    = CalcContracts(risk);
                            if (qty >= 1)
                            {
                                SetStopLoss("MOM_Long",    CalculationMode.Price, stop);
                                SetProfitTarget("MOM_Long", CalculationMode.Price, target);
                                EnterLong(0, qty, "MOM_Long");
                                pendingDir = 1;
                                pendingQty = qty;
                            }
                        }
                        trendState  = TrendState.Uptrend;
                        pullbackExt = 0;
                    }
                    break;

                case TrendState.Downtrend:
                    if (!falling)
                    {
                        trendState = TrendState.Seek;
                    }
                    else if (high >= ma)
                    {
                        trendState  = TrendState.PullbackDown;
                        pullbackExt = high;
                    }
                    break;

                case TrendState.PullbackDown:
                    pullbackExt = Math.Max(pullbackExt, high);  // track highest high
                    if (!falling)
                    {
                        trendState  = TrendState.Seek;
                        pullbackExt = 0;
                    }
                    else if (close < ma && Position.MarketPosition == MarketPosition.Flat)
                    {
                        // Resumption — generate short signal
                        double stop = pullbackExt;
                        double risk = stop - close;
                        if (risk > 0)
                        {
                            double target = close - RrRatio * risk;
                            int    qty    = CalcContracts(risk);
                            if (qty >= 1)
                            {
                                SetStopLoss("MOM_Short",    CalculationMode.Price, stop);
                                SetProfitTarget("MOM_Short", CalculationMode.Price, target);
                                EnterShort(0, qty, "MOM_Short");
                                pendingDir = -1;
                                pendingQty = qty;
                            }
                        }
                        trendState  = TrendState.Downtrend;
                        pullbackExt = 0;
                    }
                    break;
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
                        int    dir   = (execution.Order.OrderAction == OrderAction.Sell) ? 1 : -1;
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
