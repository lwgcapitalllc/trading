//+------------------------------------------------------------------+
//|                                             LondonBreakout.mq5    |
//|                                                LWG Capital LLC    |
//+------------------------------------------------------------------+
// London session breakout — reshaped to the LWG gated-layer rules (v3).
//
// Gated-layer rules (docs/LWG_Strategy_Framework.md, docs/dynamic_sizing_engine.md):
//   NO STRATEGY KNOWS HOW TO MANAGE RISK. LondonBreakout proposes setups at UNIT
//   size (the broker's minimum lot). It does NOT size off the account, halt on a
//   daily-loss cap, stop at a profit target, lock in profit, count consecutive
//   losses, or pull stops to break-even — every one of those decisions belongs to
//   the dynamic sizing & gating engine, which sizes and grades the run OFFLINE
//   from the per-trade record this EA emits.
//
//   It keeps only what is part of its edge: the entry signal (bar-close break or
//   pending-stop OCO), the stop, the target, and the time rules that define WHEN
//   the setup is valid (session windows, entry cutoff, force-flat). It emits one
//   row per closed trade — the runner→engine contract — to engine_trades.csv in
//   the tester's MQL5\Files folder: index, entry/exit time + price, direction,
//   stop_distance, point_value, commission_per_side, exit_reason. The command-center
//   MT5 agent ships that file; the engine (services/sizing_engine.py via
//   sizing_pipeline.py) reads it and decides size per ruleset.
//
//   UNIT = the broker's minimum lot (SYMBOL_VOLUME_MIN). It is the forex analog of
//   "1 micro contract": always tradeable and the finest legal granularity, so the
//   engine's integer sizing has the most resolution. point_value is reported for
//   that unit (value of one price point for one min-lot), so risk_per_contract =
//   stop_distance × point_value is the USD risk of one unit trade.
//
//   The MT5 Strategy Tester's own report is the UNIT-SIZE reference (one min-lot per
//   trade); the engine's sized daily P&L is authoritative for grading.
//
// Idea: the Asian session (00:00-06:00 GMT) sets a quiet reference range. At the
//   London open price often breaks that range and continues. We mark the Asian
//   high/low, wait for a bar-close break past a small buffer (or arm pending stops),
//   take ONE trade per day in the break direction, and are flat by late London.
//
// This file is fully INSTRUMENT-AGNOSTIC. No symbol, no pip value, and no per-pair
//   number is baked in. Everything per-instrument is read from the broker
//   (SymbolInfo) or expressed as a multiple of the instrument's own ATR, so the
//   same file runs on AUDJPY, CADJPY, USDJPY, or XAUUSD unchanged.
//
// Timezone is fully automatic — there is NO manual offset. Session windows are GMT;
//   the broker→GMT offset is derived live from the broker (TimeTradeServer vs
//   TimeGMT) and recomputed every bar, DST-safe on both sides.
//+------------------------------------------------------------------+
#property copyright "LWG Capital LLC"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

#define MAGIC_NUMBER 20240003

//--- Strategy logic parameters (Layer A — tunable by optimizer) ---
// Session windows are in GMT. They define the strategy, not the instrument, so
// they are the same for every pair. Times are "HH:MM", DST-safe (the EA derives
// the broker↔GMT offset live, see BrokerToGmtSec).
input string AsianStartGMT   = "00:00";   // [group: Session Windows] Asian range window start (GMT)
input string AsianEndGMT     = "06:00";   // [group: Session Windows] Asian range window end (GMT, exclusive)
input string LondonOpenGMT   = "07:00";   // [group: Session Windows] start watching for the break (GMT)
input string EntryCutoffGMT  = "09:00";   // [group: Session Windows] last bar we may enter on (GMT, exclusive)
input string ForceFlatGMT    = "11:00";   // [group: Session Windows] close any open trade at/after this (GMT)

// Volatility scale — everything per-pair is expressed against this ATR.
input int    AtrPeriod       = 14;        // ATR lookback, on the DAILY timeframe
input double RangeMinAtr     = 0.5;       // skip day if Asian range < this x ATR
input double RangeMaxAtr     = 1.3;       // skip day if Asian range > this x ATR
input double BufferAtr       = 0.1;       // breakout buffer = this x ATR beyond the range
input double TargetRR        = 2.0;       // target as a multiple of the stop distance (spec 2:1)

//--- Entry-shaping toggles (part of the SIGNAL — kept; each INDEPENDENT, default OFF) ---
// These change WHICH setup triggers and HOW it is entered, so they belong to the
// strategy's edge, not to risk management. All pip distances derive from the
// broker's point size via PipSize(); the word "pip" is never a hardcoded number.

// 1. Entry model. OFF = bar-close market entry using the ATR buffer.
//    ON  = pending stop orders at the breakout levels (OCO: first fill cancels the
//          other; both cancelled if neither fills by EntryCutoffGMT). The buffer
//          switches to a fixed pip distance (BufferPips).
input bool   PendingEntry    = false;     // false = bar-close market; true = pending stop OCO
input double BufferPips       = 5.0;      // breakout buffer in pips, used only when PendingEntry=true

// 2. Range filter. OFF = ATR band (RangeMin/MaxAtr). ON = fixed pip band.
input bool   PipRangeFilter  = false;     // false = ATR band; true = fixed pip band
input double RangeMinPips      = 15.0;    // reject day if Asian range < this (pips)
input double RangeMaxPips      = 40.0;    // reject day if Asian range > this (pips)
input double SweetMinPips      = 20.0;    // sweet-spot lower bound (logged, not a gate)
input double SweetMaxPips      = 35.0;    // sweet-spot upper bound (logged, not a gate)

//--- Foundational parameters (cost + execution only — injected by the lab dispatcher) ---
// Account-governance foundational params (account size, risk %, daily-loss cap,
// halt fraction, consecutive-loss limit, profit target, profit lock-in) were
// REMOVED — the engine owns every one of those decisions now. Only the cost and
// the execution-deviation facts remain. f_CommissionPerSide is recorded into the
// per-trade contract so the engine prices the sized run; it is informational for
// the tester's own report (spread is the live cost there).
input double f_CommissionPerSide     = 0;    // commission per side ($/lot-side; recorded into the contract)
input int    f_SlippageTicks         = 0;    // deviation tolerance in points

//--- Globals ---
CTrade trade;

int g_atrHandle = INVALID_HANDLE;

datetime g_lastBarTime = 0;

// Session window minutes-of-day (GMT), parsed once in OnInit.
int g_asianStartMin  = 0;
int g_asianEndMin    = 0;
int g_londonOpenMin  = 0;
int g_entryCutoffMin = 0;
int g_forceFlatMin   = 0;

// Unit size — the broker minimum lot. Every proposed trade is exactly this size;
// the engine resizes offline. Resolved once in OnInit.
double g_unitLots    = 0;
double g_pointValue  = 0;   // $ per 1.0 price point per unit lot (recorded into the contract)

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

// Open trade state.
ulong  g_ticket       = 0;
long   g_positionId   = 0;       // POSITION_IDENTIFIER — keys history lookup on close
bool   g_inTrade      = false;

// Per-trade record state (built at entry, completed at exit).
datetime g_entryTime   = 0;
double   g_entryPrice  = 0;       // fill price of the open trade
double   g_stopDist    = 0;       // price distance entry->stop at open (the contract's stop_distance)
int      g_dir         = 0;       // +1 long / -1 short

// Pending-order state (PendingEntry mode). 0 = no live order on that side.
ulong  g_buyStopTicket  = 0;
ulong  g_sellStopTicket = 0;
bool   g_pendingPlaced  = false;

// Per-trade record rows (the runner→engine contract) and the diagnostic counters.
string g_tradeRows[];            // one CSV line per closed trade
int    g_recordIndex = 0;

int      g_qualifyingDays = 0;   // days the range filter passed (levels live)
int      g_bothSidedDays  = 0;   // qualifying days with >= 1 both-sided bar
int      g_bothSidedBars  = 0;   // total both-sided bars across all qualifying days
int      g_sweetSpotDays  = 0;   // qualifying days whose range fell in the pip sweet spot
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

// Broker server time minus GMT, derived live from the broker each call and snapped
// to the nearest minute. Recomputing per call (not caching at init) tracks a DST
// shift on EITHER side automatically — no stored offset to go stale.
int BrokerToGmtSec() {
   long raw = (long)TimeTradeServer() - (long)TimeGMT();
   return (int)((long)MathRound((double)raw / 60.0) * 60);
}

datetime ToGmt(const datetime brokerTime) {
   return (datetime)((long)brokerTime - (long)BrokerToGmtSec());
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

// ISO-8601 of a broker-server time (no offset) — the per-trade record's timestamps.
// The engine buckets days off entry_time; using the broker clock keeps the engine's
// day boundaries aligned with the tester report the agent parses for the unit-size
// reference.
string IsoTime(const datetime brokerTime) {
   MqlDateTime dt;
   TimeToStruct(brokerTime, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d",
                       dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

// Daily ATR of the last COMPLETED daily bar (shift 1 — no look-ahead). 0 if unavailable.
double DailyAtr() {
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_atrHandle, 0, 1, 1, atr) < 1) return 0;
   return atr[0];
}

// One pip in price terms, derived from the broker — 10 points on 3/5-digit quotes,
// 1 point otherwise. No hardcoded pip.
double PipSize() {
   return ((_Digits == 3 || _Digits == 5) ? 10.0 : 1.0) * _Point;
}

// Value of one price point for one UNIT lot, in account currency. tickValue is the
// value of one tick for 1.0 lot; per-point for 1.0 lot = tickValue/tickSize; scale
// to the unit lot. Returns 0 if the broker doesn't expose the tick economics.
double UnitPointValue() {
   double tickSize  = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0 || tickValue <= 0 || g_unitLots <= 0) return 0;
   return (tickValue / tickSize) * g_unitLots;
}

// Reset the session-day state. (No foundational daily-risk state remains — the
// engine owns daily loss, profit target, halts and consecutive-loss limits.)
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

   CancelPendingOrders();   // safety: drop any pending order left from the prior day
   g_pendingPlaced = false;
}

//=============================================================================
// PER-TRADE RECORD (the runner→engine contract)
//=============================================================================

// Capture the open trade's contract fields. Direction, fill price, stop distance
// and entry time are fixed at entry; the exit fields are filled in on close.
void BeginTradeRecord(const int direction, const double entryPrice,
                      const double slDistPrice, const datetime entryTime) {
   g_dir        = direction;
   g_entryPrice = entryPrice;
   g_stopDist   = MathAbs(slDistPrice);
   g_entryTime  = entryTime;
}

// Append one closed trade to the per-trade record. Columns mirror ORB.cs exactly:
//   index,entry_time,exit_time,direction,entry_price,exit_price,
//   stop_distance,point_value,commission_per_side,exit_reason
void RecordClosedTrade(const double exitPrice, const datetime exitTime,
                       const string exitReason) {
   g_recordIndex++;
   string safeReason = exitReason;
   StringReplace(safeReason, "\"", "'");
   string row = StringFormat(
      "%d,%s,%s,%s,%s,%s,%s,%s,%s,\"%s\"",
      g_recordIndex,
      IsoTime(g_entryTime),
      IsoTime(exitTime),
      g_dir == 1 ? "Long" : "Short",
      DoubleToString(g_entryPrice, _Digits),
      DoubleToString(exitPrice,    _Digits),
      DoubleToString(g_stopDist,   _Digits),
      DoubleToString(g_pointValue, 2),
      DoubleToString(f_CommissionPerSide, 2),
      safeReason);
   int n = ArraySize(g_tradeRows);
   ArrayResize(g_tradeRows, n + 1);
   g_tradeRows[n] = row;
}

// Write the per-trade record the engine consumes, to the tester's MQL5\Files folder
// (same place OnTesterPass writes opt_results.csv — the agent reads it back from
// there after the run). Single instrument/run, so the file is overwritten each run.
void WriteTradeRecords() {
   if(ArraySize(g_tradeRows) == 0) return;
   int fh = FileOpen("engine_trades.csv", FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE) { Print("engine_trades: cannot write file."); return; }
   FileWrite(fh,
      "index", "entry_time", "exit_time", "direction", "entry_price", "exit_price",
      "stop_distance", "point_value", "commission_per_side", "exit_reason");
   for(int i = 0; i < ArraySize(g_tradeRows); i++) {
      // Each row is already a comma-joined CSV line; write it verbatim.
      FileWriteString(fh, g_tradeRows[i] + "\r\n");
   }
   FileClose(fh);
   PrintFormat("engine_trades: wrote %d rows.", ArraySize(g_tradeRows));
}

//=============================================================================
// ENTRY
//=============================================================================

void EnterTrade(const int direction) {
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

   double minStop = (double)SymbolInfoInteger(Symbol(), SYMBOL_TRADE_STOPS_LEVEL) * point;
   if(slDist < minStop) {
      PrintFormat("SL distance %.1f pts < broker min %.1f pts. Skipping entry.",
                  slDist / point, minStop / point);
      return;
   }

   sl = NormalizeDouble(sl, _Digits);
   tp = NormalizeDouble(tp, _Digits);

   bool ok = (direction == 1)
      ? trade.Buy (g_unitLots, Symbol(), 0, sl, tp, "LondonBreakout")
      : trade.Sell(g_unitLots, Symbol(), 0, sl, tp, "LondonBreakout");

   if(ok && PositionSelect(Symbol())) {
      g_ticket      = PositionGetInteger(POSITION_TICKET);
      g_positionId  = PositionGetInteger(POSITION_IDENTIFIER);
      g_inTrade     = true;
      g_tradedToday = true;
      double open   = PositionGetDouble(POSITION_PRICE_OPEN);
      BeginTradeRecord(direction, open, open - sl, (datetime)PositionGetInteger(POSITION_TIME));
      PrintFormat("ENTRY | %s | lots=%.2f | entry=%.5f | SL=%.5f | TP=%.5f | stop=%.1f pts",
                  direction == 1 ? "BUY" : "SELL", g_unitLots, open, sl, tp, slDist / point);
   } else {
      g_tradedToday = true;   // do not retry the same break
      PrintFormat("Order failed: retcode=%d %s",
                  trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}

//=============================================================================
// PENDING-ORDER ENTRY (PendingEntry mode)
//=============================================================================

// Arm both breakout stop orders for a qualifying day. Buy stop at the upper level,
// sell stop at the lower; first to fill is the trade, the other is cancelled in
// ManagePending (OCO). Both cancelled if neither fills by the entry cutoff. Unit
// size per side — the engine resizes offline.
void PlacePendingOrders() {
   double point    = _Point;
   double buyPx    = NormalizeDouble(g_buyLevel,  _Digits);
   double sellPx   = NormalizeDouble(g_sellLevel, _Digits);
   double buySl    = NormalizeDouble(g_asianLow,  _Digits);
   double sellSl   = NormalizeDouble(g_asianHigh, _Digits);
   double buyDist  = buyPx - buySl;
   double sellDist = sellSl - sellPx;
   if(buyDist <= 0 || sellDist <= 0) { Print("Pending: invalid stop distance, skipping day."); return; }

   double minStop = (double)SymbolInfoInteger(Symbol(), SYMBOL_TRADE_STOPS_LEVEL) * point;
   if(buyDist < minStop || sellDist < minStop) {
      PrintFormat("Pending: stop distance below broker min %.1f pts, skipping day.", minStop / point);
      return;
   }

   double buyTp  = NormalizeDouble(buyPx  + buyDist  * TargetRR, _Digits);
   double sellTp = NormalizeDouble(sellPx - sellDist * TargetRR, _Digits);

   if(trade.BuyStop(g_unitLots, buyPx, Symbol(), buySl, buyTp, ORDER_TIME_GTC, 0, "LondonBreakout"))
      g_buyStopTicket = trade.ResultOrder();
   else
      PrintFormat("BuyStop failed: retcode=%d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());

   if(trade.SellStop(g_unitLots, sellPx, Symbol(), sellSl, sellTp, ORDER_TIME_GTC, 0, "LondonBreakout"))
      g_sellStopTicket = trade.ResultOrder();
   else
      PrintFormat("SellStop failed: retcode=%d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());

   g_pendingPlaced = true;
   PrintFormat("Pending armed | buyStop=%.5f (sl=%.5f tp=%.5f) | sellStop=%.5f (sl=%.5f tp=%.5f)",
               buyPx, buySl, buyTp, sellPx, sellSl, sellTp);
}

void CancelPendingOrders() {
   if(g_buyStopTicket != 0) {
      if(OrderSelect(g_buyStopTicket)) trade.OrderDelete(g_buyStopTicket);
      g_buyStopTicket = 0;
   }
   if(g_sellStopTicket != 0) {
      if(OrderSelect(g_sellStopTicket)) trade.OrderDelete(g_sellStopTicket);
      g_sellStopTicket = 0;
   }
}

// Record the position created when a stop order fills, then mark the day traded.
void RegisterPendingFill() {
   g_ticket      = PositionGetInteger(POSITION_TICKET);
   g_positionId  = PositionGetInteger(POSITION_IDENTIFIER);
   g_inTrade     = true;
   g_tradedToday = true;
   double open   = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl     = PositionGetDouble(POSITION_SL);
   int    dir    = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   BeginTradeRecord(dir, open, open - sl, (datetime)PositionGetInteger(POSITION_TIME));
   PrintFormat("Pending FILL | ticket=%s | entry=%.5f | stop=%.1f pts",
               IntegerToString(g_ticket), open, MathAbs(open - sl) / _Point);
}

// Per-tick lifecycle for the pending orders: detect a fill (OCO-cancel the other
// side) or cancel both once the entry cutoff passes with no fill.
void ManagePending() {
   if(!PendingEntry || g_tradedToday || !g_pendingPlaced) return;

   if(PositionSelect(Symbol()) && PositionGetInteger(POSITION_MAGIC) == MAGIC_NUMBER) {
      RegisterPendingFill();      // one side filled
      CancelPendingOrders();      // OCO — drop the other side
      return;
   }

   if(GmtMinuteOfDay(TimeCurrent()) >= g_entryCutoffMin) {
      CancelPendingOrders();      // neither triggered in the window
      g_pendingPlaced = false;    // done for the day
   }
}

//=============================================================================
// EXITS
//=============================================================================

// The position is gone — find its closing (out) deal in history to recover the
// exit price/time/reason, then append the per-trade record. Works in the tester.
void RecordCloseFromHistory() {
   double   exitPrice = g_entryPrice;
   datetime exitTime  = TimeCurrent();
   string   reason    = "Close";

   if(g_positionId != 0 && HistorySelectByPosition(g_positionId)) {
      int deals = HistoryDealsTotal();
      for(int i = deals - 1; i >= 0; i--) {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0) continue;
         if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
         exitPrice = HistoryDealGetDouble(ticket, DEAL_PRICE);
         exitTime  = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
         long dr   = HistoryDealGetInteger(ticket, DEAL_REASON);
         if(dr == DEAL_REASON_SL)      reason = "StopLoss";
         else if(dr == DEAL_REASON_TP) reason = "ProfitTarget";
         else                          reason = "Close";
         break;
      }
   }
   RecordClosedTrade(exitPrice, exitTime, reason);
}

void OnPositionClosed() {
   RecordCloseFromHistory();
   g_inTrade     = false;
   g_ticket      = 0;
   g_positionId  = 0;
}

// Force flat at/after ForceFlatGMT — time-critical, checked every tick. The exit is
// recorded by ManageOpen once the position is actually gone.
void CheckForceFlat() {
   if(!g_inTrade) return;
   if(GmtMinuteOfDay(TimeCurrent()) < g_forceFlatMin) return;
   if(!PositionSelectByTicket(g_ticket)) return;   // already gone; ManageOpen reconciles
   if(trade.PositionClose(g_ticket)) Print("Force flat executed.");
   else PrintFormat("Force flat failed: retcode=%d", trade.ResultRetcode());
}

void ManageOpen() {
   if(!g_inTrade) return;
   if(!PositionSelectByTicket(g_ticket)) OnPositionClosed();   // SL/TP/force-flat took it
}

//=============================================================================
// DIAGNOSTIC OUTPUT (research only — independent of trading)
//=============================================================================

void WriteDiagnostic() {
   double pct = (g_qualifyingDays > 0)
                ? 100.0 * (double)g_bothSidedDays / (double)g_qualifyingDays : 0.0;

   PrintFormat("BOTHSIDED_DIAG | symbol=%s | qualifying_days=%d | sweet_spot_days=%d | "
               "both_sided_days=%d | both_sided_bars=%d | pct_days=%.2f",
               Symbol(), g_qualifyingDays, g_sweetSpotDays, g_bothSidedDays, g_bothSidedBars, pct);

   string fname = "LondonBreakout_diag_" + Symbol() + ".csv";
   int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE) { PrintFormat("Diag: cannot write %s", fname); return; }
   FileWrite(fh, "metric", "value");
   FileWrite(fh, "symbol", Symbol());
   FileWrite(fh, "qualifying_days", g_qualifyingDays);
   FileWrite(fh, "sweet_spot_days", g_sweetSpotDays);
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
      double atr   = DailyAtr();
      double range = g_asianHigh - g_asianLow;
      double pip   = PipSize();

      bool needAtr = (!PipRangeFilter) || (!PendingEntry);

      if(needAtr && atr <= 0) {
         Print("Range filter: ATR unavailable, skipping day.");
      } else {
         bool qualifies;
         if(PipRangeFilter) {
            double rpips = range / pip;
            qualifies = (rpips >= RangeMinPips && rpips <= RangeMaxPips);
            if(!qualifies)
               PrintFormat("Range filter: skip %s | range=%.1f pips | band=[%.1f,%.1f] pips",
                           GmtDateString(bt), rpips, RangeMinPips, RangeMaxPips);
         } else {
            qualifies = (range >= RangeMinAtr * atr && range <= RangeMaxAtr * atr);
            if(!qualifies)
               PrintFormat("Range filter: skip %s | range=%.1f pts | atr=%.1f pts | band=[%.2f,%.2f]xATR",
                           GmtDateString(bt), range / _Point, atr / _Point, RangeMinAtr, RangeMaxAtr);
         }

         if(qualifies) {
            g_dayQualifies = true;
            double buf  = PendingEntry ? (BufferPips * pip) : (BufferAtr * atr);
            g_buyLevel  = g_asianHigh + buf;
            g_sellLevel = g_asianLow  - buf;
            g_qualifyingDays++;

            if(PipRangeFilter) {
               double rpips = range / pip;
               if(rpips >= SweetMinPips && rpips <= SweetMaxPips) {
                  g_sweetSpotDays++;
                  PrintFormat("SWEETSPOT %s | range=%.1f pips", GmtDateString(bt), rpips);
               }
            }

            PrintFormat("Levels %s | buy=%.5f | sell=%.5f | range=%.1f pts | buffer=%s",
                        GmtDateString(bt), g_buyLevel, g_sellLevel, range / _Point,
                        PendingEntry ? "pips" : "atr");

            if(PendingEntry) PlacePendingOrders();
         }
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

      // Entry (PendingEntry=OFF) — bar close past a level, one trade per day.
      // With PendingEntry=ON the stop orders own entry, so skip the market path.
      // No risk gate here — the engine decides whether/how big this setup trades.
      if(!PendingEntry && !g_tradedToday && !g_inTrade) {
         if(cl > g_buyLevel)       EnterTrade(1);
         else if(cl < g_sellLevel) EnterTrade(-1);
      }
   }
}

//=============================================================================
// EA LIFECYCLE
//=============================================================================

int OnInit() {
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

   // Unit size = broker minimum lot, normalized to the volume step. The engine
   // resizes offline; the EA always proposes this fixed reference size.
   double minLot  = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MIN);
   double lotStep = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_STEP);
   if(minLot <= 0 || lotStep <= 0) {
      Print("INIT FAILED: broker did not expose a valid minimum lot / step.");
      return INIT_FAILED;
   }
   g_unitLots   = MathRound(minLot / lotStep) * lotStep;
   if(g_unitLots < minLot) g_unitLots = minLot;
   g_pointValue = UnitPointValue();
   if(g_pointValue <= 0)
      Print("WARNING: unit point value is 0 (broker tick economics unavailable) — "
            "the engine cannot price this run until it is resolved.");

   PrintFormat("Broker->GMT offset at init: %d min (server=%s, gmt=%s). Auto-derived & DST-aware.",
               BrokerToGmtSec() / 60,
               TimeToString(TimeTradeServer(), TIME_DATE | TIME_MINUTES),
               TimeToString(TimeGMT(), TIME_DATE | TIME_MINUTES));

   g_atrHandle = iATR(Symbol(), PERIOD_D1, AtrPeriod);
   if(g_atrHandle == INVALID_HANDLE) {
      Print("INIT FAILED: could not create daily ATR handle.");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(MAGIC_NUMBER);
   trade.SetDeviationInPoints(f_SlippageTicks);

   g_lastBarTime    = 0;
   g_curDayYmd      = 0;
   g_inTrade        = false;
   g_positionId     = 0;
   g_recordIndex    = 0;
   g_qualifyingDays = 0;
   g_sweetSpotDays  = 0;
   g_bothSidedDays  = 0;
   g_bothSidedBars  = 0;
   g_buyStopTicket  = 0;
   g_sellStopTicket = 0;
   g_pendingPlaced  = false;
   ArrayResize(g_bothSidedDates, 0);
   ArrayResize(g_tradeRows, 0);

   PrintFormat("LondonBreakout init | symbol=%s | TF=%s | unit=%.2f lots | pointValue=%.2f | "
               "commission/side=%.2f (recorded into the contract)",
               Symbol(), EnumToString(Period()), g_unitLots, g_pointValue, f_CommissionPerSide);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   WriteTradeRecords();   // ship the per-trade record (the runner→engine contract)
   WriteDiagnostic();
}

//=============================================================================
// OPTIMIZATION CALLBACKS
// Only invoked when the terminal runs with Optimization=1. The command-center MT5
// agent reads opt_results.csv after the run; KPI column names must match its parser
// (_parse_opt_csv / _OPT_KPI_COLS) and the param column names must match the
// optimization grid keys.
//=============================================================================

#define OPT_CSV       "opt_results.csv"
#define OPT_DATA_SIZE 13   // 5 numeric params + 8 KPI stats

void OnTesterInit()
{
    int fh = FileOpen(OPT_CSV, FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
    if(fh == INVALID_HANDLE) { Print("OnTesterInit: cannot create ", OPT_CSV); return; }
    FileWrite(fh,
        "AtrPeriod","RangeMinAtr","RangeMaxAtr","BufferAtr","TargetRR",
        "net_pnl","profit_factor","max_drawdown","trade_count",
        "win_trades","sharpe","gross_profit","gross_loss");
    FileClose(fh);
}

double OnTester()
{
    double data[OPT_DATA_SIZE];
    data[0]  = (double)AtrPeriod;
    data[1]  = RangeMinAtr;
    data[2]  = RangeMaxAtr;
    data[3]  = BufferAtr;
    data[4]  = TargetRR;
    data[5]  = TesterStatistics(STAT_PROFIT);
    data[6]  = TesterStatistics(STAT_PROFIT_FACTOR);
    data[7]  = TesterStatistics(STAT_EQUITY_DD);
    data[8]  = TesterStatistics(STAT_TRADES);
    data[9]  = TesterStatistics(STAT_PROFIT_TRADES);
    data[10] = TesterStatistics(STAT_SHARPE_RATIO);
    data[11] = TesterStatistics(STAT_GROSS_PROFIT);
    data[12] = TesterStatistics(STAT_GROSS_LOSS);
    FrameAdd("r", 0, data[6], data);
    return data[6];
}

void OnTesterPass()
{
    ulong  pass = 0;
    string name;
    long   id;
    double value;
    double data[];
    while(FrameNext(pass, name, id, value, data))
    {
        if(name != "r" || ArraySize(data) < OPT_DATA_SIZE) continue;
        int fh = FileOpen(OPT_CSV, FILE_WRITE|FILE_READ|FILE_CSV|FILE_ANSI, ',');
        if(fh == INVALID_HANDLE) continue;
        FileSeek(fh, 0, SEEK_END);
        FileWrite(fh,
            (int)data[0],  data[1],       data[2],       data[3],       data[4],
            data[5],       data[6],       data[7],       (int)data[8],
            (int)data[9],  data[10],      data[11],      data[12]);
        FileClose(fh);
    }
}

void OnTesterDeinit()
{
    Print("LondonBreakout: optimization complete.");
}

void OnTick() {
   CheckForceFlat();                         // time-critical, every tick
   ManagePending();                          // OCO + cutoff cancel; no-op unless PendingEntry

   datetime barTime = iTime(Symbol(), PERIOD_CURRENT, 0);
   if(barTime == g_lastBarTime) return;      // act only on a new completed bar
   g_lastBarTime = barTime;

   ManageOpen();
   OnClosedBar();
}
