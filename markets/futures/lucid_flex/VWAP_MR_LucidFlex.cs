// VWAP Mean Reversion — LucidFlex Prop Firm
//
// Rules:
//   Session-cumulative VWAP + volume-weighted std dev reset at 09:30 each day
//   Long signal : close < VWAP - EntryStd × σ   (stretched below)
//   Short signal: close > VWAP + EntryStd × σ   (stretched above)
//   Stop        : close ∓ StopExtension × σ      (further from VWAP)
//   Target      : close + TpFraction × (VWAP - close)  (fraction back to VWAP)
//   One trade per direction per day
//   Skip first MinBarsBeforeEntry bars of each session (VWAP needs time to stabilise)
//   Force flat  : 15:30 ET
//   Daily halt  : day loss ≥ DailyHaltFraction × MaxDailyLoss
//
// Install: copy to Documents/NinjaTrader 8/bin/Custom/Strategies/

#region Using declarations
using System;
using System.IO;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class VWAP_MR_LucidFlex : Strategy
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
        [Range(0.5, 5.0)]
        [Display(Name = "Entry Std Dev Multiplier", GroupName = "Strategy", Order = 1)]
        public double EntryStd { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 3.0)]
        [Display(Name = "Stop Extension (× σ)", GroupName = "Strategy", Order = 2)]
        public double StopExtension { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 2.0)]
        [Display(Name = "TP Fraction (back to VWAP)", GroupName = "Strategy", Order = 3)]
        public double TpFraction { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Min Bars Before Entry", GroupName = "Strategy", Order = 4)]
        public int MinBarsBeforeEntry { get; set; }

        // ── Intraday state ─────────────────────────────────────────────────────

        private bool     longDone, shortDone;
        private bool     tradingHalted;
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

        // ── Backtest performance accumulators (exported to CSV on Terminated) ─

        private double peakEquity;
        private double maxDrawdown;
        private double grossWins;
        private double grossLosses;
        private int    winCount;
        private int    tradeCount;

        // ── Cached boundaries ──────────────────────────────────────────────────

        private TimeSpan tSessionOpen;
        private TimeSpan tForceFlat;

        // ─────────────────────────────────────────────────────────────────────

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description                  = "VWAP Mean Reversion — LucidFlex Prop Firm";
                Name                         = "VWAP_MR_LucidFlex";
                Calculate                    = Calculate.OnBarClose;
                IsExitOnSessionCloseStrategy = false;
                BarsRequiredToTrade          = 1;
                EntriesPerDirection          = 1;
                EntryHandling                = EntryHandling.UniqueEntries;

                AccountSize       = 50000;
                RiskPct           = 0.5;
                MaxDailyLoss      = 2000;
                DailyHaltFraction = 0.6;
                CommissionPerSide = 2.25;
                EntryStd          = 2.0;
                StopExtension     = 1.0;
                TpFraction        = 1.0;
                MinBarsBeforeEntry = 20;
            }
            else if (State == State.Configure)
            {
                tSessionOpen = new TimeSpan(9, 30, 0);
                tForceFlat   = new TimeSpan(15, 30, 0);
                peakEquity   = AccountSize;
            }
            else if (State == State.Terminated)
            {
                try
                {
                    double net    = grossWins + grossLosses;
                    double pf     = (grossLosses != 0) ? grossWins / Math.Abs(grossLosses) : 0;
                    double winPct = (tradeCount > 0) ? (double)winCount / tradeCount * 100.0 : 0;

                    string dir  = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                        "NinjaTrader 8");
                    string path = Path.Combine(dir, "lucid_flex_results.csv");

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

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;

            TimeSpan tod     = Time[0].TimeOfDay;
            DateTime barDate = Time[0].Date;

            // ── Day boundary ───────────────────────────────────────────────────
            if (barDate != currentDay)
            {
                currentDay      = barDate;
                longDone        = false;
                shortDone       = false;
                tradingHalted   = false;
                sessionBarCount = 0;
                cumTpv          = 0;
                cumVol          = 0;
                cumTp2v         = 0;
                dayStartPnl     = cumulativePnl;
            }

            // ── Force flat at 15:30 ────────────────────────────────────────────
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

            // ── Update running VWAP accumulators ──────────────────────────────
            double tp  = (High[0] + Low[0] + Close[0]) / 3.0;
            double vol = Math.Max(Volume[0], 1.0);   // guard against zero-volume bars
            cumTpv  += tp * vol;
            cumVol  += vol;
            cumTp2v += tp * tp * vol;
            sessionBarCount++;

            // Not enough bars yet for a stable VWAP estimate
            if (sessionBarCount <= MinBarsBeforeEntry) return;

            double vwap     = cumTpv / cumVol;
            double variance = Math.Max(0.0, cumTp2v / cumVol - vwap * vwap);
            double sigma    = Math.Sqrt(variance);

            if (sigma <= 0) return;

            // ── Daily halt check ───────────────────────────────────────────────
            if (!tradingHalted)
            {
                double dayLoss = dayStartPnl - cumulativePnl;
                if (dayLoss >= MaxDailyLoss * DailyHaltFraction)
                    tradingHalted = true;
            }
            if (tradingHalted) return;

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
                double target = close + TpFraction * (vwap - close);   // negative move
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
                        int    dir   = (execution.Order.OrderAction == OrderAction.Sell) ? 1 : -1;
                        double gross = (price - pendingEntryPrice) * dir * quantity * pv;
                        double costs = CommissionPerSide * 2 * quantity;
                        double tradePnl   = gross - costs;
                        cumulativePnl    += tradePnl;
                        pendingEntryPrice = 0;
                        pendingQty        = 0;
                        pendingDir        = 0;

                        tradeCount++;
                        if (tradePnl > 0) { grossWins += tradePnl; winCount++; }
                        else                grossLosses += tradePnl;

                        double equity = AccountSize + cumulativePnl;
                        if (equity > peakEquity) peakEquity = equity;
                        double dd = peakEquity - equity;
                        if (dd > maxDrawdown) maxDrawdown = dd;
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
