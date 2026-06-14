//+------------------------------------------------------------------+
//|                                             LondonBreakout.mq5    |
//|                                                LWG Capital LLC    |
//+------------------------------------------------------------------+
// London session breakout — first honest version (v1).
//
// Idea: the Asian session (00:00-06:00 GMT) sets a quiet reference range.
//   At the London open, price often breaks that range and continues in the
//   break direction. We mark the Asian high/low, wait for a bar-close break
//   past a small buffer, take one trade in the break direction, and are flat
//   by late London.
//
// This file is fully INSTRUMENT-AGNOSTIC. No symbol, no pip value, and no
//   per-pair number is baked in. Everything that differs per instrument is
//   either read from the broker (SymbolInfo) or expressed as a multiple of
//   the instrument's own ATR, so the same file runs on AUDJPY, CADJPY,
//   USDJPY, or XAUUSD with nothing changed but the injected layers.
//   The word "pip" never appears in the logic — distances are points.
//
// Entry is BAR-CLOSE, not intrabar pending orders, to stay inside the
//   trustworthy MT5 data band (Model=1, M5/M15 bar-close).
//
// Diagnostic (the point of this run): independent of any trade, count how
//   often a single M15 bar touches BOTH breakout levels. That is the case a
//   bar model cannot resolve (it can't know which side was hit first), so it
//   quantifies how much the bar model is silently guessing. Written to a CSV
//   in the MQL5 Common\Files folder and printed at the end of the run.
//
// Layers:
//   Layer A (Strategy Logic, tunable, no prefix) — session windows + the
//     ATR-scaled range/buffer/target knobs. All scale across instruments.
//   Foundational (f_ prefix) — sizing, risk caps, and costs injected from the
//     active ruleset by the lab dispatcher. Sentinel defaults (-1) force a
//     hard fail at init if injection did not happen.
//+------------------------------------------------------------------+
#property copyright "LWG Capital LLC"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- Strategy logic parameters (Layer A — tunable by optimizer) ---
// Session windows are in GMT. They define the strategy, not the instrument,
// so they are the same for every pair. Times are "HH:MM".
input string AsianStartGMT   = "00:00";   // Asian range window start (GMT)
input string AsianEndGMT     = "06:00";   // Asian range window end (GMT, exclusive)
input string LondonOpenGMT   = "07:00";   // start watching for the break (GMT)
input string EntryCutoffGMT  = "09:00";   // last bar we may enter on (GMT, exclusive)
input string ForceFlatGMT    = "11:00";   // close any open trade at/after this (GMT)

// Volatility scale — everything per-pair is expressed against this ATR.
input int    AtrPeriod       = 14;        // ATR lookback, on the DAILY timeframe
input double RangeMinAtr     = 0.5;       // skip day if Asian range < this x ATR
input double RangeMaxAtr     = 1.3;       // skip day if Asian range > this x ATR
input double BufferAtr       = 0.1;       // breakout buffer = this x ATR beyond the range
input double TargetRR        = 1.0;       // target as a multiple of the stop distance (1:1)

//--- Foundational parameters (injected from ruleset — do not modify defaults) ---
input double f_AccountSize           = -1;   // USD account size for position sizing
input double f_RiskPerTradePct       = -1;   // % risk per trade (e.g. 1.0)
input double f_DailyLossCap          = -1;   // USD daily max loss
input double f_DailyHaltFraction     = -1;   // halt new entries at this fraction of cap (0-1)
input int    f_MaxConsecutiveLosses  = -1;   // halt after N consecutive losses (0 = disabled)
input double f_DailyProfitTarget     = -1;   // USD daily target (0 = disabled)
input double f_DailyProfitLockPct    = -1;   // fraction of target where risk halves (0 = disabled)
input double f_CommissionPerSide     = 0;    // commission per side (informational; spread is the live cost)
input int    f_SlippageTicks         = 0;    // deviation tolerance in points
input int    f_BrokerToGmtOffsetHours = 99;  // override broker-to-GMT offset hours (99 = auto-detect)

//--- Globals ---
CTrade trade;

int g_atrHandle = INVALID_HANDLE;

datetime g_lastBarTime = 0;

// Broker server time minus GMT, in seconds. Bars and tick time are in broker
// server time; subtract this to get GMT. Auto-detected in OnInit using the
// codebase's existing TimeTradeServer()-TimeGMT() handling (never hardcoded).
int g_brokerToGmtSec = 0;

// Session window minutes-of-day (GMT), parsed once in OnInit.
int g_asianStartMin  = 0;
int g_asianEndMin    = 0;
int g_londonOpenMin  = 0;
int g_entryCutoffMin = 0;
int g_forceFlatMin   = 0;

// Per-day state (keyed on GMT calendar day).
int      g_curDayYmd    = 0;       // yyyymmdd in GMT of the day being tracked
double   g_asianHigh    = 0;
double   g_asianLow     = 0;
bool     g_asianSeen    = false;   // at least one Asian bar collected this day
bool     g_dayDecided   = false;   // range filter has been evaluated this day
bool     g_dayQualifies = false;   // range filter passed -> levels live
double   g_buyLevel     = 0;
double   g_sellLevel    = 0;
bool     g_tradedToday  = false;   // one trade per day, no re-entry
bool     g_dayHasBoth   = false;   // this day already had a both-sided bar

// Foundational daily risk state (reset on GMT-day rollover).
double g_dayStartBalance   = 0;
int    g_consecutiveLosses = 0;
double g_riskMultiplier    = 1.0;
bool   g_tradingHalted     = false;

// Open trade state.
ulong  g_ticket       = 0;
double g_riskAtEntry  = 0;       // USD risk at open; used to classify win/loss in R
double g_balanceAtEntry = 0;
bool   g_inTrade      = false;

// Diagnostic counters (the point of this run).
int      g_qualifyingDays = 0;   // days the range filter passed (levels live)
int      g_bothSidedDays  = 0;   // qualifying days with >= 1 both-sided bar
int      g_bothSidedBars  = 0;   // total both-sided bars across all qualifying days
string   g_bothSidedDates[];     // one entry per both-sided day, "YYYY-MM-DD"

//=============================================================================
// HELPERS
//=============================================================================

bool ParseHHMM(const string s, int &minutes) {
   if(StringLen(s) < 5) return false;
   int h = (int)StringToInteger(StringSubstr(s, 0, 2));
   int m = (int)StringToInteger(StringSubstr(s, 3, 2));
   if(h < 0 || h > 23 || m < 0 || m > 59) return false;
   minutes = h * 60 + m;
   return true;
}

// Convert a broker-server time to GMT.
datetime ToGmt(const datetime brokerTime) {
   return (datetime)((long)brokerTime - (long)g_brokerToGmtSec);
}

int GmtMinuteOfDay(const datetime brokerTime) {
   MqlDateTime dt;
   TimeToStruct(ToGmt(brokerTime), dt);
   return dt.hour * 60 + dt.min;
}

int GmtYmd(const datetime brokerTime) {
   MqlDateTime dt;
   TimeToStruct(ToGmt(brokerTime), dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
}

string GmtDateString(const datetime brokerTime) {
   MqlDateTime dt;
   TimeToStruct(ToGmt(brokerTime), dt);
   return StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
}

// Daily ATR of the last COMPLETED daily bar (shift 1 — never the forming one,
// so there is no look-ahead). Returns 0 if unavailable.
double DailyAtr() {
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_atrHandle, 0, 1, 1, atr) < 1) return 0;
   return atr[0];
}

//=============================================================================
// FOUNDATIONAL CHECKS
//=============================================================================

bool ValidateFoundationalParams() {
   bool ok = true;
   if(f_AccountSize          < 0) { Print("ERROR: f_AccountSize not injected");          ok = false; }
   if(f_RiskPerTradePct      < 0) { Print("ERROR: f_RiskPerTradePct not injected");      ok = false; }
   if(f_DailyLossCap         < 0) { Print("ERROR: f_DailyLossCap not injected");         ok = false; }
   if(f_DailyHaltFraction    < 0) { Print("ERROR: f_DailyHaltFraction not injected");    ok = false; }
   if(f_MaxConsecutiveLosses < 0) { Print("ERROR: f_MaxConsecutiveLosses not injected"); ok = false; }
   if(f_DailyProfitTarget    < 0) { Print("ERROR: f_DailyProfitTarget not injected");    ok = false; }
   if(f_DailyProfitLockPct   < 0) { Print("ERROR: f_DailyProfitLockPct not injected");   ok = false; }
   return ok;
}

// Reset both the session-day and the foundational daily-risk state.
void ResetForNewDay(const int ymd) {
   g_curDayYmd    = ymd;
   g_asianHigh    = 0;
   g_asianLow     = 0;
   g_asianSeen    = false;
   g_dayDecided   = false;
   g_dayQualifies = false;
   g_buyLevel     = 0;
   g_sellLevel    = 0;
   g_tradedToday  = false;
   g_dayHasBoth   = false;

   g_dayStartBalance   = AccountInfoDouble(ACCOUNT_BALANCE);
   g_consecutiveLosses = 0;
   g_riskMultiplier    = 1.0;
   g_tradingHalted     = false;
}

void UpdateRiskMultiplier() {
   if(f_DailyProfitTarget <= 0 || f_DailyProfitLockPct <= 0) return;
   double dayPnl = AccountInfoDouble(ACCOUNT_BALANCE) - g_dayStartBalance;
   double lockAt = f_DailyProfitTarget * f_DailyProfitLockPct;
   if(dayPnl >= lockAt && g_riskMultiplier > 0.5) {
      g_riskMultiplier = 0.5;
      PrintFormat("Profit lock-in: day P&L=%.2f >= %.2f. Risk halved.", dayPnl, lockAt);
   }
}

bool CanEnter() {
   if(g_tradingHalted) return false;
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double dayLoss = g_dayStartBalance - balance;
   if(dayLoss >= f_DailyLossCap * f_DailyHaltFraction) return false;
   if(f_DailyProfitTarget > 0 && (balance - g_dayStartBalance) >= f_DailyProfitTarget) return false;
   return true;
}

//=============================================================================
// SIZING — risk-based, read entirely from the broker. No pip assumption.
//=============================================================================

double CalcLots(const double slDistancePrice) {
   double tickSize  = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_VALUE);
   if(tickSize == 0 || tickValue == 0 || slDistancePrice <= 0) return 0;

   double riskUSD = f_AccountSize * (f_RiskPerTradePct / 100.0) * g_riskMultiplier;
   double lots    = riskUSD / (slDistancePrice / tickSize * tickValue);

   double lotStep = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_STEP);
   double minLot  = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MAX);
   if(lotStep <= 0) return 0;

   lots = MathFloor(lots / lotStep) * lotStep;
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;
   return lots;
}

//=============================================================================
// ENTRY
//=============================================================================

void EnterTrade(const int direction, const double closePrice) {
   double point = _Point;
   double entry, sl, tp, slDist;

   if(direction == 1) {                       // long: stop at the Asian low
      entry  = SymbolInfoDouble(Symbol(), SYMBOL_ASK);
      sl     = g_asianLow;
      slDist = entry - sl;
      tp     = entry + slDist * TargetRR;
   } else {                                   // short: stop at the Asian high
      entry  = SymbolInfoDouble(Symbol(), SYMBOL_BID);
      sl     = g_asianHigh;
      slDist = sl - entry;
      tp     = entry - slDist * TargetRR;
   }

   if(slDist <= 0) { Print("Invalid SL distance. Skipping entry."); return; }

   // Respect the broker's minimum stop distance (points), if any.
   double minStop = (double)SymbolInfoInteger(Symbol(), SYMBOL_TRADE_STOPS_LEVEL) * point;
   if(slDist < minStop) {
      PrintFormat("SL distance %.1f pts < broker min %.1f pts. Skipping entry.",
                  slDist / point, minStop / point);
      return;
   }

   double lots = CalcLots(slDist);
   if(lots <= 0) { Print("Lot size zero or invalid. Skipping entry."); return; }

   sl = NormalizeDouble(sl, _Digits);
   tp = NormalizeDouble(tp, _Digits);

   bool ok = (direction == 1)
      ? trade.Buy (lots, Symbol(), 0, sl, tp, "LondonBreakout")
      : trade.Sell(lots, Symbol(), 0, sl, tp, "LondonBreakout");

   if(ok && PositionSelect(Symbol())) {
      g_ticket        = PositionGetInteger(POSITION_TICKET);
      g_inTrade       = true;
      g_tradedToday   = true;
      g_balanceAtEntry = AccountInfoDouble(ACCOUNT_BALANCE);
      g_riskAtEntry   = f_AccountSize * (f_RiskPerTradePct / 100.0) * g_riskMultiplier;
      PrintFormat("ENTRY | %s | lots=%.2f | entry=%.5f | SL=%.5f | TP=%.5f | "
                  "stop=%.1f pts | barClose=%.5f",
                  direction == 1 ? "BUY" : "SELL", lots,
                  PositionGetDouble(POSITION_PRICE_OPEN), sl, tp, slDist / point, closePrice);
   } else {
      g_tradedToday = true;   // do not retry the same break
      PrintFormat("Order failed: retcode=%d %s",
                  trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}

//=============================================================================
// EXITS
//=============================================================================

void OnPositionClosed() {
   double profitUSD = AccountInfoDouble(ACCOUNT_BALANCE) - g_balanceAtEntry;
   double profitR   = (g_riskAtEntry > 0) ? profitUSD / g_riskAtEntry : 0;
   if(profitR < -0.1) {
      g_consecutiveLosses++;
      if(f_MaxConsecutiveLosses > 0 && g_consecutiveLosses >= f_MaxConsecutiveLosses) {
         g_tradingHalted = true;
         PrintFormat("HALT: %d consecutive losses.", g_consecutiveLosses);
      }
   } else if(profitR > 0.1) {
      g_consecutiveLosses = 0;
   }
   g_inTrade = false;
   g_ticket  = 0;
}

// Force flat at/after ForceFlatGMT — time-critical, so checked every tick.
void CheckForceFlat() {
   if(!g_inTrade) return;
   if(GmtMinuteOfDay(TimeCurrent()) < g_forceFlatMin) return;
   if(!PositionSelectByTicket(g_ticket)) return;   // already gone; ManageOpen reconciles
   if(trade.PositionClose(g_ticket)) Print("Force flat executed.");
   else PrintFormat("Force flat failed: retcode=%d", trade.ResultRetcode());
}

void ManageOpen() {
   if(!g_inTrade) return;
   if(!PositionSelectByTicket(g_ticket)) OnPositionClosed();   // SL/TP took it
}

//=============================================================================
// DIAGNOSTIC OUTPUT
//=============================================================================

void WriteDiagnostic() {
   double pct = (g_qualifyingDays > 0)
                ? 100.0 * (double)g_bothSidedDays / (double)g_qualifyingDays : 0.0;

   PrintFormat("BOTHSIDED_DIAG | symbol=%s | qualifying_days=%d | both_sided_days=%d | "
               "both_sided_bars=%d | pct_days=%.2f",
               Symbol(), g_qualifyingDays, g_bothSidedDays, g_bothSidedBars, pct);

   // Persist to the Common\Files folder so the result is retrievable after the
   // tester exits (mirrors how the optimizer surfaces opt_results.csv).
   string fname = "LondonBreakout_diag_" + Symbol() + ".csv";
   int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE) { PrintFormat("Diag: cannot write %s", fname); return; }
   FileWrite(fh, "metric", "value");
   FileWrite(fh, "symbol", Symbol());
   FileWrite(fh, "qualifying_days", g_qualifyingDays);
   FileWrite(fh, "both_sided_days", g_bothSidedDays);
   FileWrite(fh, "both_sided_bars", g_bothSidedBars);
   FileWrite(fh, "pct_days", DoubleToString(pct, 2));
   FileWrite(fh, "---", "both_sided_dates_below");
   for(int i = 0; i < ArraySize(g_bothSidedDates); i++)
      FileWrite(fh, "both_sided_date", g_bothSidedDates[i]);
   FileClose(fh);
   PrintFormat("Diag: wrote %s to Common\\Files", fname);
}

//=============================================================================
// PER-BAR LOGIC (the just-closed bar, index 1)
//=============================================================================

void OnClosedBar() {
   datetime bt = iTime(Symbol(), PERIOD_CURRENT, 1);
   if(bt == 0) return;

   int ymd = GmtYmd(bt);
   if(ymd != g_curDayYmd) ResetForNewDay(ymd);

   int minute = GmtMinuteOfDay(bt);

   double bhigh[1], blow[1], bclose[1];
   if(CopyHigh (Symbol(), PERIOD_CURRENT, 1, 1, bhigh)  != 1) return;
   if(CopyLow  (Symbol(), PERIOD_CURRENT, 1, 1, blow)   != 1) return;
   if(CopyClose(Symbol(), PERIOD_CURRENT, 1, 1, bclose) != 1) return;
   double hi = bhigh[0], lo = blow[0], cl = bclose[0];

   // --- 1. Accumulate the Asian range (bars whose GMT open is in the window) ---
   if(minute >= g_asianStartMin && minute < g_asianEndMin) {
      if(!g_asianSeen) { g_asianHigh = hi; g_asianLow = lo; g_asianSeen = true; }
      else             { g_asianHigh = MathMax(g_asianHigh, hi); g_asianLow = MathMin(g_asianLow, lo); }
      return;
   }

   // --- 2. At the London open, decide the day (range filter) and set levels ---
   if(!g_dayDecided && minute >= g_londonOpenMin && g_asianSeen) {
      g_dayDecided = true;
      double atr = DailyAtr();
      double range = g_asianHigh - g_asianLow;
      if(atr <= 0) {
         Print("Range filter: ATR unavailable, skipping day.");
      } else if(range < RangeMinAtr * atr || range > RangeMaxAtr * atr) {
         PrintFormat("Range filter: skip %s | range=%.1f pts | atr=%.1f pts | band=[%.2f,%.2f]xATR",
                     GmtDateString(bt), range / _Point, atr / _Point, RangeMinAtr, RangeMaxAtr);
      } else {
         g_dayQualifies = true;
         g_buyLevel  = g_asianHigh + BufferAtr * atr;
         g_sellLevel = g_asianLow  - BufferAtr * atr;
         g_qualifyingDays++;
         PrintFormat("Levels %s | buy=%.5f | sell=%.5f | range=%.1f pts | atr=%.1f pts",
                     GmtDateString(bt), g_buyLevel, g_sellLevel, range / _Point, atr / _Point);
      }
   }

   // --- 3. In the entry window on a qualifying day: diagnostic, then maybe enter ---
   if(g_dayQualifies && minute >= g_londonOpenMin && minute < g_entryCutoffMin) {
      // Diagnostic (independent of trading): did this one bar touch BOTH levels?
      if(hi >= g_buyLevel && lo <= g_sellLevel) {
         g_bothSidedBars++;
         if(!g_dayHasBoth) {
            g_dayHasBoth = true;
            g_bothSidedDays++;
            int n = ArraySize(g_bothSidedDates);
            ArrayResize(g_bothSidedDates, n + 1);
            g_bothSidedDates[n] = GmtDateString(bt);
            PrintFormat("BOTHSIDED_DATE | %s", GmtDateString(bt));
         }
      }

      // Entry — bar close past a level, one trade per day, foundational gates pass.
      if(!g_tradedToday && !g_inTrade && CanEnter()) {
         if(cl > g_buyLevel)       EnterTrade(1, cl);
         else if(cl < g_sellLevel) EnterTrade(-1, cl);
      }
   }
}

//=============================================================================
// EA LIFECYCLE
//=============================================================================

int OnInit() {
   if(!MQLInfoInteger(MQL_OPTIMIZATION) && !ValidateFoundationalParams()) {
      Print("INIT FAILED: foundational parameters at placeholder values. "
            "The lab dispatcher must inject all f_ params before running.");
      return INIT_FAILED;
   }

   if(Period() != PERIOD_M15)
      PrintFormat("WARNING: designed for M15 bar-close logic; running on %s.",
                  EnumToString(Period()));

   if(!ParseHHMM(AsianStartGMT,  g_asianStartMin)  ||
      !ParseHHMM(AsianEndGMT,    g_asianEndMin)    ||
      !ParseHHMM(LondonOpenGMT,  g_londonOpenMin)  ||
      !ParseHHMM(EntryCutoffGMT, g_entryCutoffMin) ||
      !ParseHHMM(ForceFlatGMT,   g_forceFlatMin)) {
      Print("INIT FAILED: a session window string is not valid HH:MM.");
      return INIT_FAILED;
   }

   // Broker-to-GMT offset: auto-detect from server time unless overridden.
   // Uses the same TimeTradeServer()-TimeGMT() handling already in the codebase.
   if(f_BrokerToGmtOffsetHours != 99) {
      g_brokerToGmtSec = f_BrokerToGmtOffsetHours * 3600;
      PrintFormat("Broker-to-GMT offset: %d h (manual override).", f_BrokerToGmtOffsetHours);
   } else {
      int hours = (int)MathRound((double)(TimeTradeServer() - TimeGMT()) / 3600.0);
      g_brokerToGmtSec = hours * 3600;
      PrintFormat("Broker-to-GMT offset: %d h (auto-detected from server time).", hours);
   }

   g_atrHandle = iATR(Symbol(), PERIOD_D1, AtrPeriod);
   if(g_atrHandle == INVALID_HANDLE) {
      Print("INIT FAILED: could not create daily ATR handle.");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(20240003);
   trade.SetDeviationInPoints(f_SlippageTicks);

   g_lastBarTime     = 0;
   g_curDayYmd       = 0;
   g_inTrade         = false;
   g_qualifyingDays  = 0;
   g_bothSidedDays   = 0;
   g_bothSidedBars   = 0;
   ArrayResize(g_bothSidedDates, 0);

   PrintFormat("LondonBreakout init | symbol=%s | TF=%s | account=%.2f | risk=%.2f%% | "
               "commission/side=%.2f (informational; spread is the live cost)",
               Symbol(), EnumToString(Period()), f_AccountSize, f_RiskPerTradePct, f_CommissionPerSide);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   WriteDiagnostic();
}

void OnTick() {
   CheckForceFlat();                         // time-critical, every tick

   datetime barTime = iTime(Symbol(), PERIOD_CURRENT, 0);
   if(barTime == g_lastBarTime) return;      // act only on a new completed bar
   g_lastBarTime = barTime;

   UpdateRiskMultiplier();
   ManageOpen();
   OnClosedBar();
}
