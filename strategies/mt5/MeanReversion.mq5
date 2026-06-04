//+------------------------------------------------------------------+
//|                                              MeanReversion.mq5   |
//|                                                LWG Capital LLC   |
//+------------------------------------------------------------------+
// Mean Reversion strategy — BB + RSI + VWAP confluence
//
// Signal: enter when price is outside BB band, RSI confirms overextension,
//   VWAP deviation confirms, and a rejection candle prints. All checks
//   must align. Confluence scoring: see signal block.
//
// Exits: Breakeven at +0.3R, full close at +1R, early close on RSI
//   neutralization (45-55 range). Tight ATR trail between BE and 1R.
//
// Foundational params (prefixed with f_) come from the ruleset at
// runtime via the LWG Capital backtest lab dispatcher. Do not modify
// these defaults; they will be overridden.
//
// Tunable params (no prefix) are exposed to the optimizer.
//+------------------------------------------------------------------+
#property copyright "LWG Capital LLC"
#property version   "1.01"
#property strict

#include <Trade\Trade.mqh>

//--- Strategy logic parameters (tunable by optimizer) ---

input int    BBPeriod               = 20;           // Bollinger Band lookback
input double BBStdEntry             = 2.0;           // BB std dev for entry signal
input int    RSIPeriod              = 14;            // RSI lookback
input int    RSIOversold            = 28;            // RSI oversold threshold
input int    RSIOverbought          = 72;            // RSI overbought threshold
input int    RSIExtremeOversold     = 20;            // Extreme oversold (+1 point)
input int    RSIExtremeOverbought   = 80;            // Extreme overbought (+1 point)
input int    RSINeutralLow          = 45;            // RSI neutral zone lower bound
input int    RSINeutralHigh         = 55;            // RSI neutral zone upper bound
input int    VWAPPeriod             = 50;            // Rolling lookback for VWAP std dev (bars)
input double VWAPStdDev             = 1.5;           // VWAP deviation threshold
input int    MinConfluenceScore     = 4;             // Min confluence to enter
input double BreakevenAtR           = 0.3;           // Move to BE at this R
input double FullCloseAtR           = 1.0;           // Full close at this R
input double TrailAtrMultiplier     = 0.3;           // Trail distance after BE (ATR multiple)
input int    AtrPeriod              = 14;            // ATR lookback
input double AtrSlMultiplier        = 1.5;           // Minimum SL distance in ATR
input double MinimumRR              = 1.0;           // Minimum R:R to enter
input string LondonSessionHoursUTC  = "07:00-10:00"; // London session bonus window (UTC)
input string NewYorkSessionHoursUTC = "12:00-15:00"; // NY session bonus window (UTC)
input int    SessionBonusPoints     = 1;             // Points added when in active session

//--- Foundational parameters (injected from ruleset — do not modify defaults) ---

input double f_AccountSize            = -1;   // USD account size for position sizing
input double f_RiskPerTradePct        = -1;   // % risk per trade (e.g. 1.0)
input double f_DailyLossCap           = -1;   // USD daily max loss
input double f_DailyHaltFraction      = -1;   // Halt new entries at this fraction of cap (0-1)
input int    f_MaxConsecutiveLosses   = -1;   // Halt after N consecutive losses (0 = disabled)
input double f_DailyProfitTarget      = -1;   // USD daily target (0 = disabled)
input double f_DailyProfitLockPct     = -1;   // Fraction of target where risk halves (0 = disabled)
input string f_EarliestEntryTimeET    = "";   // "HH:MM" or "" for no restriction
input string f_LatestEntryTimeET      = "";   // "HH:MM" or "" for no restriction
input string f_ForceFlatTimeET        = "";   // "HH:MM" or "" for no force flat
input string f_DaysOfWeekAllowed      = "";   // "sun,mon,tue,wed,thu,fri,sat" or ""
input double f_CommissionPerSide      = 0;    // Commission per side (informational)
input int    f_SlippageTicks          = 0;    // Slippage tolerance in ticks
input int    f_BrokerToEtOffsetHours  = 99;   // Override broker-to-ET offset hours (99 = auto-detect; see init log for detected value)

//--- Globals ---

CTrade trade;

int g_bbHandle  = INVALID_HANDLE;
int g_rsiHandle = INVALID_HANDLE;
int g_atrHandle = INVALID_HANDLE;

datetime g_lastBarTime       = 0;
double   g_dayStartBalance   = 0;
datetime g_lastDayDate       = 0;
int      g_consecutiveLosses = 0;
double   g_riskMultiplier    = 1.0;
bool     g_tradingHalted     = false;
double   g_balanceAtEntry    = 0;
double   g_riskAtEntry       = 0;   // risk in USD at trade open; used for R-based outcome classification

// Intraday VWAP accumulators — reset at broker midnight, backfilled at init
double g_vwapSumPV = 0;
double g_vwapSumV  = 0;

// Broker-to-ET offset in hours — computed in OnInit, overridden by f_BrokerToEtOffsetHours if != 99
int g_brokerToEtOffset = -5;

// Per-bar indicator cache (set by DetectSignal, consumed by EnterTrade)
double g_bbUpper  = 0;
double g_bbMiddle = 0;
double g_bbLower  = 0;
double g_bbStd    = 0;
double g_atr      = 0;
double g_rsiLast  = 0;

// Open trade state
struct TradeState {
   ulong  ticket;
   double entryPrice;
   double sl;
   double atrAtEntry;
   bool   beDone;
   double peakPrice;
   int    direction; // 1 = buy, -1 = sell
};

TradeState g_trade;
bool       g_inTrade = false;

//=============================================================================
// HELPERS
//=============================================================================

bool ParseHHMM(const string s, int &h, int &m) {
   if(StringLen(s) < 5) return false;
   h = (int)StringToInteger(StringSubstr(s, 0, 2));
   m = (int)StringToInteger(StringSubstr(s, 3, 2));
   return (h >= 0 && h <= 23 && m >= 0 && m <= 59);
}

bool IsInSessionRange(const string sessionStr, int utcMinutes) {
   int dash = StringFind(sessionStr, "-");
   if(dash < 0) return false;
   int sh, sm, eh, em;
   if(!ParseHHMM(StringSubstr(sessionStr, 0, dash),    sh, sm)) return false;
   if(!ParseHHMM(StringSubstr(sessionStr, dash + 1),   eh, em)) return false;
   return (utcMinutes >= sh * 60 + sm && utcMinutes < eh * 60 + em);
}

bool IsInActiveSession() {
   if(SessionBonusPoints == 0) return false;
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   int nowM = dt.hour * 60 + dt.min;
   if(StringLen(LondonSessionHoursUTC)  > 0 && IsInSessionRange(LondonSessionHoursUTC,  nowM)) return true;
   if(StringLen(NewYorkSessionHoursUTC) > 0 && IsInSessionRange(NewYorkSessionHoursUTC, nowM)) return true;
   return false;
}

//=============================================================================
// INTRADAY VWAP
//=============================================================================

// Backfill the intraday VWAP accumulators from today's already-completed bars.
// Called once in OnInit so the EA has a correct VWAP from the moment it starts.
void InitIntraDayVWAP() {
   g_vwapSumPV = 0;
   g_vwapSumV  = 0;
   MqlDateTime today;
   TimeToStruct(TimeCurrent(), today);

   int barsAdded = 0;
   for(int i = 1; i <= 2000; i++) {
      datetime barTime = iTime(Symbol(), PERIOD_CURRENT, i);
      if(barTime == 0) break;
      MqlDateTime barDt;
      TimeToStruct(barTime, barDt);
      if(barDt.year != today.year || barDt.mon != today.mon || barDt.day != today.day) break;

      double hi[1], lo[1], cl[1];
      long   vol[1];
      if(CopyHigh      (Symbol(), PERIOD_CURRENT, i, 1, hi)  != 1) break;
      if(CopyLow       (Symbol(), PERIOD_CURRENT, i, 1, lo)  != 1) break;
      if(CopyClose     (Symbol(), PERIOD_CURRENT, i, 1, cl)  != 1) break;
      if(CopyTickVolume(Symbol(), PERIOD_CURRENT, i, 1, vol) != 1) break;

      double tp = (hi[0] + lo[0] + cl[0]) / 3.0;
      g_vwapSumPV += tp * (double)vol[0];
      g_vwapSumV  += (double)vol[0];
      barsAdded++;
   }
   PrintFormat("VWAP init: backfilled %d bars | vwap=%.5f",
               barsAdded, g_vwapSumV > 0 ? g_vwapSumPV / g_vwapSumV : 0.0);
}

// Append the just-completed bar (index 1) to the intraday accumulators.
// Skips the bar if it belongs to a different day (guards against day-boundary ambiguity).
void UpdateIntraDayVWAP() {
   datetime barTime = iTime(Symbol(), PERIOD_CURRENT, 1);
   if(barTime == 0) return;

   MqlDateTime barDt, today;
   TimeToStruct(barTime,      barDt);
   TimeToStruct(TimeCurrent(), today);
   if(barDt.year != today.year || barDt.mon != today.mon || barDt.day != today.day) return;

   double hi[1], lo[1], cl[1];
   long   vol[1];
   if(CopyHigh      (Symbol(), PERIOD_CURRENT, 1, 1, hi)  != 1) return;
   if(CopyLow       (Symbol(), PERIOD_CURRENT, 1, 1, lo)  != 1) return;
   if(CopyClose     (Symbol(), PERIOD_CURRENT, 1, 1, cl)  != 1) return;
   if(CopyTickVolume(Symbol(), PERIOD_CURRENT, 1, 1, vol) != 1) return;

   double tp = (hi[0] + lo[0] + cl[0]) / 3.0;
   g_vwapSumPV += tp * (double)vol[0];
   g_vwapSumV  += (double)vol[0];
}

// Intraday VWAP mean (from accumulators) + rolling VWAPPeriod-bar std dev.
// Returns vwap=0, vwapStd=0 on insufficient data.
void CalcVWAP(double &vwap, double &vwapStd) {
   vwap    = 0;
   vwapStd = 0;

   if(g_vwapSumV < 1.0) return;
   vwap = g_vwapSumPV / g_vwapSumV;

   // Rolling VWAPPeriod-bar std dev — scale factor for the deviation threshold.
   // Uses the rolling weighted mean as its reference so it stays consistent over time.
   int n = VWAPPeriod;
   double hi[], lo[], cl[];
   long   vol[];
   ArraySetAsSeries(hi,  true);
   ArraySetAsSeries(lo,  true);
   ArraySetAsSeries(cl,  true);
   ArraySetAsSeries(vol, true);
   if(CopyHigh      (Symbol(), PERIOD_CURRENT, 1, n, hi)  < n) return;
   if(CopyLow       (Symbol(), PERIOD_CURRENT, 1, n, lo)  < n) return;
   if(CopyClose     (Symbol(), PERIOD_CURRENT, 1, n, cl)  < n) return;
   if(CopyTickVolume(Symbol(), PERIOD_CURRENT, 1, n, vol) < n) return;

   double sumPV2 = 0, sumV2 = 0;
   for(int i = 0; i < n; i++) {
      double tp = (hi[i] + lo[i] + cl[i]) / 3.0;
      sumPV2 += tp * (double)vol[i];
      sumV2  += (double)vol[i];
   }
   if(sumV2 == 0) return;
   double rollingMean = sumPV2 / sumV2;

   double sumSq = 0;
   for(int i = 0; i < n; i++) {
      double dev = cl[i] - rollingMean;
      sumSq += dev * dev;
   }
   vwapStd = MathSqrt(sumSq / n);
}

bool IsDayAllowed() {
   if(StringLen(f_DaysOfWeekAllowed) == 0) return true;
   const string days[] = {"sun", "mon", "tue", "wed", "thu", "fri", "sat"};
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   string allowed = f_DaysOfWeekAllowed;
   StringToLower(allowed);
   return StringFind(allowed, days[dt.day_of_week]) >= 0;
}

bool IsInTradingWindow() {
   if(StringLen(f_EarliestEntryTimeET) == 0 && StringLen(f_LatestEntryTimeET) == 0)
      return true;
   datetime etNow = (datetime)(TimeCurrent() + (long)g_brokerToEtOffset * 3600);
   MqlDateTime dt;
   TimeToStruct(etNow, dt);
   int nowM = dt.hour * 60 + dt.min;
   int h, m;
   if(StringLen(f_EarliestEntryTimeET) > 0 && ParseHHMM(f_EarliestEntryTimeET, h, m) && nowM < h * 60 + m) return false;
   if(StringLen(f_LatestEntryTimeET)   > 0 && ParseHHMM(f_LatestEntryTimeET,   h, m) && nowM > h * 60 + m) return false;
   return true;
}

//=============================================================================
// FOUNDATIONAL CHECKS
//=============================================================================

bool ValidateFoundationalParams() {
   bool ok = true;
   if(f_AccountSize           < 0) { Print("ERROR: f_AccountSize not injected");           ok = false; }
   if(f_RiskPerTradePct       < 0) { Print("ERROR: f_RiskPerTradePct not injected");       ok = false; }
   if(f_DailyLossCap          < 0) { Print("ERROR: f_DailyLossCap not injected");          ok = false; }
   if(f_DailyHaltFraction     < 0) { Print("ERROR: f_DailyHaltFraction not injected");     ok = false; }
   if(f_MaxConsecutiveLosses  < 0) { Print("ERROR: f_MaxConsecutiveLosses not injected");  ok = false; }
   if(f_DailyProfitTarget     < 0) { Print("ERROR: f_DailyProfitTarget not injected");     ok = false; }
   if(f_DailyProfitLockPct    < 0) { Print("ERROR: f_DailyProfitLockPct not injected");    ok = false; }
   return ok;
}

void CheckDayReset() {
   MqlDateTime now, last;
   TimeToStruct(TimeCurrent(),  now);
   TimeToStruct(g_lastDayDate, last);
   if(now.year == last.year && now.mon == last.mon && now.day == last.day) return;

   g_dayStartBalance   = AccountInfoDouble(ACCOUNT_BALANCE);
   g_lastDayDate       = TimeCurrent();
   g_consecutiveLosses = 0;
   g_riskMultiplier    = 1.0;
   g_tradingHalted     = false;
   g_vwapSumPV         = 0;
   g_vwapSumV          = 0;
   PrintFormat("New day %04d-%02d-%02d | balance=%.2f | VWAP accumulators reset",
               now.year, now.mon, now.day, g_dayStartBalance);
}

void UpdateRiskMultiplier() {
   if(f_DailyProfitTarget <= 0 || f_DailyProfitLockPct <= 0) return;
   double dayPnl = AccountInfoDouble(ACCOUNT_BALANCE) - g_dayStartBalance;
   double lockAt = f_DailyProfitTarget * f_DailyProfitLockPct;
   if(dayPnl >= lockAt && g_riskMultiplier > 0.5) {
      g_riskMultiplier = 0.5;
      PrintFormat("Profit lock-in: day P&L=%.2f >= threshold=%.2f. Risk halved.", dayPnl, lockAt);
   }
}

void CheckForceFlat() {
   if(StringLen(f_ForceFlatTimeET) == 0 || !g_inTrade) return;
   datetime etNow = (datetime)(TimeCurrent() + (long)g_brokerToEtOffset * 3600);
   MqlDateTime dt;
   TimeToStruct(etNow, dt);
   int nowM = dt.hour * 60 + dt.min;
   int h, m;
   if(ParseHHMM(f_ForceFlatTimeET, h, m) && nowM >= h * 60 + m) {
      if(!PositionSelectByTicket(g_trade.ticket)) return; // already closed (e.g. SL just hit); ManagePosition will reconcile
      if(trade.PositionClose(g_trade.ticket))
         Print("Force flat executed.");
      else
         PrintFormat("Force flat failed: retcode=%d", trade.ResultRetcode());
   }
}

bool CanEnter() {
   if(g_tradingHalted) return false;

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double dayLoss = g_dayStartBalance - balance;
   double haltAt  = f_DailyLossCap * f_DailyHaltFraction;
   if(dayLoss >= haltAt) {
      PrintFormat("Daily halt: loss=%.2f >= threshold=%.2f. No new entries.", dayLoss, haltAt);
      return false;
   }

   if(f_DailyProfitTarget > 0) {
      double dayPnl = balance - g_dayStartBalance;
      if(dayPnl >= f_DailyProfitTarget) {
         PrintFormat("Daily profit target %.2f reached. No new entries.", f_DailyProfitTarget);
         return false;
      }
   }

   if(!IsDayAllowed())      return false;
   if(!IsInTradingWindow()) return false;
   return true;
}

//=============================================================================
// LOT SIZING
//=============================================================================

double CalcLots(double slDistance) {
   double tickSize  = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_VALUE);
   if(tickSize == 0 || tickValue == 0 || slDistance == 0) return 0;

   double riskUSD = f_AccountSize * (f_RiskPerTradePct / 100.0) * g_riskMultiplier;
   double lots    = riskUSD / (slDistance / tickSize * tickValue);

   double lotStep = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_STEP);
   double minLot  = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MAX);

   lots = MathFloor(lots / lotStep) * lotStep;
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;
   return lots;
}

//=============================================================================
// SIGNAL DETECTION
//=============================================================================

// Returns the confluence score and sets outDirection (1 = bullish, -1 = bearish, 0 = none).
// Also caches g_bbUpper/Middle/Lower/Std, g_atr, g_rsiLast for use by EnterTrade.
int DetectSignal(int &outDirection) {
   outDirection = 0;

   double bbU[], bbM[], bbL[], rsiArr[], atrArr[];
   ArraySetAsSeries(bbU,    true);
   ArraySetAsSeries(bbM,    true);
   ArraySetAsSeries(bbL,    true);
   ArraySetAsSeries(rsiArr, true);
   ArraySetAsSeries(atrArr, true);

   if(CopyBuffer(g_bbHandle,  1, 1, 1, bbU)    < 1) return 0;
   if(CopyBuffer(g_bbHandle,  0, 1, 1, bbM)    < 1) return 0;
   if(CopyBuffer(g_bbHandle,  2, 1, 1, bbL)    < 1) return 0;
   if(CopyBuffer(g_rsiHandle, 0, 1, 1, rsiArr) < 1) return 0;
   if(CopyBuffer(g_atrHandle, 0, 1, 1, atrArr) < 1) return 0;

   double upper  = bbU[0];
   double middle = bbM[0];
   double lower  = bbL[0];
   double rsi    = rsiArr[0];
   double atr    = atrArr[0];
   double bbStd  = (upper - middle) / BBStdEntry;

   g_bbUpper  = upper;
   g_bbMiddle = middle;
   g_bbLower  = lower;
   g_bbStd    = bbStd;
   g_atr      = atr;
   g_rsiLast  = rsi;

   double vwap, vwapStd;
   CalcVWAP(vwap, vwapStd);

   double openArr[], closeArr[];
   ArraySetAsSeries(openArr,  true);
   ArraySetAsSeries(closeArr, true);
   if(CopyOpen (Symbol(), PERIOD_CURRENT, 1, 1, openArr)  < 1) return 0;
   if(CopyClose(Symbol(), PERIOD_CURRENT, 1, 1, closeArr) < 1) return 0;
   bool bullCandle = closeArr[0] > openArr[0];
   bool bearCandle = closeArr[0] < openArr[0];

   double price = (SymbolInfoDouble(Symbol(), SYMBOL_BID) +
                   SymbolInfoDouble(Symbol(), SYMBOL_ASK)) / 2.0;

   int sessionBonus = IsInActiveSession() ? SessionBonusPoints : 0;

   // --- Bullish scoring ---
   int score = 0;
   if(price < lower) {
      score += 2;
      if(price < lower - bbStd * 0.5) score += 1;
   }
   if(rsi < RSIOversold) {
      score += 2;
      if(rsi < RSIExtremeOversold) score += 1;
   }
   if(vwapStd > 0 && price < vwap - vwapStd * VWAPStdDev) score += 1;
   if(bullCandle) score += 1;
   score += sessionBonus;

   if(score >= MinConfluenceScore) {
      outDirection = 1;
      return score;
   }

   // --- Bearish scoring ---
   score = 0;
   if(price > upper) {
      score += 2;
      if(price > upper + bbStd * 0.5) score += 1;
   }
   if(rsi > RSIOverbought) {
      score += 2;
      if(rsi > RSIExtremeOverbought) score += 1;
   }
   if(vwapStd > 0 && price > vwap + vwapStd * VWAPStdDev) score += 1;
   if(bearCandle) score += 1;
   score += sessionBonus;

   if(score >= MinConfluenceScore) {
      outDirection = -1;
      return score;
   }

   return 0;
}

//=============================================================================
// POSITION MANAGEMENT (EXITS)
//=============================================================================

void OnPositionClosed() {
   // Classify outcome in R units to avoid counting breakeven stops as losses.
   // g_riskAtEntry stores the USD risk for this trade; balance delta / risk = R.
   double profitUSD = AccountInfoDouble(ACCOUNT_BALANCE) - g_balanceAtEntry;
   double profitR   = (g_riskAtEntry > 0) ? profitUSD / g_riskAtEntry : 0;

   if(profitR < -0.1) {
      g_consecutiveLosses++;
      PrintFormat("Trade closed at a loss (%.2fR). Consecutive losses: %d", profitR, g_consecutiveLosses);
      if(f_MaxConsecutiveLosses > 0 && g_consecutiveLosses >= f_MaxConsecutiveLosses) {
         g_tradingHalted = true;
         PrintFormat("HALT: %d consecutive losses reached. No new entries today.", g_consecutiveLosses);
      }
   } else if(profitR > 0.1) {
      if(g_consecutiveLosses > 0)
         PrintFormat("Win (%.2fR). Consecutive loss streak reset from %d.", profitR, g_consecutiveLosses);
      g_consecutiveLosses = 0;
   } else {
      PrintFormat("Breakeven (%.2fR). Consecutive loss counter unchanged at %d.", profitR, g_consecutiveLosses);
   }
   g_inTrade = false;
}

void ManagePosition() {
   if(!g_inTrade) return;

   if(!PositionSelectByTicket(g_trade.ticket)) {
      // Position is gone — closed by SL, TP, or external action
      OnPositionClosed();
      return;
   }

   double price  = PositionGetDouble(POSITION_PRICE_CURRENT);
   double sl     = PositionGetDouble(POSITION_SL);
   double tp     = PositionGetDouble(POSITION_TP);
   double slDist = MathAbs(g_trade.entryPrice - g_trade.sl);
   if(slDist == 0) return;

   double profitR = g_trade.direction == 1
      ? (price - g_trade.entryPrice) / slDist
      : (g_trade.entryPrice - price) / slDist;

   double guard = 2.0 * _Point;

   // Stage 1 — Breakeven at +BreakevenAtR
   if(profitR >= BreakevenAtR && !g_trade.beDone) {
      double newSl = NormalizeDouble(g_trade.entryPrice, _Digits);
      bool needsMove = (g_trade.direction == 1) ? sl < newSl - guard : sl > newSl + guard;
      if(needsMove) {
         if(trade.PositionModify(g_trade.ticket, newSl, tp))
            PrintFormat("BREAKEVEN | ticket=%I64u | SL=%.5f | profitR=%.2f", g_trade.ticket, newSl, profitR);
      }
      g_trade.beDone = true;
   }

   // Stage 2 — Full close at +FullCloseAtR
   if(profitR >= FullCloseAtR) {
      if(trade.PositionClose(g_trade.ticket))
         PrintFormat("FULL CLOSE @ %.2fR | ticket=%I64u", profitR, g_trade.ticket);
      else
         PrintFormat("Full close failed: retcode=%d", trade.ResultRetcode());
      OnPositionClosed();
      return;
   }

   // Stage 3 — Tight ATR trail after BE
   if(g_trade.beDone) {
      double trail = g_trade.atrAtEntry * TrailAtrMultiplier;
      double newSl;
      if(g_trade.direction == 1) {
         g_trade.peakPrice = MathMax(g_trade.peakPrice, price);
         newSl = NormalizeDouble(g_trade.peakPrice - trail, _Digits);
         if(newSl > sl + guard)
            trade.PositionModify(g_trade.ticket, newSl, tp);
      } else {
         g_trade.peakPrice = MathMin(g_trade.peakPrice, price);
         newSl = NormalizeDouble(g_trade.peakPrice + trail, _Digits);
         if(newSl < sl - guard)
            trade.PositionModify(g_trade.ticket, newSl, tp);
      }
   }

   // Stage 4 — Early close when RSI returns to neutral and trade is profitable
   double rsiArr[];
   ArraySetAsSeries(rsiArr, true);
   if(CopyBuffer(g_rsiHandle, 0, 1, 1, rsiArr) < 1) return;
   double rsi = rsiArr[0];
   if(rsi >= RSINeutralLow && rsi <= RSINeutralHigh && profitR > BreakevenAtR) {
      if(trade.PositionClose(g_trade.ticket))
         PrintFormat("EARLY CLOSE (RSI neutral %.1f) | ticket=%I64u | profitR=%.2f",
                     rsi, g_trade.ticket, profitR);
      else
         PrintFormat("Early close failed: retcode=%d", trade.ResultRetcode());
      OnPositionClosed();
   }
}

//=============================================================================
// ENTRY
//=============================================================================

void EnterTrade(const int direction) {
   double slBuffer = g_atr * AtrSlMultiplier;
   double entry, sl, slDist, tp;

   if(direction == 1) { // buy
      entry  = SymbolInfoDouble(Symbol(), SYMBOL_ASK);
      sl     = g_bbLower - slBuffer;
      slDist = entry - sl;
      tp     = g_bbMiddle;
   } else { // sell
      entry  = SymbolInfoDouble(Symbol(), SYMBOL_BID);
      sl     = g_bbUpper + slBuffer;
      slDist = sl - entry;
      tp     = g_bbMiddle;
   }

   // Floor SL distance to ATR minimum — prevents oversized lots when price barely crosses BB
   double minSlDist = g_atr * AtrSlMultiplier;
   if(slDist < minSlDist) {
      slDist = minSlDist;
      sl = direction == 1 ? entry - slDist : entry + slDist;
   }

   if(slDist <= 0) { Print("Invalid SL distance. Skipping entry."); return; }

   // R:R check
   double tpDist = MathAbs(tp - entry);
   double rr     = tpDist / slDist;
   if(rr < MinimumRR) {
      PrintFormat("R:R %.2f < MinimumRR %.2f. Skipping entry.", rr, MinimumRR);
      return;
   }

   double lots = CalcLots(slDist);
   if(lots <= 0) { Print("Lot size zero or invalid. Skipping entry."); return; }

   sl = NormalizeDouble(sl, _Digits);
   tp = NormalizeDouble(tp, _Digits);

   bool ok = (direction == 1)
      ? trade.Buy (lots, Symbol(), 0, sl, tp, "MeanReversion")
      : trade.Sell(lots, Symbol(), 0, sl, tp, "MeanReversion");

   if(ok) {
      // Locate position by symbol (netting account: one position per symbol)
      if(!PositionSelect(Symbol())) {
         Print("Entry placed but position not found immediately. State may be inconsistent.");
         return;
      }
      g_trade.ticket     = PositionGetInteger(POSITION_TICKET);
      g_trade.entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      g_trade.sl         = sl;
      g_trade.atrAtEntry = g_atr;
      g_trade.beDone     = false;
      g_trade.peakPrice  = g_trade.entryPrice;
      g_trade.direction  = direction;
      g_inTrade          = true;
      g_balanceAtEntry   = AccountInfoDouble(ACCOUNT_BALANCE);
      g_riskAtEntry      = f_AccountSize * (f_RiskPerTradePct / 100.0) * g_riskMultiplier;

      PrintFormat("ENTRY | %s | lots=%.2f | entry=%.5f | SL=%.5f | TP=%.5f | R:R=%.2f | RSI=%.1f | risk=%.2f",
                  direction == 1 ? "BUY" : "SELL",
                  lots, g_trade.entryPrice, sl, tp, rr, g_rsiLast, g_riskAtEntry);
   } else {
      PrintFormat("Order failed: retcode=%d %s",
                  trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}

//=============================================================================
// EA LIFECYCLE
//=============================================================================

int OnInit() {
   if(!ValidateFoundationalParams()) {
      Print("INIT FAILED: one or more foundational parameters are at placeholder values. "
            "Ensure the lab dispatcher has injected all f_ parameters before running.");
      return INIT_FAILED;
   }

   // Broker-to-ET offset: auto-detect unless overridden
   if(f_BrokerToEtOffsetHours != 99) {
      g_brokerToEtOffset = f_BrokerToEtOffsetHours;
      PrintFormat("Broker-to-ET offset: %d hours (manual override via f_BrokerToEtOffsetHours)",
                  g_brokerToEtOffset);
   } else {
      int brokerOffsetUTC = (int)((TimeTradeServer() - TimeGMT()) / 3600);
      int etOffsetUTC     = -5; // ET standard time (UTC-5); most brokers handle DST automatically
      g_brokerToEtOffset  = etOffsetUTC - brokerOffsetUTC;
      PrintFormat("Broker-to-ET offset: %d hours (auto-detected: broker=UTC%+d, ET=UTC%+d)",
                  g_brokerToEtOffset, brokerOffsetUTC, etOffsetUTC);
   }

   g_bbHandle  = iBands (Symbol(), PERIOD_CURRENT, BBPeriod, 0, BBStdEntry, PRICE_CLOSE);
   g_rsiHandle = iRSI   (Symbol(), PERIOD_CURRENT, RSIPeriod, PRICE_CLOSE);
   g_atrHandle = iATR   (Symbol(), PERIOD_CURRENT, AtrPeriod);

   if(g_bbHandle  == INVALID_HANDLE ||
      g_rsiHandle == INVALID_HANDLE ||
      g_atrHandle == INVALID_HANDLE) {
      Print("INIT FAILED: could not create one or more indicator handles.");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(20240002);
   trade.SetDeviationInPoints(f_SlippageTicks);

   g_dayStartBalance   = AccountInfoDouble(ACCOUNT_BALANCE);
   g_lastDayDate       = TimeCurrent();
   g_lastBarTime       = 0;
   g_consecutiveLosses = 0;
   g_riskMultiplier    = 1.0;
   g_tradingHalted     = false;
   g_inTrade           = false;

   InitIntraDayVWAP();

   PrintFormat("MeanReversion initialized | symbol=%s | TF=%s | "
               "account_size=%.2f | risk=%.2f%% | daily_cap=%.2f",
               Symbol(), EnumToString(Period()),
               f_AccountSize, f_RiskPerTradePct, f_DailyLossCap);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
   if(g_bbHandle  != INVALID_HANDLE) IndicatorRelease(g_bbHandle);
   if(g_rsiHandle != INVALID_HANDLE) IndicatorRelease(g_rsiHandle);
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
}

void OnTick() {
   // Force flat is time-critical — check every tick, not just bar close
   CheckForceFlat();

   // All other logic runs once per completed bar
   datetime barTime = iTime(Symbol(), PERIOD_CURRENT, 0);
   if(barTime == g_lastBarTime) return;
   g_lastBarTime = barTime;

   CheckDayReset();        // resets VWAP accumulators on day rollover
   UpdateIntraDayVWAP();   // append the just-completed bar to intraday VWAP
   UpdateRiskMultiplier();

   // Exit management runs regardless of halt or gate state
   ManagePosition();

   // No new entry while a position is open
   if(g_inTrade) return;

   // Foundational entry gates
   if(!CanEnter()) return;

   // Signal
   int direction = 0;
   int score     = DetectSignal(direction);
   if(score < MinConfluenceScore || direction == 0) return;

   PrintFormat("SIGNAL | %s | score=%d | RSI=%.1f | BB_upper=%.5f | BB_lower=%.5f",
               direction == 1 ? "BULLISH" : "BEARISH",
               score, g_rsiLast, g_bbUpper, g_bbLower);

   EnterTrade(direction);
}
